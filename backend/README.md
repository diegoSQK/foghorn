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
run standalone with `python -m foghorn.repo.seed_venues`. Each `calendar_url`
starts as a `TBD` placeholder until that venue's Phase 2.x scraper ticket sets
the real one (Bird & Beckett's is set as of Phase 2.1).

## API Surface

FastAPI app `foghorn.api:app` (run with `make backend-run` →
`uvicorn foghorn.api:app --reload` on `:8000`). On startup it seeds the venues
so a fresh DB serves correctly and starts the nightly scrape scheduler (see
[Scheduled jobs](#scheduled-jobs)). Read-only so far.

### `GET /api/shows`

Upcoming shows, ordered by `start_utc`. Query params (all optional):

- `from` — ISO date, inclusive (default: today).
- `to` — ISO date, inclusive (default: today + 30 days).
- `venues` — comma-separated venue slugs (e.g. `bird_and_beckett,keys_jazz_bistro`); omitted = all venues. Unknown slugs simply don't match.
- `venue` — legacy single slug; prefer `venues=`.
- `time_of_day` — `early` (`start_local_time` < 21:00) or `late` (>= 21:00); exact complements, no gap. Anything else ignored.
- `performer_query` — free-text performer name; canonicalized server-side, then **token-bag matched** (Phase 4.1, via `repo/performer_match.py`) against any performer (headliner or support): every query token must be a whole token of the performer's canonical name, so "redman joshua" matches "joshua redman quartet". Empty after canonicalization = no filter.
- `region` — `SF` / `East Bay` / `Peninsula` / `South Bay`; matches the venue's `region`. Unknown values ignored (not a 400). All current venues are SF.
- `neighborhood` — matches the venue's `neighborhood`, case-insensitive exact (e.g. `North Beach`).
- `watchlist` — `true` filters to shows where any performer token-matches any watchlist entry. Empty watchlist → `[]` (not all shows).

All filters stack as ANDs. Date filters compare against `start_local_date`. Response is a JSON array of:

```json
{
  "venue": {"slug": "bird_and_beckett", "name": "Bird & Beckett Books and Records",
            "neighborhood": "Glen Park", "region": "SF"},
  "start_local_date": "2026-06-05",
  "start_local_time": "19:30",
  "doors_local_time": null,
  "headliner": {"display": "David Parker Sextet", "canonical": "david parker sextet"},
  "support": [{"display": "...", "canonical": "..."}],
  "ticket_url": null,
  "price_text": null,
  "source_url": "https://birdbeckett.com/events/"
}
```

### `GET/POST/DELETE /api/watchlist`

The single-tenant watchlist of followed performers (Phase 4.1). The canonical
performer-match utility is `repo/performer_match.py` (token-bag), shared with
`?performer_query=`.

- `GET /api/watchlist` → `[{slug-less entry}]`: `canonical_name`, `display_name`, `added_at`, `notes` (newest first).
- `POST /api/watchlist` body `{"display_name": "Joshua Redman Quartet", "notes": null}` → canonicalizes the name (422 if it canonicalizes to nothing), returns the entry. Re-adding an existing canonical name keeps the original `display_name`/`added_at`.
- `DELETE /api/watchlist/{canonical_name}` → 204, or 404 if not present.

**CORS:** the frontend's add/remove buttons call these cross-origin, so the app
enables `CORSMiddleware` (permissive by default for local-first use; tighten via
`FOGHORN_CORS_ORIGINS` when deployed).

### `GET /api/watchlist/digest`

Next-N upcoming watchlist matches for a future cron/email/push digest (Phase
4.2). Params: `days` (default 14, look-ahead window) and `limit` (default 20).
Reuses the `?watchlist=true` filter over `[today, today+days]`, ordered by
`start_utc`. Returns `{generated_at, matches}` where each match is a
`/api/shows` row plus `watchlist_matches` — the watched `display_name`(s) that
hit it (a show can match more than one). Empty watchlist → `{generated_at,
matches: []}` (200).

### `GET /api/venues`

The venues foghorn actively scrapes (the venue-filter options) — `slug`, `name`,
`neighborhood`, `region`. Excludes seeded-but-unscraped venues (SFJAZZ), so it's
filtered by `REGISTERED_SCRAPERS`, not a raw `venues` table dump.

```json
[{"slug": "bird_and_beckett", "name": "Bird & Beckett Books and Records",
  "neighborhood": "Glen Park", "region": "SF"}]
```

### `GET /api/health/scrape`

The most recent scrape run (scheduled or `make scrape`) with its per-venue
breakdown — so "did last night's refresh run, and did anything break?" is one
request away:

```json
{
  "last_run_at": "2026-05-24T04:00:01+00:00",
  "last_run_finished_at": "2026-05-24T04:01:43+00:00",
  "venues": [
    {"slug": "bird_and_beckett", "started_at": "...", "finished_at": "...",
     "created": 0, "updated": 12, "errors": []},
    {"slug": "keys_jazz_bistro", "started_at": "...", "finished_at": "...",
     "created": 0, "updated": 0, "errors": ["timeout fetching calendar (httpx.ReadTimeout)"]}
  ]
}
```

Returns **503** `{"error": "no_scrape_runs_yet"}` until the first run is
recorded — distinct from "ran but a venue failed" (200 with that venue's
`errors` populated).

## Scheduled jobs

A nightly scrape runs at **04:00 America/Los_Angeles** via APScheduler's
`BackgroundScheduler` (started in the FastAPI lifespan), refreshing every
registered scraper and recording a row read by `GET /api/health/scrape`.
`make scrape` runs the same unit of work on demand. The scheduler is suppressed
when `FOGHORN_DISABLE_SCHEDULER` is set (pytest sets it). Run history is kept to
the most recent 30 runs. See `scheduler/runner.py`.

## Scrapers

Each venue scraper lives in `foghorn.scrapers.<venue_slug>` and exposes a
zero-argument `scrape() -> list[ScrapedShow]` (the frozen scraper contract).
Scrapers have no DB side effects — that's the ingest pipeline's job — and are
independently runnable: `python -m foghorn.scrapers.<venue>` prints the scraped
shows as JSON.

`REGISTERED_SCRAPERS` (`scrapers/__init__.py`) maps venue slug → scrape
callable. `make scrape` (`foghorn.cli.scrape`) seeds venues, then runs each
registered scraper through `ingest_scraped_shows`, printing per-venue
`created / updated / errors` (exit code = total failures, for cron/CI).

**Pattern (see `bird_and_beckett`).** Split `fetch_*()` (network) from a pure
`parse_*(text, today, ...)` so the parser is deterministic and fixture-testable
without the network. Bird & Beckett reads the venue's public Google Calendar
`.ics` (a cleaner, more stable source than its WordPress event posts) and uses
`icalendar` + `recurring-ical-events` to expand the next ~90 days — including
recurring residencies — mapping each timed musical event to a `ScrapedShow`,
skipping all-day entries, and applying a conservative non-music exclusion
heuristic (errs toward inclusion). Datetimes are normalized to naive venue-local
time; ingest re-applies the tz.

**A second pattern (see `mr_tipples`).** When a venue's site runs a known events
platform, target its API over its HTML. Mr. Tipple's is WordPress + The Events
Calendar (Tribe), so the scraper pages its JSON REST API
(`/wp-json/tribe/events/v1/events`), which yields `ticket_url` (the OpenTable
reservation link) and `price_text` (`cost`) on top of the basics. Same
fetch/parse split; the `httpx.Client` is injectable so pagination is
mock-transport-testable.

**A third pattern (see `wyldflowr_arts`).** When a venue's calendar is an
embedded third-party widget, the widget's own JS names the API to target.
Wyldflowr Arts ticket through Viewcy and embed it as a `viewcyembed.com`
iframe; reading the embed's bundle gave up
`www.viewcy.com/api/o/<org>/courses` — public JSON, no auth. Two things
generalize. First, **the calendar is invisible to a plain fetch** of the venue's
own page, because it renders client-side; render the page in a browser when a
site looks maintained but its calendar looks stale. Second, **a venue's
legacy endpoint may still answer 200** — `wyldflowrarts.com/events?format=json`
serves an abandoned Squarespace collection that stops in Aug 2025, which reads
convincingly as a dormant venue. Verify a source is *current* before believing
what it implies. Viewcy nests dated `events` under a `course`, so one course
flattens to N shows.

**Adding a venue:** implement `scrapers/<slug>.py` with `scrape()`, register it
in `REGISTERED_SCRAPERS`, set the venue's `calendar_url` in the seed, and add a
fixture-driven parser test.

**SFJAZZ note.** SFJAZZ (Phase 2's nominal pilot) sits behind a Cloudflare
managed challenge that 403s simple HTTP clients, so it has no scraper yet — the
Phase 2.1 pilot was re-homed to Bird & Beckett. See `docs/SHIPPED.md`.
