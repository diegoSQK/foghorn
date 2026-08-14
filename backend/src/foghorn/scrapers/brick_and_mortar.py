"""Brick & Mortar Music Hall scraper — via the Ticketmaster Discovery API.

A 250-cap Mission indie room. Its own site is a WordPress shell whose
listings render client-side, but Ticketmaster is its box office, so the
Discovery API is first-party data through the sanctioned door.

Shared parsing lives in ``_ticketmaster``; needs ``TM_API_KEY`` in the
environment. The venue id was confirmed against the Discovery API by checking
for real *inventory*, not just a venue record — a venue can have several
records and only one that sells (see the Freight & Salvage and Blue Note Napa
notes in docs/SHIPPED.md).

Runnable standalone: ``python -m foghorn.scrapers.brick_and_mortar``.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "brick_and_mortar"
TM_VENUE_ID = "KovZpZAanJFA"


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
