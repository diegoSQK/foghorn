"""Old First Concerts scraper.

Source: the presenter's WordPress + WooCommerce site at
``oldfirstconcerts.org`` (Old First Presbyterian Church, 1751 Sacramento
St, SF — classical/chamber with some jazz and folk). Each concert is a
WooCommerce *product*, and the homepage's month submenus link every
upcoming one as ``/performance/<slug>/`` with the full billing in the
anchor text — "Mike Greensill & Friends – Celebrating his 80th birthday!
– Sunday, September 6 at 4 pm". The date is year-less, so it's rolled
forward from ``today`` (the page only lists upcoming concerts) and the
stated weekday is used as a stale-entry guard: a date whose weekday
matches in neither this year nor the next is skipped. Main-content image
cards repeat the same URLs with no text and dedup away.

Runnable standalone: ``python -m foghorn.scrapers.old_first_concerts``
prints the scraped shows as JSON and exits. No DB writes here — that's
the ingest pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import html as html_lib
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "old_first_concerts"

CALENDAR_URL = "https://www.oldfirstconcerts.org/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_PERFORMANCE_LINK_RE = re.compile(
    r'<a href="(https://www\.oldfirstconcerts\.org/performance/[^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
_MONTHS = {calendar.month_name[i].lower(): i for i in range(1, 13)}
# Trailing "… – Sunday, September 6 at 4 pm" (year-less; the site's em-dash
# separates it from the billing, but a comma-only form is tolerated).
_DATE_TAIL_RE = re.compile(
    r"[\s,–—-]*\b([A-Za-z]+day),?\s+([A-Za-z]+)\s+(\d{1,2})"
    r"\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*$",
    re.IGNORECASE,
)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the homepage. Kept separate from parsing so tests drive
    ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _strip_tags(fragment: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _resolve_date(weekday: str, month_name: str, day: int, today: dt.date) -> dt.date | None:
    """A year-less "Sunday, September 6" → a real date: assume ``today``'s
    year, roll forward one when past, and require the stated weekday to
    match (stale menu entries fail the check and drop)."""
    month = _MONTHS.get(month_name.lower())
    weekday_index = _WEEKDAYS.get(weekday.lower())
    if month is None or weekday_index is None:
        return None
    for year in (today.year, today.year + 1):
        try:
            candidate = dt.date(year, month, day)
        except ValueError:
            continue
        if candidate >= today and candidate.weekday() == weekday_index:
            return candidate
    return None


def parse_html(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Homepage → one ``ScrapedShow`` per ``/performance/`` product link
    whose date falls in ``[today, today + window_days]``. ``today`` is
    injected (not read from the clock) so the parser is deterministic and
    fixture-testable — the year inference hinges on it. Pure."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[str] = set()
    for url, anchor in _PERFORMANCE_LINK_RE.findall(page_html):
        if url in seen:
            continue
        text = _strip_tags(anchor)
        tail = _DATE_TAIL_RE.search(text)
        if tail is None:
            continue  # image-only card or undated link — the text link carries the date
        seen.add(url)
        date = _resolve_date(tail.group(1), tail.group(2), int(tail.group(3)), today)
        if date is None or not (today <= date <= window_end):
            continue
        hour = int(tail.group(4)) % 12
        if tail.group(6).lower() == "p":
            hour += 12
        title = text[: tail.start()].strip(" ,–—-")
        if not title:
            continue
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=dt.datetime.combine(date, dt.time(hour, int(tail.group(5) or 0))),
                doors_local=None,
                # The WooCommerce product page is where tickets are sold.
                ticket_url=url,
                price_text=None,
                source_url=url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live homepage listing for the next ~90 days."""
    return parse_html(fetch_html(), dt.date.today())


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
