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
authoritative. Events the aggregator flagged ``headliner_is_description``
(title is really the event's description) are likewise dropped at tracked
venues: the blob can't token-match anything, so it would always land beside
the scraper's rows as a garbage title.
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
    # Bay Improviser bills Freight & Salvage as "The Freight", which strips to
    # the canonical "freight" — and an aggregator-created venue *named* "The
    # Freight" strips to exactly that too. Since the exact-match pass runs
    # before token-subset, without this alias the quarantined row would keep
    # winning over the seeded "Freight & Salvage" (which only matches on
    # token-subset), splitting one room across two venues.
    "freight": "freight_and_salvage",
    "the freight": "freight_and_salvage",
    # Series → the venue that hosts them (long-tail audit, July 2026). Routes
    # future aggregator events to the promoted venue, where the duplicate
    # guard defers to its scraper.
    "west oakland sound series": "dresher_ensemble_studio",
    "cybersentics book club at gray area": "gray_area_art_and_technology",
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


# Billing words that don't identify *who* is playing. A venue bills the
# ensemble ("The Kasey Knudsen / Harvey Wainapel Quartet") while an aggregator
# lists the full personnel ("Kasey Knudsen, Harvey Wainapel, Jon Arkin, John
# Wiitala") — the two differ in exactly these words, so a raw token-bag subset
# test fails and the same show lands twice. Dropped from both sides before the
# comparison below.
_NON_IDENTIFYING = frozenset(
    {
        "the", "a", "an", "and", "with", "w", "featuring", "feat", "ft",
        "presents", "present", "plus",
        "duo", "trio", "quartet", "quintet", "sextet", "septet", "octet",
        "band", "group", "ensemble", "collective", "project", "orchestra",
    }
)


def _identifying(canonical: str) -> set[str]:
    """The tokens that actually name performers, noise words removed."""
    return {token for token in canonical.split() if token not in _NON_IDENTIFYING}


def _is_duplicate(
    conn: sqlite3.Connection, venue: Venue, event: AggregatedEvent
) -> bool:
    """True when a venue-scraped/manual show that day already covers this
    aggregator blob.

    Two passes: the original whole-token subset test, then a comparison of
    *identifying* tokens only, in either direction — which catches the common
    billing-shape mismatch (venue's ensemble name vs the aggregator's personnel
    list, and the reverse when the aggregator lists only the leader). Both
    sides must retain at least one identifying token, so a content-free billing
    ("The Quartet") can't collapse everything that night.
    """
    assert venue.id is not None
    rows = conn.execute(
        "SELECT headliner_canonical, source FROM shows "
        "WHERE venue_id = ? AND start_local_date = ?",
        (venue.id, event.start_local.strftime("%Y-%m-%d")),
    ).fetchall()
    blob = canonicalize(event.headliner_raw)
    blob_names = _identifying(blob)
    for row in rows:
        if row["source"] == "aggregator":
            continue  # only defer to authoritative sources
        existing = row["headliner_canonical"]
        if matches_token_bag(existing, blob):
            return True
        existing_names = _identifying(existing)
        if not existing_names or not blob_names:
            continue
        if existing_names <= blob_names or blob_names <= existing_names:
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
            if venue.source != "aggregator" and event.headliner_is_description:
                # A description-copy headliner can't token-match the venue
                # scraper's rows, so the duplicate guard never fires on it;
                # at a tracked venue the scraper is authoritative and the
                # blob would land beside its rows as a garbage title.
                continue
            if venue.source != "aggregator" and _is_duplicate(conn, venue, event):
                continue
            scraped = ScrapedShow(
                venue_slug=venue.slug,
                headliner_raw=event.headliner_raw,
                support_raw=event.support_raw,
                start_local=event.start_local,
                ticket_url=event.ticket_url,
                price_text=event.price_text,
                source_url=event.source_url,
            )
            sub = ingest_scraped_shows(conn, venue, [scraped], source="aggregator")
            result.created += sub.created
            result.updated += sub.updated
            result.errors.extend(sub.errors)
        except Exception as exc:  # isolate one bad event, keep the batch
            result.errors.append(f"{event.headliner_raw[:60]}: {exc}")
    return result
