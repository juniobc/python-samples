"""Data model for a scraped Hacker News story."""
from __future__ import annotations

from pydantic import BaseModel, HttpUrl, field_validator


class Story(BaseModel):
    rank: int
    id: int
    title: str
    url: str | None  # None for "Ask HN" / text posts with no external link
    site: str | None
    points: int
    author: str | None
    comments: int
    age_text: str

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title is blank")
        return v
