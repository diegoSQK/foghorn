"""Gray Area (Grand Theater) scraper.

Source: ``grayarea.org/events/`` is a server-rendered WordPress listing of
``/event/<slug>/`` links, and each event page embeds a Yoast ``@graph``
JSON-LD block containing a schema.org **Event** (name, ISO ``startDate``
with tz offset, the Grand Theater as ``location``). There is no Tribe REST
API and no registered event post type, so this is the
listing-walk-plus-detail-pages pattern (see ``california_jazz_conservatory``).

**Filtering.** Gray Area's calendar mixes concerts/AV performances with a
large education program (courses, workshops), member meetups, talks, and
open calls. Obvious non-performance slugs are dropped *before* fetching
their pages (keeps the walk to ~a dozen fetches); anything ambiguous is
fetched and kept per the "when ambiguous, keep" rule. Their in-house
ticketing link (``tickets.grayarea.org``) becomes ``ticket_url``.

**Title cleanup.** The JSON-LD Event name carries Yoast's site suffix
("… - Gray Area"), which is stripped; the "X and Gray Area present" prefix
is real billing and kept verbatim.

Runnable standalone: ``python -m foghorn.scrapers.gray_area`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
from typing import Any

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "gray_area_art_and_technology"

BASE_URL = "https://grayarea.org"
# Redirects to /visit/events/; follow_redirects handles it. Also the venue's
# seed calendar_url.
EVENTS_URL = f"{BASE_URL}/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Slug fragments that mark clearly-non-performance programming, skipped
# without fetching the event page. Heuristic and knowingly imperfect — an
# ambiguous slug gets fetched and kept.
_NON_MUSIC_SLUG_SIGNALS = (
    "course",
    "workshop",
    "book-club",
    "call-for",
    "submissions",
    "show-tell",
    "in-conversation",
    "creative-intelligence",  # the talks/panel series
    "vr-film",
    "xr-",
    "discussion",
    "open-studios",
    "hackathon",
    "meetup",
    "incubator",
    "touchdesigner",
    "info-session",
)

_EVENT_LINK_RE = re.compile(r'href="(?:https://grayarea\.org)?(/event/([a-z0-9-]+)/?)"')
_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
_TICKET_URL_RE = re.compile(r'href="(https://tickets\.grayarea\.org/[^"]+)"')
_SITE_SUFFIX_RE = re.compile(r"\s*-\s*Gray Area\s*$")
# Multi-night runs get a "… Friday, July 17" disambiguator appended to the
# Event name; it's the date, not billing, so it comes off the headliner.
_DATE_SUFFIX_RE = re.compile(
    r"\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2}\s*$"
)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def parse_event_links(listing_html: str) -> list[str]:
    """Event-page URLs from the listing, deduped in listing order, with
    clearly-non-performance slugs dropped (pre-fetch filter)."""
    urls: list[str] = []
    seen: set[str] = set()
    for path, slug in _EVENT_LINK_RE.findall(listing_html):
        if slug in seen:
            continue
        seen.add(slug)
        if any(signal in slug for signal in _NON_MUSIC_SLUG_SIGNALS):
            continue
        urls.append(f"{BASE_URL}{path if path.endswith('/') else path + '/'}")
    return urls


def _iter_ld_nodes(page_html: str) -> list[dict[str, Any]]:
    """Every node in every ld+json block, with ``@graph`` arrays flattened."""
    nodes: list[dict[str, Any]] = []
    for raw in _LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        stack: list[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                graph = node.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
                nodes.append(node)
    return nodes


def parse_event_page(page_html: str, url: str) -> ScrapedShow | None:
    """One event page → a ``ScrapedShow``, or None when the page carries no
    schema.org Event with a parseable start. Pure / fixture-testable."""
    event: dict[str, Any] | None = None
    for node in _iter_ld_nodes(page_html):
        if node.get("@type") == "Event" and isinstance(node.get("startDate"), str):
            event = node
            break
    if event is None:
        return None
    try:
        start = dt.datetime.fromisoformat(event["startDate"])
    except ValueError:
        return None
    # The offset is the venue's own; drop it for the naive venue-local
    # datetime the contract wants (ingest re-applies the tz).
    start_local = start.replace(tzinfo=None)

    name = _SITE_SUFFIX_RE.sub("", html_lib.unescape(str(event.get("name", "")))).strip()
    name = _DATE_SUFFIX_RE.sub("", name).strip().rstrip("-–—,").strip()
    if not name:
        return None
    ticket_match = _TICKET_URL_RE.search(page_html)
    return ScrapedShow(
        venue_slug=VENUE_SLUG,
        headliner_raw=name,
        support_raw=[],
        start_local=start_local,
        doors_local=None,
        ticket_url=ticket_match.group(1) if ticket_match else None,
        price_text=None,
        source_url=url,
    )


def scrape() -> list[ScrapedShow]:
    """Walk the live listing and event pages for the next ~90 days."""
    today = dt.date.today()
    window_end = today + dt.timedelta(days=SCRAPE_WINDOW_DAYS)
    shows: list[ScrapedShow] = []
    with _client() as client:
        listing = client.get(EVENTS_URL)
        listing.raise_for_status()
        for url in parse_event_links(listing.text):
            page = client.get(url)
            if page.status_code != httpx.codes.OK:
                continue
            show = parse_event_page(page.text, url)
            if show is not None and today <= show.start_local.date() <= window_end:
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
