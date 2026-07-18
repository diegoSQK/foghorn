"""Show persistence primitives: natural-key upsert and filtered listing.

The public ``list`` deliberately shadows the builtin to read naturally at the
call site (``shows.list(conn, filters)``); annotations use ``builtins.list`` to
sidestep the shadow.
"""

from __future__ import annotations

import builtins
import sqlite3

from foghorn.models import Show, ShowFilters, ShowPerformer
from foghorn.repo.performer_match import token_match_sql

# ``event_type`` resolves through the manual-override rules at read time
# (see ``event_type_overrides`` in the schema): the stored column is what
# ingest inferred; a matching venue+billing rule wins. Aliased back to
# ``event_type`` so row mapping stays uniform.
_EVENT_TYPE_RESOLVED = (
    "COALESCE((SELECT o.event_type FROM event_type_overrides o "
    "WHERE o.venue_id = {alias}.venue_id "
    "AND o.headliner_canonical = {alias}.headliner_canonical), "
    "{alias}.event_type)"
)

_SHOW_COLUMNS = (
    "id, venue_id, start_utc, start_local_date, start_local_time, "
    "end_local_time, doors_local_time, headliner_canonical, ticket_url, price_text, "
    "source_url, scraped_at, source, "
    + _EVENT_TYPE_RESOLVED.format(alias="shows")
    + " AS event_type, genre_override"
)


def _row_to_show(row: sqlite3.Row) -> Show:
    return Show(
        id=row["id"],
        venue_id=row["venue_id"],
        start_utc=row["start_utc"],
        start_local_date=row["start_local_date"],
        start_local_time=row["start_local_time"],
        end_local_time=row["end_local_time"],
        doors_local_time=row["doors_local_time"],
        headliner_canonical=row["headliner_canonical"],
        ticket_url=row["ticket_url"],
        price_text=row["price_text"],
        source_url=row["source_url"],
        scraped_at=row["scraped_at"],
        source=row["source"],
        event_type=row["event_type"],
        genre_override=row["genre_override"],
    )


