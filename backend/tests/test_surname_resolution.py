"""Uniqueness-gated surname resolution (#125).

The safety property under test is the *refusal*: a surname borne by two known
people must never resolve, because a wrong attribution is a silent false
positive in a digest and costs trust in every other row. The live catalogue
doesn't happen to contain a shared-surname collision on a bare-surname bill
yet, so the important cases here are constructed.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from foghorn.ingest.pipeline import canonicalize, ingest_scraped_shows
from foghorn.ingest.surnames import build_index, is_person_shaped
from foghorn.models import Performer, ScrapedShow, Venue
from foghorn.repo import performers as performers_repo
from foghorn.repo import shows as shows_repo
from foghorn.repo.performer_match import matches_token_bag


def _add_performer(conn: sqlite3.Connection, display: str) -> Performer:
    return performers_repo.upsert(
        conn,
        Performer(display_name=display, canonical_name=canonicalize(display)),
    )


def _show(venue: Venue, headliner: str, day: int = 11) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw=headliner,
        support_raw=[],
        start_local=dt.datetime(2026, 9, day, 19, 0),
        source_url="https://example.test/",
    )


class TestPersonShaped:
    """Who gets into the index at all. A band admitted here can become the
    unique bearer of a surname and start attracting shows that aren't its."""

    @pytest.mark.parametrize(
        "canonical", ["lisa mezzacappa", "larry ochs", "ruth brown davies"]
    )
    def test_people(self, canonical: str) -> None:
        assert is_person_shaped(canonical)

    @pytest.mark.parametrize(
        "canonical",
        [
            "mezzacappa",  # one token — a bare surname, not a known person
            "lisa mezzacappa quintet",
            "the rob reich swings left legacy band featuring darren johnston",
            "ochs johnston mezzacappa davis",
            "scott foster combo featuring darren johnston",
            "lisa mezzacappa 5",  # digits mean a band name
        ],
    )
    def test_not_people(self, canonical: str) -> None:
        assert not is_person_shaped(canonical)


class TestIndex:
    def test_unique_surname_resolves(self, conn: sqlite3.Connection) -> None:
        _add_performer(conn, "Lisa Mezzacappa")
        assert build_index(conn).resolve("mezzacappa").canonical_name == (
            "lisa mezzacappa"
        )

    def test_shared_surname_refuses(self, conn: sqlite3.Connection) -> None:
        """The Davis case, and the whole reason matching wasn't loosened."""
        _add_performer(conn, "Miles Davis")
        _add_performer(conn, "Ben Davis")
        index = build_index(conn)
        assert index.resolve("davis") is None
        assert "davis" in index.ambiguous

    def test_unknown_surname_refuses(self, conn: sqlite3.Connection) -> None:
        _add_performer(conn, "Lisa Mezzacappa")
        assert build_index(conn).resolve("nobody") is None

    def test_a_surname_that_becomes_ambiguous_stops_resolving(
        self, conn: sqlite3.Connection
    ) -> None:
        """The property that makes this safe as the catalogue grows: adding a
        second bearer silently withdraws the inference rather than keeping a
        now-wrong one."""
        _add_performer(conn, "Lisa Mezzacappa")
        assert build_index(conn).resolve("mezzacappa") is not None
        _add_performer(conn, "Nick Mezzacappa")
        assert build_index(conn).resolve("mezzacappa") is None

    def test_band_billings_do_not_count_as_bearers(
        self, conn: sqlite3.Connection
    ) -> None:
        """Two billings that merely *end* in Johnston are not two Johnstons —
        counting them would block the correct resolution."""
        _add_performer(conn, "Darren Johnston")
        _add_performer(conn, "Scott Foster Combo featuring Darren Johnston")
        _add_performer(conn, "The Rob Reich Swings Left Legacy Band Featuring Darren Johnston")
        assert build_index(conn).resolve("johnston").canonical_name == (
            "darren johnston"
        )

    def test_same_person_twice_is_one_bearer(
        self, conn: sqlite3.Connection
    ) -> None:
        """Re-ingesting a name under a different display spelling must not
        look like two people."""
        _add_performer(conn, "Lisa Mezzacappa")
        _add_performer(conn, "LISA MEZZACAPPA")
        assert build_index(conn).resolve("mezzacappa") is not None


