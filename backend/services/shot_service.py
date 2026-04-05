"""
backend/services/shot_service.py
Core business logic: scoring, duplicate detection, shot registration.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.config import get_settings
from backend.db.firebase import get_store
from backend.models.shot import ShotCreate, ShotRecord, ShotResponse, ShotHistoryResponse

logger = logging.getLogger(__name__)

# ─── Ring definitions ─────────────────────────────────────────────────────────
# Each tuple: (max_radius_mm, score, ring_label)
RING_TABLE: list[tuple[float, int, str]] = [
    ( 11.25, 10, "X" ),
    ( 22.5,  10, "10"),
    ( 45.0,   9, "9" ),
    ( 67.5,   8, "8" ),
    ( 90.0,   7, "7" ),
    (112.5,   6, "6" ),
    (135.0,   5, "5" ),
    (157.5,   4, "4" ),
    (180.0,   3, "3" ),
    (202.5,   2, "2" ),
    (225.0,   1, "1" ),
]


def compute_score(x_mm: float, y_mm: float) -> tuple[int, str, float]:
    """
    Compute score and ring label for a hit position.

    Returns:
        (score, ring_label, radius_mm)
    """
    radius = math.sqrt(x_mm ** 2 + y_mm ** 2)
    for max_r, score, label in RING_TABLE:
        if radius <= max_r:
            return score, label, radius
    return 0, "M", radius    # Miss


# ─── Duplicate guard ──────────────────────────────────────────────────────────

class DuplicateGuard:
    """
    Simple in-process deduplication.
    Rejects a new shot if it lands within `min_mm` of the most recent shot
    and arrives within `max_ms` milliseconds.

    NOTE: For multi-process deployments, move this state to Redis.
    """

    def __init__(self, min_mm: float = 2.0, max_ms: int = 500) -> None:
        self._min_mm = min_mm
        self._max_ms = max_ms
        self._last:  Optional[ShotRecord] = None

    def is_duplicate(self, shot: ShotCreate) -> bool:
        if self._last is None:
            return False

        # Time guard
        now  = shot.timestamp or datetime.now(timezone.utc)
        last = self._last.timestamp
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        dt_ms = abs((now - last).total_seconds() * 1000)
        if dt_ms > self._max_ms:
            return False

        # Distance guard
        dist = math.sqrt(
            (shot.x_mm - self._last.x_mm) ** 2 +
            (shot.y_mm - self._last.y_mm) ** 2
        )
        return dist < self._min_mm

    def update(self, record: ShotRecord) -> None:
        self._last = record


_guard = DuplicateGuard(
    min_mm=get_settings().duplicate_min_mm,
    max_ms=get_settings().duplicate_max_ms,
)


# ─── Service functions ────────────────────────────────────────────────────────

async def register_shot(payload: ShotCreate) -> ShotResponse:
    """
    Validate, score, deduplicate, and persist a new shot.
    Raises ValueError on duplicate detection.
    """
    if _guard.is_duplicate(payload):
        raise ValueError("Duplicate shot rejected (too close in space and time)")

    score, ring, radius = compute_score(payload.x_mm, payload.y_mm)

    record = ShotRecord(
        x_mm       = payload.x_mm,
        y_mm       = payload.y_mm,
        radius_mm  = round(radius, 4),
        score      = score,
        ring       = ring,
        timestamp  = payload.timestamp or datetime.now(timezone.utc),
        session_id = payload.session_id,
        metadata   = payload.metadata,
    )

    store = get_store()
    await store.add_shot(record)
    _guard.update(record)

    logger.info(
        "Shot registered id=%s score=%d ring=%s (%.1f, %.1f) r=%.1f mm",
        record.id, score, ring, payload.x_mm, payload.y_mm, radius,
    )

    return record.to_response()


async def get_latest_shot() -> Optional[ShotResponse]:
    store  = get_store()
    record = await store.get_latest()
    return record.to_response() if record else None


async def get_shot_history(
    limit:      int = 200,
    offset:     int = 0,
    session_id: str | None = None,
) -> ShotHistoryResponse:
    store          = get_store()
    shots, total   = await store.get_history(limit, offset, session_id)
    return ShotHistoryResponse(
        shots  = [s.to_response() for s in shots],
        total  = total,
        limit  = limit,
        offset = offset,
    )


async def delete_all_shots() -> int:
    store = get_store()
    return await store.delete_all()