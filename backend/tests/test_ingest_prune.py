"""Stale-row reaping (``ingest_scraped_shows(prune=True)``).

The natural key includes the billing and start time, so a venue *editing* a
listing inserts a new row instead of updating the old one — without pruning the
edited-away row lingers as a duplicate forever, and cancelled shows never
disappear. These tests pin the behaviour and, more importantly, the guards:
pruning deletes rows, so it must never fire on a broken run or reach beyond
what the run actually covered.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo


def _scraped(headliner: str, start: datetime) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="sfjazz",
        headliner_raw=headliner,
        start_local=start,
        source_url="https://example.com/show",
    )


def _headliners(conn: sqlite3.Connection) -> list[str]:
    return sorted(s.headliner_canonical for s in shows_repo.list(conn, ShowFilters()))


def test_retitled_show_replaces_rather_than_duplicates(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # First run: the venue's original billing (with a typo).
    ingest_scraped_shows(
        conn, venue, [_scraped("Non Stop Bhagra", datetime(2026, 8, 22, 19, 0))],
        prune=True,
    )
    assert _headliners(conn) == ["non stop bhagra"]

    # Venue fixes the typo. Same night, new natural key -> new row; the old
    # one is no longer listed, so it must be reaped, not left as a duplicate.
    result = ingest_scraped_shows(
        conn, venue, [_scraped("Non Stop Bhangra", datetime(2026, 8, 22, 19, 0))],
        prune=True,
    )
    assert result.created == 1
    assert result.reaped == 1
    assert _headliners(conn) == ["non stop bhangra"]


def test_rescheduled_show_replaces_rather_than_duplicates(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Henry Plumb Trio", datetime(2026, 7, 26, 18, 0))],
        prune=True,
    )
    result = ingest_scraped_shows(
        conn, venue, [_scraped("Henry Plumb Trio", datetime(2026, 7, 26, 18, 30))],
        prune=True,
    )
    assert result.reaped == 1
    rows = shows_repo.list(conn, ShowFilters())
    assert [r.start_local_time for r in rows] == ["18:30"]


def test_genuine_early_late_sets_both_survive(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # Two sets the same night are real distinct shows, not duplicates — a run
    # listing both must keep both.
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("April Varner Quintet", datetime(2026, 7, 22, 19, 0)),
            _scraped("April Varner Quintet", datetime(2026, 7, 22, 20, 45)),
        ],
        prune=True,
    )
    assert result.reaped == 0
    assert len(shows_repo.list(conn, ShowFilters())) == 2


def test_empty_run_never_prunes(conn: sqlite3.Connection, venue: Venue) -> None:
    # A scraper broken by a markup change returns [] — that must never be read
    # as "the venue cancelled everything".
    ingest_scraped_shows(
        conn, venue, [_scraped("Real Show", datetime(2026, 9, 1, 20, 0))], prune=True
    )
    result = ingest_scraped_shows(conn, venue, [], prune=True)
    assert result.reaped == 0
    assert _headliners(conn) == ["real show"]


def test_run_with_errors_never_prunes(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Keeper", datetime(2026, 9, 2, 20, 0))], prune=True
    )
    # A show whose tz conversion blows up lands in errors; a partially-failed
    # run isn't authoritative, so nothing is reaped.
    broken = ScrapedShow(
        venue_slug="sfjazz",
        headliner_raw="Broken",
        start_local=datetime(2026, 9, 3, 20, 0),
        source_url="https://example.com/x",
    )
    bad_venue = venue.model_copy(update={"tz": "Not/AZone"})
    result = ingest_scraped_shows(conn, bad_venue, [broken], prune=True)
    assert result.errors
    assert result.reaped == 0
    assert "keeper" in _headliners(conn)


def test_prune_is_scoped_to_the_span_the_run_returned(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # A far-future row outside this run's window must not be reaped just
    # because a short-window run didn't mention it.
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Near Show", datetime(2026, 7, 25, 20, 0)),
            _scraped("Far Future Show", datetime(2027, 3, 1, 20, 0)),
        ],
        prune=True,
    )
    # Later run covers only late July — the 2027 row is outside its span.
    result = ingest_scraped_shows(
        conn, venue, [_scraped("Near Show Renamed", datetime(2026, 7, 25, 20, 0))],
        prune=True,
    )
    assert result.reaped == 1  # only the retitled July row
    assert _headliners(conn) == ["far future show", "near show renamed"]


def test_prune_leaves_manual_and_aggregator_rows_alone(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Hand Entered", datetime(2026, 10, 1, 20, 0))],
        source="manual",
    )
    ingest_scraped_shows(
        conn, venue, [_scraped("From Aggregator", datetime(2026, 10, 2, 20, 0))],
        source="aggregator",
    )
    # A scraped run spanning those dates must not touch either.
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Scraped A", datetime(2026, 10, 1, 21, 0)),
            _scraped("Scraped B", datetime(2026, 10, 3, 21, 0)),
        ],
        prune=True,
    )
    assert result.reaped == 0
    assert _headliners(conn) == [
        "from aggregator", "hand entered", "scraped a", "scraped b",
    ]


def test_prune_defaults_off(conn: sqlite3.Connection, venue: Venue) -> None:
    # The aggregator ingests one event at a time through this same function;
    # pruning by default would wipe the venue on every call.
    ingest_scraped_shows(
        conn, venue, [_scraped("First", datetime(2026, 11, 1, 20, 0))]
    )
    result = ingest_scraped_shows(
        conn, venue, [_scraped("Second", datetime(2026, 11, 2, 20, 0))]
    )
    assert result.reaped == 0
    assert _headliners(conn) == ["first", "second"]
