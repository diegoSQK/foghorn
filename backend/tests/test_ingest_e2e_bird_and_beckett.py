"""End-to-end: the Bird & Beckett fixture run through the ingest pipeline.

Confirms the scraper output lands as the expected DB rows — counts, the
tz->UTC computation for a UTC-origin event, accented display-name
preservation, recurring-series expansion, and idempotent re-ingest.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import bird_and_beckett

FIXTURE = Path(__file__).parent / "fixtures" / "bird_and_beckett_sample.ics"
TODAY = dt.date(2026, 6, 1)


@pytest.fixture
def bb_venue(conn: sqlite3.Connection) -> Venue:
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert venue is not None
    return venue


def _scraped() -> list[ScrapedShow]:
    return bird_and_beckett.parse_ics(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_ingest_creates_expected_rows(
    conn: sqlite3.Connection, bb_venue: Venue
) -> None:
    result = ingest_scraped_shows(conn, bb_venue, _scraped())
    assert result.created == 7
    assert result.updated == 0
    assert result.errors == []

    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["bird_and_beckett"]))
    assert len(stored) == 7


def test_utc_origin_event_stored_as_utc(
    conn: sqlite3.Connection, bb_venue: Venue
) -> None:
    ingest_scraped_shows(conn, bb_venue, _scraped())
    klaxon = next(
        s
        for s in shows_repo.list(conn, ShowFilters())
        if s.headliner_canonical == "klaxon mutant all stars"
    )
    assert klaxon.start_local_date == "2026-06-06"
    assert klaxon.start_local_time == "20:00"
    # Round-trips back to the feed's original 03:00Z.
    assert klaxon.start_utc == "2026-06-07T03:00:00+00:00"


def test_accented_display_preserved(
    conn: sqlite3.Connection, bb_venue: Venue
) -> None:
    ingest_scraped_shows(conn, bb_venue, _scraped())
    cafe = next(
        s
        for s in shows_repo.list(conn, ShowFilters())
        if s.headliner_canonical == "cafe tacvba"
    )
    headliner = next(p for p in cafe.performers if p.role == "headliner")
    assert headliner.display_name == "Café Tacvba"


def test_reingest_is_idempotent(conn: sqlite3.Connection, bb_venue: Venue) -> None:
    ingest_scraped_shows(conn, bb_venue, _scraped())
    second = ingest_scraped_shows(conn, bb_venue, _scraped())
    assert second.created == 0
    assert second.updated == 7
    assert len(shows_repo.list(conn, ShowFilters())) == 7
