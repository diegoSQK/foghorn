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
  (`SF` / `East Bay` / `Peninsula` / `South Bay` / `Santa Cruz`), `address`, `tz` (IANA,
  e.g. `America/Los_Angeles`), `website_url`, `calendar_url`.
- **`performers`** — `id`, `display_name` (the venue's verbatim string, never
  overwritten), `canonical_name` (unique; lowercased, accent-stripped,
  punctuation-removed — the search / watchlist match key).
- **`shows`** — `id`, `venue_id` → `venues`, `start_utc` (ISO 8601, normalized
  to `+00:00`), `start_local_date` (`YYYY-MM-DD` in venue tz),
  `start_local_time` (`HH:MM` in venue tz), `doors_local_time` (nullable),
  `headliner_canonical`, `ticket_url`, `price_text`, `source_url`, `scraped_at`,
  `room` (nullable). `room` names the performance space inside a venue that has
  more than one — SFJAZZ's `sfjazz` row covers both Miner Auditorium and the
  Joe Henderson Lab, and 38% of its nights run both, so without it the venue
  reads as double-booking itself. Deliberately **not** part of the natural key:
  one room can't host two bills at one time, so a room correction updates the
  row rather than forking it. `NULL` for the single-room majority.
- **`event_type_overrides`** — manual event-type corrections: `venue_id` →
  `venues`, `headliner_canonical`, `event_type` (`show` / `jam`),
  `created_at`; PK `(venue_id, headliner_canonical)`. Keyed on venue +
  billing (not show id) so a correction survives re-ingest and recurring
  instances of the same billing inherit it. Reads resolve
  `COALESCE(override, shows.event_type)`.
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
[Scheduled jobs](#scheduled-jobs)).

**Auth posture (multi-user, August 2026).** Browse endpoints (`/api/shows`
without personal filters, `/api/venues`, `/api/health/scrape`) are public.
Personal data (both watchlists, the digest, the `?watchlist=` /
`?venue_watchlist=` filters) requires a session and is scoped to the signed-in
user. Global mutations (inbox, manual events, performer origin/genre and
event-type corrections, user management) are admin-only. See
[`/api/auth/*`](#auth-apiauth) below.

### Auth (`/api/auth/*`)

Invite-link-as-credential (no passwords, no email dependency): an admin
creates a user, which mints a token; `/join/<token>` claims the account on
first open and signs back in on later opens. Sessions are opaque tokens
(SHA-256 stored, `sessions` table) in an HttpOnly `foghorn_session` cookie
with rolling ~13-month expiry — active users never expire. Set
`FOGHORN_SECURE_COOKIES=1` wherever HTTPS terminates (the VPS deployment
does); leave it unset for plain-HTTP serving (the Tailscale fleet
deployment).

- `GET /api/auth/invite/{token}` → `{display_name, claimed}` (what the join
  page renders); 404 for unknown/disabled.
- `POST /api/auth/claim` body `{token, display_name?, email?}` → sets the
  session cookie, returns the user. First use stamps `claimed_at`; the
  optional email is only stored to enable magic-link recovery later.
- `GET /api/auth/me` → `{id, display_name, email, is_admin, single_user}`;
  401 anonymous.
- `POST /api/auth/logout` → 204, deletes the session + clears the cookie.
- Admin: `GET/POST /api/auth/users` (list / create-invite),
  `POST /api/auth/users/{id}/regenerate` (new link; old link dies, open
  sessions survive), `PUT /api/auth/users/{id}/disabled` (disable also
  revokes the user's sessions; self-disable is refused).

**Single-user mode (`FOGHORN_SINGLE_USER=1`).** A request with *no* session
cookie resolves as the bootstrap admin (lowest-id `is_admin` user — the same
account the multi-user migration assigned pre-existing watchlist rows to)
instead of anonymous, so the whole personal + admin surface works with no
sign-in at all. A real session cookie always wins, so a signed-in non-admin
still resolves to themselves. With no admin row in the DB the flag degrades to
anonymous rather than creating a user implicitly — run `make auth-bootstrap`.
`/api/auth/me` reports the mode as `single_user: true` (the frontend uses it to
drop the meaningless sign-out control), and the app logs a `WARNING` at startup
naming the resolved admin.

This is **laptop / Tailscale only** — it grants admin to anything that can
reach the port. It exists because the Tailscale fleet deployment can't sign
itself in: foghorn is installed there as an iOS home-screen PWA, which gets its
own storage container (a Safari sign-in doesn't carry), has no address bar to
reach `/join/<token>`, and iOS opens tapped links in Safari rather than the
installed app. **Never set it on a public deployment** — `deploy/`'s compose
pins it to `0` for exactly that reason.

CLI equivalents (run against `FOGHORN_DB_PATH`): `make auth-bootstrap`
(ensure an admin exists, print its login link — the first-run entry point),
`make invite NAME="Ada"`, `make users`.

### `GET /api/shows`

Upcoming shows, ordered by `start_utc`. Query params (all optional):

- `from` — ISO date, inclusive (default: today).
- `to` — ISO date, inclusive (default: today + 30 days).
- `venues` — comma-separated venue slugs (e.g. `bird_and_beckett,keys_jazz_bistro`); omitted = all venues. Unknown slugs simply don't match.
- `venue` — legacy single slug; prefer `venues=`.
- `time_of_day` — `early` (`start_local_time` < 21:00) or `late` (>= 21:00); exact complements, no gap. Anything else ignored.
- `performer_query` — free-text performer name; canonicalized server-side, then **token-bag matched** (Phase 4.1, via `repo/performer_match.py`) against any performer (headliner or support): every query token must be a whole token of the performer's canonical name, so "redman joshua" matches "joshua redman quartet". Empty after canonicalization = no filter.
- `region` — `SF` / `East Bay` / `North Bay` / `Peninsula` / `South Bay` / `Santa Cruz`; matches the venue's `region`. Unknown values ignored (not a 400).
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
  "source_url": "https://birdbeckett.com/events/",
  "room": null
}
```

### `GET/POST/DELETE /api/watchlist`

The signed-in user's watchlist of followed performers (Phase 4.1; per-user
since the multi-user re-key). All three require a session (401 otherwise).
The canonical performer-match utility is `repo/performer_match.py`
(token-bag), shared with `?performer_query=`.

- `GET /api/watchlist` → `[{slug-less entry}]`: `canonical_name`, `display_name`, `added_at`, `notes` (newest first).
- `POST /api/watchlist` body `{"display_name": "Joshua Redman Quartet", "notes": null}` → canonicalizes the name (422 if it canonicalizes to nothing), returns the entry. Re-adding an existing canonical name keeps the original `display_name`/`added_at`.
- `DELETE /api/watchlist/{canonical_name}` → 204, or 404 if not present.

**CORS:** browser calls are same-origin in practice (the Next `/api` rewrite
proxies them), which is also what lets the session cookie ride along without
CORS-with-credentials complexity. The permissive `CORSMiddleware` default
remains for ad-hoc cross-origin dev use; tighten via `FOGHORN_CORS_ORIGINS`.

### `GET /api/watchlist/digest`

Next-N upcoming watchlist matches for a future cron/email/push digest (Phase
4.2). Params: `days` (default 14, look-ahead window) and `limit` (default 20).
Reuses the `?watchlist=true` filter over `[today, today+days]`, ordered by
`start_utc`. Returns `{generated_at, matches}` where each match is a
`/api/shows` row plus `watchlist_matches` — the watched `display_name`(s) that
hit it (a show can match more than one). Empty watchlist → `{generated_at,
matches: []}` (200).

### `PUT` / `DELETE /api/shows/{show_id}/event_type`

Manual event-type correction ("this is a jam session") — foghorn infers
jams from title patterns, which "Standards Hang"-style names defeat, so the
user is the source of truth. `PUT` body `{"event_type": "jam"}` (or
`"show"`); the correction is stored as a **venue+billing override rule**
(see the data model), so it survives the nightly re-ingest and applies to
every instance of a recurring session. `DELETE` removes the rule (the
inferred type applies again). 404 for unknown show ids. Admin-only (like the
performer origin/genre corrections — the override is global data); the
frontend exposes it as the clickable jam badge / faint "jam?" chip on show
rows for admins, a static badge for everyone else.

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
`BackgroundScheduler` (started in the FastAPI lifespan), refreshing the
scrapers due that day and recording a row read by `GET /api/health/scrape`.
The scheduler is suppressed when `FOGHORN_DISABLE_SCHEDULER` is set (pytest
sets it). Run history is kept to the most recent 30 runs. See
`scheduler/runner.py`.

**Cadence.** Everything runs nightly except `scrapers.MONTHLY_SCRAPERS`, which
join the run on the 1st (`scrapers_due`). That's one job with a varying venue
set rather than a second job, because the health endpoint reports the *last
run* — a separate monthly job would leave it showing one venue and the rest
apparently missing. `make scrape` is deliberately cadence-agnostic and
refreshes every registered venue: typing it means "refresh now", and silently
skipping one would be a footgun.

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

**A fourth pattern (see `little_hill_lounge`).** Flyer-image-only venues go
through the **pluggable OCR layer** (`foghorn/ocr/`): engines are callables
`(image_bytes) -> list[OcrLine]` (normalized bottom-left boxes), selected via
`FOGHORN_OCR_ENGINE` — `apple_vision` (macOS default, best quality) or
`rapidocr` (any platform, `pip install .[rapidocr]`; loses inter-word spacing
on some flyer fonts). Scrapers depend only on the `OcrLine` contract and keep
their layout parsers pure/fixture-tested, so hosting off-macOS or adding an
engine never touches a scraper.

**Adding a venue:** implement `scrapers/<slug>.py` with `scrape()`, register it
in `REGISTERED_SCRAPERS`, set the venue's `calendar_url` in the seed, and add a
fixture-driven parser test.

**SFJAZZ note.** SFJAZZ (Phase 2's nominal pilot) sits behind a Cloudflare
managed challenge that 403s simple HTTP clients, so it has no scraper yet — the
Phase 2.1 pilot was re-homed to Bird & Beckett. See `docs/SHIPPED.md`.
