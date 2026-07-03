"""Kilowatt scraper.

Source: the **Dice.fm events API**. Kilowatt (a Mission rock bar at 3160 16th
St) sells through Dice; its Squarespace ``/events`` page is just an embedded
Dice event-list widget. The widget's config (visible in the page source)
carries a public API key, and the widget itself reads
``https://events-api.dice.fm/v1/events`` filtered by venue name — structured
JSON with the event name, UTC start instant, venue timezone, doors time (in
``lineup``), ticket prices in cents, and a per-event ticket link. That beats
the page HTML, which is empty until the widget's JS runs.

**Bill splitting.** Kilowatt titles its rock bills as comma lists with an
Oxford-less tail ("La Sombra, Touchy Feely and Clumsy Tungs") and its DJ
nights with "w/" ("Twisterella w/ DJs Galine, Liam and Matt"). We split those
two shapes into headliner + support; a bare "and"/"&" with no comma is left
intact ("Pearl Charles & Carson McHone") since it can't be told apart from a
single band name.

Runnable standalone: ``python -m foghorn.scrapers.kilowatt`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "kilowatt"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

EVENTS_API = "https://events-api.dice.fm/v1/events"
# Public widget key + venue filter, read from the DiceEventListWidget.create()
# config embedded on https://www.kilowattbar.com/events (not a secret — it's
# served to every visitor's browser).
API_KEY = "cxapsVUwK54628CtqISh79lqEA7pdqEH6sJ6Lt5B"
DICE_VENUE_NAME = "Kilowatt"
# Human-viewable calendar (also the venue's seed calendar_url) — fallback
# provenance when an event carries no Dice link.
CALENDAR_URL = "https://www.kilowattbar.com/events"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
PER_PAGE = 24
MAX_PAGES = 20  # safety valve; the feed is date-ascending so we stop early
REQUEST_TIMEOUT = 30.0

# Kilowatt's Dice feed is mostly gigs and DJ nights, but recurring karaoke and
# sports screenings ride along. Titles with a strong non-music signal are
# dropped; ambiguous ones (DJ nights, dance parties, birthday gigs) are kept.
_NON_MUSIC_SIGNALS = (
    "karaoke",
    "watch party",
    "world cup",
    "trivia",
    "comedy",
    "bingo",
    "private event",
)

# "7:00 PM" / "10 PM" as Dice writes lineup times.
_LINEUP_TIME_RE = re.compile(r"^\d{1,2}(?::\d{2})?\s*[AP]M$", re.IGNORECASE)


def _is_non_music(title: str) -> bool:
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "x-api-key": API_KEY},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_events(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Page through the Dice API (date-ascending) until the window is covered.
    ``client`` is injectable so tests can drive pagination with a mock
    transport instead of the network."""
    window_end = today + dt.timedelta(days=window_days)
    own_client = client is None
    if client is None:
        client = _client()
    try:
        events: list[dict[str, object]] = []
        url: str | None = (
            f"{EVENTS_API}?page[size]={PER_PAGE}&types=linkout,event"
            f"&filter[venues][]={DICE_VENUE_NAME}"
        )
        for _ in range(MAX_PAGES):
            if url is None:
                break
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            page = payload.get("data", [])
            if not page:
                break
            events.extend(page)
            last_start = _start_local(page[-1])
            if last_start is not None and last_start.date() > window_end:
                break  # feed is sorted by date; everything further is beyond
            links = payload.get("links")
            url = links.get("next") if isinstance(links, dict) else None
        return events
    finally:
        if own_client:
            client.close()


def _get_str(event: dict[str, object], key: str) -> str | None:
    value = event.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _start_local(event: dict[str, object]) -> dt.datetime | None:
    """Dice's ``date`` is a UTC instant; convert to naive venue-local time
    (the tz is re-applied at ingest)."""
    raw = _get_str(event, "date")
    if raw is None:
        return None
    try:
        instant = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return instant.astimezone(VENUE_TZ).replace(tzinfo=None)


