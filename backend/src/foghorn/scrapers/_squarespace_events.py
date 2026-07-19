"""Shared Squarespace events-collection scraper core.

Several venues (Piedmont Piano and The Lab first; the Dawn Club, Pier 23,
and the Sound Room via this helper) publish a Squarespace events collection
whose ``?format=json`` payload pre-splits ``upcoming`` from ``past`` —
title, epoch-millisecond ``startDate``/``endDate``, per-event ``fullUrl``,
and body HTML with ticket links. Venue modules supply the constants
(collection URL, non-music filter, ticket-link pattern) and re-export
``scrape``; parsing stays pure/fixture-testable via ``parse_items``.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import EventType, ScrapedShow

VENUE_TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0


def fetch_collection(
    events_json_url: str, client: httpx.Client | None = None
) -> dict[str, object]:
    """Fetch a collection's ``?format=json`` payload."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(events_json_url)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    finally:
        if own_client:
            client.close()


def _clean_text(raw: str) -> str:
    return " ".join(html.unescape(raw).split())


def _local(epoch_ms: object) -> dt.datetime | None:
    if not isinstance(epoch_ms, int | float):
        return None
    instant = dt.datetime.fromtimestamp(epoch_ms / 1000, tz=dt.UTC)
    return instant.astimezone(VENUE_TZ).replace(tzinfo=None, microsecond=0)


def parse_items(
    payload: dict[str, object],
    today: dt.date,
    *,
    venue_slug: str,
    base_url: str,
    calendar_url: str,
    non_music_re: re.Pattern[str] | None = None,
    ticket_url_re: re.Pattern[str] | None = None,
    jam_re: re.Pattern[str] | None = None,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """The collection's ``upcoming`` items → ``ScrapedShow``s. Stated
    ``endDate``s are kept (the ingest guard drops equal-to-start noise)."""
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
        if not title or (non_music_re and non_music_re.search(title)):
            continue
        start_local = _local(item.get("startDate"))
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue
        end_local = _local(item.get("endDate"))
        full_url = item.get("fullUrl")
        source_url = (
            f"{base_url}{full_url}"
            if isinstance(full_url, str) and full_url.startswith("/")
            else calendar_url
        )
        body = " ".join(
            value
            for key in ("excerpt", "body")
            if isinstance(value := item.get(key), str)
        )
        ticket_match = ticket_url_re.search(body) if ticket_url_re else None
        event_type: EventType | None = (
            "jam" if jam_re and jam_re.search(title) else None
        )
        shows.append(
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                end_local=end_local,
                doors_local=None,
                ticket_url=ticket_match.group(1) if ticket_match else None,
                price_text=None,
                source_url=source_url,
                event_type=event_type,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows
