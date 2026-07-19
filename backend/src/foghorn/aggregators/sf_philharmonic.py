"""San Francisco Philharmonic group feed (aggregator source).

The Philharmonic is a performing *group* with no hall of its own — it plays
Herbst Theatre, the Wilsey Center Atrium, wherever the season takes it. It
therefore ingests as an **aggregator source**: each concert names the hall
it actually happens in, venue resolution routes it to a seeded row (or a
quarantined auto-created one), and the ensemble rides every bill as a
support performer so the performer watchlist follows the group across halls.

Source: sfphil.org is a small Squarespace site whose entire season (3–4
concerts) is server-rendered into the homepage navigation as
``Buy Tickets - <Month D, YYYY>`` links pointing at City Box Office event
pages (``cityboxoffice.com/eventperformances.asp?evt=N``). Per concert:

- **date** — the nav link text;
- **program title** — the CBO page ``<title>`` (presenter prefix stripped);
- **start time** — CBO's server-rendered ``GetTimeSlots.asp`` fragment;
- **hall** — CBO event pages cross-reference the presenter's *other* events
  in a server-rendered "related events" block that includes each sibling's
  venue line. Fetching every event page and unioning those blocks yields
  each concert's hall from its siblings (with ≥2 concerts listed, coverage
  is complete). A concert whose hall never appears lands in a quarantined
  "San Francisco Philharmonic Offsite" bucket rather than being dropped.

All surfaces are plain HTTP — no JS execution needed even though both sites
render their widgets client-side. A concert whose time slot can't be found
is skipped — a dated but timeless row can't satisfy the show contract
(re-runs pick it up once CBO lists the performance time).

Runnable standalone: ``python -m foghorn.aggregators.sf_philharmonic``
prints the events as JSON and exits. No DB writes here — that's the ingest
layer.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.aggregators.models import AggregatedEvent

SOURCE_ID = "sf_philharmonic"
GROUP_NAME = "San Francisco Philharmonic"

HOME_URL = "https://sfphil.org"
TIMESLOTS_URL = "https://www.cityboxoffice.com/include/widgets/events/GetTimeSlots.asp"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
REQUEST_TIMEOUT = 30.0

# Quarantined bucket for concerts whose hall the related-events blocks never
# named (single-event seasons, or CBO layout drift).
OFFSITE_VENUE = "San Francisco Philharmonic Offsite"

# The whole listed season is scraped regardless of horizon — a 3-concert
# org's furthest date (often next spring) is exactly what a follower wants.

_BUY_LINK_RE = re.compile(
    r'<a[^>]+href="(https?://(?:www\.)?cityboxoffice\.com/eventperformances\.asp'
    r'\?evt=(\d+))"[^>]*>(?:(?!</a>).)*?Buy\s+Tickets\s*(?:-|–|—)\s*'
    r"([A-Z][a-z]+ \d{1,2}, \d{4})",
    re.DOTALL,
)
# One sibling entry in a CBO "related events" block:
# <h3>title</h3><div>Weekday, Month D, YYYY</div><div>VENUE</div>
# <div><a href="eventperformances.asp?evt=ID">Learn More ...</a></div>
_RELATED_VENUE_RE = re.compile(
    r"<h3>(?:(?!</h3>).)*</h3>\s*<div>[^<]*\d{4}[^<]*</div>\s*<div>([^<]+)</div>"
    r'\s*<div>\s*<a href="eventperformances\.asp\?evt=(\d+)"',
    re.DOTALL,
)
# First offered time slot on the GetTimeSlots fragment ("7:30PM").
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.IGNORECASE)
# CBO <title>: "Tickets | <event name> | City Box Office".
_CBO_TITLE_RE = re.compile(r"<title>\s*Tickets\s*\|(.*?)\|", re.DOTALL)
_PRESENTER_PREFIX_RE = re.compile(
    r"^San Francisco Philharmonic\s*(?:-|–|—|:|presents)\s*", re.IGNORECASE
)


def parse_buy_links(home_html: str) -> list[tuple[dt.date, str, str]]:
    """Homepage nav → ``(concert_date, evt_id, ticket_url)`` per concert,
    deduped in page order (Squarespace repeats the nav for mobile)."""
    concerts: list[tuple[dt.date, str, str]] = []
    seen: set[str] = set()
    for url, evt_id, date_text in _BUY_LINK_RE.findall(home_html):
        if evt_id in seen:
            continue
        seen.add(evt_id)
        try:
            date = dt.datetime.strptime(date_text, "%B %d, %Y").date()
        except ValueError:
            continue
        concerts.append((date, evt_id, url))
    return concerts


def parse_related_venues(event_html: str) -> dict[str, str]:
    """One CBO event page → ``{evt_id: venue}`` for every sibling concert its
    related-events block names."""
    return {
        evt_id: html.unescape(venue).strip()
        for venue, evt_id in _RELATED_VENUE_RE.findall(event_html)
        if venue.strip()
    }


def parse_program_title(event_html: str) -> str | None:
    """CBO event page → program name, with the presenter prefix stripped
    ("San Francisco Philharmonic - A Season of Titans" → "A Season of
    Titans"). Billing forms like "… & Anne Richardson" keep the full string —
    there the orchestra is part of the bill, not a prefix."""
    match = _CBO_TITLE_RE.search(event_html)
    if match is None:
        return None
    title = html.unescape(match.group(1)).strip()
    stripped = _PRESENTER_PREFIX_RE.sub("", title).strip()
    return stripped or title or None


def parse_first_time(timeslots_html: str) -> dt.time | None:
    """GetTimeSlots fragment → the performance start time, or None when CBO
    hasn't listed slots yet."""
    match = _TIME_RE.search(timeslots_html)
    if match is None:
        return None
    hour, minute, meridiem = (
        int(match.group(1)),
        int(match.group(2)),
        match.group(3).upper(),
    )
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return None
    hour = hour % 12 + (12 if meridiem == "PM" else 0)
    return dt.time(hour, minute)


def scrape() -> list[AggregatedEvent]:
    """Walk the live homepage nav and each concert's CBO surfaces."""
    events: list[AggregatedEvent] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        home = client.get(HOME_URL)
        home.raise_for_status()
        concerts = parse_buy_links(home.text)
        # First pass: fetch each event page once; collect titles and the
        # union of sibling venue references.
        titles: dict[str, str] = {}
        venues: dict[str, str] = {}
        for _date, evt_id, ticket_url in concerts:
            page = client.get(ticket_url)
            if page.status_code != httpx.codes.OK:
                continue
            title = parse_program_title(page.text)
            if title is not None:
                titles[evt_id] = title
            venues.update(parse_related_venues(page.text))
        for date, evt_id, ticket_url in concerts:
            title = titles.get(evt_id)
            if title is None:
                continue
            slots = client.get(
                TIMESLOTS_URL,
                params={
                    "eventid": evt_id,
                    "searchdate": f"{date.month}/{date.day}/{date.year}",
                },
            )
            time = (
                parse_first_time(slots.text)
                if slots.status_code == httpx.codes.OK
                else None
            )
            if time is None:
                continue
            events.append(
                AggregatedEvent(
                    venue_name_raw=venues.get(evt_id, OFFSITE_VENUE),
                    headliner_raw=title,
                    support_raw=[GROUP_NAME],
                    start_local=dt.datetime.combine(date, time),
                    ticket_url=ticket_url,
                    source_url=HOME_URL,
                )
            )
    events.sort(key=lambda event: event.start_local)
    return events


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
