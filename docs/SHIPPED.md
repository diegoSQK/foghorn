# foghorn Shipped Work

Chronological record of completed work — what landed, when, and why. Each entry preserves the narrative context that informed the design so it stays available as scar tissue when scoping new work.

`PROJECT_PLAN.md` is the active doc: what's in flight, queued, and deferred. When a new phase/feature ships, its spec moves here and the active doc collapses to a one-line status with a link into this file. Read this file on demand when you need detail on past work; the active doc is the daily read.

Ordering: newest at top. When adding a new entry, insert it at the top of the file. Older entries preserve their original recording order — when reorganizing, prefer "insert at top of recent block" over "deeply reorder existing history."

---

## Mailing-list ingest, stage 1 (Phase 8, July 2026)

The channel for artists whose gigs never reach a scrapeable surface (Dillon
Vado announces exclusively by mailing list). Deterministic — no LLM — with a
**review queue as the write gate**: emails parse into `pending_events`
drafts, and nothing enters `shows` until approved in the new `/inbox` UI.

- **Mail in, two ways:** an IMAP poller (`make mail-poll`; stdlib imaplib,
  read-only, Message-ID-deduped; `FOGHORN_IMAP_*` env, Gmail-label folder
  default "foghorn"; exits with a hint when unconfigured) — and a
  paste-an-email form on /inbox (`POST /api/inbox/ingest`), which makes the
  feature usable with zero configuration.
- **Rules parser** (pure, injected `today`): artist from a hand-maintained
  `mail_senders` map (managed in the UI), venue by scanning for known venue
  names, date/time regexes resolved to the next future occurrence.
  Unparseable emails still queue as raw text with the artist prefilled.
- **/inbox** ("Inbox (N)" in the nav): editable draft cards over the raw
  email, an amber token-match **possible-duplicate warning** (email-approved
  and venue-scraped billings won't collapse on the natural key — the warning
  is the stage-1 answer), Approve (creates the event through the manual-entry
  path, provenance `manual://email/<message_id>`) / Reject. Approved and
  rejected rows are kept as an audit trail.
- Verified end-to-end in a cold-start browser run, which also caught and
  fixed an approve-with-blanked-field bug (client now validates; the API 422
  remains the backstop). 31 new tests.

**Stage 2 (LLM extraction for emails the rules fumble) stays parked** on the
same enrichment-tier decision as 7.4's LLM stage.

## Search + venue-UX arc (July 2026)

Dogfooding fixes from tracking real artists, shipped as small PRs (#39,
#41–#45):

- **Token-prefix search** — "mezz" now matches "mezzacappa" while typing;
  watchlist matching stays whole-token for precision.
- **Follow a performer by name** on /watchlist — a bare "Lisa Mezzacappa"
  entry tracks the person across every billing shape; previously the only
  entry point was the '+' on a venue's verbatim billing string (which, for a
  multi-artist bill, tracks only that exact billing).
- **First-class venue UX**: venue names everywhere link to that venue's
  calendar (/?venues=slug); a "My venues ★" quick chip filters any view to
  followed venues; the 37-checkbox grid was replaced by VenuePicker
  (search-as-you-type, region groups, followed-first with ★s, removable
  selected chips — empty honestly means "all venues"), reused in follow mode
  on /venues; pins soft-refresh the surrounding server-rendered feed; event
  rows gained a "details" link to the event's own page alongside "tickets".

## Bay Improviser aggregator ingest (July 2026)

The one aggregator the May spike green-lit, shipped under the decided
quarantine-with-flag posture. A new **aggregator tier** distinct from
per-venue scrapers: `AGGREGATOR_SOURCES` runs after the venue scrapers in
every scrape (nightly + `make scrape`), recording an `aggregator:<source>`
slice in the run. Bay Improviser's calendar embeds a Google-Calendar link
per event (title / UTC start / free-text location) — parsed, converted to
Pacific, all-day entries skipped.

