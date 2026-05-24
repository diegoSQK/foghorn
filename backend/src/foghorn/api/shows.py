"""``GET /api/shows`` — the filtered show listing the frontend renders.

Read-only. Opens a SQLite connection per request (cheap, and keeps each request
on a single thread so the default ``check_same_thread`` guard is satisfied).
Phase 3 adds region / neighborhood / performer-search params; this ships the
date-window + venue slice.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from fastapi import APIRouter, Query
from pydantic import BaseModel

from foghorn.models import Show, ShowFilters, Venue
from foghorn.repo import db
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo

router = APIRouter()

DEFAULT_WINDOW_DAYS = 30


class VenueView(BaseModel):
    slug: str
    name: str
    neighborhood: str | None
    region: str | None


class PerformerView(BaseModel):
    display: str
    canonical: str


class ShowView(BaseModel):
    venue: VenueView
    start_local_date: str
    start_local_time: str
    doors_local_time: str | None
    headliner: PerformerView
    support: list[PerformerView]
    ticket_url: str | None
    price_text: str | None
    source_url: str


def _to_view(show: Show, venue: Venue) -> ShowView:
    support = [
        PerformerView(display=p.display_name, canonical=p.canonical_name)
        for p in show.performers
        if p.role == "support"
    ]
    headliner_performer = next(
        (p for p in show.performers if p.role == "headliner"), None
    )
    headliner = (
        PerformerView(
            display=headliner_performer.display_name,
            canonical=headliner_performer.canonical_name,
        )
        if headliner_performer is not None
        # Defensive: every ingested show has a headliner, but never 500 if not.
        else PerformerView(display=show.headliner_canonical, canonical=show.headliner_canonical)
    )
    return ShowView(
        venue=VenueView(
            slug=venue.slug,
            name=venue.name,
            neighborhood=venue.neighborhood,
            region=venue.region,
        ),
        start_local_date=show.start_local_date,
        start_local_time=show.start_local_time,
        doors_local_time=show.doors_local_time,
        headliner=headliner,
        support=support,
        ticket_url=show.ticket_url,
        price_text=show.price_text,
        source_url=show.source_url,
    )


def build_show_views(
    conn: sqlite3.Connection,
    *,
    venue: str | None,
    from_date: str,
    to_date: str,
) -> list[ShowView]:
    """Query shows for the window and assemble the response views. Split out so
    it's unit-testable against a connection without going through HTTP."""
    filters = ShowFilters(
        venue_slugs=[venue] if venue else None,
        from_date=from_date,
        to_date=to_date,
    )
    shows = shows_repo.list(conn, filters)
    venues_by_id = {v.id: v for v in venues_repo.list_all(conn)}
    return [_to_view(show, venues_by_id[show.venue_id]) for show in shows]


@router.get("/api/shows", response_model=list[ShowView])
def list_shows(
    venue: str | None = Query(default=None, description="venue slug"),
    from_: str | None = Query(
        default=None, alias="from", description="ISO date (default: today)"
    ),
    to: str | None = Query(
        default=None, description="ISO date (default: today + 30 days)"
    ),
) -> list[ShowView]:
    today = dt.date.today()
    from_date = from_ or today.isoformat()
    to_date = to or (today + dt.timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()

    conn = db.connect()
    try:
        return build_show_views(
            conn, venue=venue, from_date=from_date, to_date=to_date
        )
    finally:
        conn.close()
