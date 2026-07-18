"""Kuumbwa Jazz Center scraper.

Source: the venue's WordPress site runs **The Events Calendar** (Tribe),
same REST API as Mr. Tipple's/Madrone/Dresher at
``/wp-json/tribe/events/v1/events``. Kuumbwa (Santa Cruz's nonprofit jazz
room since 1975) is foghorn's first Santa Cruz-region venue — the deepest
calendar found by the July 2026 long-tail audit (~77 events on a two-year
horizon).

**The cache trap (why the browser User-Agent).** The site fronts WordPress
with a LiteSpeed cache that, for non-browser User-Agents, serves one stale
cached response for *any* query string — ``per_page``, ``start_date``, and
``page`` are all silently ignored, so pagination loops forever on the same
ten events. A browser UA bypasses that cache tier and the API honors its
params. This scraper therefore uses a browser UA (unlike the other
scrapers' ``foghorn-scraper`` string) — one polite nightly walk, but the
identification convention loses to correctness here. The pagination loop
also keeps an id-seen guard so a cache regression degrades to a partial
scrape instead of an infinite loop.

**Title conventions.** Kuumbwa marks state in the title: ``CANCELLED –
<act>`` rows are skipped; a ``RESCHEDULED: `` prefix is stripped (the row
carries the new date). Master classes/workshops are non-music programming
and drop on title signal.

Runnable standalone: ``python -m foghorn.scrapers.kuumbwa_jazz_center``
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

VENUE_SLUG = "kuumbwa_jazz_center"

EVENTS_API = "https://www.kuumbwajazz.org/wp-json/tribe/events/v1/events"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://www.kuumbwajazz.org/calendar/"
# See the module docstring — the polite foghorn UA gets a param-ignoring
# cached response; a browser UA reaches the live API.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 50
MAX_PAGES = 10
REQUEST_TIMEOUT = 30.0
_TRIBE_DT = "%Y-%m-%d %H:%M:%S"

_CANCELLED_RE = re.compile(r"^\s*CANCEL?LED\b", re.IGNORECASE)
_RESCHEDULED_PREFIX_RE = re.compile(r"^\s*RESCHEDULED:?\s*", re.IGNORECASE)
# Non-music programming (education arm): master classes, workshops, camps.
_NON_MUSIC_SIGNALS = (
    "master class",
    "masterclass",
    "workshop",
    "jazz camp",
    "summer camp",
    "auditions",
    "fundraiser",
    "private event",
)


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
    ``[today, today + window_days]``. Pages are followed via
    ``next_rest_url`` with an id-seen guard: a page that adds no new event
    ids ends the walk (the LiteSpeed cache trap — see module docstring —
    would otherwise loop one cached page forever). ``client`` is injectable
    so tests drive pagination with a mock transport."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        events: list[dict[str, object]] = []
        seen_ids: set[object] = set()
        params = {
            "per_page": str(PER_PAGE),
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=window_days)).isoformat(),
        }
        response = client.get(EVENTS_API, params=params)
        response.raise_for_status()
        payload = response.json()
        for _ in range(MAX_PAGES):
            new = [
                event
                for event in payload.get("events", [])
                if event.get("id") not in seen_ids
            ]
            if not new:
                break
            events.extend(new)
            seen_ids.update(event.get("id") for event in new)
            next_url = payload.get("next_rest_url")
            if not next_url:
                break
            response = client.get(next_url)
            # Tribe can 404 past the final page rather than returning empty.
            if response.status_code == httpx.codes.NOT_FOUND:
                break
            response.raise_for_status()
            payload = response.json()
        return events
    finally:
        if own_client:
            client.close()


def _text(value: object) -> str:
    """Unescape HTML entities Tribe leaves in text fields and trim."""
    return html.unescape(str(value)).strip() if value else ""


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Tribe event dicts to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable.

    Skips all-day rows, hidden rows, ``CANCELLED`` rows, and non-music
    (education) titles; strips the ``RESCHEDULED:`` prefix. Times are naive
    venue-local; ingest re-applies the venue tz. ``today`` is injected so
    the window doesn't depend on the clock and because Tribe's server-side
    ``end_date`` filter isn't strict.
    """
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        if event.get("all_day") or event.get("hide_from_listings"):
            continue
        start_raw = event.get("start_date")
        title = _text(event.get("title"))
        if not isinstance(start_raw, str) or not title:
            continue
        if _CANCELLED_RE.search(title) or _is_non_music(title):
            continue
        title = _RESCHEDULED_PREFIX_RE.sub("", title).strip()
        if not title:
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
