"""The schema the LLM must fill. Strict on purpose."""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"
    temporary = "temporary"
    unknown = "unknown"


class Seniority(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    staff = "staff"
    unknown = "unknown"


class Salary(BaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = Field(None, description="ISO 4217, e.g. USD, EUR, BRL")
    period: str | None = Field(None, description="year | month | day | hour")

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("min", "max")
    @classmethod
    def _non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("salary cannot be negative")
        return v


class JobPosting(BaseModel):
    title: str
    company: str
    location: str | None = None
    remote: bool = False
    employment_type: EmploymentType = EmploymentType.unknown
    seniority: Seniority = Seniority.unknown
    salary: Salary | None = None
    skills: list[str] = Field(default_factory=list)
    posted_date: date | None = None
    apply_url: str | None = None
    summary: str = Field(..., description="2-3 sentence plain summary of the role")

    model_config = {"extra": "forbid"}

    @field_validator("skills")
    @classmethod
    def _dedupe_skills(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for s in v:
            key = s.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(s.strip())
        return out

    @field_validator("title", "company", "summary")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()
