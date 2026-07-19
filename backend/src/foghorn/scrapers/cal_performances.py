"""Cal Performances (UC Berkeley) scraper.

Source: the presenter's WordPress site. The ``/events/`` archive is a
dateless blog index, but ``/calendar/`` redirects to the current season
page (``/2026-27-season/`` today), which lists every production as a
``div.event-filter-item`` block: a ``.genre-badge`` ("Jazz", "Recital",
"Dance, Illuminations: …" — first comma-segment is the primary genre), the
detail-page link, and — the payload — one inline schema.org ``Event``
JSON-LD object **per performance**, with ``startDate`` in the site's
``MM/DD/YYYYTHH:MM`` house format. One fetch covers the whole season; no
JS execution or detail pages needed.

Filtering is by primary genre: Dance and Theater drop; everything else
(Recital, Orchestra & Chamber Music, Jazz, Early/New Music, Vocal
Celebration, Seasonal Holidays, and the mostly-music Family series) is
kept per conservative house policy. The primary genre string passes
through as ``ScrapedShow.genre`` for ingest to normalize ("Jazz" → jazz;
vocabulary outside the coarse set falls back to the venue default).
Performances span Zellerbach Hall, Hertz Hall, and the campus's other
rooms — all under this one umbrella venue. The listing states no doors
times or prices. Summer-dark is normal: the season runs Sep–May, so a
mid-summer scrape may legitimately return nothing in the 90-day window.

Runnable standalone: ``python -m foghorn.scrapers.cal_performances``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "cal_performances"

# Redirects to the current season's listing (e.g. /2026-27-season/), so the
# scraper tracks season rollover without a hardcoded season URL.
CALENDAR_URL = "https://calperformances.org/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The site's JSON-LD startDate house format: "09/25/2026T19:30".
_START_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})T(\d{2}):(\d{2})$")
# Trailing season code on some billing strings ("Tom Borrow, piano 2627") —
# two consecutive 2-digit season halves; a legit year like "2026" never
# matches (20 → 26 isn't consecutive).
_SEASON_CODE_RE = re.compile(r"\s+(\d{2})(\d{2})$")
# Non-music primary genres (whole-word). Conservative: only categories that
# are clearly not concerts; the mixed Family series stays in.
_DROP_GENRE_RE = re.compile(r"\b(?:dance|theater|theatre|speaker|talk|lecture)s?\b", re.IGNORECASE)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_html(client: httpx.Client | None = None) -> str:
    """Fetch the season listing (following the ``/calendar/`` redirect).
    ``client`` is injectable so tests can drive this with a mock transport."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        response = client.get(CALENDAR_URL)
        response.raise_for_status()
        return response.text
    finally:
        if own_client:
            client.close()


def _clean(text: str) -> str:
    return " ".join(text.split())


def _ld_events(item: Tag) -> list[dict[str, Any]]:
    """All schema.org Event objects in the block's inline JSON-LD scripts.
    A script tag may hold several JSON documents back to back (one per
    performance), so decoding walks the text with ``raw_decode``."""
    events: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for script in item.select('script[type="application/ld+json"]'):
        text = script.get_text().strip()
        index = 0
        while index < len(text):
            try:
                obj, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                break
            if isinstance(obj, dict) and obj.get("@type") == "Event":
                events.append(obj)
            index = end
            while index < len(text) and text[index] in " \t\r\n":
                index += 1
    return events


def _parse_start(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    match = _START_DATE_RE.match(value.strip())
    if match is None:
        return None
    month, day, year, hour, minute = (int(group) for group in match.groups())
    try:
        return dt.datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _strip_season_code(name: str) -> str:
    """Drop a trailing "2627"-style season code (second half = first + 1)."""
    match = _SEASON_CODE_RE.search(name)
    if match is not None and int(match.group(2)) == int(match.group(1)) + 1:
        return name[: match.start()]
    return name


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """One ``ScrapedShow`` per performance JSON-LD whose date falls in
    ``[today, today + window_days]``, non-music genres dropped.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    seen: set[tuple[str, dt.datetime]] = set()
    for item in soup.select("div.event-filter-item"):
        badge = item.select_one(".genre-badge .cp-genre")
        badge_text = _clean(badge.get_text(" ", strip=True)) if badge else ""
        primary_genre = badge_text.split(",")[0].strip()
        if primary_genre and _DROP_GENRE_RE.search(primary_genre):
            continue

        link = item.select_one(".event-link a[href]")
        fallback_url = str(link["href"]) if link is not None else CALENDAR_URL

        for event in _ld_events(item):
            start = _parse_start(event.get("startDate"))
            if start is None or not (today <= start.date() <= window_end):
                continue
            name = _strip_season_code(_clean(str(event.get("name") or "")))
            if not name:
                continue
            key = (name, start)
            if key in seen:
                continue
            seen.add(key)
            url = event.get("url")
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=name,
                    support_raw=[],  # billing is one combined string
                    start_local=start,
                    doors_local=None,  # the listing states no doors times
                    ticket_url=None,  # ticketing sits behind the detail pages
                    price_text=None,  # ... and no prices on the listing
                    source_url=url if isinstance(url, str) and url else fallback_url,
                    genre=primary_genre or None,
                )
            )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live season listing for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


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
