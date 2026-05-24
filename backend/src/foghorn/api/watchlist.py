"""Watchlist management endpoints (Phase 4.1).

``GET`` lists entries, ``POST`` adds one (canonicalizing the display name),
``DELETE`` removes by canonical name. Single-tenant. The watchlist *filter* on
shows lives on ``GET /api/shows?watchlist=true`` (see ``api/shows.py``); this
module is the CRUD surface.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from foghorn.ingest.pipeline import canonicalize
from foghorn.models import Watchlist
from foghorn.repo import db
from foghorn.repo import watchlist as watchlist_repo

router = APIRouter()


class WatchlistEntryView(BaseModel):
    canonical_name: str
    display_name: str
    added_at: str
    notes: str | None


class WatchlistCreate(BaseModel):
    display_name: str
    notes: str | None = None


def _to_view(entry: Watchlist) -> WatchlistEntryView:
    return WatchlistEntryView(
        canonical_name=entry.canonical_name,
        display_name=entry.display_name,
        added_at=entry.added_at,
        notes=entry.notes,
    )


@router.get("/api/watchlist", response_model=list[WatchlistEntryView])
def list_watchlist() -> list[WatchlistEntryView]:
    conn = db.connect()
    try:
        return [_to_view(entry) for entry in watchlist_repo.list_all(conn)]
    finally:
        conn.close()


@router.post("/api/watchlist", response_model=WatchlistEntryView)
def add_watchlist(body: WatchlistCreate) -> WatchlistEntryView:
    display_name = body.display_name.strip()
    # Reject names that canonicalize to nothing (empty / punctuation only) —
    # they'd be an unusable match key.
    if not display_name or not canonicalize(display_name):
        raise HTTPException(status_code=422, detail="display_name must contain a name")
    conn = db.connect()
    try:
        entry = watchlist_repo.add(conn, display_name, body.notes)
    finally:
        conn.close()
    return _to_view(entry)


@router.delete("/api/watchlist/{canonical_name}", status_code=204)
def delete_watchlist(canonical_name: str) -> Response:
    conn = db.connect()
    try:
        removed = watchlist_repo.remove(conn, canonical_name)
    finally:
        conn.close()
    if not removed:
        raise HTTPException(status_code=404, detail="not on watchlist")
    return Response(status_code=204)
