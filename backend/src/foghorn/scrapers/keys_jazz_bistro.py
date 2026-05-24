"""Keys Jazz Bistro scraper.

Source: the venue's own WordPress site. Keys Jazz Bistro (a North Beach club at
530 Broadway) publishes a forward-looking ``/upcoming-shows/`` page rendered by
the "simple-events" WordPress plugin as a Query Loop of ``se-event`` posts. That
page is a far cleaner target than ``/event-calendar/``: it starts at today (no
past-event filtering), needs no month pagination, and lists every upcoming show
as a structured ``<li>`` with the title, a ``<p>`` date line, and a WooCommerce
"Get Tickets" link.

Plain ``httpx`` + ``beautifulsoup4`` suffices — the show list is in the
server-rendered HTML, no JS execution or ``playwright`` needed (unlike SFJAZZ,
which sits behind a Cloudflare challenge — see ``docs/SHIPPED.md``).

Runnable standalone: ``python -m foghorn.scrapers.keys_jazz_bistro`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "keys_jazz_bistro"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

CALENDAR_URL = "https://keysjazzbistro.com/upcoming-shows/"
# Fallback provenance when a row's per-event link is missing; normally each
# show's source_url is its own /event/ page.
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Saturday, May 23, 2026 @ 7pm" / "... @ 10:30pm". The weekday is present on
# every line; we don't trust it (it isn't validated against the date) — it just
# anchors the match so a stray date in a description paragraph won't match.
_DATE_RE = re.compile(
    r"[A-Za-z]+day,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*@\s*"
    r"(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)",
    re.IGNORECASE,
)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the upcoming-shows page. Kept separate from parsing so tests drive
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


def _parse_start(date_text: str, time_text: str) -> dt.datetime:
    """Combine "May 23, 2026" + "10:30pm" into a naive local datetime. The
    venue tz is applied at ingest, not here."""
    date_part = dt.datetime.strptime(date_text, "%B %d, %Y").date()
    normalized = time_text.replace(" ", "").replace(".", "").upper()  # "10:30PM"
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    time_part = dt.datetime.strptime(normalized, fmt).time()
    return dt.datetime.combine(date_part, time_part)


def _find_date(li: Tag) -> tuple[str, str] | None:
    """Return the (date, time) groups from the first ``<p>`` matching the date
    pattern, or ``None`` if the item carries no parseable date line."""
    for paragraph in li.find_all("p"):
        match = _DATE_RE.search(paragraph.get_text(" ", strip=True))
        if match:
            return match.group(1), match.group(2)
    return None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per upcoming-shows ``<li>`` whose date falls in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for li in soup.select("ul.wp-block-post-template > li"):
        title_link = li.select_one("h2.wp-block-post-title a")
        if title_link is None:
            continue
        headliner = _clean(title_link.get_text(" ", strip=True))
        if not headliner:
            continue
        found = _find_date(li)
        if found is None:
            continue
        start_local = _parse_start(*found)
        if not (today <= start_local.date() <= window_end):
            continue

        event_href = _attr(title_link, "href")
        ticket_link = li.select_one('a[href*="add-to-cart"]')
        ticket_href = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=ticket_href,
                price_text=None,
                source_url=event_href or SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live upcoming-shows page for the next ~90 days."""
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
