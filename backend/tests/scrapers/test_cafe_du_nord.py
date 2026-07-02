"""Tests for the Cafe du Nord HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/cafe_du_nord_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` page exercising the deployment's quirks — a row duplicated
inside the site's email-signup popup, hidden ``tw-event-dialog`` popups
carrying full dates/doors/prices, a "Private Event" placeholder, a same-day
pair (one show at the attached Swedish American Hall), an event with no
ticket link and an empty popup price, an out-of-window December show, and the
pagination block ``scrape`` follows.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import cafe_du_nord
from foghorn.scrapers._ticketweb_calendar import find_next_page_url

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cafe_du_nord_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return cafe_du_nord.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-07T20:00:00", "The Psycodelics"),
        ("2026-07-09T20:00:00", "ATTA BOY"),
        ("2026-07-14T20:00:00", "Brotherkenzie"),  # same day, Cafe du Nord room
        ("2026-07-14T20:00:00", "Friendlyjordies"),  # same day, Swedish American Hall
    ]


def test_email_popup_duplicate_row_deduped(parsed: list[ScrapedShow]) -> None:
    # The Psycodelics row appears twice in the markup (once inside the
    # email-signup popup); exactly one show must come out.
    assert sum(s.headliner_raw == "The Psycodelics" for s in parsed) == 1


def test_private_event_placeholder_dropped(parsed: list[ScrapedShow]) -> None:
    # The "7.11" row is a "Private Event" placeholder, not a concert.
    assert not any("Private" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Harbour (December 8) is ~159 days past the pinned today (> 90 days).
    assert not any(s.headliner_raw == "Harbour" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 6-day window from today catches only the July 7 show (July 9 is
    # exactly +7 and the window is inclusive).
    shows = cafe_du_nord.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=6
    )
    assert [s.headliner_raw for s in shows] == ["The Psycodelics"]


def test_support_acts_split_from_headliner(parsed: list[ScrapedShow]) -> None:
    psycodelics = next(s for s in parsed if s.headliner_raw == "The Psycodelics")
    assert psycodelics.support_raw == ["B. DeVeaux"]
    brotherkenzie = next(s for s in parsed if s.headliner_raw == "Brotherkenzie")
    assert brotherkenzie.support_raw == ["Dirt Buyer"]


def test_doors_and_price_joined_from_popup(parsed: list[ScrapedShow]) -> None:
    # The list rows carry neither doors nor price; both come from the hidden
    # tw-event-dialog popup matched by per-event URL.
    psycodelics = next(s for s in parsed if s.headliner_raw == "The Psycodelics")
    assert psycodelics.doors_local == dt.datetime(2026, 7, 7, 19, 0)
    assert psycodelics.price_text == "$28.30"
    friendlyjordies = next(s for s in parsed if s.headliner_raw == "Friendlyjordies")
    assert friendlyjordies.price_text == "$45.81 - $129.24"  # price range


def test_empty_popup_price_becomes_none(parsed: list[ScrapedShow]) -> None:
    # ATTA BOY's popup has a whitespace-only tw-price element.
    atta = next(s for s in parsed if s.headliner_raw == "ATTA BOY")
    assert atta.price_text is None
    assert atta.doors_local == dt.datetime(2026, 7, 9, 19, 0)


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    psycodelics = next(s for s in parsed if s.headliner_raw == "The Psycodelics")
    assert psycodelics.ticket_url == (
        "https://www.ticketweb.com/event/the-psycodelics-with-b-deveaux-cafe-du-nord"
        "-tickets/14781783?pl=cafedunord&REFID=clientsitewp"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    atta = next(s for s in parsed if s.headliner_raw == "ATTA BOY")
    assert atta.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    psycodelics = next(s for s in parsed if s.headliner_raw == "The Psycodelics")
    assert psycodelics.source_url == "https://cafedunord.com/tm-event/the-psycodelics/"


def test_swedish_american_hall_show_kept(parsed: list[ScrapedShow]) -> None:
    # Shows billed at the attached Swedish American Hall stay on this slug.
    friendlyjordies = next(s for s in parsed if s.headliner_raw == "Friendlyjordies")
    assert friendlyjordies.source_url == (
        "https://cafedunord.com/tm-event/friendlyjordies-presents-alien-hunter/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    atta = next(s for s in parsed if s.headliner_raw == "ATTA BOY")
    assert atta.venue_slug == "cafe_du_nord"
    assert atta.support_raw == []


def test_next_page_link_found() -> None:
    assert find_next_page_url(FIXTURE.read_text(encoding="utf-8")) == (
        "https://cafedunord.com/calendar/page/2/"
    )
