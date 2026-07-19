"""Smiley's Saloon scraper.

Source: the Bolinas roadhouse's own WordPress site — ``/music/`` is
fully server-rendered, one ``div.event`` card per show with a dated
``.event-date`` heading ("Jul  18, 2026"), an ``.event-time`` clock, the
bill in ``.event-title``, an Eventbrite ticket link, and the Eventbrite
price. Titles carry venue-room suffixes ("- INSIDE", "- OUTSIDE",
"- FREE") that are stripped; karaoke nights (LARRY-OKE) are dropped as
non-performances, while open mics are kept. (``/upcoming-events/`` is a
404 decoy — the listing lives at ``/music/``.)

Runnable standalone: ``python -m foghorn.scrapers.smileys_saloon``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "smileys_saloon"

CALENDAR_URL = "https://smileyssaloon.com/music/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_MONTHS = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
_DATE_RE = re.compile(r"([A-Za-z]{3})\.?\s+(\d{1,2}),\s*(\d{4})")
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\.?", re.IGNORECASE)
# Room/price suffixes stacked on titles: "Band - OUTSIDE - FREE". Uppercase
# only, so a band named "Inside" would survive.
_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*(?:INSIDE|OUTSIDE|FREE)\s*$")
# Karaoke is not a performance; the venue's recurring one is "LARRY-OKE".
_NON_MUSIC_RE = re.compile(r"karaoke|larry-oke", re.IGNORECASE)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the music page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _text(card: Tag, selector: str) -> str:
    node = card.select_one(selector)
    if node is None:
        return ""
    return " ".join(node.get_text().replace("\xa0", " ").split())


def parse_html(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Music page → one ``ScrapedShow`` per upcoming ``div.event`` card in
    ``[today, today + window_days]``. ``today`` is injected so the window
    is deterministic and fixture-testable. Pure."""
    soup = BeautifulSoup(page_html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for card in soup.select("div.event"):
        date_match = _DATE_RE.search(_text(card, ".event-date"))
        time_match = _TIME_RE.search(_text(card, ".event-time"))
        if date_match is None or time_match is None:
            continue  # never fabricate a time
        month = _MONTHS.get(date_match.group(1).lower())
        if month is None:
            continue
        try:
            date = dt.date(int(date_match.group(3)), month, int(date_match.group(2)))
        except ValueError:
            continue
        if not (today <= date <= window_end):
            continue
        hour = int(time_match.group(1)) % 12
        if time_match.group(3).lower() == "p":
            hour += 12

        title = _text(card, ".event-title")
        if not title or _NON_MUSIC_RE.search(title):
            continue
        while True:
            stripped = _TITLE_SUFFIX_RE.sub("", title)
            # "…-OUTSIDE" is sometimes glued to the name with no space.
            if stripped == title:
                break
            title = stripped.strip()

        ticket_link = card.select_one('a[href*="eventbrite.com/e/"]')
        ticket_url = None
        if ticket_link is not None:
            href = ticket_link.get("href")
            ticket_url = href if isinstance(href, str) else None
        # Free/door-charge shows render a bare "$" — no digits, no price.
        price: str | None = re.sub(r"\s*USD\s*$", "", _text(card, ".ticket-price"))
        if price is not None and not re.search(r"\d", price):
            price = None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=dt.datetime(date.year, date.month, date.day, hour,
                                        int(time_match.group(2) or 0)),
                doors_local=None,
                ticket_url=ticket_url,
                price_text=price,
                source_url=CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live music page for the next ~90 days."""
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
