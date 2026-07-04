"""Shared parser for the TicketWeb WordPress calendar template.

Several Bay Area venues (The Independent, Cafe du Nord, ...) run the same
WordPress theme whose "tw-" plugin server-renders each upcoming show as a
``div.tw-section`` block: a ``tw-event-date`` (``"7.2"`` — month.day, no
year), a ``tw-name`` link to the venue's per-event page (the headliner), an
optional ``tw-attractions`` support line, a ``tw-event-time`` ("Show: 8:00
PM"), and a TicketWeb "Buy Tickets" link. Some deployments additionally emit
hidden per-event popup dialogs (``div[id^="tw-event-dialog"]``) carrying the
richer fields the list rows lack: a full date *with year*, a doors time, and
a price.

This module is the one place that markup is understood; per-venue scrapers
stay thin wrappers supplying the URL, slug, and quirks. Notable quirks
handled here rather than per venue:

- **Per-deployment date formats.** Rows render the date as numeric ``"7.2"``
  (The Independent, Cafe du Nord), as ``"Fri, Jul 3"`` (Neck of the Woods),
  as a bare day-of-month with the month in a sibling ``tw-event-month`` span
  (Bimbo's 365 Club), or as a full ``"Saturday, July 11, 2026"`` (August
  Hall). All are handled here.
- **No year on most list dates.** When the row omits the year, it is taken
  from the matching popup when present, else inferred by rolling ``today``'s
  year forward when the month/day has already passed (the lists only show
  upcoming events, so a "past" date means next year).
- **No time on some deployments' rows.** August Hall's list rows carry only a
  date; the show time lives on the per-event page. Callers may pass a
  ``time_lookup`` callable (given the per-event URL, return a time) that is
  consulted only for in-window rows lacking a ``tw-event-time``; rows whose
  time is still unknown are skipped rather than invented.
- **Duplicate rows.** Cafe du Nord renders the first N rows twice (once
  inside an email-signup popup), so rows are deduped on
  ``(source_url, start_local)``.
- **Non-music events.** Rows whose title clearly isn't a concert ("Private
  Event", "World Cup Watch Party", lectures) are dropped; anything merely
  ambiguous is kept.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from collections.abc import Callable
from typing import NamedTuple

from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

# Titles that are clearly not concerts. Deliberately conservative — comedy
# names, DJ nights, and one-off oddities stay in (ambiguous → keep).
DROP_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bprivate event\b", re.IGNORECASE),
    re.compile(r"\bwatch party\b", re.IGNORECASE),
    re.compile(r"\blectures?\b", re.IGNORECASE),
)

# "Show: 8:00 PM", "8:00pm", "(Doors: 7:00pm)" — the time fragment shared by
# list rows and popup dialogs.
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# List-row date: "7.2" (month.day, no year).
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})$")
# List-row date with a month name: "Fri, Jul 3", "August 6" (month prepended
# from a sibling tw-event-month span), "Saturday, July 11, 2026". The weekday
# prefix is only ever comma-separated; the year is optional.
_TEXT_DATE_RE = re.compile(r"^(?:[A-Za-z]+,\s*)?([A-Za-z]+)\.?\s+(\d{1,2})(?:,\s*(\d{4}))?$")
# Popup date: "July 07, 2026".
_FULL_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")

# "July"/"Jul" → 7. "Sept" is a common fourth-letter abbreviation.
_MONTHS: dict[str, int] = {
    **{calendar.month_name[i].lower(): i for i in range(1, 13)},
    **{calendar.month_abbr[i].lower(): i for i in range(1, 13)},
    "sept": 9,
}


class _PopupDetails(NamedTuple):
    """Enrichment fields from a hidden ``tw-event-dialog`` popup."""

    start_date: dt.date | None
    doors_time: dt.time | None
    price_text: str | None


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str``. bs4 types attributes
    as ``str | list[str] | None``; ``href`` is always single, but we coerce
    defensively to stay type-safe."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _parse_time(text: str) -> dt.time | None:
    """Extract "8:00 PM" / "7:00pm" from a time fragment, ignoring any label
    prefix ("Show:", "Doors:")."""
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return dt.time(hour, minute)


def _parse_full_date(text: str) -> dt.date | None:
    """Parse a popup's "July 07, 2026" date line."""
    match = _FULL_DATE_RE.search(text)
    if match is None:
        return None
    try:
        return dt.datetime.strptime(
            f"{match.group(1)} {match.group(2)} {match.group(3)}", "%B %d %Y"
        ).date()
    except ValueError:
        return None


