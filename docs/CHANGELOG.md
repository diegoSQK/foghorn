# foghorn Changelog

Versioned releases of foghorn. Each entry corresponds to a git tag on `main`. The release ritual and event-trigger rule live in [RELEASE_PROCESS.md](RELEASE_PROCESS.md). The chronological as-shipped history with full design narrative lives in [SHIPPED.md](SHIPPED.md); this file is the indexed cut-points.

Versions are semver, locked across the project's packages.

---

## v0.4.0 — 2026-07-07

**Following + channels.** v0.3.0 built the catalog; v0.4.0 makes foghorn follow things and listen to channels venue scrapers can't reach. All five region chips are live (41 scraped venues + ~20 quarantined long-tail venues, ~1,600 shows), the watchlist grew a venue-following twin, and two new ingest channels landed: the Bay Improviser aggregator (under the quarantine-with-flag posture) and stage-1 mailing-list ingest with a human review queue.

### Headline shipments

- **Venue batches 2–3 (+8 venues → 37 scraped).** Bimbo's 365, Neck of the Woods, August Hall, The Warfield, Thee Stork Club, The UC Theatre, Club Deluxe, Club Fox — plus resolved "Moved To" annotations at August Hall and a documented New Parish block (its TicketWeb API works; the venue's inventory is empty everywhere). See [Venue batch 2](SHIPPED.md#venue-batch-2-six-more-rooms-july-2026) and [Venue batch 3](SHIPPED.md#venue-batch-3-club-deluxe--club-fox-new-parish-blocked-july-2026).
- **Venue watchlist (Phase 9) + first-class venue UX.** Follow venues with ★ pins anywhere; /venues page; ?venue_watchlist= filter; "My venues" chip; venue names link to their calendars; the checkbox grid replaced by a searchable picker. See [Venue watchlist](SHIPPED.md#venue-watchlist-phase-9-july-2026) and [Search + venue-UX arc](SHIPPED.md#search--venue-ux-arc-july-2026) (which also covers token-prefix search and follow-by-name).
- **Bay Improviser aggregator ingest** under the decided quarantine-with-flag + watchlist-bypass posture: a new aggregator tier resolves community events to known venues (token matching + aliases), fuzzy-dedupes against scraped rows, and auto-creates quarantined long-tail venues (Little Hill Lounge — unscrapeable directly — is now covered). "Long tail" toggle; pins promote. See [Bay Improviser aggregator ingest](SHIPPED.md#bay-improviser-aggregator-ingest-july-2026).
- **Mailing-list ingest, stage 1 (Phase 8)** — deterministic, review-queue-gated: IMAP poller + paste-an-email form → parsed drafts in an /inbox UI with duplicate warnings; approval creates the event through the manual path. Built for artists who announce only by mailing list. See [Mailing-list ingest, stage 1](SHIPPED.md#mailing-list-ingest-stage-1-phase-8-july-2026).
- **North Bay + South Bay regions real.** Mystic Theatre + Sweetwater Music Hall (North Bay); SJZ Break Room + The Ritz (South Bay — The Ritz via its ajax=1 gig-list endpoint after the sweep had rated it HARD). HopMonk (Eventim bot wall) and Poor House Bistro (JPEG calendar) documented blocked; Café Pink House and Art Boutiki confirmed closed.
- **Smaller:** Kilowatt threads Dice genre tags (40/51 shows tagged); the watchlist digest gained `include_venues`; watchlist e2e specs (suite now 9); e2e app port moved off 3100 so test runs can't collide with a live dev server.

### Decisions recorded

- **Aggregator discovery posture:** quarantine-with-flag with watchlist bypass (shipped as designed).
- **LLM in the enrichment tier: declined for now** — 7.4 stage 2 (performer-genre LLM pass) and Phase 8 stage 2 (LLM email extraction) both stay parked on this one call; the deterministic layers are their validation baselines if it's ever reopened.

### Known follow-ons

- **Ticketmaster Discovery API spike** (Fillmore/Regency coverage) — in flight at cut time; lands as a memo + POC after this release.
- **New Parish recheck** in ~2–4 weeks (endpoint pre-solved; inventory empty everywhere as of 2026-07-07).
- **Hosting + alerts delivery** — the digest endpoint (now venue-aware) computes "what's coming up for you"; delivery and reachability are the unbuilt half. The usage pattern (daily dogfooding, two watchlists) increasingly argues for this pairing next.
- Blocked venues with unblock conditions: SFJAZZ, HopMonk Novato, Poor House Bistro, Freight & Salvage, The Midway, El Rio (see PROJECT_PLAN deferred list).

---

## v0.3.0 — 2026-07-03

**Breadth + the reading surface.** The venue-expansion arc: foghorn grew from 3 scraped venues to 29 (≈1,200 upcoming shows across SF, East Bay, and the Peninsula), and the calendar grew the structure to read it — genre/origin/type facets, day/week/month views, manual entry for what scrapers can't see. Built as a user-directed feature-branch push (no per-venue tickets); the per-platform scraping playbook it established lives in the SHIPPED entries.

### Headline shipments

- **Venue expansion: 23 new scrapers + genre facet (Phases 5 + 7.1).** SF: Black Cat, Ocean Ale House, Boom Boom Room, Madrone, Bottom of the Hill, Rickshaw Stop, Kilowatt, The Knockout, The Independent, Cafe du Nord, GAMH, The Chapel, DNA Lounge, Medicine for Nightmares, Center for New Music. East Bay: Yoshi's, CJC, Ivy Room, 924 Gilman, Natural Grocery Annex, Cornerstone, Fox Theater, Greek Theatre, The Back Room, Piedmont Piano. Peninsula: Guild Theatre. Nearly every venue needed a different source shape (.ics, five ticketing-platform APIs, JSON-LD, Squarespace JSON, static HTML) — see [Venue expansion batch](SHIPPED.md#venue-expansion-batch-23-new-scrapers--genre-facet-july-2026). `venues.genre` + `?genre=` + data-driven chips shipped alongside, with the first additive-column migration guard. Blocked venues (For The Record, Little Hill Lounge, plus the sweep's Cloudflare walls) are documented with unblock conditions.
- **Performer origin tagging v1 (local/touring).** The mission facet — "show me local acts to support" — as performer-level tags: conservative heuristic bootstrap (`make tag-origins`), permanent manual overrides, any-performer `?origin=` filter, "(likely)" chips + local badges. First run: 153 local / 29 touring / 1,144 deliberately unknown. See [Performer origin tagging v1](SHIPPED.md#performer-origin-tagging-v1-localtouring-july-2026).
- **Manual events + jam sessions.** `POST /api/events` + `/add` form for shows scrapers can't see (house concerts, Instagram-only venues); unknown venue names become filterable manual venue rows; manual rows are badged and deletable, scraped rows aren't. `shows.event_type` makes jams first-class: explicit tags, a form checkbox, and a conservative title heuristic (35 live jams tagged); `?type=` filter + chips. See [Manual events + jam sessions](SHIPPED.md#manual-events--jam-sessions-july-2026).
- **Layered genre resolution + performer-genre bootstrap (Phases 7.2 + 7.4-deterministic).** Genre resolves per-show override → headliner's performer genre → venue default. SeeTickets per-card genres now ingest (92 overrides live); unambiguous title words fill gaps at leanless venues; `make tag-genres` tagged 353/1,368 performers on unanimous evidence. The LLM stage for the rest is deliberately deferred pending the enrichment-tier-dependency decision. See [Layered genre resolution](SHIPPED.md#layered-genre-resolution--performer-genre-bootstrap-july-2026).
- **Calendar views + UI polish.** Day/week/month views (URL-driven, filters apply across views), the teal accent system with a single UI-token file, the collapsed venue disclosure + mobile "More filters" fold, the date-input draft/commit fix, and the search-bar double-× fix. See [Calendar views + UI polish arc](SHIPPED.md#calendar-views--ui-polish-arc-july-2026).
- **Ingest hardening from the live runs:** duplicate acts on a bill no longer violate the show_performers PK (earliest billing position wins), and the full 29-venue scrape is verified idempotent (re-run: 0 created / all updated / 0 errors).

### Known follow-ons

No open GitHub issues at cut time. Doc-tracked follow-ons:

- **Next venue batch** (sweep-verified EASY/MEDIUM): UC Theatre, Bimbo's 365, Neck of the Woods, The Warfield, August Hall, Club Deluxe, Club Fox (Redwood City), Thee Stork Club, The New Parish — plus a **Ticketmaster Discovery API spike** for the Live Nation rooms (Fillmore, Regency Ballroom).
- **Bay Improviser ingest** still awaits the discovery-posture decision (unchanged from v0.2.0) — reinforced by the artist-gig research showing the creative-music scene publishes through aggregators/series, not venue calendars.
- **7.4 LLM stage** (performer genre for the untagged ~75%): deliberately parked pending Diego's comfort with an LLM dependency in the enrichment tier; the deterministic layer is its validation baseline.
- **Kilowatt Dice.fm genre tags** are parseable but not yet threaded into the genre-override layer.
- **North Bay region value** gates Mystic Theatre (SeeTickets — parser exists), Sweetwater, HopMonk.
- **Blocked venues with unblock conditions:** SFJAZZ (Cloudflare), For The Record (Instagram-only), Little Hill Lounge (flyer-JPEG calendar), Freight & Salvage + The Midway (Cloudflare), El Rio (JS-only), Eli's Mile High / Golden Bull (dead sites).

---

## v0.2.0 — 2026-05-24

**Find + follow.** Phase 3 (filtering & search) and Phase 4 (watchlist) shipped together — the calendar is now usable for "what should I do Friday" and "where are my friends playing this week." Plus the Playwright frontend-test framework that three earlier phases asked for, and a research spike that informs the post-v0.2.0 roadmap.

### Headline shipments

- **Phase 3.1 — URL-driven filter framework + date / venue / time-of-day filters.** Filter state lives in URL search params (shareable, bookmarkable, back-button-correct); the server component reads them and re-fetches on navigation; the client `FilterBar` derives state from `useSearchParams` and writes via `router.push`. Native date inputs (no picker library), venue checkboxes from a new `GET /api/venues` endpoint (filtered to scrapers that actually exist, so deferred-SFJAZZ doesn't appear as a dead checkbox), and quick-selector chips: `Tonight` / `This weekend` / `Next 7 days` plus server-side `Early` / `Late` via `?time_of_day=`. This is the framework 3.2 and 3.3 inherit. See [Date and venue filters, URL-driven framework](SHIPPED.md#date-and-venue-filters-url-driven-framework-phase-31-may-2026). A small follow-up moved the `Late` chip from 22:00 to 21:00 so every show falls into either `Early` or `Late` with no gap — see [Late filter now starts at 9pm](SHIPPED.md#late-filter-now-starts-at-9pm--no-time-of-day-gap-may-2026).
- **Phase 3.2 — Region + neighborhood filter.** `?region=` / `?neighborhood=` on `/api/shows`, region chip group with non-SF regions greyed as "(soon)" so the Phase 5 expansion is visible, and a region-scoped neighborhood dropdown. Region/venue checkboxes intentionally independent (AND-combined, no cascade) — contradictory combinations yield the honest empty state, not magic. See [Region and neighborhood filter](SHIPPED.md#region-and-neighborhood-filter-phase-32-may-2026).
- **Phase 3.3 — Free-text performer search.** Debounced (~300ms) search box wired into the URL framework. `?performer_query=` canonicalizes input server-side, then matches headliner or support. Initially substring-match; upgraded to token-bag matching as part of 4.1 (same matcher in search and watchlist for UX consistency). See [Free-text performer search](SHIPPED.md#free-text-performer-search-phase-33-may-2026).
- **Phase 4.1 — Watchlist + token-based performer matching.** Single-tenant `watchlist` table keyed on `canonical_name`; `+`/`✓` add buttons on every performer (optimistic); `/watchlist` route reusing `FilterBar`; `Watchlist (N)` nav count. Token-bag matcher (`repo/performer_match.py`) is the canonical performer match now, shared with 3.3 — "redman joshua" matches "joshua redman quartet" in both contexts. **Two-level matching is deliberate**: button reflects exact canonical membership; `?watchlist=true` filter is token-bag (so watching "Vince Lateano" surfaces "Vince Lateano Trio" shows, but that Trio's button stays `+` unless added). CORS added for the client mutations (`allow_origins=["*"]` for local-first; `FOGHORN_CORS_ORIGINS` to tighten). See [Watchlist data model, UI, and token-based matching](SHIPPED.md#watchlist-data-model-ui-and-token-based-matching-phase-41-may-2026).
- **Phase 4.2 — Watchlist digest endpoint.** `GET /api/watchlist/digest?days=14&limit=20` returns the next-N upcoming watchlist matches, each row carrying a `watchlist_matches` field naming the matching watched display_name(s). Read-only; email/push delivery stays deferred (it's the Deferred Workstream's "alerts/notifications" item). Designed to be consumed by future cron/email/push without re-shaping. See [Watchlist digest endpoint](SHIPPED.md#watchlist-digest-endpoint-phase-42-may-2026).
- **Playwright frontend-test framework.** Resolves the gap three Phase 3 ships flagged: the frontend had only `tsc`/`eslint`/`next build`, no way to assert click-through behavior. Five smoke specs prove the framework (Chromium against a real production build, with a ~30-line Node mock backend because `app/page.tsx` is a server component that `page.route()` can't intercept). Opt-in `make frontend-test` target + separate CI job — deliberately not bundled into the fast `make gate`. Subsequent UI tickets add specs as they touch the surface. See [Frontend e2e test framework — Playwright](SHIPPED.md#frontend-e2e-test-framework--playwright-may-2026).
- **Aggregator-evaluation spike** (research, not implementation). Five-candidate evaluation against a consistent rubric (DoTheBay, Bay Improviser, What's Poppin, Songkick, Bandsintown). **Headline finding: aggregator ingest does NOT replace per-venue scraping for foghorn.** Songkick/Bandsintown are API-gated *and* ToS-bars-scraping *and* coverage-skewed away from small jazz rooms. DoTheBay has the best engineering shape (open JSON API, no anti-bot) but ToS bars scraping — a permission conversation, not a ticket. What's Poppin is a YouTube talk show with no published calendar. The one win: **Bay Improviser** is genuinely ingestible (robots-permissive, structured per-event iCal/gCal data) and on-target for the new-creative wheelhouse. See [Aggregator evaluation spike](SHIPPED.md#aggregator-evaluation-spike-may-2026) and [`docs/spikes/aggregator-evaluation/RECOMMENDATION.md`](spikes/aggregator-evaluation/RECOMMENDATION.md).

### Known follow-ons

No open GitHub issues at cut time. Items noted across this phase that aren't blocking but are worth tracking:

- **Bay Improviser ingest is on hold** pending a product decision on aggregator-discovered-venue posture (auto-accept with quarantine flag vs. curated allow-list vs. first-class auto-accept). PM thread in conversation with Diego; ticket gets filed when the posture is settled. The spike's `# SPIKE — not production` POC scripts in `backend/scripts/` are the working starting point for whoever implements.
- **DoTheBay permission/feed conversation** — non-engineering action. If a permission or licensed feed arrangement is secured with DoStuff/Noise Pop, DoTheBay becomes a small (~1:1 with `ScrapedShow`) ingest add that backfills Phase 5's rock/indie venues with ~87 venues / 239 shows per week of additional coverage. Until then it's out.
- **Watchlist Playwright specs** — the framework shipped (#30) but Phase 4.1's UI didn't get its own e2e specs because 4.1 was in flight in a sibling worktree at the time. Clean small follow-up now that the framework is in place; file when convenient.
- **FTS5 / trigram fuzzy matching** — token-bag matching is the v0.2.0 shape; FTS5 with trigram tokenizer is the planned escalation when typo tolerance or aggressive variant matching is needed. PROJECT_PLAN Phase 7 carries this; the likely forcing function is real-world watchlist usage.
- **CORS posture is permissive (`allow_origins=["*"]`)** for local-first dev convenience. `FOGHORN_CORS_ORIGINS` tightens when the app is deployed publicly — a Phase-9-ish concern (hosting decision is in Deferred Workstream).
- **Sibling-scraper registry-edit footgun** (carried over from v0.1.0 follow-ons) is still open. The Phase 4.1 + Playwright concurrent work didn't hit it (different files), but the Phase 3 sibling pattern (`FilterBar.tsx` compose-via-one-line) worked well — worth applying that pattern to the scraper registry when convenient.

### Queued for the next minor

**Phase 5 — Venue expansion** (rock/indie + East Bay) is the natural next coherent block. **Phase 7.1** (venue-default genre) likely pulls in alongside Phase 5 since genre filtering only becomes meaningful with cross-genre venue diversity. **Bay Improviser ingest** likely layers in here too, pending the discovery-posture decision — if it lands as part of v0.3.0, the release narrative becomes "breadth: rock/indie + East Bay + creative-music long tail." `v0.3.0` cuts when the venue set feels comprehensive enough for personal use.

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
