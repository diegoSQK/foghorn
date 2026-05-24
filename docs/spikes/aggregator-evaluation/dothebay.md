# Aggregator evaluation — DoTheBay

> Spike memo for [#29](https://github.com/diegoSQK/foghorn/issues/29). Evaluated 2026-05-23. **Verdict: Maybe (leaning Skip as an unlicensed source).**

**Candidate:** DoTheBay — `https://dothebay.com`. SF/Bay everything-events aggregator, indie/rock/nightlife-leaning. Owned/operated by Noise Pop Industries on the DoStuff Media platform (sister sites `do312.com`, `do206.com`, etc.).

## 1. Data shape

**Preferred shape: an undocumented internal JSON API.** `https://dothebay.com/events.json` returns `200` `application/json` — the DoStuff AJAX backend (`{"events":[…], "paging":{…}, "api_version":"0.005"}`). Date-addressable (`/events/2026/5/23.json`, `/events/today.json`, `/events/tomorrow.json`) with `?page=N` pagination (25/page, `paging.total_pages` provided).

Per-event fields map almost 1:1 to `ScrapedShow`:

| `ScrapedShow` | DoTheBay JSON |
| --- | --- |
| `headliner_raw` | `title` (and `artists[]` when populated — see §5) |
| `start_local` | **`tz_adjusted_begin_date`** (correct Pacific) — **not** `begin_time`, which carries a spurious `-06:00` Chicago offset (platform artifact; using it shifts every show 2h) |
| `ticket_url` | `buy_url` (sometimes null) |
| `price_text` | `ticket_info` (e.g. `"$20-30"`) + `is_free` |
| `source_url` | `permalink` |
| venue | nested `venue` object: stable numeric `id`, `title`, `permalink`, `full_address`, lat/lng, `capacity` |
| support | `artists[]` array (`title`, `permalink`, hometown, spotify…) — ready for headliner/support split **but frequently empty** |

Other shapes are **not usable**: `/events.rss`, `/events.ics`, `/events.xml` routes exist but return **HTTP 406** (content-type negotiated, no body served). Event detail pages carry **no schema.org JSON-LD** — plain HTML only. So the JSON API is the one good door, and BeautifulSoup isn't even needed (httpx + json).

## 2. Coverage breadth

Live sample, **May 23–29 2026**, pulled from the JSON API (all pages, deduped by event id): **534 total events, 239 of them music, across ~87 distinct music venues** in one week.

Healthy mix of established rooms and a long tail — top music venues by count: Make-Out Room (13), SFJAZZ Center (8), Yoshi's Oakland (8), Bottom of the Hill (7), The UC Theatre (6), Ivy Room (6), Freight & Salvage (5), Rickshaw Stop (5), Great American Music Hall (4), The Independent (4), The Chapel (4). Geography spans SF, East Bay, and North Bay. **This is a strong Phase-5 rock/indie breadth signal** — far more rooms than we'd hand-roll.

## 3. Genre wheelhouse

Everything-aggregator; music is the largest slice (239 of 534 in the sample week; remainder Theatre/Comedy/Film/DJ/Variety). Within music the cluster is **indie / rock / electronic / nightlife** (consistent with its Noise Pop ownership). **Jazz / new-creative is present but secondary:** SFJAZZ, Yoshi's, Freight & Salvage, and Bird & Beckett all appear — but it is a rock/indie source that *also* carries some jazz, not a jazz source. Keys Jazz Bistro and Mr. Tipple's did **not** appear in the sample week (2 of foghorn's 3 anchors absent).

## 4. Freshness

**Live and current.** Sitemap `lastmod` = today; entries carry exact ISO timestamps (not date-only). Bird & Beckett present with 4 shows this week (e.g. "Dave Parker Septet plays Mingus and more", 05-29 19:30), venue labeled by full legal name "Bird & Beckett Books & Records".

One unresolved freshness flag: the Dave Parker show appears as "**Septet** … 19:30" on DoTheBay vs. "**Quintet** … 5:30pm" on the only `birdbeckett.com` page reachable — **but that B&B page was a stale 2024 listing**, so this may be a wrong-page comparison rather than a DoTheBay error. Bird & Beckett itself uses Quartet/Quintet/Septet inconsistently across dates. Needs a check against B&B's live 2026 calendar before treating it as a data-quality knock.

## 5. Dedup characteristics

Against our key `(venue_id, start_local_date, start_local_time, headliner_canonical)`, dedup would be **partial**:

- **Times are exact HH:MM** (good), but the `begin_time` tz trap (§1) breaks dedup wholesale if the wrong field is used. `doors` was always false/absent; `begin_time` appears to be show time.
- **Venue names are full legal names** ("Bird & Beckett Books & Records") → exact-string venue matching fails; needs a `venue.id`/`permalink` → `venue_slug` alias map (the stable numeric id makes this clean).
- **Headliner extraction is the weak point.** `artists[]` is reliable for big rooms (SFJAZZ → `["Makaya McCraven"]`) but **empty for the small jazz rooms** (every B&B event had `artists: []`), forcing free-text `title` parsing.

Worst-case "same show, won't auto-dedup":
1. **B&B 05-29:** our scraper → `dave parker septet`; DoTheBay `title` → `dave parker septet plays mingus and more`. Different canonical → duplicate.
2. **SFJAZZ "Terence Blanchard & Ravi Coltrane":** DoTheBay → `terence blanchard ravi coltrane`; a venue scraper recording only the headliner → `terence blanchard` (or `… quartet`). Per our own rule (suffixes/`&` not stripped), no auto-dedup.

## 6. Access mechanics

**Wide open and trivially scriptable.** No auth, no key. Stock `python-httpx`, `curl`, and even no-UA requests all returned `200`; 8 rapid sequential hits showed no rate-limiting; no CAPTCHA, no JS/managed challenge (Rails app behind Cloudflare in passive mode). The initial WebFetch 403s were that tool's specific fingerprint, not a general block. One polite daily poll of `/events/today.json` + paging is ~5 requests for a busy day.

## 7. Sustainability / ToS

**This is the blocker.** The DoStuff ToS (`https://dothebay.com/tos`) contains two clauses that cut directly against ingestion:

> "You agree not to: … **scrape, harvest, or misuse content or data**…"

> "You may access and use the Services for your **personal, non-commercial use only**. Except as expressly permitted, you may not reproduce, distribute, modify, or exploit any portion of the Services."

`robots.txt` does **not** disallow `/events` or `.json` (only `/assets/`, `/search`, `/latest`, `/*view=map`, etc.) — but the ToS prohibits exactly the activity foghorn would perform. There is **no public developer API, partnership program, or licensed feed** advertised (only a community GitHub wrapper). Posture (not legal advice): the open JSON tempts a build, but unlicensed ingest runs against the plain text of the ToS. The clean path is to **ask DoStuff/Noise Pop for permission or a feed**.

## 8. Verdict

**Maybe, leaning Skip.** Engineering-wise it is the best-shaped candidate evaluated — a stable JSON API with venue/artist/time/ticket fields, no auth, no anti-bot, easily polled daily — and it carries SFJAZZ, Yoshi's, Freight, and Bird & Beckett. But the ToS explicitly bars scraping/harvesting and restricts use to personal/non-commercial, and it misses 2 of foghorn's 3 anchor jazz rooms, so as an *unlicensed* source it's a poor fit for the jazz mission even though it'd be a strong Phase-5 rock/indie feed **if a permission/feed arrangement were secured**.

---

### Confidence & caveats

- **Verified live:** the JSON API + schema (534 real events parsed); 406 on rss/ics/xml; no JSON-LD on the detail page; robots.txt; ToS clauses (quoted from live `/tos`); no auth / no rate-limit / no UA block; B&B present, Keys + Tipple's absent this week.
- **Needs a second look:** (a) the B&B Septet-vs-Quintet / time discrepancy — likely a stale-2024-page comparison, confirm against B&B's live calendar; (b) "Keys/Tipple's absent" is this-week-only, not proof of permanent zero coverage; (c) no rate-limit in a small burst ≠ none at scale; (d) ToS read is posture, not legal advice.
