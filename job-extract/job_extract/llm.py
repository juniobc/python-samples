"""The LLM is an injected dependency, so the pipeline is testable offline.

`LLM` is a one-method protocol. `StubLLM` is what the tests use. `GeminiLLM` is
the real one (lazy import so the package installs and imports without an API key
or the google packages present).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    def complete(self, prompt: str) -> str:
        """Return the model's raw text response to a single prompt."""
        ...


class StubLLM:
    """Deterministic stand-in.

    Pass a single string, a list of strings (one per successive call), or a
    callable ``prompt -> str``.
    """

    def __init__(self, responses: str | Iterable[str] | Callable[[str], str]):
        self.calls: list[str] = []
        if callable(responses):
            self._fn: Callable[[str], str] = responses
        elif isinstance(responses, str):
            self._fn = lambda _p, _r=responses: _r
        else:
            self._queue = list(responses)
            self._fn = self._pop

    def _pop(self, _prompt: str) -> str:
        if not self._queue:
            raise AssertionError("StubLLM ran out of queued responses")
        return self._queue.pop(0)

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._fn(prompt)


class GeminiLLM:
    """Real backend via langchain-google-genai. Needs GOOGLE_API_KEY."""

    def __init__(self, model: str = "gemini-1.5-flash", *, temperature: float = 0.0):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "pip install langchain-google-genai to use GeminiLLM"
            ) from exc
        self._chat = ChatGoogleGenerativeAI(model=model, temperature=temperature)

    def complete(self, prompt: str) -> str:  # pragma: no cover - needs network
        return self._chat.invoke(prompt).content
