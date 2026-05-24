# foghorn Shipped Work

Chronological record of completed work — what landed, when, and why. Each entry preserves the narrative context that informed the design so it stays available as scar tissue when scoping new work.

`PROJECT_PLAN.md` is the active doc: what's in flight, queued, and deferred. When a new phase/feature ships, its spec moves here and the active doc collapses to a one-line status with a link into this file. Read this file on demand when you need detail on past work; the active doc is the daily read.

Ordering: newest at top. When adding a new entry, insert it at the top of the file. Older entries preserve their original recording order — when reorganizing, prefer "insert at top of recent block" over "deeply reorder existing history."

---

## Late filter now starts at 9pm — no time-of-day gap (May 2026)

Small follow-up to Phase 3.1's time-of-day chips. As shipped, `Late` was
`start_local_time >= 22:00` and `Early` was `< 21:00`, leaving a dead band:
shows starting 9:00–9:59pm matched *neither* chip (≈10% of the calendar). Per
user request, `Late` now starts at **21:00**, so Early (`< 21:00`) and Late
(`>= 21:00`) are exact complements — every show is one or the other.

One-line change to the `repo/shows.py` time-of-day clause (22:00 → 21:00), the
chip relabeled `Late (10pm+)` → `Late (9pm+)`, and the `test_time_of_day_late`
expectation updated (now matches the 21:30 set too) with a new partition test
asserting `early + late == all`. Deviates from #19's ticketed gap, intentionally
— the gap was more confusing than useful in practice.

## Free-text performer search (Phase 3.3, May 2026)

Type a name, find every upcoming show with that performer on the bill. Closes
#20. Almost entirely wiring — the matching was built in Phase 1.2 and just
hadn't been exposed.

**Reused 1.2's matching, didn't reinvent it.** `?performer_query=` on
`GET /api/shows` canonicalizes the input with the *same* `canonicalize()` the
ingest pipeline uses, then sets `ShowFilters.performer_canonical_substring` —
the field, repo clause (`shows.list`), and normalization all shipped in 1.2.
So "Joshua Redman" finds "joshua redman quartet" (substring after canon), the
existing `EXISTS` join matches **headliner or support**, and accent/case fall
out for free (NFKD strip). Phase 4's watchlist will call `shows.list` the same
way — no parallel matching implementation to drift.

**Canonicalize on input.** The query is normalized server-side before matching,
so the client sends raw text and the API does the right thing. A query that's
empty after canonicalization (whitespace or punctuation only) is treated as
**no filter**, not "match nothing" — verified against `""`, `"   "`, and
`"!!!"`.

**Search box (`PerformerSearch.tsx`).** Its own client component — composed into
`FilterBar` with one import + one JSX line — deliberately, to keep the merge
surface with #21 (region filter) to a single "keep both" line, same playbook as
the Phase 2.2 sibling scrapers. It holds the input in local `useState`
(transient typing), debounces a `?performer_query=` push ~300ms after the user
pauses (merging with the other params, not clobbering them), seeds its initial
value from `useSearchParams()`, resyncs when the URL changes externally (Clear
filters / back button), and has a clear `×`. New backend tests live in a
dedicated `tests/api/test_shows_performer_filter.py` (not the shared endpoint
test) for the same anti-conflict reason.

**No new edge cases.** 1.2's matching held up — headliner+support coverage and
accent-insensitivity worked first try; nothing needed fixing. Substring (not
token/FTS) means a reordered query like "redman joshua" won't match "joshua
redman quartet"; that's the documented v0.2.0 tradeoff, FTS5 deferred until it
bites (the watchlist is the likely forcing function).

Tests: 7 in `test_shows_performer_filter.py` (headliner/support match, no-match
empty, empty/whitespace/punctuation = no filter, accent-insensitive, stacks
with venue + date window). 87 green under mypy `strict`. Verified live against
the real DB: "lateano" → 4 Vince Lateano shows, "quartet" → 46, and
`?performer_query=quartet&venues=mr_tipples` correctly stacks.

