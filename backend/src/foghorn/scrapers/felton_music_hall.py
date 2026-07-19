"""Felton Music Hall scraper.

Source: the 400-cap San Lorenzo Valley room's server-rendered Webflow
homepage at ``feltonmusichall.com`` — the same Webflow show-card theme as
the Guild Theatre, but without the Guild's per-card JSON-LD, so the cards
themselves are parsed. Each ``div.event-card`` renders two
``main-title-hover`` divs (a full "July 9, 2026" date, then the title),
"door time:" / "show starts:" label/value pairs (values in
``text-block-19``, empty ones stamped ``w-dyn-bind-empty``), and a Tixr
ticket link. The homepage's Webflow collection list carries the full
upcoming calendar (~50 shows, months ahead); ``/events`` renders the same
collection.

Cards without a stated show-start time are skipped (never fabricate — the
date alone is not a show). Cards carry no per-event page link, so the
homepage is the provenance. The room books occasional stand-up; only
strong title signals drop (ambiguous names are kept).

Runnable standalone: ``python -m foghorn.scrapers.felton_music_hall``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "felton_music_hall"

EVENTS_URL = "https://feltonmusichall.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Strong non-music title signals (the calendar is otherwise touring music).
_NON_MUSIC_RE = re.compile(
    r"\bcomedy\b|\bcomedian\b|\bstand[- ]?up\b|\bscreening\b|\btrivia\b|"
    r"\bkaraoke\b|\bprivate event\b",
    re.IGNORECASE,
)


def fetch_html(url: str = EVENTS_URL) -> str:
    """Fetch the homepage show list. Kept separate from parsing so tests
    drive ``parse_html`` from a fixture without touching the network."""
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


def _parse_date(raw: str) -> dt.date | None:
    """ "July 9, 2026" → a date. The cards always print the full year."""
    try:
        return dt.datetime.strptime(_clean(raw), "%B %d, %Y").date()
    except ValueError:
        return None


def _parse_time(raw: str) -> dt.time | None:
    raw = _clean(raw)
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return dt.datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per event card dated within ``[today,
    today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable."""
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for card in soup.select("div.event-card"):
        hovers = [_clean(el.get_text(" ", strip=True)) for el in card.select(".main-title-hover")]
        # First hover div is the date, second the title.
        if len(hovers) < 2:
            continue
        start_date = _parse_date(hovers[0])
        title = hovers[1]
        if start_date is None or not title or _NON_MUSIC_RE.search(title):
            continue
        if not (today <= start_date <= window_end):
            continue

        start_time: dt.time | None = None
        doors_time: dt.time | None = None
        for info in card.select(".date-info"):
            label_el = info.select_one(".text-block-18")
            value_el = info.select_one(".text-block-19")
            if label_el is None or value_el is None:
                continue
            label = label_el.get_text(" ", strip=True).lower()
            value = _parse_time(value_el.get_text(" ", strip=True))
            if value is None:
                continue  # empty w-dyn-bind-empty slot
            if "show" in label:
                start_time = value
            elif "door" in label:
                doors_time = value
        if start_time is None:
            continue  # a bare date never becomes a show

        ticket_el = card.select_one("a.button-2")
        ticket_href = ticket_el.get("href") if ticket_el is not None else None
        ticket_url = ticket_href if isinstance(ticket_href, str) and ticket_href else None

        show = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=title,
            support_raw=[],
            start_local=dt.datetime.combine(start_date, start_time),
            doors_local=(dt.datetime.combine(start_date, doors_time) if doors_time else None),
            ticket_url=ticket_url,
            price_text=None,
            source_url=EVENTS_URL,
        )
        shows.setdefault((show.headliner_raw, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live show list for the next ~90 days."""
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