def _resolve_row_date(raw: str, today: dt.date) -> dt.date | None:
    """Turn a list-row date — "7.2", "Fri, Jul 3", "August 6", or "Saturday,
    July 11, 2026" — into a real date. Most deployments omit the year: assume
    ``today``'s year and roll forward one when the result would be in the
    past — the lists only ever show upcoming events."""
    raw = _clean(raw)
    year: int | None = None
    numeric = _NUMERIC_DATE_RE.match(raw)
    if numeric is not None:
        month, day = int(numeric.group(1)), int(numeric.group(2))
    else:
        text = _TEXT_DATE_RE.match(raw)
        if text is None:
            return None
        month_or_none = _MONTHS.get(text.group(1).lower())
        if month_or_none is None:
            return None
        month = month_or_none
        day = int(text.group(2))
        year = int(text.group(3)) if text.group(3) is not None else None
    try:
        candidate = dt.date(year if year is not None else today.year, month, day)
    except ValueError:
        return None
    if year is None and candidate < today:
        try:
            candidate = dt.date(today.year + 1, month, day)
        except ValueError:  # Feb 29 rolling into a non-leap year
            return None
    return candidate


def _popup_index(soup: BeautifulSoup) -> dict[str, _PopupDetails]:
    """Map each per-event page URL to its popup enrichment (full date, doors,
    price). Deployments without popups yield an empty map."""
    index: dict[str, _PopupDetails] = {}
    for dialog in soup.select('div[id^="tw-event-dialog"]'):
        name_link = dialog.select_one(".tw-name a")
        href = _attr(name_link, "href") if name_link is not None else None
        if not href:
            continue
        date_el = dialog.select_one(".tw-event-date")
        start_date = (
            _parse_full_date(date_el.get_text(" ", strip=True))
            if date_el is not None
            else None
        )
        door_el = dialog.select_one(".tw-event-door-time")
        doors_time = (
            _parse_time(door_el.get_text(" ", strip=True))
            if door_el is not None
            else None
        )
        price_el = dialog.select_one(".tw-price")
        price_text = _clean(price_el.get_text(" ", strip=True)) if price_el else None
        index[href] = _PopupDetails(start_date, doors_time, price_text or None)
    return index


def _support_acts(section: Tag) -> list[str]:
    """Read the support line. Normally "with <span>A</span>, <span>B</span>";
    fall back to the bare text (minus the "with" prefix) if a deployment drops
    the spans."""
    attractions = section.select_one(".tw-attractions")
    if attractions is None:
        return []
    spans = [_clean(span.get_text(" ", strip=True)) for span in attractions.find_all("span")]
    spans = [s for s in spans if s]
    if spans:
        return spans
    text = _clean(attractions.get_text(" ", strip=True))
    text = re.sub(r"^with\s+", "", text, flags=re.IGNORECASE)
    return [part for part in (p.strip() for p in text.split(",")) if part] if text else []


