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
- **Performer-name matching is fuzzy.** "Joshua Redman Quartet" vs. "Joshua Redman" vs. "Redman, Joshua" — the watchlist needs to match meaningfully without false positives. *Mitigation:* store `display_name` (original) + `canonical_name` (normalized) separately; substring → token-bag (shipped in 4.1, shared between watchlist + search); FTS5/trigram escalation deferred until typo tolerance bites.
- **Anti-scraping pushback.** Daily polite scraping is unlikely to draw fire, but venues running aggressive WAFs (Cloudflare bot challenges, JS-rendered calendars) can require `playwright` or block outright. *Realized risk:* SFJAZZ blocks every plain HTTP client behind a Cloudflare managed challenge — deferred to the Deferred / still-outstanding list, Phase 2.1 pivoted to Bird & Beckett's `.ics` feed. *Mitigation going forward:* keep the per-venue parser interface flexible enough that a venue can swap from `httpx`+`bs4` to `playwright` (or to a `.ics` parser, RSS, JSON-LD, etc.) without touching the ingest layer; document blocked venues here with the failure mode.
- **Aggregator-ingest constraints (new finding, May 2026 spike).** The two clean global aggregator APIs (Songkick, Bandsintown) are both ToS-bars-scraping *and* coverage-skewed away from small jazz rooms; DoTheBay is engineering-easy but ToS-blocked without permission. **Aggregator ingest cannot replace per-venue scraping** for foghorn's wheelhouse — only narrowly augment it (Bay Improviser is the one viable additive source). The real scaling lever remains Phase 6 (LLM-assisted per-venue scraping), not aggregators. See [aggregator spike SHIPPED entry](SHIPPED.md#aggregator-evaluation-spike-may-2026) and [`spikes/aggregator-evaluation/RECOMMENDATION.md`](spikes/aggregator-evaluation/RECOMMENDATION.md).
- **Scope creep into "the everything music app".** Travel ETAs, alerts, multi-user accounts, an iOS app — all defensible adds, all distractions from the jazz-venues MVP. *Mitigation:* `Deferred Workstream` in `AGENTS.md` is the explicit holding pen; new feature ideas land there until the current phase ships.

---

## Shipped

Full chronological history lives in [SHIPPED.md](SHIPPED.md); version cut-points live in [CHANGELOG.md](CHANGELOG.md). Recently shipped: the venue-expansion batch — 23 new scrapers (3 → 26 venues, 1,192 shows) + the Phase 7.1 genre facet (July 2026), see [SHIPPED.md](SHIPPED.md#venue-expansion-batch-23-new-scrapers--genre-facet-july-2026). **v0.2.0** cut 2026-05-24 — see [CHANGELOG.md](CHANGELOG.md#v020--2026-05-24). (Previous: **v0.1.0** see [CHANGELOG.md](CHANGELOG.md#v010--2026-05-24).)

When a roadmap item ships, the agent that lands it appends the as-shipped narrative to SHIPPED.md and collapses the inline status block in the Forward roadmap below to a one-line `✅ Shipped` reference with an anchor link. Structural reorganization and periodic compaction of these docs is the PM thread's responsibility, not the shipping agent's.

---

## In flight

*Nothing in flight. The July 2026 venue-expansion batch (a user-directed feature-branch push) delivered Phase 5's intent and beyond — 23 new venues across SF, East Bay, and the Peninsula — plus Phase 7.1 (genre). Venue batch 2 shipped July 2026 (UC Theatre, Bimbo's, Neck of the Woods, Warfield, August Hall, Thee Stork Club — 35 venues total); venue batch 3 (Club Deluxe, Club Fox) shipped July 2026 — 37 venues; The New Parish remains blocked on empty TicketWeb inventory (re-verified 2026-07-07 across its site, both TicketWeb venue ids, and aggregators — endpoint pre-solved; re-verified still empty 2026-07-18, recheck ~August) plus a Ticketmaster Discovery API spike for the Live Nation rooms (Fillmore, Regency); see the venue-expansion SHIPPED entry for the per-platform scraping playbook.*

