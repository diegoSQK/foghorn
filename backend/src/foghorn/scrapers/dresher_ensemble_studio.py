"""Dresher Ensemble Studio scraper.

Source: the studio's WordPress site runs **The Events Calendar** (Tribe),
exposing the same JSON REST API as Mr. Tipple's / Madrone / the Natural
Grocery Annex at ``/wp-json/tribe/events/v1/events``. The 99-seat West
Oakland performance space (Paul Dresher Ensemble's home) hosts the weekly
West Oakland Sound Series (sfSound + New Performance Traditions) plus
new-music/experimental one-offs — this scraper supersedes both the venue's
and the series' Bay Improviser quarantine entries (see ``VENUE_ALIASES`` in
``aggregators/ingest``).

**Data-quality notes.**

* Bills arrive as one ``title`` with literal ``<br>`` separators between
  acts ("The Sky Is A Suitcase<br>Jacob Pek + Raffi Garabedian"). The first
  segment is the headliner, the rest are support.
* Multi-night runs appear as one event row per date (Tribe series) — each is
  a real show, so no dedup here.
* All-day rows carry no real start time and are skipped, per the other Tribe
  scrapers.

Runnable standalone: ``python -m foghorn.scrapers.dresher_ensemble_studio``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "dresher_ensemble_studio"

EVENTS_API = "https://dresherensemble.org/wp-json/tribe/events/v1/events"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://dresherensemble.org/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 50
REQUEST_TIMEOUT = 30.0
# Tribe's start_date/end_date are local, formatted "YYYY-MM-DD HH:MM:SS".
_TRIBE_DT = "%Y-%m-%d %H:%M:%S"

# The studio also posts non-performance programming occasionally (workshops,
# open rehearsals, fundraisers). Heuristic and knowingly imperfect — when a
# title is ambiguous we keep the event.
_NON_MUSIC_SIGNALS = (
    "workshop",
    "masterclass",
    "master class",
    "open rehearsal",
    "fundraiser",
    "private event",
)

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _is_non_music(title: str) -> bool:
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_events(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Page through the Tribe REST API for events in
    ``[today, today + window_days]``. ``client`` is injectable so tests drive
    pagination with a mock transport instead of the network."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        events: list[dict[str, object]] = []
        params = {
            "per_page": str(PER_PAGE),
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=window_days)).isoformat(),
        }
        response = client.get(EVENTS_API, params=params)
        response.raise_for_status()
        payload = response.json()
        events.extend(payload.get("events", []))
        next_url = payload.get("next_rest_url")
        while next_url:
            response = client.get(next_url)
            # Tribe can 404 past the final page rather than returning empty.
            if response.status_code == httpx.codes.NOT_FOUND:
                break
            response.raise_for_status()
            payload = response.json()
            events.extend(payload.get("events", []))
            next_url = payload.get("next_rest_url")
        return events
    finally:
        if own_client:
            client.close()


def _text(value: object) -> str:
    """Unescape HTML entities Tribe leaves in text fields and trim."""
    return html.unescape(str(value)).strip() if value else ""


def _split_bill(title: str) -> tuple[str, list[str]]:
    """Split a ``<br>``-separated title into (headliner, support). Segments
    are unescaped and trimmed; empties dropped."""
    segments = [
        cleaned for raw in _BR_RE.split(title) if (cleaned := _text(raw))
    ]
    if not segments:
        return "", []
    return segments[0], segments[1:]


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Tribe event dicts to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable.

    Skips all-day entries, events hidden from listings, and clearly-non-music
    titles. Times are kept as naive venue-local; ingest re-applies the venue
    tz. ``today`` is injected so the window doesn't depend on the clock, and
    because Tribe's server-side ``end_date`` filter isn't strict.
    """
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        if event.get("all_day") or event.get("hide_from_listings"):
            continue
        start_raw = event.get("start_date")
        title_raw = event.get("title")
        if not isinstance(start_raw, str) or not isinstance(title_raw, str):
            continue
        headliner, support = _split_bill(title_raw)
        if not headliner or _is_non_music(_text(title_raw)):
            continue
        start_local = dt.datetime.strptime(start_raw, _TRIBE_DT)
        end_raw = event.get("end_date")
        end_local = (
            dt.datetime.strptime(end_raw, _TRIBE_DT)
            if isinstance(end_raw, str)
            else None
        )
        if not (today <= start_local.date() <= window_end):
            continue
        ticket_url = _text(event.get("website")) or None
        price_text = _text(event.get("cost")) or None
        source_url = _text(event.get("url")) or CALENDAR_URL
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=start_local,
                end_local=end_local,
                doors_local=None,
                ticket_url=ticket_url,
                price_text=price_text,
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    today = dt.date.today()
    return parse_events(fetch_events(today), today)


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
