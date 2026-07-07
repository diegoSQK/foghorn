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
    calendar_url  TEXT NOT NULL,
    genre         TEXT,
    source        TEXT NOT NULL DEFAULT 'seed'  -- 'seed' | 'manual'
);

CREATE TABLE IF NOT EXISTS performers (
    id              INTEGER PRIMARY KEY,
    display_name    TEXT NOT NULL,
    canonical_name  TEXT NOT NULL UNIQUE,
    origin          TEXT,  -- 'local' | 'touring' | NULL (unknown)
    origin_source   TEXT,  -- 'heuristic' | 'manual' | NULL
    genre           TEXT,  -- performer-level genre | NULL (unknown)
    genre_source    TEXT   -- 'heuristic' | 'manual' | NULL
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
    source               TEXT NOT NULL DEFAULT 'scrape',  -- 'scrape' | 'manual'
    event_type           TEXT NOT NULL DEFAULT 'show',    -- 'show' | 'jam'
    genre_override       TEXT,  -- per-show genre; NULL = venue default applies
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

-- One row per scrape run (scheduled nightly or manual `make scrape`), with a
-- per-venue breakdown child table. Trimmed to the most recent N runs on insert
-- (Phase 2.3). The scrape-health endpoint reads the latest run.
CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL
);

-- Single-tenant watchlist of followed performers (Phase 4.1). canonical_name
-- (canonicalized display_name) is the match key; no user_id (single-tenant).
CREATE TABLE IF NOT EXISTS watchlist (
    canonical_name  TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    added_at        TEXT NOT NULL,
    notes           TEXT
);

-- Single-tenant venue watchlist (Phase 9): "never miss what this room
-- books". Mirrors the performer watchlist's shape.
CREATE TABLE IF NOT EXISTS watched_venues (
    venue_slug  TEXT PRIMARY KEY,
    added_at    TEXT NOT NULL,
    notes       TEXT
);

-- Mailing-list ingest (Phase 8 stage 1). mail_senders maps a newsletter's
-- From: address to the artist it announces (artist ≈ headliner); the parser
-- prefills drafts from it.
CREATE TABLE IF NOT EXISTS mail_senders (
    email           TEXT PRIMARY KEY,
    artist_display  TEXT NOT NULL
);

-- The review queue: one row per ingested email. Draft fields (artist / venue /
-- date / time) are parser guesses and stay NULL when the rules fumble — the
-- raw text is always kept so a human can fill the gaps at approve time.
-- Nothing enters `shows` unapproved. message_id (RFC 5322) makes IMAP polling
-- idempotent; NULL for hand-pasted emails.
CREATE TABLE IF NOT EXISTS pending_events (
    id                INTEGER PRIMARY KEY,
    received_at       TEXT NOT NULL,
    from_addr         TEXT NOT NULL,
    subject           TEXT NOT NULL,
    message_id        TEXT UNIQUE,
    raw_text          TEXT NOT NULL,
    artist_display    TEXT,
    venue_slug        TEXT,
    venue_name_guess  TEXT,
    date_guess        TEXT,  -- YYYY-MM-DD
    time_guess        TEXT,  -- HH:MM (24h)
    status            TEXT NOT NULL DEFAULT 'pending'  -- 'pending' | 'approved' | 'rejected'
);

CREATE TABLE IF NOT EXISTS scrape_run_venues (
    scrape_run_id  INTEGER NOT NULL REFERENCES scrape_runs(id),
    venue_slug     TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT NOT NULL,
    created        INTEGER NOT NULL,
    updated        INTEGER NOT NULL,
    errors_json    TEXT NOT NULL,
    PRIMARY KEY (scrape_run_id, venue_slug)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they don't already exist, then apply
    additive column migrations (CREATE TABLE IF NOT EXISTS skips existing
    tables, so columns added after a DB was first created need an explicit
    ALTER)."""
    conn.executescript(SCHEMA_SQL)
    _add_column_if_missing(conn, "venues", "genre", "TEXT")
    _add_column_if_missing(conn, "performers", "origin", "TEXT")
    _add_column_if_missing(conn, "performers", "origin_source", "TEXT")
    _add_column_if_missing(conn, "venues", "source", "TEXT NOT NULL DEFAULT 'seed'")
    _add_column_if_missing(conn, "shows", "source", "TEXT NOT NULL DEFAULT 'scrape'")
    _add_column_if_missing(conn, "shows", "event_type", "TEXT NOT NULL DEFAULT 'show'")
    _add_column_if_missing(conn, "shows", "genre_override", "TEXT")
    _add_column_if_missing(conn, "performers", "genre", "TEXT")
    _add_column_if_missing(conn, "performers", "genre_source", "TEXT")
    conn.commit()


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
