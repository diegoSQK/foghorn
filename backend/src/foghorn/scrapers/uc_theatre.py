"""The UC Theatre scraper.

Source: the venue's Webflow site (theuctheatre.org) server-renders every
upcoming show on one static ``/events/`` page as ``div.shows-collection-item``
CMS items — a ``date-div`` with month/day headings (no year), the title in an
``h1.name-listing``, a comma-separated ``h1.support-listing`` openers line, a
``div.genre`` tag, doors and show times in labelled text blocks, and a link to
the venue's per-show page (which is also where tickets sell), whose visible
BUY TICKETS button carries the price ("BUY TICKETS $40 + FEES"). ~27 shows,
months ahead, no pagination and no JS execution needed, so plain ``httpx`` +
``beautifulsoup4`` suffice.

Webflow quirks: conditional-visibility variants of the same field ship in the
markup with a ``w-condition-invisible`` class (e.g. a bare "BUY TICKETS"
button next to the priced one, a SOLD OUT badge) — visible-variant filtering
happens class-side, not via JS, so the parser skips those elements. Item
dates carry no year ("Feb 17"); the year is inferred forward from ``today``
(the list only shows upcoming events, so a month/day earlier than today means
next year).

Runnable standalone: ``python -m foghorn.scrapers.uc_theatre`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "uc_theatre"

CALENDAR_URL = "https://www.theuctheatre.org/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_MONTHS = {
    abbr: index
    for index, abbr in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
# "7:00 pm" in the doors/show text blocks.
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# The visible buy button: "BUY TICKETS $40 + FEES" → "$40 + FEES".
_BUY_PREFIX_RE = re.compile(r"^\s*buy\s+tickets\s*", re.IGNORECASE)
# Genres the venue tags on clearly-non-music programming (none seen live yet;
# the live vocabulary is Jazz/Rock/Metal/…). Ambiguous/empty tags are kept.
_NON_MUSIC_GENRES = {"stand-up", "comedy", "theatre", "theater", "podcast", "film"}


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the events page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
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


def _visible(tag: Tag) -> bool:
    """Webflow ships conditional-visibility variants with a
    ``w-condition-invisible`` class; only elements without it render."""
    classes = tag.get("class")
    return classes is None or "w-condition-invisible" not in classes


def _select_text(item: Tag, selector: str) -> str:
    element = item.select_one(selector)
    if element is None or not _visible(element):
        return ""
    return _clean(element.get_text(" ", strip=True))


def _parse_date(month_text: str, day_text: str, today: dt.date) -> dt.date | None:
    """Resolve a year-less "Feb" + "17" to a concrete date at or after
    ``today`` (the list only shows upcoming events, so earlier month/days roll
    forward into next year)."""
    month = _MONTHS.get(month_text.strip().lower()[:3])
    if month is None:
        return None
    try:
        candidate = dt.date(today.year, month, int(day_text.strip()))
    except ValueError:
        return None
    return candidate.replace(year=today.year + 1) if candidate < today else candidate


def _parse_time(text: str) -> dt.time | None:
    """"7:00 pm" → time; None when missing or unparseable."""
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    if minute > 59:
        return None
    return dt.time(hour, minute)


def _price_text(item: Tag) -> str | None:
    """The visible BUY TICKETS button's price tail ("$40 + FEES"), from
    whichever visible button variant carries a dollar amount."""
    for button_text in item.select("a.uui-button-18 div"):
        if not _visible(button_text):
            continue
        text = _clean(button_text.get_text(" ", strip=True))
        tail = _BUY_PREFIX_RE.sub("", text)
        if tail.startswith("$"):
            return tail
    return None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per CMS item whose date falls in
    ``[today, today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for item in soup.select("div.shows-collection-item"):
        headliner = _select_text(item, "h1.name-listing")
        if not headliner:
            continue
        genre = _select_text(item, "div.genre").lower()
        if genre in _NON_MUSIC_GENRES:
            continue

        show_date = _parse_date(
            _select_text(item, ".date-div .heading-2"),
            _select_text(item, ".date-div .heading-3"),
            today,
        )
        if show_date is None or not (today <= show_date <= window_end):
            continue

        # Labelled time blocks: "Doors: 7:00 pm | Show: 8:00 pm".
        doors_time = _parse_time(_select_text(item, ".div-block-21 .text-block-82"))
        show_time = _parse_time(_select_text(item, ".div-block-12 .text-block-84"))
        start_time = show_time or doors_time
        if start_time is None:
            continue  # no usable time — not seen on real items

        support_text = _select_text(item, "h1.support-listing")
        support = [part for part in (_clean(p) for p in support_text.split(",")) if part]

        link = item.select_one("a.link-block-6[href]") or item.select_one(
            "a.uui-button-18[href]"
        )
        href = _attr(link, "href") if link is not None else None
        event_url = urljoin(CALENDAR_URL, href) if href else CALENDAR_URL

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                genre=genre or None,
                support_raw=support,
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=(
                    dt.datetime.combine(show_date, doors_time)
                    if doors_time is not None
                    else None
                ),
                # Tickets sell through the venue's own per-show page, so that
                # page is both the ticket link and the provenance.
                ticket_url=event_url,
                price_text=_price_text(item),
                source_url=event_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live listing for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


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
