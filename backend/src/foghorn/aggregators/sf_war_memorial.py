"""San Francisco War Memorial licensee calendar (aggregator source).

The War Memorial is the City department that **rents** Davies Symphony Hall,
Herbst Theatre and the War Memorial Opera House, and its calendar is the
building operator's own booking record:

    The War Memorial is the department of the City and County of San
    Francisco responsible for managing the rental and maintenance of the
    Performing Arts Center facilities. Production and promotion of all
    events and performances is the responsibility of Licensees.

That authority is the point. Before this source, those halls were modelled as
venues but sourced entirely from *presenters* — the SF Symphony group feed —
so a hall was only ever as complete as one resident company's season and every
rental was invisible. A Julian Lage Quartet date SFJAZZ presented at Davies on
2026-10-19 fell straight through: SFJAZZ's own scraper drops off-site dates by
design, and the Symphony feed cannot see a rental.

**An aggregator, not a venue scraper — deliberately.** #128 worried at length
about the nightly ``prune=True`` reaping the Symphony aggregator's Davies rows
if this registered as a venue scraper, and proposed either declaring this
source authoritative or scoping prune per contributing source. Neither is
needed: the aggregator tier already ingests per event with no pruning, and it
resolves each event's hall from a free-text venue name, which is exactly the
multi-venue shape this feed has. The hazard simply doesn't arise here.

**Symphony-presented dates are dropped**, because the Symphony's own feed is
authoritative for them and carries better billings — it says "Elim Chan
conducts Adams and Mendelssohn" where the booking record says "DOCTOR ATOMIC
AND MENDELSSOHN VIOLIN CONCERTO". Measured against live data before this
shipped: of 171 Symphony dates here, 86 canonicalize identically to the
existing rows (harmless), but **19 differ and would have landed as visible
duplicate rows**. ``aggregators.ingest._is_duplicate`` can't catch them — it
deliberately skips rows whose source is ``aggregator`` so that two aggregators
never suppress each other. Dropping them at the source is the honest fix, and
it matches the ticket's own acceptance, which asks for *non-Symphony*
licensee events. Other presenters with their own foghorn feed belong in
``COVERED_PRESENTERS`` alongside it.

Source shape: ``/calendar/`` is WordPress + Elementor, but the events are not
a WP custom post type (``wp/v2/types`` lists none, ``tribe/events/v1`` 404s,
and there is no JetEngine CCT). They are server-rendered into the page as a
``var eventsData = [...]`` JSON array by the building's booking system —
Momentus/Ungerboeck field names (``arrangement_customer_entity_full_name``,
``activity_detail``) show through. So a plain HTTP GET is enough; no headless
browser, which is what #128's Phase 1 was asked to establish.

Runnable standalone: ``python -m foghorn.aggregators.sf_war_memorial`` prints
the events as JSON and exits. No DB writes here — that's the ingest layer.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
import re
from typing import Any

import httpx

from foghorn.aggregators.models import AggregatedEvent

logger = logging.getLogger(__name__)

SOURCE_ID = "sf_war_memorial"
CALENDAR_URL = "https://sfwarmemorial.org/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
REQUEST_TIMEOUT = 30.0

# The booking system's hall labels → the venue name foghorn seeds. Resolution
# in aggregators.ingest matches on the venue's *name*, and "Davies Hall Stage"
# does not token-match "Davies Symphony Hall" in either direction, so these
# need naming explicitly rather than left to the fuzzy matcher.
VENUE_NAMES: dict[str, str] = {
    "Davies Hall Stage": "Davies Symphony Hall",
    "Herbst Theatre": "Herbst Theatre",
    "Opera House Stage": "War Memorial Opera House",
    "Wilsey Center": "Atrium Theater at the Wilsey Center",
}

# Halls whose bookings are not public performances. The Green Room and the
# Zellerbach Rehearsal Hall carry receptions, rehearsals and staff meetings;
# letting them through would auto-create quarantined venues full of noise.
SKIPPED_VENUES = frozenset(
    {"Veterans Building Green Room", "Zellerbach Rehearsal Hall"}
)

# Presenters foghorn already ingests from their own feed. Their dates are
# dropped here so the two sources can't both land a row — see the module
# docstring for the measurement behind this.
COVERED_PRESENTERS = frozenset({"San Francisco Symphony"})

# The calendar's own genre facet, which is reliable enough to filter on for
# everything except Film (below). "Dance" is San Francisco Ballet's season —
# real programming, but dance rather than music, and foghorn is a music
# calendar. "Special Event" is religious services and youth poetry finals;
# the empty string is mostly Nutcracker runs and staff meetings.
MUSIC_GENRES = frozenset({"Music", "Opera"})

# Film is the one ambiguous facet: it covers both plain screenings (a film
# festival's opening night) and live-orchestra performances, which are music
# events and exactly the kind of rental #128 wants surfaced. Admitted only on
# an explicit live-performance signal in the billing.
FILM_GENRE = "Film"
_LIVE_PERFORMANCE_RE = re.compile(
    r"\bin\s+concert\b|\bwith\s+(?:the\s+)?(?:live\s+)?(?:symphony|orchestra)\b"
    r"|\blive\s+orchestra\b",
    re.IGNORECASE,
)

# `var eventsData=[...]` — the booking system's payload, rendered into the page.
_EVENTS_DATA_RE = re.compile(r"var\s+eventsData\s*=\s*(\[.*?\]);", re.DOTALL)


def fetch_calendar(url: str = CALENDAR_URL) -> str:
    """Fetch the calendar page. Separate from parsing so tests drive
    ``parse_events`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def extract_events_data(page_html: str) -> list[dict[str, Any]]:
    """Pull the ``eventsData`` array out of the page. Returns ``[]`` (with a
    warning) when the array is absent or unparseable — a layout change should
    make this source report zero, not crash the nightly run."""
    match = _EVENTS_DATA_RE.search(page_html)
    if match is None:
        logger.warning(
            "sf_war_memorial: no eventsData array in %s — page layout changed?",
            CALENDAR_URL,
        )
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("sf_war_memorial: eventsData is not valid JSON")
        return []
    return [row for row in payload if isinstance(row, dict)]


def _text(value: object) -> str:
    return html.unescape(str(value)).strip() if value else ""


def is_music(record: dict[str, Any]) -> bool:
    """Whether this booking is a music performance foghorn should list."""
    genre = _text(record.get("genre"))
    if genre in MUSIC_GENRES:
        return True
    if genre == FILM_GENRE:
        return bool(_LIVE_PERFORMANCE_RE.search(_text(record.get("activity_detail"))))
    return False


def _start_local(record: dict[str, Any]) -> dt.datetime | None:
    """``date_time`` is already naive venue-local ("2026-10-19 20:00:00")."""
    raw = _text(record.get("date_time"))
    try:
        return dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_events(records: list[dict[str, Any]]) -> list[AggregatedEvent]:
    """Booking records → the music performances at the three public halls.

    Pure and fixture-testable. Drops, in order: halls that aren't public
    rooms, non-music bookings, presenters foghorn covers elsewhere, and rows
    missing a billing or a parseable start.
    """
    events: list[AggregatedEvent] = []
    for record in records:
        hall = _text(record.get("venue_name"))
        if hall in SKIPPED_VENUES:
            continue
        venue_name = VENUE_NAMES.get(hall)
        if venue_name is None:
            # An unrecognised hall is worth a human glance rather than a
            # silent drop — the building occasionally labels a new room.
            logger.warning("sf_war_memorial: unmapped hall %r", hall)
            continue
        if not is_music(record):
            continue
        presenter = _text(record.get("arrangement_customer_entity_full_name"))
        if presenter in COVERED_PRESENTERS:
            continue
        headliner = _text(record.get("activity_detail"))
        start_local = _start_local(record)
        if not headliner or start_local is None:
            continue
        events.append(
            AggregatedEvent(
                venue_name_raw=venue_name,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
                ticket_url=_text(record.get("calendar_url")) or None,
                price_text=None,
                source_url=CALENDAR_URL,
            )
        )
    events.sort(key=lambda event: (event.start_local, event.headliner_raw))
    return events


def scrape() -> list[AggregatedEvent]:
    """Fetch and parse the live licensee calendar."""
    return parse_events(extract_events_data(fetch_calendar()))


def main() -> None:
    print(
        json.dumps(
            [event.model_dump(mode="json") for event in scrape()],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
