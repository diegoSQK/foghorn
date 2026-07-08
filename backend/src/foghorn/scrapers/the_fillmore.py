"""The Fillmore scraper — via the Ticketmaster Discovery API.

The venue's own site is a Live Nation JS shell with no server-rendered event
data (see the July 2026 sweep + docs/spikes/ticketmaster-discovery/), but TM
*is* its box office, so the Discovery API is first-party data through a
sanctioned door. Shared parsing lives in _ticketmaster; needs
TM_API_KEY in the environment.

Runnable standalone: python -m foghorn.scrapers.the_fillmore.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "the_fillmore"
TM_VENUE_ID = "KovZpZAE6eeA"


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
