"""Tests for the Bay Improviser aggregator: parsing, venue resolution, the
duplicate guard, and the quarantine-with-flag filter semantics."""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.aggregators.bay_improviser import parse_events
from foghorn.aggregators.ingest import ingest_aggregated_events, resolve_venue
from foghorn.aggregators.models import AggregatedEvent
from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo import watched_venues as watched_repo
from foghorn.repo.seed_venues import seed


def _gcal_anchor(text: str, dates: str, location: str, details: str | None = None) -> str:
    from urllib.parse import quote

    details_param = f"&details={quote(details)}" if details is not None else ""
    return (
        f'<a href="https://calendar.google.com/calendar/render?action=TEMPLATE'
        f"&text={quote(text)}&dates={dates}&location={quote(location)}{details_param}"
        f'">gCal</a>'
    )


# 2026-07-11 03:00 UTC == 2026-07-10 20:00 Pacific (PDT).
_FIXTURE_HTML = "<html><body>" + "".join(
    [
        _gcal_anchor(
            "Lisa Mezzacappa Six @ The Back Room",
            "20260711T030000Z/20260711T050000Z",
            "The Back Room, 1984 Bonita Ave, Berkeley, CA",
        ),
        _gcal_anchor(
            "Euphotic / Headboggle",
            "20260712T033000Z/20260712T053000Z",
            "Peacock Lounge, 552 Haight St, San Francisco",
        ),
        # all-day (date-only) entries carry no start time -> skipped
        _gcal_anchor("Some Festival", "20260712/20260713", "Somewhere"),
        # duplicate of the first (same title+start) -> deduped
        _gcal_anchor(
            "Lisa Mezzacappa Six @ The Back Room",
            "20260711T030000Z/20260711T050000Z",
            "The Back Room, Berkeley",
        ),
    ]
) + "</body></html>"


def test_parse_events_utc_to_pacific_dedup_and_allday_skip() -> None:
    events = parse_events(_FIXTURE_HTML)
    assert [(e.venue_name_raw, e.start_local.isoformat()) for e in events] == [
        ("The Back Room", "2026-07-10T20:00:00"),
        ("Peacock Lounge", "2026-07-11T20:30:00"),
    ]
    assert events[0].venue_address_raw == "1984 Bonita Ave, Berkeley, CA"
    assert all(not e.headliner_is_description for e in events)


# The site's no-billing fallback: gCal text = description truncated to 350
# chars (details carries the full text). Seen live on Gray Area's Cybersentics
# Book Club entry, July 2026.
_PROSE = (
    "Is everyone suddenly a creative technologist? Bring your confusion with "
    "this vogue mega-identity, and let's look together at the landscape we had "
    "at the turn of the 21st century — before the breed of people who combine "
    "art and technology in their research became defined. In this endeavor, we "
    "will rely on an encyclopedia of modern media art assembled here."
)


def _description_fixture() -> str:
    assert len(_PROSE) >= 300
    return "<html><body>" + "".join(
        [
            # truncated-description fallback -> no real title exists -> skipped
            _gcal_anchor(
                _PROSE,
                "20260711T030000Z/20260711T050000Z",
                "Cybersentics Book Club at Gray Area, 2665 Mission St. SF",
                details=_PROSE + " Reading list follows in the full description.",
            ),
            # short description doubling as title -> kept, flagged
            _gcal_anchor(
                "3D/AV Live is Max Cooper's immersive audio-visual performance system.",
                "20260712T033000Z/20260712T053000Z",
                "Gray Area Art And Technology, 2665 Mission St. SF",
                details="3D/AV Live is Max Cooper's immersive audio-visual performance system.",
            ),
            # billing that legitimately doubles as the description -> kept, unflagged
            _gcal_anchor(
                "AVOTCJA & MODUPUE",
                "20260713T030000Z/20260713T050000Z",
                "Bird & Beckett, 653 Chenery St, San Francisco",
                details="AVOTCJA & MODUPUE",
            ),
            # billing whose description merely starts with it -> kept, unflagged
            _gcal_anchor(
                "Motoko Honda Quartet",
                "20260714T030000Z/20260714T050000Z",
                "The Back Room, 1984 Bonita Ave, Berkeley, CA",
                details="Motoko Honda Quartet returns with an evening of new work.",
            ),
        ]
    ) + "</body></html>"


