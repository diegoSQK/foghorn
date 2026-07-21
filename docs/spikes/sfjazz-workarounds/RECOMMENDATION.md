# SFJAZZ workarounds spike — recommendation

> Second spike on surfacing SFJAZZ despite its no-scraping stance + Cloudflare wall. Evaluated 2026-07-21. Builds on the original SFJAZZ deferral (`PROJECT_PLAN.md` → Deferred / still-outstanding) and the May 2026 [aggregator-evaluation spike](../aggregator-evaluation/RECOMMENDATION.md). Feeds the decision to build a feature-flagged SFJAZZ ingest source.

## The question this spike answers

Can foghorn surface SFJAZZ shows given (a) the Cloudflare *managed challenge* that 403s every plain HTTP client and (b) SFJAZZ's no-scraping posture — in a way that stays safe to keep **off** if/when foghorn is hosted publicly?

## What changed since the original deferral

- **The team now has a "find the clean backing surface" playbook.** Two venues audited as unscrapeable were cracked by going around the front door — SF Symphony via a public Algolia index (the Queue-it wall only fronts the calendar page, not the data host), SF Philharmonic via City Box Office. SFJAZZ plausibly has an equivalent, but confirming it needs browser network-inspection and it remains *SFJAZZ's own data under their no-scraping stance*.
- **foghorn has an aggregator ingest tier now.** Bay Improviser landed under the quarantine-with-flag posture, and `AggregatedEvent` carries `support_raw` / `ticket_url` / `price_text` (group-feed work). A new licensed feed plugs straight into this.
- **foghorn is local-first.** Single-user, laptop + phone over Tailscale; public hosting is deferred. This materially changes the ToS calculus per avenue — the legal objections that sink some options only bite once foghorn is public.

## Avenues evaluated

| Avenue | Verdict | Why |
| --- | --- | --- |
| **JamBase licensed feed** | ✅ **Recommend (POC)** | A *licensed* ("sourced, not scraped") events API with strong, room-level SFJAZZ coverage; **no headless infra**; plugs into the aggregator tier. Free Developer / 14-day eval tier covers the POC; the ongoing-display license clause + paid-for-public are the open items — both handled by the flag. |
| Direct headless scrape of `sfjazz.org` | ⏸️ **Deferred (documented fallback)** | First-party + free, and genuinely revived by the local-first frame (its only real knock — ToS exposure — bites only when public, which the flag handles). But it introduces foghorn's **first Playwright dependency** and carries an unverified question: whether headless clears the *managed* challenge (the original note only tested plain HTTP). Deferred per the decision to avoid headless as long as possible. Remains the fallback if JamBase's license doesn't clear. |
| Backing-API discovery (SF Symphony pattern) | ❔ Not pursued | Plausible (an `admin.sfjazz.org` subdomain + a data-driven calendar exist) but needs browser network-inspection to confirm, and it's still SFJAZZ's own data under their no-scraping stance — same ToS class as the direct scrape, without JamBase's licensing cleanliness. |
| Bandsintown | ❌ Out | Venue pages Cloudflare-403 to scripted clients (the *same wall as SFJAZZ* → needs headless anyway); the API is `app_id`-gated **and** artist-rooted (you need the calendar to build the artist list to query the calendar). Local-first relaxes the ToS but not the access wall — and if you're running headless anyway, the source beats the middleman. Confirmed Skip in the May spike. |
| Songkick | ❌ Out | Fastly edge **406-blocks every scripted client**; no obtainable API key (partner-only + license fee). The one sanctioned door is the logged-in personal `calendars.ics` — *tracked* events only, can't enumerate a venue calendar. Access-blocked regardless of public/private. Confirmed Skip in the May spike. |

## Headline finding

