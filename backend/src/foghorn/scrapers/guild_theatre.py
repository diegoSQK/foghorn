"""Guild Theatre scraper.

Source: the server-rendered Webflow homepage at ``https://guildtheatre.com/``
(foghorn's first Peninsula venue — a 500-cap nonprofit room in Menlo Park).
Each show card embeds a ``<script type="application/ld+json">`` schema.org
``Event`` (name, ``startDate`` as a bare date like ``"Jul 09, 2026"``, a
``Place``, a ``PerformingGroup``, and an ``Offer`` whose ``url`` is the Tixr
ticket link). The JSON-LD carries no start *time*, so the parser pairs each
block with the card markup that follows it, which renders
``door time: 7:00 pm`` / ``show starts: 8:00 pm``. Cards without a parseable
start time are skipped — a bare date never becomes a show.

The calendar is overwhelmingly touring music, but comedy nights and similar
non-music bookings appear occasionally; those carry a strong title signal and
are dropped. Ambiguous titles (tribute nights, spoken-word-adjacent evenings)
are kept per the ticket.

Runnable standalone: ``python -m foghorn.scrapers.guild_theatre`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
from typing import Any

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "guild_theatre"

EVENTS_URL = "https://guildtheatre.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Titles with a strong non-music signal (the Guild books occasional stand-up
# and film nights alongside the music calendar). Heuristic, knowingly
# imperfect — revisit if it misfires.
_NON_MUSIC_SIGNALS = (
    "comedy",
    "comedian",
    "stand up",
    "stand-up",
    "movie",
    "screening",
    "trivia",
    "karaoke",
    "bingo",
    "private event",
)

_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
# The card markup after each JSON-LD block renders
# `<div class="text-block-19">door time:</div><div class="text-block-19">7:00 pm</div>`
# (and the same shape for "show starts:").
_DOOR_RE = re.compile(
    r'class="text-block-19">\s*door time:\s*</div>\s*'
    r'<div class="text-block-19">\s*([^<]+?)\s*</div>',
    re.IGNORECASE,
)
_STARTS_RE = re.compile(
    r'class="text-block-19">\s*show starts:\s*</div>\s*'
    r'<div class="text-block-19">\s*([^<]+?)\s*</div>',
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
    """Unescape HTML entities (names arrive as ``Chasta&#39;s ...``) and
    collapse whitespace, without otherwise altering the venue's string."""
    return " ".join(html_lib.unescape(text).split())


def _parse_start_date(raw: str) -> dt.date | None:
    """Parse the JSON-LD ``startDate``. The page currently emits a bare date
    (``"Jul 09, 2026"``); ISO 8601 (with or without an offset) is tolerated in
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
        # Offsets on this venue's feed would be Pacific already; dropping the
        # offset keeps the wall-clock date correct either way.
        parsed = parsed.replace(tzinfo=None)
    return parsed.date()


def _parse_time(raw: str) -> dt.time | None:
    raw = raw.strip()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return dt.datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def _card_time(pattern: re.Pattern[str], html: str, start: int, end: int) -> dt.time | None:
    """Extract a door/show time from the card markup segment
    ``html[start:end]`` that follows a JSON-LD block."""
    match = pattern.search(html, start, end)
    return _parse_time(match.group(1)) if match else None


def _first_offer(offers: Any) -> dict[str, Any] | None:
    """Normalize ``offers`` (a single Offer object today, possibly a list per
    the schema.org spec) to its first entry."""
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    return offers if isinstance(offers, dict) else None


def _price_text(offer: dict[str, Any] | None) -> str | None:
    """``"35"`` -> ``"$35"`` (decimals like ``"97.09"`` pass through). A zero
    price is treated as unknown rather than free — Webflow stamps ``"0"`` when
    pricing isn't loaded into the schema."""
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
        # The door/show times live in the card markup between this JSON-LD
        # block and the next one. A card without a parseable show time is
        # skipped — a bare date can't become a ScrapedShow start.
        segment_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(html)
        )
        start_time = _card_time(_STARTS_RE, html, match.end(), segment_end)
        if start_time is None:
            continue
        door_time = _card_time(_DOOR_RE, html, match.end(), segment_end)
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
                doors_local=(
                    dt.datetime.combine(start_date, door_time) if door_time else None
                ),
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
