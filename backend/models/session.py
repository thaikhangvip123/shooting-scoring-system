"""
backend/models/session.py
Pydantic models for shooting-session configuration and status.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionSettings(BaseModel):
    shots_per_session: int = Field(10, ge=5, le=15)


class SessionStatus(BaseModel):
    session_id: str
    session_number: int
    shots_per_session: int
    shot_count: int
    remaining: int
    completed: bool = False
