"""Tests for the ``?region=`` and ``?neighborhood=`` params on ``GET /api/shows``.

Kept in its own file (not extending ``test_shows_endpoint.py``) so it doesn't
conflict with the sibling Phase 3.3 performer-search ticket. Seeds the real
venues — three of which carry scrapers and distinct SF neighborhoods (Glen Park,
North Beach, Hayes Valley) — ingests one show each, and drives the endpoint with
explicit ``from``/``to`` so assertions don't depend on the wall clock.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


def _show(venue_slug: str, headliner: str, start: dt.datetime) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        start_local=start,
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    # One show per scraper venue, each in a distinct SF neighborhood:
    #   bird_and_beckett → Glen Park, keys_jazz_bistro → North Beach,
    #   mr_tipples → Hayes Valley. (SFJAZZ is also Hayes Valley but has no
    #   scraper and no shows, so it never appears in results.)
    for slug, headliner in (
        ("bird_and_beckett", "Glen Park Trio"),
        ("keys_jazz_bistro", "North Beach Quartet"),
        ("mr_tipples", "Hayes Valley Combo"),
    ):
        venue = venues_repo.get_by_slug(conn, slug)
        assert venue is not None
        ingest_scraped_shows(conn, venue, [_show(slug, headliner, dt.datetime(2026, 6, 6, 20, 0))])
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def _headliners(rows: list[dict]) -> set[str]:
    return {r["headliner"]["display"] for r in rows}


def test_region_sf_returns_all(client: TestClient) -> None:
    assert _headliners(_june(client, region="SF")) == {
        "Glen Park Trio",
        "North Beach Quartet",
        "Hayes Valley Combo",
    }


def test_region_east_bay_is_empty(client: TestClient) -> None:
    # No East Bay venues yet — empties out cleanly rather than erroring.
    assert _june(client, region="East Bay") == []


def test_unknown_region_is_ignored(client: TestClient) -> None:
    # A bogus region doesn't 400 or filter everything out (mirrors time_of_day).
    assert len(_june(client, region="Mars")) == 3


def test_neighborhood_filters_to_one_venue(client: TestClient) -> None:
    assert _headliners(_june(client, neighborhood="North Beach")) == {"North Beach Quartet"}


def test_neighborhood_hayes_valley_excludes_scraperless_sfjazz(client: TestClient) -> None:
    # SFJAZZ is also Hayes Valley but has no shows; only Mr. Tipple's appears.
    assert _headliners(_june(client, neighborhood="Hayes Valley")) == {"Hayes Valley Combo"}


def test_neighborhood_is_case_insensitive(client: TestClient) -> None:
    assert _headliners(_june(client, neighborhood="north beach")) == {"North Beach Quartet"}


def test_region_and_neighborhood_combined(client: TestClient) -> None:
    rows = _june(client, region="SF", neighborhood="North Beach")
    assert _headliners(rows) == {"North Beach Quartet"}


def test_region_stacks_with_other_filters(client: TestClient) -> None:
    # region AND a narrow date window AND venue slug, all combined.
    rows = client.get(
        "/api/shows",
        params={
            "region": "SF",
            "from": "2026-06-06",
            "to": "2026-06-06",
            "venues": "keys_jazz_bistro",
        },
    ).json()
    assert _headliners(rows) == {"North Beach Quartet"}
