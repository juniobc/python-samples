"""Scrape the Hacker News front page into structured `Story` objects.

`parse_front_page(html)` is pure (HTML in, data out) so it can be unit-tested
against a saved fixture with no network. `fetch_front_page()` does the I/O.
"""
from __future__ import annotations

import re

import httpx
from selectolax.parser import HTMLParser, Node

from .models import Story

FRONT_PAGE = "https://news.ycombinator.com/"
USER_AGENT = "Mozilla/5.0 (compatible; hn-scraper-sample/1.0)"

_INT = re.compile(r"\d+")


def _first_int(text: str | None, default: int = 0) -> int:
    if not text:
        return default
    m = _INT.search(text)
    return int(m.group()) if m else default


def _subline(athing: Node) -> Node | None:
    """The metadata sits in the <tr> right after tr.athing."""
    sib = athing.next
    while sib is not None and sib.tag != "tr":
        sib = sib.next
    if sib is None:
        return None
    return sib.css_first("span.subline") or sib.css_first("td.subtext")


def parse_front_page(html: str) -> list[Story]:
    """Turn HN front-page HTML into a list of Story. No network."""
    tree = HTMLParser(html)
    stories: list[Story] = []

    for row in tree.css("tr.athing"):
        story_id = int(row.attributes.get("id") or 0)

        rank_node = row.css_first("span.rank")
        rank = _first_int(rank_node.text() if rank_node else None)

        title_link = row.css_first("span.titleline > a") or row.css_first("td.title > a")
        if title_link is None:
            continue
        title = title_link.text(strip=True)
        href = title_link.attributes.get("href") or ""
        url = href if href.startswith("http") else None  # None = internal (Ask HN etc.)

        site_node = row.css_first("span.sitestr")
        site = site_node.text(strip=True) if site_node else None

        points = comments = 0
        author: str | None = None
        age_text = ""
        sub = _subline(row)
        if sub is not None:
            score_node = sub.css_first("span.score")
            points = _first_int(score_node.text() if score_node else None)
            author_node = sub.css_first("a.hnuser")
            author = author_node.text(strip=True) if author_node else None
            age_node = sub.css_first("span.age")
            age_text = age_node.text(strip=True) if age_node else ""
            links = sub.css("a")
            if links:
                comments = _first_int(links[-1].text(strip=True))  # "N comments" / "discuss"

        stories.append(
            Story(
                rank=rank,
                id=story_id,
                title=title,
                url=url,
                site=site,
                points=points,
                author=author,
                comments=comments,
                age_text=age_text,
            )
        )

    return stories


def fetch_front_page(*, timeout: float = 15.0, client: httpx.Client | None = None) -> list[Story]:
    """Fetch and parse the live HN front page."""
    owns_client = client is None
    client = client or httpx.Client(headers={"user-agent": USER_AGENT}, timeout=timeout)
    try:
        resp = client.get(FRONT_PAGE)
        resp.raise_for_status()
        return parse_front_page(resp.text)
    finally:
        if owns_client:
            client.close()
