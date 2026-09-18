"""Off-site drops are countable and visible (#129).

`scrape_center()` drops SFJAZZ's off-site dates for a good reason, and its
docstring's justification — that those dates "arrive through the host venue's
own scraper" — was an unchecked assumption. It held for the Paramount and the
UC Theatre and failed for Davies, and the show that fell through appeared
nowhere. These tests pin the telemetry, not a behaviour change: what gets
ingested is identical before and after.
"""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import diagnostics, sfjazz

TODAY = dt.date(2026, 9, 18)


def _show(slug: str, name: str, day: int = 19) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=slug,
        headliner_raw=name,
        support_raw=[],
        start_local=dt.datetime(2026, 10, day, 20, 0),
        source_url="https://www.sfjazz.org/calendar/",
    )


BILL = [
    _show("sfjazz", "In-House Quartet", 1),
    _show("sfjazz", "Another In-House Act", 2),
    _show("paramount_theatre_oakland", "Snarky Puppy", 3),
    _show("davies_symphony_hall", "Julian Lage Quartet", 19),
    _show("davies_symphony_hall", "Another Davies Rental", 20),
    _show("grace_cathedral", "A Cathedral Date", 21),
]


class TestDropTally:
    def test_counts_by_host(self) -> None:
        assert sfjazz.offsite_drops(BILL) == {
            "davies_symphony_hall": 2,
            "grace_cathedral": 1,
            "paramount_theatre_oakland": 1,
        }

    def test_in_house_shows_are_not_drops(self) -> None:
        assert sfjazz.offsite_drops(
            [_show("sfjazz", "Only In-House")]
        ) == {}

    def test_empty_bill(self) -> None:
        assert sfjazz.offsite_drops([]) == {}


class TestScraperlessHosts:
    def test_separates_hosts_nothing_else_covers(self) -> None:
        """A Paramount date is fine — the Paramount's own scraper lists it. A
        Grace Cathedral date is a show foghorn simply loses."""
        uncovered = sfjazz.hosts_without_a_scraper(
            ["paramount_theatre_oakland", "grace_cathedral", "davies_symphony_hall"]
        )
        assert "grace_cathedral" in uncovered
        assert "paramount_theatre_oakland" not in uncovered

    def test_a_registered_host_is_covered(self) -> None:
        from foghorn.scrapers import REGISTERED_SCRAPERS

        assert "paramount_theatre_oakland" in REGISTERED_SCRAPERS
        assert sfjazz.hosts_without_a_scraper(["paramount_theatre_oakland"]) == []


class TestReporting:
    def test_note_names_every_host_and_flags_the_uncovered(self) -> None:
        diagnostics.reset()
        sfjazz._report_offsite(sfjazz.offsite_drops(BILL))
        notes = diagnostics.drain()
        assert len(notes) == 1
        note = notes[0]
        assert "4 off-site date(s) not ingested" in note
        assert "davies_symphony_hall 2" in note
        assert "grace_cathedral 1" in note
        assert "paramount_theatre_oakland 1" in note
        # The Paramount is covered, so it must not appear in the "lost" half.
        lost_half = note.split("no scraper covers", 1)[1]
        assert "grace_cathedral" in lost_half
        assert "paramount_theatre_oakland" not in lost_half

    def test_had_this_existed_the_davies_date_would_have_shown(self) -> None:
        """The ticket's acceptance, stated literally."""
        diagnostics.reset()
        sfjazz._report_offsite(
            sfjazz.offsite_drops([_show("davies_symphony_hall", "Julian Lage Quartet")])
        )
        note = diagnostics.drain()[0]
        assert "davies_symphony_hall 1" in note
        # Davies has no scraper of its own (its rentals arrive via the War
        # Memorial aggregator), so it is reported as uncovered.
        assert "no scraper covers" in note

    def test_no_note_when_nothing_was_dropped(self) -> None:
        diagnostics.reset()
        sfjazz._report_offsite({})
        assert diagnostics.drain() == []

    def test_also_logs_structurally(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="foghorn.scrapers.sfjazz"):
            sfjazz._report_offsite(sfjazz.offsite_drops(BILL))
        assert "sfjazz.offsite_dropped" in caplog.text


class TestIngestIsUnchanged:
    def test_scrape_center_still_returns_only_in_house(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Observability-only: the ticket requires the show count for the
        window to be identical before and after."""
        monkeypatch.setattr(sfjazz, "scrape", lambda *a, **k: list(BILL))
        diagnostics.reset()
        kept = sfjazz.scrape_center()
        assert [s.headliner_raw for s in kept] == [
            "In-House Quartet",
            "Another In-House Act",
        ]
        assert all(s.venue_slug == "sfjazz" for s in kept)

    def test_scrape_center_reports_while_filtering(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sfjazz, "scrape", lambda *a, **k: list(BILL))
        diagnostics.reset()
        sfjazz.scrape_center()
        assert "4 off-site date(s) not ingested" in diagnostics.drain()[0]


class TestDiagnosticsChannel:
    def test_note_outside_a_run_is_a_noop(self) -> None:
        """A scraper run standalone or from a test needs no setup."""
        diagnostics.drain()  # ensure not collecting
        diagnostics.note("ignored")
        assert diagnostics.drain() == []

    def test_drain_stops_collecting(self) -> None:
        diagnostics.reset()
        diagnostics.note("one")
        assert diagnostics.drain() == ["one"]
        diagnostics.note("after drain")
        assert diagnostics.drain() == []

    def test_reset_clears_previous_notes(self) -> None:
        diagnostics.reset()
        diagnostics.note("stale")
        diagnostics.reset()
        assert diagnostics.drain() == []
