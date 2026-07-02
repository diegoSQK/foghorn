"""Integration tests for the ingest pipeline."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo


def _scraped(
    headliner: str,
    start: datetime,
    *,
    support: list[str] | None = None,
    doors: datetime | None = None,
    ticket_url: str | None = None,
    price_text: str | None = None,
) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="sfjazz",
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        doors_local=doors,
        ticket_url=ticket_url,
        price_text=price_text,
        source_url="https://www.sfjazz.org/tickets/show",
    )


def test_created_updated_counts_and_state(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # An existing row to dedupe against.
    first = ingest_scraped_shows(
        conn, venue, [_scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0))]
    )
    assert (first.created, first.updated, first.errors) == (1, 0, [])

    # One new, one exact duplicate, one same-headliner-different-time (new key).
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Kamasi Washington", datetime(2026, 6, 10, 20, 0)),  # new
            _scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0)),  # duplicate
            _scraped("Joshua Redman", datetime(2026, 6, 1, 22, 0)),  # later set, new
        ],
    )
    assert result.created == 2
    assert result.updated == 1
    assert result.errors == []
    assert len(shows_repo.list(conn, ShowFilters())) == 3


def test_computes_utc_from_venue_tz(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, [_scraped("X", datetime(2026, 6, 1, 20, 0))])
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.start_local_date == "2026-06-01"
    assert show.start_local_time == "20:00"
    # 8pm PDT (UTC-7) on June 1 -> 03:00 UTC on June 2.
    assert show.start_utc == "2026-06-02T03:00:00+00:00"


def test_stores_doors_support_and_bill_order(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped(
                "Headliner",
                datetime(2026, 6, 1, 20, 0),
                support=["Opener A", "Opener B"],
                doors=datetime(2026, 6, 1, 19, 0),
                ticket_url="https://tix.example.com/x",
                price_text="$30",
            )
        ],
    )
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.doors_local_time == "19:00"
    assert show.ticket_url == "https://tix.example.com/x"
    assert show.price_text == "$30"
    bill = [(p.role, p.position, p.display_name) for p in show.performers]
    assert bill == [
        ("headliner", 0, "Headliner"),
        ("support", 1, "Opener A"),
        ("support", 2, "Opener B"),
    ]


def test_preserves_display_name_and_canonicalizes(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Café Tacvba", datetime(2026, 6, 1, 20, 0))]
    )
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.headliner_canonical == "cafe tacvba"
    headliner = next(p for p in show.performers if p.role == "headliner")
    assert headliner.display_name == "Café Tacvba"  # verbatim, never normalized
    assert headliner.canonical_name == "cafe tacvba"


def test_performer_reused_across_shows(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0)),
            _scraped("Joshua Redman", datetime(2026, 6, 2, 20, 0)),
        ],
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM performers WHERE canonical_name = 'joshua redman'"
    ).fetchone()[0]
    assert count == 1  # one performer row, two shows


def test_bad_show_is_isolated_in_errors(conn: sqlite3.Connection) -> None:
    bad_venue = venues_repo.upsert(
        conn,
        Venue(
            slug="bad",
            name="Bad Venue",
            tz="Not/AZone",  # unresolvable -> raises during ingest
            calendar_url="https://example.com/cal",
        ),
    )
    result = ingest_scraped_shows(
        conn, bad_venue, [_scraped("X", datetime(2026, 6, 1, 20, 0))]
    )
    assert result.created == 0
    assert result.updated == 0
    assert len(result.errors) == 1


def test_duplicate_billing_collapses_to_first_occurrence(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # Venues sometimes repeat an act on the bill (headliner listed again in
    # support, or "TBA" filling several slots). The bill must dedupe by
    # performer rather than violating the show_performers PK.
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped(
                "TBA",
                datetime(2026, 9, 2, 19, 45),
                support=["TBA", "Opener A", "TBA", "Opener A"],
            )
        ],
    )
    assert result.errors == []
    assert result.created == 1
    [show] = shows_repo.list(conn, ShowFilters())
    got = [(p.role, p.position, p.display_name) for p in show.performers]
    assert got == [("headliner", 0, "TBA"), ("support", 1, "Opener A")]
