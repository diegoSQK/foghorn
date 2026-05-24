"""FastAPI HTTP surface.

``app`` is the ASGI entry point: ``uvicorn foghorn.api:app --reload`` (or
``make backend-run``). On startup it seeds the venues so a fresh DB serves
correctly, and starts the nightly scrape scheduler (unless disabled via
``FOGHORN_DISABLE_SCHEDULER``). Serves ``GET /api/shows`` (Phase 2.1) and
``GET /api/health/scrape`` (Phase 2.3); filters/search (Phase 3) and the
watchlist (Phase 4) extend this surface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from foghorn.api.health import router as health_router
from foghorn.api.shows import router as shows_router
from foghorn.api.venues import router as venues_router
from foghorn.repo import db
from foghorn.repo.seed_venues import seed
from foghorn.scheduler.runner import start_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    conn = db.connect()
    try:
        seed(conn)
    finally:
        conn.close()
    scheduler = start_scheduler()  # None when disabled (e.g. tests)
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="foghorn", lifespan=lifespan)
app.include_router(shows_router)
app.include_router(venues_router)
app.include_router(health_router)
