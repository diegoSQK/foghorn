# foghorn Changelog

Versioned releases of foghorn. Each entry corresponds to a git tag on `main`. The release ritual and event-trigger rule live in [RELEASE_PROCESS.md](RELEASE_PROCESS.md). The chronological as-shipped history with full design narrative lives in [SHIPPED.md](SHIPPED.md); this file is the indexed cut-points.

Versions are semver, locked across the project's packages.

---

## v0.1.0 — 2026-05-24

First foghorn release. Phase 2 complete: end-to-end scraping + ingest + API + frontend across three Bay Area jazz venues (Bird & Beckett, Keys Jazz Bistro, Mr. Tipple's), with a nightly refresh and a scrape-health surface. Opening the frontend shows the next 30 days of jazz, grouped by date, refreshed automatically at 04:00 PT every night. Phase 1 (scaffolding + data-model spine) rolls up under this cut since it landed in the same week.

### Headline shipments

- **Phase 1.1 — Repo skeleton + CI gate.** Two-package monorepo (Python 3.11+ backend; Next.js 16 + TypeScript + Tailwind frontend). Storage choice: stdlib `sqlite3` (no ORM). `make gate` running ruff + mypy strict + pytest + frontend typecheck/lint/build, wired into GitHub Actions. See [Repo skeleton and CI gate](SHIPPED.md#repo-skeleton-and-ci-gate-phase-11-may-2026).
- **Phase 1.2 — Data model + ingest scaffolding.** SQLite schema (`venues` / `performers` / `shows` / `show_performers`), conn-injected typed repo layer returning Pydantic, `ingest_scraped_shows` with unicode-aware canonicalization and venue-tz→UTC, four-venue seed. Natural key `(venue_id, start_local_date, start_local_time, headliner_canonical)`; both `start_utc` and `start_local_*` stored so ordering is sortable across venues while dedup matches what the venue published. See [Data model and ingest scaffolding](SHIPPED.md#data-model-and-ingest-scaffolding-phase-12-may-2026).
- **Phase 2.1 — End-to-end pilot via Bird & Beckett.** First venue end-to-end: scrape → ingest → `GET /api/shows` → SSR'd frontend list grouped by date. Establishes the scraper registry, `make scrape` / `make backend-run` / `make frontend-run` targets, and the per-show API response shape (documented in `backend/README.md` as the reference for future scraper authors). Pilot re-homed from SFJAZZ → Bird & Beckett after SFJAZZ proved Cloudflare-blocked; B&B publishes a public Google Calendar `.ics` parsed via `icalendar` + `recurring-ical-events` (handles residencies). See [Phase 2.1 end-to-end pilot via Bird and Beckett](SHIPPED.md#phase-21-end-to-end-pilot-via-bird-and-beckett-may-2026).
- **Phase 2.2 — Keys Jazz Bistro + Mr. Tipple's scrapers.** Two more scrapers behind the same registry, in two distinct data-source patterns. **Keys** scrapes the WordPress `/upcoming-shows/` page via plain `httpx`+`bs4`. **Mr. Tipple's** reads the Tribe "The Events Calendar" REST API, which also fills `ticket_url` (OpenTable reservation link) and `price_text` that the `.ics` feed couldn't. Plus a domain-discovery fix — the seeded `mrtipples.com` was NXDOMAIN, the live site is `mrtipplessf.com`. See [Keys Jazz Bistro scraper](SHIPPED.md#keys-jazz-bistro-scraper-phase-22a-may-2026) and [Mr. Tipple's scraper via the Tribe Events API](SHIPPED.md#mr-tipples-scraper-via-the-tribe-events-api-may-2026).
- **Phase 2.3 — Daily refresh scheduler + scrape-health endpoint.** APScheduler `BackgroundScheduler` runs all registered scrapers nightly at 04:00 America/Los_Angeles on a worker thread (sync `httpx`+`sqlite3` work, off the FastAPI event loop). `make scrape` shares the same `run_scrape` unit so manual + scheduled runs record consistently into a 30-row-bounded `scrape_runs` table. `GET /api/health/scrape` surfaces the last run's per-venue counts + errors, returning a distinct 503 `{"error": "no_scrape_runs_yet"}` until the first run lands. Per-venue failures are isolated; one bad venue can't crash the scheduler thread. See [Daily refresh scheduler and scrape-health endpoint](SHIPPED.md#daily-refresh-scheduler-and-scrape-health-endpoint-phase-23-may-2026).

### Known follow-ons

No open GitHub issues at cut time. Items noted during the phase that aren't blocking but are worth tracking:

- **Non-music heuristic on Bird & Beckett's calendar is imperfect by design.** The filter errs toward inclusion (per the original ticket), so the occasional small-press literary event still leaks through. Refining is future work; file a ticket if it gets noisy in practice.
- **Sibling-scraper PRs hit registry-edit conflicts.** When two agents added scrapers in parallel, both touched `REGISTERED_SCRAPERS` in `scrapers/__init__.py` (and the seed, and docs) and the second to merge had to resolve. Working in isolated `git worktree`s is the workaround that landed; at scale a registration pattern that avoided the shared dict-edit (entry-point discovery, per-venue self-registering modules) could remove the friction.
- **SFJAZZ remains deferred.** Cloudflare managed challenge 403s every plain HTTP client; bypass was out of scope. See `docs/PROJECT_PLAN.md` → "Deferred / still-outstanding" for the unblock condition. File a fresh ticket when there's appetite for a headless-browser approach or a cleaner data feed surfaces.
- **Mr. Tipple's same-title early + late sets** persist as separate rows by design (distinct natural keys), which is correct but worth knowing the first time it surprises someone.

### Queued for the next minor

**Phase 3 — Filtering & search** is the natural next coherent block: date-range + venue filters (3.1), region/neighborhood filter (3.2), free-text performer search (3.3). PM thread will queue the three tickets as a follow-on to this cut. Per `docs/PROJECT_PLAN.md` → "Suggested sequencing," `v0.2.0` is more likely to anchor on Phase 4 (Watchlist), with Phase 3 either rolling into that cut or landing as a `v0.1.x` if a coherent sub-arc completes first.

---

*First release entry above. Subsequent entries follow the same shape: short framing paragraph, Headline shipments (anchor-linked into SHIPPED.md), Known follow-ons, optional Queued for the next minor.*
