"""Moe's Alley scraper.

Source: the blues/roots roadhouse's WordPress site at
``moesalley.com/calendar/``. The site runs the TicketWeb "tw-" plugin like
The Independent, but in its **calendar-grid** flavor: there are no
``tw-section`` list rows for ``_ticketweb_calendar`` to parse. Instead the
page pre-renders one hidden ``div[id^="tw-event-dialog"]`` popup per
upcoming show (months ahead), each self-sufficient: a ``tw-name`` link to
the per-event page, a full ``tw-event-date`` with year ("Sun Jul, 19
2026"), a ``tw-price``, a TicketWeb buy link, and a ``tw-description``
whose boilerplate states "Doors: 2pm / Show: 3pm". The popup's ``tw-event-time-complete`` span is
empty on this deployment, so the description is the only time source; a
popup without a stated show time is skipped (never fabricate). A lone
doors time is treated as the start (the Indexical precedent).

Titles carry promoter credits ("Moe's Alley Presents:", "(((folkYEAH!)))
Presents –") which are stripped, and " w/ "-joined support acts which are
split out ("Dusted Angel w/ Phantasmal Abyss + Winter Wind").

Runnable standalone: ``python -m foghorn.scrapers.moes_alley`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "moes_alley"

CALENDAR_URL = "https://moesalley.com/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# "Sun Jul, 19 2026" (popup) — also tolerates "July 19, 2026".
_DATE_RE = re.compile(r"([A-Za-z]+),?\s+(\d{1,2}),?\s+(\d{4})")
_MONTHS: dict[str, int] = {
    **{calendar.month_name[i].lower(): i for i in range(1, 13)},
    **{calendar.month_abbr[i].lower(): i for i in range(1, 13)},
    "sept": 9,
}
# Description boilerplate: "Doors: 2pm / Show: 3pm" (colon sometimes
# missing: "Doors 7pm / Show 8pm").
_SHOW_RE = re.compile(r"\bShow:?\s*(\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE)
_DOORS_RE = re.compile(r"\bDoors:?\s*(\d{1,2})(?::(\d{2}))?\s*([ap])m", re.IGNORECASE)

# Leading promoter credit: "Moe's Alley Presents:", "(((folkYEAH!)))
# Presents –". Conservative: only strips when "presents" appears early.
_PRESENTS_RE = re.compile(r"^.{0,40}?\bpresents\b\s*[:\-–—]?\s*", re.IGNORECASE)

# Clearly-not-a-concert titles. Dance/DJ nights stay (ambiguous → keep).
_NON_MUSIC_RE = re.compile(r"\bprivate event\b|\bwatch party\b", re.IGNORECASE)


def fetch_html(url: str = CALENDAR_URL) -> str:
    """Fetch the calendar page. Kept separate from parsing so tests drive
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


def _parse_date(text: str) -> dt.date | None:
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


def _time_from(match: re.Match[str] | None) -> dt.time | None:
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "p":
        hour += 12
    minute = int(match.group(2) or 0)
    return dt.time(hour, minute) if minute <= 59 else None


def _split_bill(title: str) -> tuple[str, list[str]]:
    """ "Dusted Angel w/ Phantasmal Abyss + Winter Wind" → headliner plus
    support. Only the explicit " w/ " convention splits; anything else is
    a single billing."""
    if " w/ " not in title:
        return title, []
    headliner, _, rest = title.partition(" w/ ")
    support = [part.strip() for part in re.split(r"\s*\+\s*|\s*,\s*", rest) if part.strip()]
    return headliner.strip(), support


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per popup dialog dated within
    ``[today, today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable."""
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for dialog in soup.select('div[id^="tw-event-dialog"]'):
        name_link = dialog.select_one(".tw-name a")
        if name_link is None:
            continue
        title = _clean(name_link.get_text(" ", strip=True))
        if not title or _NON_MUSIC_RE.search(title):
            continue
        href = name_link.get("href")
        source_url = href if isinstance(href, str) and href else CALENDAR_URL

        date_el = dialog.select_one(".tw-event-date")
        start_date = _parse_date(date_el.get_text(" ", strip=True)) if date_el else None
        if start_date is None or not (today <= start_date <= window_end):
            continue

        description = _description_text(dialog)
        start_time = _time_from(_SHOW_RE.search(description))
        doors_time = _time_from(_DOORS_RE.search(description))
        if start_time is None:
            # "Doors 7pm" only — treat doors as the start, never invent one.
            start_time, doors_time = doors_time, None
        if start_time is None:
            continue

        price_el = dialog.select_one(".tw-price")
        price_text = _clean(price_el.get_text(" ", strip=True)) if price_el else None

        tix_link = dialog.select_one("a.tw-buy-tix-btn")
        tix_href = tix_link.get("href") if tix_link is not None else None
        ticket_url = tix_href if isinstance(tix_href, str) and tix_href else None

        headliner, support = _split_bill(_PRESENTS_RE.sub("", title).strip() or title)
        show = ScrapedShow(
            venue_slug=VENUE_SLUG,
            headliner_raw=headliner,
            support_raw=support,
            start_local=dt.datetime.combine(start_date, start_time),
            doors_local=(dt.datetime.combine(start_date, doors_time) if doors_time else None),
            ticket_url=ticket_url,
            price_text=price_text or None,
            source_url=source_url,
        )
        shows.setdefault((show.source_url, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def _description_text(dialog: Tag) -> str:
    desc = dialog.select_one(".tw-description")
    return desc.get_text(" ", strip=True) if desc is not None else ""


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
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