def test_parse_events_description_as_title() -> None:
    events = parse_events(_description_fixture())
    assert [(e.headliner_raw[:20], e.headliner_is_description) for e in events] == [
        ("3D/AV Live is Max Co", True),
        ("AVOTCJA & MODUPUE", False),
        ("Motoko Honda Quartet", False),
    ]


def _event(
    venue: str,
    headliner: str,
    start: dt.datetime,
    address: str | None = None,
    is_description: bool = False,
) -> AggregatedEvent:
    return AggregatedEvent(
        venue_name_raw=venue,
        venue_address_raw=address,
        headliner_raw=headliner,
        headliner_is_description=is_description,
        start_local=start,
        source_url="https://www.bayimproviser.com/calendar.aspx",
    )


def test_resolve_venue_exact_token_alias_and_create(conn: sqlite3.Connection) -> None:
    seed(conn)
    start = dt.datetime(2026, 7, 10, 20, 0)
    # exact (with leading-the stripping)
    assert resolve_venue(conn, _event("the Knockout", "X", start)).slug == "the_knockout"
    # token subset: "Bird & Beckett" ⊆ "Bird & Beckett Books and Records"
    assert (
        resolve_venue(conn, _event("Bird & Beckett", "X", start)).slug
        == "bird_and_beckett"
    )
    # alias map
    assert (
        resolve_venue(conn, _event("The Jazzschool", "X", start)).slug
        == "california_jazz_conservatory"
    )
    # unknown -> quarantined creation
    created = resolve_venue(conn, _event("Peacock Lounge", "X", start, "552 Haight St"))
    assert created.slug == "peacock_lounge"
    assert created.source == "aggregator"
    assert created.address == "552 Haight St"
    # idempotent on re-resolve
    again = resolve_venue(conn, _event("Peacock Lounge", "X", start))
    assert again.id == created.id


def test_duplicate_guard_defers_to_scraped_rows(conn: sqlite3.Connection) -> None:
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "the_back_room")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="the_back_room",
                headliner_raw="Lisa Mezzacappa Six",
                start_local=dt.datetime(2026, 7, 10, 20, 0),
                source_url="https://example.com/s",
            )
        ],
    )
    result = ingest_aggregated_events(
        conn,
        [
            # blob covers the scraped headliner -> duplicate, skipped
            _event(
                "The Back Room",
                "Lisa Mezzacappa Six @ The Back Room, Berkeley",
                dt.datetime(2026, 7, 10, 19, 30),
            ),
            # different act same day -> ingested
            _event("The Back Room", "Totally Different Act", dt.datetime(2026, 7, 10, 21, 30)),
        ],
        "bay_improviser",
    )
    assert result.errors == []
    assert result.created == 1
    rows = conn.execute(
        "SELECT headliner_canonical, source FROM shows ORDER BY start_utc"
    ).fetchall()
    assert [(r["headliner_canonical"], r["source"]) for r in rows] == [
        ("lisa mezzacappa six", "scrape"),
        ("totally different act", "aggregator"),
    ]


def test_duplicate_guard_matches_across_billing_shapes(
    conn: sqlite3.Connection,
) -> None:
    """The real 2026-07-24 Bird & Beckett case: the venue bills the ensemble,
    Bay Improviser lists the full personnel. Raw token bags don't overlap
    ("the"/"quartet" are absent from the aggregator string), so the show landed
    twice until the guard compared identifying tokens only."""
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="bird_and_beckett",
                headliner_raw="The Kasey Knudsen / Harvey Wainapel Quartet",
                start_local=dt.datetime(2026, 7, 24, 19, 30),
                source_url="https://birdbeckett.com/events/",
            )
        ],
    )
    result = ingest_aggregated_events(
        conn,
        [
            # Same show, personnel-list billing -> duplicate, skipped.
            _event(
                "Bird & Beckett",
                "Kasey Knudsen/Harvey Wainapel/Jon Arkin/John Wiitala",
                dt.datetime(2026, 7, 24, 19, 30),
            ),
            # Aggregator naming only the leader -> still the same show.
            _event("Bird & Beckett", "Kasey Knudsen", dt.datetime(2026, 7, 24, 21, 0)),
            # A genuinely different act that night -> kept.
            _event("Bird & Beckett", "Totally Other Band", dt.datetime(2026, 7, 24, 22, 0)),
        ],
        "bay_improviser",
    )
    assert result.errors == []
    assert result.created == 1
    rows = conn.execute(
        "SELECT headliner_canonical FROM shows ORDER BY start_utc"
    ).fetchall()
    assert [r["headliner_canonical"] for r in rows] == [
        "the kasey knudsen harvey wainapel quartet",
        "totally other band",
    ]


