"""FastAPI HTTP surface.

``app`` is the ASGI entry point: ``uvicorn foghorn.api:app --reload`` (or
``make backend-run``). On startup it ensures the four venues are seeded so a
fresh DB serves correctly. Phase 2.1 ships ``GET /api/shows``; date-range /
region / performer-search params (Phase 3) and the scrape-health endpoint
(Phase 2.3) extend this surface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from foghorn.api.shows import router as shows_router
from foghorn.repo import db
from foghorn.repo.seed_venues import seed


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    conn = db.connect()
    try:
        seed(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="foghorn", lifespan=lifespan)
app.include_router(shows_router)
