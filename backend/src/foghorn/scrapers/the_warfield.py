"""The Warfield scraper.

Source: the venue's carbonhouse-platform site (an AEG/Goldenvoice room)
server-renders its first 20 upcoming shows into ``/events`` as static
``div.entry.warfield`` blocks — presenter and tour-name ``h5`` lines, the
headliner in an ``h3`` link to the venue's per-event detail page, an optional
``h4`` support line ("with julie" / "with Yung Miami, Bally Baby"), a
``span.date`` with the full date *including the year* ("Tue, Aug 11, 2026"),
a ``span.time`` show time, and an ``axs.com`` purchase link. The rest of the
list loads through the platform's documented lazy-load feed,
``/events/events_ajax/<offset>`` (offset 20, 40, …), which returns the same
block markup as a JSON-encoded HTML string — an empty string once the list is
exhausted. No JS execution is needed for any of it.

No doors times, prices, or genres appear anywhere on the listing, so those
fields stay ``None``. Clearly-non-music blocks (comedy/podcast/screening
keywords in the title lines) are dropped; ambiguous bookings (drag shows,
"An Evening With …") are kept per house policy.

Runnable standalone: ``python -m foghorn.scrapers.the_warfield`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "the_warfield"

CALENDAR_URL = "https://www.thewarfieldtheatre.com/events"
AJAX_URL_TEMPLATE = "https://www.thewarfieldtheatre.com/events/events_ajax/{offset}"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
_PAGE_SIZE = 20
# Safety cap on lazy-load fetches; the venue lists ~2 pages beyond the first
# today, and the feed returns "" at the end anyway.
_MAX_AJAX_PAGES = 8

# "Tue, Aug 11, 2026" — weekday ignored; the listing includes the year.
_DATE_RE = re.compile(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})")
_MONTHS = {
    abbr: index
    for index, abbr in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
# "Show 8:00 PM" in the time span; tolerant of "8 PM" / "8:00PM".
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# Support lead-ins: "with special guest Melvins" / "with julie" → the acts.
_SUPPORT_LEAD_IN_RE = re.compile(
    r"^\s*(?:with|featuring|feat\.?)\s+(?:very\s+)?(?:special\s+guests?\s+)?",
    re.IGNORECASE,
)
# Clearly-non-music toplines/titles. Conservative — the room also books drag
# shows and spoken-word bills that stay in (ambiguous → keep).
_DROP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcomedy\b", re.IGNORECASE),
    re.compile(r"\bcomedians?\b", re.IGNORECASE),
    re.compile(r"\bstand-?up\b", re.IGNORECASE),
    re.compile(r"\bpodcasts?\b", re.IGNORECASE),
    re.compile(r"\bscreenings?\b", re.IGNORECASE),
    re.compile(r"\bfilm series\b", re.IGNORECASE),
)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_pages(client: httpx.Client | None = None) -> list[str]:
    """Fetch the events page plus every ``events_ajax`` continuation fragment,
    as raw HTML strings (each parseable by ``parse_html``). The feed returns a
    JSON-encoded HTML string per offset and ``""`` when exhausted. ``client``
    is injectable so tests can drive this with a mock transport."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        response = client.get(CALENDAR_URL)
        response.raise_for_status()
        pages = [response.text]
        for page in range(_MAX_AJAX_PAGES):
            offset = _PAGE_SIZE * (page + 1)
            response = client.get(AJAX_URL_TEMPLATE.format(offset=offset))
            response.raise_for_status()
            fragment = response.json()  # a JSON string of block HTML
            if not isinstance(fragment, str) or not fragment.strip():
                break
            pages.append(fragment)
        return pages
    finally:
        if own_client:
            client.close()


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str``. bs4 types attributes
    as ``str | list[str] | None`` (multi-valued attrs like ``class``); ``href``
    is always single, but we coerce defensively to stay type-safe."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _select_text(block: Tag, selector: str) -> str:
    element = block.select_one(selector)
    return _clean(element.get_text(" ", strip=True)) if element is not None else ""


def _parse_date(text: str) -> dt.date | None:
    """"Tue, Aug 11, 2026" → date. The listing states the year explicitly, so
    no forward-rolling inference is needed."""
    match = _DATE_RE.search(text)
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    try:
        return dt.date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None


def _parse_time(text: str) -> dt.time | None:
    """Extract "8:00 PM" from the time span ("Show 8:00 PM")."""
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


def _support_acts(text: str) -> list[str]:
    """Split the "with …" support line into acts (comma-separated), stripping
    the lead-in and any "special guest" label."""
    stripped = _SUPPORT_LEAD_IN_RE.sub("", text)
    return [part for part in (_clean(piece) for piece in stripped.split(",")) if part]


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per ``div.entry.warfield`` block whose date
    falls in ``[today, today + window_days]``. Works on the full events page
    and on ``events_ajax`` fragments alike (both carry the same block markup).

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for block in soup.select("div.entry.warfield"):
        title_link = block.select_one("div.title h3 a")
        if title_link is None:
            continue
        headliner = _clean(title_link.get_text(" ", strip=True))
        if not headliner:
            continue

        # h5 lines carry the presenter and tour name; only used for the
        # non-music keyword check (never as billing).
        h5_text = " ".join(
            _clean(h5.get_text(" ", strip=True)) for h5 in block.select("div.title h5")
        )
        label = f"{h5_text} {headliner}"
        if any(pattern.search(label) for pattern in _DROP_PATTERNS):
            continue

        show_date = _parse_date(_select_text(block, "span.date"))
        if show_date is None or not (today <= show_date <= window_end):
            continue
        start_time = _parse_time(_select_text(block, "span.time"))
        if start_time is None:
            continue  # no usable time — not seen on real blocks

        support_text = _select_text(block, "div.title h4")
        support = _support_acts(support_text) if support_text else []

        detail_href = _attr(title_link, "href")
        ticket_link = block.select_one("a.btn-tickets")
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
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
    """Fetch and parse the live listing (all lazy-load pages) for the next
    ~90 days. Deduplicates across page boundaries in case the list shifts
    mid-crawl."""
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
