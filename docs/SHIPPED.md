# foghorn Shipped Work

Chronological record of completed work — what landed, when, and why. Each entry preserves the narrative context that informed the design so it stays available as scar tissue when scoping new work.

`PROJECT_PLAN.md` is the active doc: what's in flight, queued, and deferred. When a new phase/feature ships, its spec moves here and the active doc collapses to a one-line status with a link into this file. Read this file on demand when you need detail on past work; the active doc is the daily read.

Ordering: newest at top. When adding a new entry, insert it at the top of the file. Older entries preserve their original recording order — when reorganizing, prefer "insert at top of recent block" over "deeply reorder existing history."

---

## Phase 2.1 end-to-end pilot via Bird and Beckett (May 2026)

The first venue end-to-end: scrape → ingest → `GET /api/shows` → a rendered
frontend list. Closes #6 (Bird & Beckett scraper, 2.2b). Also lands the Phase
2.1 infrastructure — scraper registry, `make scrape`, the API endpoint, the
frontend page, and the run targets — that the remaining 2.2 siblings build on.

**Re-pilot: SFJAZZ → Bird & Beckett.** #4 picked SFJAZZ as the pilot for being
"largest / most-structured / lowest scraper risk." Dogfooding falsified that:
SFJAZZ sits behind a **Cloudflare managed challenge** that 403s every simple
HTTP client (the polite `foghorn-scraper` UA and a browser UA alike), and the
robots.txt sitemap host 404s. Bypassing Cloudflare is explicitly out of scope,
and a headless browser often doesn't beat a managed challenge anyway. Of the
four jazz venues, Bird & Beckett was the cleanest reachable source, so #4 was
**dropped** and the pilot re-homed here. SFJAZZ can return later as a fresh
ticket if we take on a browser/alternative-source approach. *Lesson for the
remaining venues: probe reachability before assuming a site is scrapable.*

**Data source: a public Google Calendar `.ics`.** Bird & Beckett is WordPress
with no events plugin or custom post type — its event "posts" carry the date in
free-text titles (fragile). But its `/events` page embeds a public Google
Calendar, whose `.ics` export (`.../ical/<id>/public/basic.ics`) is a clean,
current, structured feed (3600+ historical VEVENTs; ~100 upcoming). The scraper
reads that. `venues.calendar_url` for Bird & Beckett points at the human
`/events` page (also the per-show `source_url`); the `.ics` URL is a constant in
the scraper module.

**Parsing (`scrapers/bird_and_beckett.py`).** `fetch_ics()` (httpx, polite UA,
follow redirects) is split from a pure `parse_ics(ics_text, today, window_days)`
so the parser is deterministic and fixture-testable without network. Parsing
uses `icalendar` + `recurring-ical-events`: `recurring_ical_events.of(cal)
.between(today, today+90d)` expands recurring series (the venue runs ~14 active
monthly residencies — Vince Lateano, Scott Foster, etc.) into concrete dated
instances, handling `RECURRENCE-ID` overrides and `EXDATE`. Each timed event
becomes a `ScrapedShow` (SUMMARY → headliner; no support/ticket/price/doors —
the calendar doesn't carry them, and B&B takes phone reservations). All-day
(`VALUE=DATE`) entries are skipped. Expanded instances come back tz-aware (PT or
UTC); we convert to the venue tz and drop tzinfo to get naive local time, which
ingest re-applies the tz to. A **conservative non-music heuristic** drops events
whose title carries strong literary signals (poetry/reading/lecture/…); it errs
toward inclusion per the ticket, so some literary events still leak (e.g. a
small-press release) — refining it is future work.

**Registry + CLI.** `REGISTERED_SCRAPERS` (`scrapers/__init__.py`) maps slug →
`scrape`. `foghorn.cli.scrape` (`make scrape`) seeds venues, runs each scraper
through `ingest_scraped_shows`, prints per-venue `created/updated/errors`, and
exits non-zero on any failure.

**API (`api/shows.py`, `api/__init__.py`).** `GET /api/shows?venue=&from=&to=`
(defaults today..+30d, inclusive on `start_local_date`), ordered by `start_utc`.
Response rows carry venue (slug/name/neighborhood/region), local date/time,
doors, headliner + support as `{display, canonical}`, ticket_url, price_text,
source_url — see `backend/README.md` § API Surface for the shape (the reference
for future scraper authors). The app (`foghorn.api:app`) seeds venues in its
lifespan. Endpoint is sync and opens a SQLite connection per request (cheap, and
keeps each request single-threaded so the default `check_same_thread` guard
holds).

**Frontend (`frontend/app/page.tsx`).** Server component fetching `/api/shows`
(`cache: "no-store"`) from `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`), rendering shows grouped by local date with friendly
date/time formatting and a ticket link when present. Renders a clear "Backend
not reachable — `make backend-run`" panel when the fetch fails. Intentionally
bare; Phase 3 dresses it up.

