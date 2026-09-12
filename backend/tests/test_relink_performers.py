"""Backfill pass tests (#125).

The nightly scrape re-ingests upcoming shows, so it keeps them current. Past
shows never come back from a scraper, and they're precisely what makes a
surname *known* — so the catalogue needs a way to be re-walked. This is that
pass, and the properties that matter are convergence and idempotency.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from foghorn.cli.relink_performers import relink, relink_to_fixpoint
from foghorn.ingest.pipeline import canonicalize, ingest_scraped_shows
from foghorn.models import ScrapedShow, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo.performer_match import matches_token_bag


def _scraped(venue: Venue, billing: str, day: int) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw=billing,
        support_raw=[],
        start_local=dt.datetime(2026, 9, day, 19, 0),
        source_url="https://example.test/",
    )


def _ingest(conn: sqlite3.Connection, venue: Venue, billing: str, day: int) -> None:
    ingest_scraped_shows(conn, venue, [_scraped(venue, billing, day)])


def _ingest_batch(
    conn: sqlite3.Connection, venue: Venue, billings: list[tuple[str, int]]
) -> None:
    """One batch — and therefore one surname index, built before any of these
    billings has been parsed."""
    ingest_scraped_shows(
        conn, venue, [_scraped(venue, billing, day) for billing, day in billings]
    )


def _bill(conn: sqlite3.Connection, venue: Venue, billing: str, day: int):  # type: ignore[no-untyped-def]
    stored = shows_repo.get_by_natural_key(
        conn, venue.id or -1, f"2026-09-{day:02d}", "19:00", canonicalize(billing)
    )
    assert stored is not None
    return stored


def test_resolves_a_person_first_seen_in_the_same_batch(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    """Parsing a billing is what *creates* the person a later bare surname
    resolves to. Within one batch the surname index is a snapshot taken before
    any of it was parsed, so "Larry Ochs" doesn't exist yet when the bare
    "Ochs" on the sibling bill is looked up. A later pass closes the gap —
    which is why the backfill runs to a fixpoint rather than once."""
    _ingest_batch(
        conn,
        venue,
        [("Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10), ("Ochs/Vong", 11)],
    )

    before = _bill(conn, venue, "Ochs/Vong", 11)
    assert not any(
        p.canonical_name == "larry ochs" for p in before.performers
    ), "index snapshot should not have known Larry Ochs yet"

    _stats, passes = relink_to_fixpoint(conn)
    assert passes >= 2

    after = _bill(conn, venue, "Ochs/Vong", 11)
    inferred = {p.canonical_name for p in after.performers if p.source == "inferred"}
    assert "larry ochs" in inferred
    assert any(
        matches_token_bag(canonicalize("Larry Ochs"), p.canonical_name)
        for p in after.performers
    )


def test_a_separate_later_ingest_resolves_inline(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    """The common case needs no backfill at all: each ingest call rebuilds the
    index, so a bill scraped after the person is known resolves immediately."""
    _ingest(conn, venue, "Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10)
    _ingest(conn, venue, "Ochs/Vong", 11)
    stored = _bill(conn, venue, "Ochs/Vong", 11)
    assert "larry ochs" in {
        p.canonical_name for p in stored.performers if p.source == "inferred"
    }


def test_is_idempotent(conn: sqlite3.Connection, venue: Venue) -> None:
    _ingest(conn, venue, "Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10)
    _ingest(conn, venue, "Ochs/Vong", 11)
    relink_to_fixpoint(conn)

    settled = _bill(conn, venue, "Ochs/Vong", 11)
    stats = relink(conn)
    assert stats["shows_changed"] == 0
    again = _bill(conn, venue, "Ochs/Vong", 11)
    assert [(p.canonical_name, p.source) for p in again.performers] == [
        (p.canonical_name, p.source) for p in settled.performers
    ]


def test_never_changes_show_identity(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    """The regression guard: ids, natural keys and billing strings are the
    dedupe contract and the anchor for event_type_overrides."""
    _ingest(conn, venue, "Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10)
    _ingest(conn, venue, "Ochs/Vong", 11)
    before = [
        (row[0], row[1])
        for row in conn.execute("SELECT id, headliner_canonical FROM shows ORDER BY id")
    ]
    relink_to_fixpoint(conn)
    after = [
        (row[0], row[1])
        for row in conn.execute("SELECT id, headliner_canonical FROM shows ORDER BY id")
    ]
    assert before == after


def test_dry_run_writes_nothing(conn: sqlite3.Connection, venue: Venue) -> None:
    _ingest(conn, venue, "Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10)
    _ingest(conn, venue, "Ochs/Vong", 11)
    before = conn.execute("SELECT count(*) FROM show_performers").fetchone()[0]
    relink(conn, dry_run=True)
    assert conn.execute("SELECT count(*) FROM show_performers").fetchone()[0] == before


def test_ambiguity_introduced_later_is_not_retroactively_wrong(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    """A second Ochs makes the surname ambiguous. New resolutions stop; the
    already-recorded link stays until someone clears it, which is why the
    link carries `inferred` provenance rather than passing as billed."""
    _ingest(conn, venue, "Larry Ochs, Ben Davis, Darren Johnston, Kim Vong", 10)
    _ingest(conn, venue, "Ochs/Vong", 11)
    relink_to_fixpoint(conn)

    _ingest(conn, venue, "Phillip Ochs, Ann Kim, Bo Lin", 12)
    _ingest(conn, venue, "Ochs/Kim", 13)
    relink_to_fixpoint(conn)

    later = _bill(conn, venue, "Ochs/Kim", 13)
    assert not any(
        p.source == "inferred" and p.canonical_name.endswith("ochs")
        for p in later.performers
    )