**Venue resolution:** exact canonical match (leading-"the" stripped) →
token-subset match either direction ("Bird & Beckett" ⊆ "Bird & Beckett
Books and Records") → a small alias map ("The Jazzschool" →
california_jazz_conservatory) → else auto-create a quarantined
`venues.source='aggregator'` row. **Duplicate guard:** community titles are
free-text blobs, so before ingesting at a *tracked* venue, any same-venue
same-date show whose headliner token-matches the blob marks it a duplicate —
the venue's scraper is authoritative. First live run: 49 events → 33
ingested, 16 correctly skipped as duplicates, 20 new quarantined venues
(Berkeley Finnish Hall, Temescal Arts Center, Artists' Television Access…)
— and **Little Hill Lounge**, unscrapeable directly (flyer-JPEG calendar),
is now covered through the aggregator.

**Quarantine semantics** (in the shows filter SQL): aggregator-venue shows
are hidden unless the "Long tail" toggle is on (`?long_tail=true`, a chip
that appears once aggregator venues exist), the venue is pinned (a ★
promotes it into the main UI everywhere), the venue is explicitly selected,
or the performer-watchlist filter is active — the watchlist always sees
through the quarantine, so a followed artist's gig at an untracked space
surfaces regardless. `/api/venues` now returns `source` so the picker groups
long-tail venues separately and genre chips ignore them.

## Venue watchlist (Phase 9, July 2026)

Follow venues the way the watchlist follows performers. `watched_venues`
(slug PK, single-tenant, mirroring the performer watchlist's contract),
`GET/POST/DELETE /api/venues/watchlist` (POST 404s unknown slugs), and
`?venue_watchlist=true` on `/api/shows` — empty watchlist matches nothing,
and the filter AND-stacks with everything else. Frontend: a ★ pin next to
venue names on show rows across all pages, and a `/venues` page ("Venues" in
the nav): followed venues as an unpin chip row, their upcoming shows through
the shared FilterBar/ShowList, and a collapsed all-venues grid for following
more (open by default when the list is empty). Follow-ons deliberately left:
digest inclusion of watched-venue shows, and the pin-promotes-quarantined-
venue interaction (waits for Bay Improviser ingest to exist).

## Venue batch 3: Club Deluxe + Club Fox; New Parish blocked (July 2026)

**Club Deluxe** (Haight, jazz) — server-rendered Simple Calendar (simcal)
list with epoch data-start attrs and covers embedded in titles; 46 shows
live (the best nightly-jazz add left in SF; publishes ~2 months out).
**Club Fox** (Redwood City, eclectic) — hand-authored homepage show blocks
with Eventbrite links; 14 shows incl. the free Music on the Square series;
the most drift-prone scraper in the house by construction. 37 venues total.

**The New Parish — blocked, with the pipeline pre-solved:** its TicketWeb
event-discovery widget was successfully reverse-engineered (admin-ajax
`get_events_for_calendar` + page nonce), but the venue's TicketWeb inventory
is currently *empty* — the API answers "No events found", TicketWeb's own
venue pages show no events, and aggregators agree. Likely a ticketing
migration. Re-sweep in a few weeks; the endpoint (or TicketWeb's
`venue/{id}/dateSummary/{date}.html` fragment API) is ready when inventory
returns.

## Venue batch 2: six more rooms (July 2026)

The sweep's easy-leftovers batch, shipped through the normal branch/PR loop:
**Bimbo's 365 Club** (North Beach; tw-/TicketWeb template, dark-in-July so 9
shows is real), **Neck of the Woods** (Inner Richmond; tw- on the homepage,
slash-separated bills split, signup-popup duplicates deduped), **August
Hall** (Union Square; tw- "list2" — times only exist on per-event pages, so
scrape fetches ~1 small page per show; "– Moved To …" title annotations
resolved: stripped when moved *here*, dropped when moved *away* since the
destination venue's scraper carries the show), **The Warfield** (Mid-Market;
carbonhouse/AEG static blocks + the platform's events_ajax lazy-load feed,
AXS links), **Thee Stork Club** (Uptown Oakland; SeeTickets, Rickshaw flavor,
per-event genre flows into the override layer; off-site sister-venue cards
dropped by venue line), **The UC Theatre** (Downtown Berkeley; static Webflow
with per-event genre, doors, and prices). 126 shows on the first live run,
zero errors; the tw- shared helper grew month-name dates, a price fallback,
and a time_lookup hook (existing venue tests unchanged). 35 venues total.

Remaining from the sweep list: Club Deluxe, Club Fox (Redwood City), The New
Parish (TicketWeb widget API), the Ticketmaster Discovery API spike
(Fillmore/Regency), and the North Bay region value (Mystic/Sweetwater/
HopMonk).

## Layered genre resolution + performer-genre bootstrap (July 2026)

Genre moved from a pure venue attribute to a three-layer resolution chain:
**per-show override → headliner's performer-level genre → venue default** —
in the `?genre=` filter SQL and the API's resolved `genre` field alike.

- **Phase 7.2 (per-show override).** The SeeTickets scrapers were parsing
  per-card genre to drop comedy and discarding it; it now threads into
  `ScrapedShow.genre` and normalizes to the coarse vocabulary at ingest
  ("Rock / Indie"→rock, "Other Content"→None). 92 shows picked up overrides
  on the first re-scrape — Wolfmother at eclectic-default GAMH files under
  rock, Valerie June (soul) at rock-default Chapel under funk. Manual entries
  keep unmapped genres verbatim.
- **Title-derived genre + wider jam patterns.** When neither source nor venue
  says anything useful, an unambiguous genre word in the title fills the gap
  (word-boundary matched, single-bucket only, curated venue leans never
  second-guessed; B3/Hammond reads as jazz). Jam inference widened to
  plurals, open mics, and organ sessions: 9 → 35 tagged jams.
- **Phase 7.4 stage 1 (deterministic performer genre).** `performers.genre`
  + `genre_source` with a unanimous-evidence bootstrap (`make tag-genres`)
  over per-show overrides, venue leans, and performer-name keywords; mixed
  evidence stays untagged. First run: 353/1,368 performers. Manual
  corrections via `PUT /api/performers/{canonical}/genre` are permanent.
  **The LLM stage for the remaining ~75% is deliberately deferred** — an
  open decision about accepting an LLM dependency in the enrichment tier
  (never ingest-of-record or serving); this deterministic layer is its
  validation baseline if it proceeds.
- **"Eclectic" demoted to honest absence**: no badge, no filter chip — it
  resolves from a mixed-booking venue's default and says nothing about the
  show. Every visible genre badge now carries signal.

## Calendar views + UI polish arc (July 2026)

The reading surface grew up alongside the data:

- **Day / Week / Month views** (`?view=` + `?anchor=`, URL-driven like every
  filter, which all apply across views). Day = the list scoped to one date
  with prev/Today/next; Week = Mon–Sun columns (stacked on mobile); Month = a
  classic grid, two headliners + "+N more" per cell, each cell linking into
  Day view. Calendar views derive their window from the anchor, so the
  list's date controls hide there.
- **Teal accent system** in `lib/ui.ts` — one token file for chip/input/link/
  button styles (collapsed five copy-pasted chipClass definitions), sticky
  translucent nav, tinted filter card, filled genre badges (outline-only read
  as gray at 10px), semantic badge colors (emerald local / amber jam / sky
  added-by-you) kept distinct from the accent.
- **Usability fixes from dogfooding:** the 26-venue checklist collapsed
  behind a summary disclosure ("Venues · all 29") with a responsive grid;
  mobile tucks advanced filters behind a "More filters" toggle (six shows
  visible on the first screen, up from zero); date inputs hold drafts and
  commit on blur — a native date input fires `change` per segment, so the
  old commit-per-change navigated mid-edit and snapped the field back, and
  the min/max cross-constraints blocked moving a range forward; the double
  clear-× on the search bar (WebKit's native control next to ours — the
  hide-it CSS gets stripped by the build minifier, so the input is now
  `type="text"` + `role="searchbox"`).

## Manual events + jam sessions (July 2026)

Two features prompted by a coverage gap: following two real artists (Lisa
Mezzacappa, Dillon Vado) showed that part of the local scene — house
concerts, one-off spaces, Instagram-only venues, festival one-offs — will
never be reachable by scrapers, and that jam sessions are a distinct thing a
player plans around.

**Manual events** (`POST /api/events`, `/add` in the UI, "Add event" in the
nav). A manual event rides the exact scraped-ingest path — same
canonicalization and natural-key dedup, so double entry is idempotent — but
is stamped `shows.source='manual'`: deletable through the API (scraped rows
refuse deletion since the next refresh would resurrect them) and badged
"added by you" with a remove affordance in the list. The venue is an existing
slug or a free-text new name; unknown names create `venues.source='manual'`
rows that appear in `/api/venues` and every filter with no scraper attached.
Provenance is preserved via an optional source link (flyer URL, IG post);
`manual://user-entry` otherwise.

**Jam sessions** (`shows.event_type`, `?type=show|jam`, Shows/Jam-sessions
chips, amber "jam" badge). Tagging precedence: explicit scraper tag > the
manual form's checkbox > a deliberately narrow ingest-time title heuristic
("jam session" / "open jam" / "jam night" / "<genre> jam") that can't misfire
on band names (Pearl Jam tribute stays a show — regression-tested). The
heuristic alone surfaced 9 real July jams already in the scraped data (Boom
Boom Room's funk jam, Ocean Ale House's weekly jazz jam, The Back Room's
singers session, Madrone's Saturday jam).

Both features are single-tenant/no-auth like the watchlist. ShowView now
carries `id`, `source`, and `event_type`.

## Performer origin tagging v1: local/touring (July 2026)

The most mission-aligned facet — "show me local acts to support" — shipped as
performer-level tags, since venues mix (Yoshi's books local trios between
tours; big rooms put local openers under touring headliners). No scraped
source publishes this, so v1 is **inference + correction**: a conservative
heuristic bootstrap (`make tag-origins`, idempotent, safe after every scrape)
scores each performer from evidence already in the DB — recurrence spread
over weeks (consecutive-night touring runs deliberately don't count),
multi-venue presence, venue booking priors (small nightly rooms ≈ local;
Fox/Greek *headliners* ≈ touring; mixed rooms contribute nothing), and
Ticketmaster/AXS headline slots — and only tags past a threshold, leaving
everything else unknown. `PUT /api/performers/{canonical}/origin` records
manual corrections as permanent (`origin_source='manual'`; the heuristic
never overwrites them, and a stale heuristic tag clears when its evidence
fades rather than fossilizing).

`GET /api/shows?origin=local|touring` uses any-performer semantics (matching
the watchlist): a touring headliner with a local opener matches `local`,
because the opener is why a support-local user would go. Frontend: "Local
acts"/"Touring" chips labeled "(likely)" that render only when tagged
performers exist in the result set, and a subtle "local" badge on tagged
names — touring gets no badge so unknown never reads as "not local".

First live bootstrap over the 26-venue catalog: **153 local / 29 touring /
1,144 unknown (86% deliberately untagged)**; spot check: touring 10/10,
local ~9/10. Recurrence evidence compounds as scrape history accumulates
(persisted shows outlive their dates), so coverage grows by re-running the
CLI — and the deterministic scorer doubles as the validation baseline for a
future Phase 7.4 LLM pass. "regional" (Bay-based but touring) deferred until
the two-way split proves too coarse.

## Venue expansion batch: 23 new scrapers + genre facet (July 2026)

A single feature-branch push (ad-hoc, user-directed — no per-venue tickets)
that grew foghorn from 3 scraped venues to 26 and shipped the Phase 7.1 genre
facet the new cross-genre diversity finally made meaningful. Built by parallel
coding agents (one per 1–2 venues) in an isolated worktree, with central
integration (registry, seed, docs) and a full-gate + live-scrape verification
pass at each merge point. Full 26-venue live scrape at ship time: **1,192
shows, zero errors** (SF 871 / East Bay 295 / Peninsula 26), idempotent on
re-run.

**New venues and their data sources** — the scraper-interface flexibility the
plan called for got exercised hard; almost every venue needed a different
source shape:

- **Black Cat** (SF, jazz) — Turntable Tickets performance API (JSON).
- **Ocean Ale House** (SF, eclectic) — the schedule TSV on GitHub that the
  client-rendered site itself fetches (`aspyrx/oah-content/events.tsv`);
  no-year dates roll forward across New Year.
- **Boom Boom Room** (SF, funk) — server-rendered rhp-events HTML with month
  separators; doors + show times parsed.
- **Madrone Art Bar** (SF, eclectic) — WordPress Tribe Events REST API (same
  pattern as Mr. Tipple's). Known gap: recurring nights entered as all-day
  Tribe events (~30/mo) carry no start time and are skipped.
- **Bottom of the Hill** (SF, rock) — the venue's famous hand-maintained
  static `calendar.html` (HTML 4.01 table, ISO-8859-1 with no charset header —
  fetcher pins encoding); bills in top-billing order, doors/cover/stubmatic
  links.
- **Rickshaw Stop** (SF, rock) — SeeTickets white-label calendar: server-
  rendered cards + nonce'd admin-ajax pagination (nonce fetched fresh each
  run); headliner/support pre-split; non-music genres dropped.
- **Kilowatt** (SF, rock) — Dice.fm events API via the public widget key in
  the site's DiceEventListWidget config; fee-inclusive prices in cents.
- **The Knockout** (SF, rock) — Squarespace calendar-collection
  `GetItemsByMonth` JSON (the older `/calendar` collection is stale 2023 test
  data — a trap for future re-scrapes); no ticket/price/doors published.
- **Yoshi's** (Oakland, jazz) — the fullCalendar JSON feed behind the venue
  calendar (one entry per *set*, so 7:30/9:30 shows land separately — better
  than the HTML, which collapses them), prices joined from the HTML page
  best-effort. Biggest single venue: 125 shows.
- **California Jazz Conservatory** (Berkeley, jazz) — server-rendered
  `concerts.jazzschool.org` listing + per-event pages for times (classes never
  appear on that subdomain; movie nights dropped). VBO ticket widget means no
  static ticket/price.
- **Ivy Room** (Albany, rock) — Venuepilot public GraphQL API (`accountIds`
  from `window.venuepilotSettings`); the Squarespace site is a JS shell.
- **924 Gilman** (Berkeley, rock) — the collective's server-rendered
  ShowSlinger ticketing listing (the Wix calendar is client-rendered with the
  Wix Events app disabled). Unticketed shows outside ShowSlinger won't appear.
- **El Cerrito Natural Grocery Annex** (El Cerrito, jazz) — company-wide Tribe
  REST API filtered to events at the Annex venue record; "The Annex Sessions:"
  prefix stripped. First venue to activate the **East Bay region chip**.

A second wave, targeted by a scrapability sweep of ~36 remaining venues,
added ten more (two shared-template parser families did the heavy lifting):

- **The Independent** + **Cafe du Nord** (SF, rock) — one shared
  `_ticketweb_calendar` helper for the TicketWeb "tw-" WordPress template.
  Cafe du Nord's hidden per-event dialogs supply dates/doors/prices; Swedish
  American Hall shows bill under cafe_du_nord.
- **Great American Music Hall** (eclectic) + **The Chapel** (rock) — the
  SeeTickets white-label platform Rickshaw Stop established, in two markup
  flavors; sports watch parties and "Private Event" hold cards dropped.
- **Fox Theater Oakland** + **Greek Theatre Berkeley** (East Bay, rock) — one
  shared `_ape_listing` helper for their common APE template.
- **DNA Lounge** (SF, electronic) — the venue's self-published **.ics feed**,
  the cleanest source in the batch. First "electronic" genre venue.
- **Cornerstone Berkeley** (rock) — server-rendered JSON-LD + Tixr; startDate
  is date-only so times come from adjacent card markup (skips loudly if the
  markup shifts).
- **The Back Room** (Berkeley, eclectic listening room) — Humanitix JSON-LD
  merged with the public tRPC events endpoint behind the "Load more" button.
- **Guild Theatre** (Menlo Park, eclectic) — homepage JSON-LD + card times.
  **First Peninsula venue** — activates the third region chip.

Sweep verdicts worth keeping (see the deferred list for blocked venues):
Freight & Salvage and The Midway sit behind Cloudflare; The Fillmore is a
Live Nation JS shell (a **Ticketmaster Discovery API spike** would cover it
and Regency Ballroom); El Rio is JS-only; Eli's Mile High/Golden Bull have
dead sites; Starline Social Club appears closed. Still-easy leftovers for a
future wave: The UC Theatre, Bimbo's 365, Neck of the Woods, The Warfield,
August Hall (all TicketWeb/static families), Club Deluxe, Club Fox (Redwood
City), Thee Stork Club (SeeTickets), The New Parish (TicketWeb widget API).
North Bay (Mystic Theatre — SeeTickets, Sweetwater, HopMonk) needs a "North
Bay" region enum value first.

**Blocked (no scrapeable calendar exists):**

- **For The Record** (SF Cow Hollow hi-fi listening bar — *not* the Oakland
  guess): one-page Squarespace site, all programming Instagram-only.
- **Little Hill Lounge** (El Cerrito): calendar is a monthly flyer **JPEG** on
  a one-page WordPress site; a former Tribe install was removed. Bandsintown
  has it but 403s plain HTTP. Would need OCR or a headless browser.

**Genre facet (Phase 7.1)** shipped alongside: `venues.genre` (TEXT, nullable)
with an additive-column migration guard in `init_schema` (the first schema
change against pre-existing DBs — `CREATE TABLE IF NOT EXISTS` skips existing
tables, so there's now a `_add_column_if_missing` PRAGMA check), threaded
through repo/API (`?genre=`, case-insensitive, AND-stacks with the other
filters) and both venue payloads. Frontend `GenreFilter` chip row renders from
the distinct genres in `/api/venues` (data-driven like the region chips;
hidden below two genres). Current values: jazz ×8, rock ×12, eclectic ×5, electronic, funk.
Distribution at ship: jazz 455 / rock 441 / eclectic 213 / electronic 68 / funk 15.

**Ingest fix surfaced by the full live run:** venues sometimes bill the same
act twice (headliner repeated in the support list, or "TBA" filling several
slots), violating the `show_performers (show_id, performer_id)` PK.
`_build_bill` now dedupes by performer, earliest billing position wins —
regression-tested. This was invisible with 3 venues and immediate with 16.

Tests: 128 → 394 (every scraper has a trimmed-real-fixture suite with a
pinned `today`). The venues-endpoint and seed tests now derive expectations
from `SEED_VENUES` + `REGISTERED_SCRAPERS` instead of a hardcoded four-venue
list, so future venue adds don't touch them.

## Aggregator evaluation spike (May 2026)

Time-boxed research spike ([#29](https://github.com/diegoSQK/foghorn/issues/29))
evaluating whether third-party **aggregators** could feed foghorn's ingest
pipeline and short-cut the per-venue-scraper grind ahead of a Phase 5+ re-scope.
Five candidates scored against a fixed 8-point rubric (data shape, coverage,
genre, freshness, dedup, access, ToS, verdict). Output is memos only — no
production code, no `PROJECT_PLAN.md` change (the re-scope is the PM thread's
follow-on). Per-candidate detail: [`docs/spikes/aggregator-evaluation/`](spikes/aggregator-evaluation/);
synthesis + the open question: [`RECOMMENDATION.md`](spikes/aggregator-evaluation/RECOMMENDATION.md).

Headline findings:

- **One "in": Bay Improviser** ([memo](spikes/aggregator-evaluation/bay-improviser.md)) — the only source that's genuinely ingestible *and* on-target for the jazz/new-creative wheelhouse: robots-permissive HTML calendar with per-event iCal/gCal structured fields, surfacing dozens of DIY/creative rooms per-venue scrapers will never reach. Caveat: community-entered free text, so it needs venue-name aliasing + UTC→local conversion + a **fuzzy secondary dedup pass** (exact natural-key dedup won't catch its free-text headliner blobs / one-off improv-ensemble names).
- **Strongest signal — aggregator ingest does NOT replace per-venue scraping; it can only narrowly augment it.** Recommended re-shape: **Augment** (keep Phase 5 per-venue as the backbone + add Bay Improviser as one additive source). Phase 6 (LLM-assisted per-venue) stays the real scaling lever, not aggregators.
- **Biggest surprise** — the two clean *global* APIs that were supposed to define "the easy path" (Songkick, Bandsintown) are both **closed to a small unlicensed aggregator**: no obtainable key/`app_id`, ToS that ban scraping, edge-level bot walls (Songkick 406 / Bandsintown Cloudflare 403) — *and* their coverage skews to touring acts at big rooms, exactly away from foghorn's small jazz rooms (Songkick shows Bird & Beckett with 0 upcoming).
- **Cleanest API — DoTheBay's** undocumented `events.json` ([memo](spikes/aggregator-evaluation/dothebay.md)): no auth, no anti-bot, ~1:1 with `ScrapedShow`, 239 music shows / ~87 venues in a sample week. But verdict is **Maybe→Skip**: its ToS bars scraping + restricts use to personal/non-commercial. Engineering-ready; gated on a *permission/feed* conversation, not code.
- **Most concerning ToS posture** — a tie: Songkick (§9.8 explicit "no robots/scrapers/data-mine", `ClaudeBot Disallow: /`, paid partner-only API) and Bandsintown (bars commercial use *and* redistribution *and* scraping the very public pages that would fill the gap). What's Poppin is simply **not feasible** (a YouTube talk show; no web-readable calendar exists).

Two live discovery POCs landed in `backend/scripts/` (`spike_aggregator_bay_improviser.py`, `spike_aggregator_dothebay.py`), each marked `# SPIKE — not production` and **not** registered in `REGISTERED_SCRAPERS`. Both run clean against live sources (Bay Improviser: 52 events parsed with UTC→PT conversion; DoTheBay: 17 music events with correct Pacific offset). **Open question for the PM thread before tickets are filed:** auto-accept aggregator-discovered venues into the DB, or maintain a curated venue allow-list? (Shapes the Bay Improviser ticket and interacts with the Phase 3.2 region/neighborhood facets — see RECOMMENDATION.md.)

## Watchlist digest endpoint (Phase 4.2, May 2026)

A read-only `GET /api/watchlist/digest` — the next-N upcoming watchlist matches,
chronological — for a future cron/email/push "what's coming up for you" consumer
(delivery itself stays deferred). Closes #27.

**Almost pure reuse of 4.1.** The endpoint runs `build_show_views(...,
watchlist=True)` over `[today, today + days]` (the exact `?watchlist=true`
filter + a today-anchored window), then the *only* new logic computes
`watchlist_matches` per row: which watched `display_name`(s) hit, via the same
`matches_token_bag`. A show can match more than one (a bill with two watched
names), so it's a list. Response: `{generated_at, matches: [...]}` where each
match is a `/api/shows` row **plus** `watchlist_matches`. Ordered by `start_utc`;
`limit` applied after match + ordering. Empty watchlist → `{generated_at,
matches: []}` (200, not 503 — nothing wrong, just nothing to send).

**Shape held up after dogfooding 4.1** — the ticket flagged it might want
reshaping, but reusing the filter + adding the matched-names field was exactly
right; no deviation. Params `days` (default 14) and `limit` (default 20) are
bounded (`ge=1`); out-of-range values 422 rather than silently clamping.

**No frontend, no new schema or match logic** — purely the new endpoint on the
existing `api/watchlist.py`. Tests (`api/test_watchlist_digest_endpoint.py`):
ordering + window filtering, the `watchlist_matches` field (incl. a
two-watched-names overlap), `days` widening, `limit` capping, and both
empty-watchlist and no-upcoming-matches → empty. Anchored to `date.today()` (the
digest uses the real clock, unlike the param-driven endpoints) so they're
date-independent. Verified live against the real DB.

**Release signal (PM thread):** with Phase 3 (#19/#20/#21) and Phase 4 (#26/#27)
both complete, this is the **v0.2.0 release-cut point** per PROJECT_PLAN
"Suggested sequencing". Per `RELEASE_PROCESS.md` the cut is a PM-thread ritual —
*not* done in this PR; surfaced for the PM thread.

## Watchlist data model, UI, and token-based matching (Phase 4.1, May 2026)

Diego's original "find shows where my friends are playing" ask. Closes #26. A
single-tenant watchlist of performers, a dedicated `/watchlist` view, add/remove
affordances on every show card — and the performer-match logic upgraded to
token-bag and shared between this and 3.3's search.

**Token-bag matching is now the canonical performer match
(`repo/performer_match.py`).** A query matches a performer iff every whitespace
token of the (canonicalized) query is a whole token of the performer's canonical
name. So "joshua redman", "redman joshua", and "Redman, Joshua" all match
"joshua redman quartet"; "redm" does **not** match "redman" (whole tokens, not
character substrings). This replaces 3.3's one-directional substring match —
**3.3's `?performer_query=` was refactored to use it too** (one matcher, same
UX in search and watchlist), and 3.3's tests gained a reordering case that the
old substring match would have failed. `matches_token_bag` is the pure function;
`token_match_sql` builds the parameterized `(' '||name||' ') LIKE '% tok %'`
predicate (OR across bags, AND within). Tokens are pre-canonicalized to
`[a-z0-9 ]`, so they carry no `LIKE` wildcards and need no escaping. FTS5/trigram
fuzzy matching stays deferred (PROJECT_PLAN Phase 7).

**Schema + repo.** `watchlist(canonical_name PK, display_name, added_at, notes)`
— `canonical_name` (canonicalized `display_name`) is both match key and PK; no
`user_id` (single-tenant per AGENTS.md — that's a future migration, not pre-paid
now). `repo/watchlist.py` add/list/remove: **canonicalize-on-add**, and re-adding
the same canonical never overwrites the original `display_name`/`added_at` (it
can update `notes`).

**Two-level matching — deliberate.** The `+`/`✓` button on a show card reflects
**exact** canonical membership (is *this* performer on the list), while the
`?watchlist=true` filter uses **token-bag** (surface every show where any
performer matches any watched name). So watching "Vince Lateano" surfaces "Vince
Lateano Trio" shows in `/watchlist`, but that Trio's `+` button stays a `+`
unless you add it specifically. This is correct, if subtle — documented here so
a future reader doesn't "fix" it.

**`?watchlist=true` on `/api/shows`** loads the watchlist, turns each entry into
a token bag, and matches via the shared predicate, stacking (AND) with all other
filters. **Empty watchlist → `[]`** (surfaces the empty state, doesn't flood
with everything) — both API and the `/watchlist` page handle this (the page
shows a CTA to add performers from `/`, not an empty FilterBar).

**Watchlist CRUD (`api/watchlist.py`).** `GET/POST/DELETE /api/watchlist` —
POST canonicalizes the display name (422 if it canonicalizes to nothing), DELETE
by canonical name (404 if absent, 204 on success).

**CORS added.** The add/remove buttons are client components that call the API
cross-origin (frontend `:3000` → backend `:8000`), so `api/__init__.py` gained
`CORSMiddleware`. Local-first + no auth, so it defaults permissive
(`allow_origins=["*"]`); `FOGHORN_CORS_ORIGINS` tightens it when the app is ever
deployed publicly. (Server-component fetches are server-side and never needed
CORS — this is purely for the new client mutations.)

**Frontend.** Filter/show rendering was extracted into a shared `ShowList`
(used by `/` and `/watchlist`) and `lib/api.ts` (shared base/types/`getJSON`).
`AddToWatchlistButton` (client, optimistic +/✓ toggle, reverts on failure) sits
on every performer; the server passes each a server-computed `initiallyOn`.
`/watchlist` reuses `FilterBar` — which (with `PerformerSearch`) was made
route-aware via `usePathname()` so filters stay on `/watchlist` instead of
bouncing to `/`. `WatchlistChips` (client) removes entries and `router.refresh()`es
so the matches + chips + nav count re-render. The nav lives in `layout.tsx`
(async, server-fetches the count) → `Watchlist (N)`; the count updates on
navigation (optimistic card adds catch up on the next nav, per the ticket).

**FE gotcha:** the `/watchlist` split — shows are server-fetched, but the
watchlist is client-mutated — is reconciled with `router.refresh()` (chip
removal) and optimistic local state (card buttons). No client store; the server
is the source of truth, the client just nudges it and re-reads.

Tests (122 green under mypy `strict`): `repo/test_performer_match.py` (token
cases incl. reorder, partial-token-false, accents), `repo/test_repo_watchlist.py`
(add/list/remove, idempotency, display preservation), `api/test_watchlist_endpoint.py`
(CRUD + 404 + canonicalize + 422), `api/test_shows_watchlist_filter.py`
(`?watchlist=true` matches, empty→[], stacks), and 3.3's
`test_shows_performer_filter.py` updated for token behavior. Live-verified the
full UI: empty CTA → add → `/watchlist` shows token-matched shows + chips + nav
count, and the exact-performer `✓` state on `/`.

**Frontend e2e:** the Playwright framework (#30) landed in parallel and is
merged in here; its five specs are kept green against this PR's UI changes (the
new nav + the `+`/`✓` buttons). The watchlist UI doesn't have its *own* specs
yet — a natural follow-up now that the framework exists.

## Frontend e2e test framework — Playwright (May 2026)

Stands up the frontend component-test framework that 3.1 / 3.2 / 3.3 each
flagged as missing (the frontend had only `tsc` / ESLint / `next build` — no
way to assert click-through behavior). Closes #28; resolves the open flag in
those three SHIPPED entries. Five smoke specs prove the framework; subsequent
UI tickets add specs as they touch the surface (the framework is the
deliverable, not coverage).

- **Playwright, not React Testing Library.** The gap that kept getting flagged
  is *interaction* behavior — debounce, chip/toggle states, URL updates on
  click — across a mostly-server-component app with a few client islands
  (`FilterBar`, `PerformerSearch`, `LocationFilter`). Playwright drives a real
  Chromium against a production build, so it covers the SSR + hydration +
  interaction loop RTL-with-jsdom can miss. Chromium only for now (Firefox /
  WebKit deferred).

- **Mock the backend with a real process, not `page.route()`.** The ticket
  suggested `page.route()` interception, but `app/page.tsx` is an async
  *server* component — it fetches `/api/shows` and `/api/venues` from the Next
  server process, which `page.route()` (browser-only) can't intercept. Instead
  a ~30-line Node mock (`frontend/tests/mock-api/server.mjs`) serves fixture
  JSON, and the app is built with `NEXT_PUBLIC_API_BASE_URL` pointed at it (via
  `playwright.config.ts`'s `webServer` env). Same intent as the recommendation
  — isolated, fast, no Python / DB — implemented to match the app's SSR shape.
  Specs assert UI/URL state, not backend filtering (that's the pytest suite's
  job), so the mock returns a static list regardless of query params.

- **Built production app, port 3100.** `webServer` runs `npm run build && npm
  run start` (what the gate already validates; closer to prod than `dev`) on
  3100, so a developer's `npm run dev` on 3000 can keep running alongside.

- **Opt-in target, separate CI job — not in `make gate`.** Playwright is
  slower and needs a browser binary, so it's `make frontend-test` (installs
  Chromium if missing, then runs the specs), plus a `frontend-test` job in
  `gate.yml` parallel to `gate` (both required). `make gate` is unchanged and
  still ~13s: the specs + `playwright.config.ts` are excluded from the app's
  `tsconfig` and `eslint` config, so the fast gate never compiles or lints them
  — Playwright type-checks and runs them itself.

The five specs (`frontend/tests/`): the `Tonight` quick-chip date range, the
debounced performer search → URL, the SF region chip toggle + disabled "(soon)"
regions, and a deep-linked filter URL reflected in the controls. The
watchlist-button spec the ticket mentioned was skipped — Phase 4.1 hadn't
landed on `main` when this shipped (it was in flight in a sibling worktree);
the next UI ticket adds it. How to write a spec, the fixture/mock pattern, and
how to run locally are documented in `frontend/tests/README.md`.

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
