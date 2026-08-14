"""Stanford Live scraper — via Spektrix's public API.

Stanford Live is the university's presenting organisation: Bing Concert Hall,
Memorial Auditorium, Frost Amphitheater and the Studio. It's a *presenter* row
like Cal Performances, not a single room — the seed comment on
``stanford_jazz_workshop`` already flagged it as a separate, uncovered org.

**Source.** The site runs on Spektrix, whose public API needs the client's
short name. That isn't guessable — four plausible names 404'd when the same
question came up for the Freight — but the site hands it over in an inline
config: ``spektrix_base: 'https://ticketing.purchase.live.stanford.edu/
stanfordlive/'``. The client is ``stanfordlive``, reachable on either the
vanity host or ``system.spektrix.com``; this uses the canonical host.

    GET https://system.spektrix.com/stanfordlive/api/v3/events
    GET https://system.spektrix.com/stanfordlive/api/v3/instances

Unauthenticated, no key. Spektrix splits productions (``events``) from dated
performances (``instances``), joined on ``instance.event.id`` — so a run of
five nights is five instances against one event, and expansion is free.

**Two things the API does not give.** There's no venue on an instance (every
one is ``null``), so shows can't be routed to the room they play — everything
lands on the presenter row, and ``room`` stays empty. And ``webEventId`` is
unpopulated on all 171 events, so there's no per-event page to link; the
calendar is the honest provenance, and there's no ticket URL to offer.

Comedy is tagged from the source's own ``attribute_Genre``, never guessed.
Theater and Dance stay ordinary shows: the presenter books dance companies with
live music, and inventing a category per genre string would be worse than a
genre label that already rides along.

Runnable standalone: ``python -m foghorn.scrapers.stanford_live``.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from typing import Any

from foghorn.models import ScrapedShow

VENUE_SLUG = "stanford_live"
API_BASE = "https://system.spektrix.com/stanfordlive/api/v3"
CALENDAR_URL = "https://live.stanford.edu/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180
REQUEST_TIMEOUT = 40.0

# The source's own classification. Only comedy is promoted to an event type —
# it's the one non-music genre foghorn has a category for, and it arrives from
# a source that says so rather than from a title guess.
_COMEDY_GENRE = "comedy"


class StanfordLiveSourceError(RuntimeError):
    """The Spektrix API changed shape or refused the request."""


def _get(path: str) -> Any:
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise StanfordLiveSourceError(f"spektrix{path} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise StanfordLiveSourceError(f"spektrix unreachable: {exc.reason}") from exc
    except ValueError:
        raise StanfordLiveSourceError(f"spektrix{path} returned a non-JSON body") from None


def fetch_events_and_instances() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The production list and the dated-performance list, unfiltered."""
    events = _get("/events")
    instances = _get("/instances")
    if not isinstance(events, list) or not isinstance(instances, list):
        raise StanfordLiveSourceError("spektrix returned a non-list payload")
    return events, instances


def parse(
    events: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Join instances to their production and map them into shows.

    Pure — tests drive it from saved payloads. The API returns the whole
    catalogue including past seasons (2025 onward), so the window filter is
    load-bearing rather than a nicety.
    """
    by_id = {e.get("id"): e for e in events if isinstance(e, dict) and e.get("id")}
    horizon = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, str]] = set()

    for instance in instances:
        if not isinstance(instance, dict) or instance.get("cancelled"):
            continue
        event = by_id.get((instance.get("event") or {}).get("id"))
        if event is None:
            continue  # an instance with no production tells us nothing
        name = str(event.get("name") or "").strip()
        if not name:
            continue
        raw_start = instance.get("start")
        if not isinstance(raw_start, str):
            continue
        try:
            start_local = dt.datetime.fromisoformat(raw_start)
        except ValueError:
            continue
        start_local = start_local.replace(tzinfo=None)
        if not (today <= start_local.date() <= horizon):
            continue

        genre = event.get("attribute_Genre")
        genre_text = str(genre).strip() if isinstance(genre, str) and genre.strip() else None

        key = (start_local.isoformat(), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=name,
                start_local=start_local,
                doors_local=None,
                # The API exposes no per-instance web page or basket link.
                ticket_url=None,
                price_text=None,
                source_url=CALENDAR_URL,
                genre=genre_text,
                event_type=(
                    "comedy"
                    if genre_text and genre_text.casefold() == _COMEDY_GENRE
                    else None
                ),
            )
        )
    shows.sort(key=lambda show: (show.start_local, show.headliner_raw))
    return shows


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    day = today or dt.date.today()
    events, instances = fetch_events_and_instances()
    return parse(events, instances, day)


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
