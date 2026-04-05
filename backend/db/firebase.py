"""
backend/db/firebase.py
Firebase Firestore wrapper with an in-memory fallback for local dev.
Set USE_FIREBASE=false in .env to skip Firebase and use the in-memory store.

Thread-safety: the in-memory store uses a simple list protected by asyncio.Lock.
In production use Firebase — it handles concurrency natively.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.config import get_settings
from backend.models.shot import ShotRecord

logger = logging.getLogger(__name__)

# ─── In-memory store (dev / test) ─────────────────────────────────────────────

class InMemoryStore:
    """Thread-safe in-memory shot store for local development."""

    def __init__(self) -> None:
        self._shots: list[ShotRecord] = []
        self._lock  = asyncio.Lock()

    async def add_shot(self, shot: ShotRecord) -> None:
        async with self._lock:
            self._shots.insert(0, shot)   # newest first

    async def get_latest(self) -> Optional[ShotRecord]:
        async with self._lock:
            return self._shots[0] if self._shots else None

    async def get_history(
        self,
        limit:      int = 200,
        offset:     int = 0,
        session_id: str | None = None,
    ) -> tuple[list[ShotRecord], int]:
        async with self._lock:
            src = self._shots
            if session_id:
                src = [s for s in src if s.session_id == session_id]
            total = len(src)
            return src[offset : offset + limit], total

    async def delete_all(self) -> int:
        async with self._lock:
            count = len(self._shots)
            self._shots.clear()
            return count


# ─── Firebase store ───────────────────────────────────────────────────────────

class FirebaseStore:
    """Wraps Firebase Admin Firestore for persistent storage."""

    COLLECTION = "shots"

    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        settings = get_settings()
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.firebase_creds_path)
            firebase_admin.initialize_app(cred, {"databaseURL": settings.firebase_db_url})

        self._db = firestore.client()
        self._col = self._db.collection(self.COLLECTION)

    async def add_shot(self, shot: ShotRecord) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._col.document(shot.id).set(shot.to_dict()))

    async def get_latest(self) -> Optional[ShotRecord]:
        loop = asyncio.get_event_loop()

        def _fetch():
            docs = (
                self._col
                .order_by("timestamp", direction="DESCENDING")
                .limit(1)
                .stream()
            )
            return list(docs)

        docs = await loop.run_in_executor(None, _fetch)
        if not docs:
            return None
        return ShotRecord.from_dict(docs[0].to_dict())

    async def get_history(
        self,
        limit:      int = 200,
        offset:     int = 0,
        session_id: str | None = None,
    ) -> tuple[list[ShotRecord], int]:
        loop = asyncio.get_event_loop()

        def _fetch():
            q = self._col.order_by("timestamp", direction="DESCENDING")
            if session_id:
                q = q.where("session_id", "==", session_id)
            # Firestore offset is approximate; use for pagination
            if offset:
                q = q.offset(offset)
            docs = list(q.limit(limit).stream())
            return [ShotRecord.from_dict(d.to_dict()) for d in docs]

        shots = await loop.run_in_executor(None, _fetch)
        # Total count (separate query for accuracy)
        total = len(shots) + offset   # approximation; replace with count() if Firestore v1
        return shots, total

    async def delete_all(self) -> int:
        loop = asyncio.get_event_loop()

        def _delete():
            docs  = list(self._col.stream())
            batch = self._db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
            return len(docs)

        return await loop.run_in_executor(None, _delete)


# ─── Factory ──────────────────────────────────────────────────────────────────

_store: InMemoryStore | FirebaseStore | None = None


def get_store() -> InMemoryStore | FirebaseStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.use_firebase:
            try:
                _store = FirebaseStore()
                logger.info("Using Firebase Firestore backend")
            except Exception as e:
                logger.warning("Firebase init failed (%s) — falling back to in-memory store", e)
                _store = InMemoryStore()
        else:
            logger.info("Using in-memory store (USE_FIREBASE=false)")
            _store = InMemoryStore()
    return _store