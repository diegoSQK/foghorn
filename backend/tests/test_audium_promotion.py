"""Promoting a quarantined aggregator venue to a seeded one.

Audium's dates were already arriving via Bay Improviser, but the row the
aggregator created had no region, neighborhood or genre — so no filter could
reach it and the long-tail toggle hid it by default. Seeding the same slug
promotes the existing row rather than creating a second one, which is the
property worth pinning: its shows must survive the promotion.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.aggregators.ingest import resolve_venue
from foghorn.aggregators.models import AggregatedEvent
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed


def _quarantined_audium(conn: sqlite3.Connection) -> Venue:
    """The row as Bay Improviser leaves it: no region, no genre, quarantined."""
    return venues_repo.upsert(
        conn,
        Venue(
            slug="audium",
            name="Audium",
            address="1616 Bush St. SF",
            tz="America/Los_Angeles",
            calendar_url="https://www.bayimproviser.com/calendar.aspx",
            source="aggregator",
        ),
    )


def test_seed_promotes_the_existing_row_and_keeps_its_shows(
    conn: sqlite3.Connection,
) -> None:
    stale = _quarantined_audium(conn)
    ingest_scraped_shows(
        conn,
        stale,
        [
            ScrapedShow(
                venue_slug="audium",
                headliner_raw="Sound Sculpture Programme",
                start_local=dt.datetime(2026, 8, 29, 20, 0),
                source_url="https://www.bayimproviser.com/calendar.aspx",
            )
        ],
        source="aggregator",
    )

    seed(conn)

    rows = [v for v in venues_repo.list_all(conn) if v.slug == "audium"]
    assert len(rows) == 1, "promotion must update in place, not fork the venue"
    promoted = rows[0]
    assert promoted.id == stale.id
    assert promoted.source == "seed"  # out of quarantine
    assert promoted.region == "SF"  # ...and now reachable by filter
    assert promoted.neighborhood == "Polk Gulch"
    assert promoted.genre == "electronic"

    # The whole point: the shows already collected survive.
    kept = shows_repo.list(conn, ShowFilters(venue_slugs=["audium"]))
    assert len(kept) == 1


def test_future_aggregator_events_still_resolve_to_it(
    conn: sqlite3.Connection,
) -> None:
    # No VENUE_ALIASES entry is needed here, unlike Freight & Salvage: the
    # seeded name is identical to the billing, so the exact-canonical pass
    # matches the promoted row directly.
    seed(conn)
    resolved = resolve_venue(
        conn,
        AggregatedEvent(
            venue_name_raw="Audium",
            venue_address_raw="1616 Bush St. SF",
            headliner_raw="Some Programme",
            headliner_is_description=False,
            start_local=dt.datetime(2026, 9, 5, 20, 0),
            source_url="https://www.bayimproviser.com/calendar.aspx",
        ),
    )
    assert resolved.slug == "audium"
    assert resolved.source == "seed"


def test_it_is_seeded_without_a_scraper(conn: sqlite3.Connection) -> None:
    # Aggregator-fed and scraperless by design, like the group-feed halls.
    from foghorn.scrapers import REGISTERED_SCRAPERS

    seed(conn)
    assert venues_repo.get_by_slug(conn, "audium") is not None
    assert "audium" not in REGISTERED_SCRAPERS
