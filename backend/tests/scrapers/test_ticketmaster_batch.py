"""The Ticketmaster-ticketed venue batch (August 2026).

These adapters are ~30 lines each over the shared ``_ticketmaster`` parser,
which has its own fixture-driven tests. What can actually go wrong here is
wiring: a slug that doesn't match a seeded venue, a copy-pasted venue id, or a
scraper that never got registered. That's what this covers, plus the parser
being handed each venue's own slug.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed
from foghorn.scrapers import (
    REGISTERED_SCRAPERS,
    brick_and_mortar,
    mountain_winery,
    the_masonic,
    the_midway,
)
from foghorn.scrapers._ticketmaster import parse_events

BATCH = [brick_and_mortar, mountain_winery, the_masonic, the_midway]
FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "ticketmaster_fillmore_2026_07.json"
)


def test_every_adapter_is_registered() -> None:
    for module in BATCH:
        assert REGISTERED_SCRAPERS.get(module.VENUE_SLUG) is module.scrape, (
            f"{module.VENUE_SLUG} is not wired into REGISTERED_SCRAPERS"
        )


def test_every_adapter_has_a_seeded_venue(conn: sqlite3.Connection) -> None:
    # The runner logs "no seeded venue for slug" and ingests nothing otherwise —
    # a silent zero rather than an error, which is the failure this catches.
    seed(conn)
    for module in BATCH:
        venue = venues_repo.get_by_slug(conn, module.VENUE_SLUG)
        assert venue is not None, f"{module.VENUE_SLUG} is not seeded"
        assert venue.region is not None
        assert venue.calendar_url != "TBD"


def test_venue_ids_are_distinct_and_well_formed() -> None:
    # Guards the copy-paste failure: four adapters built from one template.
    ids = [m.TM_VENUE_ID for m in BATCH]
    assert len(set(ids)) == len(ids), f"duplicate TM venue id in {ids}"
    assert all(i.startswith("Kov") and len(i) > 8 for i in ids)


def test_slugs_are_distinct() -> None:
    slugs = [m.VENUE_SLUG for m in BATCH]
    assert len(set(slugs)) == len(slugs)


def _event(name: str, segment: str | None, genre: str | None = None) -> dict[str, Any]:
    cls: dict[str, Any] = {}
    if segment is not None:
        cls["segment"] = {"name": segment}
    if genre is not None:
        cls["genre"] = {"name": genre}
    return {
        "name": name,
        "classifications": [cls] if cls else [],
        "dates": {"start": {"localDate": "2026-07-02", "localTime": "20:00:00"}},
    }


def test_comedy_is_categorised_not_dropped() -> None:
    """The Masonic's calendar is a third stand-up.

    It used to be discarded. It's now ``event_type="comedy"`` — a busy Friday
    is worth knowing even when the reason isn't a band, and a category can be
    filtered out while a dropped row can't be recovered. Depth lives in
    tests/test_comedy_event_type.py; this pins the batch's own behaviour.

    "Undefined" stays music on purpose: TM leaves a sixth of the Regency's real
    gigs unclassified, so re-labelling those would be worse than the gap.
    """
    payload = {
        "_embedded": {
            "events": [
                _event("CHELSEA HANDLER: THE HIGH AND MIGHTY TOUR", "Arts & Theatre", "Comedy"),
                _event("John Mulaney", "Arts & Theatre"),
                _event("Some Band", "Music", "Rock"),
                _event("Unclassified Gig", "Undefined"),
                _event("No Classification At All", None),
            ]
        }
    }
    shows = parse_events(payload, "x", dt.date(2026, 7, 1))
    by_name = {s.headliner_raw: s.event_type for s in shows}
    assert len(by_name) == 5, "nothing is dropped any more"
    assert by_name["CHELSEA HANDLER: THE HIGH AND MIGHTY TOUR"] == "comedy"
    assert by_name["John Mulaney"] == "comedy"
    assert by_name["Some Band"] is None
    assert by_name["Unclassified Gig"] is None
    assert by_name["No Classification At All"] is None


@pytest.mark.parametrize("module", BATCH, ids=lambda m: m.VENUE_SLUG)
def test_parser_is_handed_this_venues_slug(module: Any) -> None:
    """Each adapter must stamp its *own* slug on the shows it returns.

    Ingest routes on the venue the runner passes, so a wrong slug here wouldn't
    misfile shows — but it would make the standalone output lie about where a
    show is, which is what anyone debugging reads first.
    """
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shows = parse_events(payload, module.VENUE_SLUG, dt.date(2026, 7, 1))
    assert shows, "shared fixture should yield shows"
    assert {s.venue_slug for s in shows} == {module.VENUE_SLUG}
