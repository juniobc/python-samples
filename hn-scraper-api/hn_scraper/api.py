"""Tiny FastAPI wrapper over the scraper.

    uvicorn hn_scraper.api:app --reload

Endpoints
    GET /stories?min_points=100&limit=10   -> filtered list of stories
    GET /stories/{story_id}                -> one story, or 404
    GET /healthz
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Query

from .models import Story
from .scraper import fetch_front_page

app = FastAPI(title="HN front-page scraper", version="1.0.0")

_CACHE: dict[str, object] = {"at": 0.0, "stories": []}
_TTL = 60.0  # seconds — be polite to news.ycombinator.com


def _stories() -> list[Story]:
    now = time.time()
    if now - float(_CACHE["at"]) > _TTL:
        _CACHE["stories"] = fetch_front_page()
        _CACHE["at"] = now
    return list(_CACHE["stories"])  # type: ignore[arg-type]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stories", response_model=list[Story])
def list_stories(
    min_points: int = Query(0, ge=0, description="only stories with at least this many points"),
    has_url: bool | None = Query(None, description="true = external link only, false = text posts only"),
    limit: int = Query(30, ge=1, le=30),
) -> list[Story]:
    out = [s for s in _stories() if s.points >= min_points]
    if has_url is not None:
        out = [s for s in out if (s.url is not None) == has_url]
    return out[:limit]


@app.get("/stories/{story_id}", response_model=Story)
def get_story(story_id: int) -> Story:
    for s in _stories():
        if s.id == story_id:
            return s
    raise HTTPException(status_code=404, detail="story not on the current front page")
