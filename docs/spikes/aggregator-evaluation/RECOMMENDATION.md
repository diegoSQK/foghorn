# Aggregator ingest spike — recommendation

> Synthesis for [#29](https://github.com/diegoSQK/foghorn/issues/29). Evaluated 2026-05-23. Feeds the PM thread's Phase 5+ re-scope decision. Per-candidate detail in the sibling memos.

## The decision this informs

The current plan has **Phase 5** (hand-rolled rock/indie + East Bay per-venue scrapers) and **Phase 6** (LLM-assisted per-venue scraping as the scaling lever). Diego asked whether third-party **aggregator ingest** could replace or augment that work. Five candidates were evaluated against a fixed rubric.

## In / out

| Candidate | Verdict | One-line why |
| --- | --- | --- |
| **Bay Improviser** | ✅ **In (Recommend)** | The one genuinely ingestible, high-relevance source: robots-permissive HTML calendar + per-event iCal/gCal, covering DIY/creative-music rooms per-venue scrapers will never reach. |
| **DoTheBay** | ⚠️ **Conditional (Maybe→Skip)** | Cleanest *engineering* (open JSON API, no anti-bot) but ToS bars scraping + restricts to personal/non-commercial. **In only if** a permission/feed arrangement is secured with DoStuff/Noise Pop. |
| **Songkick** | ❌ Out (Skip) | No obtainable API key (partner-only + license fee), ToS §9.8 bans scraping/data-mining, Fastly edge 406-blocks scripted clients, and small-jazz-room coverage is stale/absent. |
| **Bandsintown** | ❌ Out (Skip) | Artist-rooted API (wrong shape) + approval-gated `app_id`; public venue pages have the data but are Cloudflare-403'd and the ToS bars commercial use, redistribution, *and* scraping. |
| **What's Poppin** | ❌ Out (Not feasible) | A YouTube talk show; no web-readable calendar exists (audio/flyers only — out of ingest scope). |

No clearly-better sixth candidate surfaced. The nearest adjacent ("San Francisco Bay Area Live Music") was checked and has no events calendar.

## The headline finding

**Aggregator ingest does not replace per-venue scraping for foghorn — it can only narrowly augment it.** The two clean, well-modeled *global* APIs (Songkick, Bandsintown) — the "what does the easy path look like" benchmarks — are both **closed to a small unlicensed aggregator** on access *and* legal posture, *and* their coverage skews to touring acts at big rooms, precisely away from foghorn's small-jazz-room wheelhouse. The only genuinely open, ingestible, on-target source is a **volunteer-run community HTML calendar** (Bay Improviser) — which is additive coverage of the creative-music long tail, not a replacement for venue scrapers, and it carries data-quality/dedup caveats that *increase* engineering work rather than reduce it.

So the premise being tested — "aggregators are a shortcut to 100+ venues" — **does not hold** for this product's genre and access constraints. The real scaling lever remains **Phase 6 (LLM-assisted per-venue scraping)**, not aggregator ingest.

## Recommended Phase 5+ re-shape: **Augment** (keep per-venue; add one narrow aggregator source)

Concretely:

1. **Keep Phase 5 as-is** (hand-rolled per-venue rock/indie + East Bay). It remains the backbone and the source of truth.
2. **Add a single new ingest source for Bay Improviser** — *not* a per-venue scraper, a distinct "aggregator source" alongside `REGISTERED_SCRAPERS`. Shape: **HTML date-range fetch (`calendar.aspx?s=&e=`) → parse embedded `gCal` query string per event** (one fetch yields structured fields), with the `?ex=ical&evtId=` `.ics` as fallback. Reuse `httpx` + `beautifulsoup4` (both already deps).
3. **Treat DoTheBay as a non-engineering action item:** a permission/feed conversation with DoStuff/Noise Pop, *not* a ticket to scrape. If permission lands, it's a strong Phase-5 *rock/indie* backfill (small build — the JSON API is ~1:1 with `ScrapedShow`). Until then, leave it out.
4. **Drop aggregators from the Phase 6 framing.** Phase 6 stays LLM-assisted *per-venue* scraping; aggregator ingest is not the scaling lever the spike hoped for.

### What Bay Improviser ingest requires (the new infrastructure)

Bay Improviser is community-entered free text, so it needs three things our current exact-natural-key dedup doesn't have:

- **Venue-name → `venue_slug` alias map** (e.g. `Mr Tipple's, 39 Fell St SF` → `mr_tipples`).
- **UTC→`America/Los_Angeles` conversion** at ingest (its iCal/gCal stamps are UTC `…Z`).
- **A fuzzy secondary dedup pass** for shared venues (same `venue_id` + date + time-window overlap + token overlap on names), because free-text headliner blobs and one-off improv-ensemble names will never match a venue scraper's clean headliner on the exact natural key. **Existing per-venue scrapers stay authoritative for shared venues** (the spike found Bay Improviser disagreeing with Bird & Beckett's own site on both ensemble name and start time).

This fuzzy-dedup pass is the real cost driver — and it's reusable scar tissue if we ever add a second aggregator.

### Implementation cost estimates

| Source | Build cost | Notes |
| --- | --- | --- |
| **Bay Improviser** | **Medium** | Fetch+parse alone is Small; the venue-alias map + UTC conversion + fuzzy secondary dedup pass push it to Medium. Dedup work is one-time infrastructure reusable by future aggregators. |
| **DoTheBay** | **Small (if permission lands)** | Open JSON API, ~1:1 field map, no anti-bot. The cost is the *permission conversation*, not the code. N/A until then. |
| Songkick / Bandsintown | — | Not pursued. |

## One open question for Diego (before tickets get filed)

**Do we accept aggregator-discovered venues into the DB automatically, or maintain a curated venue allow-list and ingest only events at venues we've already added?**

This is the call that shapes the Bay Improviser ticket. Bay Improviser surfaces dozens of DIY/house/one-off spaces (e.g. "The Tiger Garage, a private studio in south Berkeley"). Two postures:

- **Auto-accept discovered venues** → broad coverage of the creative-music long tail on day one, but messier data (incomplete addresses/regions, transient rooms) and a `venues` table that grows without curation — which interacts with the Phase 3.2 region/neighborhood filters (a venue with no clean neighborhood breaks those facets).
- **Curated allow-list** → clean, filterable data, but Bay Improviser becomes mostly a *backfill* for venues we already chose to track, discarding the long-tail discovery that is its main value.

Recommendation: lean **allow-list to start** (keeps the region/neighborhood facets coherent and the watchlist meaningful), with a lightweight "unmatched venue" review queue so the long-tail rooms surface for a human curation decision rather than being silently dropped. But this is a product call, not an engineering one — hence the question.

---

*Next action: PM thread re-scopes Phase 5/6 in `PROJECT_PLAN.md` from this memo. The shipping agent intentionally does not touch the plan (per #29 "Not in scope").*
