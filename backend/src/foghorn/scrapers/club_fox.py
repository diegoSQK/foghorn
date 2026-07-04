"""Club Fox scraper.

Source: the venue's own WordPress site. Club Fox (2209 Broadway, Redwood City)
hand-writes its upcoming shows on the homepage as centered ``<h3>`` heading
blocks — one per show — with ``<br>``-separated lines: a date line ("Thursday
July 9th", no year), the bill (usually wrapped in an eventbrite.com/e/ ticket
link), and a "Doors 7PM / Show 8PM" line. There is no calendar plugin and no
per-event page on the venue's site; the Eventbrite link is the only ticketing.

Plain ``httpx`` + ``beautifulsoup4`` suffice — everything is server-rendered on
one page. Quirks handled here: year-less dates (rolled forward from ``today``),
series labels ("MUSIC ON THE SQUARE", the venue's free outdoor summer series,
and "GRATEFUL THURSDAYS") that precede the actual act, en-dash descriptors
glued to act names ("AJA VU – Steely Dan/Chicago Tribute"), and support acts
introduced by "w/" or a bare "Featuring" line.

Runnable standalone: ``python -m foghorn.scrapers.club_fox`` prints the scraped
shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "club_fox"

CALENDAR_URL = "https://clubfoxrwc.com/"
# No per-event pages exist on the venue site; every show's provenance is the
# homepage listing (Eventbrite links go in ticket_url, not source_url).
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_MONTHS: dict[str, int] = {
    **{calendar.month_name[i].lower(): i for i in range(1, 13)},
    **{calendar.month_abbr[i].lower(): i for i in range(1, 13)},
    "sept": 9,
}

# A whole line that is just a date: "Thursday July 9th", "Saturday August 1st".
# Anchored so the closure notice's "July 3rd – July 6th" range doesn't match.
_DATE_LINE_RE = re.compile(
    r"^(?:[A-Za-z]+day\s+)?([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?$",
    re.IGNORECASE,
)
_DOORS_RE = re.compile(r"doors\s*:?\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)", re.IGNORECASE)
_SHOW_RE = re.compile(r"show\s*:?\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)", re.IGNORECASE)

# Recurring series banners that precede the actual act on the bill.
_SERIES_LABELS = frozenset({"music on the square", "grateful thursdays"})
# "AJA VU – Steely Dan/Chicago Tribute" → "AJA VU". En dash only — a hyphen
# may be part of a band name; the site uses an en dash for descriptors.
_DASH_DESCRIPTOR_RE = re.compile(r"\s*–.*$")
# Support intro: "w/ZED & RANCHERO", "with X", "Featuring". After stripping the
# intro and any "special guest(s)" filler, an empty remainder means the support
# act is on the next line.
_SUPPORT_INTRO_RE = re.compile(r"^(?:w/|with\b|feat(?:uring)?\b\.?)\s*", re.IGNORECASE)
_INLINE_W_RE = re.compile(r"\s+w/\s*")
_GUEST_FILLER_RE = re.compile(r"^special\s+guests?\s*", re.IGNORECASE)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the homepage show list. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return " ".join(text.split())


def _lines(tag: Tag) -> list[str]:
    """A tag's text as clean lines, one per ``<br>``-separated fragment."""
    for br in tag.find_all("br"):
        br.replace_with("\n")
    return [line for line in (_clean(part) for part in tag.get_text().split("\n")) if line]


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str`` (bs4 types attributes
    as ``str | list[str] | None``)."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _resolve_date(line: str, today: dt.date) -> dt.date | None:
    """Turn a year-less "Thursday July 9th" line into a real date, assuming
    ``today``'s year and rolling forward one when the result would be in the
    past — the page only lists upcoming shows."""
    match = _DATE_LINE_RE.match(line)
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    day = int(match.group(2))
    try:
        candidate = dt.date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
        try:
            candidate = dt.date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def _parse_time(text: str) -> dt.time | None:
    """"7PM" / "6:30PM" → a time."""
    match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*([ap])", text, re.IGNORECASE)
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return dt.time(hour, minute)


def _parse_bill(act_lines: list[str]) -> tuple[str | None, list[str]]:
    """Resolve (headliner, support) from the bill's lines. Series labels are
    skipped; "w/…"/"Featuring" lines feed support; other extra lines are
    taglines ("A Beatles Tribute as Nature Intended") and are ignored."""
    headliner: str | None = None
    support: list[str] = []
    expect_support = False
    for line in act_lines:
        if expect_support:
            support.append(_DASH_DESCRIPTOR_RE.sub("", line) or line)
            expect_support = False
            continue
        intro = _SUPPORT_INTRO_RE.match(line)
        if intro is not None:
            remainder = _GUEST_FILLER_RE.sub("", line[intro.end() :]).strip()
            if remainder:
                support.append(remainder)
            else:
                expect_support = True
            continue
        if headliner is None:
            if line.lower() in _SERIES_LABELS:
                continue
            inline = _INLINE_W_RE.split(line, maxsplit=1)
            if len(inline) == 2:
                headliner = _DASH_DESCRIPTOR_RE.sub("", inline[0]).strip() or inline[0]
                remainder = _GUEST_FILLER_RE.sub("", inline[1]).strip()
                if remainder:
                    support.append(remainder)
                else:
                    expect_support = True
            else:
                headliner = _DASH_DESCRIPTOR_RE.sub("", line).strip() or line
        # else: tagline/blurb line after the headliner — ignored.
    return headliner, support


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per homepage ``<h3>`` show block whose date
    falls in ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable — and because the year inference for the
    page's year-less dates hinges on it.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for heading in soup.select(".entry-content h3"):
        ticket_link = heading.select_one('a[href*="eventbrite.com/e/"]')
        ticket_url = _attr(ticket_link, "href") if ticket_link is not None else None
        # _lines mutates the tree (<br> → newline), so read the link's lines
        # before flattening the whole heading.
        link_lines = _lines(ticket_link) if ticket_link is not None else []
        lines = _lines(heading)

        start_date: dt.date | None = None
        doors_time: dt.time | None = None
        show_time: dt.time | None = None
        others: list[str] = []
        for line in lines:
            if start_date is None:
                resolved = _resolve_date(line, today)
                if resolved is not None:
                    start_date = resolved
                    continue
            doors_match = _DOORS_RE.search(line)
            show_match = _SHOW_RE.search(line)
            if doors_match or show_match:
                if doors_match:
                    doors_time = _parse_time(doors_match.group(1))
                if show_match:
                    show_time = _parse_time(show_match.group(1))
                continue
            others.append(line)
        if start_date is None:
            continue  # venue notice ("over 21", holiday closure), not a show
        start_time = show_time or doors_time
        if start_time is None:
            continue

        headliner, support = _parse_bill(link_lines if link_lines else others)
        if headliner is None:
            continue
        if not (today <= start_date <= window_end):
            continue

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=dt.datetime.combine(start_date, start_time),
                doors_local=(
                    dt.datetime.combine(start_date, doors_time)
                    if doors_time is not None
                    else None
                ),
                ticket_url=ticket_url,
                price_text=None,
                source_url=SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live homepage listing for the next ~90 days."""
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
