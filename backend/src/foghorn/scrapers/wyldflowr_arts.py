"""Wyldflowr Arts scraper.

Source: the venue's **Viewcy organization API** — ``/api/o/wyldflowrarts/courses``
on ``www.viewcy.com``. Wyldflowr Arts (a nonprofit BIPOC-woman-owned music +
interdisciplinary arts space in North Oakland) sells and lists its programming
through Viewcy, a live-music ticketing platform, and embeds it on
``wyldflowrarts.com/events`` as a ``viewcyembed.com`` iframe. The API is public
(no auth, no anti-bot challenge) and returns JSON, so it's a far better source
than the embed's rendered DOM.

**Two traps worth recording.** First, ``wyldflowrarts.com/events?format=json``
also answers 200 with a plausible Squarespace events collection — but it's a
*stale leftover* whose newest item is 2025-08-24. The live calendar is rendered
client-side from the iframe, so a plain HTTP fetch of the venue's own page sees
nothing current and a paginated walk of that collection reads as a dormant
venue. Don't scrape it. Second, the API path is built from the embed's org slug
lowercased (``/api/o/<org>/courses``) — the endpoint 404s on any other shape.

**Model.** Viewcy nests one-or-more dated ``events`` under a ``course`` (its
unit of programming), so a recurring series is one course with several events;
this flattens to one ``ScrapedShow`` per event. ``starts_at`` is UTC (``Z``),
converted to the venue's naive local time here — ingest re-applies the tz.

**Filtering.** Wyldflowr books workshops and classes alongside concerts. Per
the ticket the concert is the artifact of interest: pure workshops are dropped,
and a workshop-plus-concert booking (Mike Monford's 8/30 master class + evening
concert are separate courses) keeps only the concert. Items carry a
``category_id`` that today splits these perfectly (359 = classes, 360 = events),
but the ids are org-authored groupings — the embed's own JS never reads them —
so they'd churn if the venue reorganized. We filter on the self-describing
signals instead (workshop-ish tags, then a title check), erring toward
inclusion for untagged named bookings the same way Bird & Beckett does.

Runnable standalone: ``python -m foghorn.scrapers.wyldflowr_arts`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import EventType, ScrapedShow

VENUE_SLUG = "wyldflowr_arts"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

# The Viewcy org behind the wyldflowrarts.com/events embed. The embed iframe
# (viewcyembed.com/wyldflowrarts/...) builds this same URL from its org slug.
VIEWCY_ORG = "wyldflowrarts"
COURSES_URL = f"https://www.viewcy.com/api/o/{VIEWCY_ORG}/courses"
# Human-viewable provenance when a course carries no per-event URL (the venue's
# seed calendar_url; the API endpoint itself isn't browseable).
CALENDAR_URL = "https://wyldflowrarts.com/events"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Tags Viewcy carries on Wyldflowr's non-performance programming. A course
# tagged with any of these is a class, not a show.
_WORKSHOP_TAGS = frozenset({"workshop", "vocal-class", "clinic", "class", "masterclass"})
# Backstop for untagged non-performance bookings (the venue also hosts book
# readings and art openings). Narrow on purpose: it only fires on a strong
# signal, so a named-performer booking with an unobvious genre stays in.
_NON_MUSIC_TITLE_RE = re.compile(
    r"\bworkshops?\b|\bmaster\s*class\b|\bmasterclass\b|\bclinic\b"
    r"|\bclass(?:es)?\b|\bbook\s+(?:reading|launch|release)\b"
    r"|\bart\s+(?:opening|exhibition)\b",
    re.IGNORECASE,
)
# Viewcy tags a participatory session explicitly, which beats the ingest's
# title inference — "Wyld Jam" carries no word that regex looks for.
_JAM_TAGS = frozenset({"jam-session", "open-mic"})


def fetch_courses(url: str = COURSES_URL) -> dict[str, Any]:
    """Fetch the raw org payload. Kept separate from parsing so tests drive
    ``parse_courses`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _tag_names(course: dict[str, Any]) -> set[str]:
    return {
        str(tag.get("name", "")).lower()
        for tag in course.get("tags") or []
        if isinstance(tag, dict)
    }


def _is_non_music(course: dict[str, Any], tags: set[str]) -> bool:
    if tags & _WORKSHOP_TAGS:
        return True
    return bool(_NON_MUSIC_TITLE_RE.search(str(course.get("name") or "")))


def _price_text(course: dict[str, Any]) -> str | None:
    """Summarize the ticket tiers as a range. Viewcy prices are decimal strings;
    a 0.0 tier is a real free/donation option, so it's kept in the range."""
    prices: list[float] = []
    for ticket in course.get("tickets") or []:
        try:
            prices.append(float(ticket["price"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not prices:
        return None
    low, high = min(prices), max(prices)
    if low == high:
        return "Free" if low == 0 else f"${low:.0f}"
    return f"${low:.0f}–${high:.0f}"


def parse_courses(
    payload: dict[str, Any], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per dated performance in
    ``[today, today + window_days]``, flattening each course's ``events``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for course in payload.get("data") or []:
        tags = _tag_names(course)
        if _is_non_music(course, tags):
            continue
        name = " ".join(str(course.get("name") or "").split())
        if not name:
            continue
        event_type: EventType | None = "jam" if tags & _JAM_TAGS else None
        price_text = _price_text(course)
        for event in course.get("events") or []:
            starts_at = event.get("starts_at")
            if not starts_at:
                continue
            # "2026-07-17T02:30:00.000Z" — UTC instant. Normalize to naive
            # venue-local; ingest re-applies the tz to derive start_utc.
            instant = dt.datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
            local = instant.astimezone(VENUE_TZ).replace(tzinfo=None)
            if not (today <= local.date() <= window_end):
                continue
            ends_at = event.get("ends_at")
            end_local = None
            if ends_at:
                try:
                    end_local = (
                        dt.datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
                        .astimezone(VENUE_TZ)
                        .replace(tzinfo=None)
                    )
                except ValueError:
                    end_local = None
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=name,
                    support_raw=[],
                    start_local=local,
                    end_local=end_local,
                    doors_local=None,
                    ticket_url=event.get("book_url") or course.get("url"),
                    price_text=price_text,
                    source_url=event.get("book_url") or course.get("url") or CALENDAR_URL,
                    event_type=event_type,
                )
            )
    shows.sort(key=lambda show: (show.start_local, show.headliner_raw))
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    return parse_courses(fetch_courses(), dt.date.today())


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
