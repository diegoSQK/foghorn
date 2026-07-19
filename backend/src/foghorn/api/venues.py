"""``GET /api/venues`` — the registered venues, so the frontend can render the
venue-filter checkboxes without hardcoding the list."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.scrapers import REGISTERED_SCRAPERS

router = APIRouter()


class VenueView(BaseModel):
    slug: str
    name: str
    neighborhood: str | None
    region: str | None
    genre: str | None
    # 'seed' | 'manual' | 'aggregator' — the frontend quarantines aggregator
    # venues (hidden from pickers/chips unless the long-tail toggle or a pin
    # surfaces them).
    source: str


@router.get("/api/venues", response_model=list[VenueView])
def list_venues() -> list[VenueView]:
    conn = db.connect()
    try:
        venues = venues_repo.list_all(conn)
        fed = venues_repo.ids_with_shows(conn)
    finally:
        conn.close()
    # Venues foghorn actively scrapes, user-created manual venues,
    # aggregator-discovered venues (flagged via `source` so the frontend can
    # quarantine them), and seeded venues that carry shows without a venue
    # scraper of their own — halls fed by group feeds (Davies, Herbst, the
    # Wilsey Atrium). SFJAZZ — seeded but deferred, no scraper, no shows —
    # stays excluded.
    return [
        VenueView(
            slug=v.slug,
            name=v.name,
            neighborhood=v.neighborhood,
            region=v.region,
            genre=v.genre,
            source=v.source,
        )
        for v in venues
        if v.slug in REGISTERED_SCRAPERS
        or v.source in ("manual", "aggregator")
        or v.id in fed
    ]
