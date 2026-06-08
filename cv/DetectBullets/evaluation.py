import csv
import json
import os
import threading
import time
from datetime import datetime, timezone
from urllib import error, request


class DetectionRecorder:
    """
    Thread-safe CSV recorder for newly confirmed detections.

    CSV is enabled by setting SHOOT_EVAL_OUTPUT to a writable path.
    Realtime posting is opt-in via SHOOT_BACKEND_URL.
    """

    FIELDNAMES = [
        "detected_at_ms",
        "frame_idx",
        "target_type",
        "shotID",
        "x_px",
        "y_px",
        "radius",
        "scores",
    ]

    def __init__(self, csv_path: str | None = None, backend_url: str | None = None, session_id: str | None = None) -> None:
        self.csv_path = csv_path
        self.backend_url = backend_url
        self.session_id = session_id or os.getenv("SHOOT_SESSION_ID", "realtime")
        self._lock = threading.Lock()
        if self.csv_path:
            folder = os.path.dirname(self.csv_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.csv_path:
            return
        needs_header = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
        if not needs_header:
            return
        with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.FIELDNAMES)
            writer.writeheader()

    def record(
        self,
        *,
        frame_idx: int,
        target_type: str,
        bullet_id: int,
        x_px: float,
        y_px: float,
        radius: float,
        scores: int,
    ) -> None:
        detected_at_ms = int(time.time() * 1000)
        timestamp = datetime.now(timezone.utc).isoformat()
        row = {
            "detected_at_ms": detected_at_ms,
            "frame_idx": frame_idx,
            "target_type": target_type,
            "shotID": bullet_id,
            "x_px": round(float(x_px), 4),
            "y_px": round(float(y_px), 4),
            "radius": round(float(radius), 4),
            "scores": int(scores),
        }
        if self.csv_path:
            with self._lock:
                with open(self.csv_path, "a", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=self.FIELDNAMES)
                    writer.writerow(row)

        if self.backend_url:
            payload = {
                "x_px": row["x_px"],
                "y_px": row["y_px"],
                "timestamp": timestamp,
                "shotID": bullet_id,
                "scores": int(scores),
                "session_id": self.session_id,
                "metadata": {
                    "target_type": target_type,
                    "frame_id": frame_idx,
                    "detected_at_ms": detected_at_ms,
                    "radius_px": row["radius"],
                    "source": "cv_realtime",
                },
            }
            threading.Thread(target=self._post_payload, args=(payload,), daemon=True).start()

    def _post_payload(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.backend_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=2.0) as resp:
                resp.read()
        except error.HTTPError as exc:
            if exc.code != 409:
                print(f"[realtime] POST failed {exc.code}: {exc.reason}")
        except Exception as exc:
            print(f"[realtime] POST failed: {exc}")


def create_detection_recorder_from_env():
    csv_path = os.getenv("SHOOT_EVAL_OUTPUT", "").strip()
    backend_url = os.getenv("SHOOT_BACKEND_URL", "").strip()
    if os.getenv("SHOOT_REALTIME", "1").strip().lower() in {"0", "false", "no", "off"}:
        backend_url = ""
    if not csv_path and not backend_url:
        return None
    return DetectionRecorder(csv_path or None, backend_url or None)
