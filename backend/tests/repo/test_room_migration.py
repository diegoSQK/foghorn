"""The ``shows.room`` column must land on an already-populated database.

``CREATE TABLE IF NOT EXISTS`` skips existing tables, so a column added after a
DB was first created only arrives via the additive ALTER in ``init_schema``.
The live deployment has ~1,000 shows predating this column, so the migration
has to add it without disturbing them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from foghorn.repo import schema

# The shows table as it stood immediately before `room`. Written out rather
# than derived from SCHEMA_SQL: this is a *historical* shape, so it is frozen by
# definition, and deriving it would also trip over `_table_ddl` truncating at
# the first ";" — which the shows DDL has inside a column comment.
_LEGACY_SHOWS_DDL = """
CREATE TABLE IF NOT EXISTS shows (
    id                   INTEGER PRIMARY KEY,
    venue_id             INTEGER NOT NULL REFERENCES venues(id),
    start_utc            TEXT NOT NULL,
    start_local_date     TEXT NOT NULL,
    start_local_time     TEXT NOT NULL,
    end_local_time       TEXT,
    doors_local_time     TEXT,
    headliner_canonical  TEXT NOT NULL,
    ticket_url           TEXT,
    price_text           TEXT,
    source_url           TEXT NOT NULL,
    scraped_at           TEXT NOT NULL,
    source               TEXT NOT NULL DEFAULT 'scrape',
    event_type           TEXT NOT NULL DEFAULT 'show',
    genre_override       TEXT,
    UNIQUE (venue_id, start_local_date, start_local_time, headliner_canonical)
);
"""

_LEGACY_VENUES_DDL = """
CREATE TABLE IF NOT EXISTS venues (
    id            INTEGER PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    neighborhood  TEXT,
    region        TEXT,
    address       TEXT,
    tz            TEXT NOT NULL,
    website_url   TEXT,
    calendar_url  TEXT NOT NULL
);
"""


def _legacy_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_LEGACY_VENUES_DDL)
    conn.executescript(_LEGACY_SHOWS_DDL)
    conn.execute(
        "INSERT INTO venues (slug, name, tz, calendar_url) VALUES (?, ?, ?, ?)",
        ("old_venue", "Old Venue", "America/Los_Angeles", "https://example.test/c"),
    )
    conn.execute(
        """INSERT INTO shows (venue_id, start_utc, start_local_date, start_local_time,
                              headliner_canonical, source_url, scraped_at)
           VALUES (1, '2026-09-10T02:00:00+00:00', '2026-09-09', '19:00',
                   'old act', 'https://example.test/s', '2026-09-01T00:00:00+00:00')"""
    )
    conn.commit()
    return conn


def test_room_column_is_added_to_an_existing_db(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    conn = _legacy_db(path)
    assert "room" not in {r[1] for r in conn.execute("PRAGMA table_info(shows)")}

    schema.init_schema(conn)

    assert "room" in {r[1] for r in conn.execute("PRAGMA table_info(shows)")}
    conn.close()


def test_existing_rows_survive_with_a_null_room(tmp_path: Path) -> None:
    conn = _legacy_db(tmp_path / "legacy.db")
    schema.init_schema(conn)

    rows = list(conn.execute("SELECT headliner_canonical, room FROM shows"))
    assert len(rows) == 1
    assert rows[0]["headliner_canonical"] == "old act"
    assert rows[0]["room"] is None
    conn.close()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    conn = _legacy_db(tmp_path / "legacy.db")
    schema.init_schema(conn)
    schema.init_schema(conn)  # a second boot must not error or duplicate
    columns = [r[1] for r in conn.execute("PRAGMA table_info(shows)")]
    assert columns.count("room") == 1
    assert len(list(conn.execute("SELECT 1 FROM shows"))) == 1
    conn.close()
