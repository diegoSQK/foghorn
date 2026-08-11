"""SFJAZZ scraper — the calendar API behind sfjazz.org.

SFJAZZ is a **presenter**, not only a venue. It programs two rooms inside the
SFJAZZ Center (Miner Auditorium and the Joe Henderson Lab) and also books
off-site — the Paramount in Oakland, the UC Theatre, Davies, Grace Cathedral —
so this scraper routes each event to a venue off the API's ``location`` string
rather than assuming everything lands at ``sfjazz``. Without that, Snarky Puppy
would file under Hayes Valley instead of Uptown Oakland.

**Source.** The ``/calendar/`` page renders client-side from a Redux/RTK query
against an Adage "ace" endpoint, found in ``/Static/dist/calendar.js``:

    GET https://www.sfjazz.org/ace-api/events/?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

Unauthenticated, no nonce, no key. It returns the whole window in one request —
a year came back as 282 events — already one entry per performance, so
multi-night runs need no expansion. It carries the room, the full artist list
(which becomes the support bill, so the watchlist matches sidemen), ticket and
detail URLs, and sold-out state. It does *not* carry price; the per-production
HTML pages do, but that would cost ~300 fetches a night for a price string, so
``price_text`` stays ``None``.

**The client is load-bearing — do not "modernise" this to httpx.**
``sfjazz.org`` sits behind a Cloudflare managed challenge. Cloudflare
fingerprints TLS/HTTP client stacks, and ``httpx`` and ``curl`` are both
classified as bots and served ``403`` with ``cf-mitigated: challenge``, while
Python's stdlib ``urllib`` is served normally. Measured interleaved, same URL,
same polite UA, 2s apart: urllib ``[200, 200, 200, 200]``, httpx
``[403, 403, 403, 403]``. So this module deliberately uses ``urllib.request``
where every other scraper in the repo uses ``httpx``.

That choice is a considered one (Diego's call, recorded on #91), and the limits
of it matter:

* No challenge is solved and no authentication is bypassed — these are ordinary
  GETs of endpoints the site serves openly.
* ``robots.txt`` permits it. SFJAZZ disallows only ``/umbraco/``; the calendar
  and ticketing paths are explicitly crawlable.
* It is polite: one request per scrape for the whole window, a contactable UA.
* **It is fragile.** Cloudflare reclassifies client stacks routinely, so this
  can start returning 403s with no change on our side. That failure is loud —
  ``fetch_events`` raises and the venue shows as errored on the scrape-health
  surface rather than silently reporting an empty calendar.

Runnable standalone: ``python -m foghorn.scrapers.sfjazz`` prints the scraped
shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

from foghorn.models import ScrapedShow

logger = logging.getLogger("foghorn.scrapers.sfjazz")

VENUE_SLUG = "sfjazz"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://www.sfjazz.org"
API_URL = f"{BASE_URL}/ace-api/events/"
CALENDAR_URL = f"{BASE_URL}/calendar/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180
REQUEST_TIMEOUT = 45.0

# API `location` (casefolded) -> foghorn venue slug. SFJAZZ's own two rooms fold
# into one row, following the Davies/SoundBox precedent in seed_venues: same
# building, same neighborhood, so splitting them would buy no filter precision.
#
# The off-site entries are mapped but NOT ingested — see `scrape_center`. They
# are listed here so the unmapped-location warning stays meaningful: a location
# in this map is one we've looked at and made a decision about, so anything that
# warns is genuinely new programming worth a human glance.
# The two rooms inside the Center, canonicalised for display. The feed ships
# the Lab as both "Joe Henderson Lab" and "Joe Henderson lab"; a venue's rooms
# shouldn't render two ways, so the casing is pinned here rather than passed
# through verbatim.
_ROOM_LABELS = {
    "miner auditorium": "Miner Auditorium",
    "joe henderson lab": "Joe Henderson Lab",
}

_LOCATION_SLUGS = {
    "miner auditorium": VENUE_SLUG,
    "joe henderson lab": VENUE_SLUG,  # the feed also spells this "Joe Henderson lab"
    "paramount theatre, oakland": "paramount_theatre_oakland",
    "uc theatre, berkeley": "uc_theatre",
    "davies symphony hall": "davies_symphony_hall",
    # Grace Cathedral has no foghorn venue row and no scraper of its own, so
    # this one SFJAZZ date is currently the only thing that would populate it.
    # Mapped-but-unseeded on purpose: not worth a venue row for a single
    # booking, and revisit if SFJAZZ starts programming there regularly.
    "grace cathedral": "grace_cathedral",
}
# Streamed programming — real events, but not local shows anyone can attend.
# `location == "SFJAZZ At Home"` and `isStreamingEvent` agree exactly (16/16
# over a year), so either alone would do; both are checked.
_STREAMING_LOCATION = "sfjazz at home"

# eventTypes that mean "not a concert". "Education" is deliberately *not* here:
# it tags the family matinees too, which are real shows, so it only disqualifies
# an event when it stands alone.
_NON_SHOW_TYPES = frozenset({"classes & workshops", "digital lab"})
_LECTURE_ONLY_TYPES = frozenset({"education"})

# ...and even a bare "Education" tag isn't decisive, because SFJAZZ files its
# monthly **SFJAM free community jam session** under it — nine dates a year, and
# every single bare-Education event in the feed is one. A jam at a jazz room is
# the "bring your horn" case foghorn's event_type exists for, so these are kept
# and tagged rather than swept up with the classes. The ingest's own inference
# would catch "jam session" too; tagging explicitly keeps the intent visible and
# survives a rename to something its regex doesn't know.
_JAM_RE = re.compile(r"\bjam\s+session\b|\bsfjam\b|\bopen\s+mic\b", re.IGNORECASE)

_TAG_RE = re.compile(r"<[^>]+>")


class SFJazzSourceError(RuntimeError):
    """The source changed shape, or the client is being challenged again."""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", text))).strip()


def fetch_events(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Fetch the forward window in a single request.

    Uses ``urllib`` deliberately — see the module docstring. A challenge shows
    up as an ``HTTPError`` here and is re-raised as ``SFJazzSourceError`` so the
    scrape-health surface reports the venue as broken rather than empty.
    """
    end = today + dt.timedelta(days=window_days)
    url = f"{API_URL}?startDate={today.isoformat()}&endDate={end.isoformat()}"
    # This header set is load-bearing and was arrived at empirically; both
    # halves were verified reproducible against the live endpoint.
    #
    #   UA + Accept              -> 200
    #   UA + Accept + Referer    -> 403 cf-mitigated: challenge
    #   UA, no Accept            -> 403 cf-mitigated: challenge
    #
    # So an explicit Accept is *required*, and sending a Referer is *fatal* —
    # the opposite of the usual "look more like a browser" instinct, and the
    # opposite of what the other scrapers in this repo do. Don't add headers
    # here without re-measuring.
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        mitigation = exc.headers.get("cf-mitigated", "") if exc.headers else ""
        if exc.code == 403 and mitigation == "challenge":
            raise SFJazzSourceError(
                "sfjazz.org served a Cloudflare challenge — the client stack is being "
                "fingerprinted as a bot again; see this module's docstring"
            ) from exc
        raise SFJazzSourceError(f"ace-api/events returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SFJazzSourceError(f"ace-api/events unreachable: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except ValueError:
        raise SFJazzSourceError("ace-api/events returned a non-JSON body") from None
    if not isinstance(payload, list):
        raise SFJazzSourceError(
            f"ace-api/events returned {type(payload).__name__}, expected a list"
        )
    events: list[dict[str, Any]] = payload
    return events


def venue_slug_for(location: str) -> str | None:
    """Route an event to a venue slug. ``None`` = deliberately not ingested."""
    key = _clean(location).casefold()
    if not key or key == _STREAMING_LOCATION:
        return None
    return _LOCATION_SLUGS.get(key)


def _is_jam(name: str) -> bool:
    return bool(_JAM_RE.search(name))


def _is_show(event: dict[str, Any], name: str) -> bool:
    if event.get("isStreamingEvent") or event.get("hideFromCalendar"):
        return False
    types = {str(t).casefold() for t in (event.get("eventTypes") or [])}
    if types & _NON_SHOW_TYPES:
        return False
    # A bare "Education" tag is the class programme — except for the SFJAM
    # community jams, which carry nothing else. Family matinees pair it with
    # "Family Events", and plain concerts sometimes carry no type at all.
    if types == _LECTURE_ONLY_TYPES:
        return _is_jam(name)
    return True


def _start_local(event: dict[str, Any]) -> dt.datetime | None:
    """Naive venue-local start. ``eventDate`` is ISO-8601, usually with a
    ``-07:00`` offset but not always (26 of 282 omit it over a year) — both
    forms are already venue-local, so the offset is simply dropped."""
    raw = event.get("eventDate")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def _absolute(url: Any) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    stripped = url.strip()
    if stripped.startswith("http"):
        return stripped
    return f"{BASE_URL}{stripped}" if stripped.startswith("/") else None


def _support(event: dict[str, Any], headliner: str) -> list[str]:
    """The billed act's personnel, minus the act's own name.

    The API lists every named performer, so a trio's sidemen become support
    rows — which is what makes the watchlist able to follow a player across
    the bands they sit in.
    """
    headliner_key = headliner.casefold()
    support: list[str] = []
    seen: set[str] = set()
    for artist in event.get("artists") or []:
        name = _clean(str(artist))
        key = name.casefold()
        if not name or key == headliner_key or key in seen:
            continue
        seen.add(key)
        support.append(name)
    return support


def parse_events(
    events: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Turn API events into shows, routed to the venue each one plays.

    Pure — the tests drive it from a saved payload. Events at locations the map
    doesn't know are dropped with a warning rather than raising: SFJAZZ books
    the odd one-off room, and losing one show is a better failure than losing
    the other 180 in the window.
    """
    horizon = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, str, str]] = set()
    unmapped: set[str] = set()

    for event in events:
        headliner = _clean(str(event.get("name") or ""))
        if not headliner or not _is_show(event, headliner):
            continue
        location = _clean(str(event.get("location") or ""))
        venue_slug = venue_slug_for(location)
        if venue_slug is None:
            if location and location.casefold() != _STREAMING_LOCATION:
                unmapped.add(location)
            continue

        start_local = _start_local(event)
        if start_local is None or not (today <= start_local.date() <= horizon):
            continue

        source_url = _absolute(event.get("viewDetailCtaUrl")) or CALENDAR_URL
        ticket_url = None if event.get("isSoldOut") else _absolute(event.get("buyTicketCtaUrl"))

        key = (venue_slug, start_local.isoformat(), headliner.casefold())
        if key in seen:
            continue
        seen.add(key)
        shows.append(
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=headliner,
                support_raw=_support(event, headliner),
                start_local=start_local,
                doors_local=None,
                ticket_url=ticket_url,
                # The API publishes no price; only the per-production HTML
                # pages do, at ~300 extra fetches a night.
                price_text=None,
                source_url=source_url,
                event_type="jam" if _is_jam(headliner) else None,
                # Both Center rooms share the `sfjazz` row, so without this the
                # 700-seat hall and the 100-seat club are indistinguishable —
                # and since 38% of programmed nights run both, the venue reads
                # as double-booking itself. Only set for the rooms that share a
                # venue row; an off-site booking's "room" is its own venue.
                room=_ROOM_LABELS.get(location.casefold()) if venue_slug == VENUE_SLUG else None,
            )
        )

    if unmapped:
        logger.warning(
            "sfjazz.unmapped_locations",
            extra={"locations": sorted(unmapped)},
        )
    shows.sort(key=lambda show: (show.start_local, show.venue_slug, show.headliner_raw))
    return shows


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    """Fetch and parse every SFJAZZ-presented show in the forward window,
    across all the rooms SFJAZZ books."""
    day = today or dt.date.today()
    return parse_events(fetch_events(day), day)


def scrape_center() -> list[ScrapedShow]:
    """The SFJAZZ Center's own rooms — and the *only* thing registered.

    This filter is a safety property, not tidiness. The nightly runner ingests a
    registered scraper's whole output against that one venue with ``prune=True``,
    which reaps rows the run didn't return across the span it covered. SFJAZZ's
    feed is authoritative for its own building, but for the Paramount it lists
    only the two nights SFJAZZ presents there — so registering this scraper
    under ``paramount_theatre_oakland`` would reap every *other* Paramount show
    in that span, wiping out the Paramount's own scraper's work.

    Off-site SFJAZZ dates therefore arrive through the host venue's own scraper,
    where they already do: Snarky Puppy's Paramount date is in foghorn today via
    ``scrapers/paramount_theatre_oakland``, with a natural key
    ``(venue, date, time, headliner)`` identical to what this feed reports.
    """
    return [show for show in scrape() if show.venue_slug == VENUE_SLUG]


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
