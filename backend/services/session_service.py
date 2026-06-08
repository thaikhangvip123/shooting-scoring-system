"""
backend/services/session_service.py
In-process shooting-session state shared by the API and realtime shot service.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.db.firebase import get_store
from backend.models.session import SessionSettings, SessionStartRequest, SessionStatus, SessionState, TargetType


class SessionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session_number = 1
        self._shots_per_session = 10
        self._shot_count: int | None = None
        self._status: SessionState = "idle"
        self._target_type: TargetType | None = None
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._completed = False

    def _session_id(self) -> str:
        return f"session-{self._session_number}"

    async def _count_current_locked(self) -> int:
        if self._shot_count is not None:
            return self._shot_count
        store = get_store()
        shots, _ = await store.get_history(limit=10_000, session_id=self._session_id())
        self._shot_count = len(shots)
        return self._shot_count

    def _advance_locked(self) -> None:
        self._session_number += 1
        self._shot_count = 0
        self._status = "idle"
        self._target_type = None
        self._started_at = None
        self._completed_at = None
        self._completed = False

    def _status_from_count(self, shot_count: int) -> SessionStatus:
        if self._status == "running" and shot_count >= self._shots_per_session:
            self._completed = True
            self._status = "completed"
            if self._completed_at is None:
                self._completed_at = datetime.now(timezone.utc)
        elif self._status == "completed":
            self._completed = True
        else:
            self._completed = False
        remaining = max(self._shots_per_session - shot_count, 0)
        return SessionStatus(
            session_id=self._session_id(),
            session_number=self._session_number,
            shots_per_session=self._shots_per_session,
            shot_count=shot_count,
            remaining=remaining,
            status=self._status,
            target_type=self._target_type,
            started_at=self._started_at,
            completed_at=self._completed_at,
            completed=self._completed,
        )

    async def get_status(self) -> SessionStatus:
        async with self._lock:
            shot_count = await self._count_current_locked()
            return self._status_from_count(shot_count)

    async def update_settings(self, settings: SessionSettings) -> SessionStatus:
        async with self._lock:
            if self._completed:
                self._advance_locked()
            self._shots_per_session = settings.shots_per_session
            shot_count = await self._count_current_locked()
            if shot_count >= self._shots_per_session:
                self._completed = True
            return self._status_from_count(shot_count)

    async def start(self, request: SessionStartRequest) -> SessionStatus:
        async with self._lock:
            if self._status == "completed":
                self._advance_locked()
            shot_count = await self._count_current_locked()
            self._status = "running"
            self._target_type = request.target_type
            self._started_at = datetime.now(timezone.utc)
            self._completed_at = None
            self._completed = False
            return self._status_from_count(shot_count)

    async def prepare_shot(self, target_type: str) -> tuple[str, int, int, int, TargetType | None]:
        async with self._lock:
            shot_count = await self._count_current_locked()
            if self._status != "running":
                raise ValueError("Session is not running. Start Session before saving shots.")
            normalized_target = target_type.upper()
            if self._target_type is not None and normalized_target != self._target_type:
                raise ValueError(f"Shot target {normalized_target} does not match active session target {self._target_type}.")
            if self._completed or shot_count >= self._shots_per_session:
                self._completed = True
                self._status = "completed"
                if self._completed_at is None:
                    self._completed_at = datetime.now(timezone.utc)
                raise ValueError("Session complete. Start a new session before saving more shots.")
            self._shot_count = shot_count + 1
            return (
                self._session_id(),
                self._session_number,
                self._shot_count,
                self._shots_per_session,
                self._target_type,
            )

    async def finish_shot(self, session_id: str, shot_index: int) -> SessionStatus:
        async with self._lock:
            if session_id == self._session_id() and shot_index >= self._shots_per_session:
                self._completed = True
                self._status = "completed"
                if self._completed_at is None:
                    self._completed_at = datetime.now(timezone.utc)
                return self._status_from_count(shot_index)
            shot_count = await self._count_current_locked()
            return self._status_from_count(shot_count)

    async def reset_current(self) -> tuple[str, int, SessionStatus]:
        async with self._lock:
            session_id = self._session_id()
            store = get_store()
            deleted = await store.delete_session(session_id)
            self._shot_count = 0
            self._status = "idle"
            self._target_type = None
            self._started_at = None
            self._completed_at = None
            self._completed = False
            return session_id, deleted, self._status_from_count(0)


session_manager = SessionManager()
