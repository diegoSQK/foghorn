"""SJZ Break Room (San Jose Jazz) scraper.

Source: sanjosejazz.org's own WordPress site (custom "sjz" theme + Visual
Composer). San Jose Jazz runs year-round programming (Winter/Spring/Fall
Series, Break Room Sessions, jazz jams) at its 100-cap SJZ Break Room venue at
310 S. First Street in downtown San Jose's SoFA district. Summer Fest lives on
a separate subdomain and is out of scope.

The ``/events/`` archive and its filters are server-rendered but only list
*upcoming* events, and the events CPT isn't exposed over the WP REST API — so
between series (e.g. July, when programming pauses for Summer Fest) the
archive is empty and offers nothing to anchor a parser on. The stable source
is the **Yoast event sitemap** (``/event-sitemap.xml``): every event detail
page is listed with a ``lastmod``, and the detail pages are fully
server-rendered with the title (``.hero-title h1``), a ``.description-date``
block carrying the date ("Fri, Jun 5" — no year), doors/showtime spans, and a
"price / venue" line ("$27 (Incl. fees) / SJZ Break Room"). We fetch the
sitemap, then only the event pages modified within a recent lookback (SJZ
posts events weeks — not years — ahead, so this bounds the per-run fetches),
parse each page, keep only Break Room events, and infer the missing year by
requiring the printed weekday to match a date inside the scrape window.

Runnable standalone: ``python -m foghorn.scrapers.sjz_break_room`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "sjz_break_room"

BASE_URL = "https://sanjosejazz.org"
SITEMAP_URL = f"{BASE_URL}/event-sitemap.xml"
# Human-viewable events archive (also the venue's seed calendar_url).
CALENDAR_URL = f"{BASE_URL}/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
# Only event pages touched this recently are fetched. Events are created (and
# so last-modified) well inside this horizon of their date; anything older is
# a past event whose page we can skip without fetching.
SITEMAP_LOOKBACK_DAYS = 180
# Hard cap on per-run page fetches, in case a bulk edit touches the whole CPT.
MAX_EVENT_PAGES = 60
REQUEST_TIMEOUT = 30.0

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# Event *detail* pages only — the sitemap also lists the /events/ archive.
_EVENT_URL_RE = re.compile(r"https://sanjosejazz\.org/events/[^/]+/?$")
# "Fri, Jun 5" — weekday + month abbreviations, day of month; no year.
_DATE_RE = re.compile(r"([A-Za-z]{3}),\s+([A-Za-z]{3,})\.?\s+(\d{1,2})")
# "5pm", "7:30pm" inside "5pm Doors," / "7pm showtime (Pacific)".
_TIME_RE = re.compile(r"(\d{1,2}(?::\d{2})?)\s*([ap])\.?m\.?", re.IGNORECASE)
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_sitemap(client: httpx.Client) -> str:
    response = client.get(SITEMAP_URL)
    response.raise_for_status()
    return response.text


def fetch_event_page(client: httpx.Client, url: str) -> str:
    response = client.get(url)
    response.raise_for_status()
    return response.text


def parse_sitemap(
    xml: str, today: dt.date, lookback_days: int = SITEMAP_LOOKBACK_DAYS
) -> list[str]:
    """Event-page URLs whose ``lastmod`` falls within the lookback. Pure /
    fixture-testable; sitemap order (oldest first) is preserved, capped at
    ``MAX_EVENT_PAGES`` newest entries."""
    cutoff = today - dt.timedelta(days=lookback_days)
    urls: list[str] = []
    for entry in ET.fromstring(xml).findall("sm:url", _SITEMAP_NS):
        loc = entry.findtext("sm:loc", default="", namespaces=_SITEMAP_NS).strip()
        lastmod = entry.findtext("sm:lastmod", default="", namespaces=_SITEMAP_NS).strip()
        if not loc or not lastmod or _EVENT_URL_RE.match(loc) is None:
            continue
        try:
            modified = dt.datetime.fromisoformat(lastmod).date()
        except ValueError:
            continue
        if modified >= cutoff:
            urls.append(loc)
    return urls[-MAX_EVENT_PAGES:]


def _clean(text: str) -> str:
    return " ".join(text.split())


def _parse_time(text: str) -> dt.time | None:
    match = _TIME_RE.search(text)
    if match is None:
        return None
    clock, meridiem = match.group(1), match.group(2).lower()
    hour_text, _, minute_text = clock.partition(":")
    hour = int(hour_text) % 12
    if meridiem == "p":
        hour += 12
    return dt.time(hour, int(minute_text or 0))


def _infer_date(
    weekday_text: str, month_text: str, day: int, today: dt.date, window_end: dt.date
) -> dt.date | None:
    """The site prints dates without a year ("Fri, Jun 5"). Try this year and
    next; accept the first candidate that lands in ``[today, window_end]``
    *and* falls on the printed weekday (the weekday check rejects stale pages
    whose month/day happens to recur inside the window)."""
    try:
        month = dt.datetime.strptime(month_text[:3].title(), "%b").month
    except ValueError:
        return None
    weekday = weekday_text.lower()[:3]
    if weekday not in _WEEKDAYS:
        return None
    for year in (today.year, today.year + 1):
        try:
            candidate = dt.date(year, month, day)
        except ValueError:
            continue
        if today <= candidate <= window_end and _WEEKDAYS[candidate.weekday()] == weekday:
            return candidate
    return None


def _price_and_venue(date_block: Tag) -> tuple[str | None, str]:
    """The ``.description-date`` block ends with a bare "price / venue" text
    line ("$27 (Incl. fees) / SJZ Break Room", "Free Admission / SJZ Break
    Room"). Returns ``(price_text, venue_name)``; venue is "" when absent."""
    leftovers = " ".join(
        fragment for fragment in date_block.find_all(string=True, recursive=False)
    )
    text = _clean(leftovers)
    if not text:
        return None, ""
    price, sep, venue = text.rpartition("/")
    if not sep:
        return text or None, ""
    return _clean(price) or None, _clean(venue)


def parse_event_page(
    html: str,
    source_url: str,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> ScrapedShow | None:
    """One event detail page → a ``ScrapedShow``, or ``None`` when the page is
    not an upcoming in-window show at the Break Room (past events, other
    venues like Parque de los Pobladores, pages without a parseable
    date/showtime). Pure / fixture-testable; ``today`` is injected."""
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one(".hero-title h1")
    date_block = soup.select_one(".description-date")
    if title_el is None or date_block is None:
        return None
    headliner = _clean(title_el.get_text(" ", strip=True))
    if not headliner:
        return None

    price_text, venue_name = _price_and_venue(date_block)
    if "break room" not in venue_name.lower():
        return None

    date_el = date_block.select_one(".e-date")
    date_match = _DATE_RE.search(date_el.get_text(" ", strip=True)) if date_el else None
    if date_match is None:
        return None
    window_end = today + dt.timedelta(days=window_days)
    show_date = _infer_date(
        date_match.group(1), date_match.group(2), int(date_match.group(3)), today, window_end
    )
    if show_date is None:
        return None

    time_el = date_block.select_one(".e-time")
    showtime = _parse_time(time_el.get_text(" ", strip=True)) if time_el else None
    if showtime is None:
        return None
    doors_el = date_block.select_one(".e-doors")
    doors = _parse_time(doors_el.get_text(" ", strip=True)) if doors_el else None

    # Ticketed events render the hero call-to-action as a link; free shows
    # render it as an inert <span> ("FREE ADMISSION").
    ticket_el = soup.select_one("a.call-to-action[href]")
    ticket_href = ticket_el.get("href") if ticket_el is not None else None

    return ScrapedShow(
        venue_slug=VENUE_SLUG,
        headliner_raw=headliner,
        support_raw=[],
        start_local=dt.datetime.combine(show_date, showtime),
        doors_local=dt.datetime.combine(show_date, doors) if doors else None,
        ticket_url=ticket_href if isinstance(ticket_href, str) else None,
        price_text=price_text,
        source_url=source_url,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch the event sitemap, then each recently-modified event page, and
    return the in-window Break Room shows sorted by start time."""
    today = dt.date.today()
    shows: list[ScrapedShow] = []
    with _client() as client:
        for url in parse_sitemap(fetch_sitemap(client), today):
            show = parse_event_page(fetch_event_page(client, url), url, today)
            if show is not None:
                shows.append(show)
    shows.sort(key=lambda show: show.start_local)
    return shows


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
