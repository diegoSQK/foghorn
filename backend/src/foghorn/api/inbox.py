"""The mailing-list review queue HTTP surface (Phase 8 stage 1).

- ``GET /api/inbox`` — pending drafts, each with ``possible_duplicates``:
  existing shows at the guessed venue+date whose headliner token-matches the
  artist. Email-approved gigs and later venue-scraped ones won't collapse on
  the natural key when billing strings differ ("Dillon Vado" vs "Dillon Vado
  Trio"), so the warning is how the reviewer avoids double entry.
- ``POST /api/inbox/ingest`` — paste an email (from/subject/text) straight
  into the queue; the same seam the tests drive, usable without IMAP.
- ``POST /api/inbox/{id}/approve`` — overrides merged over the draft, then
  the event is created through the exact ``POST /api/events`` internals
  (``source='manual'``); the row is stamped approved.
- ``POST /api/inbox/{id}/reject`` — stamped rejected; the raw text is kept.
- ``GET/POST/DELETE /api/inbox/senders`` — the sender→artist map.

Single-tenant, no auth — same posture as the watchlist.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from foghorn.api.events import ManualEvent, ManualEventView, NewVenue, create_manual_event
from foghorn.ingest.pipeline import canonicalize
from foghorn.mailingest.parser import parse_email
from foghorn.models import EventType, PendingEvent, ShowFilters
from foghorn.repo import db
from foghorn.repo import mail_senders as mail_senders_repo
from foghorn.repo import pending_events as pending_events_repo
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.performer_match import matches_token_bag

router = APIRouter()


class DuplicateView(BaseModel):
    """An existing show the draft probably duplicates."""

    show_id: int
    headliner: str
    venue_slug: str
    start_local_date: str
    start_local_time: str
    source: str  # 'scrape' | 'manual'


class PendingEventView(BaseModel):
    id: int
    received_at: str
    from_addr: str
    subject: str
    raw_text: str
    artist_display: str | None
    venue_slug: str | None
    venue_name_guess: str | None
    date_guess: str | None
    time_guess: str | None
    status: str
    possible_duplicates: list[DuplicateView]


def _possible_duplicates(
    conn: sqlite3.Connection, row: PendingEvent
) -> list[DuplicateView]:
    """Shows already booked at the guessed venue+date whose headliner
    token-matches the artist (either direction — "Dillon Vado" flags a
    scraped "Dillon Vado Trio" and vice versa). Needs all three guesses;
    a draft missing any can't be checked and warns nothing."""
    if not (row.artist_display and row.venue_slug and row.date_guess):
        return []
    artist_canonical = canonicalize(row.artist_display)
    if not artist_canonical:
        return []
    day_shows = shows_repo.list(
        conn,
        ShowFilters(
            venue_slugs=[row.venue_slug],
            from_date=row.date_guess,
            to_date=row.date_guess,
        ),
    )
    duplicates: list[DuplicateView] = []
    for show in day_shows:
        if not (
            matches_token_bag(artist_canonical, show.headliner_canonical)
            or matches_token_bag(show.headliner_canonical, artist_canonical)
        ):
            continue
        headliner = next(
            (p.display_name for p in show.performers if p.role == "headliner"),
            show.headliner_canonical,
        )
        assert show.id is not None
        duplicates.append(
            DuplicateView(
                show_id=show.id,
                headliner=headliner,
                venue_slug=row.venue_slug,
                start_local_date=show.start_local_date,
                start_local_time=show.start_local_time,
                source=show.source,
            )
        )
    return duplicates


def _to_view(conn: sqlite3.Connection, row: PendingEvent) -> PendingEventView:
    assert row.id is not None
    return PendingEventView(
        id=row.id,
        received_at=row.received_at,
        from_addr=row.from_addr,
        subject=row.subject,
        raw_text=row.raw_text,
        artist_display=row.artist_display,
        venue_slug=row.venue_slug,
        venue_name_guess=row.venue_name_guess,
        date_guess=row.date_guess,
        time_guess=row.time_guess,
        status=row.status,
        possible_duplicates=_possible_duplicates(conn, row),
    )


@router.get("/api/inbox", response_model=list[PendingEventView])
def list_inbox() -> list[PendingEventView]:
    conn = db.connect()
    try:
        return [
            _to_view(conn, row)
            for row in pending_events_repo.list_by_status(conn, "pending")
        ]
    finally:
        conn.close()


class IngestEmail(BaseModel):
    """A hand-pasted email. Only the body is required — without a From: the
    draft simply has no artist guess."""

    from_addr: str = ""
    subject: str = ""
    text: str = Field(min_length=1)


@router.post("/api/inbox/ingest", response_model=PendingEventView, status_code=201)
def ingest_email(body: IngestEmail) -> PendingEventView:
    conn = db.connect()
    try:
        draft = parse_email(
            body.from_addr,
            body.subject,
            body.text,
            venues=venues_repo.list_all(conn),
            senders={
                s.email: s.artist_display for s in mail_senders_repo.list_all(conn)
            },
            today=dt.date.today(),
        )
        row = pending_events_repo.add(
            conn,
            PendingEvent(
                received_at=dt.datetime.now(dt.UTC).isoformat(),
                from_addr=body.from_addr,
                subject=body.subject,
                message_id=None,  # pasted, not polled — no IMAP dedup key
                raw_text=body.text,
                **draft.model_dump(),
            ),
        )
        return _to_view(conn, row)
    finally:
        conn.close()