### Pending strategic decisions

- **Aggregator-ingest — SHIPPED July 2026** (see [SHIPPED entry](SHIPPED.md#bay-improviser-aggregator-ingest-july-2026)) under the decided quarantine-with-flag + watchlist-bypass posture. Aggregator-discovered venues are auto-accepted as `venues.source='aggregator'` rows but default-hidden from the main UI (venue chips, show list) behind a "creative-music long tail" toggle; watchlist matching always looks inside the quarantine, so a followed artist's gig at an untracked space surfaces regardless of the toggle. Bay Improviser ingest is now unblocked — file when next in line. Implementation notes: reuse the `venues.source` machinery from manual events; BI's free-text billings need the token-match duplicate warning specced for Phase 8 (shared machinery); BI publishes only ~5 weeks out, so poll on the nightly schedule. (Original spike context: **Aggregator-ingest discovery posture.** The aggregator-evaluation spike ([SHIPPED entry](SHIPPED.md#aggregator-evaluation-spike-may-2026), [RECOMMENDATION memo](spikes/aggregator-evaluation/RECOMMENDATION.md)) recommends adding **Bay Improviser** as one new ingest source to augment Phase 5. Filing the ticket is on hold pending a product decision: do we auto-accept aggregator-discovered venues (broad coverage, messier data, interacts with the Phase 3.2 region/neighborhood facets), maintain a curated allow-list (clean data, loses the long-tail discovery value), or quarantine-with-flag (auto-accept but default-hide from main UI, opt-in via a separate "creative music long tail" toggle)? PM thread in conversation with Diego. Once settled, Bay Improviser ingest likely lands alongside Phase 5 — see ["Suggested sequencing"](#suggested-sequencing-for-future-releases) below.)

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

#### 2.1 First scraper end-to-end: Bird & Beckett (P1) ✅

Shipped May 2026 — see [Phase 2.1 end-to-end pilot via Bird and Beckett](SHIPPED.md#phase-21-end-to-end-pilot-via-bird-and-beckett-may-2026). Bird & Beckett `.ics` feed + scraper registry + ingest wiring + `GET /api/shows` + minimal frontend list page + `make scrape` / `make backend-run` / `make frontend-run` targets. Pilot re-homed from SFJAZZ → Bird & Beckett after the SFJAZZ Cloudflare block (the original [#4](https://github.com/diegoSQK/foghorn/issues/4) ticket was dropped; SFJAZZ deferred).

#### 2.2 Two more jazz scrapers (P1) ✅

Shipped May 2026. **Keys Jazz Bistro (#5)** — HTML scrape of the venue's WordPress `/upcoming-shows/` page (plain `httpx`+`bs4`), see [Keys Jazz Bistro scraper](SHIPPED.md#keys-jazz-bistro-scraper-phase-22a-may-2026). **Mr. Tipple's (#7)** — Tribe Events REST API (also fills `ticket_url` + `price_text`), see [Mr. Tipple's scraper via the Tribe Events API](SHIPPED.md#mr-tipples-scraper-via-the-tribe-events-api-may-2026). (Bird & Beckett shipped as the 2.1 pilot; SFJAZZ deferred.) All three venues now interleave by date on the frontend.

#### 2.3 Daily refresh scheduler (P1) ✅

Shipped May 2026 — see [Daily refresh scheduler and scrape-health endpoint](SHIPPED.md#daily-refresh-scheduler-and-scrape-health-endpoint-phase-23-may-2026). APScheduler `BackgroundScheduler` runs all registered scrapers nightly at 04:00 PT; `make scrape` shares the same `run_scrape` unit so manual runs are recorded too. `GET /api/health/scrape` surfaces the last run's per-venue counts + errors (503 until the first run). **Phase 2 is complete (2.1 + 2.2 + 2.3) — cut as `v0.1.0` on 2026-05-24** ([CHANGELOG](CHANGELOG.md#v010--2026-05-24)).

### Phase 3 — Filtering & search

All three dimensions shipped — the calendar is now usable for "what should I do this Friday." **Phase 3 is complete and rolled into `v0.2.0`** ([CHANGELOG](CHANGELOG.md#v020--2026-05-24)).

#### 3.1 Date-range + venue filters + URL-driven filter framework (P1) ✅

Shipped May 2026 — see [Date and venue filters, URL-driven framework](SHIPPED.md#date-and-venue-filters-url-driven-framework-phase-31-may-2026). URL search params are the single source of truth; the server component reads them and re-fetches on navigation (shareable/bookmarkable, back-button works), and `FilterBar` (client) writes changes back via `router.push`. Native date inputs (apply-on-change, no picker lib), venue checkboxes (from the new `GET /api/venues`), and quick chips (`Tonight`/`This weekend`/`Next 7 days` + server-side `Early`/`Late` via `?time_of_day=`). Backend adds `?venues=` (comma slugs) + `?time_of_day=`. **3.2 and 3.3 inherit this framework.**

#### 3.2 Region / neighborhood filter (P1) ✅

Shipped May 2026 — see [Region and neighborhood filter](SHIPPED.md#region-and-neighborhood-filter-phase-32-may-2026). `?region=` / `?neighborhood=` on `GET /api/shows` (case-insensitive neighborhood; AND-stack with existing filters), and a `LocationFilter.tsx` with region chips (non-SF greyed "(soon)") + a region-scoped neighborhood dropdown. Region/venue filters independent (AND, no cascade). Mostly framework-complete until Phase 5 brings non-SF venues — each region chip activates as its first venue ships.

#### 3.3 Free-text performer search (P1) ✅

Shipped May 2026 — see [Free-text performer search](SHIPPED.md#free-text-performer-search-phase-33-may-2026). `GET /api/shows?performer_query=` canonicalizes the input and matches headliner or support. Frontend: a prominent debounced (~300ms) search box (`PerformerSearch.tsx`) wired into the URL-driven framework. **Matching upgraded substring → token-bag as part of 4.1** (`repo/performer_match.py`, shared with the watchlist); FTS5 still deferred until relevance demands it.

### Phase 4 — Watchlist

The friend-tracking surface — the headline feature for the primary user. **Phase 4 is complete and rolled into `v0.2.0`** ([CHANGELOG](CHANGELOG.md#v020--2026-05-24)).

#### 4.1 Watchlist data model + UI (P1) ✅

Shipped May 2026 — see [Watchlist data model, UI, and token-based matching](SHIPPED.md#watchlist-data-model-ui-and-token-based-matching-phase-41-may-2026). Single-tenant `watchlist` table keyed on `canonical_name`; `GET/POST/DELETE /api/watchlist` + `?watchlist=true` filter on `/api/shows` (empty watchlist → `[]`). Token-bag matching (`repo/performer_match.py`) is now the shared performer matcher (also powers 3.3). Frontend: `+`/`✓` add buttons on every performer, a `/watchlist` route (reusing FilterBar), and a `Watchlist (N)` nav count. CORS added for the client mutations.

#### 4.2 Watchlist digest (P2) ✅

Shipped May 2026 — see [Watchlist digest endpoint](SHIPPED.md#watchlist-digest-endpoint-phase-42-may-2026). `GET /api/watchlist/digest?days=14&limit=20` returns the next-N upcoming watchlist matches (each row + `watchlist_matches`), reusing the `?watchlist=true` filter. Read-only; email/push delivery stays deferred.

### Phase 5 — Venue expansion

Add the rock / indie venues so foghorn covers both Diego's jazz-leaning use case and the broader Bay indie scene. **Largely delivered by the July 2026 venue-expansion batch** — see [SHIPPED.md](SHIPPED.md#venue-expansion-batch-23-new-scrapers--genre-facet-july-2026) — which shipped 23 venues (SF: Black Cat, Ocean Ale House, Boom Boom Room, Madrone Art Bar, Bottom of the Hill, Rickshaw Stop, Kilowatt, The Knockout, The Independent, Cafe du Nord, GAMH, The Chapel, DNA Lounge; East Bay: Yoshi's, California Jazz Conservatory, Ivy Room, 924 Gilman, Natural Grocery Annex, Cornerstone, Fox Theater, Greek Theatre, The Back Room; Peninsula: Guild Theatre) and pulled in Phase 7.1 (genre) as predicted. Bay Improviser ingest still awaits the discovery-posture decision (see In flight → "Pending strategic decisions").

#### 5.1 Rock / indie venue batch (P2) ✅

Bottom of the Hill, The Independent, The Chapel all shipped (July 2026 batch), plus Rickshaw Stop, Kilowatt, The Knockout, Cafe du Nord, GAMH, DNA Lounge beyond the original scope.

#### 5.2 East Bay expansion (P2) ✅

Yoshi's, Cornerstone Berkeley, The New Parish → shipped except New Parish (TicketWeb widget API — in the next-block leftovers); Starline Social Club appears closed (July 2026 sweep). Also shipped beyond scope: CJC, Ivy Room, 924 Gilman, Natural Grocery Annex, Fox Theater, Greek Theatre, The Back Room.

### Phase 8 — Mailing-list ingest — stage 1 ✅ / stage 2 parked

Stage 1 shipped July 2026 — see [SHIPPED entry](SHIPPED.md#mailing-list-ingest-stage-1-phase-8-july-2026). Stage 2 (LLM extraction in the same review queue): **decided against for now (July 2026)** — same call as 7.4's stage 2; revisit only if Diego reopens it.

<!-- original design:

Artists in the creative-music scene (e.g. the two currently-followed ones) announce gigs primarily via their mailing lists — often the *only* machine-reachable source (Dillon Vado has no scrapeable footprint at all). Design agreed with Diego:

- **Mail in:** Gmail filter auto-labels artist newsletters; foghorn polls the label over IMAP (app password via `FOGHORN_IMAP_*`), on the existing scheduler. Local-first — no public endpoint; inbound-webhook services become an option only post-hosting.
- **Review queue is the write gate:** emails parse into a `pending_events` table and a small "Inbox" UI (approve/edit/reject); approving creates a manual event with the email as provenance. Nothing enters `shows` unapproved — regardless of extractor.
- **Stage 1 (deterministic):** sender→artist mapping (artist ≈ headliner), venue by scanning text for known venue names, date/time regexes; unparseable emails still queue as raw text with the artist prefilled.
- **Stage 2 (optional LLM extraction, same queue):** an LLM fills drafts the rules fumble. Human approval keeps it out of ingest-of-record — the contained pilot for the Phase 6 question. Gated on the same LLM-dependency decision as 7.4's stage 2.
- **Dedup warning:** email-approved gigs and later venue-scraped ones won't collapse on the natural key when billing strings differ; the review UI must warn on token-match against existing shows at that venue+date.

Scope: Stage 1 ≈ one focused session. **Unblock condition:** none — ready to build; file the ticket when it's next in line. -->

### Phase 9 — Venue watchlist (P2) ✅

Shipped July 2026 — see [Venue watchlist](SHIPPED.md#venue-watchlist-phase-9-july-2026). Digest inclusion + quarantine-promotion interaction are follow-ons.

<!-- original design:

Follow *venues* the way the watchlist follows performers — "never miss what the Back Room books." Single-tenant `watched_venues` table (venue_slug PK, added_at, notes) mirroring the performer watchlist; `GET/POST/DELETE` endpoints + a `?venue_watchlist=true` filter on `/api/shows`; a pin/star affordance on venue names (show rows + venue checklist) and a separate page (e.g. `/venues`) rendering pinned venues' upcoming shows through the existing FilterBar/ShowList. Two synergies: the watchlist digest should take a param to include watched-venue shows, and pinning a quarantined aggregator venue naturally promotes it into the main UI (interaction with the quarantine-with-flag posture above). **Unblock condition:** none — ready to build. -->

### Phase 6 — LLM-assisted scraping (deferred until Phase 5 is real)

Once we've got 10+ hand-rolled scrapers, generalize: a pipeline that fetches a venue's page and uses an LLM to extract `ScrapedShow` records, with per-venue overrides where the LLM is unreliable. Lets us add long-tail venues without per-venue parser work. Cost / reliability characteristics measured against the hand-rolled baseline. **Note from the aggregator-evaluation spike (May 2026):** this remains the real scaling lever — aggregator ingest does *not* short-cut Phase 6 the way that spike hoped to test.

### Phase 7 — Metadata & tagging (cross-cutting workstream)

Extend the foundational tagging skeleton (performers, region, neighborhood — all shipped in Phases 1–3) into a unified metadata / faceting layer. Each sub-item ships when its prerequisite conditions hold; sequencing is interleaved with Phases 4–6 rather than strictly after them.

What's already in place that this builds on: performers are first-class entities in the schema (Phase 1.2), and the `show_performers` join captures headliner + support roles. Region + neighborhood are venue-level tags filterable via Phase 3.2. Phase 4's watchlist is the first user-facing surface that *reads* the performer-tagging layer for filtering. The sub-items below are the natural extensions of that pattern.

#### 7.1 Venue-default genre (P2) ✅

Shipped July 2026 with the venue-expansion batch — see [SHIPPED entry](SHIPPED.md#venue-expansion-batch-23-new-scrapers--genre-facet-july-2026). Landed as a single `venues.genre` TEXT column (not a join — no venue has needed multi-genre yet) with the first additive-column migration guard, `?genre=` on `GET /api/shows`, and a data-driven genre chip row.

#### 7.2 Per-show genre override (P2) ✅

Shipped July 2026 (venue-expansion branch). `shows.genre_override` populated from sources that publish per-event genre (the SeeTickets venues; Dice tags are a future add) and normalized to the coarse vocabulary at ingest; manual entries keep unmapped genres verbatim. `?genre=` resolves `COALESCE(override, venue default)`; rows render a genre badge. Artist-level genre remains 7.4.

#### 7.3 User-defined tags (P2)

Personal annotations on shows (`must-see`, `skip`, `saw last year`, `Diego's crew is on the bill`). Schema: `user_tags(user_id, show_id, tag)`, single-user shape consistent with Phase 4's watchlist. UI: per-show "add tag" affordance; tags surface as chips; filterable like other facets. **Unblock condition:** Phase 4 watchlist has proven out the single-user per-show metadata pattern. Likely the second user-facing tagging surface after the watchlist.

#### 7.5 Performer origin: local/touring (P1) ✅

Shipped July 2026 — see [Performer origin tagging v1](SHIPPED.md#performer-origin-tagging-v1-localtouring-july-2026). Performer-level `origin` tag with a conservative heuristic bootstrap (`make tag-origins`), permanent manual overrides, `?origin=` any-performer filter, and "(likely)" chips + local badges. Re-run the CLI as history accumulates; escalate to an LLM pass under 7.4 when heuristic coverage plateaus.

#### 7.4 Performer-level metadata — deterministic stage ✅ / LLM stage deferred

**Stage 1 (deterministic) shipped July 2026** (venue-expansion branch): `performers.genre` + `genre_source` with a unanimous-evidence bootstrap (`make tag-genres`) over per-show genre overrides, venue leans, and performer-name keywords; genre resolution chain is show override > headliner performer genre > venue default. First run tagged 353/1,368 performers; manual corrections via `PUT /api/performers/{canonical}/genre` are permanent. **Stage 2 (LLM pass for the remaining ~75%): DECIDED AGAINST for now (July 2026)** — Diego declined the LLM dependency in the enrichment tier (it would not enter ingest-of-record or serving; tags would carry `genre_source='llm'` provenance and be bulk-revocable). The deterministic layer is the validation baseline if it proceeds. Unlike previously assumed, stage 2 does NOT depend on Phase 6 — it needs only an API key + a batching CLI.

#### 7.4b (formerly 7.4) LLM-inferred metadata (P2, depends on Phase 6)

Performer-level genre / instrumentation / mood inferred by an LLM from the bill + venue + any extracted text. Hand-curated genre tags (7.1–7.2) and the deterministic scraping baseline are the validation reference. Same doctrine as Phase 6 LLM-assisted scraping: defer until the deterministic version proves out, then layer this on as a scaling lever.

---

## Deferred / still-outstanding

- **SFJAZZ scraper.** Originally the Phase 2.1 pilot. The calendar sits behind a Cloudflare managed challenge that 403s every plain HTTP client (polite `foghorn-scraper` UA and a browser UA both); the sitemap host in `robots.txt` 404s. Cloudflare-bypass was explicitly out of scope for the original ticket. **Unblock condition:** willingness to take on per-venue Playwright (headless browser) complexity, or discovery of a cleaner SFJAZZ data feed (sitemap, third-party calendar, public API). File a fresh ticket when unblocked; the dropped original is [#4](https://github.com/diegoSQK/foghorn/issues/4).
- **For The Record scraper** (SF Cow Hollow hi-fi listening bar). One-page Squarespace site with no events collection; all programming is Instagram-only (@fortherecordsf). **Unblock condition:** the venue publishes a web calendar, or an Instagram-ingest capability is deliberately taken on.
- **Little Hill Lounge scraper** (El Cerrito). ✅ Shipped July 2026 via on-device Apple Vision OCR over the monthly flyer JPEG — see [SHIPPED entry](SHIPPED.md#little-hill-lounge-via-on-device-ocr--the-flyer-venue-pattern-july-2026). The OCR pattern is reusable for other flyer-only venues (Monkey House is the next candidate, quality check first).
- **Long-tail audit leftovers (July 2026).** The audit ([SHIPPED entry](SHIPPED.md#long-tail-audit--four-scraper-promotions-dresher-the-lab-gray-area-mills-littlefield-july-2026)) is now nearly worked off: the four easy wins, Kuumbwa + Santa Cruz region, and batch 4 (Indexical, Meyhouse, Make-Out Room, Poor House Bistro — [SHIPPED entry](SHIPPED.md#venue-batch-4-indexical-meyhouse-jazz-make-out-room-poor-house-bistro-july-2026)) all shipped; Arc Gallery declined on data. Still open: **The Monkey House** (OCR pattern ready, but Wix 429s all fetches from this IP as of 2026-07-18 — retry gently on a later pass); **ATA** (days-ahead posting horizon); **Peacock Lounge** and **Shapeshifters Cinema** (hand-edited HTML, low volume); **Santa Cruz Civic** (403s plain fetch — headless appetite); and a **human check on Temescal Arts Center** (Yelp says closed June 2026; BI still lists shows). **Unblock conditions:** explicit effort appetite per venue; a cooled-off Wix for Monkey House.
- **Red Poppy Art House scraper** (SF Mission). Runs Tribe Events — the REST endpoint answers validly — but publishes zero events (archive renders 2011-era imports); dormant as a calendar, absent from Bay Improviser too. **Unblock condition:** the venue resumes publishing events (endpoint pre-solved; recheck occasionally or on a Mission dogfooding pass).
- **HopMonk Tavern Novato scraper.** Squarespace hub with no events collection; the real calendar lives at wl.eventim.us/HopMonkNovato, which 403s every plain HTTP client behind a JS bot challenge (same class as SFJAZZ's Cloudflare block). **Unblock condition:** headless-browser appetite or an Eventim feed arrangement.
- **Poor House Bistro scraper** (San Jose blues). ✅ Shipped July 2026 via the OCR pattern's month-grid flavor — see [SHIPPED entry](SHIPPED.md#venue-batch-4-indexical-meyhouse-jazz-make-out-room-poor-house-bistro-july-2026). (Café Pink House and Art Boutiki: confirmed CLOSED July 2026 — struck from candidate lists, do not re-sweep.)
- **DoTheBay ingest.** Spike-validated (May 2026) as engineering-ready (open JSON API, no anti-bot, ~87 music venues / 239 shows per sample week) but blocked by ToS — not a ticket, a permission/feed conversation with DoStuff/Noise Pop. **Unblock condition:** a permission or licensed feed arrangement.
- **Travel-time ETAs** from home/work/studio addresses. Original requirement; deferred until the core calendar is solid. Map-provider decision (Google / Mapbox / ORS / coarse neighborhood table) deferred with it. **Unblock condition:** the core calendar is in regular use and "how long will it take to get there" is actually the friction point.
- **Hosting / deployment.** Runs locally through Phases 1–5 minimum. **Unblock condition:** ready to share with friends, or want to view from a phone away from the laptop. Decision between Vercel + Python host vs. single VPS deferred to that point.
- **Multi-user accounts.** Watchlist + user tags are single-tenant for now. **Unblock condition:** the app goes public.
- **Alerts / notifications.** Email or push when a watchlist performer is announced or imminent. 4.2's digest endpoint produces the data; delivery itself is the deferred part. **Unblock condition:** watchlist proves valuable as a manual surface and the daily-check pattern feels like friction.
- **Postgres.** SQLite suffices at single-user scale through Phase 5. **Unblock condition:** hosting platform demands it, or the dataset / query patterns outgrow SQLite.
- **CORS tighten.** Currently `allow_origins=["*"]` for local-first dev convenience; `FOGHORN_CORS_ORIGINS` tightens. **Unblock condition:** the hosting decision lands and the app is reachable from the public internet.

---

## Suggested sequencing for future releases

1. **Phase 1** — scaffolding. Foundation; nothing depends on it being done well, but everything depends on it being done at all. ✅
2. **Phase 2** — three jazz venues end-to-end. The first "this is useful" milestone. ✅ Cut as **v0.1.0** on 2026-05-24.
3. **Phase 3 + Phase 4** — filtering & search + watchlist. The "find + follow" surface. ✅ Cut as **v0.2.0** on 2026-05-24.
4. **Phase 5** — venue expansion (rock/indie + East Bay). Breadth without changing the model. Likely pulls in **Phase 7.1** (venue-default genre) as venue diversity makes the filter meaningful, and **Bay Improviser ingest** if the discovery-posture decision (see In flight) lands in time. Cut `v0.3.0` when the venue set feels comprehensive enough for personal use.
5. **Phase 7.3** (user tags) — likely after Phase 4 lands, when the single-user per-show metadata pattern is proven.
6. **Phase 6** — LLM-assisted scraping. Scaling lever, picked up once breadth is the bottleneck.
7. **Phase 7.4** (LLM-inferred metadata) — pairs with Phase 6 since the LLM infra overlaps.
8. **Deferred items revisited.** SFJAZZ, DoTheBay (permission-gated), Travel ETAs, hosting, accounts — addressed when their unblock conditions are met, not on a fixed schedule.

---

## Out of scope

- **Ticketing / purchase flow.** foghorn links out to venue ticket pages; it doesn't intermediate purchases.
- **User reviews / ratings / social features.** Not a social product.
- **Festival aggregation.** Multi-day festivals (Outside Lands, Hardly Strictly, etc.) are a different content shape; if they ever land, it's as a separate surface, not bolted onto the venue calendar.
- **Bands' own-website scraping.** Venue calendars are the source of truth. Performer-side data comes from what the venue listed, not from scraping every band's site.
- **Non-music events.** Comedy, theater, spoken word — if a venue's calendar includes them, the scraper filters them out unless they're explicitly tagged music.
