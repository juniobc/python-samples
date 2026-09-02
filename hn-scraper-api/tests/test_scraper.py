"""Unit tests for the pure parser — run offline against a saved fixture.

    pytest -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hn_scraper.scraper import parse_front_page

FIXTURE = Path(__file__).parent / "fixture_front_page.html"


@pytest.fixture(scope="module")
def stories():
    return parse_front_page(FIXTURE.read_text(encoding="utf-8"))


def test_parses_a_full_page(stories):
    # HN shows 30 stories per page
    assert len(stories) == 30


def test_ranks_are_1_to_30_in_order(stories):
    assert [s.rank for s in stories] == list(range(1, 31))


def test_every_story_has_id_and_title(stories):
    for s in stories:
        assert s.id > 0
        assert s.title.strip()


def test_points_and_comments_are_non_negative_ints(stories):
    for s in stories:
        assert isinstance(s.points, int) and s.points >= 0
        assert isinstance(s.comments, int) and s.comments >= 0


def test_external_links_are_absolute_or_none(stories):
    for s in stories:
        assert s.url is None or s.url.startswith("http")


def test_at_least_one_story_has_an_external_url(stories):
    assert any(s.url for s in stories)


def test_at_least_one_story_has_points_and_author(stories):
    assert any(s.points > 0 and s.author for s in stories)


def test_json_roundtrip(stories):
    for s in stories[:5]:
        again = type(s).model_validate_json(s.model_dump_json())
        assert again == s
