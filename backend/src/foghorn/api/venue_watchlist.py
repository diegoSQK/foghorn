"""Venue-watchlist endpoints (Phase 9): follow venues the way the performer
watchlist follows names. CRUD here; the filter lives on
``GET /api/shows?venue_watchlist=true``. Per-user since the multi-user re-key
(August 2026) — every endpoint requires a session."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from foghorn.api.auth import require_user
from foghorn.models import User
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo import watched_venues as watched_repo

router = APIRouter()


class WatchedVenueView(BaseModel):
    venue_slug: str
    name: str
    added_at: str
    notes: str | None


class WatchedVenueCreate(BaseModel):
    venue_slug: str
    notes: str | None = None


@router.get("/api/venues/watchlist", response_model=list[WatchedVenueView])
def list_watched(user: Annotated[User, Depends(require_user)]) -> list[WatchedVenueView]:
    assert user.id is not None
    conn = db.connect()
    try:
        names = {v.slug: v.name for v in venues_repo.list_all(conn)}
        return [
            WatchedVenueView(
                venue_slug=e.venue_slug,
                name=names.get(e.venue_slug, e.venue_slug),
                added_at=e.added_at,
                notes=e.notes,
            )
            for e in watched_repo.list_all(conn, user.id)
        ]
    finally:
        conn.close()


@router.post("/api/venues/watchlist", response_model=WatchedVenueView, status_code=201)
def add_watched(
    body: WatchedVenueCreate, user: Annotated[User, Depends(require_user)]
) -> WatchedVenueView:
    assert user.id is not None
    conn = db.connect()
    try:
        venue = venues_repo.get_by_slug(conn, body.venue_slug)
        if venue is None:
            raise HTTPException(status_code=404, detail="unknown venue slug")
        entry = watched_repo.add(conn, user.id, body.venue_slug, body.notes)
        return WatchedVenueView(
            venue_slug=entry.venue_slug,
            name=venue.name,
            added_at=entry.added_at,
            notes=entry.notes,
        )
    finally:
        conn.close()


@router.delete("/api/venues/watchlist/{venue_slug}", status_code=204)
def remove_watched(venue_slug: str, user: Annotated[User, Depends(require_user)]) -> Response:
    assert user.id is not None
    conn = db.connect()
    try:
        if not watched_repo.remove(conn, user.id, venue_slug):
            raise HTTPException(status_code=404, detail="venue not watched")
    finally:
        conn.close()
    return Response(status_code=204)
