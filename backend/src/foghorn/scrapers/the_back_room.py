"""The Back Room scraper.

Source: the venue's Humanitix collection page at
``https://collections.humanitix.com/the-back-room-calendar`` (the intimate
acoustic/jazz/folk listening room at 1984 Bonita Ave, Berkeley — its own site,
backroommusic.com, links there for the calendar). Two complementary reads of
that SvelteKit app:

1. The server-rendered HTML embeds a schema.org ``ItemList`` JSON-LD block
   whose ``Event`` items carry offset-qualified ``startDate``s and per-tier
   ``Offer`` prices — but only for the first ~12 upcoming events (the rest sit
   behind a "Load more events" button).
2. The page's serialized state lists *every* collection event id; the button
   hydrates them via the public tRPC endpoint
   ``/trpc/events.getEventsFromIds``, which we call directly to cover the full
   window. Its payload has titles, offset-qualified start datetimes, and
   per-event/ticket URLs — but no prices.

The parser merges the two by event slug: the tRPC list is authoritative for
which shows exist, and JSON-LD contributes ``price_text`` where present. If
the tRPC id list ever fails to extract, the JSON-LD events alone still yield
the near-term calendar.

``startDate`` offsets are venue-local Pacific already; they're normalized
through ``America/Los_Angeles`` to naive local datetimes (the ``ScrapedShow``
contract) so a UTC-shaped feed change wouldn't corrupt wall-clock times.

Runnable standalone: ``python -m foghorn.scrapers.the_back_room`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import urllib.parse
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_back_room"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

COLLECTION_URL = "https://collections.humanitix.com/the-back-room-calendar"
TRPC_EVENTS_URL = "https://collections.humanitix.com/trpc/events.getEventsFromIds"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Page size for the tRPC fetch (the collection currently holds ~33 events;
# the loop follows ``hasNextPage`` regardless).
TRPC_PAGE_LIMIT = 50

# Titles with a strong non-music signal. The Back Room is a listening room —
# essentially everything it books is music (jams and singalongs included) —
# but the filter guards against the odd spoken-word/comedy booking.
_NON_MUSIC_SIGNALS = (
    "comedy",
    "comedian",
    "stand up",
    "stand-up",
    "movie",
    "screening",
    "trivia",
    "private event",
)

_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
# The SvelteKit state serializes the full collection id list as a JS array of
# 24-hex Mongo ids immediately before the ``showLoadMore`` key.
_ID_LIST_RE = re.compile(r"\[(\"[0-9a-f]{24}\"(?:,\"[0-9a-f]{24}\")*)\],showLoadMore")
_HEX_ID_RE = re.compile(r"[0-9a-f]{24}")


def fetch_html(url: str = COLLECTION_URL) -> str:
    """Fetch the collection page. Kept separate from parsing so tests drive
    the pure functions from fixtures without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def extract_event_ids(html: str) -> list[str]:
    """Pull the collection's full event id list out of the serialized SvelteKit
    state. Returns ``[]`` if the marker isn't found (the JSON-LD fallback in
    ``parse`` still covers the server-rendered events)."""
    match = _ID_LIST_RE.search(html)
    if match is None:
        return []
    return _HEX_ID_RE.findall(match.group(1))


