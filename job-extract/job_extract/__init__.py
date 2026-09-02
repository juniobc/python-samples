"""LLM-assisted scraping: messy job-posting HTML -> a validated typed record.

The scraping half is ordinary (fetch + strip to text). The interesting half is
making an LLM produce data you can *trust*: a strict schema, tolerant JSON
parsing, and a re-prompt loop that feeds the validation error back to the model
until it complies or a retry budget runs out.
"""
from .models import JobPosting
from .llm import LLM, StubLLM
from .extract import extract, ExtractionError

__all__ = ["JobPosting", "LLM", "StubLLM", "extract", "ExtractionError"]
