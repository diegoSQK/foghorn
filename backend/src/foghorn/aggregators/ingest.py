"""Aggregator-event ingest: venue resolution, duplicate guard, quarantine.

The posture (decided July 2026): **quarantine-with-flag, watchlist bypass.**
Events at venues foghorn already tracks attribute to those venues (matched by
canonical-name token subset, plus a small alias map for community spellings);
everything else auto-creates a ``source='aggregator'`` venue that stays out
of the main UI until the long-tail toggle — or a pin — surfaces it.

Duplicate guard: aggregator titles are free-text blobs ("Lisa Mezzacappa Six
at the Back Room 8pm"), so the exact natural key can't collapse them against
venue-scraped rows. Before ingesting an event at a *tracked* venue, any
existing same-venue-same-date show whose headliner token-matches the blob
marks it a duplicate and it's skipped — the venue's own scraper is
authoritative.
"""

from __future__ import annotations

import sqlite3

from foghorn.aggregators.models import AggregatedEvent
from foghorn.ingest.pipeline import canonicalize, ingest_scraped_shows
from foghorn.models import IngestResult, ScrapedShow, Venue
from foghorn.repo import venues as venues_repo
from foghorn.repo.performer_match import matches_token_bag

# Community spellings → foghorn slugs, for names token-matching can't bridge.
VENUE_ALIASES: dict[str, str] = {
    "jazzschool": "california_jazz_conservatory",
    "the jazzschool": "california_jazz_conservatory",
    "california jazz conservatory": "california_jazz_conservatory",
    "cjc": "california_jazz_conservatory",
    "bird beckett": "bird_and_beckett",
    "back room": "the_back_room",
    "makeout room": "make_out_room",
}


def _strip_leading_the(canonical: str) -> str:
    return canonical[4:] if canonical.startswith("the ") else canonical


def resolve_venue(conn: sqlite3.Connection, event: AggregatedEvent) -> Venue:
    """Match the event's free-text venue name to an existing venue, else
    create a quarantined aggregator venue for it."""
    raw_canonical = canonicalize(event.venue_name_raw)
    needle = _strip_leading_the(raw_canonical)

    alias_slug = VENUE_ALIASES.get(raw_canonical) or VENUE_ALIASES.get(needle)
    if alias_slug is not None:
        aliased = venues_repo.get_by_slug(conn, alias_slug)
        if aliased is not None:
            return aliased

    existing = venues_repo.list_all(conn)
    # Exact canonical match first, then token-subset either direction
    # ("bird beckett" ⊆ "bird beckett books and records").
    for venue in existing:
        if _strip_leading_the(canonicalize(venue.name)) == needle:
            return venue
    if needle:  # token matching on an empty needle would be meaningless
        for venue in existing:
            venue_canonical = _strip_leading_the(canonicalize(venue.name))
            if matches_token_bag(needle, venue_canonical) or matches_token_bag(
                venue_canonical, needle
            ):
                return venue

    slug = raw_canonical.replace(" ", "_") or "unknown_venue"
    return venues_repo.upsert(
        conn,
        Venue(
            slug=slug,
            name=event.venue_name_raw,
            neighborhood=None,
            region=None,
            address=event.venue_address_raw,
            tz="America/Los_Angeles",
            website_url=None,
            calendar_url=event.source_url,
            genre=None,
            source="aggregator",
        ),
    )


def _is_duplicate(
    conn: sqlite3.Connection, venue: Venue, event: AggregatedEvent
) -> bool:
    """True when a venue-scraped/manual show that day already covers this
    aggregator blob (any existing headliner's tokens all appear in it)."""
    assert venue.id is not None
    rows = conn.execute(
        "SELECT headliner_canonical, source FROM shows "
        "WHERE venue_id = ? AND start_local_date = ?",
        (venue.id, event.start_local.strftime("%Y-%m-%d")),
    ).fetchall()
    blob = canonicalize(event.headliner_raw)
    for row in rows:
        if row["source"] == "aggregator":
            continue  # only defer to authoritative sources
        if matches_token_bag(row["headliner_canonical"], blob):
            return True
    return False


def ingest_aggregated_events(
    conn: sqlite3.Connection, events: list[AggregatedEvent], source_id: str
) -> IngestResult:
    """Resolve, dedupe, and persist one aggregator run. Returned counts ride
    the same ``IngestResult`` shape the scheduler records for venues (slug =
    ``aggregator:<source_id>``); duplicate skips aren't errors and aren't
    counted."""
    result = IngestResult(venue_slug=f"aggregator:{source_id}")
    for event in events:
        try:
            venue = resolve_venue(conn, event)
            if venue.source != "aggregator" and _is_duplicate(conn, venue, event):
                continue
            scraped = ScrapedShow(
                venue_slug=venue.slug,
                headliner_raw=event.headliner_raw,
                start_local=event.start_local,
                source_url=event.source_url,
            )
            sub = ingest_scraped_shows(conn, venue, [scraped], source="aggregator")
            result.created += sub.created
            result.updated += sub.updated
            result.errors.extend(sub.errors)
        except Exception as exc:  # isolate one bad event, keep the batch
            result.errors.append(f"{event.headliner_raw[:60]}: {exc}")
    return result
