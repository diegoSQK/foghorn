"""Napa Music Hall scraper — via the Ticketmaster Discovery API.

The historic Napa Valley Opera House at 1030 Main Street. It housed **Blue Note
Napa** until that club closed on 31 December after ten years; the building was
rebranded Napa Music Hall, and the Blue Note name survives only as the summer
series at the Meritage (see ``blue_note_napa_summer_sessions``). Anyone
auditing coverage will look for "Blue Note Napa" and find a closed venue —
this is its successor, and the room that actually books music in downtown Napa.

**Two rooms, one building.** Discovery lists the main hall and "The Club at
Napa Music Hall" as separate venue ids at the same address. They share a venue
row and are told apart by ``room``, the same way SFJAZZ's Miner Auditorium and
Joe Henderson Lab do — different rooms, one place, so splitting them would buy
no filter precision while fragmenting a venue that genuinely is one address.

Shared parsing lives in ``_ticketmaster``; needs ``TM_API_KEY``. Both ids were
confirmed to carry real inventory, not just a venue record.

Runnable standalone: ``python -m foghorn.scrapers.napa_music_hall``.
"""

from __future__ import annotations

import datetime as dt
import json

from foghorn.models import ScrapedShow
from foghorn.scrapers._ticketmaster import fetch_events, parse_events

VENUE_SLUG = "napa_music_hall"

# TM venue id -> the room label stored on each show. The main hall carries no
# room: it *is* the venue to anyone standing outside, and a label that repeats
# the venue name is noise on every card.
TM_ROOMS: dict[str, str | None] = {
    "KovZ917AVdu": None,  # Napa Music Hall (main)
    "KovZ917AV1r": "The Club",  # The Club at Napa Music Hall
}


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    day = today or dt.date.today()
    shows: list[ScrapedShow] = []
    for venue_id, room in TM_ROOMS.items():
        parsed = parse_events(fetch_events(venue_id, day), VENUE_SLUG, day)
        # ScrapedShow is frozen, so the room is stamped via model_copy.
        shows.extend(s.model_copy(update={"room": room}) for s in parsed)
    shows.sort(key=lambda show: (show.start_local, show.headliner_raw))
    return shows


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