def _load_performers(
    conn: sqlite3.Connection, show_id: int
) -> builtins.list[ShowPerformer]:
    rows = conn.execute(
        """
        SELECT sp.performer_id, p.display_name, p.canonical_name, p.origin,
               p.genre, sp.role, sp.position
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
            origin=row["origin"],
            genre=row["genre"],
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
                           end_local_time, doors_local_time, headliner_canonical,
                           ticket_url, price_text, source_url, scraped_at, source,
                           event_type, genre_override)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venue_id, start_local_date, start_local_time, headliner_canonical)
        DO UPDATE SET
            start_utc        = excluded.start_utc,
            end_local_time   = excluded.end_local_time,
            doors_local_time = excluded.doors_local_time,
            ticket_url       = excluded.ticket_url,
            price_text       = excluded.price_text,
            source_url       = excluded.source_url,
            scraped_at       = excluded.scraped_at,
            source           = excluded.source,
            event_type       = excluded.event_type,
            genre_override   = excluded.genre_override
        """,
        (
            show.venue_id,
            show.start_utc,
            show.start_local_date,
            show.start_local_time,
            show.end_local_time,
            show.doors_local_time,
            show.headliner_canonical,
            show.ticket_url,
            show.price_text,
            show.source_url,
            show.scraped_at,
            show.source,
            show.event_type,
            show.genre_override,
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


def _performer_match_clause(
    token_bags: builtins.list[builtins.list[str]],
    prefix: bool = False,
) -> tuple[str, builtins.list[str]]:
    """An EXISTS-over-the-bill clause: true when any performer on the show
    token-matches any of ``token_bags``. Returns ``("", [])`` when there's
    nothing to match."""
    predicate, params = token_match_sql("p.canonical_name", token_bags, prefix=prefix)
    if not predicate:
        return "", []
    clause = (
        "EXISTS (SELECT 1 FROM show_performers sp "
        "JOIN performers p ON p.id = sp.performer_id "
        f"WHERE sp.show_id = s.id AND {predicate})"
    )
    return clause, params


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
    # Aggregator quarantine (decided July 2026: quarantine-with-flag,
    # watchlist bypass). Shows at aggregator-created venues are hidden unless:
    # the long-tail toggle is on; the venue is pinned (watched_venues) — a pin
    # promotes it into the main UI; the venue was explicitly selected; or the
    # performer-watchlist filter is active (the watchlist always sees through
    # the quarantine, so a followed artist's gig at an untracked space
    # surfaces regardless).
    if (
        not filters.include_long_tail
        and filters.watchlist_token_bags is None
    ):
        exemptions = [
            "v.slug IN (SELECT venue_slug FROM watched_venues)",
        ]
        quarantine_params: builtins.list[object] = []
        if filters.venue_slugs:
            placeholders = ", ".join("?" for _ in filters.venue_slugs)
            exemptions.append(f"v.slug IN ({placeholders})")
            quarantine_params.extend(filters.venue_slugs)
        clauses.append(
            "(v.source != 'aggregator' OR " + " OR ".join(exemptions) + ")"
        )
        params.extend(quarantine_params)
    if filters.region:
        clauses.append("v.region = ?")
        params.append(filters.region)
    if filters.neighborhood:
        # Neighborhoods are short distinct strings; case-insensitive exact match.
        clauses.append("v.neighborhood = ? COLLATE NOCASE")
        params.append(filters.neighborhood)
    if filters.genre:
        # Layered genre resolution: per-show override > the headliner's
        # performer-level genre (Phase 7.4) > the venue's default lean.
        clauses.append(
            "COALESCE(s.genre_override, "
            "(SELECT pg.genre FROM show_performers spg "
            " JOIN performers pg ON pg.id = spg.performer_id "
            " WHERE spg.show_id = s.id AND spg.role = 'headliner' LIMIT 1), "
            "v.genre) = ? COLLATE NOCASE"
        )
        params.append(filters.genre)
    if filters.origin:
        # Any-performer semantics, like the watchlist: a touring headliner
        # with a local opener matches origin=local (the opener is the reason
        # a support-local user would go).
        clauses.append(
            "EXISTS (SELECT 1 FROM show_performers spo "
            "JOIN performers po ON po.id = spo.performer_id "
            "WHERE spo.show_id = s.id AND po.origin = ?)"
        )
        params.append(filters.origin)
    if filters.watched_venue_slugs is not None:
        if filters.watched_venue_slugs:
            ph = ", ".join("?" for _ in filters.watched_venue_slugs)
            clauses.append(f"v.slug IN ({ph})")
            params.extend(filters.watched_venue_slugs)
        else:
            clauses.append("1 = 0")  # empty venue watchlist -> no matches
    if filters.event_type:
        # Filter on the RESOLVED type so manual corrections move shows
        # between the Shows/Jam facets.
        clauses.append(_EVENT_TYPE_RESOLVED.format(alias="s") + " = ?")
        params.append(filters.event_type)
    if filters.from_date:
        clauses.append("s.start_local_date >= ?")
        params.append(filters.from_date)
    if filters.to_date:
        clauses.append("s.start_local_date <= ?")
        params.append(filters.to_date)
    # Performer match (token-bag, Phase 4.1): a show matches if any of its
    # performers' canonical names whole-token-matches the query / any watchlist
    # bag. Both go through the same EXISTS-over-the-bill helper.
    if filters.performer_query_canonical:
        # Search-as-you-type: each query token matches as a token *prefix*
        # ("mezz" finds "mezzacappa"). The watchlist clause below stays
        # whole-token for precision.
        clause, clause_params = _performer_match_clause(
            [filters.performer_query_canonical.split()], prefix=True
        )
        if clause:
            clauses.append(clause)
            params.extend(clause_params)
    if filters.watchlist_token_bags is not None:
        clause, clause_params = _performer_match_clause(filters.watchlist_token_bags)
        if clause:
            clauses.append(clause)
            params.extend(clause_params)
        else:
            clauses.append("1 = 0")  # watchlist requested but empty -> no matches
    # HH:MM is zero-padded 24h, so lexical comparison is chronological.
    # Early (< 21:00) and Late (>= 21:00) are exact complements — no gap.
    if filters.time_of_day == "early":
        clauses.append("s.start_local_time < ?")
        params.append("21:00")
    elif filters.time_of_day == "late":
        clauses.append("s.start_local_time >= ?")
        params.append("21:00")

    resolved = _EVENT_TYPE_RESOLVED.format(alias="s")
    sql = (
        "SELECT s.id, s.venue_id, s.start_utc, s.start_local_date, "
        "s.start_local_time, s.end_local_time, s.doors_local_time, "
        "s.headliner_canonical, "
        "s.ticket_url, s.price_text, s.source_url, s.scraped_at, s.source, "
        f"{resolved} AS event_type, s.genre_override "
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


def get_by_id(conn: sqlite3.Connection, show_id: int) -> Show | None:
    row = conn.execute(
        f"SELECT {_SHOW_COLUMNS} FROM shows WHERE id = ?", (show_id,)
    ).fetchone()
    if row is None:
        return None
    show = _row_to_show(row)
    assert show.id is not None
    show.performers = _load_performers(conn, show.id)
    return show


def delete_manual(conn: sqlite3.Connection, show_id: int) -> bool:
    """Delete a manually-entered show (and its bill rows). Refuses scraped
    rows — a scraper would just recreate them on the next run, so deleting
    them through the API would silently un-stick. Returns True if deleted."""
    row = conn.execute("SELECT source FROM shows WHERE id = ?", (show_id,)).fetchone()
    if row is None or row["source"] != "manual":
        return False
    conn.execute("DELETE FROM show_performers WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM shows WHERE id = ?", (show_id,))
    conn.commit()
    return True


def set_event_type_override(
    conn: sqlite3.Connection,
    venue_id: int,
    headliner_canonical: str,
    event_type: str,
) -> None:
    """Record a manual event-type correction for this venue + billing. The
    rule survives re-ingest (it lives off the show row) and applies to every
    show with the same billing at the venue — past, present, and future
    instances of a recurring session."""
    conn.execute(
        """
        INSERT INTO event_type_overrides (venue_id, headliner_canonical,
                                          event_type, created_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(venue_id, headliner_canonical)
        DO UPDATE SET event_type = excluded.event_type
        """,
        (venue_id, headliner_canonical, event_type),
    )
    conn.commit()


def clear_event_type_override(
    conn: sqlite3.Connection, venue_id: int, headliner_canonical: str
) -> bool:
    """Remove a manual correction; the ingest-inferred type applies again.
    Returns whether a rule existed."""
    cursor = conn.execute(
        "DELETE FROM event_type_overrides "
        "WHERE venue_id = ? AND headliner_canonical = ?",
        (venue_id, headliner_canonical),
    )
    conn.commit()
    return cursor.rowcount > 0
