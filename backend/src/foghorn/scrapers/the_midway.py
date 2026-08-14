"""The Midway scraper — via the Ticketmaster Discovery API.

The 40,000 sq ft Dogpatch complex. It sells through several platforms at
once (Eventbrite, SeeTickets, Tixr all appear on its site); TM is the one
with a clean API, and carries the ticketed music programming.

Shared parsing lives in ``_ticketmaster``; needs ``TM_API_KEY`` in the
environment. The venue id was confirmed against the Discovery API by checking
for real *inventory*, not just a venue record — a venue can have several
records and only one that sells (see the Freight & Salvage and Blue Note Napa
notes in docs/SHIPPED.md).

Runnable standalone: ``python -m foghorn.scrapers.the_midway``.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "the_midway"
TM_VENUE_ID = "KovZ917AiWC"


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
