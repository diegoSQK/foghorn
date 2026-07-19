"""San Francisco Philharmonic scraper.

Source: sfphil.org is a small Squarespace site whose entire season (3–4
concerts) is server-rendered into the homepage navigation as
``Buy Tickets - <Month D, YYYY>`` links pointing at City Box Office event
pages (``cityboxoffice.com/eventperformances.asp?evt=N``). The nav link text
carries the concert *date*; the CBO page's ``<title>`` carries the program
name; and CBO's ``GetTimeSlots.asp`` widget endpoint (a server-rendered HTML
fragment) carries the start *time*. All three surfaces are plain HTTP — no
JS execution needed even though both sites render their widgets client-side.

The Philharmonic is an itinerant presenter (Herbst Theatre, the Wilsey
Center Atrium, …), so like Cal Performances it gets one presenter venue row
rather than per-hall rows. Program titles arrive as
"San Francisco Philharmonic - <program>" / "… presents <program>"; the
presenter prefix is stripped since the venue row already says who's playing.
A concert whose time slot can't be found is skipped — a dated but timeless
row can't satisfy the show contract (re-runs pick it up once CBO lists the
performance time).

Runnable standalone: ``python -m foghorn.scrapers.sf_philharmonic`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "sf_philharmonic"

HOME_URL = "https://sfphil.org"
TIMESLOTS_URL = "https://www.cityboxoffice.com/include/widgets/events/GetTimeSlots.asp"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
REQUEST_TIMEOUT = 30.0

# The whole listed season is scraped regardless of horizon — a 3-concert
# org's furthest date (often next spring) is exactly what a follower wants.

_BUY_LINK_RE = re.compile(
    r'<a[^>]+href="(https?://(?:www\.)?cityboxoffice\.com/eventperformances\.asp'
    r'\?evt=(\d+))"[^>]*>(?:(?!</a>).)*?Buy\s+Tickets\s*(?:-|–|—)\s*'
    r"([A-Z][a-z]+ \d{1,2}, \d{4})",
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


def scrape() -> list[ScrapedShow]:
    """Walk the live homepage nav and each concert's CBO surfaces."""
    shows: list[ScrapedShow] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        home = client.get(HOME_URL)
        home.raise_for_status()
        for date, evt_id, ticket_url in parse_buy_links(home.text):
            event_page = client.get(ticket_url)
            if event_page.status_code != httpx.codes.OK:
                continue
            title = parse_program_title(event_page.text)
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
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=title,
                    support_raw=[],
                    start_local=dt.datetime.combine(date, time),
                    doors_local=None,
                    ticket_url=ticket_url,
                    price_text=None,
                    source_url=HOME_URL,
                )
            )
    shows.sort(key=lambda show: show.start_local)
    return shows


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
