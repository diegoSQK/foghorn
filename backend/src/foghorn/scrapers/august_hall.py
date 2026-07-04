"""August Hall scraper.

Source: the venue's own WordPress site. August Hall (420 Mason St, Union
Square) renders its upcoming-shows list server-side at ``/events/`` using the
same TicketWeb "tw-" calendar template family as The Independent (the "list2"
view) — shared parsing lives in ``_ticketweb_calendar``. Ticketing is
Ticketmaster, but the markup (``tw-section``, ``tw-name``, ``tw-buy-tix-btn``)
is the same. Plain ``httpx`` + ``beautifulsoup4`` suffice; no JS execution
needed.

Deployment quirks:

- **Full dates, no times on the list.** Rows carry a full date with year
  ("Saturday, July 11, 2026") but no show time anywhere on the list pages;
  the time is server-rendered only on each per-event page (``tw-event-time``
  "6:00 pm"). ``scrape`` therefore fetches the list pages plus one small
  page per in-window event (~25 today) and joins via the shared parser's
  ``time_lookup`` hook — the same listing-then-event-pages shape as the
  California Jazz Conservatory scraper. Events whose page carries no
  parseable time are skipped rather than invented.
- **No doors, no prices, no support lines** anywhere server-rendered, so
  ``doors_local``/``price_text`` stay ``None`` and ``support_raw`` stays
  empty (guests are part of the title verbatim: "… (w/special guest …)").
- **Pagination.** 20 events per page with a "Next »" link (3 pages as of
  July 2026); the walk stops once a page has nothing left inside the window.

Runnable standalone: ``python -m foghorn.scrapers.august_hall`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable

import httpx

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketweb_calendar import (
    find_next_page_url,
    parse_calendar_html,
    parse_event_page_time,
)

VENUE_SLUG = "august_hall"

CALENDAR_URL = "https://www.augusthallsf.com/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
# Safety valve for the pagination walk; the list is 3 pages today.
MAX_PAGES = 10

# The venue annotates relocated shows in the title ("Low Cut Connie – Moved
# To August Hall", "Futurebirds – MOVED TO THE CHAPEL"). Moved *here*: strip
# the suffix so the row dedupes with the venue's plain duplicate listing via
# the natural key. Moved *away*: drop the row — the destination venue's
# scraper carries the show.
_MOVED_RE = re.compile(r"\s*[–—-]\s*moved\s+to\s+(?P<dest>.+?)\s*$", re.IGNORECASE)


def _resolve_moved(show: ScrapedShow) -> ScrapedShow | None:
    match = _MOVED_RE.search(show.headliner_raw)
    if match is None:
        return show
    if "august hall" in match.group("dest").lower():
        stripped = _MOVED_RE.sub("", show.headliner_raw).strip()
        return show.model_copy(update={"headliner_raw": stripped or show.headliner_raw})
    return None


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch one page (a list page or a per-event page). Kept separate from
    parsing so tests drive ``parse_html`` from fixtures without the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def parse_html(
    html: str,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    *,
    time_lookup: Callable[[str], dt.time | None] | None = None,
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per listed show on one list page, dated
    within ``[today, today + window_days]``, sorted by ``start_local``.

    List rows carry no time, so without a ``time_lookup`` (per-event URL →
    show time) every row is skipped; ``scrape`` wires in one that fetches the
    event page. Rows whose time is unknown are skipped, not invented."""
    parsed = parse_calendar_html(
        html,
        venue_slug=VENUE_SLUG,
        today=today,
        window_days=window_days,
        fallback_source_url=CALENDAR_URL,
        time_lookup=time_lookup,
    )
    return [show for raw in parsed if (show := _resolve_moved(raw)) is not None]


def _live_time_lookup() -> Callable[[str], dt.time | None]:
    """A ``time_lookup`` that fetches the per-event page, memoized so the
    duplicate listings the venue sometimes posts don't refetch."""
    cache: dict[str, dt.time | None] = {}

    def lookup(url: str) -> dt.time | None:
        if url not in cache:
            try:
                cache[url] = parse_event_page_time(fetch_html(url))
            except httpx.HTTPError:
                cache[url] = None  # skip the row rather than abort the run
        return cache[url]

    return lookup


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the paginated list (plus one per-event page per
    in-window show, for the time) for the next ~90 days, stopping the page
    walk once a page has no shows left inside the window."""
    today = dt.date.today()
    lookup = _live_time_lookup()
    merged: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    url: str | None = CALENDAR_URL
    seen: set[str] = set()
    while url is not None and url not in seen and len(seen) < MAX_PAGES:
        seen.add(url)
        html = fetch_html(url)
        page_shows = parse_html(html, today, time_lookup=lookup)
        if not page_shows:  # pages are chronological; we're past the window
            break
        for show in page_shows:
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
