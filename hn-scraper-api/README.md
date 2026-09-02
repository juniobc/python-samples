# hn-scraper-api

A small, production-shaped Python scraper + API. Built as a work sample: it shows
how I structure a scraping job — a **pure parser** that's unit-tested offline, a
thin I/O layer, typed models, and a cached FastAPI wrapper.

## What it does

Scrapes the [Hacker News](https://news.ycombinator.com/) front page into typed
records and serves them over a tiny JSON API.

```json
{
  "rank": 2,
  "id": 41234567,
  "title": "Gemini 3.8 Flash",
  "url": "https://blog.google/...",
  "site": "blog.google",
  "points": 728,
  "author": "someuser",
  "comments": 424,
  "age_text": "5 hours ago"
}
```

## Run it

```bash
python -m venv .venv && . .venv/Scripts/activate      # (.venv/bin/activate on mac/linux)
pip install -r requirements.txt

python -c "from hn_scraper import fetch_front_page; [print(s.rank, s.points, s.title) for s in fetch_front_page()]"

uvicorn hn_scraper.api:app --reload
#  GET http://127.0.0.1:8000/stories?min_points=100&limit=10
#  GET http://127.0.0.1:8000/stories?has_url=false      (Ask HN / text posts)
#  GET http://127.0.0.1:8000/stories/41234567
#  http://127.0.0.1:8000/docs   (interactive)
```

## Tests

```bash
pytest -q          # 8 tests, run offline against tests/fixture_front_page.html
```

## Design notes

- **`parse_front_page(html) -> list[Story]`** is pure. HTML in, data out, no
  network — so the tests are fast and don't depend on HN being up or unchanged.
- **`fetch_front_page()`** is the only thing that touches the network; it accepts
  an injected `httpx.Client` for testing/retries.
- Parsing with **selectolax** (fast C parser). The metadata (points/author/
  comments) lives in the `<tr>` *after* each `tr.athing`, handled by `_subline`.
- The API **caches for 60s** so hammering the endpoint doesn't hammer HN.
- Models are **pydantic v2** — validation + JSON (de)serialization for free.

## What a real client job looks like

Same shape, different target: a product catalog, a directory, a marketplace, a
government dataset. Deliverables: the scraper, tests against saved fixtures, an
output format you pick (CSV / JSON / Postgres / Google Sheet), and a short doc so
your team can re-run and extend it.
