# Ticketmaster Discovery API spike — recommendation

> Research spike, evaluated 2026-07-07. Candidate: **Ticketmaster Discovery API v2** (`https://app.ticketmaster.com/discovery/v2/`, docs at [developer.ticketmaster.com](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/)) as the ingest path for the two Live Nation/Goldenvoice rooms that block scraping: **The Fillmore** (SF — Next.js shell, no SSR event data) and **The Regency Ballroom** (SF — 403s direct fetches). Modeled on the May aggregator spike (`docs/spikes/aggregator-evaluation/`). POC: `backend/scripts/spike_ticketmaster_discovery.py`.

## Verdict: ✅ **Recommend (with conditions)**

This is the first candidate evaluated where the front door is actually open. Unlike Songkick (partner-only key + license fee, ToS §9.8 scraping ban, Fastly 406 wall) and Bandsintown (approval-gated `app_id`, Cloudflare 403), Ticketmaster issues **free API keys instantly on self-serve signup**, the Discovery API is explicitly an **OPEN API** product, and — decisively — **Ticketmaster is the venue's own ticketing system** for these rooms, so this is first-party data through a sanctioned door, not aggregator scraping. The ToS is workable for a personal, non-commercial aggregator, with real conditions (below).

**Conditions:**

1. **Stay non-revenue.** The ToS bars "deriv[ing] revenues from the use or provision of the Ticketmaster API." foghorn is personal/non-commercial today; if that ever changes, this ingest path must be re-evaluated first.
2. **Refresh, don't archive.** Cache posture must be "current upcoming events, refreshed on the ingest cadence" — not a permanent historical archive of TM data (ToS allows caching only "for reasonable periods in order to provide the service").
3. **Honor the 24-hour takedown duty** (remove Event Content within 24h if an owner asks) — fine for a daily-refresh pipeline where stale events age out anyway, but it should be written down as an operating rule.
4. **Keep TM as the ticket link.** `event.url` goes straight to the Ticketmaster purchase page — we link to them, never around them. This also keeps us clearly outside the "replicates or attempts to replace the unique essential user experience of Ticketmaster.com" prohibition: foghorn is a local what's-on list, not a ticket marketplace.
5. **Batch politely.** ~2–4 API calls per nightly run (one page per venue) is far inside the 5,000/day quota and can't plausibly trip the "large number of calls … not primarily in response to direct user actions" clause, but keep ingest to venue-scoped queries, not market-wide crawls.

## The ToS analysis (this decided the verdict)

