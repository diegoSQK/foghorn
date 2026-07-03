"""Piedmont Piano Company scraper.

Source: the showroom's **Squarespace events collection JSON**. Piedmont Piano
Company (a piano showroom + concert series at 1728 San Pablo Ave, Oakland)
lists its concerts on ``piedmontpiano.com/calendar``; appending
``?format=json`` returns the collection's structured payload whose
``upcoming`` array carries every posted future event (title, epoch-millisecond
start instant, per-event page URL, body HTML with the ticket link and price).
The array is not paginated — ``?offset=`` pagination only walks the ``past``
list — so one request covers the window.

**Filtering & extras.** The calendar is nearly all concerts (jazz/classical,
including the "Jazz Piano Masters" series) and items carry a ``Concerts``
category; those are kept outright. Uncategorized items are kept unless the
title signals a non-concert showroom event (lessons, workshops, classes,
sales, open houses). Event bodies embed a ``buytickets.at`` button (→
``ticket_url``) and a "$25 in advance / $30 at the door" line (→
``price_text``); both are ``None`` when absent. Titles are single billings
("Amendola Vs. Blades", "Aimee Nolte & Mike Scott" are act names, not
multi-act bills), so ``support_raw`` is always empty.

Runnable standalone: ``python -m foghorn.scrapers.piedmont_piano`` prints the
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

VENUE_SLUG = "piedmont_piano"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://piedmontpiano.com"
# Human-viewable calendar (also the venue's seed calendar_url) — fallback
# provenance when an item carries no per-event URL.
CALENDAR_URL = f"{BASE_URL}/calendar"
EVENTS_JSON_URL = f"{CALENDAR_URL}?format=json"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The category Squarespace puts on every concert; carrying it keeps an item
# outright (even showroom specials like "Meet Luca Fazioli" that carry it are
# performance events).
_CONCERT_CATEGORY = "Concerts"
# Non-concert showroom programming, dropped on title signal when an item has
# no Concerts category. None are posted today; this guards future listings.
_NON_MUSIC_TITLE_RE = re.compile(
    r"\blessons?\b|\bworkshop\b|\bmasterclass\b|\bclass(?:es)?\b|\bsale\b"
    r"|\bclearance\b|\bopen house\b",
    re.IGNORECASE,
)

# Ticket button in the event body: <a href="https://buytickets.at/piedmontpiano/…">
_TICKET_URL_RE = re.compile(r'href="(https?://buytickets\.at/[^"]+)"')
# Price line in the event body: "$25 in advance / $30 at the door".
_PRICE_RE = re.compile(
    r"\$\d+(?:\.\d{2})?\s+in advance\s*/\s*\$\d+(?:\.\d{2})?\s+at the door",
    re.IGNORECASE,
)

_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_events(client: httpx.Client | None = None) -> dict[str, object]:
    """Fetch the calendar collection JSON. ``client`` is injectable so tests
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


def _raw_html(item: dict[str, object]) -> str:
    """The item's excerpt+body HTML, concatenated (ticket links are anchors in
    the body, so this stays un-stripped)."""
    parts: list[str] = []
    for key in ("excerpt", "body"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _is_concert(item: dict[str, object], title: str) -> bool:
    """Keep Concerts-categorized items outright; otherwise drop only on a
    non-concert title signal (uncategorized concerts do occur)."""
    categories = item.get("categories")
    if isinstance(categories, list) and _CONCERT_CATEGORY in categories:
        return True
    return not _NON_MUSIC_TITLE_RE.search(title)


def _ticket_url(body_html: str) -> str | None:
    match = _TICKET_URL_RE.search(body_html)
    return match.group(1) if match else None


def _price_text(body_html: str) -> str | None:
    text = _clean_text(_TAG_RE.sub(" ", _STYLE_RE.sub(" ", body_html)))
    match = _PRICE_RE.search(text)
    return " ".join(match.group(0).split()) if match else None


def _start_local(item: dict[str, object]) -> dt.datetime | None:
    """``startDate`` is a UTC epoch in milliseconds; convert to naive
    venue-local time (the tz is re-applied at ingest)."""
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
        raw_items = payload.get("items")
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
        body_html = _raw_html(item)
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=_ticket_url(body_html),
                price_text=_price_text(body_html),
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
