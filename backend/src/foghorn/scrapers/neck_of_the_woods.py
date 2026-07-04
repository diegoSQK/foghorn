"""Neck of the Woods scraper.

Source: the venue's own WordPress site. Neck of the Woods (406 Clement St,
Inner Richmond) renders its upcoming-shows list server-side on the homepage
using the same TicketWeb "tw-" calendar template as The Independent and Cafe
du Nord — shared parsing lives in ``_ticketweb_calendar``. Plain ``httpx`` +
``beautifulsoup4`` suffice; no JS execution needed.

Deployment quirks:

- **Textual dates.** Rows show "Fri, Jul 3" (no year); the shared parser
  infers the year from ``today``.
- **Slash-separated bills.** There are no ``tw-attractions`` support lines;
  multi-act bills are crammed into the title ("Frolic/ Blind Illusion/
  Broken Glass Sanctuary/ Hemotoxin"). Titles are split on "/ " (slash +
  whitespace) into headliner + support; an unspaced slash inside a name
  ("W*B*PR*S*NC*/The Unevicted") stays joined, and "w/" never splits.
- **Row prices.** Each row prints a ``tw-price`` (often "$0.00" for free
  nights), which the shared parser captures verbatim.
- **Pagination + duplicate rows.** ~18 events per page with a "Next »" link
  (8 pages as of July 2026), and each page repeats its rows inside an
  email-signup popup (deduped by the shared parser). ``scrape`` stops
  walking once a page yields nothing inside the window.
- **Weekly non-music series.** Karaoke, open-mic, comedy, and trivia nights
  recur weekly and are dropped here (they'd drown out the concerts);
  anything merely ambiguous is kept.

Runnable standalone: ``python -m foghorn.scrapers.neck_of_the_woods`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketweb_calendar import find_next_page_url, parse_calendar_html

VENUE_SLUG = "neck_of_the_woods"

CALENDAR_URL = "https://www.neckofthewoodssf.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Safety valve for the pagination walk (8 pages live; the window walk stops
# earlier, once a page has nothing left inside it).
MAX_PAGES = 10

# This venue's recurring clearly-non-music series (weekly karaoke / open mic /
# stand-up / trivia). Kept per-venue: the shared list stays conservative.
_NON_MUSIC_RE = re.compile(r"\bkaraoke\b|\bopen mic\b|\bcomedy\b|\btrivia\b", re.IGNORECASE)

# Bill separator: slash followed by whitespace. "W*B*PR*S*NC*/The Unevicted"
# has no space after the slash and stays one act.
_BILL_SPLIT_RE = re.compile(r"\s*/\s+")


def _split_bill(title: str) -> tuple[str, list[str]]:
    """Split a slash-separated bill into (headliner, support). Returns the
    title unsplit when it isn't a bill — including "w/ Guest" phrasings, where
    the slash belongs to "with"."""
    parts = [part for part in (p.strip() for p in _BILL_SPLIT_RE.split(title)) if part]
    if len(parts) < 2 or any(p.lower() == "w" or p.lower().endswith(" w") for p in parts):
        return title, []
    return parts[0], parts[1:]


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch one homepage/list page. Kept separate from parsing so tests
    drive ``parse_html`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _postprocess(shows: list[ScrapedShow]) -> list[ScrapedShow]:
    """Apply the venue's quirks to shared-parser output: drop the weekly
    non-music series, then split slash-separated bills."""
    out: list[ScrapedShow] = []
    for show in shows:
        if _NON_MUSIC_RE.search(show.headliner_raw):
            continue
        headliner, support = _split_bill(show.headliner_raw)
        if support:
            show = show.model_copy(
                update={"headliner_raw": headliner, "support_raw": support}
            )
        out.append(show)
    return out


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per listed show on one page, dated within
    ``[today, today + window_days]``, sorted by ``start_local``."""
    return _postprocess(
        parse_calendar_html(
            html,
            venue_slug=VENUE_SLUG,
            today=today,
            window_days=window_days,
            fallback_source_url=CALENDAR_URL,
        )
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the paginated list for the next ~90 days, stopping
    once a page has no shows left inside the window."""
    today = dt.date.today()
    merged: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    url: str | None = CALENDAR_URL
    seen: set[str] = set()
    while url is not None and url not in seen and len(seen) < MAX_PAGES:
        seen.add(url)
        html = fetch_html(url)
        in_window = parse_calendar_html(
            html,
            venue_slug=VENUE_SLUG,
            today=today,
            window_days=SCRAPE_WINDOW_DAYS,
            fallback_source_url=CALENDAR_URL,
        )
        if not in_window:  # pages are chronological; we're past the window
            break
        for show in _postprocess(in_window):
            merged.setdefault((show.source_url, show.start_local), show)
        url = find_next_page_url(html)
    return sorted(merged.values(), key=lambda show: show.start_local)


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
