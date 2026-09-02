"""No network, no real LLM. Fixtures + StubLLM drive everything."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_extract.extract import ExtractionError, build_prompt, extract, parse_llm_json
from job_extract.llm import StubLLM
from job_extract.models import EmploymentType, JobPosting, Seniority
from job_extract.pipeline import clean_text, from_html

FIX = Path(__file__).parent / "fixtures"

GOOD_A = {
    "title": "Senior Backend Engineer (Python)",
    "company": "Nimbus Data",
    "location": "Remote (US time zones)",
    "remote": True,
    "employment_type": "full_time",
    "seniority": "senior",
    "salary": {"min": 150000, "max": 185000, "currency": "usd", "period": "year"},
    "skills": ["Python", "FastAPI", "Postgres", "SQL", "Kafka", "AWS", "python"],
    "posted_date": "2026-08-18",
    "apply_url": "https://jobs.nimbusdata.example/apply/be-eng",
    "summary": "Own a high-throughput ingestion pipeline in Python, Postgres and Kafka on AWS. Senior role, fully remote for US time zones.",
}


# --------------------------------------------------------------------------- #
# parse_llm_json
# --------------------------------------------------------------------------- #
def test_parse_plain_json():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_parse_strips_code_fence():
    assert parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_extracts_from_prose():
    raw = 'Sure! Here is the data:\n{"a": 1, "b": [2,3]}\nHope that helps.'
    assert parse_llm_json(raw) == {"a": 1, "b": [2, 3]}


def test_parse_rejects_non_object():
    with pytest.raises(ValueError):
        parse_llm_json("[1, 2, 3]")


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_llm_json("no json here at all")


# --------------------------------------------------------------------------- #
# clean_text
# --------------------------------------------------------------------------- #
def test_clean_text_drops_boilerplate_and_keeps_content():
    text = clean_text((FIX / "posting_a.html").read_text(encoding="utf-8"))
    assert "Senior Backend Engineer" in text
    assert "Kafka" in text
    assert "All rights reserved" not in text  # footer dropped
    assert "window.dataLayer" not in text  # script dropped
    assert "Home" not in text.split("\n")[0]  # nav dropped


# --------------------------------------------------------------------------- #
# extract: happy path
# --------------------------------------------------------------------------- #
def test_extract_happy_path():
    llm = StubLLM(json.dumps(GOOD_A))
    job = extract("some page text", llm)
    assert isinstance(job, JobPosting)
    assert job.title == "Senior Backend Engineer (Python)"
    assert job.remote is True
    assert job.employment_type is EmploymentType.full_time
    assert job.seniority is Seniority.senior
    assert job.salary and job.salary.currency == "USD"  # normalised
    assert job.skills.count("Python") == 1  # deduped (had "Python" and "python")
    assert len(llm.calls) == 1


def test_extract_retries_then_succeeds():
    llm = StubLLM(["not json at all", "```json\n" + json.dumps(GOOD_A) + "\n```"])
    job = extract("text", llm, max_retries=2)
    assert job.company == "Nimbus Data"
    assert len(llm.calls) == 2
    # the 2nd prompt must carry the parse error as feedback
    assert "rejected with this error" in llm.calls[1]


def test_extract_feeds_validation_error_back():
    bad = dict(GOOD_A, salary={"min": -5, "currency": "USD", "period": "year"})
    llm = StubLLM([json.dumps(bad), json.dumps(GOOD_A)])
    job = extract("text", llm, max_retries=2)
    assert job.salary.min == 150000
    assert "salary" in llm.calls[1].lower()


def test_extract_gives_up_after_budget():
    llm = StubLLM(["garbage", "still garbage", "garbage again"])
    with pytest.raises(ExtractionError) as ei:
        extract("text", llm, max_retries=2)
    assert ei.value.attempts == 3
    assert len(llm.calls) == 3


def test_extract_empty_text_raises_without_calling_llm():
    llm = StubLLM("{}")
    with pytest.raises(ExtractionError):
        extract("   ", llm)
    assert llm.calls == []


def test_extract_rejects_unknown_fields():
    payload = dict(GOOD_A, made_up_field="oops")
    llm = StubLLM([json.dumps(payload), json.dumps(GOOD_A)])
    job = extract("text", llm, max_retries=2)
    assert job.title == GOOD_A["title"]
    assert "made_up_field" in llm.calls[1]


# --------------------------------------------------------------------------- #
# build_prompt
# --------------------------------------------------------------------------- #
def test_build_prompt_includes_schema_and_text():
    p = build_prompt("HELLO POSTING")
    assert "JSON Schema" in p and "HELLO POSTING" in p
    assert "properties" in p  # the schema itself


def test_build_prompt_truncates_huge_text():
    # 'Q' does not appear in the JSON schema, so its count is the text length
    p = build_prompt("Q" * 50_000)
    assert p.count("Q") == 12_000


# --------------------------------------------------------------------------- #
# pipeline.from_html
# --------------------------------------------------------------------------- #
def test_from_html_end_to_end_with_stub():
    html = (FIX / "posting_b.html").read_text(encoding="utf-8")
    good_b = {
        "title": "Automation Engineer (n8n / Python)",
        "company": "Peppercorn Studio",
        "location": "London, UK",
        "remote": False,
        "employment_type": "contract",
        "seniority": "mid",
        "salary": {"min": 450, "max": None, "currency": "GBP", "period": "day"},
        "skills": ["n8n", "Python", "HubSpot", "Stripe", "Google Workspace"],
        "posted_date": None,
        "apply_url": None,
        "summary": "Build and maintain n8n workflows plus Python glue for a small agency automating client back-offices. Six-month hybrid contract in London.",
    }

    def fake_llm(prompt: str) -> str:
        assert "Automation Engineer" in prompt  # cleaned text reached the model
        return json.dumps(good_b)

    job = from_html(html, StubLLM(fake_llm))
    assert job.employment_type is EmploymentType.contract
    assert job.salary.currency == "GBP" and job.salary.period == "day"
    assert "n8n" in job.skills
