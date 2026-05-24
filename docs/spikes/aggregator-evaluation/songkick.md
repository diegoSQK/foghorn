# Aggregator evaluation — Songkick

> Spike memo for [#29](https://github.com/diegoSQK/foghorn/issues/29). Evaluated 2026-05-23. Global API benchmark. **Verdict: Skip.**

**Candidate:** Songkick — `https://songkick.com`. Global, performer-centric concert listings. Evaluated with **no API key** (foghorn has none; see §6).

## 1. Data shape

**The API (documented, not key-verifiable by us)** is academically a near-perfect fit: JSON wrapped in `{ "resultsPage": { "results": { … }, "totalEntries", "page", "status":"ok" } }` ([response objects](https://www.songkick.com/developer/response-objects)). The **event object** has `start` `{date, time, datetime:"…-0800"}` and a `performance[]` array with explicit `"headline"`/`"support"` billing + venue address — i.e. it would hand us `headliner_raw`/`support_raw` pre-split. **Documented omissions that hurt:** no doors time, **no ticket/buy URL**, no price.

**Realistically usable shape for us (no key):**
- **JSON-LD:** could **not confirm** `MusicEvent` on current event pages (WebFetch strips `<script>`; curl is 406-blocked). The existence of third-party tools that *generate* JSON-LD from Songkick data hints it's thin/absent. **Unverified.**
- **.ics:** the only iCal feed is a **logged-in personal feed** (`/users/USERNAME/calendars.ics`, explicitly allowed in robots.txt) — your *tracked* events, not a venue or per-event feed. **No per-venue/per-event `.ics`.**
- **Metro/venue/event HTML** renders in a browser but is not scriptable (§6).

So the clean API is off the table and the public web is access-blocked — there is no realistically usable shape for foghorn.

## 2. Coverage breadth (SF)

The SF Bay Area metro page ([metro 26330](https://www.songkick.com/metro-areas/26330-us-sf-bay-area)) reports **~2,347 upcoming events** (29 pages); the sample week is dense with **touring-act venues** (Fillmore, Bottom of the Hill = 74 upcoming, The Independent, Bimbo's = 11, GAMH, The Chapel, Warfield, Yoshi's, SFJAZZ). But foghorn's three anchor jazz rooms are the headline result:

| Venue | On Songkick? | Upcoming | Reality |
| --- | --- | --- | --- |
| Keys Jazz Bistro ([4523553](https://www.songkick.com/venues/4523553-keys-jazz-bistro)) | Yes | **2** (Jun 6–7) | own site: 3–4+/week, multiple sets/night |
| Bird & Beckett ([31459](https://www.songkick.com/venues/31459-bird-and-beckett-books-and-records)) | Yes (legacy) | **0** upcoming; 368 past, last Apr 2026 | weekly jazz since 2002 |
| Mr. Tipple's | **No page found** | — | live music Wed–Sat/Sun |

Of foghorn's 3 anchors: 1 stale-empty, 1 wildly under-covered, 1 absent. The big touring rooms are well-populated; **the small local jazz rooms foghorn cares about are exactly where Songkick is weakest.**

## 3. Genre wheelhouse

Clusters in **touring rock/indie/pop/EDM/hip-hop + festivals** (sample: Paper Kites, Cut Copy, Benny Benassi, California Roots). Jazz / new-creative is **thin** — it surfaces only for rooms that feed ticketing partners, and partially even then. Bird & Beckett's 368-event "gigography" is backfilled *history* with **zero forward bookings** — Songkick captured the past but isn't fed the venue's actual calendar. For "what's on in SF jazz this week", this genre is Songkick's blind spot.

## 4. Freshness

No exposed "last updated" timestamp; spot-checks reveal **lag and gaps, not real-time accuracy**. Keys = 2 upcoming vs. 5+ named shows on its own site in the same two weeks; Bird & Beckett = 0 upcoming despite weekly programming (effectively abandoned on-platform). Freshness depends entirely on whether a venue/promoter feeds Songkick via a ticketing integration — indie jazz rooms mostly don't.

## 5. Dedup characteristics

- **Performer names** are a *plus*: canonical artist `displayName` with explicit `headline`/`support` billing — cleaner than free-text. But public titles read "Artist at Venue", and "X Quartet / & Her Band / feat." forms still need our `canonicalize()` handling (Songkick won't pre-split those).
- **Times are the hazard:** public pages show **"Doors open: 20:00"** and **omit the onstage/start time** — so Songkick's "time" is often *doors*, which misaligns with `start_local` and corrupts the natural key. Multi-set jazz nights (Keys lists 3 sets) have no clean time model here.
- **Venue names** map fine for big rooms (full address present), useless for the absent/stale small rooms.
- **Worst-case:** doors-vs-start mismatch on essentially every show + multi-set nights collapsing → both false dupes and missed shows.

## 6. Access mechanics

- **API:** key-based, but **new keys are not being issued** — quote: *"We are currently not approving API requests for student projects, educational purposes or hobbyist purposes,"* and *"Use of the Songkick API will be subject to the standard terms of our partnership agreement and a license fee"* ([developer](https://www.songkick.com/developer), [support](https://support.songkick.com/hc/en-us/articles/360012423194-Access-the-Songkick-API)). Partner-only, paid. **foghorn cannot get a key.**
- **Anti-bot (live-verified):** scripted `curl` returns **HTTP 406 Not Acceptable** regardless of UA/Accept headers, served by Fastly (`x-edge-pop: Fastly/US-West/PAO`) — a hard edge rejection, no body returned.
- **robots.txt (verified):** `Disallow: /` for 30+ bots **including ClaudeBot, GPTBot, PerplexityBot**; only sanctioned feed is `Allow: /users/*/calendars.ics`.
- **Net:** public-page scraping is neither realistically scriptable (406 wall) nor permitted (robots.txt + ToS).

## 7. Sustainability / ToS

Explicitly hostile to programmatic access ([terms](https://www.songkick.com/info/terms)):

> **§9.8** — "Use any robots, botnets, scrapers or spiders … to retrieve, index, scrape, data mine or in any way reproduce/republish … the Services, without our express prior written consent"

> **§9.9** — "Use any automated analytical technique aimed at analysing text and data in digital form …" (reserves rights under EU DCD 2019/790)

> **§9.10** — "Use any part of the Services for commercial purposes without our written consent" (personal use only)

Scraping is contractually prohibited *and* technically blocked; the API is the only legitimate door and it's closed. **No compliant, sustainable ingest path without a paid partnership.**

## 8. Verdict

**Skip.** A strong data *model* (clean headline/support billing, ISO datetimes) wrapped in an *inaccessible* delivery surface — no obtainable key, a ToS that bans scraping/data-mining, and a Fastly edge returning 406 to all scripted clients. Even setting access aside, the coverage is the wrong shape: performer/touring-act centric and skewed to big rooms, while foghorn's anchor jazz venues are stale, under-covered, or absent.

---

### Confidence & caveats

- **Live-verified:** robots.txt + the `calendars.ics` allow rule; HTTP 406 hard-block + Fastly headers; metro/venue/event pages render via WebFetch (Keys 2 upcoming, B&B 0 upcoming/368 past, Bottom of the Hill 74, Fillmore 45, Bimbo's 11, Mr. Tipple's not found); "Doors open: 20:00" format with no onstage time; ToS §9.8–9.10 verbatim; the "partner-only + license fee" key notice.
- **Documented-only / not key-verifiable:** full API event/venue schema; API rate limits (undocumented).
- **Could not verify:** whether event pages emit `MusicEvent` JSON-LD (indirect signal suggests thin/absent — unconfirmed). Note: WebFetch reached pages where curl got 406, so a foghorn job using a standard HTTP client would hit the 406 wall reproduced here.
