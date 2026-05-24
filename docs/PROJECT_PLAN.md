# foghorn Project Plan

Active roadmap — what's in flight, queued, and deferred. Shipped work lives in [SHIPPED.md](SHIPPED.md) so this file stays the dense daily read.

Priority tiers used below:

- **P0** — fixes active correctness issues or unblocks high-value work
- **P1** — meaningfully improves practical usefulness
- **P2** — valuable enhancement, can wait

---

## Architecture

Two-package monorepo. `backend/` is Python 3.11+, FastAPI for the HTTP surface, stdlib `sqlite3` for storage, with per-venue scrapers in `backend/scrapers/`. `frontend/` is Next.js 16 + TypeScript + Tailwind.

The data lifecycle is **scrape → normalize → persist → serve → render**:

1. Per-venue scrapers fetch and parse HTML (or `.ics`, etc.), return typed `ScrapedShow` records. Standalone-runnable for debugging.
2. An ingest pipeline normalizes performer names (display + canonical forms), resolves timezones, and dedupes against existing rows using the natural key `(venue_id, start_local_date, start_local_time, headliner_canonical)`.
3. The repository layer persists normalized shows to SQLite, preserving `source_url` + `scraped_at` for provenance.
4. FastAPI serves filtered queries (date range, region, performer search, watchlist matches).
5. The Next.js frontend renders the calendar with filter and search UI; server components fetch from the API, client components handle interactivity.

A daily scheduled scrape refreshes the data. The scheduler runs in-process (APScheduler) for now; if/when we split into a separate worker, it moves to cron or a systemd timer.

See `AGENTS.md` → "Project Shape" / "Architecture Debugging Map" / "Conventions" for the operational details.

## Key risks and mitigations

- **Venue site fragility.** Venues change their markup without warning; scrapers break silently. *Mitigation:* every scraper is independently runnable, returns typed output, and writes a `scraped_at` + `source_url` per show; the ingest pipeline logs per-venue counts so a venue that "suddenly has zero shows" is immediately visible. Phase 2.3 ships a scrape-health check surface.
- **Performer-name matching is fuzzy.** "Joshua Redman Quartet" vs. "Joshua Redman" vs. "Redman, Joshua" — the watchlist needs to match meaningfully without false positives. *Mitigation:* store `display_name` (original) + `canonical_name` (normalized) separately; start with normalized substring match, escalate to token-based matching if false negatives become a problem.
- **Anti-scraping pushback.** Daily polite scraping is unlikely to draw fire, but venues running aggressive WAFs (Cloudflare bot challenges, JS-rendered calendars) can require `playwright` or block outright. *Realized risk:* SFJAZZ blocks every plain HTTP client behind a Cloudflare managed challenge — deferred to the Deferred / still-outstanding list, Phase 2.1 pivoted to Bird & Beckett's `.ics` feed. *Mitigation going forward:* keep the per-venue parser interface flexible enough that a venue can swap from `httpx`+`bs4` to `playwright` (or to a `.ics` parser, RSS, JSON-LD, etc.) without touching the ingest layer; document blocked venues here with the failure mode.
- **Scope creep into "the everything music app".** Travel ETAs, alerts, multi-user accounts, an iOS app — all defensible adds, all distractions from the jazz-venues MVP. *Mitigation:* `Deferred Workstream` in `AGENTS.md` is the explicit holding pen; new feature ideas land there until the current phase ships.

---

## Shipped

