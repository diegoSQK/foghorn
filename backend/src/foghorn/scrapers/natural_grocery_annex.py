"""El Cerrito Natural Grocery Annex scraper.

Source: the Natural Grocery Company's WordPress site runs **The Events Calendar**
(Tribe) plugin, exposing the JSON REST API at ``/wp-json/tribe/events/v1/events``.
The Annex (the store's event space at 10387 San Pablo Ave, El Cerrito) hosts
"The Annex Sessions", a weekly early-evening jazz / creative-music series. The
JSON API beats the site's ``?ical=1`` feed here because each event carries a
structured ``venue`` object — the calendar covers the whole grocery company, so
we filter to events explicitly placed at The Annex rather than guessing from
free text.

The calendar mixes the concert series with store programming (wine / chocolate
tastings, sale announcements, art receptions) and posts occasional "No Music
Tonight" markers; those are dropped by a title heuristic that errs toward
inclusion. The venue's series-branding prefix ("The Annex Sessions:") is
stripped so ``headliner_raw`` is the act's own billing.

Runnable standalone: ``python -m foghorn.scrapers.natural_grocery_annex`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "natural_grocery_annex"

EVENTS_API = "https://naturalgrocery.com/wp-json/tribe/events/v1/events"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://naturalgrocery.com/events/"
# Tribe venue slug for The Annex on this site (venue id 114).
ANNEX_VENUE_SLUG = "annex"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 50
REQUEST_TIMEOUT = 30.0
# Tribe's start_date/end_date are local, formatted "YYYY-MM-DD HH:MM:SS".
_TRIBE_DT = "%Y-%m-%d %H:%M:%S"

# "The Annex Sessions:" series branding prefix (occasionally without "The").
_SERIES_PREFIX_RE = re.compile(r"^\s*(?:the\s+)?annex\s+sessions:\s*", re.IGNORECASE)

# The Annex calendar mixes the concert series with store programming. Per the
# house rule we err toward inclusion and only drop events whose title carries a
# strong non-music signal (tastings, sales, gallery receptions) or the series'
# own "No Music Tonight" closure marker. Whole-word matched — "sale" must not
# catch performer names like "Rosales". Heuristic, knowingly imperfect —
# revisit if it misfires.
_NON_MUSIC_RE = re.compile(
    r"\b(?:tasting|wine|reception|sales?|flyer|no\s+music)\b", re.IGNORECASE
)


def _is_non_music(title: str) -> bool:
    return _NON_MUSIC_RE.search(title) is not None


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


def _at_annex(event: dict[str, object]) -> bool:
    """True when the event is explicitly placed at The Annex. The calendar is
    company-wide (Berkeley store included), so venue-less or other-venue events
    don't belong to this scraper's venue."""
    venue = event.get("venue")
    return isinstance(venue, dict) and venue.get("slug") == ANNEX_VENUE_SLUG


def parse_events(
    events: list[dict[str, object]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Map Tribe event dicts to ``ScrapedShow``s for timed musical events at The
    Annex in ``[today, today + window_days]``. Pure / fixture-testable —
    ``today`` is injected (not read from the clock).

    Skips all-day entries, events hidden from listings, events not at The
    Annex, and store programming per ``_NON_MUSIC_SIGNALS``. Times are kept as
    naive venue-local (``start_date``); ingest re-applies the venue tz.
    """
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        if event.get("all_day") or event.get("hide_from_listings"):
            continue
        if not _at_annex(event):
            continue
        start_raw = event.get("start_date")
        title = _text(event.get("title"))
        if not isinstance(start_raw, str) or not title or _is_non_music(title):
            continue
        start_local = dt.datetime.strptime(start_raw, _TRIBE_DT)
        if not (today <= start_local.date() <= window_end):
            continue
        headliner = _SERIES_PREFIX_RE.sub("", title) or title
        ticket_url = _text(event.get("website")) or None
        price_text = _text(event.get("cost")) or None
        source_url = _text(event.get("url")) or CALENDAR_URL
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
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
