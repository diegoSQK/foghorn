"""``GET /api/shows`` — the filtered show listing the frontend renders.

Read-only. Opens a SQLite connection per request (cheap, and keeps each request
on a single thread so the default ``check_same_thread`` guard is satisfied).
Phase 3 adds region / neighborhood / performer-search params; this ships the
date-window + venue slice.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from foghorn.ingest.pipeline import canonicalize
from foghorn.models import EventType, Origin, Region, Show, ShowFilters, Venue
from foghorn.repo import db
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo import watched_venues as watched_venues_repo
from foghorn.repo import watchlist as watchlist_repo

router = APIRouter()

DEFAULT_WINDOW_DAYS = 30

# The known regions, used to narrow the free-text ?region= param to the
# Region literal (and ignore anything else rather than 400).
_REGIONS: tuple[Region, ...] = (
    "SF", "East Bay", "North Bay", "Peninsula", "South Bay", "Santa Cruz",
)


class VenueView(BaseModel):
    slug: str
    name: str
    neighborhood: str | None
    region: str | None
    genre: str | None


class PerformerView(BaseModel):
    display: str
    canonical: str
    origin: str | None = None  # 'local' | 'touring' | None (unknown)


class ShowView(BaseModel):
    id: int
    source: str  # 'scrape' | 'manual' — manual rows are user-deletable
    event_type: str  # 'show' | 'jam'
    # Resolved genre: the per-show override when the source published one,
    # else the venue's default lean. None when neither is known.
    genre: str | None
    venue: VenueView
    start_local_date: str
    start_local_time: str
    end_local_time: str | None
    doors_local_time: str | None
    headliner: PerformerView
    support: list[PerformerView]
    ticket_url: str | None
    price_text: str | None
    source_url: str


def _to_view(show: Show, venue: Venue) -> ShowView:
    support = [
        PerformerView(
            display=p.display_name, canonical=p.canonical_name, origin=p.origin
        )
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
            origin=headliner_performer.origin,
        )
        if headliner_performer is not None
        # Defensive: every ingested show has a headliner, but never 500 if not.
        else PerformerView(display=show.headliner_canonical, canonical=show.headliner_canonical)
    )
    assert show.id is not None  # read paths always return persisted rows
    return ShowView(
        id=show.id,
        source=show.source,
        event_type=show.event_type,
        # Resolution chain: per-show override > headliner's performer-level
        # genre > venue default.
        genre=(
            show.genre_override
            or (headliner_performer.genre if headliner_performer else None)
            or venue.genre
        ),
        venue=VenueView(
            slug=venue.slug,
            name=venue.name,
            neighborhood=venue.neighborhood,
            region=venue.region,
            genre=venue.genre,
        ),
        start_local_date=show.start_local_date,
        start_local_time=show.start_local_time,
        end_local_time=show.end_local_time,
        doors_local_time=show.doors_local_time,
        headliner=headliner,
        support=support,
        ticket_url=show.ticket_url,
        price_text=show.price_text,
        source_url=show.source_url,
    )


def _parse_venue_slugs(venues: str | None, venue: str | None) -> list[str] | None:
    """Resolve the venue filter from the multi-value ``venues=`` param (comma
    separated) or the legacy singular ``venue=``. An empty/blank list means
    "no constraint" (all venues), avoiding the empty-filter footgun."""
    if venues is not None:
        slugs = [s.strip() for s in venues.split(",") if s.strip()]
        return slugs or None
    if venue:
        return [venue]
    return None


def build_show_views(
    conn: sqlite3.Connection,
    *,
    venue_slugs: list[str] | None,
    from_date: str,
    to_date: str | None,
    time_of_day: Literal["early", "late"] | None = None,
    performer_query_canonical: str | None = None,
    region: Region | None = None,
    neighborhood: str | None = None,
    genre: str | None = None,
    origin: Origin | None = None,
    event_type: EventType | None = None,
    watchlist: bool = False,
    venue_watchlist: bool = False,
    long_tail: bool = False,
    limit: int | None = None,
) -> list[ShowView]:
    """Query shows for the window and assemble the response views. Split out so
    it's unit-testable against a connection without going through HTTP."""
    # When the watchlist filter is on, turn each entry's canonical name into a
    # token bag. An empty watchlist yields [] → shows.list matches nothing
    # (surfacing the empty state rather than flooding with all shows).
    watchlist_bags: list[list[str]] | None = None
    if watchlist:
        watchlist_bags = [
            entry.canonical_name.split() for entry in watchlist_repo.list_all(conn)
        ]
    watched_slugs: list[str] | None = None
    if venue_watchlist:
        watched_slugs = [e.venue_slug for e in watched_venues_repo.list_all(conn)]
    filters = ShowFilters(
        venue_slugs=venue_slugs,
        watched_venue_slugs=watched_slugs,
        include_long_tail=long_tail,
        from_date=from_date,
        to_date=to_date,
        time_of_day=time_of_day,
        performer_query_canonical=performer_query_canonical,
        watchlist_token_bags=watchlist_bags,
        region=region,
        neighborhood=neighborhood,
        genre=genre,
        origin=origin,
        event_type=event_type,
        limit=limit,
    )
    shows = shows_repo.list(conn, filters)
    venues_by_id = {v.id: v for v in venues_repo.list_all(conn)}
    return [_to_view(show, venues_by_id[show.venue_id]) for show in shows]


