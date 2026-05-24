# Aggregator evaluation — Bay Improviser

> Spike memo for [#29](https://github.com/diegoSQK/foghorn/issues/29). Evaluated 2026-05-23. **Verdict: Recommend (with a dedup-hardening caveat).**

**Candidate:** Bay Improviser — "Bay Area Improviser's Network", `https://www.bayimproviser.com`. A community calendar for "Experimental, Improvised, Noise, Electronic, Free-Jazz, Avant Garde, Modern Composition, and Other Forms of Contemporary Sound" in the SF Bay Area. Descends from the print **Transbay Creative Music Calendar** (running ~2001+; Matt Ingalls et al.), now an actively maintained ASP.NET site (maintainer contact `johnlee@bayimproviser.com`). **Relevance to foghorn: HIGH** — directly in the jazz-adjacent / new-creative wheelhouse.

## 1. Data shape

Custom **ASP.NET (`.aspx`) database-driven site** (`__VIEWSTATE`/`GENERATOR` markers present). **No public JSON API and no single combined RSS/iCal feed** — `calendar.aspx?ex=ical` with no event id returns HTML, not `text/calendar`. But there IS structured per-event access:

- **Per-event iCal export:** every event row carries `…/calendar.aspx?ex=ical&evtId=NNNNN`. Verified live (`evtId=23037` → `200`, `Content-Type: text/calendar`, valid `BEGIN:VCALENDAR` with `DTSTART`/`LOCATION`/`SUMMARY`/`UID`/`ORGANIZER`).
- **Per-event Google Calendar links:** `✚gCal` links carry `dates=`, `text=`, `location=`, `details=` query params — the same fields, parseable straight off the HTML with no second fetch.
- **Date-range query:** `calendar.aspx?s=MM/DD/YYYY&e=MM/DD/YYYY` (verified — one page covers ~6 weeks).
- **Per-event detail pages:** `EventView.aspx?e=NNNNN` → stable `source_url`.

**Preferred ingest approach:** scrape the date-range HTML calendar (`calendar.aspx?s=…&e=…`) and parse the embedded `gCal` query string per event (one fetch yields all structured fields); fall back to the `?ex=ical&evtId=` `.ics` where needed. The HTML is the source of truth; the iCal/gCal links ride on it.

## 2. Coverage breadth

Live sample, week of 5/24/2026 (default view spans ~5/23–7/7): **~67 events, ~41 distinct venue name-heads.** A mix of recognizable rooms (Center for New Music, The Lab, ODC Theater, Gray Area, CCRMA/Stanford, Mills/Littlefield, Noe Valley Ministry, Ivy Room, Artists' Television Access) and a long DIY tail (Forte House, The Tiger Garage "a private studio in south Berkeley", West Oakland Sound Series, Bric-a-Brac) — spread across SF, Oakland, Berkeley, Palo Alto/Stanford, Albany, Vallejo. **The bulk of these rooms foghorn's per-venue scrapers will never reach** — this is purely additive coverage for the creative-music end. Venue overlap with foghorn: **Bird & Beckett** and **Mr Tipple's** both appear; Keys Jazz Bistro did not this week.

## 3. Genre wheelhouse

Clusters firmly in **improvised / free-jazz / experimental / new-creative / electroacoustic / new-composition** (sample: Rova Saxophone Quartet, Composers Inside Electronics, sfSound, Earplay, noise/DIY bills) plus straight-ahead/chamber jazz where it intersects the creative scene. **The single most on-target source evaluated for the avant/creative end that per-venue scrapers miss.** It will *not* cover mainstream commercial straight-ahead rooms well — but that's not its job here.

## 4. Freshness

**Actively maintained** — footer `© 2026`, events dated forward from today into July 2026. Community **event-submission** model, so freshness tracks promoter diligence; the 20+ year Transbay lineage lowers abandonment risk.

**Bird & Beckett spot-check — mismatch found (important):** for the same Fri 5/29/2026 show, Bay Improviser lists `DAVE PARKER SEPTET` at **7:30 PM** (iCal `DTSTART:20260530T023000Z`) while `birdbeckett.com` lists "The Dave Parker **Quintet**" at **5:30–8:00 pm**. Different ensemble noun *and* different start time. Treat Bay Improviser's times/lineups as approximate, not authoritative, for venues foghorn scrapes directly — our own scrapers stay the source of truth on shared venues.

## 5. Dedup characteristics

A **notable dedup hazard** against `(venue_id, start_local_date, start_local_time, headliner_canonical)`:

- **Timezone:** iCal/gCal timestamps are **UTC (`…Z`)**; ingest must convert UTC→`America/Los_Angeles` (PST/PDT) to get `start_local`. Any off-by-one-hour/day error corrupts the date/time key components.
- **Headliner is a free-text blob, not a clean headliner.** `SUMMARY`/`text=` values look like `Grex, Murder Murder, Rip Room at Bric-a-Brac SF` or `Donald Robinson/Bruce Ackley/Eric Hunt` — no headliner/support split; `canonicalize()` produces long multi-name strings that won't match a venue scraper's clean headliner.
- **Venue-name conventions differ** (`Mr Tipple's, 39 Fell St SF` with no possessive spacing) → needs a venue-name → `venue_slug` alias map.

Worst-case "same show, won't auto-dedup":
1. **Dave Parker, 5/29 B&B:** our scraper → `the dave parker quintet` @ 17:30; Bay Improviser → `dave parker septet` @ 19:30 — different canonical *and* different time. Two rows.
2. **Ad-hoc improv ensembles with one-off names** (`Donald Robinson/Bruce Ackley/Eric Hunt`, a name that exists for one night) vs. however the venue bills it → essentially never matches. The classic improv-calendar failure: nightly-changing ensemble names defeat string dedup entirely.

Net: ingesting alongside venue scrapers will produce **duplicate rows for shared venues** unless we add venue-name aliasing + a fuzzy secondary dedup pass (same venue + date + time-window overlap + token overlap). For the DIY venues foghorn does **not** scrape, dedup is a non-issue — it's purely additive.

## 6. Access mechanics

**No auth, no key, no anti-bot.** Full 135 KB calendar pulled with a plain `curl` + UA (`200`); all event data is server-rendered HTML (jQuery present but not required); per-event iCal export also `200`. No rate-limit headers observed. **Realistically scriptable** with the backend's existing stack — `httpx` for the date-range page, `beautifulsoup4` to pull event rows + embedded `gCal`/`iCal` query strings, optional `icalendar` for the `.ics`. One daily poll of one (or a couple paged) URLs covers the look-ahead window. `__VIEWSTATE` is present but not needed for GET navigation.

## 7. Sustainability / ToS

- **robots.txt** (verified): `User-agent: *` / `Allow: /`, only `/.well-known/` and `/apple-app-site-association` disallowed → **calendar is explicitly crawl-permitted.**
- A **Terms link exists in the footer but `/terms.aspx` did not render on fetch** — automated-reuse language is **unverified**; check before shipping ingest.
- **Community/volunteer-run** with an event-submission model. Etiquette matters: one polite daily poll, honest UA, cache, and link back via `source_url` (stable `EventView.aspx?e=N`). Small-site disappearance risk exists but is mitigated by 20+ years of continuity. Posture: respectful, low-volume, attribution-friendly (not legal advice).

## 8. Verdict

**Recommend (with a dedup-hardening caveat).** Highest-relevance source evaluated for foghorn's jazz/new-creative wheelhouse — actively maintained, no auth/anti-bot, robots-permitted, server-rendered HTML with bonus per-event iCal/gCal structured fields, surfacing dozens of DIY/creative rooms per-venue scrapers will never reach. The catch: it's free-text/community-entered, so it needs venue-name aliasing, UTC→local conversion, and a fuzzy secondary dedup pass to coexist with existing scrapers (which stay authoritative for shared venues like B&B and Mr Tipple's given the verified Septet/Quintet + time mismatch).

---

### Confidence & caveats

- **Verified live:** ASP.NET site; ~67 events / ~41 venues for week of 5/24; per-event iCal returns valid `text/calendar`; gCal links carry structured UTC dates; date-range `?s=&e=` works; robots.txt crawl-permissive; plain curl gets full content (no anti-bot); B&B and Mr Tipple's both appear; the Dave Parker Septet-vs-Quintet / 7:30-vs-5:30 mismatch confirmed against `birdbeckett.com`.
- **Not fully verified / needs a second look:** (1) Terms-of-Service automated-access language (`/terms.aspx` didn't render); (2) whether `?s=&e=` has a max window (to size the daily poll); (3) build + validate the venue-alias + fuzzy-dedup rules against a few weeks of real overlap with the B&B / Mr Tipple's scrapers; (4) no combined all-events `.ics` found, but only the obvious `?ex=ical` shape was tested.
