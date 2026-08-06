"""Watchlist management endpoints (Phase 4.1).

``GET`` lists entries, ``POST`` adds one (canonicalizing the display name),
``DELETE`` removes by canonical name. ``GET /api/watchlist/digest`` returns the
next-N upcoming matches for a future cron/email/push consumer. Per-user since
the multi-user re-key (August 2026): every endpoint requires a session and
operates on the signed-in user's list. The watchlist *filter* on shows lives on
``GET /api/shows?watchlist=true`` (see ``api/shows.py``); this module is the
CRUD + digest surface.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from foghorn.api.auth import require_user
from foghorn.api.shows import ShowView, build_show_views
from foghorn.ingest.pipeline import canonicalize
from foghorn.models import User, Watchlist
from foghorn.repo import db
from foghorn.repo import watchlist as watchlist_repo
from foghorn.repo.performer_match import matches_token_bag

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
def list_watchlist(user: Annotated[User, Depends(require_user)]) -> list[WatchlistEntryView]:
    assert user.id is not None
    conn = db.connect()
    try:
        return [_to_view(entry) for entry in watchlist_repo.list_all(conn, user.id)]
    finally:
        conn.close()


@router.post("/api/watchlist", response_model=WatchlistEntryView)
def add_watchlist(
    body: WatchlistCreate, user: Annotated[User, Depends(require_user)]
) -> WatchlistEntryView:
    assert user.id is not None
    display_name = body.display_name.strip()
    # Reject names that canonicalize to nothing (empty / punctuation only) —
    # they'd be an unusable match key.
    if not display_name or not canonicalize(display_name):
        raise HTTPException(status_code=422, detail="display_name must contain a name")
    conn = db.connect()
    try:
        entry = watchlist_repo.add(conn, user.id, display_name, body.notes)
    finally:
        conn.close()
    return _to_view(entry)


@router.delete("/api/watchlist/{canonical_name}", status_code=204)
def delete_watchlist(
    canonical_name: str, user: Annotated[User, Depends(require_user)]
) -> Response:
    assert user.id is not None
    conn = db.connect()
    try:
        removed = watchlist_repo.remove(conn, user.id, canonical_name)
    finally:
        conn.close()
    if not removed:
        raise HTTPException(status_code=404, detail="not on watchlist")
    return Response(status_code=204)


class DigestMatch(ShowView):
    """A `/api/shows` row plus the watchlist name(s) that matched it. When the
    digest is asked to ``include_venues``, rows at a watched venue carry
    ``watched_venue: true`` — a row contributed *only* by its venue has an
    empty ``watchlist_matches``."""

    watchlist_matches: list[str]
    watched_venue: bool = False


class DigestResponse(BaseModel):
    generated_at: str  # ISO 8601 UTC
    matches: list[DigestMatch]


@router.get("/api/watchlist/digest", response_model=DigestResponse)
def watchlist_digest(
    user: Annotated[User, Depends(require_user)],
    days: int = Query(default=14, ge=1, le=365, description="look-ahead window"),
    limit: int = Query(default=20, ge=1, le=200, description="max matches"),
    include_venues: bool = Query(
        default=False,
        description="also include upcoming shows at watched venues",
    ),
) -> DigestResponse:
    """Next upcoming watchlist matches, chronological — the read surface a future
    cron/email/push digest consumes. Reuses the ``?watchlist=true`` filter; the
    only new bit is ``watchlist_matches`` per row (which watched name(s) hit).
    With ``include_venues=true``, shows at venues on the venue watchlist are
    merged in (deduped by show id, still chronological) and flagged
    ``watched_venue``."""
    assert user.id is not None
    generated_at = dt.datetime.now(dt.UTC).isoformat()
    conn = db.connect()
    try:
        entries = watchlist_repo.list_all(conn, user.id)
        today = dt.date.today()
        from_date = today.isoformat()
        to_date = (today + dt.timedelta(days=days)).isoformat()
        performer_views: list[ShowView] = []
        if entries:
            performer_views = build_show_views(
                conn,
                venue_slugs=None,
                from_date=from_date,
                to_date=to_date,
                watchlist=True,
                user_id=user.id,
            )
        venue_views: list[ShowView] = []
        if include_venues:
            venue_views = build_show_views(
                conn,
                venue_slugs=None,
                from_date=from_date,
                to_date=to_date,
                venue_watchlist=True,
                user_id=user.id,
            )
    finally:
        conn.close()

    # Merge the two lists, deduped by show id — a show matching both ways keeps
    # its watchlist_matches *and* gains the watched_venue flag. Each source list
    # is start_utc-ordered; re-sort the union on the local instant (single-tz
    # region, so local order == UTC order).
    watched_venue_ids = {view.id for view in venue_views}
    performer_ids = {view.id for view in performer_views}
    views = performer_views + [
        view for view in venue_views if view.id not in performer_ids
    ]
    views.sort(key=lambda view: (view.start_local_date, view.start_local_time, view.id))

    matches: list[DigestMatch] = []
    for view in views[:limit]:
        performer_canonicals = [view.headliner.canonical] + [
            performer.canonical for performer in view.support
        ]
        matched_names = [
            entry.display_name
            for entry in entries
            if any(
                matches_token_bag(entry.canonical_name, canonical)
                for canonical in performer_canonicals
            )
        ]
        matches.append(
            DigestMatch(
                **view.model_dump(),
                watchlist_matches=matched_names,
                watched_venue=view.id in watched_venue_ids,
            )
        )
    return DigestResponse(generated_at=generated_at, matches=matches)
