"""Cornerstone Berkeley scraper.

Source: the server-rendered events page at
``https://cornerstoneberkeley.com/events/``. Each show card on the Webflow
page embeds a ``<script type="application/ld+json">`` schema.org ``Event``
(name, ``startDate`` as a date like ``"Jul 03, 2026"``, a ``Place``, a
``PerformingGroup``, and an ``Offer`` whose ``url`` is the Tixr ticket link).
The JSON-LD carries no start *time*, so the parser pairs each block with the
card markup that follows it, which renders ``starts 8:30 pm``.

Cornerstone is a music hall first, but the calendar mixes in comedy nights and
private-style bookings (class reunions); those carry a strong non-music title
signal and are dropped. Ambiguous titles are kept per the ticket.

Runnable standalone: ``python -m foghorn.scrapers.cornerstone_berkeley``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
from typing import Any

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "cornerstone_berkeley"

EVENTS_URL = "https://cornerstoneberkeley.com/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Titles with a strong non-music signal. Comedy tours and reunions are booked
# here alongside the music calendar; DJ/dance/kids-party nights are kept per
# the ticket. Heuristic, knowingly imperfect — revisit if it misfires.
_NON_MUSIC_SIGNALS = (
    "comedy",
    "reunion",
    "trivia",
    "movie",
    "screening",
    "karaoke",
    "bingo",
    "private event",
)

_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
# The card markup after each JSON-LD block renders the start time as
# `<div class="doors-time">starts</div><div class="doors-time">8:30 pm</div>`.
_STARTS_RE = re.compile(
    r'class="doors-time">\s*(?:starts|doors)\s*</div>\s*'
    r'<div class="doors-time">\s*([^<]+?)\s*</div>',
    re.IGNORECASE,
)


def fetch_html(url: str = EVENTS_URL) -> str:
    """Fetch the events page. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _is_non_music(name: str) -> bool:
    lowered = name.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _clean(text: str) -> str:
    """Unescape HTML entities (names arrive as ``Kelsy Karter &amp; ...``) and
    collapse whitespace, without otherwise altering the venue's string."""
    return " ".join(html_lib.unescape(text).split())


def _parse_start_date(raw: str) -> dt.date | None:
    """Parse the JSON-LD ``startDate``. The page currently emits a bare date
    (``"Jul 03, 2026"``); ISO 8601 (with or without an offset) is tolerated in
    case Webflow starts emitting spec-shaped values."""
    raw = raw.strip()
    try:
        return dt.datetime.strptime(raw, "%b %d, %Y").date()
    except ValueError:
        pass
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        # Offsets on this venue's feed would be Pacific already; normalizing
        # via the offset keeps the wall-clock date correct either way.
        parsed = parsed.replace(tzinfo=None)
    return parsed.date()


def _parse_start_time(raw: str) -> dt.time | None:
    raw = raw.strip()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return dt.datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def _first_offer(offers: Any) -> dict[str, Any] | None:
    """Normalize ``offers`` (a single Offer object today, possibly a list per
    the schema.org spec) to its first entry."""
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    return offers if isinstance(offers, dict) else None


def _price_text(offer: dict[str, Any] | None) -> str | None:
    """``"28"`` -> ``"$28"``. The page stamps ``"0"`` on shows whose pricing
    isn't loaded into the schema (including ticketed ones), so zero is treated
    as unknown rather than free."""
    if offer is None:
        return None
    raw = str(offer.get("price", "")).strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return f"${raw}"


def _support_names(performer: Any, headliner: str) -> list[str]:
    """schema.org allows a list of performers; today the page emits a single
    ``PerformingGroup`` duplicating the event name. Any listed performer that
    isn't the headliner itself becomes support."""
    entries = performer if isinstance(performer, list) else [performer]
    names = [
        _clean(str(entry.get("name", "")))
        for entry in entries
        if isinstance(entry, dict)
    ]
    return [name for name in names if name and name != headliner]


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per musical JSON-LD Event in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    window_end = today + dt.timedelta(days=window_days)
    matches = list(_LD_JSON_RE.finditer(html))

    shows: list[ScrapedShow] = []
    for index, match in enumerate(matches):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Event":
            continue
        name = _clean(str(data.get("name", "")))
        if not name or _is_non_music(name):
            continue
        start_raw = data.get("startDate")
        start_date = _parse_start_date(str(start_raw)) if start_raw else None
        if start_date is None or not (today <= start_date <= window_end):
            continue
        # The start time lives in the card markup between this JSON-LD block
        # and the next one. A card without a parseable time is skipped — a
        # bare date can't become a ScrapedShow start (mirrors the .ics
        # scrapers skipping all-day entries).
        segment_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(html)
        )
        time_match = _STARTS_RE.search(html, match.end(), segment_end)
        start_time = _parse_start_time(time_match.group(1)) if time_match else None
        if start_time is None:
            continue
        offer = _first_offer(data.get("offers"))
        ticket_url = str(offer["url"]) if offer and offer.get("url") else None
        # Events carry no per-show page; the listing page is the provenance
        # (JSON-LD "url" would win if the site ever adds one).
        source_url = str(data.get("url") or EVENTS_URL)
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=name,
                support_raw=_support_names(data.get("performer"), name),
                start_local=dt.datetime.combine(start_date, start_time),
                doors_local=None,
                ticket_url=ticket_url,
                price_text=_price_text(offer),
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live page for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


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
