"""Persistence for scrape-run history (``scrape_runs`` + ``scrape_run_venues``).

A run is recorded by both the nightly scheduler and manual ``make scrape``, so
the scrape-health endpoint reflects either. The tables are trimmed to the most
recent ``DEFAULT_KEEP`` runs on each insert to stay bounded.
"""

from __future__ import annotations

import json
import sqlite3

from foghorn.models import ScrapeRun, ScrapeRunVenue

DEFAULT_KEEP = 30


def record_run(
    conn: sqlite3.Connection, run: ScrapeRun, *, keep: int = DEFAULT_KEEP
) -> ScrapeRun:
    """Insert a run and its per-venue rows, trim old runs, return the stored
    run (with ``id`` populated)."""
    cursor = conn.execute(
        "INSERT INTO scrape_runs (started_at, finished_at) VALUES (?, ?)",
        (run.started_at, run.finished_at),
    )
    run_id = cursor.lastrowid
    assert run_id is not None
    for venue in run.venues:
        conn.execute(
            """
            INSERT INTO scrape_run_venues
                (scrape_run_id, venue_slug, started_at, finished_at,
                 created, updated, errors_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                venue.venue_slug,
                venue.started_at,
                venue.finished_at,
                venue.created,
                venue.updated,
                json.dumps(venue.errors),
            ),
        )
    conn.commit()
    trim(conn, keep=keep)
    stored = run.model_copy(update={"id": run_id})
    return stored


def trim(conn: sqlite3.Connection, *, keep: int = DEFAULT_KEEP) -> None:
    """Delete all but the most recent ``keep`` runs (and their venue rows)."""
    stale = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM scrape_runs ORDER BY id DESC LIMIT -1 OFFSET ?",
            (keep,),
        ).fetchall()
    ]
    if not stale:
        return
    placeholders = ", ".join("?" for _ in stale)
    conn.execute(
        f"DELETE FROM scrape_run_venues WHERE scrape_run_id IN ({placeholders})",
        stale,
    )
    conn.execute(
        f"DELETE FROM scrape_runs WHERE id IN ({placeholders})", stale
    )
    conn.commit()


def latest(conn: sqlite3.Connection) -> ScrapeRun | None:
    """The most recent run with its per-venue breakdown, or ``None`` if none."""
    row = conn.execute(
        "SELECT id, started_at, finished_at FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    venue_rows = conn.execute(
        """
        SELECT venue_slug, started_at, finished_at, created, updated, errors_json
        FROM scrape_run_venues WHERE scrape_run_id = ?
        ORDER BY venue_slug
        """,
        (row["id"],),
    ).fetchall()
    venues = [
        ScrapeRunVenue(
            venue_slug=v["venue_slug"],
            started_at=v["started_at"],
            finished_at=v["finished_at"],
            created=v["created"],
            updated=v["updated"],
            errors=json.loads(v["errors_json"]),
        )
        for v in venue_rows
    ]
    return ScrapeRun(
        id=row["id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        venues=venues,
    )


def count(conn: sqlite3.Connection) -> int:
    """Number of stored runs (for tests / trim assertions)."""
    return int(conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0])
