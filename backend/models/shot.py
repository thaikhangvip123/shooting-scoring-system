"""
backend/models/shot.py
Pydantic models for shot data: request, response, and DB shapes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ShotCreate(BaseModel):
    """Payload sent by the computer-vision module."""

    x_px: float = Field(..., description="X coordinate in the CV target image (pixels)")
    y_px: float = Field(..., description="Y coordinate in the CV target image (pixels)")
    shotID: int | str | None = Field(default=None, description="CV bullet tracker ID")
    scores: int | None = Field(default=None, description="Score calculated by the CV module")
    timestamp: datetime | None = Field(
        default=None,
        description="UTC timestamp; defaults to server time if omitted",
    )
    session_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Free-form CV pipeline metadata, including target_type",
    )

    @field_validator("x_px", "y_px")
    @classmethod
    def finite_float(cls, v: float) -> float:
        import math

        if not math.isfinite(v):
            raise ValueError("Coordinate must be a finite number")
        return round(v, 4)

    @model_validator(mode="after")
    def set_default_timestamp(self) -> ShotCreate:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        return self


class ShotResponse(BaseModel):
    """Full shot record returned by the API."""

    id: str
    x_px: float
    y_px: float
    radius_px: float | None = None
    score: int
    ring: str
    timestamp: datetime
    session_id: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ShotHistoryResponse(BaseModel):
    shots: list[ShotResponse]
    total: int
    limit: int
    offset: int


class ShotRecord(BaseModel):
    """Internal representation stored in the DB."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    x_px: float
    y_px: float
    radius_px: float | None = None
    score: int
    ring: str
    timestamp: datetime
    session_id: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def x_mm(self) -> float:
        return self.x_px

    @property
    def y_mm(self) -> float:
        return self.y_px

    @property
    def radius_mm(self) -> float:
        return self.radius_px or 0.0

    def to_response(self) -> ShotResponse:
        return ShotResponse(**self.model_dump())

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_storage_dict(self) -> dict:
        metadata = self.metadata or {}
        return {
            "shot_id": self.id,
            "score": self.score,
            "session_id": self.session_id,
            "target_type": str(metadata.get("target_type", "TRON")).upper(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ShotRecord:
        if "id" not in data and "shot_id" in data:
            data["id"] = data["shot_id"]
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if "x_px" not in data and "x_mm" in data:
            data["x_px"] = data.pop("x_mm")
        if "y_px" not in data and "y_mm" in data:
            data["y_px"] = data.pop("y_mm")
        if "radius_px" not in data and "radius_mm" in data:
            data["radius_px"] = data.pop("radius_mm")
        if "metadata" not in data and "target_type" in data:
            data["metadata"] = {"target_type": data["target_type"]}
        data.setdefault("x_px", 0.0)
        data.setdefault("y_px", 0.0)
        data.setdefault("ring", str(data.get("score", "")))
        if data.get("timestamp") is None:
            data["timestamp"] = datetime.now(timezone.utc)
        return cls(**data)