class TestEndToEnd:
    """The reported bug, reproduced through ingest and the real matcher."""

    def test_reported_case_now_matches_the_follow(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        # Lisa is known from her other four billings.
        _add_performer(conn, "Lisa Mezzacappa")

        result = ingest_scraped_shows(
            conn, venue, [_show(venue, "Ochs/Johnston/Mezzacappa/Davis")]
        )
        assert result.errors == []

        stored = shows_repo.get_by_natural_key(
            conn,
            venue.id or -1,
            "2026-09-11",
            "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert stored is not None

        follow = canonicalize("Lisa Mezzacappa")
        assert any(
            matches_token_bag(follow, p.canonical_name) for p in stored.performers
        ), [p.canonical_name for p in stored.performers]

    def test_display_string_is_untouched(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        """AGENTS.md → Conventions: the venue's billing is never rewritten."""
        _add_performer(conn, "Lisa Mezzacappa")
        ingest_scraped_shows(
            conn, venue, [_show(venue, "Ochs/Johnston/Mezzacappa/Davis")]
        )
        stored = shows_repo.get_by_natural_key(
            conn,
            venue.id or -1,
            "2026-09-11",
            "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert stored is not None
        headliner = next(p for p in stored.performers if p.role == "headliner")
        assert headliner.display_name == "Ochs/Johnston/Mezzacappa/Davis"
        assert stored.headliner_canonical == "ochs johnston mezzacappa davis"

    def test_shared_surname_produces_no_match(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        """A followed Miles Davis must NOT match the bare Davis on this bill.
        This is the false positive the whole design exists to prevent."""
        _add_performer(conn, "Miles Davis")
        _add_performer(conn, "Ben Davis")

        ingest_scraped_shows(
            conn, venue, [_show(venue, "Ochs/Johnston/Mezzacappa/Davis")]
        )
        stored = shows_repo.get_by_natural_key(
            conn,
            venue.id or -1,
            "2026-09-11",
            "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert stored is not None
        follow = canonicalize("Miles Davis")
        assert not any(
            matches_token_bag(follow, p.canonical_name) for p in stored.performers
        )

    def test_link_provenance_is_recorded(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        _add_performer(conn, "Lisa Mezzacappa")
        ingest_scraped_shows(
            conn, venue, [_show(venue, "Ochs/Johnston/Mezzacappa/Davis")]
        )
        stored = shows_repo.get_by_natural_key(
            conn,
            venue.id or -1,
            "2026-09-11",
            "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert stored is not None
        by_source = {p.source for p in stored.performers}
        assert by_source == {"billed", "parsed", "inferred"}
        inferred = [p for p in stored.performers if p.source == "inferred"]
        assert [p.canonical_name for p in inferred] == ["lisa mezzacappa"]

    def test_reingest_is_idempotent(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        _add_performer(conn, "Lisa Mezzacappa")
        show = _show(venue, "Ochs/Johnston/Mezzacappa/Davis")
        ingest_scraped_shows(conn, venue, [show])
        first = shows_repo.get_by_natural_key(
            conn, venue.id or -1, "2026-09-11", "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert first is not None
        ingest_scraped_shows(conn, venue, [show])
        second = shows_repo.get_by_natural_key(
            conn, venue.id or -1, "2026-09-11", "19:00",
            canonicalize("Ochs/Johnston/Mezzacappa/Davis"),
        )
        assert second is not None
        assert second.id == first.id  # no churn
        assert [(p.canonical_name, p.source) for p in second.performers] == [
            (p.canonical_name, p.source) for p in first.performers
        ]

    def test_ordinary_billing_gains_nothing(
        self, conn: sqlite3.Connection, venue: Venue
    ) -> None:
        """The 99% case must be untouched: one act, one link, billed."""
        ingest_scraped_shows(conn, venue, [_show(venue, "Lisa Mezzacappa Quintet")])
        stored = shows_repo.get_by_natural_key(
            conn, venue.id or -1, "2026-09-11", "19:00",
            canonicalize("Lisa Mezzacappa Quintet"),
        )
        assert stored is not None
        assert [(p.canonical_name, p.source) for p in stored.performers] == [
            ("lisa mezzacappa quintet", "billed")
        ]
