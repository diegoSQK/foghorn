"""Mr. Tipple's Recording Studio scraper.

Source: the venue's WordPress site runs **The Events Calendar** (Tribe) plugin,
which exposes a clean JSON REST API at ``/wp-json/tribe/events/v1/events``. That
beats scraping the rendered calendar HTML — it's structured, paginated, and
carries tz-aware times, the event URL, the price, and the OpenTable reservation
link directly.

**Domain note.** The Phase 2 seed (and the #7 ticket) had the site as
``mrtipples.com``, which is NXDOMAIN. The live site is ``mrtipplessf.com`` — the
seed's ``website_url`` / ``calendar_url`` are corrected alongside this scraper.

Runnable standalone: ``python -m foghorn.scrapers.mr_tipples`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "mr_tipples"

EVENTS_API = "https://mrtipplessf.com/wp-json/tribe/events/v1/events"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://mrtipplessf.com/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 50
REQUEST_TIMEOUT = 30.0
# Tribe's start_date/end_date are local, formatted "YYYY-MM-DD HH:MM:SS".
_TRIBE_DT = "%Y-%m-%d %H:%M:%S"


def _is_non_show(title: str) -> bool:
    """The venue posts closure markers as calendar entries ("Closed",
    "Closed for Private Event", …). These aren't public shows — drop them."""
    lowered = title.lower()
    return lowered.startswith("closed") or "private event" in lowered


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
    """Unescape HTML entities Tribe leaves in text fields (e.g. ``&#8217;``,
    ``&amp;``) and trim."""
    return html.unescape(str(value)).strip() if value else ""


def parse_events(events: list[dict[str, object]]) -> list[ScrapedShow]:
    """Map Tribe event dicts to ``ScrapedShow``s. Pure / fixture-testable.

    Skips all-day entries and events hidden from listings. Times are kept as
    naive venue-local (``start_date``); ingest re-applies the venue tz.
    Mr. Tipple's is a pure music venue, so there's no non-music filtering.
    """
    shows: list[ScrapedShow] = []
    for event in events:
        if event.get("all_day") or event.get("hide_from_listings"):
            continue
        start_raw = event.get("start_date")
        title = _text(event.get("title"))
        if not isinstance(start_raw, str) or not title or _is_non_show(title):
            continue
        start_local = dt.datetime.strptime(start_raw, _TRIBE_DT)
        end_raw = event.get("end_date")
        end_local = (
            dt.datetime.strptime(end_raw, _TRIBE_DT)
            if isinstance(end_raw, str)
            else None
        )
        ticket_url = _text(event.get("website")) or None
        price_text = _text(event.get("cost")) or None
        source_url = _text(event.get("url")) or CALENDAR_URL
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
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
    return parse_events(fetch_events(dt.date.today()))


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