**Frontend test gap (still open, per 3.1):** no component-test framework, so
`PerformerSearch`'s debounce/clear/resync is verified by build + live exercise,
not an automated test. Same future ticket 3.1 flagged.

## Region and neighborhood filter (Phase 3.2, May 2026)

The second Phase 3 filter dimension, built on 3.1's URL-as-state framework.
Closes #21. Adds `?region=` and `?neighborhood=` to `GET /api/shows` plus a
region chip group and a region-scoped neighborhood dropdown on the frontend.

- **Backend.** `?region=SF` matches the venue's `region`; `?neighborhood=`
  matches the venue's `neighborhood` case-insensitively (`COLLATE NOCASE`,
  exact — neighborhoods are short distinct strings, no fuzzy match needed). Both
  stack as ANDs with the existing date / venue / time-of-day / performer
  filters. `repo.shows.list` already joined `venues` and filtered `region`
  (added speculatively in an earlier phase); this wires `neighborhood` into the
  same query and threads both params through `ShowFilters` and the endpoint.
  Unknown `region` values are ignored (narrowed to the `Region` literal) rather
  than 400, mirroring `time_of_day`.
- **No seed changes needed.** The four-venue seed already carries `region="SF"`
  and correct neighborhoods (Hayes Valley — SFJAZZ + Mr. Tipple's; North Beach —
  Keys; Glen Park — Bird & Beckett). Verified, left as-is.
- **Frontend.** A single `LocationFilter.tsx` (co-locating the region chips and
  the neighborhood select) composes into `FilterBar` with one import + one JSX
  line — deliberately small to keep the merge with the sibling 3.3 search ticket
  trivial. All four regions render; only regions with scraped venues are
  interactive (derived from `/api/venues`), the rest greyed with a "(soon)"
  affordance so the Phase 5 expansion is visible. Region is **single-select**
  (re-click clears). The neighborhood dropdown appears only when a region is
  active and lists that region's neighborhoods; changing/clearing the region
  drops the neighborhood param (it's region-scoped).
- **Region/neighborhood vs. venue checkboxes: independent.** They AND together
  in the backend rather than cascading — a contradictory combination just yields
  the honest empty state. Simpler than auto-toggling checkboxes, and the URL
  stays a faithful record of exactly what was asked.

Mostly framework-complete until Phase 5 brings non-SF venues: today every venue
is SF, so region doesn't discriminate and only neighborhood meaningfully
narrows. The moment an East Bay / Peninsula / South Bay venue ships a scraper,
its region chip activates and the filter just works.

Tests: `tests/api/test_shows_region_filter.py` (its own file, to avoid conflict
with 3.3's tests) covers region SF / East Bay / unknown, neighborhood exact +
case-insensitive, combined, and stacking; `tests/test_repo_shows.py` gains a
neighborhood repo case. Verified live over HTTP (`region=SF` → all,
`East Bay` → `[]`, `neighborhood=Hayes Valley` → Mr. Tipple's,
`region=SF&neighborhood=North Beach` → Keys). Full `make gate` green.

**Worktree note.** Built in an isolated `git worktree` alongside the active 3.3
performer-search work; both touch `FilterBar.tsx`, `api/shows.py`, and
`page.tsx` additively, so the second of #20 / #21 to merge resolves a small
"keep both" conflict.

## Date and venue filters, URL-driven framework (Phase 3.1, May 2026)

The first Phase 3 ticket and the one that sets the pattern: the calendar is now
filterable by date range, venue, and time of day, with all filter state living
in the URL. Closes #19. Builds on v0.1.0; 3.2 (region) and 3.3 (performer
search) plug into this framework.

**URL is the single source of truth.** `app/page.tsx` is an `async` server
component reading `searchParams` (`?from=&to=&venues=&time_of_day=`), building
the `/api/shows` query, fetching, and rendering. Filters are shareable,
bookmarkable, and back-button-correct. The client `FilterBar` derives every
control's state from `useSearchParams()` on each render and writes changes via
`router.push` — **no local filter state**, so URL and UI can't drift. This is
the contract 3.2/3.3 inherit: add a param, read it server-side, add a control
that pushes it.

**Native date inputs, no picker library.** Two `<input type="date">` (with
`min`/`max` cross-bounding) on apply-on-change — selecting a complete date
navigates immediately; native inputs don't fire per-keystroke, so no debounce
needed. Skipped `react-day-picker` et al.: a dependency + bundle weight for a
two-field range the platform already gives us. Revisit if we need range-drag or
multi-month UX.

**`?venues=` (multi-value).** Comma-separated slugs
(`?venues=bird_and_beckett,keys_jazz_bistro`) parsed into
`ShowFilters.venue_slugs`; unknown slugs simply don't match (mixed valid/invalid
filters to the valid). The legacy singular `?venue=` still works. The frontend
omits the param entirely when all (or zero) venue checkboxes are selected,
keeping the default URL clean and dodging the empty-set footgun (zero
checked = all).

