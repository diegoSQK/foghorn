"""The Knockout scraper.

Source: the venue's **Squarespace calendar collection JSON**. The Knockout (a
Mission punk/rock bar at 3223 Mission St) lists shows on
``theknockoutsf.com/calendar2``, a Squarespace 7.1 calendar block whose events
live in collection ``668dcda020574371451c8e12``. Squarespace serves that
collection month-by-month as JSON at ``/api/open/GetItemsByMonth`` — each item
carries the title, an epoch-millisecond start instant, and the per-event page
URL. That beats the rendered page, which is empty until the calendar block's
JS runs. (The site's older ``/calendar`` events collection and its Dice widget
partner key are both stale — 2023 test entries and zero events respectively.)

**Bill splitting.** The Knockout titles multi-act bills with "+" separators
and appends a set-time note ("PLUMMET + STARBELLIED BUG + SACRAMENTO + DEAD
DOG FARM (7PM - CLOSE)"). The trailing time note is stripped, then the bill is
split on "+" into headliner + support. The month JSON carries no ticket links
or prices (the event bodies are only on the per-event pages, which we don't
fetch), so ``ticket_url``/``price_text`` are always ``None``.

Runnable standalone: ``python -m foghorn.scrapers.the_knockout`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_knockout"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://theknockoutsf.com"
EVENTS_API = f"{BASE_URL}/api/open/GetItemsByMonth"
# The calendar block's events collection, read from the block's
# ``data-block-json`` on /calendar2.
COLLECTION_ID = "668dcda020574371451c8e12"
# Human-viewable calendar (also the venue's seed calendar_url) — fallback
# provenance when an item carries no per-event URL.
CALENDAR_URL = f"{BASE_URL}/calendar2"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The Knockout mixes its live bills and DJ dance parties with clearly
# non-music bar programming: karaoke, trivia, bingo, comedy, and a
# drink-and-draw night. Those are dropped on title signal; ambiguous ones
# (DJ/dance parties, vinyl happy hours, open mics) are kept.
_NON_MUSIC_SIGNALS = (
    "karaoke",
    "trivia",
    "comedy",
    "bingo",
    "private event",
    "drink & draw",
    "watch party",
)

# Trailing set-time note: "(9PM - CLOSE)", "(6pM - 9PM)", "(8p - close)", …
_TIME_NOTE_RE = re.compile(r"\s*\([^()]*(?:\d\s*[ap]\.?m?\b|close)[^()]*\)\s*$", re.IGNORECASE)


def _is_non_music(title: str) -> bool:
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _months(today: dt.date, window_end: dt.date) -> list[str]:
    """The ``MM-YYYY`` month keys covering ``[today, window_end]``."""
    months: list[str] = []
    year, month = today.year, today.month
    while (year, month) <= (window_end.year, window_end.month):
        months.append(f"{month:02d}-{year}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def fetch_events(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Fetch every calendar month overlapping ``[today, today + window_days]``.
    ``client`` is injectable so tests can drive the month requests with a mock
    transport instead of the network."""
    window_end = today + dt.timedelta(days=window_days)
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        events: list[dict[str, object]] = []
        for month in _months(today, window_end):
            response = client.get(
                EVENTS_API, params={"month": month, "collectionId": COLLECTION_ID}
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                events.extend(payload)
        return events
    finally:
        if own_client:
            client.close()


def _clean_title(raw: str) -> str:
    """Unescape entities, collapse whitespace, and strip the trailing
    "(9PM - CLOSE)"-style set-time note."""
    text = " ".join(html.unescape(raw).split())
    return _TIME_NOTE_RE.sub("", text).strip()


def _split_bill(title: str) -> tuple[str, list[str]]:
    """Split a "+"-separated bill into (headliner, support). "&" inside a
    segment is part of an act's name ("MUK MUK & THE KEWKS")."""
    parts = [part.strip() for part in re.split(r"\s\+\s", title) if part.strip()]
    if len(parts) <= 1:
        return title, []
    return parts[0], parts[1:]


def _start_local(item: dict[str, object]) -> dt.datetime | None:
    """``startDate`` is a UTC epoch in milliseconds; convert to naive
    venue-local time (the tz is re-applied at ingest)."""
    raw = item.get("startDate")
    if not isinstance(raw, int | float):
        return None
    instant = dt.datetime.fromtimestamp(raw / 1000, tz=dt.UTC)
    return instant.astimezone(VENUE_TZ).replace(tzinfo=None, microsecond=0)


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Squarespace calendar items to ``ScrapedShow``s in ``[today, today +
    window_days]``. Pure / fixture-testable; ``today`` is injected so the
    window doesn't depend on the clock."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[str] = set()
    for item in events:
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                continue
            seen.add(item_id)
        title_raw = item.get("title")
        if not isinstance(title_raw, str):
            continue
        title = _clean_title(title_raw)
        if not title or _is_non_music(title):
            continue
        start_local = _start_local(item)
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue
        headliner, support = _split_bill(title)
        full_url = item.get("fullUrl")
        source_url = (
            f"{BASE_URL}{full_url}"
            if isinstance(full_url, str) and full_url.startswith("/")
            else CALENDAR_URL
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=start_local,
                doors_local=None,
                ticket_url=None,
                price_text=None,
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
