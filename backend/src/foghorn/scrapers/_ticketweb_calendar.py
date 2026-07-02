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

- **No year on list dates.** Rows show ``"7.2"``; the year is taken from the
  matching popup when present, else inferred by rolling ``today``'s year
  forward when the month.day has already passed (the lists only show
  upcoming events, so a "past" date means next year).
- **Duplicate rows.** Cafe du Nord renders the first N rows twice (once
  inside an email-signup popup), so rows are deduped on
  ``(source_url, start_local)``.
- **Non-music events.** Rows whose title clearly isn't a concert ("Private
  Event", "World Cup Watch Party", lectures) are dropped; anything merely
  ambiguous is kept.
"""

from __future__ import annotations

import datetime as dt
import re
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
# Popup date: "July 07, 2026".
_FULL_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")


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
    """Turn a list-row "7.2" into a real date. The template omits the year, so
    assume ``today``'s year and roll forward one when the result would be in
    the past — the lists only ever show upcoming events."""
    match = _NUMERIC_DATE_RE.match(raw)
    if match is None:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    try:
        candidate = dt.date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
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
) -> list[ScrapedShow]:
    """Parse one calendar page into ``ScrapedShow``s dated within
    ``[today, today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable — and because the year inference for
    the template's year-less "7.2" dates hinges on it.
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
        start_date = (popup.start_date if popup is not None else None) or (
            _resolve_row_date(date_el.get_text(strip=True), today)
        )
        if start_date is None or not (today <= start_date <= window_end):
            continue

        time_el = section.select_one(".tw-event-time")
        show_time = (
            _parse_time(time_el.get_text(" ", strip=True))
            if time_el is not None
            else None
        )
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
            price_text=popup.price_text if popup is not None else None,
            source_url=source_url,
        )
        # Some deployments render rows twice (e.g. Cafe du Nord repeats its
        # first rows inside an email-signup popup); keep the first occurrence.
        shows.setdefault((show.source_url, show.start_local), show)

    return sorted(shows.values(), key=lambda show: show.start_local)


def find_next_page_url(html: str) -> str | None:
    """Return the "Next »" pagination link, or ``None`` on the last (or only)
    page. The Independent lists everything on one page; Cafe du Nord paginates
    at 20 events per page."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one(".tm-paginate a.next.page-numbers")
    return _attr(link, "href") if link is not None else None