class ApproveBody(BaseModel):
    """Reviewer overrides, merged over the draft guesses. Venue accepts a
    known slug or a new venue (same shape as ``POST /api/events``); fields
    left null fall back to the draft."""

    venue_slug: str | None = None
    venue: NewVenue | None = None
    headliner: str | None = None
    support: list[str] = Field(default_factory=list)
    date: dt.date | None = None
    time: dt.time | None = None
    doors_time: dt.time | None = None
    event_type: EventType = "show"
    genre: str | None = None
    ticket_url: str | None = None
    price_text: str | None = None
    source_url: str | None = None


def _fallback_source_url(row: PendingEvent) -> str:
    """Provenance when the reviewer has no better link: point at the email
    itself (its Message-ID, or the queue row for pasted emails)."""
    if row.message_id:
        return f"manual://email/{row.message_id.strip('<>')}"
    return f"manual://email/pending-{row.id}"


@router.post(
    "/api/inbox/{pending_id}/approve", response_model=ManualEventView, status_code=201
)
def approve_pending(pending_id: int, body: ApproveBody) -> ManualEventView:
    conn = db.connect()
    try:
        row = pending_events_repo.get_by_id(conn, pending_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no such pending event")
        if row.status != "pending":
            raise HTTPException(status_code=409, detail=f"already {row.status}")

        headliner = (body.headliner or row.artist_display or "").strip()
        venue_slug = body.venue_slug if body.venue is None else None
        if venue_slug is None and body.venue is None:
            venue_slug = row.venue_slug
        date = body.date or (
            dt.date.fromisoformat(row.date_guess) if row.date_guess else None
        )
        time = body.time or (
            dt.time.fromisoformat(row.time_guess) if row.time_guess else None
        )
        missing = [
            name
            for name, value in (
                ("headliner", headliner),
                ("venue", venue_slug or body.venue),
                ("date", date),
                ("time", time),
            )
            if not value
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"still missing: {', '.join(missing)} — edit the draft "
                "before approving",
            )
        assert date is not None and time is not None  # narrowed by `missing`

        view = create_manual_event(
            conn,
            ManualEvent(
                venue_slug=venue_slug,
                venue=body.venue,
                headliner=headliner,
                support=body.support,
                date=date,
                time=time,
                doors_time=body.doors_time,
                ticket_url=body.ticket_url,
                price_text=body.price_text,
                event_type=body.event_type,
                genre=body.genre,
                source_url=body.source_url or _fallback_source_url(row),
            ),
        )
        # Persist what actually shipped, so the approved row is a record of
        # the reviewer's final call rather than the parser's first guess.
        pending_events_repo.update_draft(
            conn,
            pending_id,
            {
                "artist_display": headliner,
                "venue_slug": view.venue_slug,
                "date_guess": view.start_local_date,
                "time_guess": view.start_local_time,
            },
        )
        pending_events_repo.set_status(conn, pending_id, "approved")
        return view
    finally:
        conn.close()


@router.post("/api/inbox/{pending_id}/reject", status_code=204)
def reject_pending(pending_id: int) -> Response:
    conn = db.connect()
    try:
        row = pending_events_repo.get_by_id(conn, pending_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no such pending event")
        pending_events_repo.set_status(conn, pending_id, "rejected")
    finally:
        conn.close()
    return Response(status_code=204)


class MailSenderView(BaseModel):
    email: str
    artist_display: str


class MailSenderCreate(BaseModel):
    email: str = Field(min_length=3, pattern=r".+@.+")
    artist_display: str = Field(min_length=1)


@router.get("/api/inbox/senders", response_model=list[MailSenderView])
def list_senders() -> list[MailSenderView]:
    conn = db.connect()
    try:
        return [
            MailSenderView(email=s.email, artist_display=s.artist_display)
            for s in mail_senders_repo.list_all(conn)
        ]
    finally:
        conn.close()


@router.post("/api/inbox/senders", response_model=MailSenderView, status_code=201)
def add_sender(body: MailSenderCreate) -> MailSenderView:
    if not body.artist_display.strip():
        raise HTTPException(status_code=422, detail="artist_display must not be blank")
    conn = db.connect()
    try:
        stored = mail_senders_repo.upsert(conn, body.email, body.artist_display.strip())
    finally:
        conn.close()
    return MailSenderView(email=stored.email, artist_display=stored.artist_display)


@router.delete("/api/inbox/senders/{email}", status_code=204)
def delete_sender(email: str) -> Response:
    conn = db.connect()
    try:
        removed = mail_senders_repo.remove(conn, email)
    finally:
        conn.close()
    if not removed:
        raise HTTPException(status_code=404, detail="no such sender")
    return Response(status_code=204)
