"""Freight & Salvage (Berkeley) scraper.

Source: the venue's **Tessitura TNEW** ticketing host, not its website.

``thefreight.org`` sits behind a Cloudflare managed challenge — 403 with a
"Just a moment..." interstitial to every plain HTTP client, polite UA and
browser UA alike, right down to ``robots.txt``. Per the posture set in #91 we
don't touch the challenge. Ticketmaster Discovery is no help either: it lists
three Freight venue ids and every one returns ``totalElements: 0``, because the
Freight self-tickets.

The way in was DNS, not HTTP. ``secure.thefreight.org`` is a CNAME to
``frts-tnew-prod.tnhs.cloud`` — Tessitura Network Hosting Services running TNEW
(Tessitura Network Express Web) — and that host has no bot challenge on it; it
answers 200 to a plain client and serves the real events listing. **General
move: when a venue site is challenge-walled, check for a ``secure.`` /
``tickets.`` / ``ci.`` CNAME before giving up.** A self-ticketing venue usually
fronts ticketing on a separate host that has no reason to be challenged.

The listing renders client-side from a single unauthenticated JSON endpoint —
no nonce, no cookie, no API key:

    POST https://secure.thefreight.org/api/products/productionseasons
    {"startDate": "2026-08-11T00:00", "endDate": "2027-08-11T23:59"}

It returns the whole window in one request (a year came back as 78 productions
/ 119 performances, with no sign of a cap or pagination). Multi-night runs and
repeating series arrive already expanded — one entry per performance — so
there's no recurrence maths here.

The Freight is a teaching institution as well as a concert hall, so its feed
mixes ticketed shows with the class programme; see ``_is_concert`` for how those
are separated and why ``productTypeId`` alone isn't enough.

Runnable standalone: ``python -m foghorn.scrapers.freight_and_salvage`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "freight_and_salvage"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

API_URL = "https://secure.thefreight.org/api/products/productionseasons"
# Human-viewable provenance when a performance carries no action URL of its own.
CALENDAR_URL = "https://secure.thefreight.org/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180
REQUEST_TIMEOUT = 30.0

# Tessitura product types, as this client has them configured. Type 3 is the
# concert programme; 1 and 2 are the "teaching and community" programme.
# `productTypeName` is an empty string on every record, so the numeric id is
# the only taxonomy available — and it is a poor gate in both directions:
# type 3 carries the Berkeley Public Library story time, while types 1/2 carry
# the venue's Community Mondays series, which is real programming (the weekly
# bluegrass jam, open mics, and booked gigs like Karl Evangelista's Grex).
# Gating on the id alone silently dropped 39 in-window entries including those.
_CONCERT_PRODUCT_TYPE_IDS = frozenset({3})

# The Freight is a teaching institution, and its term classes are filed under
# a "<Term> <N>: <instructor>" production ("Fall I: Tamsen Fynn"). That pattern
# is the single cleanest class marker in the feed.
_CLASS_TERM_RE = re.compile(r"^(spring|summer|fall|winter)\s+[IVX]+\s*:", re.I)

# The venue's community-programming series. Mixed by design — jams and gigs
# alongside comedy and listening parties — so it's kept and filtered on title
# rather than dropped wholesale with the rest of its product type.
_COMMUNITY_SERIES_PREFIX = "community mondays"

# Non-music and instructional programming, dropped so classes and spoken-word
# nights don't land in the calendar as concerts. Kept short and specific; the
# Freight's bookings are overwhelmingly real shows, so this errs toward
# inclusion like the other mixed-programming scrapers.
_NON_CONCERT_SIGNALS = (
    "story time",
    "storytime",
    # The Freight hosts The Moth's storytelling slams. Spoken word, not music —
    # dropped for the same reason bird_and_beckett drops readings and author
    # talks.
    "storyslam",
    "story slam",
    "comedy",
    "listening party",
    "singalong",
    "sing-along",
    "workshop",
    "masterclass",
    "master class",
    # Skill-level framing is how the one-off classes outside the term
    # programme are titled ("Beginning Harmonica with Aki Kumar").
    "beginning ",
    "intermediate ",
    "advanced ",
    "intro to ",
    "introduction to ",
    "for beginners",
    "private event",
    "facility rental",
)

# Participatory nights, tagged event_type="jam" so they're filterable as such.
# The ingest's own inference is deliberately narrow and would miss "Country
# Bluegrass Jam" (no genre word it knows, no "session"/"night" framing), and
# the scraper is the source that knows — an explicit tag always wins.
_JAM_RE = re.compile(r"\bjam\b|\bopen\s+mic\b", re.IGNORECASE)

_TAG_RE = re.compile(r"<[^>]+>")


class FreightSourceError(RuntimeError):
    """The feed changed shape in a way that would silently lose shows."""


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_productions(
    client: httpx.Client,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Fetch every production season overlapping the forward window.

    One request covers the whole window — the endpoint takes the range directly
    and returns all of it.
    """
    body = {
        "startDate": f"{today.isoformat()}T00:00",
        "endDate": f"{(today + dt.timedelta(days=window_days)).isoformat()}T23:59",
    }
    response = client.post(
        API_URL,
        json=body,
        headers={"Accept": "application/json", "Referer": CALENDAR_URL},
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        raise FreightSourceError("productionseasons returned a non-JSON body") from None
    if not isinstance(payload, dict) or "productions" not in payload:
        raise FreightSourceError(
            f"productionseasons payload has no 'productions' key: {sorted(payload)[:8]}"
            if isinstance(payload, dict)
            else "productionseasons payload is not an object"
        )
    productions: list[dict[str, Any]] = payload["productions"] or []
    return productions


def _clean(text: str) -> str:
    """Strip the HTML the feed embeds in titles and collapse whitespace.

    Titles routinely carry ``<br />`` + ``<font size=...>`` subtitle markup, and
    a couple leak a whole ``<h1 id="tn-page-heading">`` wrapper. Entities are
    unescaped after tag removal so ``&amp;`` survives as ``&``.
    """
    without_tags = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _headliner(performance: dict[str, Any], production: dict[str, Any]) -> str:
    """The billed act. ``performanceTitle`` is the specific billing ("Jeff
    Parker ETA IVtet"); ``productionTitle`` is the umbrella ("Jeff Parker").
    Only the part before a ``<br>`` is the act — the rest is a subtitle."""
    raw = str(performance.get("performanceTitle") or production.get("productionTitle") or "")
    lead = re.split(r"<br\s*/?>", raw, maxsplit=1)[0]
    return _clean(lead) or _clean(raw)


def _is_concert(performance: dict[str, Any], production: dict[str, Any], title: str) -> bool:
    """Whether this performance belongs in a music calendar.

    Order matters: the term-class programme and the non-music title signals
    drop first, and only then does the product type decide. A non-concert
    product type is kept solely for the Community Mondays series, whose jams
    and booked gigs are real programming filed under the teaching type.
    """
    if _CLASS_TERM_RE.match(_clean(str(production.get("productionTitle") or ""))):
        return False
    lowered = title.lower()
    if any(signal in lowered for signal in _NON_CONCERT_SIGNALS):
        return False
    if performance.get("productTypeId") in _CONCERT_PRODUCT_TYPE_IDS:
        return True
    return lowered.startswith(_COMMUNITY_SERIES_PREFIX)


def _start_local(performance: dict[str, Any]) -> dt.datetime | None:
    """Venue-local naive start, per the ScrapedShow contract.

    ``iso8601DateString`` is local-with-offset (``...T20:00:00.0000000-07:00``);
    ``performanceDate`` is the same instant in UTC. The local field is used
    directly so no tz conversion is needed. The 7-digit fractional seconds are
    trimmed for ``fromisoformat``.
    """
    raw = performance.get("iso8601DateString")
    if not isinstance(raw, str) or not raw:
        return None
    normalized = re.sub(r"\.(\d{6})\d+", r".\1", raw)
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def parse_productions(
    productions: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Flatten production seasons into one show per performance.

    Pure — the tests drive it from a saved payload.
    """
    horizon = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, str]] = set()
    for production in productions:
        performances = production.get("performances") or []
        for performance in performances:
            if performance.get("isPerformanceVisible") is False:
                continue
            title = _headliner(performance, production)
            if not title or not _is_concert(performance, production, title):
                continue
            start_local = _start_local(performance)
            if start_local is None:
                continue
            if not (today <= start_local.date() <= horizon):
                continue

            # A performance's own action URL is the show page; the production
            # season page is the fallback. Both are stable and human-viewable.
            action_url = performance.get("actionUrl") or production.get(
                "productionSeasonActionUrl"
            )
            source_url = str(action_url or CALENDAR_URL)
            # "Tickets Not On Sale" performances are real announced shows with
            # an on-sale still pending — kept, but without a ticket link, since
            # the URL wouldn't sell anything yet.
            ticket_url = source_url if performance.get("isOnSale") else None

            key = (start_local.isoformat(), title.casefold())
            if key in seen:
                continue
            seen.add(key)
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=title,
                    start_local=start_local,
                    doors_local=None,
                    ticket_url=ticket_url,
                    # The feed carries no price anywhere in the payload.
                    price_text=None,
                    source_url=source_url,
                    event_type="jam" if _JAM_RE.search(title) else None,
                )
            )
    shows.sort(key=lambda show: (show.start_local, show.headliner_raw))
    return shows


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    """Fetch and parse the forward window."""
    day = today or dt.date.today()
    with _client() as client:
        return parse_productions(fetch_productions(client, day), day)


def main() -> None:
    shows = scrape()
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in shows],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