@router.get("/api/shows", response_model=list[ShowView])
def list_shows(
    venue: str | None = Query(
        default=None, description="single venue slug (legacy; prefer venues=)"
    ),
    venues: str | None = Query(
        default=None, description="comma-separated venue slugs"
    ),
    from_: str | None = Query(
        default=None, alias="from", description="ISO date (default: today)"
    ),
    to: str | None = Query(
        default=None,
        description="ISO date (default: today + 30 days), or 'all' for no upper bound",
    ),
    time_of_day: str | None = Query(
        default=None, description="early | late (filters by start time)"
    ),
    performer_query: str | None = Query(
        default=None, description="free-text performer name (canonicalized)"
    ),
    region: str | None = Query(
        default=None, description="SF | East Bay | Peninsula | South Bay | Santa Cruz"
    ),
    neighborhood: str | None = Query(
        default=None, description="venue neighborhood (case-insensitive exact)"
    ),
    genre: str | None = Query(
        default=None, description="venue-default genre (case-insensitive exact)"
    ),
    origin: str | None = Query(
        default=None, description="local | touring (any performer on the bill)"
    ),
    type: str | None = Query(
        default=None, description="show | jam (default: both)"
    ),
    watchlist: str | None = Query(
        default=None, description="'true' to filter to watchlist matches"
    ),
    venue_watchlist: str | None = Query(
        default=None, description="'true' to filter to watched venues"
    ),
    long_tail: str | None = Query(
        default=None,
        description="'true' to include shows at aggregator-discovered venues",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        description="cap the result count (chronological prefix); default: no cap",
    ),
) -> list[ShowView]:
    today = dt.date.today()
    from_date = from_ or today.isoformat()
    # 'all' lifts the upper bound (the repo layer skips the <= clause when
    # to_date is None) — the "everything ingested from here on" mode.
    to_date: str | None
    if to == "all":
        to_date = None
    else:
        to_date = to or (today + dt.timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()

    # Narrow to the Literal; unknown values are ignored rather than 400.
    tod: Literal["early", "late"] | None = None
    if time_of_day == "early":
        tod = "early"
    elif time_of_day == "late":
        tod = "late"

    # Canonicalize the query the same way performers are stored (Phase 1.2), so
    # "Joshua Redman" matches "joshua redman quartet". A query that's empty
    # after canonicalization (e.g. only punctuation) means "no filter".
    performer_canonical = canonicalize(performer_query) if performer_query else ""

    # Narrow region to a known value; unknown values are ignored, not a 400.
    reg: Region | None = next((r for r in _REGIONS if r == region), None)

    # Narrow origin the same way (mirrors time_of_day).
    org: Origin | None = None
    if origin == "local":
        org = "local"
    elif origin == "touring":
        org = "touring"

    etype: EventType | None = None
    if type == "show":
        etype = "show"
    elif type == "jam":
        etype = "jam"

    conn = db.connect()
    try:
        return build_show_views(
            conn,
            venue_slugs=_parse_venue_slugs(venues, venue),
            from_date=from_date,
            to_date=to_date,
            time_of_day=tod,
            performer_query_canonical=performer_canonical or None,
            region=reg,
            neighborhood=neighborhood or None,
            genre=genre or None,
            origin=org,
            event_type=etype,
            watchlist=watchlist == "true",
            venue_watchlist=venue_watchlist == "true",
            long_tail=long_tail == "true",
            limit=limit,
        )
    finally:
        conn.close()


class EventTypeUpdate(BaseModel):
    event_type: EventType


class EventTypeView(BaseModel):
    show_id: int
    event_type: EventType
    # The correction is stored as a venue+billing rule, so it also covers
    # future instances of a recurring session — surfaced so callers/UIs can
    # explain the scope.
    applies_to_billing: str


@router.put("/api/shows/{show_id}/event_type", response_model=EventTypeView)
def set_event_type(show_id: int, update: EventTypeUpdate) -> EventTypeView:
    """Manual event-type correction ("this is a jam session"). Permanent —
    stored as a venue+billing override rule that re-ingest never touches and
    that recurring instances of the same billing inherit. Same single-tenant
    no-auth posture as the performer origin/genre corrections."""
    conn = db.connect()
    try:
        show = shows_repo.get_by_id(conn, show_id)
        if show is None:
            raise HTTPException(status_code=404, detail="unknown show")
        shows_repo.set_event_type_override(
            conn, show.venue_id, show.headliner_canonical, update.event_type
        )
        return EventTypeView(
            show_id=show_id,
            event_type=update.event_type,
            applies_to_billing=show.headliner_canonical,
        )
    finally:
        conn.close()


@router.delete("/api/shows/{show_id}/event_type", status_code=204)
def clear_event_type(show_id: int) -> None:
    """Remove the manual correction; ingest's inferred type applies again."""
    conn = db.connect()
    try:
        show = shows_repo.get_by_id(conn, show_id)
        if show is None:
            raise HTTPException(status_code=404, detail="unknown show")
        shows_repo.clear_event_type_override(
            conn, show.venue_id, show.headliner_canonical
        )
    finally:
        conn.close()