**Deps + config.** Added `uvicorn[standard]==0.47.0` (the run target),
`icalendar==7.1.2`, `recurring-ical-events==3.8.2` to `backend/pyproject.toml`,
plus a mypy `ignore_missing_imports` override for `recurring_ical_events` (no
`py.typed`; icalendar/httpx/bs4 ship types). `db.connect()` now reads
`FOGHORN_DB_PATH` at call time (was import time) so tests/ops can repoint the DB
after import. Makefile gained `scrape`, `backend-run`, `frontend-run`.

Tests (49 total green under mypy `strict`): `scrapers/test_bird_and_beckett.py`
drives `parse_ics` against a curated fixture (`fixtures/bird_and_beckett_sample
.ics`) with a pinned `today` — covering TZID vs UTC times, non-music exclusion,
all-day skip, weekly-recurrence expansion, accents, and windowing.
`test_ingest_e2e_bird_and_beckett.py` runs the fixture through ingest (counts,
tz→UTC round-trip, display-name preservation, idempotent re-ingest).
`api/test_shows_endpoint.py` points the app at a tmp DB via `FOGHORN_DB_PATH`
and drives `GET /api/shows` with `TestClient` (ordering, shape, filters).
Verified live too: `make scrape` ingested 59 shows, and a real
`uvicorn`+`next start` run rendered them grouped by date in the SSR'd HTML.

**Gotchas.** (1) UTC-stored events near midnight render a day earlier in local
time (e.g. a show at 03:00Z shows as the prior evening PT) — correct, just
worth knowing. (2) No `ticket_url`/`price` from this calendar (phone
reservations). (3) The non-music heuristic is imperfect by design.

**Bookkeeping.** Closes #6; #4 (SFJAZZ) was dropped (closed) with the Cloudflare
rationale. The 2.2 siblings #5 (Keys) and #7 (Mr. Tipple's) remain — their
tickets say "depends on #4," now moot: the registry/ingest/API/frontend infra
they need ships here. A PM-thread pass should re-point those references and
reconcile the "Next.js 15" doc mentions (create-next-app installed Next 16).

## Data model and ingest scaffolding (Phase 1.2, May 2026)

The data-model spine every Phase 2.x scraper plugs into: the SQLite schema, the
typed repository layer, the ingest pipeline, and the four-venue seed. No
scraping yet — that's Phase 2. Closes #3.

**Schema** (`repo/schema.py`, bootstrapped via `CREATE TABLE IF NOT EXISTS` on
every `db.connect()`). Four tables: `venues`, `performers`, `shows`,
`show_performers` (the headliner+support join, with `role` and `position`).
No migrations framework — the schema is pre-feature and additive-only for now;
AGENTS.md's "add migrations when evolution gets painful" still holds.

**Natural key, split across two columns.** AGENTS.md specifies the show natural
key as `(venue_id, local_start_datetime, headliner_canonical)`. The schema
stores the local datetime as two columns it already needs for display and
filtering — `start_local_date` (`YYYY-MM-DD`) and `start_local_time` (`HH:MM`)
— so the UNIQUE constraint is `(venue_id, start_local_date, start_local_time,
headliner_canonical)`. Same identity, no redundant combined column. `shows.upsert`
keys on this: re-running a scraper refreshes `scraped_at`/`ticket_url`/`price_text`
(plus `start_utc`/`doors`/`source_url`) and rewrites the bill, never duplicating.
The bill is replaced wholesale (DELETE + re-INSERT of `show_performers`) so a
re-scrape that drops or reorders support acts converges instead of accumulating
stale links.