Source: [General Terms of Use](https://developer.ticketmaster.com/support/terms-of-use/), last updated June 27, 2023 (full text fetched and read verbatim, not summarized from secondary sources).

**What it permits / requires:**

- License is worldwide, non-exclusive, non-transferable, and free; "Event Content" (= "event name, dates, times, venue name, and additional information such as Tickets, Attendees, Orders") is owned by "the organizers and/or Ticketmaster."
- **You shall** "Remove from your application within 24 hours any Event Content or other information or tickets that the owner asks you to remove," and disclose data practices "through a privacy policy or otherwise displayed in the footer of each page."
- **No explicit attribution/logo/backlink mandate** in the general terms (branding-guideline compliance is cited only as a criterion for *rate-limit increases* we don't need). We should still credit "via Ticketmaster" per show as good hygiene — it costs nothing and matches `source="aggregator"` provenance display.

**What it prohibits (relevant subset, verbatim):**

- "Use the Ticketmaster API for any application that **replicates or attempts to replace the unique essential user experience of Ticketmaster.com** or the Ticketmaster apps." — foghorn aggregates dozens of non-TM venues and links out to TM for tickets; it is not a TM replacement. Low risk, but it's the clause to re-read if foghorn ever grows ticketing features.
- "**Cache or store any Event Content other than for reasonable periods** in order to provide the service you are providing." — the historically feared "24-hour storage window" **is not in the current terms**; the standard is "reasonable periods" tied to the service. A show-listing DB refreshed nightly, holding only upcoming events, is a defensible reading. A permanent TM-sourced history table is not. (Note: foghorn's `shows` table naturally ages events out of the UI by date; we should not treat TM rows as an archival dataset.)
- "Sell, lease, or sublicense the Ticketmaster API … or **derive revenues** from the use or provision of the Ticketmaster API." — fine while foghorn is personal/non-commercial.
- "We reserve the right to rate limit or block applications that make a **large number of calls … not primarily in response to direct user actions**." — a nightly batch is not user-initiated, but 2–4 calls/night is not "a large number"; the FAQ points genuinely high-volume use to the (partner-gated) Discovery Feed instead.
- Termination: "Ticketmaster may terminate the license at any time for any reason." — the sustainability risk is *business*, not legal: same at-will posture as every free API.

**Compared with the May spike's ToS scoring:** Songkick was Skip on "contractually prohibited *and* technically blocked, key unobtainable"; Bandsintown was Skip on "ToS bars commercial use, redistribution, *and* scraping + approval-gated key"; DoTheBay was conditional on a permission conversation. Ticketmaster is categorically different: the access is *granted by design* (open API, instant key), the restrictions are operating conditions rather than prohibitions, and the data is first-party (TM is the box office). On the house rubric's ToS axis this is the strongest legal posture of any external source evaluated to date.

## Rubric

### 1. Data shape — excellent, best seen so far

`GET /discovery/v2/events.json?apikey={key}&venueId={id}&sort=date,asc&size=100` returns `_embedded.events[]`, each with:

| API field | ScrapedShow field | Notes |
| --- | --- | --- |
| `_embedded.attractions[]` | `headliner_raw` = `[0].name`, `support_raw` = `[1:].name` | **The bill, pre-split** — canonical artist names in billing order (verified on live TM venue pages: "Old 97's w/ River Shook", "Kamelot w/ Visions of Atlantis, Frozen Crown"). Fallback to `event.name` when no attractions. |
| `dates.start.localDate` + `localTime` | `start_local` (naive) | Venue-local, exactly the ScrapedShow contract (tz applied at ingest). `dates.timezone` (`America/Los_Angeles`) available as a sanity check. TBA/TBD flags (`dateTBD`, `dateTBA`, `timeTBA`, `noSpecificTime`) let us skip un-dated events cleanly. |
| `classifications[]` (segment → genre → subGenre, `primary: true`) | `genre` | Per-event genre passthrough (e.g. segment "Music", genre "Rock") — feeds the Phase 7.2 `genre_override` pipeline like SeeTickets/Dice tags do. |
| `url` | `ticket_url` **and** `source_url` | Direct TM purchase page. |
| `priceRanges[] {min, max, currency}` | `price_text` | Format as `"$25–$45"`; often absent pre-onsale — leave `None`. |
| `dates.status.code` | (filter) | `cancelled` / `postponed` events are flagged — we can *exclude cancellations at ingest*, which venue-site scrapers can't always see. |
| — | `doors_local` | **Not provided** — same gap as Songkick, but unlike Songkick the published `localTime` is showtime, not doors, so the natural key stays clean. |

Pagination: `page {size, totalElements, totalPages, number}`, deep-paging capped at `size * page < 1000` — irrelevant at per-venue volumes (≤ ~60 events).

### 2. Coverage — exactly the two blocked rooms, verified live

- **The Fillmore** (TM venue page 229424): **56 upcoming events** listed through fall 2026, with support acts and a flagged cancellation.
- **The Regency Ballroom** (TM venue page 229653): **20+ upcoming events** through Oct 2026, support acts listed ("Streetlight Manifesto w/ AJJ", "Citizen w/ Hotline TNT").

These are TM-exclusive rooms — TM inventory *is* the venue calendar, not a partial mirror. Genre skew is touring rock/indie/hip-hop, i.e. the Phase 5 rock/indie lane these venues were already slated for; this does nothing for the small-jazz-room wheelhouse and isn't claimed to.

**Ride-alongs (note only, no action):** Fox Theater Oakland (TM page 229846; its box office states tickets are "available exclusively through Ticketmaster") and Greek Theatre–UC Berkeley (TM page 229421) are also TM-ticketed, so the same key would cover them for free if the APE-site scrapers (`_ape_listing`) ever break. Keep the existing scrapers authoritative; Discovery is a free fallback/cross-check, and adopting it there would need the fuzzy-dedup posture below.

### 3. Freshness — authoritative

This is the box office's own system: onsales, cancellations, postponements, and reschedules land in the API when they land on ticketmaster.com. Strictly fresher than scraping a venue's marketing site, and it carries an explicit event status our scrapers have to infer.

### 4. Dedup — clean, with one boundary to respect

- Attraction names are canonical artist names with billing order — cleaner input to `canonicalize()` than any scraped free text.
- `localDate`/`localTime` is the advertised showtime → natural key (`venue_id` + local date/time + headliner) forms correctly. No doors-vs-showtime hazard.
- Fillmore/Regency have **no existing scrapers**, so there is no shared-venue collision at all — the fuzzy secondary-dedup infrastructure the Bay Improviser memo priced in is **not needed** for this source. It only becomes relevant if TM ingest is later pointed at Fox/Greek alongside their scrapers (then: scrapers stay authoritative, same rule as the May spike).
- Multi-night runs (e.g. Courtney Barnett ×3, Sleep ×2) arrive as separate events with distinct dates — correct for our model.

### 5. Access mechanics — open, instant, generous enough

- **Key signup (owner action, ~5 minutes):**
  1. Go to `https://developer-acct.ticketmaster.com/user/register` and create a free developer account (name, email, password; no company/approval step).
  2. Registration provisions a default app with a **Consumer Key** immediately — that string is the API key.
  3. Verify with: `curl "https://app.ticketmaster.com/discovery/v2/venues.json?apikey=KEY&keyword=fillmore&stateCode=CA"`
  4. Export it as **`TM_API_KEY`** for the POC (and later for the ingest job's environment). Do not commit it.
- **Auth:** `apikey` query param on every request; 401 `"Invalid ApiKey"` otherwise.
- **Quota:** documented default **5,000 calls/day**; per-second limit documented inconsistently (getting-started says 5 req/s, FAQ says 2 req/s) — assume 2 req/s and it never matters at our volume. Nightly ingest for two venues ≈ 2 calls.
- **No anti-bot wall:** this is the sanctioned programmatic surface; no UA games, no edge blocks.

### 6. Venue IDs (found this spike)

| Venue | Discovery API `venueId` | Legacy TM page id | Confirmation |
| --- | --- | --- | --- |
| **The Fillmore** (1805 Geary Blvd, SF) | **`KovZpZAE6eeA`** | 229424 | livenation.com venue URL (`/venue/KovZpZAE6eeA/the-fillmore-events`) + third-party references |
| **The Regency Ballroom** (1300 Van Ness Ave, SF) | **`KovZpZAEet6A`** | 229653 (dup legacy page 360464) | livenation.com venue URL (`/venue/KovZpZAEet6A/the-regency-ballroom-events`), page verified as 1300 Van Ness, SF 94109 |

The Discovery API takes only the alphanumeric IDs (legacy numeric ids are the ticketmaster.com page ids, not accepted by `venueId`). The POC hardcodes the two IDs above but also demonstrates runtime resolution via `/discovery/v2/venues.json?keyword=…&stateCode=CA` as a first-run cross-check, since the IDs came from public references rather than a keyed API call.

### 7. What promotion to production would look like (not in this spike)

A single `ticketmaster` aggregator-style source (alongside `REGISTERED_SCRAPERS`, `source="aggregator"` or arguably `"scrape"` since TM is the venue's own box office — PM call), config-mapping Discovery `venueId` → `venue_slug` for seeded `the_fillmore` / `regency_ballroom` venues. Build cost: **Small** — one HTTP fetch per venue, ~1:1 field map (see §1), no new dedup infrastructure. The two venues need seeding in `seed_venues.py` first.

## Confidence & caveats

- **Live-verified:** full ToS text (fetched raw, quoted verbatim above); TM venue pages for Fillmore (56 events, support acts, a cancellation) and Regency (20+ events, support acts); both Discovery venue IDs via livenation.com URLs; signup flow described from the developer portal's own getting-started page.
- **Documented-only (no key in hand):** exact response payloads for these two venues; quota numbers; the per-second limit discrepancy (5 vs 2 req/s). The POC is syntax-checked but **not run against the live API** — first action after key signup is to run it and eyeball the output against the venue pages.
- **Known unknowns:** whether Regency events ever route through AXS instead of TM (Goldenvoice is AEG; the TM page currently shows a full, current calendar, so TM has the inventory today — but worth a glance during the first live run); whether `priceRanges` is populated for these rooms (often absent pre-onsale).
