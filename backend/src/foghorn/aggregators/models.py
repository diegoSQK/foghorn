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
    start_local: datetime  # naive, America/Los_Angeles
    source_url: str