def fetch_events(
    event_ids: list[str], client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Page through ``events.getEventsFromIds`` for the given ids. ``client``
    is injectable so tests can drive this with a mock transport."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        events: list[dict[str, Any]] = []
        skip = 0
        while True:
            payload = {
                "eventIds": event_ids,
                "skip": skip,
                "limit": TRPC_PAGE_LIMIT,
                "stackRecurring": True,
                "showPastEvents": False,
                "privacyLevel": "public",
                "userTimezone": "America/Los_Angeles",
            }
            response = client.get(
                TRPC_EVENTS_URL, params={"input": json.dumps(payload)}
            )
            response.raise_for_status()
            data = response.json()["result"]["data"]
            events.extend(data.get("events", []))
            if not data.get("hasNextPage"):
                break
            skip += TRPC_PAGE_LIMIT
        return events
    finally:
        if own_client:
            client.close()


def _clean(text: str) -> str:
    """Unescape HTML entities (JSON-LD names arrive as ``Blues &amp; Jazz``)
    and collapse whitespace, without otherwise altering the venue's string."""
    return " ".join(html_lib.unescape(text).split())


def _is_non_music(name: str) -> bool:
    lowered = name.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _strip_query(url: str) -> str:
    """Drop the query string (tRPC urls carry a ``?hxchl=hex-col`` tracking
    param; the JSON-LD urls are bare — stripping keeps the two consistent)."""
    return urllib.parse.urlsplit(url)._replace(query="", fragment="").geturl()


def _slug_of(url: str) -> str:
    """``https://events.humanitix.com/<slug>[/tickets]`` -> ``<slug>`` (the
    merge key between the JSON-LD and tRPC views of an event)."""
    path = urllib.parse.urlsplit(url).path.strip("/")
    return path.split("/")[0] if path else ""


def _parse_start(raw: str) -> dt.datetime | None:
    """``"2026-07-03T20:00:00-0700"`` -> naive venue-local datetime. Offsets
    are normalized through the venue tz (a no-op for the Pacific offsets the
    feed emits today, correct if it ever switches to UTC)."""
    try:
        parsed = dt.datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(VENUE_TZ).replace(tzinfo=None)
    return parsed


def _format_price(value: float) -> str:
    return f"${value:g}"


def _price_text(offers: Any) -> str | None:
    """Min/max across the JSON-LD ``Offer`` tiers (GA + student/low-income):
    ``"$15–$20"``, or ``"$20"`` when all tiers price the same. ``None`` when
    nothing priced. ``AggregateOffer`` entries carry no price and are skipped."""
    if not isinstance(offers, list):
        offers = [offers]
    prices: list[float] = []
    for offer in offers:
        if not isinstance(offer, dict) or offer.get("@type") != "Offer":
            continue
        raw = offer.get("price")
        if isinstance(raw, bool) or not isinstance(raw, int | float | str):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            prices.append(value)
    if not prices:
        return None
    low, high = min(prices), max(prices)
    if low == high:
        return _format_price(low)
    return f"{_format_price(low)}–{_format_price(high)}"


def _ld_events(html: str) -> list[dict[str, Any]]:
    """The schema.org ``Event`` items from the page's ``ItemList`` JSON-LD
    block (other blocks — e.g. the host's ``ProfilePage`` — are ignored)."""
    events: list[dict[str, Any]] = []
    for match in _LD_JSON_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "ItemList":
            continue
        for entry in data.get("itemListElement", []):
            if not isinstance(entry, dict):
                continue
            item = entry.get("item")
            if isinstance(item, dict) and item.get("@type") == "Event":
                events.append(item)
    return events


def parse(
    html: str,
    events: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Merge the page's JSON-LD events (first ~12, with prices) with the tRPC
    event list (complete, no prices) into one ``ScrapedShow`` per musical
    event in ``[today, today + window_days]``.

    Pure / fixture-testable: ``today`` is injected, and both inputs are plain
    data. Events are keyed by slug; JSON-LD wins where both know a show (it
    carries the price), tRPC fills in the rest.
    """
    window_end = today + dt.timedelta(days=window_days)
    by_slug: dict[str, ScrapedShow] = {}

    for item in _ld_events(html):
        url = _strip_query(str(item.get("url", "")))
        slug = _slug_of(url)
        name = _clean(str(item.get("name", "")))
        start = _parse_start(str(item.get("startDate", "")))
        if not slug or not name or start is None:
            continue
        offers = item.get("offers", [])
        ticket_url = next(
            (
                _strip_query(str(o["url"]))
                for o in (offers if isinstance(offers, list) else [offers])
                if isinstance(o, dict) and o.get("url")
            ),
            None,
        )
        by_slug[slug] = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=name,
            support_raw=[],
            start_local=start,
            doors_local=None,
            ticket_url=ticket_url,
            price_text=_price_text(offers),
            source_url=url,
        )

    for event in events:
        slug = str(event.get("slug", ""))
        if not slug or slug in by_slug:
            continue
        name = _clean(str(event.get("title", "")))
        dates = event.get("dates")
        start_raw = dates.get("timeTagDate") if isinstance(dates, dict) else None
        start = _parse_start(str(start_raw)) if start_raw else None
        if not name or start is None:
            # No usable start datetime — never invent one.
            continue
        urls_raw = event.get("urls")
        urls: dict[str, Any] = urls_raw if isinstance(urls_raw, dict) else {}
        event_url = _strip_query(str(urls.get("url", ""))) or COLLECTION_URL
        tickets_url = _strip_query(str(urls.get("ticketsUrl", ""))) or None
        by_slug[slug] = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=name,
            support_raw=[],
            start_local=start,
            doors_local=None,
            ticket_url=tickets_url,
            price_text=None,
            source_url=event_url,
        )

    shows = [
        show
        for show in by_slug.values()
        if today <= show.start_local.date() <= window_end
        and not _is_non_music(show.headliner_raw)
    ]
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live collection for the next ~90 days."""
    html = fetch_html()
    event_ids = extract_event_ids(html)
    events = fetch_events(event_ids) if event_ids else []
    return parse(html, events, dt.date.today())


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
