# python-samples

Small, production-shaped Python projects, built as work samples.

| Project | What it shows | Tests |
|---|---|---|
| [`hn-scraper-api`](hn-scraper-api) | A web scraper structured as a **pure parser** (unit-tested offline against a saved page) + a thin I/O layer + typed pydantic models + a cached FastAPI wrapper. | 8, `pytest -q` |
| [`sales-cleanup`](sales-cleanup) | Cleans a deliberately messy sales export — four date formats, `$19.90` / `R$ 45,00` / `1.299,00`, blanks, duplicates — into one tidy table plus by-month / by-product / top-customer summaries, and the script to re-run it. Dropped-row reasons are reported, not silent. | 20, `pytest -q` |
| [`github-sync`](github-sync) | A GitHub REST client with the plumbing a real API job needs: token auth, `Link`-header pagination, `403` rate-limit → wait-for-reset, `5xx` → capped backoff, `ETag` / `304` conditional requests, add/remove/update diff between runs. Driven end to end by `httpx.MockTransport`. | 27, `pytest -q` |

Each folder has its own `README.md` and `requirements.txt`.

```bash
cd hn-scraper-api        # or sales-cleanup, github-sync
python -m venv .venv && . .venv/Scripts/activate   # .venv/bin/activate on mac/linux
pip install -r requirements.txt
pytest -q
```