def test_duplicate_guard_ignores_content_free_billing(
    conn: sqlite3.Connection,
) -> None:
    """A venue billing made entirely of noise words keeps no identifying
    tokens, so it must not swallow every aggregator event that night."""
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="bird_and_beckett",
                headliner_raw="The Quartet",
                start_local=dt.datetime(2026, 7, 25, 19, 30),
                source_url="https://birdbeckett.com/events/",
            )
        ],
    )
    result = ingest_aggregated_events(
        conn,
        [_event("Bird & Beckett", "Someone Else Entirely", dt.datetime(2026, 7, 25, 21, 0))],
        "bay_improviser",
    )
    assert result.created == 1


def test_description_headliner_dropped_at_tracked_venue(conn: sqlite3.Connection) -> None:
    seed(conn)
    result = ingest_aggregated_events(
        conn,
        [
            # tracked venue + description-flagged headliner -> dropped
            _event(
                "The Back Room",
                "An evening of improvised music awaits you.",
                dt.datetime(2026, 7, 10, 20, 0),
                is_description=True,
            ),
            # quarantined venue -> kept even when flagged (only record we have)
            _event(
                "Peacock Lounge",
                "An evening of improvised music awaits you.",
                dt.datetime(2026, 7, 10, 21, 0),
                is_description=True,
            ),
        ],
        "bay_improviser",
    )
    assert result.errors == []
    assert result.created == 1
    rows = conn.execute("SELECT venue_id FROM shows").fetchall()
    assert len(rows) == 1


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    ingest_aggregated_events(
        conn,
        [_event("Peacock Lounge", "Euphotic", dt.datetime(2026, 6, 10, 20, 0))],
        "bay_improviser",
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_quarantine_hidden_by_default(client: TestClient) -> None:
    assert _june(client) == []


def test_long_tail_toggle_reveals(client: TestClient) -> None:
    rows = _june(client, long_tail="true")
    assert [r["headliner"]["display"] for r in rows] == ["Euphotic"]
    assert rows[0]["source"] == "aggregator"


def test_explicit_selection_reveals(client: TestClient) -> None:
    assert len(_june(client, venues="peacock_lounge")) == 1


def test_pin_promotes_into_main_ui(client: TestClient, sign_in) -> None:
    pinner = sign_in(client)
    assert pinner.id is not None
    conn = db.connect()
    watched_repo.add(conn, pinner.id, "peacock_lounge")
    conn.close()
    assert len(_june(client)) == 1  # no toggle needed once pinned


def test_pin_promotion_is_per_user(client: TestClient, sign_in) -> None:
    # One user's pin must not reveal the quarantined venue to anonymous
    # browsers (multi-user, August 2026).
    pinner = sign_in(client)
    assert pinner.id is not None
    conn = db.connect()
    watched_repo.add(conn, pinner.id, "peacock_lounge")
    conn.close()
    client.cookies.clear()
    assert _june(client) == []


def test_performer_watchlist_bypasses_quarantine(client: TestClient, sign_in) -> None:
    sign_in(client)
    client.post("/api/watchlist", json={"display_name": "Euphotic"})
    rows = _june(client, watchlist="true")
    assert [r["headliner"]["display"] for r in rows] == ["Euphotic"]


def test_venues_endpoint_flags_aggregator_source(client: TestClient) -> None:
    venues = {v["slug"]: v for v in client.get("/api/venues").json()}
    assert venues["peacock_lounge"]["source"] == "aggregator"
    assert venues["keys_jazz_bistro"]["source"] == "seed"
