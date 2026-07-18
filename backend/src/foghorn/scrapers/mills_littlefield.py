"""Mills College Littlefield Concert Hall scraper.

Source: the hall itself publishes nothing, but **Mills Performing Arts**
(Northeastern Oakland) feeds its site from a public Trumba / 25Live Publisher
calendar whose JSON lives at ``25livepub.collegenet.com`` (.ics and .rss
siblings exist; the JSON is richest). One feed covers every campus
performance space and co-presenter (Mills Music Now, the Center for
Contemporary Music, Other Minds), so this scraper filters to rows whose
``template`` is the explicit ``"Oakland - Music Event"`` discriminator *and*
whose ``location`` names Littlefield — lectures, films, and other halls drop
out on data, not heuristics.

**Extras.** Descriptions carry a "Tickets: $…" line (→ ``price_text``) and a
"Register on Eventbrite" anchor (→ ``ticket_url``); ``permaLinkUrl`` is the
event's provenance page. ``canceled`` rows are skipped. Titles carry a
"— Mills Music Now" series suffix, stripped for the headliner. Volume is
seasonal (Sep–Jun academic programming; a near-empty summer feed is normal).

Runnable standalone: ``python -m foghorn.scrapers.mills_littlefield`` prints
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

VENUE_SLUG = "mills_college_littlefield_concert_hall"

FEED_URL = (
    "https://25livepub.collegenet.com/calendars/"
    "northeastern-oaklandmills-events-performing-arts-events-prod.json"
)
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://performingarts.oakland.northeastern.edu/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_MUSIC_TEMPLATE = "Oakland - Music Event"
_HALL_SIGNAL = "littlefield"
_SERIES_SUFFIX_RE = re.compile(r"\s*[—–-]{1,2}\s*Mills Music Now\s*$", re.IGNORECASE)
_TICKET_URL_RE = re.compile(r'href="(https://www\.eventbrite\.com/e/[^"]+)"')
_PRICE_RE = re.compile(r"Tickets:\s*([^<]+)")


def fetch_events(client: httpx.Client | None = None) -> list[dict[str, object]]:
    """Fetch the Trumba feed. ``client`` is injectable so tests can drive the
    request with a mock transport instead of the network."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(FEED_URL)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []
    finally:
        if own_client:
            client.close()


def _is_truthy_flag(value: object) -> bool:
    """Trumba booleans arrive as JSON bools or "True"/"False" strings."""
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.lower() == "true"


def _clean_text(raw: str) -> str:
    return " ".join(html.unescape(raw).split())


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Trumba rows to ``ScrapedShow``s in ``[today, today + window_days]``:
    music-template rows at Littlefield, not canceled. Pure / fixture-testable;
    ``today`` is injected so the window doesn't depend on the clock."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        if event.get("template") != _MUSIC_TEMPLATE:
            continue
        location = event.get("location")
        if not isinstance(location, str) or _HALL_SIGNAL not in location.lower():
            continue
        if _is_truthy_flag(event.get("canceled")) or _is_truthy_flag(
            event.get("allDay")
        ):
            continue
        start_raw = event.get("startDateTime")
        title_raw = event.get("title")
        if not isinstance(start_raw, str) or not isinstance(title_raw, str):
            continue
        try:
            start_local = dt.datetime.fromisoformat(start_raw)
        except ValueError:
            continue
        if not (today <= start_local.date() <= window_end):
            continue
        title = _SERIES_SUFFIX_RE.sub("", _clean_text(title_raw)).strip()
        if not title:
            continue
        description = event.get("description")
        desc_html = description if isinstance(description, str) else ""
        ticket_match = _TICKET_URL_RE.search(desc_html)
        price_match = _PRICE_RE.search(desc_html)
        perma = event.get("permaLinkUrl")
        source_url = perma if isinstance(perma, str) and perma else CALENDAR_URL
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=ticket_match.group(1) if ticket_match else None,
                price_text=(
                    _clean_text(price_match.group(1)) or None
                    if price_match
                    else None
                ),
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live feed for the next ~90 days."""
    return parse_events(fetch_events(), dt.date.today())


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