**Why both `start_utc` and `start_local_*` are stored.** `start_utc` (always
normalized to `+00:00`) is the single sortable instant for `ORDER BY` across
venues and any future multi-tz world; the local date/time are what the venue
published and what the natural key dedups on. Deriving one from the other on
every read would be lossy and tz-fragile, so both are persisted. The ingest
pipeline applies the venue's IANA tz (via stdlib `zoneinfo`) to the scraper's
*naive* local datetime to compute `start_utc` — e.g. 8pm `America/Los_Angeles`
on 2026-06-01 → `2026-06-02T03:00:00+00:00` (PDT, UTC-7).

**Canonicalization** (`ingest.pipeline.canonicalize`). NFKD-decompose, drop
combining marks (`é`→`e`), lowercase, replace every non-alphanumeric char with a
space, collapse whitespace. Punctuation becomes a *separator*, not deleted, so
`"Earth, Wind & Fire"` → `"earth wind fire"` (not `"earthwind fire"`). Uses
`str.isalnum()` so it's unicode-aware rather than ASCII-only. Performers are
stored with both `display_name` (verbatim, never overwritten on conflict) and
`canonical_name` (unique) per the AGENTS.md display-vs-search split; the
watchlist (Phase 4) and free-text search (Phase 3.3) match on canonical.

**Repo layer is conn-injected, returns Pydantic.** Every repo function takes a
`sqlite3.Connection` as its first arg (no global/singleton connection), which
makes tests trivial (a per-test tmp-file DB fixture in `conftest.py`) and keeps
the Postgres-swap seam clean. `repo/db.py` centralizes connection setup
(`Row` factory, `PRAGMA foreign_keys = ON`, schema bootstrap) and the default
DB path (`FOGHORN_DB_PATH` env override). `shows.list` shadows the builtin to
read as `shows.list(conn, filters)`; annotations use `builtins.list` to dodge
the shadow.

**Models** (`foghorn/models.py`). All cross-layer shapes live in one module so
repo/ingest/scrapers/api agree without importing each other: `Venue`,
`Performer`, `ShowPerformer`, `Show`, `ScrapedShow` (frozen — the scraper
contract), `ShowFilters`, `IngestResult`. `Region`/`Role` are `Literal`s so
seeds and ingest are validated at construction rather than writing typos.
`IngestResult.errors` is a `list[str]` (one message per failed show) rather than
a bare count, so Phase 2.1's `make scrape` and 2.3's scrape-health endpoint can
surface *what* failed.

**Seed.** `repo/seed_venues.py` upserts the four jazz venues; idempotent via
upsert-on-slug (so the "seed only if empty" guard is unnecessary — re-running
converges either way). Each `calendar_url` is a `TBD` placeholder set by the
per-venue Phase 2.x scraper ticket. The "seed on app startup" hook lands with
the FastAPI app in Phase 2.1; for now `seed()` is callable directly /
`python -m foghorn.repo.seed_venues`.

Tests (32, all green under mypy `strict`): `test_canonicalize.py` (accents,
punctuation-as-separator, idempotence), `test_repo_venues.py` and
`test_repo_shows.py` (upsert idempotency, bill replacement, every `list` filter
combination + `start_utc` ordering), `test_seed_venues.py` (four venues,
idempotent), and `test_ingest_pipeline.py` (the new/duplicate/same-headliner-
different-time count matrix, tz→UTC math, display-name preservation, performer
reuse across shows, and per-show error isolation via a bad-tz venue). A shared
`conn`/`venue` fixture pair in `tests/conftest.py` gives each test a fresh DB.

**API-surface note for scraper authors:** filling in `backend/README.md` §
Data Model documented the schema, the natural-key dedup, and the
`ingest_scraped_shows(conn, venue, scraped) -> IngestResult` entry point a
Phase 2.x scraper hands its output to. § Storage gained the connection-handling
and repo-primitive details.

## Repo skeleton and CI gate (Phase 1.1, May 2026)

