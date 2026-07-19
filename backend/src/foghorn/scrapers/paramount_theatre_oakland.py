"""Paramount Theatre (Oakland) scraper.

Source: the venue's carbonhouse-platform site (same CMS family as The
Warfield, different skin). ``/events/`` server-renders the first batch of
upcoming events as ``div.eventItem`` blocks — a ``div.presented-by``
presenter line ("SF Jazz Presents"), the title in an ``h3.title`` link to
the venue's per-event detail page, a split date (``span.m-date__month`` /
``__day`` / ``__year``, year always present), an "Event Starts 7:30 PM"
``h5.time`` line, and usually a Ticketmaster ``a.tickets`` link. The rest
of the list loads through the platform's lazy-load feed,
``/events/events_ajax/<offset>`` (offset = events already seen; the page
renders 6, so 6, 8, …), which returns the same block markup as a
JSON-encoded HTML string — ``""`` once exhausted. No JS execution needed.

The movie palace books films, comedy, and Broadway runs alongside music;
clearly-non-music blocks (movie/film/screening, comedy/stand-up, podcast,
broadway/ballet keywords in the presenter or title) are dropped, and
ambiguous bookings are kept per house policy. No doors times, prices, or
genres appear on the listing, so those fields stay ``None``.

Runnable standalone: ``python -m foghorn.scrapers.paramount_theatre_oakland``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "paramount_theatre_oakland"

CALENDAR_URL = "https://www.paramountoakland.org/events/"
AJAX_URL_TEMPLATE = "https://www.paramountoakland.org/events/events_ajax/{offset}"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Safety cap on lazy-load fetches; the venue lists ~1 fragment beyond the
# first page today, and the feed returns "" at the end anyway.
_MAX_AJAX_PAGES = 12

_MONTHS = {
    abbr: index
    for index, abbr in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
# "7:00 PM" in the h5.time start span; tolerant of "7 PM" / "7:00PM".
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# Clearly-non-music presenter/title keywords. The room's film series bills as
# "Paramount Movie Classics" / "Paramount Movie Night" presenters; Broadway
# runs and ballet are dance/theater. Conservative — podcast-brand live shows
# with no keyword ride through (ambiguous → keep).
_DROP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmovies?\b", re.IGNORECASE),
    re.compile(r"\bfilms?\b", re.IGNORECASE),
    re.compile(r"\bcinema\b", re.IGNORECASE),
    re.compile(r"\bscreenings?\b", re.IGNORECASE),
    re.compile(r"\bcomedy\b", re.IGNORECASE),
    re.compile(r"\bcomedians?\b", re.IGNORECASE),
    re.compile(r"\bstand-?up\b", re.IGNORECASE),
    re.compile(r"\bpodcasts?\b", re.IGNORECASE),
    re.compile(r"\bbroadway\b", re.IGNORECASE),
    re.compile(r"\bballet\b", re.IGNORECASE),
)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_pages(client: httpx.Client | None = None) -> list[str]:
    """Fetch the events page plus every ``events_ajax`` continuation fragment,
    as raw HTML strings (each parseable by ``parse_html``). The feed's offset
    is the number of events already delivered (the page renders 6 today), so
    the running block count drives the next request; the feed returns a
    JSON-encoded HTML string per offset and ``""`` when exhausted. ``client``
    is injectable so tests can drive this with a mock transport."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        response = client.get(CALENDAR_URL)
        response.raise_for_status()
        pages = [response.text]
        offset = response.text.count('class="eventItem')
        for _ in range(_MAX_AJAX_PAGES):
            response = client.get(AJAX_URL_TEMPLATE.format(offset=offset))
            response.raise_for_status()
            fragment = response.json()  # a JSON string of block HTML
            if not isinstance(fragment, str) or not fragment.strip():
                break
            pages.append(fragment)
            delivered = fragment.count('class="eventItem')
            if delivered == 0:
                break
            offset += delivered
        return pages
    finally:
        if own_client:
            client.close()


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str`` (bs4 types attribute
    values as ``str | list[str] | None``)."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _select_text(block: Tag, selector: str) -> str:
    element = block.select_one(selector)
    return _clean(element.get_text(" ", strip=True)) if element is not None else ""


def _parse_date(block: Tag) -> dt.date | None:
    """The split single-date spans ("July / 24 / | 2026", month sometimes
    abbreviated with a period) → date. Multi-day runs render range spans
    instead of ``m-date__singleDate`` and are skipped (none are music
    bookings today)."""
    month_text = _select_text(block, "span.m-date__singleDate span.m-date__month")
    day_text = _select_text(block, "span.m-date__singleDate span.m-date__day")
    year_match = re.search(
        r"(\d{4})", _select_text(block, "span.m-date__singleDate span.m-date__year")
    )
    month = _MONTHS.get(month_text[:3].lower())
    day_match = re.search(r"(\d{1,2})", day_text)
    if month is None or day_match is None or year_match is None:
        return None
    try:
        return dt.date(int(year_match.group(1)), month, int(day_match.group(1)))
    except ValueError:
        return None


def _parse_time(text: str) -> dt.time | None:
    """Extract "7:00 PM" from the ``h5.time`` start span."""
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    if minute > 59:
        return None
    return dt.time(hour, minute)


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per ``div.eventItem`` block whose date falls
    in ``[today, today + window_days]``. Works on the full events page and on
    ``events_ajax`` fragments alike (both carry the same block markup).

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for block in soup.select("div.eventItem"):
        title_link = block.select_one("h3.title a")
        if title_link is None:
            continue
        headliner = _clean(title_link.get_text(" ", strip=True))
        if not headliner:
            continue

        presenter = _select_text(block, "div.presented-by")
        label = f"{presenter} {headliner}"
        if any(pattern.search(label) for pattern in _DROP_PATTERNS):
            continue

        show_date = _parse_date(block)
        if show_date is None or not (today <= show_date <= window_end):
            continue
        start_time = _parse_time(_select_text(block, "h5.time span.start"))
        if start_time is None:
            continue  # no stated time — never fabricate one

        detail_href = _attr(title_link, "href")
        ticket_link = block.select_one("a.tickets")
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],  # the listing never carries support billing
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=None,  # the listing shows no doors times
                ticket_url=ticket_href,
                price_text=None,  # the listing shows no prices
                source_url=detail_href or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live listing (all lazy-load fragments) for the
    next ~90 days. Deduplicates across page boundaries in case the list
    shifts mid-crawl."""
    today = dt.date.today()
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, dt.datetime]] = set()
    for page_html in fetch_pages():
        for show in parse_html(page_html, today):
            key = (show.headliner_raw, show.start_local)
            if key not in seen:
                seen.add(key)
                shows.append(show)
    shows.sort(key=lambda show: show.start_local)
    return shows


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
