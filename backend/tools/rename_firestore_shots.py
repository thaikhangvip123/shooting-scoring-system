"""
Rename Firestore shot documents from UUID-style IDs to readable IDs.

Preview:
    python backend/tools/rename_firestore_shots.py --dry-run

Apply:
    python backend/tools/rename_firestore_shots.py --commit
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CREDS = ROOT_DIR / "backend" / "serviceAccountKey.json"
COLLECTION = "shots"


def _created_at(doc) -> datetime:
    return getattr(doc, "create_time", None) or datetime.min.replace(tzinfo=timezone.utc)


def _target_type(data: dict[str, Any]) -> str:
    metadata = data.get("metadata") or {}
    return str(data.get("target_type") or metadata.get("target_type") or "TRON").upper()


def _shot_index(data: dict[str, Any]) -> int | None:
    metadata = data.get("metadata") or {}
    raw = data.get("shot_index") or metadata.get("shot_index")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _is_readable_id(doc_id: str) -> bool:
    parts = doc_id.split("-shot-")
    return len(parts) == 2 and parts[0].startswith("session-") and parts[1].isdigit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--creds", default=str(DEFAULT_CREDS), help="Firebase service account JSON path")
    parser.add_argument("--commit", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    args = parser.parse_args()

    if not args.commit and not args.dry_run:
        parser.error("Choose --dry-run or --commit")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(args.creds))

    db = firestore.client()
    docs = list(db.collection(COLLECTION).stream())
    grouped = defaultdict(list)
    for doc in docs:
        data = doc.to_dict() or {}
        grouped[data.get("session_id") or "session-unknown"].append((doc, data))

    changes = []
    for session_id, items in grouped.items():
        items.sort(key=lambda item: _created_at(item[0]))
        used_ids = {doc.id for doc, _data in items}
        for fallback_index, (doc, data) in enumerate(items, 1):
            if _is_readable_id(doc.id):
                continue
            index = _shot_index(data) or fallback_index
            new_id = f"{session_id}-shot-{index:02d}"
            if new_id in used_ids:
                new_id = f"{new_id}-{doc.id[:8]}"
            used_ids.add(new_id)
            new_data = {
                "shot_id": new_id,
                "score": int(data.get("score", 0)),
                "session_id": session_id,
                "target_type": _target_type(data),
            }
            changes.append((doc.id, new_id, new_data))

    if not changes:
        print("No UUID-style shot documents to rename.")
        return

    for old_id, new_id, data in changes:
        print(f"{old_id} -> {new_id}: {data}")

    if not args.commit:
        print(f"Dry run only. {len(changes)} document(s) would be renamed.")
        return

    batch = db.batch()
    collection = db.collection(COLLECTION)
    for old_id, new_id, data in changes:
        batch.set(collection.document(new_id), data)
        batch.delete(collection.document(old_id))
    batch.commit()
    print(f"Renamed {len(changes)} document(s).")


if __name__ == "__main__":
    main()
