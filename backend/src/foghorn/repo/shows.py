"""Show persistence primitives: natural-key upsert and filtered listing.

The public ``list`` deliberately shadows the builtin to read naturally at the
call site (``shows.list(conn, filters)``); annotations use ``builtins.list`` to
sidestep the shadow.
"""

from __future__ import annotations

import builtins
import sqlite3

from foghorn.models import Show, ShowFilters, ShowPerformer

_SHOW_COLUMNS = (
    "id, venue_id, start_utc, start_local_date, start_local_time, "
    "doors_local_time, headliner_canonical, ticket_url, price_text, "
    "source_url, scraped_at"
)


def _row_to_show(row: sqlite3.Row) -> Show:
    return Show(
        id=row["id"],
        venue_id=row["venue_id"],
        start_utc=row["start_utc"],
        start_local_date=row["start_local_date"],
        start_local_time=row["start_local_time"],
        doors_local_time=row["doors_local_time"],
        headliner_canonical=row["headliner_canonical"],
        ticket_url=row["ticket_url"],
        price_text=row["price_text"],
        source_url=row["source_url"],
        scraped_at=row["scraped_at"],
    )


def _load_performers(
    conn: sqlite3.Connection, show_id: int
) -> builtins.list[ShowPerformer]:
    rows = conn.execute(
        """
        SELECT sp.performer_id, p.display_name, p.canonical_name, sp.role, sp.position
        FROM show_performers sp
        JOIN performers p ON p.id = sp.performer_id
        WHERE sp.show_id = ?
        ORDER BY sp.position
        """,
        (show_id,),
    ).fetchall()
    return [
        ShowPerformer(
            performer_id=row["performer_id"],
            display_name=row["display_name"],
            canonical_name=row["canonical_name"],
            role=row["role"],
            position=row["position"],
        )
        for row in rows
    ]


def get_by_natural_key(
    conn: sqlite3.Connection,
    venue_id: int,
    start_local_date: str,
    start_local_time: str,
    headliner_canonical: str,
) -> Show | None:
    """Look up a show by its natural key. Used by ingest to distinguish a
    create from an update before upserting."""
    row = conn.execute(
        f"""
        SELECT {_SHOW_COLUMNS} FROM shows
        WHERE venue_id = ? AND start_local_date = ? AND start_local_time = ?
              AND headliner_canonical = ?
        """,
        (venue_id, start_local_date, start_local_time, headliner_canonical),
    ).fetchone()
    if row is None:
        return None
    show = _row_to_show(row)
    assert show.id is not None
    show.performers = _load_performers(conn, show.id)
    return show


def upsert(
    conn: sqlite3.Connection, show: Show, performers: builtins.list[ShowPerformer]
) -> Show:
    """Insert or update a show on its natural key, then replace its bill.

    Idempotent: re-upserting the same natural key refreshes the mutable
    columns (``scraped_at``, ``ticket_url``, ``price_text``, ``start_utc``,
    ``doors_local_time``, ``source_url``) and rewrites the performer rows
    rather than creating duplicates. Performers must already be persisted
    (carry a ``performer_id``) — the ingest pipeline upserts them first.
    """
    conn.execute(
        """
        INSERT INTO shows (venue_id, start_utc, start_local_date, start_local_time,
                           doors_local_time, headliner_canonical, ticket_url,
                           price_text, source_url, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venue_id, start_local_date, start_local_time, headliner_canonical)
        DO UPDATE SET
            start_utc        = excluded.start_utc,
            doors_local_time = excluded.doors_local_time,
            ticket_url       = excluded.ticket_url,
            price_text       = excluded.price_text,
            source_url       = excluded.source_url,
            scraped_at       = excluded.scraped_at
        """,
        (
            show.venue_id,
            show.start_utc,
            show.start_local_date,
            show.start_local_time,
            show.doors_local_time,
            show.headliner_canonical,
            show.ticket_url,
            show.price_text,
            show.source_url,
            show.scraped_at,
        ),
    )
    stored = get_by_natural_key(
        conn,
        show.venue_id,
        show.start_local_date,
        show.start_local_time,
        show.headliner_canonical,
    )
    assert stored is not None  # just inserted/updated
    assert stored.id is not None
    # Replace the bill wholesale so a re-scrape that drops or reorders support
    # acts converges rather than accumulating stale links.
    conn.execute("DELETE FROM show_performers WHERE show_id = ?", (stored.id,))
    for sp in performers:
        conn.execute(
            "INSERT INTO show_performers (show_id, performer_id, role, position) "
            "VALUES (?, ?, ?, ?)",
            (stored.id, sp.performer_id, sp.role, sp.position),
        )
    conn.commit()
    stored.performers = _load_performers(conn, stored.id)
    return stored


def list(conn: sqlite3.Connection, filters: ShowFilters) -> builtins.list[Show]:
    """Return shows matching ``filters``, ordered by ``start_utc``, each with
    its bill attached. Date filters are inclusive and compare against
    ``start_local_date``."""
    clauses: builtins.list[str] = []
    params: builtins.list[object] = []

    if filters.venue_slugs:
        placeholders = ", ".join("?" for _ in filters.venue_slugs)
        clauses.append(f"v.slug IN ({placeholders})")
        params.extend(filters.venue_slugs)
    if filters.region:
        clauses.append("v.region = ?")
        params.append(filters.region)
    if filters.from_date:
        clauses.append("s.start_local_date >= ?")
        params.append(filters.from_date)
    if filters.to_date:
        clauses.append("s.start_local_date <= ?")
        params.append(filters.to_date)
    if filters.performer_canonical_substring:
        clauses.append(
            "EXISTS (SELECT 1 FROM show_performers sp "
            "JOIN performers p ON p.id = sp.performer_id "
            "WHERE sp.show_id = s.id AND p.canonical_name LIKE ?)"
        )
        params.append(f"%{filters.performer_canonical_substring}%")

    sql = (
        f"SELECT {', '.join('s.' + c.strip() for c in _SHOW_COLUMNS.split(','))} "
        "FROM shows s JOIN venues v ON v.id = s.venue_id"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY s.start_utc"

    rows = conn.execute(sql, params).fetchall()
    shows = [_row_to_show(row) for row in rows]
    for show in shows:
        assert show.id is not None
        show.performers = _load_performers(conn, show.id)
    return shows
