"""Bird & Beckett Books and Records scraper.

**Two sources, deliberately split by role.**

*Billing and existence* come from the venue's public Google Calendar, exposed
as an iCalendar feed. Bird & Beckett (a Glen Park bookshop with a dense
live-jazz calendar) publishes its schedule to a public Google Calendar embedded
on its ``/events`` page. The ``.ics`` export beats the WordPress event *posts*,
whose dates live in free-text titles.

*Per-event metadata* comes from The Events Calendar's REST API
(``/wp-json/tribe/events/v1/events``), which is a perfectly clean structured
source — it just isn't the better source for the billing. The ``.ics`` names
the whole band where Tribe names only the act:

===========  ==================================================  ====================
Date         ``.ics`` (what we keep)                             Tribe
===========  ==================================================  ====================
Sep 13       Vocalist Marina Crouse, with Danny Caron,           Marina Crouse Trio
             guitar; and Ruth Davies, bass
Sep 15       Alon Nechustan Quintet                              Alon Nechustan's
                                                                 Venture Bound Quintet
===========  ==================================================  ====================

Switching wholesale would drop the sidemen from ``headliner_raw``, so Danny
Caron and Ruth Davies would stop token-matching the watchlist — a regression in
the feature the product exists for. It would also change
``headliner_canonical``, part of the dedupe natural key, re-ingesting every row
and orphaning this venue's ``event_type_overrides`` jam rules.

So Tribe is a **metadata lookup only**, joined on ``(date, start time)`` — not
on title, which the table above shows would misfire. It supplies ``source_url``
(the per-event page, so "details" links land on the show you clicked instead of
the generic ``/events/``) and ``price_text``. The join is **fail-open**: any
Tribe error yields an empty index and every show still ingests with the
``/events/`` fallback. A Tribe outage must never reduce the show count.

Unlike ``kuumbwa_jazz_center``, birdbeckett.com has no caching proxy in front
of its REST API — it honors ``per_page`` / ``start_date`` / ``page`` correctly,
so this scraper needs none of kuumbwa's browser-UA-and-id-guard workaround.

**Re-pilot note.** Phase 2.1 originally targeted SFJAZZ, but SFJAZZ sits behind
a Cloudflare managed challenge that 403s every simple HTTP client (polite UA and
browser UA alike). Bird & Beckett was chosen as the end-to-end pilot instead —
see ``docs/SHIPPED.md``.

Runnable standalone: ``python -m foghorn.scrapers.bird_and_beckett`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from foghorn.models import ScrapedShow

logger = logging.getLogger(__name__)

VENUE_SLUG = "bird_and_beckett"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

# Public Google Calendar behind https://birdbeckett.com/events/ ("view our full
# calendar"). The calendar id was read from the embed `src` on that page.
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "r5o3loovr013c5rftpv75lji18%40group.calendar.google.com/public/basic.ics"
)
# Human-viewable provenance, and the fallback when a show has no Tribe match
# (the .ics itself isn't browseable).
SOURCE_URL = "https://birdbeckett.com/events/"
# The Events Calendar REST API — per-event page URLs and prices. Metadata only;
# see the module docstring for why the .ics stays authoritative for billing.
EVENTS_API = "https://birdbeckett.com/wp-json/tribe/events/v1/events"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0
PER_PAGE = 50
# Bounds the pagination walk. The window holds ~60 events, so this is slack,
# not a tuning knob.
MAX_PAGES = 20

# Bird & Beckett's calendar mixes its jazz programming with literary events
# (poetry readings, author talks, small-press launches). Per the ticket we err
# toward inclusion and only drop events whose title carries a strong non-music
# signal. This is a heuristic, knowingly imperfect — revisit if it misfires.
_NON_MUSIC_SIGNALS = (
    "poet",
    "poetry",
    "reading",
    "novelist",
    "author",
    "book release",
    "book launch",
    "lecture",
    "talks",
    # The shop's calendar also carries entries that aren't events at all
    # (#124). Both phrases are deliberately narrow: bare "closed" and bare
    # "market" would be plausible inside a band name, "closed for" and
    # "night market" are not.
    "closed for",
    "night market",
)

# Tribe categories that mean this *is* a music performance. A jam is a show
# foghorn wants — the event_type inference tags it separately.
_MUSIC_CATEGORIES = frozenset({"live music", "jam session"})

# Tribe categories that mean it isn't, when nothing marks it as music. The
# venue's own tagging, so it catches what a title never could: "Amy O'Hair
# presents 'History Walks in Sunnyside'" reads like a gig and is a talk.
_NON_MUSIC_CATEGORIES = frozenset(
    {"poetry reading", "talks / interviews", "book event"}
)


def fetch_ics(url: str = ICS_URL) -> str:
    """Fetch the raw iCalendar feed. Kept separate from parsing so tests drive
    ``parse_ics`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


@dataclass(frozen=True)
class EventDetails:
    """The per-event metadata the Tribe feed contributes to an ``.ics`` show."""

    source_url: str
    price_text: str | None
    # Tribe's own category names, casefolded. The venue tags its programming
    # ("Live Music", "Poetry Reading", "Talks / Interviews", "Book Event"),
    # which is a far better signal than reading the title — see
    # ``_is_non_music``. Empty when Tribe has the event but tagged it nothing.
    categories: frozenset[str] = frozenset()


# What ``parse_ics`` accepts: (venue-local date, start time) -> details.
DetailIndex = Mapping[tuple[dt.date, dt.time], EventDetails]


def _text(value: object) -> str:
    """Unescape HTML entities Tribe leaves in text fields and trim."""
    return html.unescape(str(value)).strip() if value else ""


def _category_names(value: object) -> frozenset[str]:
    """Casefolded category names off a Tribe event's ``categories`` list.

    Defensive about the shape: the field is absent on some events and the
    payload is untyped JSON, so anything unexpected reads as "no categories"
    — which falls back to the title heuristic rather than dropping a show.
    """
    if not isinstance(value, list):
        return frozenset()
    names = set()
    for category in value:
        if isinstance(category, dict):
            name = _text(category.get("name")).casefold()
            if name:
                names.add(name)
    return frozenset(names)


def fetch_event_details(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Page through the Tribe REST API for events in
    ``[today, today + window_days]``, following ``next_rest_url``.

    birdbeckett.com honors the query params (verified against
    ``total``/``total_pages``), so this is a plain walk — no cache-trap guard.
    ``client`` is injectable so tests drive pagination with a mock transport.
    """
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        events: list[dict[str, object]] = []
        params = {
            "per_page": str(PER_PAGE),
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=window_days)).isoformat(),
        }
        response = client.get(EVENTS_API, params=params)
        response.raise_for_status()
        payload = response.json()
        for _ in range(MAX_PAGES):
            events.extend(payload.get("events", []))
            next_url = payload.get("next_rest_url")
            if not next_url:
                break
            response = client.get(next_url)
            # Tribe can 404 past the final page rather than returning empty.
            if response.status_code == httpx.codes.NOT_FOUND:
                break
            response.raise_for_status()
            payload = response.json()
        return events
    finally:
        if own_client:
            client.close()


def build_detail_index(events: list[dict[str, object]]) -> dict[
    tuple[dt.date, dt.time], EventDetails
]:
    """Index Tribe events by ``(date, start time)`` in venue-local terms.

    B&B is a single room, so date+time is effectively unique. A key claimed by
    more than one event is **dropped entirely** rather than resolved
    arbitrarily — the caller then falls back, which is the honest outcome when
    we can't tell which page the show belongs to. Logged so a real collision
    is visible rather than silently degrading the links.
    """
    grouped: dict[tuple[dt.date, dt.time], list[dict[str, object]]] = {}
    for event in events:
        raw = _text(event.get("start_date"))  # "2026-09-11 19:30:00", venue-local
        if not raw:
            continue
        try:
            stamp = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning("bird_and_beckett: unparseable Tribe start_date %r", raw)
            continue
        grouped.setdefault((stamp.date(), stamp.time()), []).append(event)

    index: dict[tuple[dt.date, dt.time], EventDetails] = {}
    for key, matches in grouped.items():
        if len(matches) > 1:
            logger.warning(
                "bird_and_beckett: %d Tribe events share %s %s (%r) — "
                "skipping the join for that slot",
                len(matches),
                key[0].isoformat(),
                key[1].strftime("%H:%M"),
                [_text(m.get("title")) for m in matches],
            )
            continue
        url = _text(matches[0].get("url"))
        if not url:
            continue
        index[key] = EventDetails(
            source_url=url,
            price_text=_text(matches[0].get("cost")) or None,
            categories=_category_names(matches[0].get("categories")),
        )
    return index


def _is_non_music(summary: str, details: EventDetails | None = None) -> bool:
    """Whether this calendar entry is something other than a gig.

    **Tribe's categories first, the title only as a fallback.** The venue tags
    its own programming, which is a far better signal than reading the title —
    "Amy O\'Hair presents \'History Walks in Sunnyside\'" reads like a gig and
    is a talk. But categories can\'t be the whole answer: the two entries that
    prompted #124 ("closed for Thanksgiving", "Glen Park Night Market") have no
    Tribe event at all, so *absence* of a category must never be read as
    "not a show" — that would silently drop the ~8% of the calendar Tribe
    doesn\'t carry, including real gigs like the November Will Bernard date.

    So: a category decides it when there is one, and the keyword heuristic —
    knowingly imperfect, and now aware that the shop also posts closures and
    street fairs — handles everything else.
    """
    categories = details.categories if details is not None else frozenset()
    if categories & _MUSIC_CATEGORIES:
        return False
    if categories & _NON_MUSIC_CATEGORIES:
        return True
    lowered = summary.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _clean(text: str) -> str:
    """Collapse the whitespace artifacts iCal text tends to carry, without
    otherwise altering the venue's string (which becomes the display name)."""
    return " ".join(text.split())


def parse_ics(
    ics_text: str,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    details: DetailIndex | None = None,
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per timed musical event in
    ``[today, today + window_days]``, with recurring series expanded.

    ``today`` is injected (not read from the clock) and ``details`` is passed
    in rather than fetched, so the parser stays pure, network-free, and
    fixture-testable. ``details`` maps ``(date, start time)`` to the Tribe
    metadata for that slot; a show with no entry keeps the ``/events/``
    fallback and a null price, exactly as before this feed existed.
    """
    calendar = icalendar.Calendar.from_ical(ics_text)
    window_end = today + dt.timedelta(days=window_days)
    instances = recurring_ical_events.of(calendar).between(today, window_end)

    shows: list[ScrapedShow] = []
    for event in instances:
        start = event.get("DTSTART")
        if start is None:
            continue
        start_value = start.dt
        # Skip all-day (date-only) entries — not single timed performances.
        if not isinstance(start_value, dt.datetime):
            continue
        summary = _clean(str(event.get("SUMMARY", "")))
        if not summary:
            continue
        # Normalize to naive local time in the venue tz; ingest re-applies the
        # tz to derive start_utc. Expanded instances come back tz-aware (PT or
        # UTC) — convert before dropping tzinfo so UTC-stored events land right.
        if start_value.tzinfo is not None:
            local = start_value.astimezone(VENUE_TZ).replace(tzinfo=None)
        else:
            local = start_value
        # Tribe metadata for this slot, if the two feeds agree on the time.
        # Resolved before the music filter, which prefers the venue's own
        # categories over reading the title.
        matched = (details or {}).get((local.date(), local.time()))
        if _is_non_music(summary, matched):
            continue
        end = event.get("DTEND")
        end_local = None
        if end is not None and isinstance(end.dt, dt.datetime):
            end_value = end.dt
            end_local = (
                end_value.astimezone(VENUE_TZ).replace(tzinfo=None)
                if end_value.tzinfo is not None
                else end_value
            )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=summary,
                support_raw=[],
                start_local=local,
                end_local=end_local,
                doors_local=None,
                ticket_url=None,
                price_text=matched.price_text if matched else None,
                source_url=matched.source_url if matched else SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch both feeds for the next ~90 days and join them.

    The ``.ics`` is authoritative for what exists; Tribe only decorates it.
    A Tribe failure is therefore logged and swallowed — the show set must come
    back whole with ``/events/`` links rather than shrink.
    """
    today = dt.date.today()
    try:
        details = build_detail_index(fetch_event_details(today))
    except Exception:
        logger.warning(
            "bird_and_beckett: Tribe metadata fetch failed — falling back to %s "
            "for every show",
            SOURCE_URL,
            exc_info=True,
        )
        details = {}
    return parse_ics(fetch_ics(), today, details=details)


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
