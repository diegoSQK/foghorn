# SFJAZZ backing-API recon — is there an openly-served calendar endpoint?

> Phase 1 of #91, run 2026-07-21. Narrow question: does SFJAZZ expose a backing data path
> that returns its calendar to a **plain HTTP client with no bot-challenge on it**?
> Companion to [RECOMMENDATION.md](RECOMMENDATION.md) (the JamBase-vs-headless spike, #89).

## Verdict — **No.**

**There is no challenge-free path to SFJAZZ's calendar reachable by a plain HTTP client.**
Cloudflare's *managed challenge* fronts the entire `www.sfjazz.org` origin: every HTML route
probed returned `403` with the response header `cf-mitigated: challenge` and a
"Just a moment…" interstitial body. This includes routes their own `robots.txt` permits
(`/calendar/`, `/sitemap.xml`).

Per the ticket's hard line, each challenge was **recorded and abandoned** — never retried,
never circumvented. No headless browser was used anywhere in this work, not even for
discovery, and no User-Agent spoofing or fingerprint games were attempted.

Phase 2 (the scraper) is therefore **not built**. This is a complete result, not a failure
to route around.

## Rules of engagement

- Plain `httpx`, one request per route, redirects followed, ~1s spacing — **6 requests total**.
- Honest identifying User-Agent throughout: `foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)`.
  Deliberately *not* a spoofed browser UA — if the honest bot is blocked, that **is** the answer.
- Any challenge / 403 / bot-wall = hard dead end for that route, recorded and walked away from.

## What was probed

| Route | Status | `cf-mitigated` | Result |
|---|---|---|---|
| `/robots.txt` | 200 | — | Served (97 bytes, `text/plain`). Challenges typically exempt it. |
| `/` | 403 | `challenge` | "Just a moment…" interstitial |
| `/calendar/` | 403 | `challenge` | "Just a moment…" interstitial |
| `/calendar/?month=8.2026` | 403 | `challenge` | "Just a moment…" interstitial |
| `/sitemap.xml` | 403 | `challenge` | "Just a moment…" interstitial |
| `/tickets/productions/` | 403 | `challenge` | "Just a moment…" interstitial |

### The `robots.txt` finding (worth recording precisely)

```
user-agent: *
sitemap: https://sfjazz-redesign-stage.adagetech.net/xmlsitemap
Disallow: /umbraco/
```

Their **published crawl policy is permissive** — for all user-agents it disallows only
`/umbraco/`. The restriction that actually bites is the WAF challenge, which is applied
origin-wide regardless of what `robots.txt` permits. Both signals were honored here: we
neither crawled `/umbraco/` nor attempted to pass the challenge.

## Deliberately NOT probed, and why

| Route | Why not |
|---|---|
| `/umbraco/api/...` | `robots.txt` disallows `/umbraco/`. That's the site's machine-readable instruction to automated clients; honored. |
| `sfjazz-redesign-stage.adagetech.net` | A third-party vendor's **non-production staging** host, exposed only through a misconfigured `Sitemap:` directive. A misconfiguration is not an invitation, and staging environments aren't public data sources. |
| `admin.sfjazz.org` (noted in the prior spike) | An administrative interface, not a public data surface. |
| Subdomain / host enumeration (CT logs, guessing Tessitura **TNEW** hostnames) | That's scanning for an unadvertised host, not "reading an endpoint that answers openly to a normal request." Out of scope by the ticket's own framing. |
| Mobile-app API | Would require reverse-engineering an app binary — well beyond "plain requests," and any endpoint found would likely carry app credentials or sit behind the same protection. |

## Why the SF Symphony pattern cannot be replicated here

The SF Symphony crack worked because **the calendar page itself was readable**: its inline
`var settings = {...}` block published the Algolia app id, search-only key, and index name,
and the Algolia *data host* sat outside the Queue-it wall that fronted only the *page host*.
Read page → learn endpoint → query endpoint directly.

At SFJAZZ, **step one is blocked**: the calendar page is itself challenge-protected, so the
inline wiring that would name a backing data host (Tessitura REST/TNEW base, an Algolia index
and key, or an Umbraco JSON route) cannot be read. There may or may not be an unprotected
data host behind it — **we cannot find out without passing the challenge**, which is exactly
what this ticket forbids. Discovery is gated by the same control we've committed not to touch.

This also means the platform intel (Umbraco front end, Adage build, almost-certainly-Tessitura
box office) is **not actionable** here: knowing the platform class doesn't yield an endpoint
when the pages that reference it are unreadable, and guessing at platform-conventional
hostnames is enumeration, not open-endpoint reading.

## Consequences

- **No Phase 2 build.** No `backend/src/foghorn/scrapers/sfjazz.py`, no venue seed, no
  `FOGHORN_SFJAZZ_ENABLED` flag under this ticket.
- **Credential-rotation posture:** N/A — no endpoint, no credentials.
- SFJAZZ now rests on:
  - **#90 (JamBase)** — licensed, but partial: ~37 of SFJAZZ's advertised "350+ concerts,
    Sept–May" (mainstage headliners; Joe Henderson Lab nearly absent — 7 listings, 6 of them
    one residency).
  - **A direct permission ask to SFJAZZ** — a feed or listing arrangement, the same posture
    held for DoTheBay. Given the challenge is deliberate and origin-wide, consent is the only
    route to the full calendar. This is the recommended next step if fuller coverage matters.

## Re-checking later (cheap)

SFJAZZ's WAF posture could relax. A future session can re-run this in ~6 requests:

```python
import httpx
UA = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
r = httpx.get("https://www.sfjazz.org/calendar/", headers={"User-Agent": UA},
              timeout=30, follow_redirects=True)
print(r.status_code, r.headers.get("cf-mitigated"))   # 403 challenge  → still walled
```

If that ever returns `200` with event wiring in the HTML, the SF Symphony playbook becomes
available and this verdict should be revisited. **The hard line does not expire**: a `403`
or a challenge remains a dead end to record and walk away from, not an obstacle to engineer
around.
