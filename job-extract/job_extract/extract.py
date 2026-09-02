"""Turn cleaned page text into a validated :class:`JobPosting`.

The flow:

1. build a prompt that includes the JSON schema and the page text
2. ask the LLM
3. parse its answer tolerantly (models love to wrap JSON in prose or ```json)
4. validate against the schema
5. on a parse/validation failure, re-prompt with the exact error, up to
   ``max_retries`` times, then give up with :class:`ExtractionError`

Steps 3 and 4 are pure and unit-tested on their own; step 5 is exercised with a
:class:`~job_extract.llm.StubLLM` that returns junk first and good JSON second.
"""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from .llm import LLM
from .models import JobPosting

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_FIRST_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


class ExtractionError(RuntimeError):
    """The model could not produce a valid JobPosting within the retry budget."""

    def __init__(self, message: str, *, attempts: int, last_raw: str):
        super().__init__(message)
        self.attempts = attempts
        self.last_raw = last_raw


def parse_llm_json(raw: str) -> dict:
    """Best-effort: strip code fences / prose, return the first JSON object."""
    if raw is None:
        raise ValueError("empty response")
    text = _FENCE_RE.sub("", raw.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = _FIRST_OBJ_RE.search(text)
        if not m:
            raise ValueError("no JSON object found in response")
        obj = json.loads(m.group(0))  # may still raise -> caller handles
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    return obj


def build_prompt(page_text: str, *, error_feedback: str | None = None) -> str:
    schema = json.dumps(JobPosting.model_json_schema(), indent=2)
    parts = [
        "Extract the job posting below into a single JSON object that validates "
        "against this JSON Schema. Use null / defaults when a field is not "
        "stated. Do not invent values. Reply with ONLY the JSON object.",
        "",
        "JSON Schema:",
        schema,
        "",
        "Job posting:",
        '"""',
        page_text.strip()[:12_000],
        '"""',
    ]
    if error_feedback:
        parts += [
            "",
            "Your previous answer was rejected with this error - fix it:",
            error_feedback,
        ]
    return "\n".join(parts)


def extract(page_text: str, llm: LLM, *, max_retries: int = 2) -> JobPosting:
    """Cleaned page text -> validated JobPosting, with a re-prompt loop."""
    if not page_text or not page_text.strip():
        raise ExtractionError("page text is empty", attempts=0, last_raw="")

    feedback: str | None = None
    last_raw = ""
    for attempt in range(1, max_retries + 2):  # first try + max_retries
        prompt = build_prompt(page_text, error_feedback=feedback)
        last_raw = llm.complete(prompt)
        try:
            data = parse_llm_json(last_raw)
            return JobPosting.model_validate(data)
        except (ValueError, ValidationError) as err:
            feedback = _short_error(err)

    raise ExtractionError(
        f"no valid JobPosting after {max_retries + 1} attempts: {feedback}",
        attempts=max_retries + 1,
        last_raw=last_raw,
    )


def _short_error(err: Exception) -> str:
    if isinstance(err, ValidationError):
        bits = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in err.errors()[:6]
        ]
        return "; ".join(bits)
    return str(err)
