"""
backend/services/session_service.py
In-process shooting-session state shared by the API and realtime shot service.
"""

from __future__ import annotations

import asyncio

from backend.db.firebase import get_store
from backend.models.session import SessionSettings, SessionStatus


class SessionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session_number = 1
        self._shots_per_session = 10
        self._shot_count: int | None = None
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
        self._completed = False

    def _status_from_count(self, shot_count: int) -> SessionStatus:
        if shot_count >= self._shots_per_session:
            self._completed = True
        remaining = max(self._shots_per_session - shot_count, 0)
        return SessionStatus(
            session_id=self._session_id(),
            session_number=self._session_number,
            shots_per_session=self._shots_per_session,
            shot_count=shot_count,
            remaining=remaining,
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

    async def prepare_shot(self) -> tuple[str, int, int, int]:
        async with self._lock:
            shot_count = await self._count_current_locked()
            if self._completed or shot_count >= self._shots_per_session:
                self._completed = True
                raise ValueError("Session complete. Apply a new session before saving more shots.")
            self._shot_count = shot_count + 1
            return (
                self._session_id(),
                self._session_number,
                self._shot_count,
                self._shots_per_session,
            )

    async def finish_shot(self, session_id: str, shot_index: int) -> SessionStatus:
        async with self._lock:
            if session_id == self._session_id() and shot_index >= self._shots_per_session:
                self._completed = True
                return self._status_from_count(shot_index)
            shot_count = await self._count_current_locked()
            return self._status_from_count(shot_count)

    async def reset_current(self) -> tuple[str, int, SessionStatus]:
        async with self._lock:
            session_id = self._session_id()
            store = get_store()
            deleted = await store.delete_session(session_id)
            self._shot_count = 0
            self._completed = False
            return session_id, deleted, self._status_from_count(0)


session_manager = SessionManager()
