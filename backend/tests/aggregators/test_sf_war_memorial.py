"""War Memorial licensee-calendar parser tests (#128).

The fixture is eleven real booking records captured from the live calendar on
2026-09-18, trimmed to the fields the parser reads and chosen to hit every
branch: one music event per public hall, a presenter foghorn already covers,
a dance/ceremony/talk booking, both kinds of Film, and a back-of-house room.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.aggregators import sf_war_memorial as wm
from foghorn.aggregators.models import AggregatedEvent

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "sf_war_memorial_calendar.json"
)


@pytest.fixture
def records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def events(records: list[dict]) -> list[AggregatedEvent]:
    return wm.parse_events(records)


def _billings(events: list[AggregatedEvent]) -> set[str]:
    return {event.headliner_raw for event in events}


class TestTheReportedGap:
    """The show that motivated the ticket: an SFJAZZ rental at Davies, which
    neither SFJAZZ's own scraper (drops off-site) nor the Symphony feed
    (publishes only its own season) could see."""

    def test_julian_lage_is_parsed(self, events: list[AggregatedEvent]) -> None:
        lage = next(e for e in events if "LAGE" in e.headliner_raw.upper())
        assert lage.start_local == dt.datetime(2026, 10, 19, 20, 0)
        assert lage.venue_name_raw == "Davies Symphony Hall"
        assert lage.ticket_url == (
            "https://www.sfjazz.org/tickets/productions/26-27/julian-lage-quartet/"
        )


class TestHallRouting:
    def test_every_public_hall_is_named_as_foghorn_names_it(
        self, events: list[AggregatedEvent]
    ) -> None:
        """The booking system's labels don't token-match foghorn's venue
        names ("Davies Hall Stage" vs "Davies Symphony Hall"), so the mapping
        is explicit and resolution takes the exact-match path."""
        assert {e.venue_name_raw for e in events} == {
            "Davies Symphony Hall",
            "Herbst Theatre",
            "War Memorial Opera House",
            "Atrium Theater at the Wilsey Center",
        }

    def test_back_of_house_rooms_are_skipped(
        self, events: list[AggregatedEvent]
    ) -> None:
        """The Green Room and Zellerbach Rehearsal Hall carry receptions and
        rehearsals; letting them through would auto-create quarantined venues
        full of noise."""
        assert not any("Green Room" in e.venue_name_raw for e in events)
        assert "JULIA MORGAN AWARDS" not in _billings(events)

    def test_unmapped_hall_is_logged_not_silently_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger=wm.__name__):
            assert wm.parse_events(
                [
                    {
                        "venue_name": "Some New Room",
                        "genre": "Music",
                        "activity_detail": "A BAND",
                        "date_time": "2026-10-19 20:00:00",
                    }
                ]
            ) == []
        assert "unmapped hall" in caplog.text


class TestMusicFilter:
    def test_music_and_opera_are_kept(self, events: list[AggregatedEvent]) -> None:
        assert "THE BARBER OF SEVILLE" in _billings(events)
        assert any("ONENESS EXPERIENCE" in b for b in _billings(events))

    @pytest.mark.parametrize(
        "billing",
        [
            "BRAVO BASH: A TUTU TALE UNTANGLED Shows",  # Dance
            "UCSF SCHOOL OF MEDICINE WHITE COAT CEREMONY",  # Ceremony
            "INSIDE MUSIC TALK",  # Speaking Engagement
            "46th ANNUAL SFJFF OPENING NIGHT",  # a plain film screening
        ],
    )
    def test_non_music_bookings_are_dropped(
        self, events: list[AggregatedEvent], billing: str
    ) -> None:
        assert not any(b.startswith(billing[:24]) for b in _billings(events))

    def test_film_with_live_orchestra_is_music(
        self, events: list[AggregatedEvent]
    ) -> None:
        """The one genre the calendar's own facet can't settle: "Film" covers
        both screenings and live-orchestra performances, and the latter are
        exactly the kind of rental this source exists to surface."""
        assert any("HARRY POTTER" in b for b in _billings(events))

    @pytest.mark.parametrize(
        "detail,expected",
        [
            ("HARRY POTTER AND THE DEATHLY HALLOWS™ PART 2 IN CONCERT", True),
            ("WEST SIDE STORY FILM with SYMPHONY", True),
            ("SOME FILM with live orchestra", True),
            ("46th ANNUAL SFJFF OPENING NIGHT", False),
            ("FILM SCREENING: DIRTY DANCING", False),
            ("LOST LANDSCAPES 2026", False),
        ],
    )
    def test_film_live_performance_signal(self, detail: str, expected: bool) -> None:
        assert wm.is_music({"genre": "Film", "activity_detail": detail}) is expected


class TestCoveredPresenters:
    def test_symphony_dates_defer_to_the_symphony_feed(
        self, events: list[AggregatedEvent]
    ) -> None:
        """Measured on live data: 19 of the Symphony's dates here carry a
        different billing from the same date+time row the Symphony feed
        already produced, and `ingest._is_duplicate` deliberately doesn't
        dedupe one aggregator against another — so they'd land as visible
        duplicates. Dropping them at the source is the fix."""
        assert not any("YO-YO MA" in b for b in _billings(events))
        assert "San Francisco Symphony" in wm.COVERED_PRESENTERS

    def test_other_presenters_are_kept(self, events: list[AggregatedEvent]) -> None:
        """SF Opera has no other foghorn source, so its season is new
        coverage rather than a duplicate."""
        assert "THE BARBER OF SEVILLE" in _billings(events)


class TestExtraction:
    def test_reads_the_embedded_array(self) -> None:
        page = 'junk <script>var eventsData=[{"a":1},{"b":2}];</script> more'
        assert wm.extract_events_data(page) == [{"a": 1}, {"b": 2}]

    def test_missing_array_reports_zero_rather_than_raising(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A layout change should make this source report nothing on the
        nightly run, not abort it."""
        import logging

        with caplog.at_level(logging.WARNING, logger=wm.__name__):
            assert wm.extract_events_data("<html>no events here</html>") == []
        assert "no eventsData" in caplog.text

    def test_malformed_json_reports_zero(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger=wm.__name__):
            assert wm.extract_events_data("var eventsData=[{oops};") == []


class TestRecordHygiene:
    def test_rows_without_a_billing_or_time_are_dropped(self) -> None:
        assert wm.parse_events(
            [
                {"venue_name": "Herbst Theatre", "genre": "Music",
                 "activity_detail": "", "date_time": "2026-10-19 20:00:00"},
                {"venue_name": "Herbst Theatre", "genre": "Music",
                 "activity_detail": "A BAND", "date_time": "not-a-time"},
            ]
        ) == []

    def test_events_are_chronological(self, events: list[AggregatedEvent]) -> None:
        assert [e.start_local for e in events] == sorted(
            e.start_local for e in events
        )

    def test_presenter_is_not_put_on_the_bill(
        self, events: list[AggregatedEvent]
    ) -> None:
        """A presenter is a promoter, not a performer — SFJAZZ doesn't play
        the Julian Lage date. Group feeds put their *ensemble* in support_raw
        because there the presenter really is on stage; here that would
        pollute performer matching."""
        assert all(e.support_raw == [] for e in events)
