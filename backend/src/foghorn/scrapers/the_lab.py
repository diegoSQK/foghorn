"""The Lab scraper.

Source: the nonprofit's **Squarespace events collection JSON**. The Lab (2948
16th St, Mission — a 40-year experimental art/music space) lists programming
at ``thelab.org/projects``; appending ``?format=json`` returns the
collection's structured payload whose ``upcoming`` array carries every posted
future event — the same shape as Piedmont Piano's calendar, with the
stale-collection trap already avoided because the payload itself pre-splits
``upcoming`` from ``past``.

**Filtering & extras.** Music events carry a ``Concert`` category; those are
kept outright. The Lab also programs screenings, readings, and open studios —
uncategorized items are kept unless the title signals a non-music event, per
the "when ambiguous, keep" rule. Every current concert tickets through Dice
(``link.dice.fm`` anchors in the body HTML → ``ticket_url``). ``startDate``
epoch values carry stray sub-second precision, which truncates away in the
conversion.

Runnable standalone: ``python -m foghorn.scrapers.the_lab`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_lab"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://www.thelab.org"
# Human-viewable calendar (also the venue's seed calendar_url) — fallback
# provenance when an item carries no per-event URL.
CALENDAR_URL = f"{BASE_URL}/projects"
EVENTS_JSON_URL = f"{CALENDAR_URL}?format=json"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The category The Lab puts on music events; carrying it keeps an item
# outright.
_CONCERT_CATEGORY = "Concert"
# Non-music programming, dropped on title signal when an item has no Concert
# category (uncategorized concerts do occur; ambiguous titles are kept).
_NON_MUSIC_TITLE_RE = re.compile(
    r"\bscreening\b|\bfilm\b|\breading\b|\bbook launch\b|\btalk\b"
    r"|\bworkshop\b|\bopen studios\b|\bsymposium\b|\bfundraiser\b",
    re.IGNORECASE,
)

# Ticket button in the event body: <a href="https://link.dice.fm/…">
_TICKET_URL_RE = re.compile(r'href="(https?://link\.dice\.fm/[^"]+)"')


def fetch_events(client: httpx.Client | None = None) -> dict[str, object]:
    """Fetch the projects collection JSON. ``client`` is injectable so tests
    can drive the request with a mock transport instead of the network."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(EVENTS_JSON_URL)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    finally:
        if own_client:
            client.close()


def _clean_text(raw: str) -> str:
    """Unescape entities and collapse whitespace (incl. non-breaking spaces)."""
    return " ".join(html.unescape(raw).split())


def _is_concert(item: dict[str, object], title: str) -> bool:
    """Keep Concert-categorized items outright; otherwise drop only on a
    non-music title signal."""
    categories = item.get("categories")
    if isinstance(categories, list) and _CONCERT_CATEGORY in categories:
        return True
    return not _NON_MUSIC_TITLE_RE.search(title)


def _ticket_url(item: dict[str, object]) -> str | None:
    for key in ("excerpt", "body"):
        value = item.get(key)
        if isinstance(value, str):
            match = _TICKET_URL_RE.search(value)
            if match:
                return match.group(1)
    return None


def _start_local(item: dict[str, object]) -> dt.datetime | None:
    """``startDate`` is a UTC epoch in milliseconds (with stray sub-second
    noise); convert to naive venue-local time (tz re-applied at ingest)."""
    raw = item.get("startDate")
    if not isinstance(raw, int | float):
        return None
    instant = dt.datetime.fromtimestamp(raw / 1000, tz=dt.UTC)
    return instant.astimezone(VENUE_TZ).replace(tzinfo=None, microsecond=0)


def parse_events(
    payload: dict[str, object], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map the collection JSON's ``upcoming`` items to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable; ``today`` is
    injected so the window doesn't depend on the clock."""
    raw_items = payload.get("upcoming")
    if not isinstance(raw_items, list):
        return []
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                continue
            seen.add(item_id)
        title_raw = item.get("title")
        if not isinstance(title_raw, str):
            continue
        title = _clean_text(title_raw)
        if not title or not _is_concert(item, title):
            continue
        start_local = _start_local(item)
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue
        full_url = item.get("fullUrl")
        source_url = (
            f"{BASE_URL}{full_url}"
            if isinstance(full_url, str) and full_url.startswith("/")
            else CALENDAR_URL
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=_ticket_url(item),
                price_text=None,
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
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
