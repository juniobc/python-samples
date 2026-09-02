# github-sync

A work sample for the most common **API-integration** job: pull data from a
paginated, rate-limited, token-authenticated REST API and land it locally —
without dropping rows to a `500` or a rate-limit window, and without re-downloading
everything every run.

It syncs a GitHub user's public repositories to a JSON file and prints what
changed since last time.

## The parts that matter

| Concern | Where | Tested |
|---|---|---|
| Token auth (`Authorization: Bearer …`) | `client.py` | `test_token_is_sent_as_bearer` |
| `Link` header pagination (RFC 5988), followed to the last page | `parse_link_header`, `GitHubClient.paginate` | `test_paginate_follows_link_to_last_page` |
| `403` + `X-RateLimit-Remaining: 0` → sleep to the reset, then retry | `is_rate_limited`, `retry_after_seconds` | `test_rate_limited_then_succeeds` |
| Give up if the wait blows a budget | `GitHubClient._request` | `test_rate_limited_beyond_budget_raises` |
| `5xx` / `429` → capped exponential backoff with jitter | `backoff_delays`, `is_retryable` | `test_transient_5xx_is_retried` |
| `4xx` that isn't throttling → fail fast, no retries | `GitHubClient._request` | `test_404_is_not_retried` |
| Conditional requests: store the `ETag`, send `If-None-Match`, treat `304` as "reuse cache" | `GitHubClient._request` / `.paginate` | `test_etag_is_stored_and_replayed_as_304` |
| Add / remove / update diff between runs | `sync.merge_snapshots` | `test_merge_snapshots_detects_add_remove_update` |

## Run

```bash
python -m venv .venv && . .venv/Scripts/activate      # Linux/macOS: . .venv/bin/activate
pip install -r requirements.txt

python -m github_sync.sync <github-username> -o repos.json
#   + <user>/new-repo
#   ~ <user>/repo-that-got-a-push
#   repos.json: +1 ~1 -0

export GITHUB_TOKEN=ghp_...      # optional: 60 -> 5000 requests/hour
```

Run it again and it prints `repos.json: up to date` — the second call costs one
conditional request per page and transfers no bodies.

## Tests

```bash
pytest -q          # 27 tests, no network
```

The retry / rate-limit / pagination loop is driven end to end by
`httpx.MockTransport`, and every `sleep` is injected, so the suite runs in well
under a second and never actually waits.

## Design

- **Pure helpers carry the tricky logic.** `parse_link_header`,
  `retry_after_seconds`, `backoff_delays`, `is_rate_limited`, `merge_snapshots` —
  all HTTP-free, all unit-tested in isolation.
- **`GitHubClient` takes `transport`, `sleep` and `now`.** That is the whole
  reason the network behaviour is testable without mocks-of-mocks.
- **The client is generic.** `list_user_repos` is a thin call over `paginate`;
  pointing it at issues, gists or another endpoint is a few lines.

## Real client version

Same core, plus: the specific endpoints you need, output to Postgres / BigQuery /
a warehouse table instead of JSON, a scheduled run, secrets from your vault, and
metrics on request count and rate-limit headroom.
