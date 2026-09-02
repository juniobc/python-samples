"""End-to-end over httpx.MockTransport — no network, no sleeping."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from github_sync.client import (
    GitHubClient,
    GitHubError,
    RateLimited,
    backoff_delays,
    is_rate_limited,
    is_retryable,
    parse_link_header,
    retry_after_seconds,
)
from github_sync.models import parse_repos
from github_sync.sync import merge_snapshots, run

FIX = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_parse_link_header_next_and_last():
    header = (
        '<https://api.github.com/user/1/repos?page=2>; rel="next", '
        '<https://api.github.com/user/1/repos?page=5>; rel="last"'
    )
    links = parse_link_header(header)
    assert links["next"].endswith("page=2")
    assert links["last"].endswith("page=5")


def test_parse_link_header_empty():
    assert parse_link_header(None) == {}
    assert parse_link_header("") == {}


@pytest.mark.parametrize("code,expected", [(429, True), (500, True), (503, True), (404, False), (200, False), (403, False)])
def test_is_retryable(code, expected):
    assert is_retryable(code) is expected


def test_retry_after_prefers_retry_after_header():
    h = httpx.Headers({"retry-after": "12", "x-ratelimit-reset": "9999999999"})
    assert retry_after_seconds(h, now=0.0) == 12.0


def test_retry_after_falls_back_to_ratelimit_reset():
    h = httpx.Headers({"x-ratelimit-reset": "100"})
    assert retry_after_seconds(h, now=40.0) == 60.0


def test_retry_after_never_negative():
    h = httpx.Headers({"x-ratelimit-reset": "10"})
    assert retry_after_seconds(h, now=999.0) == 0.0


def test_retry_after_default_floor():
    assert retry_after_seconds(httpx.Headers({}), now=0.0) == 1.0


def test_backoff_delays_shape():
    delays = backoff_delays(4, base=0.5, cap=30.0, jitter=0.0)
    assert delays == [0.5, 1.0, 2.0, 4.0]
    capped = backoff_delays(8, base=1.0, cap=10.0, jitter=0.0)
    assert max(capped) == 10.0


def test_is_rate_limited_403_with_zero_remaining():
    resp = httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, text="{}")
    assert is_rate_limited(resp) is True


def test_is_rate_limited_403_permissions_is_not():
    resp = httpx.Response(403, headers={"x-ratelimit-remaining": "57"}, text='{"message":"Forbidden"}')
    assert is_rate_limited(resp) is False


# --------------------------------------------------------------------------- #
# fixtures / helpers for the transport-driven tests
# --------------------------------------------------------------------------- #
def _client(handler, **kw):
    calls: list[float] = []
    return (
        GitHubClient(
            token="t",
            transport=httpx.MockTransport(handler),
            sleep=calls.append,
            now=lambda: 1000.0,
            **kw,
        ),
        calls,
    )


def _page(items, *, next_url=None, etag=None):
    headers = {}
    if next_url:
        headers["link"] = f'<{next_url}>; rel="next"'
    if etag:
        headers["etag"] = etag
    return httpx.Response(200, json=items, headers=headers)


# --------------------------------------------------------------------------- #
# pagination
# --------------------------------------------------------------------------- #
def test_paginate_follows_link_to_last_page():
    p1 = json.loads((FIX / "repos_page1.json").read_text())
    p2 = json.loads((FIX / "repos_page2.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return _page(p2)
        return _page(p1, next_url="https://api.github.com/users/octo/repos?page=2")

    gh, slept = _client(handler)
    with gh:
        repos = gh.list_user_repos("octo")

    assert [r.name for r in repos] == ["alpha", "beta", "gamma"]
    assert repos[0].stars == 12 and repos[2].language == "Python"
    assert slept == []  # nothing to wait for


# --------------------------------------------------------------------------- #
# rate limiting
# --------------------------------------------------------------------------- #
def test_rate_limited_then_succeeds():
    state = {"hits": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["hits"] += 1
        if state["hits"] == 1:
            return httpx.Response(
                403,
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"},
                text='{"message":"API rate limit exceeded"}',
            )
        return _page([], )

    gh, slept = _client(handler)
    with gh:
        repos = gh.list_user_repos("octo")

    assert repos == []
    assert slept == [30.0]  # reset(1030) - now(1000)


def test_rate_limited_beyond_budget_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "5000"},
            text="rate limit",
        )

    gh, _ = _client(handler, max_rate_limit_wait=100.0)
    with gh, pytest.raises(RateLimited):
        gh.list_user_repos("octo")


# --------------------------------------------------------------------------- #
# retry on 5xx
# --------------------------------------------------------------------------- #
def test_transient_5xx_is_retried():
    state = {"hits": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["hits"] += 1
        if state["hits"] <= 2:
            return httpx.Response(502, text="bad gateway")
        return _page([{"id": 1, "name": "x", "full_name": "o/x", "private": False,
                       "html_url": "http://h"}])

    gh, slept = _client(handler)
    with gh:
        repos = gh.list_user_repos("octo")

    assert len(repos) == 1 and repos[0].name == "x"
    assert len(slept) == 2  # two backoff sleeps


def test_5xx_past_max_retries_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    gh, _ = _client(handler, max_retries=2)
    with gh, pytest.raises(GitHubError):
        gh.list_user_repos("octo")


def test_404_is_not_retried():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='{"message":"Not Found"}')

    gh, slept = _client(handler)
    with gh, pytest.raises(GitHubError):
        gh.list_user_repos("ghost")
    assert slept == []


# --------------------------------------------------------------------------- #
# conditional requests / ETag
# --------------------------------------------------------------------------- #
def test_etag_is_stored_and_replayed_as_304():
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("if-none-match"))
        if request.headers.get("if-none-match") == '"abc"':
            return httpx.Response(304, headers={"etag": '"abc"'})
        return _page([{"id": 1, "name": "x", "full_name": "o/x", "private": False,
                       "html_url": "http://h"}], etag='"abc"')

    gh, _ = _client(handler)
    with gh:
        first = gh.list_user_repos("octo")
        second = gh.list_user_repos("octo")

    assert len(first) == 1
    assert second == []  # 304 -> no page yielded, caller keeps its cache
    assert seen_headers == [None, '"abc"']


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def test_token_is_sent_as_bearer():
    captured: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization"))
        return _page([])

    gh, _ = _client(handler)
    with gh:
        gh.list_user_repos("octo")
    assert captured == ["Bearer t"]


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #
def test_parse_repos_aliases_and_ignores_extra():
    raw = [{
        "id": 9, "name": "r", "full_name": "o/r", "private": False,
        "html_url": "http://h", "stargazers_count": 4, "forks_count": 1,
        "open_issues_count": 2, "some_field_we_dont_care_about": 123,
    }]
    (repo,) = parse_repos(raw)
    assert repo.stars == 4 and repo.forks == 1 and repo.open_issues == 2


# --------------------------------------------------------------------------- #
# merge / diff
# --------------------------------------------------------------------------- #
def _repo(**kw):
    base = {"id": 1, "name": "a", "full_name": "o/a", "private": False, "html_url": "http://h"}
    base.update(kw)
    return parse_repos([base])[0]


def test_merge_snapshots_detects_add_remove_update():
    old = [_repo(id=1, pushed_at="2024-01-01T00:00:00Z"),
           _repo(id=2, full_name="o/b", pushed_at="2024-01-01T00:00:00Z")]
    new = [_repo(id=1, pushed_at="2024-02-01T00:00:00Z"),   # updated
           _repo(id=3, full_name="o/c", pushed_at="2024-03-01T00:00:00Z")]  # added
    merged, diff = merge_snapshots(old, new)

    assert diff.added == ["o/c"]
    assert diff.removed == ["o/b"]
    assert diff.updated == ["o/a"]
    assert diff.changed is True
    assert [r.id for r in merged] == [3, 1]  # newest pushed_at first


def test_merge_snapshots_no_change():
    old = [_repo(id=1, pushed_at="2024-01-01T00:00:00Z")]
    new = [_repo(id=1, pushed_at="2024-01-01T00:00:00Z")]
    _, diff = merge_snapshots(old, new)
    assert diff.changed is False


# --------------------------------------------------------------------------- #
# run() writes the file  (monkeypatched client, still no network)
# --------------------------------------------------------------------------- #
def test_run_writes_json_and_returns_diff(tmp_path, monkeypatch):
    from github_sync import sync as sync_mod

    p1 = json.loads((FIX / "repos_page1.json").read_text())

    class _FakeGH:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def list_user_repos(self, username): return parse_repos(p1)

    monkeypatch.setattr(sync_mod, "GitHubClient", _FakeGH)
    out = tmp_path / "repos.json"

    diff = run("octo", out)
    assert out.exists()
    assert set(diff.added) == {"octo/alpha", "octo/beta"}

    diff2 = run("octo", out)  # second run: nothing new
    assert diff2.changed is False
