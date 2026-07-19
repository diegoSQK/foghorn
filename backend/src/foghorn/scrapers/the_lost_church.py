"""The Lost Church (San Francisco) scraper.

Source: the nonprofit listening room's PatronTicket (PatronManager)
box office at ``thelostchurch.my.salesforce-sites.com``. The WordPress
calendar page shows title + date only — times live in the ticket app, a
Visualforce-remoting SPA. The scraper does what the SPA does: GET the
app shell, lift the per-session ``fetchEvents`` CSRF descriptor out of
the remoting manifest, and POST one ``apexremote`` call — the JSON reply
carries every upcoming event with venue-local dates, clock times, tiered
prices, and the venue's own category tags.

One org, two rooms: the feed mixes San Francisco and Santa Rosa, split
by category tag — only "San Francisco" events are kept. Music filtering
also rides the venue's tags (conservative: keep "Music", drop
Comedy/Rental/Theater Production); instance names carry a genre blurb
("Indie/Folk/Singer-Songwriter | Friday … | Doors 7:30pm") and the doors
time, both parsed out.

Runnable standalone: ``python -m foghorn.scrapers.the_lost_church``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_lost_church"

# The human-facing listing (seed calendar_url); data comes from the ticket app.
CALENDAR_URL = "https://thelostchurch.org/san-francisco/"
TICKET_APP_URL = "https://thelostchurch.my.salesforce-sites.com/ticket"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The remoting manifest entry for fetchEvents: version + per-session tokens.
_DESCRIPTOR_RE = re.compile(
    r'\{"name":"fetchEvents","len":\d+,"ns":"PatronTicket","ver":([\d.]+),'
    r'"csrf":"([^"]+)","authorization":"([^"]+)"\}'
)
_VID_RE = re.compile(r'"vid":"([^"]+)"')

# Category tags are the venue's own taxonomy, semicolon-joined.
_CITY_TAG = "San Francisco"
_MUSIC_TAGS = frozenset({"Music", "Traditional Music"})
_NON_MUSIC_TAGS = frozenset({"Comedy", "Rental", "Theater Production"})

_WEEKDAY_LOOKAHEAD = r"(?=(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b)"
# Instance names read "<genre blurb> | Friday, July 24th, 2026 | Doors 7:30pm"
# (some use " - " separators). The leading blurb is the venue's per-event
# genre string; ingest normalizes it (junk → None).
_INSTANCE_GENRE_RE = re.compile(r"^(.*?)\s*[|–—-]\s*" + _WEEKDAY_LOOKAHEAD, re.IGNORECASE)
_DOORS_RE = re.compile(r"Doors\s+(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*([AP])M$", re.IGNORECASE)
# Event names carry the room as a suffix, sometimes with a matinée note or a
# "LIVE at The Lost Church" flourish before it.
_LOCATION_SUFFIX_RE = re.compile(r"\s*[–—-]\s*(?:San Francisco|SF)\s*!?\s*$")
_MATINEE_SUFFIX_RE = re.compile(r"\s*\(?Matin[ée]e\)?\s*$", re.IGNORECASE)
_VENUE_TAIL_RE = re.compile(r"\s*(?:LIVE\s+)?at\s+The\s+Lost\s+Church\s*$", re.IGNORECASE)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_events(client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """GET the ticket-app shell, then replay its ``fetchEvents`` remoting
    call. Returns the raw event dicts (the remoting ``result``)."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        shell = client.get(TICKET_APP_URL)
        shell.raise_for_status()
        descriptor = _DESCRIPTOR_RE.search(shell.text)
        vid = _VID_RE.search(shell.text)
        if descriptor is None or vid is None:
            raise RuntimeError("fetchEvents remoting descriptor not found in ticket app shell")
        response = client.post(
            f"{TICKET_APP_URL}/apexremote",
            json={
                "action": "PatronTicket.Controller_PublicTicketApp",
                "method": "fetchEvents",
                # (siteURL, accessCode, passcode, eventView)
                "data": [TICKET_APP_URL, "", "", None],
                "type": "rpc",
                "tid": 1,
                "ctx": {
                    "csrf": descriptor.group(2),
                    "vid": vid.group(1),
                    "ns": "PatronTicket",
                    "ver": int(float(descriptor.group(1))),
                    "authorization": descriptor.group(3),
                },
            },
            headers={"Referer": TICKET_APP_URL},
        )
        response.raise_for_status()
        return unwrap_remoting(response.json())
    finally:
        if own_client:
            client.close()