def parse_calendar_html(
    html: str,
    *,
    venue_slug: str,
    today: dt.date,
    window_days: int,
    fallback_source_url: str,
    time_lookup: Callable[[str], dt.time | None] | None = None,
) -> list[ScrapedShow]:
    """Parse one calendar page into ``ScrapedShow``s dated within
    ``[today, today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable — and because the year inference for
    the template's year-less "7.2" dates hinges on it.

    ``time_lookup`` (optional) supplies the show time for deployments whose
    rows carry none (August Hall): it is called with the per-event page URL,
    only for rows already inside the date window, and may return ``None`` to
    skip the row.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)
    popups = _popup_index(soup)

    shows: dict[tuple[str, dt.datetime], ScrapedShow] = {}
    for section in soup.select("div.tw-section"):
        name_link = section.select_one(".tw-name a")
        if name_link is None:
            continue
        headliner = _clean(name_link.get_text(" ", strip=True))
        if not headliner:
            continue
        if any(pattern.search(headliner) for pattern in DROP_TITLE_PATTERNS):
            continue

        source_url = _attr(name_link, "href") or fallback_source_url
        popup = popups.get(source_url)

        date_el = section.select_one(".tw-event-date")
        if date_el is None:
            continue
        raw_date = date_el.get_text(strip=True)
        # Bimbo's renders the month name in a sibling span: <span
        # class="tw-event-month">August</span> <span class="tw-event-date">6</span>.
        month_el = section.select_one(".tw-event-month")
        if month_el is not None and raw_date.isdigit():
            raw_date = f"{month_el.get_text(strip=True)} {raw_date}"
        start_date = (popup.start_date if popup is not None else None) or (
            _resolve_row_date(raw_date, today)
        )
        if start_date is None or not (today <= start_date <= window_end):
            continue

        time_el = section.select_one(".tw-event-time")
        show_time = (
            _parse_time(time_el.get_text(" ", strip=True))
            if time_el is not None
            else None
        )
        if show_time is None and time_lookup is not None:
            show_time = time_lookup(source_url)
        if show_time is None:
            continue
        start_local = dt.datetime.combine(start_date, show_time)

        doors_time = popup.doors_time if popup is not None else None
        if doors_time is None:
            door_el = section.select_one(".tw-event-door-time")
            if door_el is not None:
                doors_time = _parse_time(door_el.get_text(" ", strip=True))

        ticket_link = section.select_one("a.tw-buy-tix-btn")
        ticket_url = _attr(ticket_link, "href") if ticket_link is not None else None

        # Price: prefer the popup's; some deployments (Neck of the Woods)
        # print it directly on the list row instead.
        price_text = popup.price_text if popup is not None else None
        if price_text is None:
            price_el = section.select_one(".tw-price")
            if price_el is not None:
                price_text = _clean(price_el.get_text(" ", strip=True)) or None

        show = ScrapedShow(
            venue_slug=venue_slug,
            headliner_raw=headliner,
            support_raw=_support_acts(section),
            start_local=start_local,
            doors_local=(
                dt.datetime.combine(start_date, doors_time)
                if doors_time is not None
                else None
            ),
            ticket_url=ticket_url,
            price_text=price_text,
            source_url=source_url,
        )
        # Some deployments render rows twice (e.g. Cafe du Nord repeats its
        # first rows inside an email-signup popup); keep the first occurrence.
        shows.setdefault((show.source_url, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def parse_event_page_time(html: str) -> dt.time | None:
    """Extract the show time from a per-event (``tm-event``) page. Used by
    deployments whose list rows omit the time (August Hall renders it only on
    the event page, as a bare ``tw-event-time`` "6:00 pm")."""
    soup = BeautifulSoup(html, "html.parser")
    time_el = soup.select_one(".tw-event-time")
    return _parse_time(time_el.get_text(" ", strip=True)) if time_el is not None else None


def find_next_page_url(html: str) -> str | None:
    """Return the "Next »" pagination link, or ``None`` on the last (or only)
    page. The Independent lists everything on one page; Cafe du Nord paginates
    at 20 events per page."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one(".tm-paginate a.next.page-numbers")
    return _attr(link, "href") if link is not None else None
