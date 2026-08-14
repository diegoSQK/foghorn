"""The Masonic scraper — via the Ticketmaster Discovery API.

The 3,300-cap Nob Hill theatre. Live Nation-operated, so like the
Fillmore and the Regency its site carries no server-rendered listings
and TM is the first-party source.

Shared parsing lives in ``_ticketmaster``; needs ``TM_API_KEY`` in the
environment. The venue id was confirmed against the Discovery API by checking
for real *inventory*, not just a venue record — a venue can have several
records and only one that sells (see the Freight & Salvage and Blue Note Napa
notes in docs/SHIPPED.md).

Runnable standalone: ``python -m foghorn.scrapers.the_masonic``.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "the_masonic"
TM_VENUE_ID = "KovZpZAJ6nlA"


def scrape() -> list[ScrapedShow]:
    today = dt.date.today()
    return parse_events(fetch_events(TM_VENUE_ID, today), VENUE_SLUG, today)


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
