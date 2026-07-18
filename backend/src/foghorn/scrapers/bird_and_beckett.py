"""Bird & Beckett Books and Records scraper.

Source: the venue's public Google Calendar, exposed as an iCalendar feed. Bird &
Beckett (a Glen Park bookshop with a dense live-jazz calendar) publishes its
schedule to a public Google Calendar embedded on its ``/events`` page; the
calendar's ``.ics`` export is a far cleaner and more stable source than the
WordPress event posts, whose dates live in free-text titles.

**Re-pilot note.** Phase 2.1 originally targeted SFJAZZ, but SFJAZZ sits behind
a Cloudflare managed challenge that 403s every simple HTTP client (polite UA and
browser UA alike). Bird & Beckett was chosen as the end-to-end pilot instead —
see ``docs/SHIPPED.md``.

Runnable standalone: ``python -m foghorn.scrapers.bird_and_beckett`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from foghorn.models import ScrapedShow

VENUE_SLUG = "bird_and_beckett"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

# Public Google Calendar behind https://birdbeckett.com/events/ ("view our full
# calendar"). The calendar id was read from the embed `src` on that page.
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "r5o3loovr013c5rftpv75lji18%40group.calendar.google.com/public/basic.ics"
)
# Human-viewable provenance for each show (the .ics itself isn't browseable).
SOURCE_URL = "https://birdbeckett.com/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Bird & Beckett's calendar mixes its jazz programming with literary events
# (poetry readings, author talks, small-press launches). Per the ticket we err
# toward inclusion and only drop events whose title carries a strong non-music
# signal. This is a heuristic, knowingly imperfect — revisit if it misfires.
_NON_MUSIC_SIGNALS = (
    "poet",
    "poetry",
    "reading",
    "novelist",
    "author",
    "book release",
    "book launch",
    "lecture",
    "talks",
)


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


def parse_ics(
    ics_text: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per timed musical event in
    ``[today, today + window_days]``, with recurring series expanded.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
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
        # tz to derive start_utc. Expanded instances come back tz-aware (PT or
        # UTC) — convert before dropping tzinfo so UTC-stored events land right.
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
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=summary,
                support_raw=[],
                start_local=local,
                end_local=end_local,
                doors_local=None,
                ticket_url=None,
                price_text=None,
                source_url=SOURCE_URL,
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
