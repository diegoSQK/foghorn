"""The Dawn Club scraper.

Source: the revived 1930s trad-jazz/swing club's **Squarespace events
collection** at ``dawnclub.com/music?format=json`` — the shared
``_squarespace_events`` core (pre-split ``upcoming`` array, epoch-ms
starts/ends, per-event pages). Programming is live jazz nightly; swing
dance classes are the one non-music admixture and drop on title signal.

Runnable standalone: ``python -m foghorn.scrapers.the_dawn_club`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from foghorn.models import ScrapedShow
from foghorn.scrapers import _squarespace_events as core

VENUE_SLUG = "the_dawn_club"
BASE_URL = "https://www.dawnclub.com"
CALENDAR_URL = f"{BASE_URL}/music"
EVENTS_JSON_URL = f"{CALENDAR_URL}?format=json"

_NON_MUSIC_RE = re.compile(
    r"\bclass\b|\blesson\b|\bworkshop\b|\bprivate event\b", re.IGNORECASE
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
