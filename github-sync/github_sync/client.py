"""A small, well-behaved GitHub REST client.

What this sample is really about — the stuff that separates a script that works
on your machine from one you can hand to a client:

* token auth via the ``Authorization`` header
* ``Link`` header pagination (RFC 5988), followed to the last page
* ``403`` + ``X-RateLimit-Remaining: 0`` -> sleep until the reset, then retry
* ``5xx`` and ``429`` -> capped exponential backoff with jitter
* conditional requests: keep the ``ETag`` per URL, send ``If-None-Match``,
  treat ``304`` as "reuse what I had"

The pure helpers (``parse_link_header``, ``retry_after_seconds``,
``backoff_delays``, ``is_retryable``) carry the tricky logic and are unit-tested
with no network. :class:`GitHubClient` takes an injectable ``transport`` and
``sleep`` so the retry/pagination loop is tested end to end against
``httpx.MockTransport``.
"""
from __future__ import annotations

import random
import re
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from .models import Repo, parse_repos

API_ROOT = "https://api.github.com"
_UA = "github-sync-sample/1.0"

_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="([^"]+)"')


class GitHubError(RuntimeError):
    """Non-retryable API failure (4xx that isn't rate limiting)."""


class RateLimited(GitHubError):
    """Rate limit hit and not clearing within the allowed wait budget."""


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def parse_link_header(value: str | None) -> dict[str, str]:
    """``<url>; rel="next", <url>; rel="last"`` -> ``{"next": url, "last": url}``."""
    if not value:
        return {}
    return {rel: url for url, rel in _LINK_RE.findall(value)}


def is_retryable(status_code: int) -> bool:
    """Transient server-side / throttling statuses worth another attempt."""
    return status_code in (429, 500, 502, 503, 504)


def retry_after_seconds(headers: httpx.Headers | dict, *, now: float) -> float:
    """How long to wait before retrying a throttled response.

    Honours ``Retry-After`` (seconds) if present, else ``X-RateLimit-Reset``
    (an epoch second), else a 1s floor. Never negative.
    """
    ra = headers.get("retry-after")
    if ra is not None:
        try:
            return max(0.0, float(ra))
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            return max(0.0, float(reset) - now)
        except ValueError:
            pass
    return 1.0


def backoff_delays(
    attempts: int, *, base: float = 0.5, cap: float = 30.0, jitter: float = 0.2
) -> list[float]:
    """Capped exponential backoff, e.g. 0.5, 1, 2, 4, ... with +/- jitter."""
    out: list[float] = []
    for i in range(attempts):
        raw = min(cap, base * (2 ** i))
        spread = raw * jitter
        out.append(max(0.0, raw + random.uniform(-spread, spread)))
    return out


def is_rate_limited(response: httpx.Response) -> bool:
    """A 403 that is actually the hourly quota, not a permissions error."""
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    remaining = response.headers.get("x-ratelimit-remaining")
    return remaining == "0" or "rate limit" in response.text.lower()


# --------------------------------------------------------------------------- #
# client
# --------------------------------------------------------------------------- #
class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        max_retries: int = 4,
        max_rate_limit_wait: float = 900.0,
        timeout: float = 20.0,
    ) -> None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": _UA}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=API_ROOT, headers=headers, transport=transport, timeout=timeout
        )
        self._sleep = sleep
        self._now = now
        self._max_retries = max_retries
        self._max_rate_limit_wait = max_rate_limit_wait
        self._etags: dict[str, str] = {}

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- one request, with the retry / rate-limit policy applied -----------
    def _request(self, method: str, url: str) -> httpx.Response:
        backoff = backoff_delays(self._max_retries)
        rate_waited = 0.0
        attempt = 0

        while True:
            req_headers: dict[str, str] = {}
            etag = self._etags.get(url)
            if etag:
                req_headers["If-None-Match"] = etag

            response = self._client.request(method, url, headers=req_headers)

            if is_rate_limited(response):
                wait = retry_after_seconds(response.headers, now=self._now())
                rate_waited += wait
                if rate_waited > self._max_rate_limit_wait:
                    raise RateLimited(
                        f"rate limited on {url}; would need to wait "
                        f"{rate_waited:.0f}s (budget {self._max_rate_limit_wait:.0f}s)"
                    )
                self._sleep(wait)
                continue

            if is_retryable(response.status_code):
                if attempt >= self._max_retries:
                    raise GitHubError(
                        f"{response.status_code} on {url} after {attempt} retries"
                    )
                self._sleep(backoff[attempt])
                attempt += 1
                continue

            if response.status_code == 304:
                return response

            if response.status_code >= 400:
                raise GitHubError(f"{response.status_code} on {url}: {response.text[:200]}")

            new_etag = response.headers.get("etag")
            if new_etag:
                self._etags[url] = new_etag
            return response

    # -- follow Link: rel="next" to the end ------------------------------
    def paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[list]:
        """Yield each page's JSON body (a list) until there is no ``next`` link.

        A ``304`` yields nothing for that URL — the caller keeps its cached copy.
        """
        url = str(httpx.URL(path, params=params or {}))
        while url:
            response = self._request("GET", url)
            if response.status_code != 304:
                yield response.json()
            links = parse_link_header(response.headers.get("link"))
            url = links.get("next", "")

    # -- the thing a caller actually wants -----------------------------
    def list_user_repos(
        self, username: str, *, per_page: int = 100, kind: str = "owner"
    ) -> list[Repo]:
        repos: list[Repo] = []
        for page in self.paginate(
            f"/users/{username}/repos",
            {"per_page": per_page, "type": kind, "sort": "pushed"},
        ):
            repos.extend(parse_repos(page))
        return repos
