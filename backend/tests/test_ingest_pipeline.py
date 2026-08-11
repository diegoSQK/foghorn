"""Integration tests for the ingest pipeline."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo


def _scraped(
    headliner: str,
    start: datetime,
    *,
    support: list[str] | None = None,
    doors: datetime | None = None,
    ticket_url: str | None = None,
    price_text: str | None = None,
) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="sfjazz",
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        doors_local=doors,
        ticket_url=ticket_url,
        price_text=price_text,
        source_url="https://www.sfjazz.org/tickets/show",
    )


def test_created_updated_counts_and_state(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # An existing row to dedupe against.
    first = ingest_scraped_shows(
        conn, venue, [_scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0))]
    )
    assert (first.created, first.updated, first.errors) == (1, 0, [])

    # One new, one exact duplicate, one same-headliner-different-time (new key).
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Kamasi Washington", datetime(2026, 6, 10, 20, 0)),  # new
            _scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0)),  # duplicate
            _scraped("Joshua Redman", datetime(2026, 6, 1, 22, 0)),  # later set, new
        ],
    )
    assert result.created == 2
    assert result.updated == 1
    assert result.errors == []
    assert len(shows_repo.list(conn, ShowFilters())) == 3


def test_computes_utc_from_venue_tz(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(conn, venue, [_scraped("X", datetime(2026, 6, 1, 20, 0))])
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.start_local_date == "2026-06-01"
    assert show.start_local_time == "20:00"
    # 8pm PDT (UTC-7) on June 1 -> 03:00 UTC on June 2.
    assert show.start_utc == "2026-06-02T03:00:00+00:00"


def test_stores_doors_support_and_bill_order(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped(
                "Headliner",
                datetime(2026, 6, 1, 20, 0),
                support=["Opener A", "Opener B"],
                doors=datetime(2026, 6, 1, 19, 0),
                ticket_url="https://tix.example.com/x",
                price_text="$30",
            )
        ],
    )
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.doors_local_time == "19:00"
    assert show.ticket_url == "https://tix.example.com/x"
    assert show.price_text == "$30"
    bill = [(p.role, p.position, p.display_name) for p in show.performers]
    assert bill == [
        ("headliner", 0, "Headliner"),
        ("support", 1, "Opener A"),
        ("support", 2, "Opener B"),
    ]


def test_preserves_display_name_and_canonicalizes(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn, venue, [_scraped("Café Tacvba", datetime(2026, 6, 1, 20, 0))]
    )
    show = shows_repo.list(conn, ShowFilters())[0]
    assert show.headliner_canonical == "cafe tacvba"
    headliner = next(p for p in show.performers if p.role == "headliner")
    assert headliner.display_name == "Café Tacvba"  # verbatim, never normalized
    assert headliner.canonical_name == "cafe tacvba"


def test_performer_reused_across_shows(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Joshua Redman", datetime(2026, 6, 1, 20, 0)),
            _scraped("Joshua Redman", datetime(2026, 6, 2, 20, 0)),
        ],
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM performers WHERE canonical_name = 'joshua redman'"
    ).fetchone()[0]
    assert count == 1  # one performer row, two shows


def test_bad_show_is_isolated_in_errors(conn: sqlite3.Connection) -> None:
    bad_venue = venues_repo.upsert(
        conn,
        Venue(
            slug="bad",
            name="Bad Venue",
            tz="Not/AZone",  # unresolvable -> raises during ingest
            calendar_url="https://example.com/cal",
        ),
    )
    result = ingest_scraped_shows(
        conn, bad_venue, [_scraped("X", datetime(2026, 6, 1, 20, 0))]
    )
    assert result.created == 0
    assert result.updated == 0
    assert len(result.errors) == 1


def test_duplicate_billing_collapses_to_first_occurrence(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    # Venues sometimes repeat an act on the bill (headliner listed again in
    # support, or "TBA" filling several slots). The bill must dedupe by
    # performer rather than violating the show_performers PK.
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped(
                "TBA",
                datetime(2026, 9, 2, 19, 45),
                support=["TBA", "Opener A", "TBA", "Opener A"],
            )
        ],
    )
    assert result.errors == []
    assert result.created == 1
    [show] = shows_repo.list(conn, ShowFilters())
    got = [(p.role, p.position, p.display_name) for p in show.performers]
    assert got == [("headliner", 0, "TBA"), ("support", 1, "Opener A")]


def test_event_type_inference_and_explicit_tag(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    result = ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Sunday Blues Jam", datetime(2026, 6, 7, 18, 0)),
            _scraped("Weekly Jam Session at the Annex", datetime(2026, 6, 8, 18, 0)),
            _scraped("Pearl Jam Tribute Night", datetime(2026, 6, 9, 20, 0)),
            _scraped("Regular Old Quartet", datetime(2026, 6, 10, 20, 0)),
        ],
    )
    assert result.errors == []
    by_name = {
        s.headliner_canonical: s.event_type for s in shows_repo.list(conn, ShowFilters())
    }
    assert by_name["sunday blues jam"] == "jam"
    assert by_name["weekly jam session at the annex"] == "jam"
    # "jam" inside a band name must NOT trigger the heuristic.
    assert by_name["pearl jam tribute night"] == "show"
    assert by_name["regular old quartet"] == "show"

    # An explicit scraper tag beats the title heuristic in both directions.
    explicit = ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw="Totally Normal Name",
        start_local=datetime(2026, 6, 11, 20, 0),
        source_url="https://example.com/x",
        event_type="jam",
    )
    ingest_scraped_shows(conn, venue, [explicit])
    listed = {
        s.headliner_canonical: s.event_type for s in shows_repo.list(conn, ShowFilters())
    }
    assert listed["totally normal name"] == "jam"


def test_event_type_filter(conn: sqlite3.Connection, venue: Venue) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Open Jam Mondays", datetime(2026, 6, 1, 19, 0)),
            _scraped("Some Band", datetime(2026, 6, 2, 20, 0)),
        ],
    )
    jams = shows_repo.list(conn, ShowFilters(event_type=["jam"]))
    assert [s.headliner_canonical for s in jams] == ["open jam mondays"]
    shows_only = shows_repo.list(conn, ShowFilters(event_type=["show"]))
    assert [s.headliner_canonical for s in shows_only] == ["some band"]


def test_genre_normalization() -> None:
    from foghorn.ingest.pipeline import normalize_genre

    assert normalize_genre("Rock / Indie") == "rock"
    assert normalize_genre("Hip-Hop") == "hip-hop"
    assert normalize_genre("Soul/Funk") == "funk"
    assert normalize_genre("JAZZ") == "jazz"
    assert normalize_genre("Other Content") is None
    assert normalize_genre("") is None
    assert normalize_genre(None) is None
    # Classical cluster — the real Cal Performances badge vocabulary.
    assert normalize_genre("Recital") == "classical"
    assert normalize_genre("Orchestra & Chamber Music") == "classical"
    assert normalize_genre("Early Music") == "classical"
    assert normalize_genre("New Music") == "classical"
    assert normalize_genre("Opera") == "classical"
    # Jazz outranks the classical words ("Jazz Orchestra" is a big band).
    assert normalize_genre("Jazz Orchestra") == "jazz"
    # Ambiguous badges stay unmapped -> venue default applies.
    assert normalize_genre("Vocal Celebration") is None
    assert normalize_genre("Family") is None
    assert normalize_genre("Seasonal Holidays") is None
    # "indie pop" hits the more specific pop before rock? Order check: pop
    # precedes indie in the table, so "Indie Pop" buckets as pop.
    assert normalize_genre("Indie Pop") == "pop"


def test_manual_genre_kept_verbatim_when_unmapped(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    scraped = ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw="Noise Set",
        start_local=datetime(2026, 6, 12, 20, 0),
        source_url="https://example.com/n",
        genre="Harsh Noise Wall",
    )
    # As a scrape: unmapped genre drops to None (venue default applies).
    ingest_scraped_shows(conn, venue, [scraped])
    [show] = shows_repo.list(conn, ShowFilters())
    assert show.genre_override is None
    # As a manual entry: the user's word is kept (lowercased).
    manual = ScrapedShow(
        venue_slug=venue.slug,
        headliner_raw="Noise Set Two",
        start_local=datetime(2026, 6, 13, 20, 0),
        source_url="https://example.com/n2",
        genre="Harsh Noise Wall",
    )
    ingest_scraped_shows(conn, venue, [manual], source="manual")
    by_name = {s.headliner_canonical: s for s in shows_repo.list(conn, ShowFilters())}
    assert by_name["noise set two"].genre_override == "harsh noise wall"


def test_jam_patterns_cover_plurals_open_mics_and_organ_sessions(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("Jazz Jams at Jupiter", datetime(2026, 7, 8, 19, 0)),
            _scraped("SUNDAY B3 SESSIONS", datetime(2026, 7, 5, 18, 0)),
            _scraped("Vocal Open Mic", datetime(2026, 7, 26, 19, 0)),
            _scraped("Duncan James Quartet", datetime(2026, 7, 4, 20, 0)),  # not a jam
        ],
    )
    by_name = {
        s.headliner_canonical: s.event_type for s in shows_repo.list(conn, ShowFilters())
    }
    assert by_name["jazz jams at jupiter"] == "jam"
    assert by_name["sunday b3 sessions"] == "jam"
    assert by_name["vocal open mic"] == "jam"
    assert by_name["duncan james quartet"] == "show"  # "James" must not match


def test_title_genre_fills_gap_only_at_leanless_venues() -> None:
    from foghorn.ingest.pipeline import infer_genre_from_title

    assert infer_genre_from_title("Motown on Mondays") == "funk"
    assert infer_genre_from_title("Brazilian Disco") == "funk"
    assert infer_genre_from_title("SPIKE SPINS OSCAR’S JAZZ RECORDS") == "jazz"
    # B3/Hammond in a title means the organ — soul-jazz idiom.
    assert infer_genre_from_title("SUNDAY B3 SESSIONS") == "jazz"
    # Two distinct buckets -> ambiguous -> no inference.
    assert infer_genre_from_title("Hector Lugo Jazz/Latin Trio") is None
    # Same bucket twice is still unambiguous.
    assert infer_genre_from_title("Soul & Funk Revue") == "funk"
    assert infer_genre_from_title("Regular Band Name") is None
    # Classical title words fire only on the safe ones.
    assert (
        infer_genre_from_title("Tchaikovsky Symphony No. 4 & Rachmaninov Piano Concerto No. 2")
        == "classical"
    )
    assert infer_genre_from_title("The Philharmonic at the Park") == "classical"
    # "opera"/"orchestra"/"quartet" deliberately don't claim from titles.
    assert infer_genre_from_title("A Night at the Opera — Queen Tribute") is None
    assert infer_genre_from_title("Mingus Big Band Orchestra") is None


def test_title_genre_respects_venue_lean(conn: sqlite3.Connection, venue: Venue) -> None:
    # Give the venue a curated lean; a punk-titled show there must NOT get a
    # title-derived override (the heuristic only fills gaps).
    leaned = venue.model_copy(update={"genre": "jazz"})
    leaned = venues_repo.upsert(conn, leaned)
    ingest_scraped_shows(
        conn, leaned, [_scraped("Punk Rock Karaoke Band", datetime(2026, 7, 9, 20, 0))]
    )
    [show] = shows_repo.list(conn, ShowFilters())
    assert show.genre_override is None