**`GET /api/venues`** returns the venue-filter options — `slug`/`name`/
`neighborhood`/`region`. It's filtered to `REGISTERED_SCRAPERS`, so seeded-but-
deferred **SFJAZZ is excluded** (no scraper, never any shows → no dead
checkbox). This couples the venues endpoint to the scraper registry on purpose:
"venues foghorn tracks" is exactly the registry.

**Time-of-day is server-side.** `Early` (`start_local_time` < 21:00) / `Late`
(>= 22:00) are a `?time_of_day=` param → `ShowFilters.time_of_day` → a SQL
clause (lexical compare works since `HH:MM` is zero-padded 24h). Chosen over
client-side post-filtering for consistency with the other filters and so the
URL fully determines the result set (cache-friendly, shareable). Unknown values
are ignored, not 400. Note the deliberate 21:00–21:59 gap between Early and
Late — matches the ticket's definition.

Backend tests (`api/test_shows_endpoint.py` extended, `api/test_venues_endpoint.py`
new) cover `?venues=` (single/multi/unknown/mixed), legacy `?venue=`,
`time_of_day` early/late + ignored-bogus, filter stacking, and that
`/api/venues` lists exactly the three scraped venues. 80 tests green under mypy
`strict`.

**Frontend testing gap (flagged per ticket).** The frontend still has no unit/
component test framework — only `tsc`/`eslint`/`next build`. The
URL→fetch→render path was verified by a live SSR check (filtered URLs render
the right venues/times), but `FilterBar`'s click-through (chip toggles,
checkbox→URL) isn't covered by an automated test. Standing up Playwright/RTL is
its own ticket; didn't introduce one here.

## Daily refresh scheduler and scrape-health endpoint (Phase 2.3, May 2026)

Phase 2's last piece: refreshes now happen on their own (nightly 04:00 PT) and
there's a surface to answer "did last night's run work?" Closes #8. With this,
Phase 2 is complete — open the page in the morning and all three jazz venues
are current.

**`BackgroundScheduler`, not `AsyncIOScheduler`.** The scrape job is synchronous
and blocking (httpx fetches + SQLite writes). `BackgroundScheduler` runs it on a
worker thread, off the FastAPI event loop, so the API stays responsive during a
refresh. Each run opens its **own** SQLite connection inside that thread, which
satisfies sqlite3's `check_same_thread` guard (the app's request connections are
separate and short-lived). An `AsyncIOScheduler` would have run the blocking job
on the event loop — wrong fit.

**One unit of work, two callers.** `scheduler/runner.py:run_scrape(conn,
scrapers=…)` runs every registered scraper through ingest, captures a per-venue
result (`created` / `updated` / `errors`), and records one run. Both the nightly
job *and* `make scrape` call it, so a manual refresh lands a `scrape_runs` row
and shows in `/api/health/scrape` exactly like a scheduled one (the old
bespoke loop in `cli/scrape.py` is gone). A per-venue failure — scraper raises,
or ingest reports errors — is captured in that venue's `errors` and never
propagates: one bad venue can't crash the run or kill the scheduler thread.

