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
from datetime import datetime, timezone
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

    async def delete_session(self, session_id: str) -> int:
        async with self._lock:
            before = len(self._shots)
            self._shots = [s for s in self._shots if s.session_id != session_id]
            return before - len(self._shots)


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

    @staticmethod
    def _shot_from_doc(doc) -> ShotRecord:
        data = doc.to_dict() or {}
        data.setdefault("shot_id", doc.id)
        data.setdefault("timestamp", getattr(doc, "create_time", None))
        return ShotRecord.from_dict(data)

    @staticmethod
    def _created_at(doc) -> datetime:
        return getattr(doc, "create_time", None) or datetime.min.replace(tzinfo=timezone.utc)

    async def add_shot(self, shot: ShotRecord) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._col.document(shot.id).set(shot.to_storage_dict()))

    async def get_latest(self) -> Optional[ShotRecord]:
        loop = asyncio.get_event_loop()

        def _fetch():
            docs = list(self._col.stream())
            docs.sort(key=self._created_at, reverse=True)
            return docs[:1]

        docs = await loop.run_in_executor(None, _fetch)
        if not docs:
            return None
        return self._shot_from_doc(docs[0])

    async def get_history(
        self,
        limit:      int = 200,
        offset:     int = 0,
        session_id: str | None = None,
    ) -> tuple[list[ShotRecord], int]:
        loop = asyncio.get_event_loop()

        def _fetch():
            docs = list(self._col.stream())
            docs.sort(key=self._created_at, reverse=True)
            if session_id:
                records = [
                    self._shot_from_doc(d)
                    for d in docs
                    if d.to_dict().get("session_id") == session_id
                ]
                total = len(records)
                return records[offset : offset + limit], total
            total = len(docs)
            page = docs[offset : offset + limit]
            return [self._shot_from_doc(d) for d in page], total

        return await loop.run_in_executor(None, _fetch)

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

    async def delete_session(self, session_id: str) -> int:
        loop = asyncio.get_event_loop()

        def _delete():
            docs = list(self._col.where("session_id", "==", session_id).stream())
            if not docs:
                return 0
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
