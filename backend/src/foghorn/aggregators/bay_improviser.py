"""Bay Improviser aggregator (bayimproviser.com).

The community calendar for the Bay Area creative/improvised-music scene —
the one aggregator the May 2026 spike found both ingestible (robots-
permissive, structured data) and on-target. Each calendar entry embeds a
Google-Calendar "add" link whose query string carries the event title, a
UTC start/end, and a free-text location — a self-contained structured
surface riding on otherwise plain HTML.

Community-submitted caveats the ingest layer handles (not this module):
titles are free-text blobs (not clean headliners) and locations are venue
names foghorn has to resolve. The site publishes only ~5 weeks out, so the
scheduler polls it nightly like everything else.

One caveat *is* handled here: when a submission carries no billing at all,
the site builds the gCal ``text`` param from the event *description* instead
(truncated to ~350 chars; the full description rides in ``details``). A
truncated-description title is unusable anywhere, so those entries are
dropped; a short description doubling as the title (``text == details`` and
prose-shaped) is kept but flagged ``headliner_is_description`` so the ingest
layer can drop it at venues whose own scraper is authoritative.

Runnable standalone: ``python -m foghorn.aggregators.bay_improviser``.
"""

from __future__ import annotations

import datetime as dt
import json
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from foghorn.aggregators.models import AggregatedEvent

SOURCE_ID = "bay_improviser"
BASE_URL = "https://www.bayimproviser.com"
CALENDAR_URL = f"{BASE_URL}/calendar.aspx"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
# The site publishes ~5 weeks ahead; ask for a bit more so nothing clips.
WINDOW_DAYS = 45
REQUEST_TIMEOUT = 30.0
_PACIFIC = ZoneInfo("America/Los_Angeles")


def fetch_html(today: dt.date | None = None) -> str:
    """Fetch the calendar for ``[today, today + WINDOW_DAYS]``."""
    start = today or dt.datetime.now(_PACIFIC).date()
    end = start + dt.timedelta(days=WINDOW_DAYS)
    response = httpx.get(
        CALENDAR_URL,
        params={"s": start.strftime("%m/%d/%Y"), "e": end.strftime("%m/%d/%Y")},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _parse_gcal_start(raw: str) -> dt.datetime | None:
    """``20260530T023000Z/…`` → naive Pacific-local start. Date-only (all-day)
    entries return None — a listing without a start time isn't a show row we
    can place on the calendar."""
    start_part = raw.split("/", 1)[0]
    if not start_part.endswith("Z"):
        return None
    try:
        instant = dt.datetime.strptime(start_part, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=dt.UTC
        )
    except ValueError:
        return None
    return instant.astimezone(_PACIFIC).replace(tzinfo=None)


# The site's no-billing fallback truncates the description to 350 chars for
# the gCal title; anything at/near that length that prefixes ``details`` is
# that fallback, not a real title. Real titles stay well under this.
_TRUNCATED_DESCRIPTION_MIN_LEN = 300


def _looks_like_prose(title: str) -> bool:
    """Sentence-shaped rather than billing-shaped. Only consulted when the
    title verbatim-matches the description (billings like "AVOTCJA & MODUPUE"
    legitimately double as both and must survive this test)."""
    return len(title) >= 140 or title.endswith((".", "!", "?"))


def _classify_title(title: str, details: str) -> tuple[bool, bool]:
    """(skip, is_description) for a gCal title given the ``details`` param.

    - ``details`` strictly extends a ~350-char title → the site's truncation
      fallback; no real title exists anywhere, so skip the entry.
    - ``title == details`` and prose-shaped → the description doubling as the
      title; keep (it may be the only record of the show) but flag it.
    """
    if not details or not details.startswith(title):
        return False, False
    if len(details) > len(title):
        return len(title) >= _TRUNCATED_DESCRIPTION_MIN_LEN, False
    return False, _looks_like_prose(title)


def _split_location(raw: str) -> tuple[str, str | None]:
    """``"Venue Name, 123 St, City, CA"`` → (name, address-remainder)."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return raw.strip(), None
    name = parts[0]
    rest = ", ".join(parts[1:]) or None
    return name, rest


def parse_events(html: str) -> list[AggregatedEvent]:
    """One event per embedded gCal link with a usable title, location, and
    timed start. Pure / fixture-testable."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[AggregatedEvent] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "google.com/calendar" not in href and "calendar.google.com" not in href:
            continue
        qs = parse_qs(urlparse(href).query)
        title = (qs.get("text") or [""])[0].strip()
        location_raw = (qs.get("location") or [""])[0].strip()
        start = _parse_gcal_start((qs.get("dates") or [""])[0])
        if not title or not location_raw or start is None:
            continue
        skip, is_description = _classify_title(
            title, (qs.get("details") or [""])[0].strip()
        )
        if skip:
            continue
        venue_name, address = _split_location(location_raw)
        if not venue_name:
            continue
        key = (title, start.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            AggregatedEvent(
                venue_name_raw=venue_name,
                venue_address_raw=address,
                headliner_raw=title,
                headliner_is_description=is_description,
                start_local=start,
                source_url=CALENDAR_URL,
            )
        )
    events.sort(key=lambda e: e.start_local)
    return events


def scrape() -> list[AggregatedEvent]:
    return parse_events(fetch_html())


def main() -> None:
    events = scrape()
    print(
        json.dumps(
            [event.model_dump(mode="json") for event in events],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
