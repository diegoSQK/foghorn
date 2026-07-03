"""924 Gilman scraper.

Source: the collective's ShowSlinger ticketing page. 924 Gilman's own Wix site
(924gilman.org) renders both its CALENDAR and TICKETS pages entirely
client-side (the served HTML carries no event data, and the site's Wix Events
app is disabled), but the site's nav links to its ShowSlinger listing at
``https://app.showslinger.com/e1/460/924-gilman/8c96699fd6`` — and that page
*is* server-rendered: one structured card per upcoming show with title, date,
time, price, and a per-event ``/v/<slug>`` ticket page. Plain ``httpx`` +
``beautifulsoup4`` suffices.

Card quirks handled here: each show appears twice (a list layout and a grid
layout — only the list card carries time/price, so only ``.list-layout-1``
cards are parsed), the visible date lacks a year (recovered from the card's
numeric ``<day><month><year>`` filter class), and bills are packed into the
title as "A + B + C" or "A, B, C" (split into headliner + support, dropping
"More!"/"TBD" placeholders). Gilman is volunteer-run; the rare non-show
entries (collective/membership meetings) are dropped by title.

Runnable standalone: ``python -m foghorn.scrapers.gilman_924`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "gilman_924"

CALENDAR_URL = "https://app.showslinger.com/e1/460/924-gilman/8c96699fd6"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Jul 3" (the visible card date; whitespace can be doubled in the source).
_DATE_RE = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2})$")
# "7:00 PM" / "10:30 PM".
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.IGNORECASE)
# Support-slot placeholders that aren't real acts ("... + More!").
_PLACEHOLDER_RE = re.compile(r"^(tbd|tba|more)\W*$", re.IGNORECASE)
# Collective business, not shows.
_NON_SHOW_SIGNALS = ("membership meeting", "collective meeting", "volunteer orientation")


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the ShowSlinger listing page. Kept separate from parsing so tests
    drive ``parse_html`` from a fixture without touching the network."""
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


def _classes(tag: Tag) -> list[str]:
    value = tag.get("class")
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.split()
    return []


def _is_non_show(title: str) -> bool:
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_SHOW_SIGNALS)


def _split_bill(title: str) -> tuple[str, list[str]]:
    """Split a packed bill into headliner + support. Gilman titles use
    "A + B + C" or "A, B, C, D" (two-plus commas — a single comma is left
    alone, it may be part of one act's name). Segments are kept verbatim;
    "More!"/"TBD" placeholder slots are dropped."""
    if " + " in title:
        parts = [part.strip() for part in title.split(" + ")]
    elif title.count(", ") >= 2:
        parts = [part.strip() for part in title.split(", ")]
    else:
        parts = [title]
    parts = [part for part in parts if part]
    if not parts:
        return title.strip(), []
    support = [part for part in parts[1:] if not _PLACEHOLDER_RE.match(part)]
    return parts[0], support


def _resolve_date(month_day: str, date_token: str | None, today: dt.date) -> dt.date | None:
    """Resolve "Jul 3" to a full date. The card's filter class encodes
    ``<day><month><year>`` unpadded (Jul 3 2026 → "372026"); when it confirms
    the visible month/day we take its year, otherwise we roll the month/day
    forward from ``today`` (listings never show past events)."""
    match = _DATE_RE.match(month_day)
    if match is None:
        return None
    month = dt.datetime.strptime(match.group(1), "%b").month
    day = int(match.group(2))
    if date_token is not None:
        prefix = f"{day}{month}"
        if date_token.startswith(prefix) and len(date_token) == len(prefix) + 4:
            return dt.date(int(date_token[len(prefix) :]), month, day)
    candidate = dt.date(today.year, month, day)
    if candidate < today:
        candidate = dt.date(today.year + 1, month, day)
    return candidate


def _parse_time(text: str) -> dt.time | None:
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3).upper()
    hour %= 12
    if meridiem == "PM":
        hour += 12
    return dt.time(hour, minute)


def _event_url(card: Tag) -> str | None:
    """Absolute per-event page ("/v/<slug>?from=..." → clean URL)."""
    link = card.select_one("a.mrk_ticket_event_url")
    if link is None:
        return None
    href = _attr(link, "href")
    if not href:
        return None
    absolute = urljoin(CALENDAR_URL, href)
    scheme, netloc, path, _query, _fragment = urlsplit(absolute)
    return urlunsplit((scheme, netloc, path, "", ""))


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per list-layout card whose date falls in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for card in soup.select("div.mrk_filter_event_by_venue.list-layout-1"):
        title_tag = card.select_one("h4.widget-name")
        date_tag = card.select_one("div.widget-date-month")
        time_tag = card.select_one("span.widget-time")
        if title_tag is None or date_tag is None or time_tag is None:
            continue
        title = _clean(title_tag.get_text(" ", strip=True))
        if not title or _is_non_show(title):
            continue
        date_token = next((c for c in _classes(card) if c.isdigit()), None)
        date = _resolve_date(_clean(date_tag.get_text(" ", strip=True)), date_token, today)
        start_time = _parse_time(time_tag.get_text(" ", strip=True))
        if date is None or start_time is None:
            continue
        if not (today <= date <= window_end):
            continue
        headliner, support = _split_bill(title)
        price_tag = card.select_one("span.widget-price")
        price_text = _clean(price_tag.get_text(" ", strip=True)) if price_tag else ""
        event_url = _event_url(card)
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=dt.datetime.combine(date, start_time),
                doors_local=None,  # cards carry a single time
                ticket_url=event_url,
                price_text=price_text or None,
                source_url=event_url or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live listing for the next ~90 days."""
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
