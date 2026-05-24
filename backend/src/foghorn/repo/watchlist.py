"""Watchlist persistence (Phase 4.1).

Single-tenant. ``canonical_name`` (the canonicalized ``display_name``) is the
primary key + match key; the verbatim ``display_name`` is kept for the UI and
never overwritten on re-add.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from foghorn.ingest.pipeline import canonicalize
from foghorn.models import Watchlist


def _row_to_entry(row: sqlite3.Row) -> Watchlist:
    return Watchlist(
        canonical_name=row["canonical_name"],
        display_name=row["display_name"],
        added_at=row["added_at"],
        notes=row["notes"],
    )


def get(conn: sqlite3.Connection, canonical_name: str) -> Watchlist | None:
    row = conn.execute(
        "SELECT canonical_name, display_name, added_at, notes FROM watchlist "
        "WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def list_all(conn: sqlite3.Connection) -> list[Watchlist]:
    rows = conn.execute(
        "SELECT canonical_name, display_name, added_at, notes FROM watchlist "
        "ORDER BY added_at DESC"
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def add(
    conn: sqlite3.Connection, display_name: str, notes: str | None = None
) -> Watchlist:
    """Add a performer (keyed on canonicalized name). Re-adding an existing
    canonical name updates ``notes`` (when given) but never the original
    ``display_name`` / ``added_at``."""
    canonical = canonicalize(display_name)
    existing = get(conn, canonical)
    if existing is not None:
        if notes is not None:
            conn.execute(
                "UPDATE watchlist SET notes = ? WHERE canonical_name = ?",
                (notes, canonical),
            )
            conn.commit()
            refreshed = get(conn, canonical)
            assert refreshed is not None
            return refreshed
        return existing
    added_at = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO watchlist (canonical_name, display_name, added_at, notes) "
        "VALUES (?, ?, ?, ?)",
        (canonical, display_name, added_at, notes),
    )
    conn.commit()
    return Watchlist(
        canonical_name=canonical,
        display_name=display_name,
        added_at=added_at,
        notes=notes,
    )


def remove(conn: sqlite3.Connection, canonical_name: str) -> bool:
    """Delete an entry; return True if a row was removed."""
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE canonical_name = ?", (canonical_name,)
    )
    conn.commit()
    return cursor.rowcount > 0
