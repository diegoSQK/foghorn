"""Yoshi's (Oakland) scraper.

Source: the fullCalendar JSON feed behind the venue's own calendar page.
Yoshi's (Jack London Square, Oakland) renders ``/events/default/calendar`` with
a legacy fullCalendar widget that POSTs to ``/events/default/calendarJson``
with a ``start``/``end`` date range. That endpoint returns one JSON object per
*set* — nights with 7:30pm and 9:30pm shows come back as two entries, which the
server-rendered HTML list collapses into one row — plus the naive local start
("YYYY-MM-DD HH:MM:SS"), the per-event detail-page URL, and the etix ticket
link (or a "SOLD OUT" button) embedded in the ``title`` HTML fragment.

The one thing the JSON lacks is the price, which only appears on the HTML
calendar page (``p.price`` per row). ``scrape()`` therefore also fetches that
page once and joins prices to shows by detail-page URL — best-effort, so a
markup change there degrades ``price_text`` to ``None`` rather than breaking
the scraper.

Runnable standalone: ``python -m foghorn.scrapers.yoshis`` prints the scraped
shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "yoshis"

EVENTS_JSON_URL = "https://yoshis.com/events/default/calendarJson"
# Human-viewable calendar (also the venue's seed calendar_url); fetched once
# per scrape as the price source, and the provenance fallback when an entry
# carries no detail-page URL.
CALENDAR_URL = "https://yoshis.com/events/default/calendar"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# calendarJson's start field, e.g. "2026-07-02 19:30:00" (naive venue-local).
_START_FMT = "%Y-%m-%d %H:%M:%S"

# Leading set time in the title fragment: "7:30PM FOO" / "7:00 PM BAR".
_LEADING_TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*[AP]\.?M\.?\s*", re.IGNORECASE)


def fetch_events(
    today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[dict[str, object]]:
    """POST the fullCalendar feed for ``[today, today + window_days]``. The
    endpoint requires the range (no params → literal ``null``). Kept separate
    from parsing so tests drive ``parse_events`` from a fixture."""
    response = httpx.post(
        EVENTS_JSON_URL,
        data={
            "start": today.isoformat(),
            "end": (today + dt.timedelta(days=window_days)).isoformat(),
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def fetch_calendar_html(url: str = CALENDAR_URL) -> str:
    """Fetch the HTML calendar page (the price source for ``parse_price_map``)."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str``. bs4 types attributes
    as ``str | list[str] | None`` (multi-valued attrs like ``class``); ``href``
    is always single, but we coerce defensively to stay type-safe."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def parse_price_map(html: str) -> dict[str, str]:
    """Map each detail-page URL on the HTML calendar to its ``p.price`` text
    (e.g. "$49 - $89"). Rows without a title link or price are skipped."""
    soup = BeautifulSoup(html, "html.parser")
    prices: dict[str, str] = {}
    for li in soup.select("ul.event-full-list li.event-indv"):
        title_link = li.select_one("div.etitle h3 a")
        price_tag = li.select_one("p.price")
        if title_link is None or price_tag is None:
            continue
        href = _attr(title_link, "href")
        price = _clean(price_tag.get_text(" ", strip=True))
        if href and price:
            prices[href] = price
    return prices


def _split_title(title_html: str) -> tuple[str, str | None]:
    """Break a calendarJson ``title`` fragment ("7:30PM NAME<br/><a …>Buy
    Tickets</a>") into the headliner text and the etix ticket URL (``None`` for
    sold-out entries, whose button anchor has no ``href``)."""
    fragment = BeautifulSoup(title_html, "html.parser")
    ticket_url: str | None = None
    for anchor in fragment.find_all("a"):
        if isinstance(anchor, Tag):
            ticket_url = _attr(anchor, "href")
            anchor.decompose()
    text = _clean(fragment.get_text(" ", strip=True))
    # What remains is "7:30PM NAME" (the button text was removed with its <a>).
    headliner = _LEADING_TIME_RE.sub("", text).strip()
    return headliner, ticket_url


def parse_events(
    events: list[dict[str, object]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    prices: dict[str, str] | None = None,
) -> list[ScrapedShow]:
    """Map calendarJson entries in ``[today, today + window_days]`` to
    ``ScrapedShow``s. Pure / fixture-testable: ``today`` is injected, and
    ``prices`` (detail URL → price text, from ``parse_price_map``) is optional.

    Yoshi's is a music room top to bottom, so there's no non-music filtering.
    Doors aren't published on the calendar; ``doors_local`` stays ``None``.
    """
    price_map = prices or {}
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for event in events:
        start_raw = event.get("start")
        title_raw = event.get("title")
        if not isinstance(start_raw, str) or not isinstance(title_raw, str):
            continue
        try:
            start_local = dt.datetime.strptime(start_raw, _START_FMT)
        except ValueError:
            continue
        if not (today <= start_local.date() <= window_end):
            continue
        headliner, ticket_url = _split_title(title_raw)
        if not headliner:
            continue
        detail_url = event.get("url")
        source_url = detail_url if isinstance(detail_url, str) and detail_url else CALENDAR_URL
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=ticket_url,
                price_text=price_map.get(source_url),
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days. The price
    lookup is enrichment — if the HTML page fails, shows still ship."""
    today = dt.date.today()
    events = fetch_events(today)
    try:
        prices = parse_price_map(fetch_calendar_html())
    except httpx.HTTPError:
        prices = {}
    return parse_events(events, today, prices=prices)


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
