"""Shared domain + transport models for foghorn.

Everything that crosses a layer boundary is a Pydantic model defined here, so
the repo, ingest, scraper, and (later) API layers all agree on shapes without
importing each other. Persisted rows are exposed through these models — callers
never touch raw ``sqlite3.Row`` objects.

See ``AGENTS.md`` → "Conventions" for the rules these encode: the show natural
key, UTC-plus-local time storage, and the display-vs-canonical performer split.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed enumerations stored as TEXT. Kept as Literals so seeds and ingest are
# validated at construction time rather than silently writing typos to the DB.
Region = Literal["SF", "East Bay", "Peninsula", "South Bay"]
Role = Literal["headliner", "support"]
# Performer origin (v1 of local/touring tagging). No scraped source publishes
# this — it's inferred (heuristic bootstrap) or hand-set; None = unknown.
# "regional" (touring-the-West-Coast-but-Bay-based) deferred until the two-way
# split proves too coarse.
Origin = Literal["local", "touring"]
OriginSource = Literal["heuristic", "manual"]


class Venue(BaseModel):
    """A music venue. ``id`` is ``None`` until persisted."""

    id: int | None = None
    slug: str
    name: str
    neighborhood: str | None = None
    region: Region | None = None
    address: str | None = None
    tz: str  # IANA, e.g. "America/Los_Angeles"
    website_url: str | None = None
    calendar_url: str
    # Venue-default genre (Phase 7.1): the coarse booking lean ("jazz", "rock",
    # "funk", "eclectic"). Kept TEXT-loose rather than a Literal so adding a
    # value is a seed edit, not a schema change; a per-show override is a later
    # phase (7.2).
    genre: str | None = None


class Performer(BaseModel):
    """A performer. ``canonical_name`` is the normalized search/match key;
    ``display_name`` is the venue's verbatim string and is never overwritten."""

    id: int | None = None
    display_name: str
    canonical_name: str
    # Local/touring tag. origin_source records who set it: the heuristic
    # bootstrap never overwrites a "manual" row.
    origin: Origin | None = None
    origin_source: OriginSource | None = None


class ShowPerformer(BaseModel):
    """One performer's slot on a show's bill (the ``show_performers`` join row,
    denormalized with the performer's names for convenient read-back)."""

    performer_id: int | None = None
    display_name: str
    canonical_name: str
    role: Role
    position: int  # display order on the bill; headliner is 0
    origin: Origin | None = None  # denormalized from performers for read-back


class Show(BaseModel):
    """A persisted show. Times are stored as both UTC (for ordering across
    venues / future multi-tz) and venue-local date+time (for natural-key dedup
    and display). ``performers`` is populated by the read paths, empty on the
    objects handed to ``shows.upsert``."""

    id: int | None = None
    venue_id: int
    start_utc: str  # ISO 8601, always normalized to +00:00
    start_local_date: str  # YYYY-MM-DD in the venue's tz
    start_local_time: str  # HH:MM in the venue's tz
    doors_local_time: str | None = None  # HH:MM in the venue's tz
    headliner_canonical: str
    ticket_url: str | None = None
    price_text: str | None = None
    source_url: str
    scraped_at: str  # ISO 8601 UTC
    performers: list[ShowPerformer] = Field(default_factory=list)


class ScrapedShow(BaseModel):
    """The scraper output contract. Frozen: a scraper produces these and hands
    them to the ingest pipeline, which is the only thing that touches the DB.

    ``start_local`` / ``doors_local`` are *naive* datetimes — the venue's tz is
    applied at ingest, not by the scraper."""

    model_config = ConfigDict(frozen=True)

    venue_slug: str
    headliner_raw: str
    support_raw: list[str] = Field(default_factory=list)
    start_local: datetime
    doors_local: datetime | None = None
    ticket_url: str | None = None
    price_text: str | None = None
    source_url: str


class ShowFilters(BaseModel):
    """Query filters for ``shows.list``. All optional; omitted filters don't
    constrain. Date filters compare against ``start_local_date`` (the day the
    show happens in the venue's tz), inclusive on both ends."""

    venue_slugs: list[str] | None = None
    from_date: str | None = None  # YYYY-MM-DD, inclusive
    to_date: str | None = None  # YYYY-MM-DD, inclusive
    # Canonicalized free-text query; whole-token matched against any performer
    # (Phase 4.1 upgraded this from substring to token-bag matching).
    performer_query_canonical: str | None = None
    # Watchlist filter: each inner list is one entry's canonical tokens. A show
    # matches if any performer token-matches any bag. Empty list = no matches
    # (empty watchlist), None = filter not requested.
    watchlist_token_bags: list[list[str]] | None = None
    region: Region | None = None
    neighborhood: str | None = None  # case-insensitive exact match on venue
    genre: str | None = None  # case-insensitive exact match on venue genre
    # A show matches if ANY performer on the bill carries this origin tag
    # (same any-performer semantics as the watchlist filter).
    origin: Origin | None = None
    # "early" = start_local_time < 21:00; "late" = >= 21:00 (exact complements).
    time_of_day: Literal["early", "late"] | None = None


class IngestResult(BaseModel):
    """Per-venue outcome of an ingest run. ``errors`` holds one message per
    show that failed to ingest, so a partial failure doesn't abort the batch."""

    venue_slug: str
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class ScrapeRunVenue(BaseModel):
    """One venue's slice of a scrape run — what the scheduler/`make scrape`
    recorded for it (mirrors the ``scrape_run_venues`` row)."""

    venue_slug: str
    started_at: str  # ISO 8601 UTC
    finished_at: str  # ISO 8601 UTC
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class ScrapeRun(BaseModel):
    """A single refresh of all registered scrapers — scheduled (04:00 PT) or
    manual (`make scrape`). ``GET /api/health/scrape`` returns the latest one."""

    id: int | None = None
    started_at: str  # ISO 8601 UTC
    finished_at: str  # ISO 8601 UTC
    venues: list[ScrapeRunVenue] = Field(default_factory=list)


class Watchlist(BaseModel):
    """A performer the user follows. ``canonical_name`` (the canonicalized
    ``display_name``) is the match key + primary key; ``display_name`` is the
    verbatim string the user added, kept for the UI. Single-tenant — no user_id."""

    canonical_name: str
    display_name: str
    added_at: str  # ISO 8601 UTC
    notes: str | None = None
