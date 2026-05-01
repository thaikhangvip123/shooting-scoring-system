"""
state.py — Per-target mutable state container.

Each target (BIA_TRON, BIA_IPSC, BIA_NGUOI) owns one TargetState instance
that holds the rolling background model, homography cache, tracking dicts,
and a thread-safe lock for the worker threads.
"""

import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import CFG, DST_POINTS
from scoring import calculate_score
from coords import px_to_score_px


class TargetState:
    """All mutable state for a single shooting target."""

    def __init__(self, name: str):
        self.name = name

        # ── Background model ────────────────────────────────────────────
        self.bg_float:    Optional[np.ndarray] = None   # float32 rolling BG
        self.noise_std:   float = 20.0                  # estimated noise sigma
        self.noise_ready: bool  = False
        self.warmup_diffs: List[np.ndarray] = []
        self.warmup_count: int  = 0

        # ── Homography cache ────────────────────────────────────────────
        self.H_cached:   Optional[np.ndarray] = None
        self.H_src_prev: Optional[np.ndarray] = None

        # ── Tracking ────────────────────────────────────────────────────
        # candidates: detections seen < confirm_frames times
        # confirmed:  stable bullet holes (score cached)
        self.candidates: Dict[int, dict] = {}
        self.confirmed:  Dict[int, dict] = {}
        self.next_id: int = 0

        # ── Thread safety ───────────────────────────────────────────────
        self.lock = threading.Lock()

        # ── Display ─────────────────────────────────────────────────────
        self.display_frame: Optional[np.ndarray] = None
        self.result_ready   = threading.Event()

    # ── Homography cache ────────────────────────────────────────────────────

    def get_homography(self, src_pts: np.ndarray) -> Optional[np.ndarray]:
        """
        Return a cached homography if markers haven't drifted, otherwise
        recompute with RANSAC and cache the result.
        """
        if self.H_src_prev is not None:
            drift = np.max(np.linalg.norm(src_pts - self.H_src_prev, axis=1))
            if drift < CFG.homography_drift_thresh and self.H_cached is not None:
                return self.H_cached

        H, _ = cv2.findHomography(src_pts, DST_POINTS, cv2.RANSAC, 3.0)
        if H is None:
            return self.H_cached          # keep old if RANSAC fails
        self.H_cached   = H
        self.H_src_prev = src_pts.copy()
        return H

    # ── Background model ────────────────────────────────────────────────────

    def update_background(self, warped_gray: np.ndarray) -> None:
        """
        Incrementally update the rolling background model.
        During warmup: collect frames to estimate per-pixel noise.
        After warmup:  exponential moving average, skipping confirmed bullet regions.
        """
        if self.bg_float is None:
            self.bg_float = warped_gray.astype(np.float32)
            return

        if not self.noise_ready:
            diff = warped_gray.astype(np.float32) - self.bg_float
            self.warmup_diffs.append(diff)
            self.warmup_count += 1
            if self.warmup_count >= CFG.bg_warmup_frames:
                stack = np.stack(self.warmup_diffs, axis=0)
                self.noise_std  = float(np.std(stack))
                self.noise_ready = True
                self.warmup_diffs.clear()
                print(f"[{self.name}] Noise σ = {self.noise_std:.1f} → "
                      f"dark thresh = {-CFG.sigma_mult * self.noise_std:.1f}  "
                      f"bright thresh = +{CFG.sigma_mult * self.noise_std:.1f}")
            return   # do NOT update BG during warmup

        # Mask: exclude confirmed bullet holes from BG learning
        bullet_mask = np.zeros(warped_gray.shape, dtype=bool)
        for v in self.confirmed.values():
            cx, cy = int(v["pos"][0]), int(v["pos"][1])
            rr     = CFG.expected_radius + 12
            y0 = max(0, cy - rr);  y1 = min(warped_gray.shape[0], cy + rr)
            x0 = max(0, cx - rr);  x1 = min(warped_gray.shape[1], cx + rr)
            bullet_mask[y0:y1, x0:x1] = True

        upd = ~bullet_mask
        fg  = warped_gray.astype(np.float32)
        self.bg_float[upd] = (
            self.bg_float[upd] * (1.0 - CFG.bg_alpha)
            + fg[upd] * CFG.bg_alpha
        )

    def get_bg_u8(self) -> Optional[np.ndarray]:
        if self.bg_float is None:
            return None
        return np.clip(self.bg_float, 0, 255).astype(np.uint8)

    def get_thresholds(self) -> Tuple[float, float]:
        """Return (dark_thresh, bright_thresh) for signed-diff detection."""
        if self.noise_ready:
            t = CFG.sigma_mult * self.noise_std
            return -t, t
        return float(CFG.dark_thresh_fallback), float(CFG.bright_thresh_fallback)

    # ── Score lookup for a confirmed bullet ─────────────────────────────────

    def compute_and_cache_score(self, bullet_id: int) -> int:
        """Compute score for a confirmed bullet and cache it in-place."""
        cx, cy = self.confirmed[bullet_id]["pos"]
        score_pt = px_to_score_px(cx, cy)
        score    = calculate_score(self.name, score_pt)
        self.confirmed[bullet_id]["score"] = score
        return score

    def total_score(self) -> int:
        return sum(v.get("score", 0) for v in self.confirmed.values())


# ── Lazy import fix (cv2 needed inside get_homography) ──────────────────────
import cv2   # noqa: E402  (placed here to avoid circular imports at module level)


# ── Global registry ─────────────────────────────────────────────────────────
target_states: Dict[str, TargetState] = {
    "BIA_TRON":  TargetState("BIA_TRON"),
    "BIA_IPSC":  TargetState("BIA_IPSC"),
    "BIA_NGUOI": TargetState("BIA_NGUOI"),
}