First code to land in foghorn — the two-package monorepo skeleton, the
lint/type/test gate, and CI. No application logic; this is the structure that
Phase 1.2 (data model) and Phase 2 (scrapers) fill in. Closes #2.

**Backend** (`backend/`). Python 3.11+, `src/` layout with `foghorn` as the
import root and empty-but-present `scrapers/`, `ingest/`, `repo/`, `api/`
subpackages. `pyproject.toml` uses hatchling and pins runtime deps (fastapi,
httpx, beautifulsoup4, apscheduler, pydantic v2) and dev deps (pytest, ruff,
mypy) to the exact versions resolved at scaffold time. APScheduler is held on
the 3.x line — 4.x is a different API. mypy runs in `strict` mode; one smoke
test (`tests/test_smoke.py`) imports all four subpackages so the gate has
something real to run.

**Storage decision: stdlib `sqlite3`, not SQLAlchemy.** The ticket left this to
the implementer. foghorn is single-user / local-first through Phase 5, the
query surface is small (filtered `SELECT`s plus upsert-on-natural-key for
idempotent scraper re-runs), and a hand-written SQL layer in `repo/` keeps the
dependency surface minimal and the DB trivially inspectable with any `sqlite3`
client. The repo layer (Phase 1.2) will wrap `sqlite3` behind typed functions
returning Pydantic models, so callers never touch raw rows or `Any`. If hosting
later forces Postgres, `repo/` is the single seam to swap. Documented in
`backend/README.md` § Storage.

**Frontend** (`frontend/`). `create-next-app` with TypeScript + Tailwind +
App Router (no `src/` dir, `@/*` import alias). The demo page is stripped to a
"foghorn — coming soon" placeholder and the layout metadata set to foghorn.
Added a `typecheck` script (`tsc --noEmit`) because the gate calls
`npm run typecheck` and create-next-app doesn't generate one.

**Gate + CI.** Root `Makefile`: `make gate` runs the backend half
(`ruff check . && mypy src && pytest`) then the frontend half
(`npm run typecheck && npm run lint && npm run build`), stopping at the first
non-zero exit; `make backend-gate` / `make frontend-gate` run the halves
individually; `make install` installs both. The backend targets assume the
project's tools are on PATH (an activated venv locally, or the CI runner's
setup-python environment after `make install`). `.github/workflows/gate.yml`
runs `make install && make gate` on ubuntu-latest with Python 3.11 + Node 20,
caching pip and npm. Root `.gitignore` covers Python, Node, and the
`*.db`/`*.sqlite*` files Phase 1.2 will start writing.

**Notes / gotchas (some for the PM thread):**

- **`create-next-app@latest` now installs Next.js 16 (16.2.6) + React
  19.2.4**, not Next 15. AGENTS.md, README, and PROJECT_PLAN still say
  "Next.js 15"; the ticket said use `@latest`, so 16 is what shipped. Those doc
  references should be reconciled (PM-thread territory). Next 16 uses Turbopack
  for `next build` by default and carries breaking changes vs. 15 — future
  frontend work should consult the bundled docs in `node_modules/next/dist/docs`.
- **Removed the `frontend/AGENTS.md` + `frontend/CLAUDE.md` stubs** that
  create-next-app now generates. The repo's model is one authoritative root
  `AGENTS.md`; a competing nested `AGENTS.md` is a footgun about which doc is
  canonical. The one useful nugget from the stub is preserved above (Next 16
  breaking changes / bundled docs).
- Filled the leftover `{{PROJECT_NAME}}` placeholder in this file's header
  while adding this entry. `docs/CHANGELOG.md` still carries the same
  placeholder, left for the PM thread / first release cut.
- mypy `strict` is on with no per-module overrides yet. A forward-looking
  `ignore_missing_imports` override for bs4/apscheduler produced an "unused
  section" note (nothing imports them yet), so it was omitted; Phase 2.x adds
  it when those libraries are actually imported.

Acceptance verified locally: `make install` and `make gate` both run clean on
the skeleton (backend ruff/mypy/pytest green; frontend typecheck/lint/build
green), and the four subpackages import cleanly. CI on the PR is the remaining
check.
