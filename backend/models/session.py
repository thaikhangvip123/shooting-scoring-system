"""
backend/models/session.py
Pydantic models for shooting-session configuration and status.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TargetType = Literal["TRON", "IPSC", "NGUOI"]
SessionState = Literal["idle", "running", "completed"]


class SessionSettings(BaseModel):
    shots_per_session: int = Field(10, ge=5, le=15)


class SessionStartRequest(BaseModel):
    target_type: TargetType = "TRON"


class SessionStatus(BaseModel):
    session_id: str
    session_number: int
    shots_per_session: int
    shot_count: int
    remaining: int
    status: SessionState = "idle"
    target_type: TargetType | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed: bool = False
