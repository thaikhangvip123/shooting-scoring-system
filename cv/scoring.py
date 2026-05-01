"""
scoring.py — Load scoring geometry from disk and expose calculate_score().

Supports three target types:
  BIA_TRON  — concentric rings (distance-based)
  BIA_IPSC  — IPSC polygons loaded from file
  BIA_NGUOI — human silhouette contours loaded from file
"""

import math
import os
import cv2
import numpy as np
from typing import List, Tuple

from config import CFG, SCALE_FACTOR, CENTER_X_PX, CENTER_Y_PX, PIXELS_PER_MM


# ── BIA_TRON ───────────────────────────────────────────────────────────────
# Ring radii in the 2480-px scoring space (outer → inner)
tron_center = (CFG.width * SCALE_FACTOR / 2, CFG.height * SCALE_FACTOR / 2)
tron_radii  = [897.0, 802.5, 708.0, 613.5, 519.0,
               424.5, 330.0, 235.5, 141.0,  51.0]


# ── BIA_IPSC ───────────────────────────────────────────────────────────────
ipsc_polys:  List[np.ndarray] = []
ipsc_scores: List[int]        = [10, 5, 3, 10, 7]

if os.path.exists(CFG.path_ipsc_poly):
    _current: List = []
    with open(CFG.path_ipsc_poly) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("polygon"):
                continue
            if _line == "END":
                ipsc_polys.append(np.array(_current))
                _current = []
                continue
            _x, _y = map(int, _line.split(","))
            _current.append([_x, _y])
else:
    print(f"[scoring] WARNING: IPSC polygon file not found: {CFG.path_ipsc_poly}")


# ── BIA_NGUOI ──────────────────────────────────────────────────────────────
nguoi_cnts:   List[np.ndarray] = []
nguoi_scores: List[int]        = [6, 7, 8, 9, 9, 10, 10]

if os.path.exists(CFG.path_nguoi_cont):
    _current_c: List = []
    with open(CFG.path_nguoi_cont) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line:
                continue
            if _line.startswith("contour"):
                if _current_c:
                    nguoi_cnts.append(np.array(_current_c, dtype=np.int32))
                _current_c = []
                continue
            _x, _y = map(int, _line.split(","))
            _current_c.append([_x, _y])
    if _current_c:
        nguoi_cnts.append(np.array(_current_c, dtype=np.int32))
else:
    print(f"[scoring] WARNING: Nguoi contour file not found: {CFG.path_nguoi_cont}")


# ── Main scoring function ──────────────────────────────────────────────────

def calculate_score(target_name: str, point: Tuple[int, int]) -> int:
    """
    Return the score for a hit at `point` (in 2480-px scoring coordinates).

    Args:
        target_name: one of "BIA_TRON", "BIA_IPSC", "BIA_NGUOI"
        point:       (x, y) in the 2480-px scoring coordinate space
                     (use coords.px_to_score_px() to convert from warped pixels)

    Returns:
        Integer score (0 if outside all scoring zones).
    """
    if target_name == "BIA_TRON":
        dx = point[0] - tron_center[0]
        dy = point[1] - tron_center[1]
        dist = math.sqrt(dx * dx + dy * dy)
        for i, r in enumerate(reversed(tron_radii)):
            if dist <= r:
                return 10 - i
        return 0

    elif target_name == "BIA_IPSC":
        for i, poly in enumerate(ipsc_polys):
            if cv2.pointPolygonTest(
                    poly, (float(point[0]), float(point[1])), False) >= 0:
                return ipsc_scores[i]
        return 0

    elif target_name == "BIA_NGUOI":
        best_score   = 0
        smallest_area = float("inf")
        for i, cnt in enumerate(nguoi_cnts):
            if cv2.pointPolygonTest(
                    cnt, (float(point[0]), float(point[1])), False) >= 0:
                area = cv2.contourArea(cnt)
                if area < smallest_area:
                    smallest_area = area
                    best_score    = nguoi_scores[i]
        return best_score

    return 0
