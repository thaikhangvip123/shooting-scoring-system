"""
layer1.py — Layer 1 detection: signed background difference + morphology.

Pipeline:
  1. Compute signed diff: current_frame − rolling_BG
  2. Threshold into dark_mask (bullet holes get darker than BG)
  3. Mask out ArUco corners and already-confirmed bullet regions
  4. Morphological clean-up (open → dilate → close)
  5. Find external contours → classify each as bullet_candidate or shadow_candidate

Key fix vs V1:
  - Removed the overlap_ratio ≥ 0.20 check that misclassified almost every
    real bullet hole as a shadow (bullet rims naturally produce a bright edge).
  - Classification now uses circularity only: ≥ threshold → bullet_candidate.
"""

import math
import cv2
import numpy as np
from typing import Dict, List, Tuple

from config import CFG, DST_POINTS
from state import TargetState


# ── Structuring elements (built once, reused every frame) ───────────────────
_K_OPEN  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
_K_DIL   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
_K_CLOSE = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))

# How far around each ArUco corner to blank (pixels in warped space)
_ARUCO_BLANK_R = CFG.margin * 2


def _build_confirmed_exclusion_mask(shape: Tuple[int, int],
                                    confirmed: Dict[int, dict]) -> np.ndarray:
    """
    Binary mask (255 = excluded) covering already-confirmed bullet holes.
    Prevents Layer 1 from re-detecting the same hole every frame.
    """
    mask = np.zeros(shape, dtype=np.uint8)
    for v in confirmed.values():
        cx, cy = int(v["pos"][0]), int(v["pos"][1])
        cv2.circle(mask, (cx, cy), CFG.expected_radius + 15, 255, -1)
    return mask


def process_layer_1(state: TargetState,
                    warped_gray: np.ndarray
                    ) -> Tuple[List[dict], np.ndarray]:
    """
    Detect candidate regions in `warped_gray` by comparing to rolling BG.

    Returns:
        candidates  — list of dicts, each:
                        { "contour": np.ndarray,
                          "label":   "bullet_candidate" | "shadow_candidate",
                          "area":    float }
        dark_mask   — uint8 mask after morphology (useful for debug display)
    """
    bg_u8 = state.get_bg_u8()
    if bg_u8 is None:
        return [], np.zeros_like(warped_gray)

    dark_t, _ = state.get_thresholds()

    # ── 1. Signed diff and threshold ────────────────────────────────────────
    diff = warped_gray.astype(np.int16) - bg_u8.astype(np.int16)

    # We only care about pixels that became DARKER (bullet holes absorb light)
    dark_mask = np.where(diff < dark_t, 255, 0).astype(np.uint8)

    # ── 2. Mask ArUco corner regions ─────────────────────────────────────────
    for pt in DST_POINTS:
        cv2.circle(dark_mask, (int(pt[0]), int(pt[1])), _ARUCO_BLANK_R, 0, -1)

    # ── 3. Mask confirmed bullets (don't re-detect already-found holes) ──────
    excl = _build_confirmed_exclusion_mask(warped_gray.shape, state.confirmed)
    dark_mask = cv2.bitwise_and(dark_mask, cv2.bitwise_not(excl))

    # ── 4. Morphology: remove noise speckles, fill gaps, connect nearby blobs ─
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN,  _K_OPEN)
    dark_mask = cv2.dilate       (dark_mask, _K_DIL, iterations=1)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, _K_CLOSE)

    # ── 5. Find contours and classify ────────────────────────────────────────
    cnts, _ = cv2.findContours(dark_mask,
                               cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    candidates: List[dict] = []

    for c in cnts:
        area = cv2.contourArea(c)
        if area < CFG.min_blob_area:
            continue

        hull      = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue

        hull_perim = cv2.arcLength(hull, True)
        if hull_perim == 0:
            continue

        circularity = 4 * math.pi * (hull_area / (hull_perim ** 2))

        # Build a dense (CHAIN_APPROX_NONE) contour from the hull mask
        # so Layer 2 RANSAC has full point coverage
        blob_mask = np.zeros_like(dark_mask)
        cv2.drawContours(blob_mask, [hull], -1, 255, -1)
        dense_cnts, _ = cv2.findContours(blob_mask,
                                         cv2.RETR_EXTERNAL,
                                         cv2.CHAIN_APPROX_NONE)
        if not dense_cnts:
            continue
        dense_contour = dense_cnts[0]

        # ── Classification ────────────────────────────────────────────────
        # FIX: removed overlap_ratio check (caused all bullets to be shadows).
        # Real bullet holes: roughly circular (0.55–1.0).
        # Shadows / smears: elongated or irregular (< threshold).
        if circularity >= CFG.circularity_threshold:
            label = "bullet_candidate"
        else:
            label = "shadow_candidate"

        candidates.append({
            "contour": dense_contour,
            "label":   label,
            "area":    hull_area,
            "blob_mask": blob_mask,   # passed to Layer 2 for HoughCircles
        })

    return candidates, dark_mask
