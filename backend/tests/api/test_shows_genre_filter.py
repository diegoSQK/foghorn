"""Tests for the ``?genre=`` param on ``GET /api/shows`` (Phase 7.1).

Same shape as the region/neighborhood filter tests: seeds the real venues,
ingests one show at a jazz venue, a funk venue, and an eclectic venue, and
drives the endpoint with explicit ``from``/``to`` so assertions don't depend
on the wall clock.
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
from foghorn.repo import performers as performers_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


def _show(venue_slug: str, headliner: str) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        start_local=dt.datetime(2026, 6, 6, 20, 0),
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    # One show per genre: keys_jazz_bistro is seeded "jazz", boom_boom_room
    # "funk", ocean_ale_house "eclectic".
    for slug, headliner in (
        ("keys_jazz_bistro", "Jazz Venue Act"),
        ("boom_boom_room", "Funk Venue Act"),
        ("ocean_ale_house", "Eclectic Venue Act"),
    ):
        venue = venues_repo.get_by_slug(conn, slug)
        assert venue is not None
        ingest_scraped_shows(conn, venue, [_show(slug, headliner)])
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def _headliners(rows: list[dict]) -> set[str]:
    return {r["headliner"]["display"] for r in rows}


def test_genre_filters_to_matching_venues(client: TestClient) -> None:
    assert _headliners(_june(client, genre="funk")) == {"Funk Venue Act"}


def test_genre_is_case_insensitive(client: TestClient) -> None:
    assert _headliners(_june(client, genre="Jazz")) == {"Jazz Venue Act"}


def test_no_genre_returns_everything(client: TestClient) -> None:
    assert len(_june(client)) == 3


def test_unknown_genre_empties_cleanly(client: TestClient) -> None:
    # Unlike region (a closed enum, unknown ignored), genre is open text — an
    # unmatched value returns no rows rather than erroring.
    assert _june(client, genre="polka") == []


def test_genre_stacks_with_region(client: TestClient) -> None:
    assert _headliners(_june(client, genre="eclectic", region="SF")) == {
        "Eclectic Venue Act"
    }
    assert _june(client, genre="eclectic", region="East Bay") == []


def test_show_rows_carry_venue_genre(client: TestClient) -> None:
    row = next(r for r in _june(client) if r["venue"]["slug"] == "boom_boom_room")
    assert row["venue"]["genre"] == "funk"


def test_genre_override_wins_over_venue_default(client: TestClient) -> None:
    # ocean_ale_house is seeded "eclectic"; a show with a per-source genre of
    # "Rock / Indie" must surface under the rock filter, not eclectic.
    conn = db.connect()
    venue = venues_repo.get_by_slug(conn, "ocean_ale_house")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="ocean_ale_house",
                headliner_raw="Overridden Act",
                start_local=dt.datetime(2026, 6, 20, 20, 0),
                source_url="https://example.com/o",
                genre="Rock / Indie",
            )
        ],
    )
    conn.close()
    assert "Overridden Act" in _headliners(_june(client, genre="rock"))
    assert "Overridden Act" not in _headliners(_june(client, genre="eclectic"))


def test_show_rows_carry_resolved_genre(client: TestClient) -> None:
    row = next(r for r in _june(client) if r["venue"]["slug"] == "boom_boom_room")
    assert row["genre"] == "funk"  # no override -> venue default resolves


def test_performer_genre_sits_between_override_and_venue(client: TestClient) -> None:
    # A show at eclectic-default ocean_ale_house with no override: the
    # headliner's performer-level genre resolves (and filters).
    conn = db.connect()
    venue = venues_repo.get_by_slug(conn, "ocean_ale_house")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="ocean_ale_house",
                headliner_raw="Tagged Performer",
                start_local=dt.datetime(2026, 6, 21, 20, 0),
                source_url="https://example.com/tp",
            )
        ],
    )
    performers_repo.set_genre(conn, "tagged performer", "latin", "manual")
    conn.close()
    assert "Tagged Performer" in _headliners(_june(client, genre="latin"))
    row = next(
        r for r in _june(client) if r["headliner"]["display"] == "Tagged Performer"
    )
    assert row["genre"] == "latin"