**Schema + trim.** Two additive tables: `scrape_runs(id, started_at,
finished_at)` and `scrape_run_venues(scrape_run_id, venue_slug, started_at,
finished_at, created, updated, errors_json)` — errors are stored as a JSON array
in `errors_json`. `repo/scrape_runs.record_run` inserts the run + child rows
then trims to the most recent 30 (`DELETE … ORDER BY id DESC LIMIT -1 OFFSET
30`), deleting child rows first so no orphans accumulate.

**`GET /api/health/scrape`** (`api/health.py`) returns the latest run's
`last_run_at` / `last_run_finished_at` + a per-venue breakdown (`slug`,
timestamps, counts, `errors`). Returns **503 `{"error":
"no_scrape_runs_yet"}`** when no run exists yet — deliberately distinct from "ran
but a venue failed" (200 with that venue's `errors` populated), so an ops poller
can tell "never ran" from "ran badly."

**Test-environment guard.** The scheduler is gated behind
`FOGHORN_DISABLE_SCHEDULER`; `start_scheduler()` returns `None` when it's set.
`tests/conftest.py` sets it at import so no pytest run (including the
`TestClient`-driven API tests, which exercise the lifespan) ever starts a
background thread or fires cron. The app lifespan starts the scheduler on
startup and `shutdown(wait=False)`s it on exit.

Tests (7 new, all green under mypy `strict`): `scheduler/test_runner.py`
(success + raising scraper isolation, persistence/readback, unseeded-venue
error), `scheduler/test_trim.py` (32 inserts trim to 30 keeping newest; explicit
trim leaves no orphan child rows), `api/test_health_scrape.py` (the 503 no-runs
case + latest-run shape with a populated `errors`). Live: `make scrape` recorded
a run across all three venues (59 / 36 / 106), and startup registered the job
with `next_run_time` at the next 04:00 PT.

**Deps note.** `apscheduler` (already pinned since Phase 1.1) ships no `py.typed`,
so it joined the mypy `ignore_missing_imports` override alongside
`recurring_ical_events`.