def _doors_local(event: dict[str, object], start_local: dt.datetime) -> dt.datetime | None:
    """Doors come from the ``lineup`` entry labelled "Doors open" (e.g.
    ``{"details": "Doors open", "time": "7:00 PM"}``), combined with the
    show's local date."""
    lineup = event.get("lineup")
    if not isinstance(lineup, list):
        return None
    for entry in lineup:
        if not isinstance(entry, dict):
            continue
        details = entry.get("details")
        time_raw = entry.get("time")
        if not (isinstance(details, str) and details.strip().lower() == "doors open"):
            continue
        if not (isinstance(time_raw, str) and _LINEUP_TIME_RE.match(time_raw.strip())):
            continue
        normalized = time_raw.strip().replace(" ", "").upper()  # "7:00PM"
        fmt = "%I:%M%p" if ":" in normalized else "%I%p"
        doors_time = dt.datetime.strptime(normalized, fmt).time()
        doors = dt.datetime.combine(start_local.date(), doors_time)
        if doors > start_local:  # doors before a past-midnight start
            doors -= dt.timedelta(days=1)
        return doors
    return None


def _format_cents(cents: int) -> str:
    dollars = f"{cents / 100:.2f}".removesuffix(".00")
    return f"${dollars}"


def _price_text(event: dict[str, object]) -> str | None:
    """Ticket prices live in ``ticket_types[].price.total`` (cents, fees
    included — what Dice's own widget displays). All-zero means a free show."""
    ticket_types = event.get("ticket_types")
    if not isinstance(ticket_types, list):
        return None
    totals: list[int] = []
    for ticket_type in ticket_types:
        if not isinstance(ticket_type, dict):
            continue
        price = ticket_type.get("price")
        if isinstance(price, dict) and isinstance(price.get("total"), int):
            totals.append(price["total"])
    if not totals:
        return None
    if max(totals) == 0:
        return "Free"
    low, high = min(totals), max(totals)
    if low == high:
        return _format_cents(low)
    return f"{_format_cents(low)}–{_format_cents(high)}"


def _split_tail(text: str) -> list[str]:
    """Split "X, Y and Z" into acts: commas separate, and only the final
    comma segment is split on " and " (Oxford-less list tail)."""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) > 1 and " and " in parts[-1]:
        tail = [piece.strip() for piece in parts[-1].split(" and ") if piece.strip()]
        parts = parts[:-1] + tail
    return parts


def _split_bill(name: str) -> tuple[str, list[str]]:
    """Split a Dice event name into (headliner, support).

    "A w/ B, C and D" → A + [B, C, D]; "A, B and C" → A + [B, C]. A name with
    no comma and no "w/" is a single billing — "and"/"&" inside it may be part
    of the band name, so it's left whole.
    """
    if " w/ " in name:
        headliner, _, rest = name.partition(" w/ ")
        return headliner.strip(), _split_tail(rest)
    parts = _split_tail(name)
    if len(parts) <= 1:
        return name.strip(), []
    return parts[0], parts[1:]


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Dice event dicts to ``ScrapedShow``s in ``[today, today +
    window_days]``. Pure / fixture-testable; ``today`` is injected so the
    window doesn't depend on the clock."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[str] = set()
    for event in events:
        event_id = _get_str(event, "id")
        if event_id is not None:
            if event_id in seen:
                continue
            seen.add(event_id)
        name = _get_str(event, "name")
        if name is None or _is_non_music(name):
            continue
        flags = event.get("flags")
        if isinstance(flags, list) and ("cancelled" in flags or "postponed" in flags):
            continue
        start_local = _start_local(event)
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue
        headliner, support = _split_bill(" ".join(name.split()))
        dice_url = _get_str(event, "url")
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=start_local,
                doors_local=_doors_local(event, start_local),
                ticket_url=dice_url,
                price_text=_price_text(event),
                source_url=dice_url or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live Dice feed for the next ~90 days."""
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
