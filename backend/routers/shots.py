"""
backend/routers/shots.py
REST endpoints for shot registration and retrieval.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.models.shot import ShotCreate, ShotResponse, ShotHistoryResponse
from backend.services import shot_service
from backend.services.export_service import shots_to_csv, shots_to_pdf
from backend.db.firebase import get_store

router = APIRouter(prefix="", tags=["shots"])
# router = logger  # alias to keep variable name consistent


@router.post(
    "/shot",
    response_model=ShotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new shot from the CV pipeline",
)
async def post_shot(payload: ShotCreate) -> ShotResponse:
    try:
        return await shot_service.register_shot(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get(
    "/latest",
    response_model=ShotResponse | None,
    summary="Get the most recent shot",
)
async def get_latest() -> ShotResponse | None:
    return await shot_service.get_latest_shot()


@router.get(
    "/history",
    response_model=ShotHistoryResponse,
    summary="Get paginated shot history (newest first)",
)
async def get_history(
    limit:      int          = Query(200, ge=1,  le=2000),
    offset:     int          = Query(0,   ge=0),
    session_id: Optional[str]= Query(None),
) -> ShotHistoryResponse:
    return await shot_service.get_shot_history(limit, offset, session_id)


@router.delete(
    "/shots",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all shots (reset session)",
)
async def delete_shots():
    await shot_service.delete_all_shots()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ─── Export endpoints ─────────────────────────────────────────────────────────

@router.get("/export/csv", summary="Export shots as CSV")
async def export_csv(session_id: Optional[str] = Query(None)) -> Response:
    store        = get_store()
    shots, _     = await store.get_history(limit=10_000, session_id=session_id)
    csv_bytes    = shots_to_csv(shots)
    return Response(
        content      = csv_bytes,
        media_type   = "text/csv",
        headers      = {"Content-Disposition": "attachment; filename=shots.csv"},
    )


@router.get("/export/pdf", summary="Export PDF report")
async def export_pdf(session_id: Optional[str] = Query(None)) -> Response:
    store        = get_store()
    shots, _     = await store.get_history(limit=10_000, session_id=session_id)
    pdf_bytes    = shots_to_pdf(shots)
    return Response(
        content      = pdf_bytes,
        media_type   = "application/pdf",
        headers      = {"Content-Disposition": "attachment; filename=shoot-report.pdf"},
    )