"""Stanford Jazz Workshop scraper.

Source: stanfordjazz.org is WordPress running **The Events Calendar** (Tribe),
exposing the same JSON REST API as Mr. Tipple's / Madrone / Dresher at
``/wp-json/tribe/events/v1/events``. SJW is a presenter, not a room: festival
concerts land at Dinkelspiel Auditorium and Campbell Recital Hall, and the
year-round CoHo Jams at the campus coffee house — all on Stanford campus, so
they're modeled as one umbrella venue per the Cal Performances precedent
(multi-hall campus presenter = one seed row). Stanford Live (Bing Concert
Hall / Frost Amphitheater) is a separate organization and site, out of scope.

**Data-quality notes.**

* Programming is seasonal: the Stanford Jazz Festival runs June–August, with
  only the roughly-monthly CoHo Jams otherwise — a near-empty off-season feed
  is normal (Mills Littlefield precedent).
* The calendar publishes public performances only (categories
  ``stanford-jazz-festival`` and ``year-round-programs``); education
  programming (Jazz Camp etc.) isn't posted here, so no non-music filtering.
* The recurring "CoHo Jams" rows are open jam sessions — tagged
  ``event_type="jam"`` explicitly, because ingest's conservative title regex
  wouldn't catch the name. Only ``year-round-programs`` rows qualify: the
  festival's ticketed "SJW All-Star Jam" closer is a show, and is left to
  ingest's default.
* Tribe pads ``end_date`` with a copy of ``start_date`` when no end is
  stated — those are dropped rather than stored as zero-length ends. CoHo
  Jams rows carry a real end.
* Titles arrive with HTML entities (``&#038;``, ``&#8217;``) — unescaped.

Runnable standalone: ``python -m foghorn.scrapers.stanford_jazz_workshop``
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

VENUE_SLUG = "stanford_jazz_workshop"

EVENTS_API = "https://stanfordjazz.org/wp-json/tribe/events/v1/events"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://stanfordjazz.org/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 50
REQUEST_TIMEOUT = 30.0
# Tribe's start_date/end_date are local, formatted "YYYY-MM-DD HH:MM:SS".
_TRIBE_DT = "%Y-%m-%d %H:%M:%S"

# The year-round series category — the only rows eligible for the jam tag.
_YEAR_ROUND_CATEGORY = "year-round-programs"
_JAM_TITLE_RE = re.compile(r"\bjams?\b", re.IGNORECASE)


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
    ``&#038;``) and trim."""
    return html.unescape(str(value)).strip() if value else ""


def _is_jam(event: dict[str, object], title: str) -> bool:
    """The recurring year-round jam sessions ("CoHo Jams"). Festival rows
    never qualify — the ticketed "SJW All-Star Jam" closer is a show."""
    categories = event.get("categories")
    if not isinstance(categories, list):
        return False
    slugs = {
        c.get("slug") for c in categories if isinstance(c, dict)
    }
    return _YEAR_ROUND_CATEGORY in slugs and bool(_JAM_TITLE_RE.search(title))


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Tribe event dicts to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable.

    Skips all-day entries and events hidden from listings. Times are kept as
    naive venue-local; ingest re-applies the venue tz. ``today`` is injected
    so the window doesn't depend on the clock, and because Tribe's server-side
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
        start_local = dt.datetime.strptime(start_raw, _TRIBE_DT)
        if not (today <= start_local.date() <= window_end):
            continue
        end_raw = event.get("end_date")
        end_local = (
            dt.datetime.strptime(end_raw, _TRIBE_DT)
            if isinstance(end_raw, str)
            else None
        )
        # Tribe pads end_date with the start when no end is stated.
        if end_local == start_local:
            end_local = None
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
                event_type="jam" if _is_jam(event, title) else None,
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
