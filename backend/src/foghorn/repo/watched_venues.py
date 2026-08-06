"""Venue-watchlist persistence (Phase 9; per-user since August 2026). Keyed on
``(user_id, venue_slug)``; mirrors the performer watchlist's contract (re-add
updates notes only)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from foghorn.models import WatchedVenue


def _row_to_entry(row: sqlite3.Row) -> WatchedVenue:
    return WatchedVenue(
        venue_slug=row["venue_slug"], added_at=row["added_at"], notes=row["notes"]
    )


def get(conn: sqlite3.Connection, user_id: int, venue_slug: str) -> WatchedVenue | None:
    row = conn.execute(
        "SELECT venue_slug, added_at, notes FROM watched_venues "
        "WHERE user_id = ? AND venue_slug = ?",
        (user_id, venue_slug),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def list_all(conn: sqlite3.Connection, user_id: int) -> list[WatchedVenue]:
    rows = conn.execute(
        "SELECT venue_slug, added_at, notes FROM watched_venues "
        "WHERE user_id = ? ORDER BY added_at DESC",
        (user_id,),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def add(
    conn: sqlite3.Connection,
    user_id: int,
    venue_slug: str,
    notes: str | None = None,
) -> WatchedVenue:
    existing = get(conn, user_id, venue_slug)
    if existing is not None:
        if notes is not None:
            conn.execute(
                "UPDATE watched_venues SET notes = ? WHERE user_id = ? AND venue_slug = ?",
                (notes, user_id, venue_slug),
            )
            conn.commit()
            refreshed = get(conn, user_id, venue_slug)
            assert refreshed is not None
            return refreshed
        return existing
    added_at = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO watched_venues (user_id, venue_slug, added_at, notes) "
        "VALUES (?, ?, ?, ?)",
        (user_id, venue_slug, added_at, notes),
    )
    conn.commit()
    return WatchedVenue(venue_slug=venue_slug, added_at=added_at, notes=notes)


def remove(conn: sqlite3.Connection, user_id: int, venue_slug: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM watched_venues WHERE user_id = ? AND venue_slug = ?",
        (user_id, venue_slug),
    )
    conn.commit()
    return cursor.rowcount > 0
