"""Performer persistence primitives.

Get-or-create keyed on ``canonical_name``. Per AGENTS.md → "Conventions", the
``display_name`` (the venue's verbatim string) is never overwritten: if a
performer already exists for a canonical name, the stored display string wins.
The first spelling foghorn sees is the one it keeps.

The ``origin`` tag (local/touring, Phase 7 tagging) rides on the performer
row. ``set_origin`` records who set it via ``origin_source``; the heuristic
bootstrap (``foghorn.tagging.origin``) refuses to overwrite ``manual`` rows.
"""

from __future__ import annotations

import sqlite3

from foghorn.models import Origin, OriginSource, Performer

_COLUMNS = "id, display_name, canonical_name, origin, origin_source, genre, genre_source"


def _row_to_performer(row: sqlite3.Row) -> Performer:
    return Performer(
        id=row["id"],
        display_name=row["display_name"],
        canonical_name=row["canonical_name"],
        origin=row["origin"],
        origin_source=row["origin_source"],
        genre=row["genre"],
        genre_source=row["genre_source"],
    )


def get_by_canonical(conn: sqlite3.Connection, canonical_name: str) -> Performer | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM performers WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    return _row_to_performer(row) if row is not None else None


def upsert(conn: sqlite3.Connection, performer: Performer) -> Performer:
    """Return the existing performer for this canonical name, or create one.
    Does not overwrite an existing ``display_name`` (or origin tags)."""
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


def set_origin(
    conn: sqlite3.Connection,
    canonical_name: str,
    origin: Origin | None,
    source: OriginSource,
) -> Performer | None:
    """Set (or clear) a performer's origin tag, recording who set it. A manual
    clear keeps ``origin_source='manual'`` so the heuristic won't re-tag a
    performer the user deliberately marked unknown. Returns the updated
    performer, or None if no such canonical name exists."""
    cursor = conn.execute(
        "UPDATE performers SET origin = ?, origin_source = ? WHERE canonical_name = ?",
        (origin, source, canonical_name),
    )
    conn.commit()
    if cursor.rowcount == 0:
        return None
    return get_by_canonical(conn, canonical_name)


def set_genre(
    conn: sqlite3.Connection,
    canonical_name: str,
    genre: str | None,
    source: OriginSource,
) -> Performer | None:
    """Set (or clear) a performer's genre tag, recording who set it — same
    contract as ``set_origin``: a manual clear stays manual so the heuristic
    won't re-tag. Returns the updated performer, or None if no such
    canonical name exists."""
    cursor = conn.execute(
        "UPDATE performers SET genre = ?, genre_source = ? WHERE canonical_name = ?",
        (genre, source, canonical_name),
    )
    conn.commit()
    if cursor.rowcount == 0:
        return None
    return get_by_canonical(conn, canonical_name)
