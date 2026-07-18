"""Indexical scraper.

Source: the experimental-music nonprofit's custom Rails site at
``indexical.org`` (Tannery Arts Center, Santa Cruz — foghorn's second
Santa Cruz venue). ``/events`` is fully server-rendered; upcoming events
link as ``/events/YYYY-MM-DD-slug``, so the **date lives in the URL** and
only pages for future dates are fetched (the CJC
listing-plus-detail-pages pattern, with a date prefilter). Detail pages
carry clean text: "Doors at 6:30pm | Show at 7pm" and a "$16" price.

Series filtering: recurring "monthly meetup" entries are gatherings, not
performances, and drop on slug signal before fetching; open mics are kept
(ingest's title inference types them as jams).

Runnable standalone: ``python -m foghorn.scrapers.indexical`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "indexical"

BASE_URL = "https://indexical.org"
EVENTS_URL = f"{BASE_URL}/events"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_EVENT_LINK_RE = re.compile(r'href="(/events/(\d{4})-(\d{2})-(\d{2})-[a-z0-9-]+)"')
# Gatherings, not performances; skipped before fetching.
_NON_MUSIC_SLUG_SIGNALS = ("meetup", "member-meeting", "fundraiser", "open-studios")

_TITLE_RE = re.compile(r"<title>([^<]+)</title>")
_SHOW_TIME_RE = re.compile(
    r"(?:Show|Event) at (\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE
)
_DOORS_TIME_RE = re.compile(r"Doors at (\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\d+(?:\.\d{2})?(?:\s*[-–/]\s*\$?\d+(?:\.\d{2})?)?")


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def parse_event_links(
    listing_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[tuple[str, dt.date]]:
    """(url, date) pairs for future performance events, deduped, dated from
    the slug — no detail fetch needed to know the day."""
    window_end = today + dt.timedelta(days=window_days)
    out: list[tuple[str, dt.date]] = []
    seen: set[str] = set()
    for path, year, month, day in _EVENT_LINK_RE.findall(listing_html):
        if path in seen:
            continue
        seen.add(path)
        if any(signal in path for signal in _NON_MUSIC_SLUG_SIGNALS):
            continue
        try:
            date = dt.date(int(year), int(month), int(day))
        except ValueError:
            continue
        if today <= date <= window_end:
            out.append((f"{BASE_URL}{path}", date))
    return out


def _time_from(match: re.Match[str] | None) -> dt.time | None:
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "p":
        hour += 12
    return dt.time(hour, int(match.group(2) or 0))


def parse_event_page(page_html: str, url: str, date: dt.date) -> ScrapedShow | None:
    """One detail page → a ``ScrapedShow``; None when no show time is
    stated (never fabricate). Pure / fixture-testable."""
    text = html_lib.unescape(page_html)
    start = _time_from(_SHOW_TIME_RE.search(text))
    doors = _time_from(_DOORS_TIME_RE.search(text))
    if start is None:
        start, doors = doors, None  # "Doors at 7pm" only — treat as start
    if start is None:
        return None
    title_match = _TITLE_RE.search(text)
    if title_match is None:
        return None
    title = " ".join(title_match.group(1).split())
    # The <title> carries the site name on one side ("Indexical | <event>").
    title = re.sub(r"^\s*Indexical\s*[|—–-]\s*", "", title)
    title = re.sub(r"\s*[|—–-]\s*Indexical\s*$", "", title).strip()
    if not title:
        return None
    price_match = _PRICE_RE.search(text)
    price = price_match.group(0) if price_match else None
    if price is None and re.search(r"FREE to Attend", text, re.IGNORECASE):
        price = "Free"
    return ScrapedShow(
        venue_slug=VENUE_SLUG,
        headliner_raw=title,
        support_raw=[],
        start_local=dt.datetime.combine(date, start),
        doors_local=dt.datetime.combine(date, doors) if doors else None,
        ticket_url=None,
        price_text=price,
        source_url=url,
    )


def scrape() -> list[ScrapedShow]:
    """Walk the live listing and future event pages."""
    today = dt.date.today()
    shows: list[ScrapedShow] = []
    with _client() as client:
        listing = client.get(EVENTS_URL)
        listing.raise_for_status()
        for url, date in parse_event_links(listing.text, today):
            page = client.get(url)
            if page.status_code != httpx.codes.OK:
                continue
            show = parse_event_page(page.text, url, date)
            if show is not None:
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
