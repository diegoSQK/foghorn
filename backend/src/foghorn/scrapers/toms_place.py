"""Tom's Place scraper.

Source: the Berkeley free-improv house series' hand-rolled static HTML at
``4-33.com/toms-place`` (plain HTTP — the host has no TLS). Entries are
``[ ddd mon D, YYYY ]`` date lines followed by billing lines. The page
also lists OFFSITE events the series presents elsewhere (SFPL, Gray Area,
The Lab — venues foghorn scrapes directly), recognizable by a street
address line; those are skipped, as are multi-day date ranges. The page
states "Unless otherwise noted, all events begin at 7:30 PM" — 19:30 is
the stated default, with an in-entry time overriding it.

Runnable standalone: ``python -m foghorn.scrapers.toms_place`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "toms_place"
PAGE_URL = "http://4-33.com/toms-place/index.html"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180  # sparse house series posts far ahead
REQUEST_TIMEOUT = 30.0
DEFAULT_START = dt.time(19, 30)  # page-stated default, not a fabrication

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec")
    )
}
_DATE_LINE_RE = re.compile(
    r"\[\s*(?:<[^>]+>\s*)*\w{3}\s+(\w{3})\s+(\d{1,2}),\s*(\d{4})", re.IGNORECASE
)
_RANGE_RE = re.compile(r"\d{1,2}\s*-\s*\w{3}\s+\w{3}\s+\d{1,2}", re.IGNORECASE)
_ADDRESS_RE = re.compile(
    r"\d{2,5}\s+[A-Z][\w.]*\s+(?:Street|St\b|Avenue|Ave\b|Blvd|Road|Rd\b|Way\b)"
)
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*pm\b", re.IGNORECASE)


def fetch_page(client: httpx.Client | None = None) -> str:
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(PAGE_URL)
        response.raise_for_status()
        return response.text
    finally:
        if own_client:
            client.close()


def parse_page(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Static page → ``ScrapedShow``s. Pure / fixture-testable."""
    # Case-sensitive anchors: the nav bar carries lowercase "[ upcoming
    # events ] … [ past events ]" on one line; the real section headings
    # are title-case.
    section = page_html
    upcoming = section.find("Upcoming Events")
    past = section.find("Past Events", max(upcoming, 0))
    section = section[max(upcoming, 0) : past if past > 0 else len(section)]
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    matches = list(_DATE_LINE_RE.finditer(section))
    for index, match in enumerate(matches):
        chunk = section[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(section)
        ]
        if _RANGE_RE.search(section[match.start() : match.end() + 24]):
            continue  # multi-day festival listing (offsite)
        lines = [
            cleaned
            for raw in re.split(r"<br\s*/?>", chunk)
            if (cleaned := " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split()))
            and cleaned != "]"
        ]
        if not lines or any(_ADDRESS_RE.search(line) for line in lines):
            continue  # offsite presentation at another venue
        month = _MONTHS.get(match.group(1).lower())
        if month is None:
            continue
        try:
            date = dt.date(int(match.group(3)), month, int(match.group(2)))
        except ValueError:
            continue
        if not (today <= date <= window_end):
            continue
        headliner = lines[0].lstrip("] ").strip()
        if not headliner:
            continue
        time_match = _TIME_RE.search(" ".join(lines))
        start = (
            dt.time(int(time_match.group(1)) % 12 + 12, int(time_match.group(2) or 0))
            if time_match
            else DEFAULT_START
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[line for line in lines[1:3] if len(line) < 80],
                start_local=dt.datetime.combine(date, start),
                doors_local=None,
                ticket_url=None,
                price_text=None,
                source_url=PAGE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live page."""
    return parse_page(fetch_page(), dt.date.today())


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