**Release signal (for the PM thread):** Phase 2.1 (#6), 2.2 (#5, #7), and 2.3
(#8) are all shipped — this is the **v0.1.0 release-cut point** per
`docs/PROJECT_PLAN.md` → "Suggested sequencing." Per `RELEASE_PROCESS.md` the
cut is a PM-thread ritual, so it is *not* done in this PR — surfaced for the PM
thread to run.

## Mr. Tipple's scraper via the Tribe Events API (May 2026)

Second of the three Phase 2.2 sibling scrapers (closes #7). Adds Mr. Tipple's
Recording Studio (39 Fell St, Hayes Valley) behind the registry the 2.1 pilot
established — a third distinct data-source pattern.

**Domain fix.** The #7 ticket and the Phase 1.2 seed both had the site as
`mrtipples.com`, which is **NXDOMAIN**. The live site is `mrtipplessf.com`
(found by probing variants after the seeded domain failed to resolve). The
seed's `website_url` and `calendar_url` for `mr_tipples` are corrected here.
*Same lesson as the SFJAZZ re-pilot: probe before trusting a seeded URL.*

**Data source: The Events Calendar (Tribe) REST API.** Mr. Tipple's is
WordPress running the Tribe "The Events Calendar" plugin, which exposes a clean
JSON API at `/wp-json/tribe/events/v1/events` — richer than the iCal feeds used
elsewhere. Each event carries `title`, `start_date` (venue-local
`YYYY-MM-DD HH:MM:SS`), `timezone`, the event `url`, a `website` (the OpenTable
reservation link), and `cost`. So this scraper fills `ticket_url` (OpenTable)
and `price_text` (`cost`, e.g. "$15 – $30") that Bird & Beckett's calendar
couldn't. `source_url` is the Tribe event permalink.

**Parsing (`scrapers/mr_tipples.py`).** Same fetch/parse split as B&B.
`fetch_events(today, window_days, client=)` pages the REST API across the next
~90 days via `next_rest_url` (and stops if Tribe 404s past the last page); the
`client` is injectable for mock-transport tests. `parse_events` is pure: it
HTML-unescapes Tribe's entity-laden text (`&#8217;`, `&amp;`), keeps times as
naive venue-local (ingest re-applies the tz), and skips `all_day` entries,
`hide_from_listings` events, and **closure markers** the venue posts as calendar
entries ("Closed", "Closed for Private Event"). No recurrence expansion needed
(Tribe returns concrete instances) and no music/non-music filter (it's a pure
jazz room) beyond the closure filter.

Tests (6, in `scrapers/test_mr_tipples.py`): a saved API-response fixture
(`fixtures/mr_tipples_2026_05.json`) drives `parse_events` deterministically
(entity decoding, accents, ticket/price mapping, free-event nulls, and the
all-day / hidden / closed exclusions); two `httpx.MockTransport` tests cover
pagination and the 404-past-last-page stop. Live: `make scrape` ingested 106
shows, idempotent on re-run.

**Gotcha.** Mr. Tipple's runs early + late sets, which appear as same-title
events at different start times — distinct natural keys, so both persist (this
is correct: they're separate performances).

**Concurrency note.** Built alongside #5 (Keys Jazz Bistro), shipped concurrently
by another agent — which moved to an isolated `git worktree` to stop clobbering
the shared tree (#14). Both register a scraper in `scrapers/__init__.py`; this
branch merged `main` and kept all three venues in `REGISTERED_SCRAPERS`.

## Keys Jazz Bistro scraper (Phase 2.2a, May 2026)

Second venue, and the first HTML scraper — Bird & Beckett (the pilot) reads an
`.ics` feed. Closes #5. Follows the scraper-author pattern the
[Phase 2.1 pilot](#phase-21-end-to-end-pilot-via-bird-and-beckett-may-2026)
established — isolated `fetch_html`, a pure `today`-injected `parse_html`, a
registry entry, a fixture test — so this entry records only what's
Keys-specific.

- **Source: `/upcoming-shows/`, not `/event-calendar/`.** Keys runs WordPress
  with the "simple-events" plugin, which renders both. `/event-calendar/` has
  machine-readable `<time datetime>` but shows one month at a time (including
  past days) and duplicates a desktop grid + a mobile list. `/upcoming-shows/`
  is a forward-looking WP Query Loop (`ul.wp-block-post-template`) that starts
  at today, needs no pagination, and lists every upcoming show as a structured
  `<li>`. Cleaner on every axis, so the scraper targets it.
- **Plain `httpx` + `bs4`; no `playwright`.** The show list is in the
  server-rendered HTML. (SFJAZZ — the original 2.1 target — was dropped for a
  Cloudflare challenge; Keys has no such wall.)
- **Dates are free text** (`Saturday, May 23, 2026 @ 10:30pm`) in a bare `<p>`.
  The parser scans `<p>` elements — not the whole `<li>` text — so a show's
  description paragraph or the ticket link's `aria-label` date can't be
  mis-read. A weekday-anchored regex splits date + time; the weekday is not
  trusted (it isn't validated against the date).
- **Per-show provenance**: `source_url` is each show's own `/event/<slug>/`
  page; `ticket_url` is the WooCommerce "Get Tickets" add-to-cart link when
  present, else `None`. The listing carries no doors time or price → both
  `None`.

Verified live: `python -m foghorn.scrapers.keys_jazz_bistro` returns 36 shows
(May 23 → Jun 24); two `make scrape` runs report `created=36` then
`updated=36, errors=0` — idempotent on the natural key. The fixture test drives
`parse_html` from a trimmed real snapshot covering the edge cases (multi-show
day, minutes in the time, curly quotes, a missing ticket link, an out-of-window
event). Full `make gate` green.

**Worktree note.** Built in an isolated `git worktree` because another agent was
shipping Mr. Tipple's (#7) in the main working tree at the same time, and one
shared tree was clobbering both. The sibling 2.2 PRs each touch the registry
(`scrapers/__init__.py`), the seed (`seed_venues.py`), and these docs, so expect
a small conflict when the second of the two lands — resolve by keeping both
venues' entries.

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
