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


@router.get("/api/venues", response_model=list[VenueView])
def list_venues() -> list[VenueView]:
    conn = db.connect()
    try:
        venues = venues_repo.list_all(conn)
    finally:
        conn.close()
    # Only venues foghorn actively scrapes are useful filter options. SFJAZZ is
    # seeded but deferred (Cloudflare) with no scraper, so it's excluded here.
    return [
        VenueView(
            slug=v.slug, name=v.name, neighborhood=v.neighborhood, region=v.region
        )
        for v in venues
        if v.slug in REGISTERED_SCRAPERS
    ]
