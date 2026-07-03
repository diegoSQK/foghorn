"""Bottom of the Hill scraper.

Source: the venue's own famously old-school static site. Bottom of the Hill
(1233 17th St, Potrero Hill) hand-maintains ``calendar.html`` as one big HTML
4.01 table — no ticketing-platform widget, no JSON, no feed. It is nonetheless
very scrapeable: every show is a ``<tr>`` anchored by ``<a name="YYYYMMDD">``
(same-day second shows get a suffix, e.g. ``20260725A``), with the bill as
``<big class="band">`` elements in top-billing order (the site's own legend:
"headliner is listed at the top"), times in ``class="time"`` spans, the cover
in ``class="cover"`` spans, a per-date detail page (``/YYYYMMDD.html``), and an
advance-tickets link into the venue's own ``/stubmatic/`` store when advance
sales exist.

Plain ``httpx`` + ``beautifulsoup4`` suffices — no JS execution needed. One
quirk: the server sends ``Content-Type: text/html`` with no charset while the
page is ISO-8859-1 (per its ``<meta>``), so the fetcher pins the encoding to
avoid mojibake in band names like "Dümsurf".

Runnable standalone: ``python -m foghorn.scrapers.bottom_of_the_hill`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "bottom_of_the_hill"

CALENDAR_URL = "https://www.bottomofthehill.com/calendar.html"
# Fallback provenance when a row's per-date detail link is missing; normally
# each show's source_url is its own /YYYYMMDD.html page.
SOURCE_URL = CALENDAR_URL
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Row anchors: <a name="20260701">, with same-day second shows suffixed
# ("20260725A") and the occasional fat-fingered extra digit ("2026082023") —
# the first eight digits are always the date.
_ANCHOR_RE = re.compile(r"^\d{8}")
# Times as rendered ("8:00PM", "3:00PM") — but the hand-edited spans split
# tokens mid-time ("music at 8" + ":30PM"), so whitespace is tolerated
# everywhere inside a token.
_TIME_RE = re.compile(r"(\d{1,2})\s*(?::\s*(\d{2}))?\s*([AP])\.?M\.?", re.IGNORECASE)
# Editorial asides embedded in cover spans, e.g. "[co-headlining]".
_BRACKETED_RE = re.compile(r"\[[^\]]*\]")


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
    if response.charset_encoding is None:
        # No charset in the Content-Type header; the page's <meta> declares
        # ISO-8859-1. Without this, httpx assumes UTF-8 and garbles names.
        response.encoding = "iso-8859-1"
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


def _class_text(row: Tag, class_name: str) -> str:
    """Concatenated, whitespace-collapsed text of every ``class_name`` element
    in the row. The site fragments a single logical string ("8:00PM doors --
    music at 8:30PM") across many adjacent spans; joining them restores it."""
    joined = " ".join(el.get_text(" ", strip=True) for el in row.select(f".{class_name}"))
    return _clean(joined)


def _parse_time(match: re.Match[str]) -> dt.time:
    hour = int(match.group(1)) % 12
    if match.group(3).upper() == "P":
        hour += 12
    return dt.time(hour, int(match.group(2) or 0))


def _times(time_text: str) -> tuple[dt.time | None, dt.time | None]:
    """Return ``(start, doors)`` from a joined time line like
    "8:00PM doors -- music at 8:30PM". The doors time always comes first when
    both are given; a lone time is the start (and also doors if labelled so,
    e.g. "8:00PM doors/signups -- karaoke starts at 9:00PM" degenerates fine)."""
    matches = list(_TIME_RE.finditer(time_text))
    if not matches:
        return None, None
    if len(matches) == 1:
        only = _parse_time(matches[0])
        doors = only if "door" in time_text.lower() else None
        return only, doors
    return _parse_time(matches[1]), _parse_time(matches[0])


def _price_text(row: Tag) -> str | None:
    """The cover charge, reassembled from its fragmented spans and stripped of
    bracketed asides. The service-fee breakdown lives in ``class="note"`` spans
    and is deliberately not part of this."""
    text = _BRACKETED_RE.sub("", _class_text(row, "cover"))
    text = re.sub(r"\$\s+", "$", text)
    return _clean(text) or None


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per calendar row whose date falls in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    seen_rows: set[int] = set()
    for anchor in soup.find_all("a", attrs={"name": _ANCHOR_RE}):
        if not isinstance(anchor, Tag):
            continue
        row = anchor.find_parent("tr")
        if row is None or id(row) in seen_rows:
            continue
        seen_rows.add(id(row))
        name = _attr(anchor, "name") or ""
        try:
            show_date = dt.datetime.strptime(name[:8], "%Y%m%d").date()
        except ValueError:
            continue
        if not (today <= show_date <= window_end):
            continue

        # Bill, in top-billing order per the site's own legend. Rows without
        # any band name aren't shows (placeholders, flyers-only rows).
        bands = [
            _clean(band.get_text(" ", strip=True)) for band in row.select("big.band")
        ]
        bands = [band for band in bands if band]
        if not bands:
            continue

        start_time, doors_time = _times(_class_text(row, "time"))
        if start_time is None:
            continue  # a dated row with no time is unbuildable, and unheard of

        detail_link = row.find("a", href=re.compile(rf"/{re.escape(name)}\.html$"))
        detail_href = _attr(detail_link, "href") if isinstance(detail_link, Tag) else None
        ticket_link = row.find("a", href=re.compile(r"stubmatic"))
        ticket_href = _attr(ticket_link, "href") if isinstance(ticket_link, Tag) else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=bands[0],
                support_raw=bands[1:],
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=(
                    dt.datetime.combine(show_date, doors_time)
                    if doors_time is not None
                    else None
                ),
                ticket_url=ticket_href,
                price_text=_price_text(row),
                source_url=detail_href or SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
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
