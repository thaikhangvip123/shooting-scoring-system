"""
backend/services/shot_service.py
Core business logic: pixel-based scoring, duplicate detection, shot registration.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
import time
from datetime import datetime, timezone
from typing import Optional

from backend.config import get_settings
from backend.db.firebase import get_store
from backend.models.shot import ShotCreate, ShotHistoryResponse, ShotRecord, ShotResponse
from backend.services.session_service import session_manager

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
IPSC_POLYGON_PATH = ROOT_DIR / "cv" / "Scoring" / "IPSC" / "polygon.txt"
NGUOI_CONTOUR_PATH = ROOT_DIR / "cv" / "Scoring" / "Nguoi" / "Nguoi_contours.txt"

TRON_CENTER_PX = (1240.0, 1754.0)
TRON_RING_TABLE: list[tuple[float, int, str]] = [
    (51.0, 10, "X"),
    (141.0, 9, "9"),
    (235.5, 8, "8"),
    (330.0, 7, "7"),
    (424.5, 6, "6"),
    (519.0, 5, "5"),
    (613.5, 4, "4"),
    (708.0, 3, "3"),
    (802.5, 2, "2"),
    (897.0, 1, "1"),
]
IPSC_SCORES = [10, 5, 3, 10, 7]
IPSC_LABELS = ["A", "C", "D", "A2", "B"]
NGUOI_SCORES = [6, 7, 8, 9, 9, 10, 10]


def _load_point_sets(path: Path, prefix: str) -> list[list[tuple[float, float]]]:
    sets: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    if not path.exists():
        logger.warning("Target geometry file not found: %s", path)
        return sets

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(prefix):
            current = []
            sets.append(current)
            continue
        if line == "END":
            current = None
            continue
        if current is None:
            continue
        x, y = map(float, line.split(","))
        current.append((x, y))

    return [points for points in sets if len(points) >= 3]


def _polygon_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area / 2.0)


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_intersection = ((xj - xi) * (y - yi)) / (yj - yi) + xi
            if x < x_intersection:
                inside = not inside
        j = i
    return inside


IPSC_POLYGONS = _load_point_sets(IPSC_POLYGON_PATH, "polygon")
NGUOI_CONTOURS = _load_point_sets(NGUOI_CONTOUR_PATH, "contour")


def compute_score_tron(x_px: float, y_px: float) -> tuple[int, str, float]:
    dx = x_px - TRON_CENTER_PX[0]
    dy = y_px - TRON_CENTER_PX[1]
    radius = math.sqrt(dx * dx + dy * dy)
    for max_r, score, label in TRON_RING_TABLE:
        if radius <= max_r:
            return score, label, radius
    return 0, "M", radius


def compute_score_ipsc(x_px: float, y_px: float) -> tuple[int, str, None]:
    point = (x_px, y_px)
    for index, polygon in enumerate(IPSC_POLYGONS):
        if _point_in_polygon(point, polygon):
            return IPSC_SCORES[index], IPSC_LABELS[index], None
    return 0, "M", None


def compute_score_nguoi(x_px: float, y_px: float) -> tuple[int, str, None]:
    point = (x_px, y_px)
    best: tuple[int, float] | None = None
    for index, contour in enumerate(NGUOI_CONTOURS):
        if _point_in_polygon(point, contour):
            area = _polygon_area(contour)
            if best is None or area < best[1]:
                best = (index, area)
    if best is None:
        return 0, "M", None
    index = best[0]
    return NGUOI_SCORES[index], str(NGUOI_SCORES[index]), None


def compute_score(target_type: str, x_px: float, y_px: float) -> tuple[int, str, float | None]:
    normalized = target_type.upper()
    if normalized == "IPSC":
        return compute_score_ipsc(x_px, y_px)
    if normalized == "NGUOI":
        return compute_score_nguoi(x_px, y_px)
    return compute_score_tron(x_px, y_px)


class DuplicateGuard:
    """Simple in-process duplicate guard using pixel distance."""

    def __init__(self, min_px: float = 2.0, max_ms: int = 500) -> None:
        self._min_px = min_px
        self._max_ms = max_ms
        self._last: Optional[ShotRecord] = None

    def is_duplicate(self, shot: ShotCreate) -> bool:
        if self._last is None:
            return False
        shot_target = str((shot.metadata or {}).get("target_type", "TRON")).upper()
        last_target = str((self._last.metadata or {}).get("target_type", "TRON")).upper()
        if shot_target != last_target:
            return False

        now = shot.timestamp or datetime.now(timezone.utc)
        last = self._last.timestamp
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        dt_ms = abs((now - last).total_seconds() * 1000)
        if dt_ms > self._max_ms:
            return False

        dist = math.sqrt(
            (shot.x_px - self._last.x_px) ** 2 +
            (shot.y_px - self._last.y_px) ** 2
        )
        return dist < self._min_px

    def update(self, record: ShotRecord) -> None:
        self._last = record

    def reset(self) -> None:
        self._last = None


_guard = DuplicateGuard(
    min_px=get_settings().duplicate_min_mm,
    max_ms=get_settings().duplicate_max_ms,
)


async def register_shot(payload: ShotCreate) -> ShotResponse:
    received_at_ms = int(time.time() * 1000)
    if _guard.is_duplicate(payload):
        raise ValueError("Duplicate shot rejected (too close in space and time)")

    session_id, session_number, shot_index, shots_per_session = await session_manager.prepare_shot()

    metadata = dict(payload.metadata or {})
    target_type = str(metadata.get("target_type", "TRON")).upper()
    score, ring, radius = compute_score(target_type, payload.x_px, payload.y_px)
    metadata["target_type"] = target_type
    metadata["session_number"] = session_number
    metadata["shot_index"] = shot_index
    metadata["shots_per_session"] = shots_per_session
    if payload.session_id:
        metadata["source_session_id"] = payload.session_id
    if payload.shotID is not None:
        metadata["shotID"] = payload.shotID
    if payload.scores is not None:
        metadata["cv_score"] = payload.scores

    eval_meta = dict(metadata.get("eval") or {})
    eval_meta["backend_received_at_ms"] = received_at_ms
    metadata["eval"] = eval_meta

    record = ShotRecord(
        x_px=payload.x_px,
        y_px=payload.y_px,
        radius_px=round(radius, 4) if radius is not None else None,
        score=score,
        ring=ring,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
        session_id=session_id,
        metadata=metadata,
    )

    store = get_store()
    await store.add_shot(record)
    persisted_at_ms = int(time.time() * 1000)
    if record.metadata is not None:
        record.metadata.setdefault("eval", {})
        record.metadata["eval"]["backend_persisted_at_ms"] = persisted_at_ms
    _guard.update(record)
    await session_manager.finish_shot(session_id, shot_index)

    logger.info(
        "Shot registered id=%s target=%s score=%d ring=%s (%.1f, %.1f) px",
        record.id,
        target_type,
        score,
        ring,
        payload.x_px,
        payload.y_px,
    )

    return record.to_response()


async def get_latest_shot() -> Optional[ShotResponse]:
    store = get_store()
    record = await store.get_latest()
    return record.to_response() if record else None


async def get_shot_history(
    limit: int = 200,
    offset: int = 0,
    session_id: str | None = None,
) -> ShotHistoryResponse:
    store = get_store()
    shots, total = await store.get_history(limit, offset, session_id)
    return ShotHistoryResponse(
        shots=[s.to_response() for s in shots],
        total=total,
        limit=limit,
        offset=offset,
    )


async def delete_all_shots() -> int:
    store = get_store()
    return await store.delete_all()


async def reset_current_session() -> tuple[str, int]:
    session_id, deleted, _status = await session_manager.reset_current()
    reset_duplicate_guard()
    return session_id, deleted


def reset_duplicate_guard() -> None:
    _guard.reset()
