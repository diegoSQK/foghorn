"""Pier 23 Cafe scraper.

Source: the Embarcadero waterfront fixture's **Squarespace events
collection** at ``pier23cafe.com/events?format=json`` — the shared
``_squarespace_events`` core. Jazz trios on weekdays, the Sunday Blues Jam
(typed jam on title signal), and dance parties; non-music bar programming
(mahjong, trivia, private events) drops on title signal.

Runnable standalone: ``python -m foghorn.scrapers.pier_23_cafe`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from foghorn.models import ScrapedShow
from foghorn.scrapers import _squarespace_events as core

VENUE_SLUG = "pier_23_cafe"
BASE_URL = "https://www.pier23cafe.com"
CALENDAR_URL = f"{BASE_URL}/events"
EVENTS_JSON_URL = f"{CALENDAR_URL}?format=json"

_NON_MUSIC_RE = re.compile(
    r"\bmahjong\b|\btrivia\b|\bbingo\b|\bkaraoke\b|\bprivate event\b"
    r"|\bwatch party\b",
    re.IGNORECASE,
)
_JAM_RE = re.compile(r"\bjam\b|\bopen mic\b", re.IGNORECASE)


def parse_items(
    payload: dict[str, object], today: dt.date
) -> list[ScrapedShow]:
    return core.parse_items(
        payload,
        today,
        venue_slug=VENUE_SLUG,
        base_url=BASE_URL,
        calendar_url=CALENDAR_URL,
        non_music_re=_NON_MUSIC_RE,
        jam_re=_JAM_RE,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    return parse_items(core.fetch_collection(EVENTS_JSON_URL), dt.date.today())


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
