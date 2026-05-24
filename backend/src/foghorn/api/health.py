"""``GET /api/health/scrape`` — did last night's refresh run, and did anything
break? Reads the most-recent ``scrape_runs`` row + its per-venue breakdown.

503 (``{"error": "no_scrape_runs_yet"}``) when no run has been recorded yet —
distinct from "ran but a venue failed" (200 with that venue's ``errors``
populated).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from foghorn.repo import db
from foghorn.repo import scrape_runs as scrape_runs_repo

router = APIRouter()


class ScrapeVenueHealth(BaseModel):
    slug: str
    started_at: str
    finished_at: str
    created: int
    updated: int
    errors: list[str]


class ScrapeHealth(BaseModel):
    last_run_at: str
    last_run_finished_at: str
    venues: list[ScrapeVenueHealth]


@router.get("/api/health/scrape")
def scrape_health() -> JSONResponse:
    conn = db.connect()
    try:
        run = scrape_runs_repo.latest(conn)
    finally:
        conn.close()
    if run is None:
        return JSONResponse(
            status_code=503, content={"error": "no_scrape_runs_yet"}
        )
    health = ScrapeHealth(
        last_run_at=run.started_at,
        last_run_finished_at=run.finished_at,
        venues=[
            ScrapeVenueHealth(
                slug=v.venue_slug,
                started_at=v.started_at,
                finished_at=v.finished_at,
                created=v.created,
                updated=v.updated,
                errors=v.errors,
            )
            for v in run.venues
        ],
    )
    return JSONResponse(content=health.model_dump())
