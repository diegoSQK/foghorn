"""Shared aggregator-event shape."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AggregatedEvent(BaseModel):
    """One event from an aggregator: a show plus a free-text venue reference
    (aggregators name venues; they don't share our slugs)."""

    model_config = ConfigDict(frozen=True)

    venue_name_raw: str
    venue_address_raw: str | None = None
    headliner_raw: str
    # True when the aggregator could tell headliner_raw is really the event's
    # *description* (the source had no billing and fell back to it). Ingest
    # drops such events at tracked venues, where the venue scraper is
    # authoritative and a description blob is pure noise.
    headliner_is_description: bool = False
    start_local: datetime  # naive, America/Los_Angeles
    source_url: str
