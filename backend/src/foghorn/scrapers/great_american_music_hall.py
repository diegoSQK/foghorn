"""Great American Music Hall scraper.

Source: the venue's WordPress site (gamh.com) runs the same **SeeTickets**
white-label plugin as Rickshaw Stop, server-rendering the full event list into
``/calendar/`` as structured "list event" cards — title, date, doors/show
times, headliners vs supporting talent (already split!), price range, genre,
and the per-event ``wl.seetickets.us`` ticket page. No JS execution is needed
for page one; the remaining pages load through the plugin's documented
``admin-ajax.php`` action (``get_seetickets_events``) that returns the same
card HTML, using a nonce embedded in the calendar page.

This site's flavor of the plugin differs from Rickshaw Stop's in three ways,
which is why the venue gets its own parser rather than reusing that module:
the card fields are classed ``p.event-title`` / ``p.event-date`` /
``p.event-header`` (not ``p.title`` / ``p.date`` / ``p.header``); the
supporting-talent line reads "with Love Gang" rather than "Supporting
Talent: …"; and the page embeds nonces from several WordPress plugins, so the
SeeTickets one must be read from the ``seetickets_ajax_obj`` assignment
specifically.

Card dates carry no year ("Wed Jul 8"); the year is inferred forward from
``today`` (the list only shows upcoming events, so a month/day earlier than
today means next year). GAMH also programs FIFA watch parties (genre "Sports
General") and bare "PRIVATE EVENT" hold cards — both non-shows, both dropped.

Runnable standalone: ``python -m foghorn.scrapers.great_american_music_hall``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from foghorn.models import ScrapedShow

VENUE_SLUG = "great_american_music_hall"

CALENDAR_URL = "https://gamh.com/calendar/"
AJAX_URL = "https://gamh.com/wp-admin/admin-ajax.php"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# var seetickets_ajax_obj = {"ajax_url":"...","nonce":"0f13fb1395"};
# Anchored to the SeeTickets config object — the page carries other plugins'
# nonces too, so a bare "nonce" match could grab the wrong one.
_NONCE_RE = re.compile(r'seetickets_ajax_obj\s*=\s*\{[^{}]*?"nonce"\s*:\s*"([0-9a-f]+)"')
# Pagination items: <li data-see-ajax-page="2">…
_AJAX_PAGE_RE = re.compile(r"data-see-ajax-page=[\"'](\d+)[\"']")
# "Wed Jul 8" — the weekday is ignored, month is a three-letter abbreviation.
_DATE_RE = re.compile(r"([A-Za-z]{3})\s+(\d{1,2})\s*$")
_MONTHS = {
    abbr: index
    for index, abbr in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
# GAMH's supporting-talent line is "with Love Gang"; strip the label either
# way the plugin renders it ("with …" here, "Supporting Talent: …" elsewhere).
_SUPPORT_PREFIX_RE = re.compile(r"^\s*(?:supporting\s+talent\s*:?\s*|with\s+)", re.IGNORECASE)
# Genres the venue tags on clearly-non-music programming. Ambiguous tags
# ("Other Content") are kept per house policy; the "sports" prefix catches the
# FIFA watch parties ("Sports General").
_NON_MUSIC_GENRES = {"stand-up", "comedy", "theatre", "theater", "podcast", "film"}
# Hold cards that aren't public shows at all, matched on the resolved billing.
_PLACEHOLDER_TITLES = {"private event"}


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def _extract_nonce(html: str) -> str | None:
    match = _NONCE_RE.search(html)
    return match.group(1) if match else None


def _extract_total_pages(html: str) -> int:
    """Highest AJAX page number advertised by the pagination strip (1 when the
    list fits on a single page)."""
    pages = [int(number) for number in _AJAX_PAGE_RE.findall(html)]
    return max(pages, default=1)


def fetch_pages(client: httpx.Client | None = None) -> list[str]:
    """Fetch the calendar page plus every AJAX continuation page, as raw HTML
    fragments (each parseable by ``parse_html``). ``client`` is injectable so
    tests can drive this with a mock transport instead of the network."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        response = client.get(CALENDAR_URL)
        response.raise_for_status()
        first = response.text
        pages = [first]
        nonce = _extract_nonce(first)
        if nonce is None:
            return pages  # no AJAX config → page one is all there is
        for page_number in range(2, _extract_total_pages(first) + 1):
            response = client.get(
                AJAX_URL,
                params={
                    "action": "get_seetickets_events",
                    "seeAjaxPage": str(page_number),
                    "listType": "list",
                    "nonce": nonce,
                },
            )
            response.raise_for_status()
            pages.append(response.text)
        return pages
    finally:
        if own_client:
            client.close()


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


