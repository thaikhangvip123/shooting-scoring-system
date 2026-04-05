"""
backend/services/analytics_service.py
Ballistic analytics: CEP, R50, group size, standard deviation, heatmap.
Uses numpy/scipy when available; pure-Python fallback otherwise.
"""

from __future__ import annotations

import math
import logging
from typing import Optional

import numpy as np
from scipy import stats as sp_stats

from backend.config import get_settings
from backend.db.firebase import get_store
from backend.models.shot import ShotRecord
from backend.models.stats import StatsResponse, HeatmapResponse, MeanPOI

logger = logging.getLogger(__name__)


# ─── Pure-math helpers ────────────────────────────────────────────────────────

def _radial(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def compute_cep(shots: list[ShotRecord]) -> float:
    """
    Circular Error Probable: median radial deviation from (0,0).
    For large samples this converges to the true CEP at confidence = 0.5.
    """
    if not shots:
        return 0.0
    radii = [_radial(s.x_mm, s.y_mm) for s in shots]
    return round(_median(radii), 3)


def compute_r50(shots: list[ShotRecord]) -> float:
    """
    R50: radius of smallest circle centred on group centroid
    that contains 50% of shots.
    """
    if not shots:
        return 0.0
    mx = sum(s.x_mm for s in shots) / len(shots)
    my = sum(s.y_mm for s in shots) / len(shots)
    radii = [_radial(s.x_mm - mx, s.y_mm - my) for s in shots]
    return round(_median(radii), 3)


def compute_group_size(shots: list[ShotRecord]) -> float:
    """
    Extreme spread: maximum distance between any two shots.
    O(n²) — acceptable for typical session sizes (≤ 1000 shots).
    """
    if len(shots) < 2:
        return 0.0
    pts = [(s.x_mm, s.y_mm) for s in shots]
    max_d = 0.0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = _radial(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
            if d > max_d:
                max_d = d
    return round(max_d, 3)


def compute_mean_poi(shots: list[ShotRecord]) -> MeanPOI:
    if not shots:
        return MeanPOI(x_mm=0.0, y_mm=0.0)
    return MeanPOI(
        x_mm=round(sum(s.x_mm for s in shots) / len(shots), 3),
        y_mm=round(sum(s.y_mm for s in shots) / len(shots), 3),
    )


def compute_std(shots: list[ShotRecord]) -> tuple[float, float]:
    """Standard deviation in X and Y (population std)."""
    if len(shots) < 2:
        return 0.0, 0.0
    xs = np.array([s.x_mm for s in shots])
    ys = np.array([s.y_mm for s in shots])
    return round(float(np.std(xs)), 3), round(float(np.std(ys)), 3)


def compute_ring_distribution(shots: list[ShotRecord]) -> dict[str, int]:
    labels = ["X", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "M"]
    dist   = {k: 0 for k in labels}
    for s in shots:
        key = s.ring if s.ring in dist else "M"
        dist[key] += 1
    return dist


# ─── Heatmap ──────────────────────────────────────────────────────────────────

def compute_heatmap(shots: list[ShotRecord], resolution: int = 50) -> list[list[int]]:
    """
    Build an NxN grid of hit counts.
    Cell [row][col] covers a 2R/N × 2R/N mm region.
    Row 0 = top (positive Y), col 0 = left (negative X).
    """
    R    = get_settings().target_radius_mm
    step = (2 * R) / resolution
    grid = [[0] * resolution for _ in range(resolution)]

    for s in shots:
        col = int((s.x_mm + R) / step)
        row = int((R - s.y_mm) / step)
        col = max(0, min(resolution - 1, col))
        row = max(0, min(resolution - 1, row))
        grid[row][col] += 1

    return grid


# ─── Main service function ────────────────────────────────────────────────────

async def get_stats(session_id: Optional[str] = None) -> StatsResponse:
    store         = get_store()
    shots, _total = await store.get_history(limit=10_000, session_id=session_id)

    if not shots:
        return StatsResponse(
            count=0, total_score=0, avg_score=0.0,
            cep_mm=0.0, r50_mm=0.0, group_size_mm=0.0,
            std_x_mm=0.0, std_y_mm=0.0,
            mean_poi=MeanPOI(x_mm=0.0, y_mm=0.0),
            hit_rate=0.0,
            ring_distribution=compute_ring_distribution([]),
            session_id=session_id,
        )

    total_score = sum(s.score for s in shots)
    hits        = [s for s in shots if s.score > 0]
    std_x, std_y = compute_std(shots)

    return StatsResponse(
        count            = len(shots),
        total_score      = total_score,
        avg_score        = round(total_score / len(shots), 3),
        cep_mm           = compute_cep(shots),
        r50_mm           = compute_r50(shots),
        group_size_mm    = compute_group_size(shots),
        std_x_mm         = std_x,
        std_y_mm         = std_y,
        mean_poi         = compute_mean_poi(shots),
        hit_rate         = round(len(hits) / len(shots), 4),
        ring_distribution= compute_ring_distribution(shots),
        session_id       = session_id,
    )


async def get_heatmap(resolution: int = 50) -> HeatmapResponse:
    store         = get_store()
    shots, _total = await store.get_history(limit=10_000)

    return HeatmapResponse(
        resolution       = resolution,
        target_radius_mm = get_settings().target_radius_mm,
        grid             = compute_heatmap(shots, resolution),
    )