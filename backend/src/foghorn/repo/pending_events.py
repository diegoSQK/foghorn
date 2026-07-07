"""Pending-event (review queue) persistence — Phase 8 stage 1.

One row per ingested mailing-list email. ``add`` is idempotent on
``message_id`` (the IMAP poller re-seeing a message is a no-op); rows move
``pending`` → ``approved`` / ``rejected`` via ``set_status`` and are never
deleted — a rejected row with its raw text is the record that a human looked.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from foghorn.models import PendingEvent, PendingStatus

_COLUMNS = (
    "id, received_at, from_addr, subject, message_id, raw_text, artist_display, "
    "venue_slug, venue_name_guess, date_guess, time_guess, status"
)

# The reviewer-editable draft columns `update_draft` may touch. Everything
# else (provenance: received_at, from_addr, subject, message_id, raw_text)
# is immutable once ingested.
_DRAFT_COLUMNS = frozenset(
    {"artist_display", "venue_slug", "venue_name_guess", "date_guess", "time_guess"}
)


def _row_to_event(row: sqlite3.Row) -> PendingEvent:
    return PendingEvent(
        id=row["id"],
        received_at=row["received_at"],
        from_addr=row["from_addr"],
        subject=row["subject"],
        message_id=row["message_id"],
        raw_text=row["raw_text"],
        artist_display=row["artist_display"],
        venue_slug=row["venue_slug"],
        venue_name_guess=row["venue_name_guess"],
        date_guess=row["date_guess"],
        time_guess=row["time_guess"],
        status=row["status"],
    )


def get_by_id(conn: sqlite3.Connection, pending_id: int) -> PendingEvent | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM pending_events WHERE id = ?", (pending_id,)
    ).fetchone()
    return _row_to_event(row) if row is not None else None


def get_by_message_id(conn: sqlite3.Connection, message_id: str) -> PendingEvent | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM pending_events WHERE message_id = ?", (message_id,)
    ).fetchone()
    return _row_to_event(row) if row is not None else None


def list_by_status(
    conn: sqlite3.Connection, status: PendingStatus = "pending"
) -> list[PendingEvent]:
    """Rows in ``status``, newest received first (the review queue reads top
    of the pile)."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM pending_events WHERE status = ? "
        "ORDER BY received_at DESC, id DESC",
        (status,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def add(conn: sqlite3.Connection, event: PendingEvent) -> PendingEvent:
    """Insert a pending row. Idempotent on ``message_id``: re-adding a message
    the queue already has returns the existing row untouched (whatever its
    status — an approved/rejected email must not reappear)."""
    if event.message_id is not None:
        existing = get_by_message_id(conn, event.message_id)
        if existing is not None:
            return existing
    cursor = conn.execute(
        """
        INSERT INTO pending_events (received_at, from_addr, subject, message_id,
                                    raw_text, artist_display, venue_slug,
                                    venue_name_guess, date_guess, time_guess, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.received_at,
            event.from_addr,
            event.subject,
            event.message_id,
            event.raw_text,
            event.artist_display,
            event.venue_slug,
            event.venue_name_guess,
            event.date_guess,
            event.time_guess,
            event.status,
        ),
    )
    conn.commit()
    stored = get_by_id(conn, int(cursor.lastrowid or 0))
    assert stored is not None  # just inserted
    return stored


def update_draft(
    conn: sqlite3.Connection, pending_id: int, fields: Mapping[str, str | None]
) -> PendingEvent | None:
    """Overwrite draft guess columns (approve persists the reviewer's final
    values here before creating the event, so the row records what shipped).
    Unknown/immutable column names raise; returns None for an unknown id."""
    unknown = set(fields) - _DRAFT_COLUMNS
    if unknown:
        raise ValueError(f"not draft columns: {sorted(unknown)}")
    if fields:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = conn.execute(
            f"UPDATE pending_events SET {assignments} WHERE id = ?",
            (*fields.values(), pending_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None
    return get_by_id(conn, pending_id)


def set_status(
    conn: sqlite3.Connection, pending_id: int, status: PendingStatus
) -> bool:
    """Move a row through the review lifecycle; True if a row was updated."""
    cursor = conn.execute(
        "UPDATE pending_events SET status = ? WHERE id = ?", (status, pending_id)
    )
    conn.commit()
    return cursor.rowcount > 0