def _select_text(card: Tag, selector: str) -> str:
    element = card.select_one(selector)
    return _clean(element.get_text(" ", strip=True)) if element is not None else ""


def _parse_date(text: str, today: dt.date) -> dt.date | None:
    """Resolve a year-less "Wed Jul 8" to a concrete date at or after ``today``
    (the list only shows upcoming events, so earlier month/days roll forward
    into next year)."""
    match = _DATE_RE.search(text)
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    try:
        candidate = dt.date(today.year, month, int(match.group(2)))
    except ValueError:
        return None
    return candidate.replace(year=today.year + 1) if candidate < today else candidate


def _parse_time(text: str) -> dt.time | None:
    """"7:30PM" / "8PM" → time; None when unparseable (e.g. "TBA")."""
    normalized = text.replace(" ", "").replace(".", "").upper()
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    try:
        return dt.datetime.strptime(normalized, fmt).time()
    except ValueError:
        return None


def _split_acts(text: str) -> list[str]:
    return [part for part in (_clean(piece) for piece in text.split(",")) if part]


def _support_acts(card: Tag) -> list[str]:
    """The card's supporting-talent line, minus its label and TBA placeholders."""
    text = _SUPPORT_PREFIX_RE.sub("", _select_text(card, "p.supporting-talent"))
    if text.lower() in {"", "tba", "support tba"}:
        return []
    return _split_acts(text)


def parse_html(
    html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per SeeTickets list card whose date falls in
    ``[today, today + window_days]``. Works on the full calendar page and on
    AJAX fragments alike (both carry the same card markup).

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for card in soup.select("div.seetickets-list-event-container"):
        show_date = _parse_date(_select_text(card, "p.event-date"), today)
        if show_date is None or not (today <= show_date <= window_end):
            continue
        genre = _select_text(card, "p.genre").lower()
        if genre in _NON_MUSIC_GENRES or genre.startswith("sports"):
            continue

        # SeeTickets pre-splits the bill: p.headliners is the comma-separated
        # main billing (top billing first), p.supporting-talent the openers.
        headliners = _split_acts(_select_text(card, "p.headliners"))
        title_link = card.select_one("p.event-title a")
        title = _clean(title_link.get_text(" ", strip=True)) if title_link else ""
        if not headliners:
            if not title:
                continue  # placeholder card (e.g. a bare "SOLD OUT" tile)
            headliners = [title]
        if headliners[0].lower() in _PLACEHOLDER_TITLES:
            continue  # "PRIVATE EVENT" hold card — not a public show
        support = headliners[1:] + _support_acts(card)

        doors_time = _parse_time(_select_text(card, "span.see-doortime"))
        show_time = _parse_time(_select_text(card, "span.see-showtime"))
        start_time = show_time or doors_time
        if start_time is None:
            continue  # no usable time — seen only on placeholder cards

        event_href = _attr(title_link, "href") if title_link is not None else None
        if event_href is None:
            buy_link = card.select_one("a.seetickets-buy-btn")
            event_href = _attr(buy_link, "href") if buy_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliners[0],
                genre=genre or None,
                support_raw=support,
                start_local=dt.datetime.combine(show_date, start_time),
                doors_local=(
                    dt.datetime.combine(show_date, doors_time)
                    if doors_time is not None
                    else None
                ),
                ticket_url=event_href,
                price_text=_select_text(card, "span.price") or None,
                source_url=event_href or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar (all pages) for the next ~90 days.
    Deduplicates across page boundaries in case the list shifts mid-crawl —
    and within a page: GAMH lists multi-night "pass" products as extra cards
    that carry the same billing and start time as the night-one show."""
    today = dt.date.today()
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, dt.datetime]] = set()
    for page_html in fetch_pages():
        for show in parse_html(page_html, today):
            key = (show.headliner_raw, show.start_local)
            if key not in seen:
                seen.add(key)
                shows.append(show)
    shows.sort(key=lambda show: show.start_local)
    return shows


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