Under the local-first frame the real contest is **JamBase vs. a direct headless scrape** — Bandsintown and Songkick are out on **access**, not merely ToS, so the "we're not public yet" reframe does not revive them. JamBase wins as the path that (a) avoids a headless/Playwright dependency, (b) is licensed and therefore the *right long-term answer for a public foghorn*, and (c) has genuinely good, room-level SFJAZZ coverage. The direct headless scrape is the free/first-party fallback, deliberately deferred.

## Coverage evidence (public JamBase site, 2026-07-21)

- **Miner Auditorium @ SFJAZZ Center** — 17 multi-night engagements, ~30+ performances, spanning **Jul 2026 → May 2027** (Joshua Redman, Wynton Marsalis, Cécile McLorin Salvant, John Scofield, Kurt Elling, Chucho Valdés, …). Robust and current.
- **Joe Henderson Lab @ SFJAZZ Center** — its own schedule (the smaller room).
- Plus **SFJAZZ Collective** and the **SF Jazz Festival**.
- Room-level granularity — finer than SFJAZZ's own front page would hand a scraper.

Coverage is *not* the risk here (SFJAZZ is a flagship room, not the small-jazz-room blind spot that sank the aggregators in May). The license is.

## Access, license & the flag

- **Product:** JamBase Data — licensed events API + feeds + a data MCP. ~616k artists / 91k venues / ~5M performances, "60+ sources."
- **Free Developer tier** (pricing page): 1,000 calls/mo, 3,600/hr, 6 months forward, **non-commercial**, **attribution required**. A nightly poll of one venue is trivially under quota.
- **14-day Trial / Evaluation ToS** (read in full — it's a PDF): evaluation-only, no commercial use, no third-party sharing, **delete data on termination**. Fine to *build and validate* a POC under; cannot back a persistent app.
- **Paid tiers:** Startup $500/mo → Pro $1,500/mo; any commercial / public use requires a **Commercial Data Usage Agreement**.
- **The flag is JamBase's commercial line, drawn in code.** `FOGHORN_SFJAZZ_ENABLED` (default **off**): **on** for the local single-user instance (non-commercial + attribution), **off — or licensed —** for any public deployment. Exactly the boundary requested, now contract-backed rather than merely cautious.

## Open item (the caveat this memo ships with)

Whether the **Developer-tier license permits *ongoing* non-commercial display** (vs. the trial's eval-only stance) could not be machine-read this session — the Master Services Agreement is a JS-rendered page (plain fetch returns only metadata) and the browser extension was not connected. **Resolve before productionizing**, via either: read the in-account Developer terms after the free signup, or email `api@jambase.com` (they explicitly invite non-profit/student discussion). **The POC itself is unaffected** — it runs legitimately under the free Developer / 14-day eval terms.

## Recommended approach

Build a **feature-flagged JamBase SFJAZZ ingest source, POC-first**:

1. **POC** under the free Developer / eval key: validate the live payload, SFJAZZ coverage completeness (both rooms, showtimes, timezone, ticket URLs), and the mapping into the aggregator tier.
2. **Gate productionization** on (a) a POC data-quality pass and (b) the Developer-tier display-license confirmation above.
3. Ship behind **`FOGHORN_SFJAZZ_ENABLED`** (default off). Render **"Data via JamBase"** attribution on JamBase-sourced rows (free-tier requirement).
4. Keep the **direct headless scrape documented as the fallback** if the license doesn't clear.

## Engineering fit

- Plugs into the **existing aggregator tier**; SFJAZZ is already a seeded venue, so events resolve to it (**no quarantine**). `AggregatedEvent` already carries `support_raw` / `ticket_url` / `price_text`.
- **httpx / JSON only — no new heavyweight dependency** (preserves the no-headless posture).
- Attribution rides on the `source_url` / provenance foghorn already stores per row.
- Nightly poll of one venue sits far under the free quota.

## Next action

PM files the POC ticket (gated on Diego providing a JamBase Developer key). A coding agent builds the POC; PM re-scopes the SFJAZZ item in `PROJECT_PLAN.md` → Deferred once it lands.
