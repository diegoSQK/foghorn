"""The per-show ``room`` field: persistence, normalization, and the API view.

Rooms exist because a venue row can cover more than one performance space.
SFJAZZ is the motivating case — Miner Auditorium (a ~700-seat hall) and the Joe
Henderson Lab (a ~100-seat club) share the ``sfjazz`` row, and 38% of its
programmed nights run both, so without a room the venue reads as double-booking
itself.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import db
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo


@pytest.fixture
def venue(conn: sqlite3.Connection) -> Venue:
    return venues_repo.upsert(
        conn,
        Venue(
            slug="two_room_hall",
            name="Two Room Hall",
            neighborhood="Hayes Valley",
            region="SF",
            tz="America/Los_Angeles",
            calendar_url="https://example.test/calendar",
            genre="jazz",
        ),
    )


def _scraped(headliner: str, hour: int, room: str | None) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="two_room_hall",
        headliner_raw=headliner,
        start_local=dt.datetime(2026, 9, 10, hour, 0),
        source_url="https://example.test/e",
        room=room,
    )


def test_room_round_trips(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Big Band", 19, "Main Hall"), _scraped("A Trio", 19, "The Lab")]
    )
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert {s.room for s in stored} == {"Main Hall", "The Lab"}


def test_concurrent_shows_in_different_rooms_coexist(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # The exact case that made the fold untenable: same venue, same minute,
    # two rooms. The natural key separates them on headliner, and the room is
    # what makes the pair legible rather than looking like a data bug.
    result = ingest_scraped_shows(
        conn, venue, [_scraped("Big Band", 19, "Main Hall"), _scraped("A Trio", 19, "The Lab")]
    )
    assert result.created == 2
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert len({s.start_local_time for s in stored}) == 1
    assert len({s.room for s in stored}) == 2


def test_room_is_not_part_of_the_natural_key(conn: sqlite3.Connection, venue: Venue) -> None:
    """A room correction must update the row, not fork it.

    If room joined the natural key, a venue relabelling a room — or a scraper
    learning to read it — would double every affected show instead of
    correcting it.
    """
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, None)])
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, "Main Hall")])
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert len(stored) == 1
    assert stored[0].room == "Main Hall"


def test_room_whitespace_is_normalized(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, "  Main   Hall \n")])
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert stored[0].room == "Main Hall"


def test_blank_room_becomes_none(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, "   ")])
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert stored[0].room is None


def test_room_casing_is_left_to_the_source(conn: sqlite3.Connection, venue: Venue) -> None:
    # Display strings are the source's to choose, as with performer names.
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, "the LAB")])
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert stored[0].room == "the LAB"


def test_single_room_venues_are_unaffected(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, [_scraped("Big Band", 19, None)])
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["two_room_hall"]))
    assert stored[0].room is None


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "room_api.db"))
    conn = db.connect()
    stored = venues_repo.upsert(
        conn,
        Venue(
            slug="two_room_hall",
            name="Two Room Hall",
            neighborhood="Hayes Valley",
            region="SF",
            tz="America/Los_Angeles",
            calendar_url="https://example.test/calendar",
        ),
    )
    ingest_scraped_shows(
        conn, stored, [_scraped("Big Band", 19, "Main Hall"), _scraped("A Trio", 19, None)]
    )
    conn.commit()
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def test_api_exposes_room(api_client: TestClient) -> None:
    payload = api_client.get("/api/shows?from=2026-09-10&to=2026-09-10").json()
    rooms = {s["headliner"]["display"]: s["room"] for s in payload}
    assert rooms == {"Big Band": "Main Hall", "A Trio": None}
