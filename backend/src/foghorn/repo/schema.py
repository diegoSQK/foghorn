"""SQLite schema definition and bootstrap.

The schema is created idempotently with ``CREATE TABLE IF NOT EXISTS`` at
connection time (see ``db.connect``). There is no migrations framework yet —
the schema is small and pre-feature, so additive evolution via this script is
enough. If schema *changes* (not just additions) become painful, add a
migrations tool then (deferred per the Phase 1.2 ticket).
"""

from __future__ import annotations

import sqlite3

# Natural key for a show: (venue_id, start_local_date, start_local_time,
# headliner_canonical). The UNIQUE constraint enforces idempotent scraper
# re-runs — see AGENTS.md → "Conventions" → "Show identity".
SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS performers (
    id              INTEGER PRIMARY KEY,
    display_name    TEXT NOT NULL,
    canonical_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS shows (
    id                   INTEGER PRIMARY KEY,
    venue_id             INTEGER NOT NULL REFERENCES venues(id),
    start_utc            TEXT NOT NULL,
    start_local_date     TEXT NOT NULL,
    start_local_time     TEXT NOT NULL,
    doors_local_time     TEXT,
    headliner_canonical  TEXT NOT NULL,
    ticket_url           TEXT,
    price_text           TEXT,
    source_url           TEXT NOT NULL,
    scraped_at           TEXT NOT NULL,
    UNIQUE (venue_id, start_local_date, start_local_time, headliner_canonical)
);

CREATE TABLE IF NOT EXISTS show_performers (
    show_id       INTEGER NOT NULL REFERENCES shows(id),
    performer_id  INTEGER NOT NULL REFERENCES performers(id),
    role          TEXT NOT NULL,
    position      INTEGER NOT NULL,
    PRIMARY KEY (show_id, performer_id)
);

-- Supports ORDER BY start_utc and date-window filters on the hot read path.
CREATE INDEX IF NOT EXISTS idx_shows_start_utc ON shows(start_utc);
CREATE INDEX IF NOT EXISTS idx_shows_local_date ON shows(start_local_date);
CREATE INDEX IF NOT EXISTS idx_show_performers_performer ON show_performers(performer_id);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they don't already exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
