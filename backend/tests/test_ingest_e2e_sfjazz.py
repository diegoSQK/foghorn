"""End-to-end: the SFJAZZ fixture run through the ingest pipeline.

The property that matters here is that only the Center's own rooms are ingested
under ``sfjazz``. SFJAZZ presents off-site too, and the runner ingests a
registered scraper's whole output against one venue with ``prune=True`` — so
routing has to happen before ingest, not after.
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
from foghorn.scrapers import sfjazz

FIXTURE = Path(__file__).parent / "fixtures" / "sfjazz_2026_08.json"
TODAY = dt.date(2026, 8, 11)


def _scraped() -> list[ScrapedShow]:
    events: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return sfjazz.parse_events(events, today=TODAY)


def _center_only() -> list[ScrapedShow]:
    return [s for s in _scraped() if s.venue_slug == sfjazz.VENUE_SLUG]


@pytest.fixture
def venue(conn: sqlite3.Connection) -> Venue:
    seed(conn)
    resolved = venues_repo.get_by_slug(conn, "sfjazz")
    assert resolved is not None
    return resolved


def test_seed_row_now_has_a_real_calendar_url(venue: Venue) -> None:
    # sfjazz was the last Phase 2 venue still carrying the "TBD" placeholder.
    assert venue.calendar_url == "https://www.sfjazz.org/calendar/"
    assert venue.region == "SF"


def test_only_center_shows_are_ingested(conn: sqlite3.Connection, venue: Venue) -> None:
    result = ingest_scraped_shows(conn, venue, _center_only())
    assert result.errors == []
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["sfjazz"]))
    assert len(stored) == len(_center_only())
    # Brad Mehldau's Paramount date is in the scraper's output but must not
    # land under sfjazz.
    names = {p.display_name for s in stored for p in s.performers}
    assert not any("Mehldau" in n for n in names)


def test_local_times_convert_to_utc(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _center_only())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["sfjazz"]))
    take6 = min(
        (s for s in stored if any(p.display_name == "Take 6" for p in s.performers)),
        key=lambda s: s.start_utc,
    )
    # 2026-08-13 19:30 PDT (UTC-7) == 2026-08-14 02:30 UTC.
    assert take6.start_local_date == "2026-08-13"
    assert take6.start_local_time == "19:30"
    assert take6.start_utc.startswith("2026-08-14T02:30")


def test_sidemen_land_on_the_bill(conn: sqlite3.Connection, venue: Venue) -> None:
    # This is what lets the watchlist follow a player across bands.
    ingest_scraped_shows(conn, venue, _center_only())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["sfjazz"]))
    take6 = next(s for s in stored if any(p.display_name == "Take 6" for p in s.performers))
    roles = {p.display_name: p.role for p in take6.performers}
    assert roles["Take 6"] == "headliner"
    assert roles.get("Alvin Chea") == "support"


def test_sfjam_persists_as_a_jam(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _center_only())
    stored = shows_repo.list(conn, ShowFilters(venue_slugs=["sfjazz"]))
    jams = [s for s in stored if s.event_type == "jam"]
    assert len(jams) == 1
    assert jams[0].start_local_date == "2026-09-14"


def test_reingest_is_idempotent(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, _center_only())
    before = len(shows_repo.list(conn, ShowFilters()))
    ingest_scraped_shows(conn, venue, _center_only())
    assert len(shows_repo.list(conn, ShowFilters())) == before
