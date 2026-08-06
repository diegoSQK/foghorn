"""End-to-end for the group-feed model: an ensemble's events land at the
halls they actually play (seeded or quarantined), the group rides the bill
as a support performer, and watchlisting the group surfaces its shows across
venues — including quarantined off-site ones (the watchlist bypass)."""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.aggregators.ingest import ingest_aggregated_events
from foghorn.aggregators.models import AggregatedEvent
from foghorn.api.shows import build_show_views
from foghorn.models import User
from foghorn.repo import venues as venues_repo
from foghorn.repo import watchlist as watchlist_repo
from foghorn.repo.seed_venues import seed

_GROUP = "San Francisco Symphony"


def _event(venue: str, program: str, start: dt.datetime) -> AggregatedEvent:
    return AggregatedEvent(
        venue_name_raw=venue,
        headliner_raw=program,
        support_raw=[_GROUP],
        start_local=start,
        ticket_url="https://www.sfsymphony.org/Buy-Tickets/x",
        source_url="https://www.sfsymphony.org/Buy-Tickets/x",
    )


def test_group_feed_routes_to_halls_and_watchlist_follows(
    conn: sqlite3.Connection, user: User
) -> None:
    assert user.id is not None
    seed(conn)
    result = ingest_aggregated_events(
        conn,
        [
            _event("Davies Symphony Hall", "Mahler 9", dt.datetime(2026, 9, 10, 19, 30)),
            # Not seeded -> quarantined aggregator venue, auto-created.
            _event(
                "Gunn Theater at the Legion of Honor",
                "Chamber Series: Brahms",
                dt.datetime(2026, 9, 12, 14, 0),
            ),
        ],
        "sf_symphony",
    )
    assert result.errors == []
    assert result.created == 2

    # Events landed at the actual halls — the group is not a venue.
    davies = venues_repo.get_by_slug(conn, "davies_symphony_hall")
    assert davies is not None and davies.source == "seed"
    gunn = venues_repo.get_by_slug(conn, "gunn_theater_at_the_legion_of_honor")
    assert gunn is not None and gunn.source == "aggregator"

    # The ensemble rides the bill (support), and ticket_url survives ingest.
    row = conn.execute(
        "SELECT s.id, s.ticket_url FROM shows s WHERE s.venue_id = ?",
        (davies.id,),
    ).fetchone()
    assert row["ticket_url"] == "https://www.sfsymphony.org/Buy-Tickets/x"
    support = conn.execute(
        "SELECT p.display_name FROM show_performers sp "
        "JOIN performers p ON p.id = sp.performer_id "
        "WHERE sp.show_id = ? AND sp.role = 'support'",
        (row["id"],),
    ).fetchall()
    assert [r["display_name"] for r in support] == [_GROUP]

    # Watchlisting the group surfaces both shows — the Davies one normally,
    # the Legion of Honor one through the quarantine watchlist bypass.
    watchlist_repo.add(conn, user.id, _GROUP)
    views = build_show_views(
        conn,
        venue_slugs=None,
        from_date="2026-09-01",
        to_date="2026-09-30",
        watchlist=True,
        user_id=user.id,
    )
    assert [(v.headliner.display, v.venue.slug) for v in views] == [
        ("Mahler 9", "davies_symphony_hall"),
        ("Chamber Series: Brahms", "gunn_theater_at_the_legion_of_honor"),
    ]
    # Without the watchlist filter, the quarantined hall stays hidden.
    default_views = build_show_views(
        conn,
        venue_slugs=None,
        from_date="2026-09-01",
        to_date="2026-09-30",
    )
    assert [v.venue.slug for v in default_views] == ["davies_symphony_hall"]
