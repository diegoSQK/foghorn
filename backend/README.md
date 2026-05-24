# foghorn backend

Python 3.11+ backend for foghorn: per-venue scrapers, an ingest pipeline, a
SQLite store, and a FastAPI HTTP surface. This README is the authoritative
reference for the data model, scraper interface, ingest pipeline, and API
surface. Most sections are placeholders filled in over Phase 1.2 / 2.x — see
[`docs/PROJECT_PLAN.md`](../docs/PROJECT_PLAN.md) for sequencing.

## Overview

```
src/foghorn/
  scrapers/   per-venue scrapers → list[ScrapedShow]   (Phase 2.x)
  ingest/     normalize · dedupe · persist pipeline      (Phase 1.2)
  repo/       SQLite persistence layer                   (Phase 1.2)
  api/        FastAPI HTTP surface                        (Phase 2.x)
```

The data lifecycle is **scrape → normalize → persist → serve → render**. See
`AGENTS.md` → "Architecture Debugging Map" for where each kind of show-data
bug originates.

### Local development

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The lint / type / test gate (also runnable from the repo root via
`make backend-gate`):

```bash
ruff check .
mypy src
pytest
```

## Storage

**Decision: stdlib `sqlite3`, not an ORM.** foghorn is single-user and
local-first through Phase 5 (see `AGENTS.md` → "Deferred Workstream"). The
query surface is small and well understood — filtered `SELECT`s over shows,
upsert-on-natural-key for idempotent scraper re-runs — so a hand-written SQL
layer in `repo/` carries less ceremony than SQLAlchemy and keeps the
dependency surface minimal. SQLite files are trivially inspectable with any
`sqlite3` client when debugging show-data issues.

`sqlite3` is in the standard library, so it adds no entry to `pyproject.toml`.
The repo layer wraps it behind typed functions returning Pydantic models, so
callers never touch raw rows or `Any`. If/when hosting forces Postgres (the
deferred unblock condition), the repo layer is the single seam to swap; nothing
above it issues SQL directly.

**Connection handling.** `repo/db.py` exposes `connect(db_path=None)`, which
opens the connection with `Row` access and `PRAGMA foreign_keys = ON`, then
bootstraps the schema. App code calls `connect()` (default path
`<backend>/foghorn.db`, overridable via the `FOGHORN_DB_PATH` env var); tests
pass a tmp path or `":memory:"`. There is **no migrations framework** — the
schema is created idempotently with `CREATE TABLE IF NOT EXISTS` in
`repo/schema.py` on every connect. Additive changes go straight in; if a
non-additive migration ever becomes necessary, add a tool then.

**Repo primitives.** `repo/venues.py` (`get_by_slug`, `list_all`, `upsert`),
`repo/performers.py` (`get_by_canonical`, `upsert` — get-or-create that never
overwrites an existing `display_name`), and `repo/shows.py`
(`upsert(show, bill)`, `get_by_natural_key`, `list(filters)`). The ingest
pipeline (`ingest/pipeline.py`) is the only writer of show data; the repo
layer is otherwise read-mostly and exposes no raw SQL upward.

## Data Model

Four tables (defined in `repo/schema.py`). All datetimes are stored as text;
the Python models live in `foghorn/models.py`.

- **`venues`** — `id`, `slug` (unique), `name`, `neighborhood`, `region`
  (`SF` / `East Bay` / `Peninsula` / `South Bay`), `address`, `tz` (IANA,
  e.g. `America/Los_Angeles`), `website_url`, `calendar_url`.
- **`performers`** — `id`, `display_name` (the venue's verbatim string, never
  overwritten), `canonical_name` (unique; lowercased, accent-stripped,
  punctuation-removed — the search / watchlist match key).
- **`shows`** — `id`, `venue_id` → `venues`, `start_utc` (ISO 8601, normalized
  to `+00:00`), `start_local_date` (`YYYY-MM-DD` in venue tz),
  `start_local_time` (`HH:MM` in venue tz), `doors_local_time` (nullable),
  `headliner_canonical`, `ticket_url`, `price_text`, `source_url`, `scraped_at`.
- **`show_performers`** — join table: `show_id` → `shows`, `performer_id` →
  `performers`, `role` (`headliner` / `support`), `position` (display order on
  the bill; headliner is 0). PK `(show_id, performer_id)`.

**Natural key / dedup.** A show is uniquely identified by
`(venue_id, start_local_date, start_local_time, headliner_canonical)` — this is
AGENTS.md's `(venue_id, local_start_datetime, headliner_canonical)` with the
local datetime split into its already-stored date and time columns, so the
UNIQUE constraint maps directly onto existing columns. Re-running a scraper
upserts on this key: idempotent, no duplicates, mutable fields (`scraped_at`,
`ticket_url`, `price_text`, …) and the bill refresh in place.

**Why store both `start_utc` and `start_local_*`.** `start_utc` gives a single
sortable instant for ordering shows across venues (and future multi-tz
support); the local date/time are what the venue published, what users see, and
what the natural key dedups on — deriving them back from UTC on every read
would be lossy and tz-fragile. See `AGENTS.md` → "Conventions" for the full
rules.

**Ingest.** `ingest/pipeline.py`'s `ingest_scraped_shows(conn, venue, scraped)`
normalizes each `ScrapedShow`'s performer names via `canonicalize()`, applies
the venue tz to the naive local time to compute `start_utc`, upserts performers
and the show, and returns an `IngestResult` (`created` / `updated` / `errors`).
A failure on one show is captured in `errors` without aborting the batch.

**Seed.** `repo/seed_venues.py` upserts the four Phase 2 jazz venues (SFJAZZ,
Keys Jazz Bistro, Bird & Beckett, Mr. Tipple's). Idempotent via upsert-on-slug;
run standalone with `python -m foghorn.repo.seed_venues`. Each `calendar_url` is
a `TBD` placeholder until that venue's Phase 2.x scraper ticket sets the real
one.

## API Surface

*Filled in Phase 2.x.* FastAPI app serving filtered show queries
(`GET /api/shows` with date-range / region / performer-search params), a
scrape-health endpoint (`GET /api/health/scrape`), and the watchlist surface
(Phase 4).

## Scrapers

*Filled in Phase 2.x.* Each venue scraper lives in
`foghorn.scrapers.<venue_slug>` and returns `list[ScrapedShow]` (a frozen
Pydantic model). Scrapers are independently runnable
(`python -m foghorn.scrapers.<venue>`) with no DB write side effects — that's
the ingest pipeline's job. Seed venues: SFJAZZ, Keys Jazz Bistro, Bird &
Beckett, Mr. Tipple's.
