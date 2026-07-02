"""Heuristic local/touring origin bootstrap.

No scraped source publishes whether an act is local, so v1 infers it from
signals already in the DB and stays deliberately conservative: a performer is
tagged only when the evidence clears a threshold in one direction; everything
else stays ``None`` (unknown). Tags are written with ``origin_source =
'heuristic'`` and never overwrite ``'manual'`` rows, so a hand correction is
permanent. Re-running is idempotent and reflects the latest evidence (scraped
shows persist after their dates pass, so recurrence signals strengthen as
scrape history accumulates).

Signals and weights (see ``score_performer``):

- **Recurrence spread over weeks** — 2+ distinct show dates ≥ 7 days apart is
  the strongest local tell (touring runs are consecutive nights; locals gig
  across the season). Consecutive-night-only repeats stay neutral.
- **Multi-venue presence** — playing 2+ of our venues reads local (tours route
  through one Bay room, not several).
- **Venue booking priors** — small nightly rooms book overwhelmingly local;
  big touring rooms' *headliners* are overwhelmingly touring. Mixed rooms
  (Yoshi's, Bottom of the Hill, GAMH, ...) contribute nothing.
- **Support slot at a local-leaning room** — mild local lean.
- **Ticketmaster/AXS headliner** — those platforms serve the big touring
  rooms; a mild touring lean on top of the venue prior.

Runnable standalone: ``python -m foghorn.cli.tag_origins`` applies the
heuristic to the default DB and prints a summary.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from foghorn.models import Origin
from foghorn.repo import performers as performers_repo

# Venue priors by booking lean. Small rooms whose calendars are essentially
# all Bay Area acts vs. rooms whose *headliners* are essentially all tours.
# Mixed-booking rooms (yoshis, bottom_of_the_hill, great_american_music_hall,
# the_chapel, the_independent, cafe_du_nord, rickshaw_stop, dna_lounge,
# guild_theatre, cornerstone_berkeley) are deliberately absent — no prior.
LOCAL_LEANING_VENUES = frozenset(
    {
        "bird_and_beckett",
        "keys_jazz_bistro",
        "mr_tipples",
        "black_cat",
        "ocean_ale_house",
        "madrone_art_bar",
        "boom_boom_room",
        "natural_grocery_annex",
        "california_jazz_conservatory",
        "gilman_924",
        "ivy_room",
        "kilowatt",
        "the_knockout",
        "the_back_room",
    }
)
TOURING_LEANING_VENUES = frozenset(
    {
        "fox_theater_oakland",
        "greek_theatre_berkeley",
    }
)
# Ticketing hosts that serve the big touring rooms.
_TOURING_TICKET_HOSTS = ("ticketmaster.", "axs.com", "livenation.")

# Score thresholds: |score| must clear these to tag at all.
LOCAL_THRESHOLD = 2.0
TOURING_THRESHOLD = -2.0

# Weights.
_W_SPREAD_RECURRENCE = 2.0  # 2+ dates >= 7 days apart
_W_MULTI_VENUE = 1.5
_W_LOCAL_VENUE_SHOW = 1.0  # per local-leaning-venue appearance, capped
_W_LOCAL_VENUE_CAP = 2.0
_W_SUPPORT_AT_LOCAL = 0.5
_W_TOURING_HEADLINE = -2.0  # headlining a touring-leaning venue
_W_TOURING_TICKETS = -1.0  # headliner sold via Ticketmaster/AXS


@dataclass(frozen=True)
class _Appearance:
    date: str  # YYYY-MM-DD
    venue_slug: str
    role: str
    ticket_url: str | None


@dataclass(frozen=True)
class OriginVerdict:
    performer_id: int
    canonical_name: str
    score: float
    origin: Origin | None  # None = evidence didn't clear either threshold


def _dates_spread_over_weeks(dates: list[str], min_gap_days: int = 7) -> bool:
    if len(dates) < 2:
        return False
    parsed = sorted(dt.date.fromisoformat(d) for d in dates)
    return (parsed[-1] - parsed[0]).days >= min_gap_days


def score_appearances(appearances: list[_Appearance]) -> float:
    """Pure scoring over one performer's appearances (positive = local)."""
    score = 0.0
    dates = sorted({a.date for a in appearances})
    venues = {a.venue_slug for a in appearances}

    if _dates_spread_over_weeks(dates):
        score += _W_SPREAD_RECURRENCE
    if len(venues) >= 2:
        score += _W_MULTI_VENUE

    local_venue_points = 0.0
    for a in appearances:
        if a.venue_slug in LOCAL_LEANING_VENUES:
            local_venue_points += _W_LOCAL_VENUE_SHOW
            if a.role == "support":
                local_venue_points += _W_SUPPORT_AT_LOCAL
    score += min(local_venue_points, _W_LOCAL_VENUE_CAP)

    for a in appearances:
        if a.role != "headliner":
            continue
        if a.venue_slug in TOURING_LEANING_VENUES:
            score += _W_TOURING_HEADLINE
        if a.ticket_url and any(h in a.ticket_url for h in _TOURING_TICKET_HOSTS):
            score += _W_TOURING_TICKETS
    return score


def compute_verdicts(conn: sqlite3.Connection) -> list[OriginVerdict]:
    """Score every performer from the shows currently in the DB."""
    rows = conn.execute(
        """
        SELECT sp.performer_id, p.canonical_name, s.start_local_date,
               v.slug AS venue_slug, sp.role, s.ticket_url
        FROM show_performers sp
        JOIN performers p ON p.id = sp.performer_id
        JOIN shows s ON s.id = sp.show_id
        JOIN venues v ON v.id = s.venue_id
        """
    ).fetchall()

    by_performer: dict[int, tuple[str, list[_Appearance]]] = {}
    for row in rows:
        entry = by_performer.setdefault(row["performer_id"], (row["canonical_name"], []))
        entry[1].append(
            _Appearance(
                date=row["start_local_date"],
                venue_slug=row["venue_slug"],
                role=row["role"],
                ticket_url=row["ticket_url"],
            )
        )

    verdicts: list[OriginVerdict] = []
    for performer_id, (canonical, appearances) in by_performer.items():
        score = score_appearances(appearances)
        origin: Origin | None = None
        if score >= LOCAL_THRESHOLD:
            origin = "local"
        elif score <= TOURING_THRESHOLD:
            origin = "touring"
        verdicts.append(
            OriginVerdict(
                performer_id=performer_id,
                canonical_name=canonical,
                score=score,
                origin=origin,
            )
        )
    return verdicts


def apply_heuristic(conn: sqlite3.Connection) -> dict[str, int]:
    """Tag performers from the current evidence. Never touches rows with
    ``origin_source='manual'``; clears a stale heuristic tag whose evidence no
    longer clears the threshold. Returns summary counts."""
    counts = {"local": 0, "touring": 0, "unknown": 0, "manual_kept": 0}
    for verdict in compute_verdicts(conn):
        row = conn.execute(
            "SELECT origin, origin_source FROM performers WHERE id = ?",
            (verdict.performer_id,),
        ).fetchone()
        if row is not None and row["origin_source"] == "manual":
            counts["manual_kept"] += 1
            continue
        if verdict.origin is None:
            counts["unknown"] += 1
            if row is not None and row["origin_source"] == "heuristic":
                performers_repo.set_origin(conn, verdict.canonical_name, None, "heuristic")
            continue
        counts[verdict.origin] += 1
        performers_repo.set_origin(conn, verdict.canonical_name, verdict.origin, "heuristic")
    conn.commit()
    return counts
