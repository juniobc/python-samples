"""The one shape we keep from GitHub's fat repo payload."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Repo(BaseModel):
    """A trimmed GitHub repository record."""

    id: int
    name: str
    full_name: str
    private: bool
    description: str | None = None
    fork: bool = False
    html_url: str
    language: str | None = None
    stars: int = Field(0, alias="stargazers_count")
    forks: int = Field(0, alias="forks_count")
    open_issues: int = Field(0, alias="open_issues_count")
    archived: bool = False
    pushed_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}


def parse_repos(payload: list[dict]) -> list[Repo]:
    """List[dict] from the API -> List[Repo]. Pure; no network."""
    return [Repo.model_validate(item) for item in payload]
