"""End-to-end: the Freight & Salvage fixture run through the ingest pipeline.

Confirms the scraper's output lands on the seeded row (not a quarantined
aggregator venue), that the tz->UTC computation is right for a venue whose feed
publishes local-with-offset times, and that a multi-night run survives the
natural-key dedup as one row per date.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import freight_and_salvage

FIXTURE = Path(__file__).parent / "fixtures" / "freight_and_salvage_2026_08.json"
TODAY = dt.date(2026, 8, 11)


def _scraped() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    productions: list[dict[str, Any]] = payload["productions"]
    return freight_and_salvage.parse_productions(productions, today=TODAY)


@pytest.fixture
def venue(conn: sqlite3.Connection) -> Venue:
    seed(conn)
    resolved = venues_repo.get_by_slug(conn, "freight_and_salvage")
    assert resolved is not None
    return resolved


def test_ingest_creates_expected_rows(conn: sqlite3.Connection, venue: Venue) -> None:
    result = ingest_scraped_shows(conn, venue, _scraped())
    assert result.errors == []
    assert result.created == 13
    assert result.updated == 0

    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["freight_and_salvage"]))
    assert len(stored) == 13


def test_jam_tagging_survives_ingest(conn: sqlite3.Connection, venue: Venue) -> None:
    # The scraper's explicit event_type must win over the pipeline's narrower
    # title inference, which wouldn't recognise "Country Bluegrass Jam".
    ingest_scraped_shows(conn, venue, _scraped())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["freight_and_salvage"]))
    jams = {
        s.start_local_date for s in stored if s.event_type == "jam"
    }
    assert jams == {"2026-09-14", "2026-09-28"}
    assert all(
        s.event_type == "show"
        for s in stored
        if any(p.display_name == "Jeff Parker ETA IVtet" for p in s.performers)
    )


def test_local_times_convert_to_utc(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _scraped())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["freight_and_salvage"]))
    parker = next(
        s
        for s in stored
        if any(p.display_name == "Jeff Parker ETA IVtet" for p in s.performers)
    )
    # 2026-08-22 20:00 PDT (UTC-7) == 2026-08-23 03:00 UTC.
    assert parker.start_local_date == "2026-08-22"
    assert parker.start_local_time == "20:00"
    assert parker.start_utc.startswith("2026-08-23T03:00")


def test_multi_night_run_persists_per_date(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _scraped())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["freight_and_salvage"]))
    lavette = sorted(
        s.start_local_date
        for s in stored
        if any(p.display_name == "Bettye LaVette" for p in s.performers)
    )
    assert lavette == ["2026-09-04", "2026-09-05"]


def test_reingest_is_idempotent(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _scraped())
    before = len(shows_repo.list(conn, ShowFilters()))
    ingest_scraped_shows(conn, venue, _scraped())
    assert len(shows_repo.list(conn, ShowFilters())) == before


def test_lands_on_the_seeded_row_not_a_quarantined_one(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    assert venue.source == "seed"
    assert venue.region == "East Bay"
    ingest_scraped_shows(conn, venue, _scraped())
    # Reachable by the East Bay region filter — the thing the aggregator row,
    # with its empty region, could never do.
    east_bay = shows_repo.list(conn, ShowFilters(regions=["East Bay"]))
    assert any(s.venue_id == venue.id for s in east_bay)
