"""SQLite schema definition and bootstrap.

The schema is created idempotently with ``CREATE TABLE IF NOT EXISTS`` at
connection time (see ``db.connect``). There is no migrations framework yet —
the schema is small and pre-feature, so additive evolution via this script is
enough. If schema *changes* (not just additions) become painful, add a
migrations tool then (deferred per the Phase 1.2 ticket).
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime

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
    end_local_time       TEXT,  -- stated end 'HH:MM'; < start = past midnight
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
-- Manual event-type corrections (July 2026): "this billing at this venue
-- is a jam (or a show)". Keyed on venue + billing rather than show id so a
-- correction survives re-ingest AND applies to future instances of
-- recurring events (sessions/hangs recur under the same billing string).
-- Reads resolve COALESCE(override, shows.event_type).
CREATE TABLE IF NOT EXISTS event_type_overrides (
    venue_id             INTEGER NOT NULL REFERENCES venues(id),
    headliner_canonical  TEXT NOT NULL,
    event_type           TEXT NOT NULL,  -- 'show' | 'jam'
    created_at           TEXT NOT NULL,
    PRIMARY KEY (venue_id, headliner_canonical)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL
);

-- Accounts (multi-user, August 2026). A row is created at invite time; the
-- invite token doubles as the durable login credential ("invite link = the
-- account key"), so claimed_at only records first use. Regenerating the token
-- invalidates old links but not open sessions.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    display_name  TEXT NOT NULL,
    email         TEXT,              -- optional; enables future magic-link recovery
    invite_token  TEXT NOT NULL UNIQUE,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    claimed_at    TEXT               -- NULL until the invite link is first opened
);

-- Browser sessions. Only a SHA-256 hash of the opaque cookie token is stored,
-- so a leaked DB never yields usable sessions. Rolling expiry: reads bump
-- last_seen_at/expires_at (throttled — see repo/sessions.py).
CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Per-user watchlist of followed performers (Phase 4.1; re-keyed by user_id
-- August 2026). canonical_name (canonicalized display_name) is the match key.
CREATE TABLE IF NOT EXISTS watchlist (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    canonical_name  TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    added_at        TEXT NOT NULL,
    notes           TEXT,
    PRIMARY KEY (user_id, canonical_name)
);

-- Per-user venue watchlist (Phase 9; re-keyed by user_id August 2026):
-- "never miss what this room books". Mirrors the performer watchlist's shape.
CREATE TABLE IF NOT EXISTS watched_venues (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    venue_slug  TEXT NOT NULL,
    added_at    TEXT NOT NULL,
    notes       TEXT,
    PRIMARY KEY (user_id, venue_slug)
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
    _migrate_watchlists_to_multiuser(conn)
    _add_column_if_missing(conn, "venues", "genre", "TEXT")
    _add_column_if_missing(conn, "performers", "origin", "TEXT")
    _add_column_if_missing(conn, "performers", "origin_source", "TEXT")
    _add_column_if_missing(conn, "venues", "source", "TEXT NOT NULL DEFAULT 'seed'")
    _add_column_if_missing(conn, "shows", "source", "TEXT NOT NULL DEFAULT 'scrape'")
    _add_column_if_missing(conn, "shows", "event_type", "TEXT NOT NULL DEFAULT 'show'")
    _add_column_if_missing(conn, "shows", "end_local_time", "TEXT")
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


# The multi-user re-key (August 2026) changes these tables' PRIMARY KEY, which
# SQLite can't ALTER in place — pre-existing single-tenant tables are rebuilt
# row-preservingly. The new-shape DDL is re-derived from SCHEMA_SQL so the
# rebuilt table can never drift from the canonical definition.
_REKEYED_TABLES = {
    "watchlist": "SELECT ?, canonical_name, display_name, added_at, notes FROM ",
    "watched_venues": "SELECT ?, venue_slug, added_at, notes FROM ",
}


def _table_ddl(table: str) -> str:
    """Extract one CREATE TABLE statement from SCHEMA_SQL."""
    marker = f"CREATE TABLE IF NOT EXISTS {table} ("
    start = SCHEMA_SQL.index(marker)
    end = SCHEMA_SQL.index(";", start)
    return SCHEMA_SQL[start : end + 1]


def _migrate_watchlists_to_multiuser(conn: sqlite3.Connection) -> None:
    """Rebuild single-tenant watchlist / watched_venues tables (no user_id
    column) into the per-user shape, assigning existing rows to the first
    admin user — created here as the bootstrap admin if none exists yet.
    ``python -m foghorn.cli.auth bootstrap`` prints that admin's login link."""
    for table, select_sql in _REKEYED_TABLES.items():
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "user_id" in columns:
            continue
        has_rows = conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None
        owner_id = _ensure_bootstrap_admin(conn) if has_rows else 0
        conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
        conn.execute(_table_ddl(table))
        conn.execute(
            f"INSERT INTO {table} {select_sql}{table}_legacy",  # noqa: S608
            (owner_id,),
        )
        conn.execute(f"DROP TABLE {table}_legacy")


def _ensure_bootstrap_admin(conn: sqlite3.Connection) -> int:
    """Return the first admin user's id, creating one (already claimed, with a
    fresh invite token) when no admin exists — the owner for rows that predate
    multi-user."""
    row = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if row is not None:
        return int(row[0])
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        "INSERT INTO users (display_name, invite_token, is_admin, created_at, claimed_at) "
        "VALUES (?, ?, 1, ?, ?)",
        ("Admin", secrets.token_urlsafe(24), now, now),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid
