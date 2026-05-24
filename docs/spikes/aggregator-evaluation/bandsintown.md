# Aggregator evaluation — Bandsintown

> Spike memo for [#29](https://github.com/diegoSQK/foghorn/issues/29). Evaluated 2026-05-23. Global API benchmark. **Verdict: Skip.**

**Candidate:** Bandsintown — `https://bandsintown.com`. Global, performer-centric concert service. Evaluated with **no `app_id`** (foghorn has none; see §6), against foghorn's venue-calendar-centric needs.

## 1. Data shape

**The public API (`rest.bandsintown.com`) — documented, not verifiable without `app_id`** — is **artist-rooted only**:

- `GET /artists/{artist_name}/events/?app_id=…` (`date=upcoming|past|all|YYYY-MM-DD,YYYY-MM-DD`) ([API docs](https://help.artists.bandsintown.com/en/articles/9186477-api-documentation)).
- **`app_id` mandatory on every call**, assigned only after Bandsintown approves the use case. **No documented venue or city/metro "what's on" discovery endpoint** ([what is the API](https://help.artists.bandsintown.com/en/articles/7053475-what-is-the-bandsintown-api)).
- Event fields: `datetime` (ISO start), `url`, `on_sale_datetime`, `lineup[]` (artist-name strings), `offers[]` (`{type,url,status}` — **no price**), nested `venue`. **Data-quality gotcha:** when an event has a *title*, `venue.name` is **replaced by the event title** — i.e. the exact field foghorn keys on is unreliable.

**The public web surface** (the unexpected upside): **city pages** `bandsintown.com/c/san-francisco-ca` (filterable by date + genre, e.g. `…/this-week/genre/jazz`), **venue pages** `bandsintown.com/v/{id}-{slug}` (these *are* the venue calendars foghorn wants), and **event pages** `bandsintown.com/e/{id}-{slug}` that carry **schema.org `MusicEvent` JSON-LD**.

**Realistically usable shape given no `app_id` + a venue-calendar need:** only the public **venue page HTML + embedded JSON-LD** matches foghorn (the API is unusable for us). **But both the API and the web surface are blocked — see §6.**

## 2. Coverage breadth

The pleasant surprise: **all three foghorn jazz venues exist as venue pages**, but coverage is uneven:

- **Bird & Beckett** ([/v/10006662](https://www.bandsintown.com/v/10006662-bird-and-beckett-books-and-records)) — **sparse** (~2 upcoming surfaced despite weekly programming); the smallest/DIY room is the worst-covered.
- **Keys Jazz Bistro** ([/v/10327734](https://www.bandsintown.com/v/10327734-keys-jazz-bistro)) — "packed 2026–2027 schedule" (looks BIT-Pro-fed).
- **Mr. Tipple's** ([/v/10465546](https://www.bandsintown.com/v/10465546-mr.-tipple's-jazz-club)) — "packed 2026–2027 schedule".
- Rock rooms present too (Bottom of the Hill `/v/10001325`, The Independent `/v/10001466`).

SF city page is cited as "over 57 upcoming concerts/festivals/comedy" (a search snippet, **not** a clean page read — the live HTML 403s). **Better established-room coverage than expected; smallest DIY rooms thin.**

## 3. Genre wheelhouse

Clusters around **touring/promoted acts that maintain claimed Bandsintown profiles** and venues using **Bandsintown Pro for Venues** (self-publish — Keys & Tipple's "packed" schedules look Pro-fed). Where a room uses BIT Pro or hosts self-listing artists, coverage is good; where the room is DIY and the artists are local/new-creative who don't maintain profiles, coverage is **thin** — structurally inherent to the artist-claims-profile model (corroborated by user reviews complaining it "misses local talent"). For foghorn's small-room local jazz/new-creative wheelhouse: **partial coverage with gaps**, not a reliable full mirror.

## 4. Freshness

No published cadence SLA. Records carry `datetime`/`on_sale_datetime`; pages list 2026–2027. Freshness is **source-path-dependent** — BIT-Pro venues publish directly (likely fresh), artist-claimed events update when the artist does, unclaimed/aggregated entries lag. Could **not** diff a live SF show against a venue's own calendar — the venue/event HTML is 403-blocked. Indirect signal: B&B at ~2 upcoming vs. its real weekly cadence suggests stale/incomplete forward coverage for low-engagement rooms.

## 5. Dedup characteristics

- **Time:** `datetime` is ISO with offset → straightforward conversion to naive `start_local` (watch tz mapping).
- **Performer names:** `lineup[]` maps cleanly to `headliner_raw` (`lineup[0]`) + `support_raw` (rest); names often include "Trio/Quartet", which foghorn *keeps* — compatible.
- **Major hazard — artist-centric duplication:** because the API is artist-rooted, a 3-act bill returns as **3 separate events** (same venue + datetime, different headliner) if you query by artist. Our key includes `headliner_canonical`, so these **would not dedup** — 3 distinct rows. (The public venue/event pages avoid this — they're already venue-rooted — another reason the web surface beats the API for us.)
- **Venue names:** mostly match, but the `venue.name`→event-title replacement bug makes the **API** venue field unsafe for `venue_id` resolution; the stable `/v/{id}` web page is the reliable anchor.

## 6. Access mechanics

- **API:** mandatory `app_id`, **approval-gated** via a partnership program with bespoke terms; foghorn (non-artist, aggregation use) likely **wouldn't qualify**. No published numeric rate limits, but the [optimizing-usage guide](https://help.artists.bandsintown.com/en/articles/13142424-optimizing-api-usage) flags exactly our pattern: *"Large, regular traffic spikes that look like scheduled jobs"* and *"Avoid broad sweeps over the full internal artist catalog,"* reserving the right to throttle/suspend.
- **Artist-by-artist reality:** to use the API for our venues we'd have to maintain a per-venue artist roster — but you need the calendar to build the roster, and the API only answers by artist. **Chicken-and-egg non-starter.**
- **Public site anti-bot (live-verified):** `/c/san-francisco-ca`, the Mr. Tipple's venue page, and an event page all returned **HTTP 403 (Cloudflare)**. robots.txt has `Disallow: /` for **ClaudeBot, GPTBot, CCBot, Bytespider, Google-Extended, Amazonbot, …** (no path-level ban on `/c//v//e/`, but the edge blocks bot-like clients anyway). Getting the HTML+JSON-LD would require headless/residential-proxy — i.e. adversarial scraping.

## 7. Sustainability / ToS

Both viable paths are explicitly closed. [Data Application Terms](https://corp.bandsintown.com/data-applications-terms):

> "Unless you receive Bandsintown's written approval, **commercial uses are not permitted** …"

> "You shall not … **re-distribute or re-transmit the Bandsintown Content**." (feeding BIT data into foghorn's pipeline + republishing = redistribution)

> "You shall not use **any automated means (e.g., scraping, robots, etc.) other than the Bandsintown Data Applications** to access, query or otherwise collect the Bandsintown Content." (directly bars scraping the public `/c//v//e/` pages)

> "You may employ **session-based caching** … provided that you notify us … and update cached results upon any changes." (no persistent local store)

The general site [Terms](https://corp.bandsintown.com/termsprivacy) separately prohibit "spidering", "screen scraping", "database scraping". **Posture:** a deliberately closed garden for third-party aggregation (not legal advice).

## 8. Verdict

**Skip.** Bandsintown has the data foghorn wants — every target venue has a clean venue-calendar page with JSON-LD — but it is **wrong-shaped (artist-rooted API), access-gated (approval-only `app_id`), bot-walled (Cloudflare 403 + explicit crawler bans), and legally closed (ToS bars commercial use, redistribution, *and* scraping the very public pages that would fill the gap).** Every realistic ingestion path is blocked, so it fails the "easy/sustainable" benchmark rather than defining it.

---

### Confidence & caveats

- **Live-verified:** API endpoints/shape, `app_id` requirement, event-field list, ToS clauses, rate-limit "noisy traffic" guidance (read from official docs); **Cloudflare 403** on the SF city page + a venue page + an event page; robots.txt bot bans; existence of all 3 jazz venue pages + 2 rock venue pages (IDs/addresses via search snippets).
- **Documented-only / not verified (no `app_id`, pages 403):** the exact runtime JSON-LD on an event page (strongly evidenced, not live-read); the live per-week SF count (the "57" is a snippet); the `venue.name`→title replacement + "no price" (from a community API breakdown). Net confidence: **high on verdict** (ToS + access gates are unambiguous and official), medium on public-web data-richness details.
