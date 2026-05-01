"""
worker.py — Per-target processing worker (runs in a ThreadPoolExecutor thread).

Responsibilities:
  1. Warp the raw frame using cached homography
  2. Update rolling background model
  3. Run Layer 1 → Layer 2 → Layer 3
  4. Draw debug overlay with VISIBLE bullet holes:
       - Confirmed bullets: green circle + red centre dot + score label
       - Candidates (unconfirmed): semi-transparent cyan circle
       - Shadow blobs: RED double-ring (was yellow in V1)
  5. Write the resized display frame into state.display_frame
"""

import time
from typing import Dict, Tuple

import cv2
import numpy as np

from config import CFG, TARGET_SETS, DST_POINTS
from state import TargetState, target_states
from aruco_utils import get_src_points
from layer1 import process_layer_1
from layer2 import process_layer_2
from layer3 import temporal_tracking


# ── Drawing helpers ──────────────────────────────────────────────────────────

def _draw_shadow(frame: np.ndarray, cx: int, cy: int) -> None:
    """
    Draw a RED double-ring for shadow / ambiguous blobs.
    Much more visible than the old yellow single circle.
    Outer ring thick → easy to see even at display_scale.
    """
    cv2.circle(frame, (cx, cy), 30, (0,   0, 200), 3)   # dark-red outer
    cv2.circle(frame, (cx, cy), 22, (0,   0, 255), 2)   # bright-red inner
    cv2.circle(frame, (cx, cy),  3, (0,   0, 255), -1)  # centre dot


def _draw_candidate(frame: np.ndarray, cx: int, cy: int, r: int) -> None:
    """Cyan thin ring for detections not yet confirmed (< confirm_frames seen)."""
    cv2.circle(frame, (cx, cy), r + 4, (255, 255, 0), 1)


def _draw_confirmed(frame: np.ndarray,
                    cx: int, cy: int, r: int, score: int) -> None:
    """
    Green ring + red fill dot + white score label for confirmed bullet holes.
    Two-pass drawing (thick background stroke + thin foreground) makes the
    circle visible against both light and dark paper.
    """
    # Outer glow: slightly larger, semi-opaque white ring
    cv2.circle(frame, (cx, cy), r + 5, (255, 255, 255), 2)
    # Main green circle
    cv2.circle(frame, (cx, cy), r,     (0,   220,   0), 3)
    # Centre dot (red)
    cv2.circle(frame, (cx, cy), 4,     (0,   0,   255), -1)

    # Score label — black shadow + white text for contrast on any background
    label_pos = (cx + r + 6, cy - 6)
    cv2.putText(frame, str(score), label_pos,
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 4)
    cv2.putText(frame, str(score), label_pos,
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)


# ── Worker ───────────────────────────────────────────────────────────────────

def process_target(target_name: str,
                   frame:        np.ndarray,
                   marker_dict:  Dict[int, np.ndarray],
                   frame_idx:    int,
                   now:          float) -> None:
    """
    Full detection + drawing pipeline for one target.
    Called from a ThreadPoolExecutor worker thread.
    Result written to state.display_frame (thread-safe via state.lock).
    """
    state  = target_states[target_name]
    id_set = TARGET_SETS[target_name]

    # ── Homography warp ──────────────────────────────────────────────────────
    src_pts = get_src_points(marker_dict, id_set)
    if src_pts is None:
        return   # markers not visible this frame

    H = state.get_homography(src_pts)
    if H is None:
        return

    warped      = cv2.warpPerspective(frame, H, (CFG.width, CFG.height))
    warped_gray = cv2.GaussianBlur(
        cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (7, 7), 0
    )

    with state.lock:
        # ── Background update ────────────────────────────────────────────────
        state.update_background(warped_gray)

        # Still collecting warmup frames — show plain warped image
        if not state.noise_ready:
            msg = f"Warming up... {state.warmup_count}/{CFG.bg_warmup_frames}"
            cv2.putText(warped, msg, (50, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
            disp = cv2.resize(warped, (0, 0),
                              fx=CFG.display_scale, fy=CFG.display_scale)
            state.display_frame = disp
            state.result_ready.set()
            return

        # ── Layer 1: signed diff → candidate blobs ───────────────────────────
        candidates, dark_mask = process_layer_1(state, warped_gray)

        # ── Layer 2: circle fitting on each blob ─────────────────────────────
        raw_circles = []

        for cand in candidates:
            contour   = cand["contour"]
            label     = cand["label"]
            blob_mask = cand.get("blob_mask")

            # Draw faint contour outline so we can see what Layer 1 found
            cv2.drawContours(warped, [contour], -1, (180, 180, 180), 1)

            if label == "bullet_candidate":
                circles = process_layer_2(contour, blob_mask)
                raw_circles.extend(circles)

                # Draw unconfirmed circle positions as thin cyan rings
                for cx, cy, r in circles:
                    _draw_candidate(warped, cx, cy, r)

            elif label == "shadow_candidate":
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    _draw_shadow(warped, cx, cy)

        # ── Layer 3: temporal tracking ────────────────────────────────────────
        confirmed_positions = temporal_tracking(state, raw_circles, now)

        # ── Draw confirmed bullets ────────────────────────────────────────────
        for (cx, cy, r) in confirmed_positions:
            # Look up the cached score for this bullet
            score = 0
            for v in state.confirmed.values():
                if abs(v["pos"][0] - cx) < 1 and abs(v["pos"][1] - cy) < 1:
                    score = v.get("score", 0)
                    break
            _draw_confirmed(warped, int(cx), int(cy), int(r), score)

        # ── HUD: hit count and total score ────────────────────────────────────
        total  = state.total_score()
        n_hits = len(state.confirmed)
        hud    = f"Hits: {n_hits}   Score: {total}"
        cv2.putText(warped, hud, (50, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0),   5)
        cv2.putText(warped, hud, (50, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)

        # ── Resize for display window ─────────────────────────────────────────
        disp = cv2.resize(warped, (0, 0),
                          fx=CFG.display_scale, fy=CFG.display_scale)
        state.display_frame = disp
        state.result_ready.set()
