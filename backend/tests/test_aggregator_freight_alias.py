"""Regression: Bay Improviser's "The Freight" must resolve to the seeded
Freight & Salvage row, not to a quarantined aggregator venue.

This is the trap the alias entry exists for. ``resolve_venue`` tries the alias
map, then an *exact* canonical-name match, then token-subset. Bay Improviser
bills the venue as "The Freight", which ``_strip_leading_the`` reduces to
``"freight"`` — and an aggregator-created venue *named* "The Freight" (which is
exactly what the live DB grew before this scraper existed) reduces to the same
string. So the quarantined row wins the exact pass, while the seeded
"Freight & Salvage" could only ever have matched on token-subset, which runs
later. Without the alias, one room ends up split across two venue rows with its
shows divided between them.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.aggregators.ingest import resolve_venue
from foghorn.aggregators.models import AggregatedEvent
from foghorn.models import Venue
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed

START = dt.datetime(2026, 9, 3, 20, 0)


def _event(venue_name: str) -> AggregatedEvent:
    return AggregatedEvent(
        venue_name_raw=venue_name,
        venue_address_raw="2020 Addison St. Berkeley",
        headliner_raw="Some Quartet",
        headliner_is_description=False,
        start_local=START,
        source_url="https://www.bayimproviser.com/calendar.aspx",
    )


def test_the_freight_resolves_to_the_seeded_row(conn: sqlite3.Connection) -> None:
    seed(conn)
    for billing in ("The Freight", "the freight", "Freight"):
        assert resolve_venue(conn, _event(billing)).slug == "freight_and_salvage", billing


def test_seeded_row_wins_over_a_preexisting_aggregator_row(
    conn: sqlite3.Connection,
) -> None:
    # Reproduces the live DB's state: a quarantined "The Freight" row created
    # by the aggregator before the venue had a scraper. It exact-matches the
    # billing, so without the alias it would keep absorbing these events.
    seed(conn)
    stale = venues_repo.upsert(
        conn,
        Venue(
            slug="the_freight",
            name="The Freight",
            tz="America/Los_Angeles",
            calendar_url="https://www.bayimproviser.com/calendar.aspx",
            source="aggregator",
        ),
    )
    resolved = resolve_venue(conn, _event("The Freight"))
    assert resolved.slug == "freight_and_salvage"
    assert resolved.id != stale.id
    assert resolved.source == "seed"


def test_full_name_billing_still_resolves(conn: sqlite3.Connection) -> None:
    # Belt and braces: the unabbreviated spellings resolve too, via exact match
    # and token-subset respectively.
    seed(conn)
    assert resolve_venue(conn, _event("Freight & Salvage")).slug == "freight_and_salvage"
    assert (
        resolve_venue(conn, _event("Freight & Salvage Coffeehouse")).slug
        == "freight_and_salvage"
    )
