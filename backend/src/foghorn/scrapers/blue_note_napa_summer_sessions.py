"""Blue Note Napa Summer Sessions scraper — via the Ticketmaster Discovery API.

What's left of Blue Note Napa. The club at 1030 Main Street closed on 31
December after ten years (that address is now ``napa_music_hall``); the brand
continues as this seasonal series at the Meritage Resort, booking up to 40
shows a summer for audiences of ~3,000 — a different address, a different room
size, and only part of the year.

It gets its own venue row rather than being folded under a "Blue Note Napa"
heading, because the two aren't the same place: an August show here is 3.5
miles from the old club, outdoors, at a resort.

**The trap this venue is the poster child for.** Discovery has four records
matching "Blue Note Napa" and only this one carries events; the club's record
returns zero. Matching a venue by *name* would have quietly substituted a
summer series for a year-round jazz room — and, since the club has closed,
substituted an operating venue for a dead one. Ids here are confirmed by
querying for inventory.

Shared parsing lives in ``_ticketmaster``; needs ``TM_API_KEY``.

Runnable standalone: ``python -m foghorn.scrapers.blue_note_napa_summer_sessions``.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "blue_note_napa_summer_sessions"
TM_VENUE_ID = "KovZ917AmJ7"


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
