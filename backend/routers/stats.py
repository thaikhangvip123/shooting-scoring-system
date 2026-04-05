"""
backend/routers/stats.py
Analytics endpoints: aggregated stats and heatmap grid.
"""

from typing import Optional

from fastapi import APIRouter, Query

from backend.models.stats import StatsResponse, HeatmapResponse
from backend.services.analytics_service import get_stats, get_heatmap

router = APIRouter(prefix="", tags=["analytics"])


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get aggregated shooting statistics",
)
async def stats_endpoint(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
) -> StatsResponse:
    return await get_stats(session_id)


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Get hit-density heatmap grid",
)
async def heatmap_endpoint(
    resolution: int = Query(50, ge=10, le=200, description="Grid size NxN"),
) -> HeatmapResponse:
    return await get_heatmap(resolution)