"""DNA Lounge scraper.

Source: the venue's own public iCalendar feed at
``https://cdn.dnalounge.com/calendar/dnalounge.ics`` (linked from
dnalounge.com/calendar). DNA Lounge (375 Eleventh St, SoMa) self-publishes a
clean, hand-maintained feed: one ``VEVENT`` per night/room with a
``TZID=US/Pacific`` start, an event-page ``URL``, and a ``DESCRIPTION`` that
ends with door-price lines (``$10 limited advance; ...``) and — for events with
online sales open — a ``Buy tickets: <event page>`` line.

The calendar is club-heavy: DJ, dance, goth (Death Guild), and burlesque
(Hubba Hubba) nights are all real programming and are kept. Only titles with a
strong non-music signal (movie screenings, meetups, trivia, private events)
are dropped. Summaries are usually a single event-brand name; live multi-act
bills are delimited with `` + `` (e.g. ``16 Volt + Acumen Nation``) and are
split into headliner + support.

Runnable standalone: ``python -m foghorn.scrapers.dna_lounge`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from foghorn.models import ScrapedShow

VENUE_SLUG = "dna_lounge"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

ICS_URL = "https://cdn.dnalounge.com/calendar/dnalounge.ics"
# Fallback provenance when a VEVENT somehow lacks its event-page URL.
CALENDAR_URL = "https://www.dnalounge.com/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# DNA Lounge is nearly all music/dance programming, so this list stays short
# and only catches titles that clearly aren't a show: film nights, tech
# meetups, trivia, and private rentals. Drag/burlesque/DJ nights are kept per
# the ticket. Heuristic, knowingly imperfect — revisit if it misfires.
_NON_MUSIC_SIGNALS = (
    "trivia",
    "movie",
    "screening",
    "meetup",
    "lecture",
    "private event",
    "watch party",
)

# Live bills pack multiple acts into SUMMARY with " + " (colons introduce
# subtitles, not co-bills, so they are left alone).
_ACT_DELIMITER = " + "


def fetch_ics(url: str = ICS_URL) -> str:
    """Fetch the raw iCalendar feed. Kept separate from parsing so tests drive
    ``parse_ics`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _is_non_music(summary: str) -> bool:
    lowered = summary.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _clean(text: str) -> str:
    """Collapse the whitespace artifacts iCal text tends to carry, without
    otherwise altering the venue's string (which becomes the display name)."""
    return " ".join(text.split())


def _split_acts(summary: str) -> tuple[str, list[str]]:
    """Split a `` + ``-delimited co-bill into (headliner, support). Single-act
    summaries pass through verbatim."""
    acts = [act.strip() for act in summary.split(_ACT_DELIMITER) if act.strip()]
    if len(acts) < 2:
        return summary, []
    return acts[0], acts[1:]


def _price_text(description: str) -> str | None:
    """Pull the door-price lines DNA appends to every description (``$10
    limited advance;`` / ``$15 door.`` ...) into one display string."""
    prices = [
        line.strip() for line in description.splitlines() if line.strip().startswith("$")
    ]
    if not prices:
        return None
    return _clean(" ".join(prices))


def parse_ics(
    ics_text: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per timed musical event in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable. The feed has no RRULEs today, but
    expansion via ``recurring_ical_events`` keeps us safe if DNA adds any.
    """
    calendar = icalendar.Calendar.from_ical(ics_text)
    window_end = today + dt.timedelta(days=window_days)
    instances = recurring_ical_events.of(calendar).between(today, window_end)

    shows: list[ScrapedShow] = []
    for event in instances:
        start = event.get("DTSTART")
        if start is None:
            continue
        start_value = start.dt
        # Skip all-day (date-only) entries — not single timed performances.
        if not isinstance(start_value, dt.datetime):
            continue
        summary = _clean(str(event.get("SUMMARY", "")))
        if not summary or _is_non_music(summary):
            continue
        # Normalize to naive local time in the venue tz; ingest re-applies the
        # tz to derive start_utc. The feed stamps TZID=US/Pacific, but convert
        # defensively in case entries ever come back UTC.
        if start_value.tzinfo is not None:
            local = start_value.astimezone(VENUE_TZ).replace(tzinfo=None)
        else:
            local = start_value
        end = event.get("DTEND")
        end_local = None
        if end is not None and isinstance(end.dt, dt.datetime):
            end_value = end.dt
            end_local = (
                end_value.astimezone(VENUE_TZ).replace(tzinfo=None)
                if end_value.tzinfo is not None
                else end_value
            )
        headliner, support = _split_acts(summary)
        url = str(event.get("URL", "")) or CALENDAR_URL
        description = str(event.get("DESCRIPTION", ""))
        # The event page doubles as the ticket page, but only when the
        # description advertises sales ("Buy tickets: <url>"); free/door-only
        # nights omit that line.
        ticket_url = url if "Buy tickets:" in description else None
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=local,
                end_local=end_local,
                doors_local=None,
                ticket_url=ticket_url,
                price_text=_price_text(description),
                source_url=url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live feed for the next ~90 days."""
    return parse_ics(fetch_ics(), dt.date.today())


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
