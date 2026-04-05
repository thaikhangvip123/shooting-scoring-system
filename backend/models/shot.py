"""
backend/models/shot.py
Pydantic models for Shot data — request, response, and DB shapes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Inbound (from CV pipeline) ───────────────────────────────────────────────

class ShotCreate(BaseModel):
    """Payload sent by the computer-vision module."""

    x_mm:       float = Field(..., description="X offset from target centre (mm)")
    y_mm:       float = Field(..., description="Y offset from target centre (mm)")
    timestamp:  datetime | None = Field(
        default=None,
        description="UTC timestamp; defaults to server time if omitted",
    )
    session_id: str | None = Field(default=None, max_length=64)
    metadata:   dict[str, Any] | None = Field(
        default=None,
        description="Free-form CV pipeline metadata (frame_id, confidence, etc.)",
    )

    @field_validator("x_mm", "y_mm")
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


# ─── Outbound (API responses) ─────────────────────────────────────────────────

class ShotResponse(BaseModel):
    """Full shot record returned by the API."""

    id:         str
    x_mm:       float
    y_mm:       float
    radius_mm:  float
    score:      int
    ring:       str
    timestamp:  datetime
    session_id: str | None = None
    metadata:   dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ShotHistoryResponse(BaseModel):
    shots:  list[ShotResponse]
    total:  int
    limit:  int
    offset: int


# ─── Internal (stored in Firebase / memory) ───────────────────────────────────

class ShotRecord(BaseModel):
    """Internal representation stored in the DB."""

    id:         str       = Field(default_factory=lambda: str(uuid.uuid4()))
    x_mm:       float
    y_mm:       float
    radius_mm:  float
    score:      int
    ring:       str
    timestamp:  datetime
    session_id: str | None = None
    metadata:   dict[str, Any] | None = None

    def to_response(self) -> ShotResponse:
        return ShotResponse(**self.model_dump())

    def to_dict(self) -> dict:
        """Serialise for Firebase (datetime → ISO string)."""
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ShotRecord:
        """Deserialise from Firebase document."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)