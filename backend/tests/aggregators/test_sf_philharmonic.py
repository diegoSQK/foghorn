"""Tests for the SF Philharmonic group feed's pure parse layer, driven by
real captures (2026-07-19) of the sfphil.org nav, a City Box Office event
page head, its related-events block, and a ``GetTimeSlots`` fragment."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.aggregators.sf_philharmonic import (
    parse_buy_links,
    parse_first_time,
    parse_program_title,
    parse_related_venues,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_buy_links_real_nav() -> None:
    html = (_FIXTURES / "sf_philharmonic_home_nav.html").read_text()
    links = parse_buy_links(html)
    assert [(d.isoformat(), evt) for d, evt, _ in links] == [
        ("2026-10-03", "3318"),
        ("2026-12-18", "3328"),
        ("2027-04-24", "3329"),
    ]
    assert links[0][2].endswith("eventperformances.asp?evt=3318")


def test_parse_buy_links_dedupes_repeated_nav() -> None:
    html = (_FIXTURES / "sf_philharmonic_home_nav.html").read_text()
    assert len(parse_buy_links(html + html)) == 3  # mobile nav repeats


def test_parse_related_venues_real_block() -> None:
    # The evt=3318 page's related-events block names its two siblings'
    # halls — this is where each concert's venue comes from (union across
    # all fetched pages).
    html = (_FIXTURES / "sf_philharmonic_cbo_related.html").read_text()
    assert parse_related_venues(html) == {
        "3328": "Atrium Theater, The Wilsey Center",
        "3329": "Herbst Theatre",
    }


def test_parse_related_venues_absent() -> None:
    assert parse_related_venues("<html><body>no related events</body></html>") == {}


def test_parse_program_title_strips_presenter_prefix() -> None:
    html = (_FIXTURES / "sf_philharmonic_cbo_event.html").read_text()
    assert parse_program_title(html) == "A Season of Titans"


def test_parse_program_title_keeps_billing_forms() -> None:
    page = (
        "<title>Tickets | San Francisco Philharmonic &amp; Anne Richardson"
        " | City Box Office</title>"
    )
    assert parse_program_title(page) == "San Francisco Philharmonic & Anne Richardson"


def test_parse_program_title_missing() -> None:
    assert parse_program_title("<html><body>no title tag</body></html>") is None


def test_parse_first_time_real_fragment() -> None:
    html = (_FIXTURES / "sf_philharmonic_timeslots.html").read_text()
    assert parse_first_time(html) == dt.time(19, 30)


def test_parse_first_time_handles_noon_midnight_and_absence() -> None:
    assert parse_first_time("<li>12:00PM</li>") == dt.time(12, 0)
    assert parse_first_time("<li>12:30 am</li>") == dt.time(0, 30)
    assert parse_first_time("<ul id='timeslot-options'></ul>") is None
