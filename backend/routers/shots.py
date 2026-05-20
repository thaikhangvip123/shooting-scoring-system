"""
backend/routers/shots.py
REST endpoints for shot registration and retrieval.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.models.session import SessionSettings, SessionStartRequest, SessionStatus
from backend.models.shot import ShotCreate, ShotResponse, ShotHistoryResponse
from backend.services import shot_service
from backend.services.session_service import session_manager
from backend.services.export_service import shots_to_csv, shots_to_pdf
from backend.db.firebase import get_store
from backend.routers.websocket import manager as ws_manager

router = APIRouter(prefix="", tags=["shots"])
# router = logger  # alias to keep variable name consistent

TARGET_NAME_MAP = {
    "TRON": "BIA_TRON",
    "IPSC": "BIA_IPSC",
    "NGUOI": "BIA_NGUOI",
    "BIA_TRON": "BIA_TRON",
    "BIA_IPSC": "BIA_IPSC",
    "BIA_NGUOI": "BIA_NGUOI",
}


def _to_cv_target(target_type: str | None) -> str:
    normalized = (target_type or "TRON").strip().upper()
    return TARGET_NAME_MAP.get(normalized, "BIA_TRON")


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
    current_session: bool    = Query(False),
) -> ShotHistoryResponse:
    if current_session:
        session_id = (await session_manager.get_status()).session_id
    return await shot_service.get_shot_history(limit, offset, session_id)


@router.delete(
    "/shots",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete shots in the current session",
)
async def delete_shots():
    session_id, deleted = await shot_service.reset_current_session()
    if ws_manager.client_count > 0:
        session = await session_manager.get_status()
        await ws_manager.broadcast({
            "type": "session_reset",
            "session_id": session_id,
            "deleted": deleted,
            "session": session.model_dump(),
        })
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/session",
    response_model=SessionStatus,
    summary="Get current shooting session status",
)
async def get_session() -> SessionStatus:
    return await session_manager.get_status()


@router.put(
    "/session",
    response_model=SessionStatus,
    summary="Update shots per session",
)
async def update_session(settings: SessionSettings) -> SessionStatus:
    session = await session_manager.update_settings(settings)
    if ws_manager.client_count > 0:
        await ws_manager.broadcast({
            "type": "session_updated",
            "session": session.model_dump(),
        })
    return session


@router.post(
    "/session/start",
    response_model=SessionStatus,
    summary="Start CV detection for the selected target",
)
async def start_session(payload: SessionStartRequest) -> SessionStatus:
    session = await session_manager.get_status()
    target = _to_cv_target(payload.target_type)
    if ws_manager.client_count > 0:
        await ws_manager.broadcast({
            "type": "cv_start",
            "target": target,
            "target_type": payload.target_type,
            "session": session.model_dump(),
        })
    return session

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
