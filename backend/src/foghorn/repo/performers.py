"""Performer persistence primitives.

Get-or-create keyed on ``canonical_name``. Per AGENTS.md → "Conventions", the
``display_name`` (the venue's verbatim string) is never overwritten: if a
performer already exists for a canonical name, the stored display string wins.
The first spelling foghorn sees is the one it keeps.
"""

from __future__ import annotations

import sqlite3

from foghorn.models import Performer


def get_by_canonical(conn: sqlite3.Connection, canonical_name: str) -> Performer | None:
    row = conn.execute(
        "SELECT id, display_name, canonical_name FROM performers WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    if row is None:
        return None
    return Performer(
        id=row["id"],
        display_name=row["display_name"],
        canonical_name=row["canonical_name"],
    )


def upsert(conn: sqlite3.Connection, performer: Performer) -> Performer:
    """Return the existing performer for this canonical name, or create one.
    Does not overwrite an existing ``display_name``."""
    existing = get_by_canonical(conn, performer.canonical_name)
    if existing is not None:
        return existing
    cursor = conn.execute(
        "INSERT INTO performers (display_name, canonical_name) VALUES (?, ?)",
        (performer.display_name, performer.canonical_name),
    )
    conn.commit()
    return Performer(
        id=cursor.lastrowid,
        display_name=performer.display_name,
        canonical_name=performer.canonical_name,
    )
