"""Unit tests for the deterministic mailing-list email parser (Phase 8)."""

from __future__ import annotations

import datetime as dt

from foghorn.mailingest.parser import ParsedDraft, parse_email
from foghorn.models import Venue

TODAY = dt.date(2026, 7, 7)  # a Tuesday

SENDERS = {
    "list@dillonvado.com": "Dillon Vado",
    "news@mezzacappa.example": "Lisa Mezzacappa",
}


def _venue(slug: str, name: str) -> Venue:
    return Venue(
        slug=slug,
        name=name,
        tz="America/Los_Angeles",
        calendar_url="https://example.com/cal",
    )


VENUES = [
    _venue("make_out_room", "The Make-Out Room"),
    _venue("yoshis", "Yoshi's"),
    _venue("keys", "Keys"),
    _venue("keys_jazz_bistro", "Keys Jazz Bistro"),
    _venue("back_room", "Back Room"),
]


def parse(
    text: str,
    subject: str = "shows",
    from_addr: str = "list@dillonvado.com",
    today: dt.date = TODAY,
) -> ParsedDraft:
    return parse_email(
        from_addr, subject, text, venues=VENUES, senders=SENDERS, today=today
    )


def test_tonight_at_known_venue() -> None:
    draft = parse("TONIGHT at the Make-Out Room, 8pm — trio set, no cover.")
    assert draft.artist_display == "Dillon Vado"
    assert draft.venue_slug == "make_out_room"
    assert draft.venue_name_guess == "The Make-Out Room"
    assert draft.date_guess == "2026-07-07"  # tonight = injected today
    assert draft.time_guess == "20:00"


def test_slash_date_and_set_times() -> None:
    draft = parse("Fri 7/24 · Yoshi's · two sets 7:30/9:30")
    assert draft.venue_slug == "yoshis"
    assert draft.date_guess == "2026-07-24"
    # First set wins; the "/9:30" must not be misread as a September 30 date.
    assert draft.time_guess == "19:30"


def test_unknown_venue_stays_none() -> None:
    draft = parse("Saturday July 18, 8pm at the Red Poppy Art House")
    assert draft.venue_slug is None
    assert draft.venue_name_guess is None
    assert draft.date_guess == "2026-07-18"
    assert draft.time_guess == "20:00"


def test_unknown_sender_leaves_artist_none() -> None:
    draft = parse("tonight 9pm", from_addr="someone@else.example")
    assert draft.artist_display is None


def test_sender_match_unwraps_display_name_and_case() -> None:
    draft = parse("tonight", from_addr="Dillon Vado <LIST@DillonVado.com>")
    assert draft.artist_display == "Dillon Vado"


def test_venue_leading_the_is_optional() -> None:
    # Venue named "The Make-Out Room" found without its article…
    assert parse("Thursday at Make-Out Room").venue_slug == "make_out_room"
    # …and a venue named without one found with it.
    assert parse("at the Back Room, Berkeley").venue_slug == "back_room"


def test_longest_venue_name_wins_and_tokens_are_whole() -> None:
    draft = parse("Friday at Keys Jazz Bistro, 7pm")
    assert draft.venue_slug == "keys_jazz_bistro"  # not the shorter "Keys"
    # Whole-token matching: "Keystone" must not fire the "Keys" venue.
    assert parse("Friday at Keystone Korner").venue_slug is None


def test_weekday_month_day_and_ordinal_dates() -> None:
    assert parse("see you Thursday July 16!").date_guess == "2026-07-16"
    assert parse("July 16th, doors 7").date_guess == "2026-07-16"
    assert parse("2026-08-02 at 20:00").date_guess == "2026-08-02"


def test_yearless_dates_resolve_to_next_future_occurrence() -> None:
    later_today = dt.date(2026, 8, 1)
    assert parse("7/16 show", today=later_today).date_guess == "2027-07-16"
    assert parse("March 1 show", today=later_today).date_guess == "2027-03-01"
    # An explicit year is kept even when it's in the past.
    assert parse("12/31/25 recap", today=later_today).date_guess == "2025-12-31"


def test_tomorrow_and_earliest_date_mention_wins() -> None:
    assert parse("tomorrow night!").date_guess == "2026-07-08"
    # Two dates: the earliest mention (the show date) wins over later ones.
    assert (
        parse("Friday 7/10 at Yoshi's — tickets on sale until 7/9").date_guess
        == "2026-07-10"
    )


def test_time_formats() -> None:
    assert parse("music at 8:30 PM sharp").time_guess == "20:30"
    assert parse("doors 7").time_guess == "19:00"
    assert parse("Doors at 7:30, all ages").time_guess == "19:30"
    assert parse("midnight set at 12am").time_guess == "00:00"
    assert parse("matinee 2pm").time_guess == "14:00"
    assert parse("no clock words here").time_guess is None


def test_unparseable_email_yields_all_none_but_artist() -> None:
    draft = parse("hello friends, big news coming soon…")
    assert draft.artist_display == "Dillon Vado"
    assert draft.venue_slug is None
    assert draft.date_guess is None
    assert draft.time_guess is None
