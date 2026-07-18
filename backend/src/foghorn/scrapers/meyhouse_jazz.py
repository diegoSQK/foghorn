"""Meyhouse Jazz (Palo Alto) scraper.

Source: the jazz program of Meyhouse restaurant, whose SFJAZZ-designed
listening room at 640 Emerson St is the Bay Improviser-known "Meyhouse
Jazz" venue. The Wix site server-renders ``/event-list`` (the Palo Alto
upcoming-events page) with ``/event-details/<slug>`` links, and each
detail page embeds the **Wix Events scheduling JSON** — a UTC
``startDate`` plus ``timeZoneId`` — alongside an ``og:title`` and the
stage's address. That's real structured data under a JS-heavy surface;
no headless browser needed.

**Multi-location + seatings.** Meyhouse also runs Sunnyvale and San Ramon
stages; detail pages are filtered to the Palo Alto stage by location
text. The 5 PM / 8 PM seatings are separate Wix events sharing a billing
— both are kept as separate shows, per the Yoshi's one-row-per-set
precedent. The "(Fri 7/31 - 5 PM seating)"-style suffix Wix appends to
titles comes off the headliner.

Runnable standalone: ``python -m foghorn.scrapers.meyhouse_jazz`` prints
the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "meyhouse_jazz"

BASE_URL = "https://www.meyhousejazz.com"
EVENTS_URL = f"{BASE_URL}/event-list"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_EVENT_LINK_RE = re.compile(r'href="(https://www\.meyhousejazz\.com/event-details/[^"?#]+)"')
_SCHEDULING_RE = re.compile(
    r'"scheduling":\{"config":\{[^{}]*"startDate":"([^"]+)"'
    r'(?:[^{}]*?"endDate":"([^"]+)")?[^{}]*'
    r'"timeZoneId":"([^"]+)"'
)
_OG_TITLE_RE = re.compile(r'property="og:title" content="([^"]+)"')
# "(Fri 7/31 - 5 PM seating)" / "(7/18-5pm)" style suffixes — sometimes
# typed with fullwidth parens, sometimes unclosed, sometimes without the
# weekday; normalize before stripping.
_SEATING_SUFFIX_RE = re.compile(
    r"\s*\((?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)|\d{1,2}/\d{1,2})[^)]*\)?\s*$",
    re.IGNORECASE,
)
_SITE_SUFFIX_RE = re.compile(r"\s*\|\s*Meyhouse[^|]*$", re.IGNORECASE)
_PALO_ALTO_SIGNALS = ("Palo Alto Stage", "Emerson St")


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def parse_event_links(listing_html: str) -> list[str]:
    """Detail-page URLs, deduped in listing order."""
    urls: list[str] = []
    seen: set[str] = set()
    for url in _EVENT_LINK_RE.findall(listing_html):
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_event_page(page_html: str, url: str) -> ScrapedShow | None:
    """One detail page → a ``ScrapedShow``; None for non-Palo-Alto stages
    or pages without scheduling data. Pure / fixture-testable."""
    if not any(signal in page_html for signal in _PALO_ALTO_SIGNALS):
        return None
    scheduling = _SCHEDULING_RE.search(page_html)
    if scheduling is None:
        return None
    start_raw, end_raw, tz_raw = (
        scheduling.group(1),
        scheduling.group(2),
        scheduling.group(3),
    )
    try:
        instant = dt.datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        tz = ZoneInfo(tz_raw.replace("\\/", "/"))
    except (ValueError, KeyError):
        return None
    start_local = instant.astimezone(tz).replace(tzinfo=None, microsecond=0)
    end_local = None
    if end_raw:
        try:
            end_local = (
                dt.datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                .astimezone(tz)
                .replace(tzinfo=None, microsecond=0)
            )
        except ValueError:
            end_local = None

    title_match = _OG_TITLE_RE.search(page_html)
    if title_match is None:
        return None
    title = " ".join(html_lib.unescape(title_match.group(1)).split())
    title = title.replace("\uff08", "(").replace("\uff09", ")")
    title = _SITE_SUFFIX_RE.sub("", title)
    title = _SEATING_SUFFIX_RE.sub("", title).strip()
    if not title:
        return None
    return ScrapedShow(
        venue_slug=VENUE_SLUG,
        headliner_raw=title,
        support_raw=[],
        start_local=start_local,
        end_local=end_local,
        doors_local=None,
        # Wix native ticketing lives on the event page itself.
        ticket_url=url,
        price_text=None,
        source_url=url,
    )


def scrape() -> list[ScrapedShow]:
    """Walk the live Palo Alto listing and detail pages for the window."""
    today = dt.date.today()
    window_end = today + dt.timedelta(days=SCRAPE_WINDOW_DAYS)
    shows: list[ScrapedShow] = []
    with _client() as client:
        listing = client.get(EVENTS_URL)
        listing.raise_for_status()
        for url in parse_event_links(listing.text):
            page = client.get(url)
            if page.status_code != httpx.codes.OK:
                continue
            show = parse_event_page(page.text, url)
            if show is not None and today <= show.start_local.date() <= window_end:
                shows.append(show)
    shows.sort(key=lambda show: show.start_local)
    return shows


def main() -> None:
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in scrape()],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
