"""Manual event entry: ``POST /api/events`` + ``DELETE /api/events/{id}``.

Not every show foghorn should know about comes from a scraper — house
concerts, one-off spaces, venues whose calendars are Instagram-only. A manual
event rides the exact same ingest path as scraped shows (same normalization,
canonicalization, and natural-key dedup) but is stamped ``source='manual'``,
which keeps it deletable here and lets the UI badge it.

The venue is either an existing slug or a new name: unknown venues are
created as ``source='manual'`` rows (visible in ``GET /api/venues`` despite
having no scraper). Single-tenant, no auth — same posture as the watchlist.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from foghorn.api.auth import require_admin
from foghorn.ingest.pipeline import canonicalize, ingest_scraped_shows
from foghorn.models import EventType, Region, ScrapedShow, Venue
from foghorn.repo import db
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo

# Manual events create/delete *global* show rows every user sees, so the whole
# surface is admin-only (August 2026 multi-user).
router = APIRouter(dependencies=[Depends(require_admin)])

MANUAL_SOURCE_URL = "manual://user-entry"


class NewVenue(BaseModel):
    """A venue foghorn doesn't track yet. Only the name is required."""

    name: str = Field(min_length=1)
    neighborhood: str | None = None
    region: Region | None = None
    address: str | None = None
    website_url: str | None = None
    genre: str | None = None


class ManualEvent(BaseModel):
    """The POST body. Exactly one of ``venue_slug`` / ``venue`` is required."""

    venue_slug: str | None = None
    venue: NewVenue | None = None
    headliner: str = Field(min_length=1)
    support: list[str] = Field(default_factory=list)
    date: dt.date
    time: dt.time
    doors_time: dt.time | None = None
    ticket_url: str | None = None
    price_text: str | None = None
    # Jam sessions are mostly hand-entered — this is where they come in.
    event_type: EventType = "show"
    # Per-show genre; normalized to the coarse vocabulary where it maps, kept
    # verbatim otherwise. Empty = the venue's default genre applies.
    genre: str | None = None
    # Where the user learned about the show (flyer link, IG post, artist
    # site); becomes the row's provenance like a scraper's source_url.
    source_url: str | None = None


class ManualEventView(BaseModel):
    id: int
    venue_slug: str
    headliner: str
    start_local_date: str
    start_local_time: str


def _venue_slug_for(name: str) -> str:
    slug = canonicalize(name).replace(" ", "_")
    if not slug:
        raise HTTPException(status_code=422, detail="venue name has no usable characters")
    return slug


def _resolve_venue(conn: sqlite3.Connection, event: ManualEvent) -> Venue:
    if (event.venue_slug is None) == (event.venue is None):
        raise HTTPException(
            status_code=422, detail="provide exactly one of venue_slug or venue"
        )
    if event.venue_slug is not None:
        venue = venues_repo.get_by_slug(conn, event.venue_slug)
        if venue is None:
            raise HTTPException(status_code=404, detail="unknown venue slug")
        return venue
    assert event.venue is not None
    slug = _venue_slug_for(event.venue.name)
    existing = venues_repo.get_by_slug(conn, slug)
    if existing is not None:
        return existing  # name matched a known venue; don't duplicate
    return venues_repo.upsert(
        conn,
        Venue(
            slug=slug,
            name=event.venue.name.strip(),
            neighborhood=event.venue.neighborhood,
            region=event.venue.region,
            address=event.venue.address,
            tz="America/Los_Angeles",
            website_url=event.venue.website_url,
            calendar_url=event.venue.website_url or MANUAL_SOURCE_URL,
            genre=event.venue.genre,
            source="manual",
        ),
    )


def create_manual_event(conn: sqlite3.Connection, event: ManualEvent) -> ManualEventView:
    """The create-event internals, callable outside the route: the inbox
    approve endpoint (Phase 8) funnels reviewed emails through this exact
    path so every manual show is normalized/deduped identically."""
    venue = _resolve_venue(conn, event)
    scraped = ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw=event.headliner.strip(),
        support_raw=[s.strip() for s in event.support if s.strip()],
        start_local=dt.datetime.combine(event.date, event.time),
        doors_local=(
            dt.datetime.combine(event.date, event.doors_time)
            if event.doors_time is not None
            else None
        ),
        ticket_url=event.ticket_url,
        price_text=event.price_text,
        source_url=event.source_url or MANUAL_SOURCE_URL,
        event_type=event.event_type,
        genre=event.genre,
    )
    result = ingest_scraped_shows(conn, venue, [scraped], source="manual")
    if result.errors:
        raise HTTPException(status_code=422, detail=result.errors[0])
    stored = shows_repo.get_by_natural_key(
        conn,
        venue.id if venue.id is not None else -1,
        event.date.isoformat(),
        event.time.strftime("%H:%M"),
        canonicalize(event.headliner),
    )
    assert stored is not None and stored.id is not None
    return ManualEventView(
        id=stored.id,
        venue_slug=venue.slug,
        headliner=event.headliner.strip(),
        start_local_date=stored.start_local_date,
        start_local_time=stored.start_local_time,
    )


@router.post("/api/events", response_model=ManualEventView, status_code=201)
def create_event(event: ManualEvent) -> ManualEventView:
    conn = db.connect()
    try:
        return create_manual_event(conn, event)
    finally:
        conn.close()


@router.delete("/api/events/{show_id}", status_code=204)
def delete_event(show_id: int) -> None:
    conn = db.connect()
    try:
        show = shows_repo.get_by_id(conn, show_id)
        if show is None:
            raise HTTPException(status_code=404, detail="no such show")
        if show.source != "manual":
            raise HTTPException(
                status_code=403,
                detail="only manually-entered events can be deleted "
                "(scraped rows would come back on the next refresh)",
            )
        deleted = shows_repo.delete_manual(conn, show_id)
        assert deleted
    finally:
        conn.close()