Full chronological history lives in [SHIPPED.md](SHIPPED.md). Recently shipped: Phase 1.2 — data model + ingest scaffolding (May 2026), see [SHIPPED.md](SHIPPED.md#data-model-and-ingest-scaffolding-phase-12-may-2026).

When a roadmap item ships, the agent that lands it appends the as-shipped narrative to SHIPPED.md and collapses the inline status block in the Forward roadmap below to a one-line `✅ Shipped` reference with an anchor link. Structural reorganization and periodic compaction of these docs is the PM thread's responsibility, not the shipping agent's.

---

## In flight

**Phase 2.1 — Bird & Beckett end-to-end pilot** ([#6](https://github.com/diegoSQK/foghorn/issues/6)). Originally scoped to SFJAZZ; pivoted to Bird & Beckett after SFJAZZ proved Cloudflare-blocked (see [#4 pivot comment](https://github.com/diegoSQK/foghorn/issues/4#issuecomment-4526998270)). This ticket carries the full Phase 2.1 deliverable: scraper registry, ingest wiring, `GET /api/shows`, the minimal frontend list page, and the `make scrape` / `make backend-run` / `make frontend-run` targets — with Bird & Beckett (public Google Calendar `.ics`) as the pilot venue rather than SFJAZZ. Coding agent claimed.

---

## Forward roadmap

### Phase 1 — Scaffolding

Stand up the monorepo skeleton, the CI gate, and the minimal data model so subsequent phases can ship features instead of plumbing.

#### 1.1 Repo skeleton + CI gate (P1) ✅

Shipped May 2026 — see [Repo skeleton + CI gate](SHIPPED.md#repo-skeleton-and-ci-gate-phase-11-may-2026). Storage choice landed as stdlib `sqlite3` (not an ORM). `create-next-app@latest` now resolves to Next.js 16 (not 15); doc references reconciled by a follow-up PM pass.

#### 1.2 Data model + ingest scaffolding (P1) ✅

Shipped May 2026 — see [Data model + ingest scaffolding](SHIPPED.md#data-model-and-ingest-scaffolding-phase-12-may-2026). SQLite schema (venues/performers/shows/show_performers), conn-injected typed repo layer, `ingest_scraped_shows` with unicode-aware canonicalization + tz→UTC, and the four-venue seed. No scraping yet — Phase 2.1 wires the first scraper into this.

### Phase 2 — Three jazz venues end-to-end

Ship the three-jazz-venue MVP: one scraper per venue, daily refresh, list view in the frontend. This is the "is foghorn useful yet" milestone. SFJAZZ was originally part of the set but blocked behind Cloudflare; revisit deferred (see Deferred / still-outstanding).

#### 2.1 First scraper end-to-end: Bird & Beckett (P1)

Originally scoped to SFJAZZ; pivoted to Bird & Beckett after SFJAZZ proved Cloudflare-blocked (the original [#4](https://github.com/diegoSQK/foghorn/issues/4) ticket was dropped — see its [pivot comment](https://github.com/diegoSQK/foghorn/issues/4#issuecomment-4526998270)). Bird & Beckett publishes a public Google Calendar `.ics` — clean, structured, no anti-bot challenges. The 2.1 deliverable is unchanged: implement the scraper, the scraper registry, the ingest wiring, the `GET /api/shows` endpoint, the minimal `frontend/app/page.tsx` flat-list view, and `make scrape` / `make backend-run` / `make frontend-run` targets. Tracked under [#6](https://github.com/diegoSQK/foghorn/issues/6) (originally a sibling parser ticket; promoted to the pilot).

#### 2.2 Two more jazz scrapers (P1)

`backend/scrapers/keys_jazz_bistro.py` ([#5](https://github.com/diegoSQK/foghorn/issues/5)) and `mr_tipples.py` ([#7](https://github.com/diegoSQK/foghorn/issues/7)). Each is its own issue so they can be claimed independently. Each must implement the same `ScrapedShow` interface and be CLI-runnable per the scraper convention. Frontend list page now shows all three venues' shows interleaved by date. (Bird & Beckett shipped as part of 2.1; SFJAZZ deferred.)

✅ **Keys Jazz Bistro (#5) shipped May 2026** — see [Keys Jazz Bistro scraper](SHIPPED.md#keys-jazz-bistro-scraper-phase-22a-may-2026). HTML scrape of the venue's WordPress `/upcoming-shows/` page; plain `httpx`+`bs4`, no playwright. Collapse this 2.2 entry to a single `✅ Shipped` line once Mr. Tipple's (#7) lands.

#### 2.3 Daily refresh scheduler (P1)

Tracked under [#8](https://github.com/diegoSQK/foghorn/issues/8). Wire APScheduler into the backend process so all configured scrapers run once nightly (target: 04:00 PT, low traffic). Log per-venue counts + duration. Surface a `GET /api/health/scrape` endpoint that returns `last_run_at`, per-venue counts, and any per-venue errors from the last run. Phase 2 done = open the page tomorrow morning and see fresh shows across all three jazz venues.

### Phase 3 — Filtering & search

Make the calendar useful for "what should I do this Friday."

#### 3.1 Date-range and venue filters (P1)

Frontend: date range picker (default = next 14 days), venue checkboxes, "tonight / this weekend / next 7 days" quick selectors. Backend: `GET /api/shows?from=&to=&venues=` query params.

#### 3.2 Region / neighborhood filter (P1)

Tag each venue with `neighborhood` (already in the seed) and `region` (`SF`, `East Bay`, `Peninsula`, `South Bay`). Frontend exposes region as a top-level toggle; neighborhood as a secondary filter when a region is selected.

#### 3.3 Free-text performer search (P1)

Backend: `GET /api/shows?performer_query=joshua+redman` — matches against `canonical_name` of any performer on the bill (headliner or support). Substring match to start; consider postgres FTS or sqlite FTS5 later if relevance becomes an issue. Frontend: search box prominent at the top of the page.

### Phase 4 — Watchlist

The friend-tracking surface — the headline feature for the primary user.

#### 4.1 Watchlist data model + UI (P1)

Single-user / local watchlist (no accounts yet): a `watchlist` table keyed on `canonical_name`. UI: a dedicated `/watchlist` route that lists upcoming shows where any performer matches a watchlist entry. From a show card on the main page, "add headliner to watchlist" and "add support to watchlist" actions. Persisted locally in the SQLite DB — no auth, single-tenant assumption documented.

#### 4.2 Watchlist digest (P2)

A `/api/watchlist/digest` endpoint that returns next-N upcoming watchlist matches, suitable for a future cron-emailed digest. Email delivery itself stays deferred.

### Phase 5 — Venue expansion

Add the rock / indie venues so foghorn covers both Diego's jazz-leaning use case and the broader Bay indie scene.

#### 5.1 Rock / indie venue batch (P2)

Hand-rolled scrapers for Bottom of the Hill, The Independent, The Chapel. Same pattern as Phase 2; one ticket per venue.

#### 5.2 East Bay expansion (P2)

Cornerstone Berkeley, Starline Social Club, The New Parish, Yoshi's (jazz). Same pattern.

### Phase 6 — LLM-assisted scraping (deferred until Phase 5 is real)

Once we've got 10+ hand-rolled scrapers, generalize: a pipeline that fetches a venue's page and uses an LLM to extract `ScrapedShow` records, with per-venue overrides where the LLM is unreliable. Lets us add long-tail venues without per-venue parser work. Cost / reliability characteristics measured against the hand-rolled baseline.

---

## Deferred / still-outstanding

- **SFJAZZ scraper.** Originally the Phase 2.1 pilot. The calendar sits behind a Cloudflare managed challenge that 403s every plain HTTP client (polite `foghorn-scraper` UA and a browser UA both); the sitemap host in `robots.txt` 404s. Cloudflare-bypass was explicitly out of scope for the original ticket. **Unblock condition:** willingness to take on per-venue Playwright (headless browser) complexity, or discovery of a cleaner SFJAZZ data feed (sitemap, third-party calendar, public API). File a fresh ticket when unblocked; the dropped original is [#4](https://github.com/diegoSQK/foghorn/issues/4).
- **Travel-time ETAs** from home/work/studio addresses. Original requirement; deferred until the core calendar is solid. Map-provider decision (Google / Mapbox / ORS / coarse neighborhood table) deferred with it. **Unblock condition:** the core calendar is in regular use and "how long will it take to get there" is actually the friction point.
- **Hosting / deployment.** Runs locally through Phases 1–5 minimum. **Unblock condition:** ready to share with friends, or want to view from a phone away from the laptop. Decision between Vercel + Python host vs. single VPS deferred to that point.
- **Multi-user accounts.** Watchlist is single-tenant for now. **Unblock condition:** the app goes public (Phase 9+).
- **Alerts / notifications.** Email or push when a watchlist performer is announced or imminent. **Unblock condition:** watchlist proves valuable as a manual surface and the daily-check pattern feels like friction.
- **Postgres.** SQLite suffices at single-user scale through Phase 5. **Unblock condition:** hosting platform demands it, or the dataset / query patterns outgrow SQLite.

---

## Suggested sequencing for future releases

1. **Phase 1** — scaffolding. Foundation; nothing depends on it being done well, but everything depends on it being done at all. ✅
2. **Phase 2** — three jazz venues end-to-end. The first "this is useful" milestone. Cut a `v0.1.0` release tag at the end of this phase.
3. **Phase 3** — filtering & search. Turns the raw calendar into something you'd actually open on a Friday afternoon.
4. **Phase 4** — watchlist. Headline feature for the primary use case. Likely `v0.2.0` cut here.
5. **Phase 5** — venue expansion. Breadth without changing the model. Cut `v0.3.0` when the venue set feels comprehensive enough for personal use.
6. **Phase 6** — LLM-assisted scraping. Scaling lever, picked up once breadth is the bottleneck.
7. **Deferred items revisited.** SFJAZZ, Travel ETAs, hosting, accounts — addressed when their unblock conditions are met, not on a fixed schedule.

---

## Out of scope

- **Ticketing / purchase flow.** foghorn links out to venue ticket pages; it doesn't intermediate purchases.
- **User reviews / ratings / social features.** Not a social product.
- **Festival aggregation.** Multi-day festivals (Outside Lands, Hardly Strictly, etc.) are a different content shape; if they ever land, it's as a separate surface, not bolted onto the venue calendar.
- **Bands' own-website scraping.** Venue calendars are the source of truth. Performer-side data comes from what the venue listed, not from scraping every band's site.
- **Non-music events.** Comedy, theater, spoken word — if a venue's calendar includes them, the scraper filters them out unless they're explicitly tagged music.