def unwrap_remoting(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ``fetchEvents`` result out of a remoting response envelope."""
    for entry in payload:
        if entry.get("method") == "fetchEvents" and entry.get("statusCode") == 200:
            result: list[dict[str, Any]] = entry["result"]
            return result
    raise RuntimeError(f"fetchEvents remoting call failed: {json.dumps(payload)[:300]}")


def _is_sf_music(event: dict[str, Any]) -> bool:
    tags = {tag.strip() for tag in (event.get("category") or "").split(";")}
    return (
        _CITY_TAG in tags
        and bool(tags & _MUSIC_TAGS)
        and not (tags & _NON_MUSIC_TAGS)
    )


def _clean_title(name: str) -> str:
    for pattern in (_LOCATION_SUFFIX_RE, _MATINEE_SUFFIX_RE, _VENUE_TAIL_RE):
        name = pattern.sub("", name).strip()
    return name


def _price_text(instance: dict[str, Any]) -> str | None:
    """The tiered price levels collapsed to "$15" / "$15–$100"."""
    prices = [
        level["price"]
        for allocation in instance.get("allocations") or []
        for level in allocation.get("levels") or []
        if isinstance(level.get("price"), int | float)
    ]
    if not prices:
        return None
    low, high = min(prices), max(prices)
    if low == high:
        return f"${low:g}"
    return f"${low:g}–${high:g}"


def parse_events(
    events: list[dict[str, Any]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Remoting event dicts → one ``ScrapedShow`` per San Francisco music
    instance in ``[today, today + window_days]``. ``today`` is injected so
    the window is deterministic and fixture-testable. Pure."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        if not _is_sf_music(event):
            continue
        title = _clean_title(event.get("name") or "")
        if not title:
            continue
        for instance in event.get("instances") or []:
            if instance.get("nonTimed"):
                continue
            dates = instance.get("formattedDates") or {}
            time_match = _TIME_RE.match(dates.get("TIME_STRING") or "")
            date_digits = dates.get("YYYYMMDD") or ""
            if time_match is None or not re.fullmatch(r"\d{8}", date_digits):
                continue  # never fabricate a time
            hour = int(time_match.group(1)) % 12
            if time_match.group(3).lower() == "p":
                hour += 12
            try:
                start = dt.datetime(
                    int(date_digits[:4]), int(date_digits[4:6]), int(date_digits[6:8]),
                    hour, int(time_match.group(2)),
                )
            except ValueError:
                continue
            if not (today <= start.date() <= window_end):
                continue
            instance_name = instance.get("name") or ""
            doors = None
            doors_match = _DOORS_RE.search(instance_name)
            if doors_match is not None:
                doors_hour = int(doors_match.group(1)) % 12
                if doors_match.group(3).lower() == "p":
                    doors_hour += 12
                doors = start.replace(hour=doors_hour, minute=int(doors_match.group(2) or 0))
            genre_match = _INSTANCE_GENRE_RE.match(instance_name)
            genre = genre_match.group(1).strip() if genre_match else None
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=title,
                    support_raw=[],
                    start_local=start,
                    doors_local=doors,
                    ticket_url=instance.get("purchaseUrl") or event.get("purchaseUrl"),
                    price_text=_price_text(instance),
                    source_url=event.get("purchaseUrl") or CALENDAR_URL,
                    genre=genre or None,
                )
            )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live box-office feed for the next ~90 days."""
    return parse_events(fetch_events(), dt.date.today())


def main() -> None:
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in scrape()],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
