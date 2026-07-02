"""``PUT /api/performers/{canonical_name}/origin`` — manual local/touring tag.

The heuristic bootstrap (``foghorn.tagging.origin``) is conservative and
wrong sometimes; this is the correction path. A manual set (or clear) is
recorded with ``origin_source='manual'`` and is permanent — the heuristic
never overwrites manual rows. Single-tenant, no auth, same posture as the
watchlist endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from foghorn.models import Origin
from foghorn.repo import db
from foghorn.repo import performers as performers_repo

router = APIRouter()


class OriginUpdate(BaseModel):
    origin: Origin | None  # null = deliberately unknown (heuristic stays off)


class PerformerOriginView(BaseModel):
    display_name: str
    canonical_name: str
    origin: str | None
    origin_source: str | None


@router.put(
    "/api/performers/{canonical_name}/origin",
    response_model=PerformerOriginView,
)
def set_origin(canonical_name: str, update: OriginUpdate) -> PerformerOriginView:
    conn = db.connect()
    try:
        performer = performers_repo.set_origin(
            conn, canonical_name, update.origin, "manual"
        )
    finally:
        conn.close()
    if performer is None:
        raise HTTPException(status_code=404, detail="unknown performer")
    return PerformerOriginView(
        display_name=performer.display_name,
        canonical_name=performer.canonical_name,
        origin=performer.origin,
        origin_source=performer.origin_source,
    )
