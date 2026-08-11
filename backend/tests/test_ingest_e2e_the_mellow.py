"""End-to-end: The Mellow's two rooms run through the ingest pipeline.

The interesting property here is the split. One scraper produces shows for two
venues, and the runner ingests each venue's slice against its own seeded row —
so this asserts the rows land under the right venue, that neither room picks up
the other's shows, and that the weekly Lakehouse series survives the natural-key
dedup as one row per date per set.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, Show, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import the_mellow

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 8, 11)


def _headliner(show: Show) -> str:
    """The stored headliner's verbatim display name (never the search form)."""
    return next(p.display_name for p in show.performers if p.role == "headliner")


def _scraped() -> list[ScrapedShow]:
    occurrences: list[dict[str, Any]] = json.loads(
        (FIXTURES / "the_mellow_2026_08_occurrences.json").read_text(encoding="utf-8")
    )
    events: list[dict[str, Any]] = json.loads(
        (FIXTURES / "the_mellow_2026_08_events.json").read_text(encoding="utf-8")
    )
    index = {int(event["id"]): event for event in events}
    return the_mellow.parse_occurrences(occurrences, index, today=TODAY)


@pytest.fixture
def venues(conn: sqlite3.Connection) -> dict[str, Venue]:
    seed(conn)
    resolved: dict[str, Venue] = {}
    for slug in (the_mellow.VENUE_SLUG_HAIGHT, the_mellow.VENUE_SLUG_BOATHOUSE):
        venue = venues_repo.get_by_slug(conn, slug)
        assert venue is not None, f"{slug} is not seeded"
        resolved[slug] = venue
    return resolved


def _ingest_both(conn: sqlite3.Connection, venues: dict[str, Venue]) -> None:
    scraped = _scraped()
    for slug, venue in venues.items():
        slice_ = [show for show in scraped if show.venue_slug == slug]
        result = ingest_scraped_shows(conn, venue, slice_)
        assert result.errors == []


def test_shows_land_on_the_right_venue(
    conn: sqlite3.Connection, venues: dict[str, Venue]
) -> None:
    _ingest_both(conn, venues)

    boathouse = shows_repo.list(conn, ShowFilters(venue_slugs=["blue_heron_boathouse"]))
    haight = shows_repo.list(conn, ShowFilters(venue_slugs=["the_mellow_haight"]))

    assert {_headliner(s) for s in boathouse} == {"Lakehouse Jazz"}
    assert {_headliner(s) for s in haight} == {
        "Mellow Sessions: Rebecca DuMaine Trio",
        "Mellow Sessions: Open Bandstand",
    }
    assert len(boathouse) == 8  # 4 dates x 2 sets
    assert len(haight) == 2


def test_weekly_series_persists_as_one_row_per_date(
    conn: sqlite3.Connection, venues: dict[str, Venue]
) -> None:
    _ingest_both(conn, venues)
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["blue_heron_boathouse"]))
    pairs = sorted((s.start_local_date, s.start_local_time) for s in stored)
    assert pairs == [
        ("2026-08-14", "19:00"),
        ("2026-08-14", "20:30"),
        ("2026-08-15", "19:00"),
        ("2026-08-15", "20:30"),
        ("2026-08-21", "19:00"),
        ("2026-08-21", "20:30"),
        ("2026-08-22", "19:00"),
        ("2026-08-22", "20:30"),
    ]


def test_local_times_convert_to_utc(
    conn: sqlite3.Connection, venues: dict[str, Venue]
) -> None:
    _ingest_both(conn, venues)
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["blue_heron_boathouse"]))
    first = min(stored, key=lambda s: s.start_utc)
    # 2026-08-14 19:00 PDT (UTC-7) == 2026-08-15 02:00 UTC.
    assert first.start_local_date == "2026-08-14"
    assert first.start_local_time == "19:00"
    assert first.start_utc.startswith("2026-08-15T02:00")


def test_reingest_is_idempotent(
    conn: sqlite3.Connection, venues: dict[str, Venue]
) -> None:
    _ingest_both(conn, venues)
    before = len(shows_repo.list(conn, ShowFilters()))
    _ingest_both(conn, venues)
    assert len(shows_repo.list(conn, ShowFilters())) == before


def test_neither_room_is_quarantined_as_an_aggregator_venue(
    conn: sqlite3.Connection, venues: dict[str, Venue]
) -> None:
    # Both rooms are seeded venues, so their shows must be visible without the
    # long-tail toggle that gates aggregator-created venues.
    _ingest_both(conn, venues)
    for venue in venues.values():
        assert venue.source == "seed"
        assert shows_repo.list(conn, ShowFilters(venue_slugs=[venue.slug]))
