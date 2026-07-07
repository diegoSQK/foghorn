"""Sweetwater Music Hall scraper.

Source: the venue's WordPress site (sweetwatermusichall.com, which redirects to
``.org``) runs the **Rockhouse Partners / etix** events plugin, which
server-renders the complete upcoming-events list into ``/events/?view=list``
as structured ``eventWrapper`` blocks — title, full date (with year, unlike
the SeeTickets venues), doors/show times, the event's own detail page, and an
``etix.com/ticket/p/…`` purchase link (absent on free shows and open mics).
Everything through ~six months out fits on the one page — no pagination or JS
needed. The site also exposes a The Events Calendar REST route, but it
answers with an HTML fake-200 rather than JSON, so the server-rendered listing
is the trustworthy target.

The listing does not publish price or genre, and the bill is not pre-split —
support acts live inside the title text ("Margo Price … with Jeremy Ivey"), so
the full title is kept verbatim as ``headliner_raw`` rather than guessing at a
split (house policy: only split when the markup provides it).

Runnable standalone: ``python -m foghorn.scrapers.sweetwater_music_hall``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "sweetwater_music_hall"

EVENTS_URL = "https://sweetwatermusichall.org/events/?view=list"
# Fallback provenance when a wrapper's per-event link is missing; normally each
# show's source_url is its own /event/ page.
SOURCE_URL = EVENTS_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Doors: 7 pm Show: 8 pm" / "Doors: 11:30 am Show: 12 pm" / "Show: 7 pm".
_DOORS_RE = re.compile(r"doors:\s*(\d{1,2}(?::\d{2})?\s*[ap]m)", re.IGNORECASE)
_SHOW_RE = re.compile(r"show:\s*(\d{1,2}(?::\d{2})?\s*[ap]m)", re.IGNORECASE)


def fetch_html(url: str = EVENTS_URL) -> str:
    """Fetch the events-list page. Kept separate from parsing so tests drive
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


def _select_text(wrapper: Tag, selector: str) -> str:
    element = wrapper.select_one(selector)
    return _clean(element.get_text(" ", strip=True)) if element is not None else ""


def _parse_date(text: str) -> dt.date | None:
    """"Wed, Jul 08, 2026" → date (the year is printed, no inference needed)."""
    try:
        return dt.datetime.strptime(text, "%a, %b %d, %Y").date()
    except ValueError:
        return None


def _parse_time(text: str) -> dt.time | None:
    """"7 pm" / "11:30 am" → time; None when unparseable."""
    normalized = text.replace(" ", "").replace(".", "").upper()
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    try:
        return dt.datetime.strptime(normalized, fmt).time()
    except ValueError:
        return None


def _match_time(pattern: re.Pattern[str], text: str) -> dt.time | None:
    match = pattern.search(text)
    return _parse_time(match.group(1)) if match else None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per ``eventWrapper`` block whose date falls
    in ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for wrapper in soup.select("div.eventWrapper"):
        headliner = _select_text(wrapper, "div.eventTitleDiv h2")
        if not headliner:
            continue
        show_date = _parse_date(_select_text(wrapper, ".singleEventDate"))
        if show_date is None or not (today <= show_date <= window_end):
            continue

        # "Doors: 7 pm Show: 8 pm" (open mics carry only "Show: 7 pm").
        times_text = _select_text(wrapper, ".eventDoorStartDate")
        doors_time = _match_time(_DOORS_RE, times_text)
        show_time = _match_time(_SHOW_RE, times_text)
        start_time = show_time or doors_time
        if start_time is None:
            continue  # no usable time — not seen on real wrappers

        title_link = wrapper.select_one("div.eventTitleDiv a.url")
        event_href = _attr(title_link, "href") if title_link is not None else None
        ticket_link = wrapper.select_one('a[href*="etix.com/ticket/p/"]')
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=(
                    dt.datetime.combine(show_date, doors_time)
                    if doors_time is not None
                    else None
                ),
                ticket_url=ticket_href,  # None on free shows / open mics
                price_text=None,  # the listing doesn't publish prices
                source_url=event_href or SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live events list for the next ~90 days."""
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
