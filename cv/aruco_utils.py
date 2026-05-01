"""
aruco_utils.py — ArUco detector initialisation and marker utilities.

Handles OpenCV 4.8+ API (ArucoDetector class, renamed parameters).
If you need to downgrade to 4.6, see the comments marked [4.6-COMPAT].
"""

import cv2
import cv2.aruco as aruco
import numpy as np
from typing import Dict, List, Optional, Tuple

from config import CFG


# ── CLAHE equaliser (applied to frame before marker detection) ──────────────
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


# ── Detector parameters ─────────────────────────────────────────────────────
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

params = aruco.DetectorParameters()

# Larger adaptive window: handles motion blur and perspective distortion better
params.adaptiveThreshWinSizeMin  = 3
params.adaptiveThreshWinSizeMax  = 53
params.adaptiveThreshWinSizeStep = 4

params.minMarkerPerimeterRate    = 0.02   # detect small / far markers
params.maxMarkerPerimeterRate    = 4.0

# NOTE: renamed in OpenCV 4.8+  (was polygonApproxAccuracyRate)
params.polygonalApproxAccuracyRate = 0.04

params.perspectiveRemoveIgnoredMarginPerCell = 0.13
params.errorCorrectionRate       = 0.6

# [4.6-COMPAT] If you're on 4.6, replace everything above with:
#   params = aruco.DetectorParameters_create()
#   params.polygonApproxAccuracyRate = 0.04   # old name
#   ... (same other fields)
#   And replace detector.detectMarkers() calls with:
#   aruco.detectMarkers(gray_eq, aruco_dict, parameters=params)

detector = aruco.ArucoDetector(aruco_dict, params)


# ── Public helpers ───────────────────────────────────────────────────────────

def detect_markers(frame: np.ndarray) -> Dict[int, np.ndarray]:
    """
    Detect ArUco markers in `frame` using CLAHE-equalised grayscale.

    Returns:
        Dict mapping marker_id → corner array (shape [4, 2], float32).
        Empty dict if no markers found.
    """
    gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_eq = clahe.apply(gray)

    corners, ids, _ = detector.detectMarkers(gray_eq)

    if ids is None:
        return {}

    return {int(ids[i][0]): corners[i][0] for i in range(len(ids))}


def is_valid_quad(pts: np.ndarray, min_area: float = 8000.0) -> bool:
    """
    Sanity check: four source points form a proper convex quadrilateral
    with enough area to be worth processing.
    """
    hull = cv2.convexHull(pts.reshape(-1, 1, 2).astype(np.float32))
    return float(cv2.contourArea(hull)) > min_area


def get_src_points(marker_dict: Dict[int, np.ndarray],
                   id_set: List[int]) -> Optional[np.ndarray]:
    """
    Extract the four source corners for a target's marker set.

    Convention (matching DST_POINTS order):
        id_set[0] = TL marker → use its corner[0]
        id_set[1] = TR marker → use its corner[1]
        id_set[2] = BR marker → use its corner[2]
        id_set[3] = BL marker → use its corner[3]

    Returns None if any marker is missing.
    """
    TL, TR, BR, BL = id_set
    if not all(mid in marker_dict for mid in id_set):
        return None

    src_pts = np.array([
        marker_dict[TL][0],
        marker_dict[TR][1],
        marker_dict[BR][2],
        marker_dict[BL][3],
    ], dtype=np.float32)

    return src_pts if is_valid_quad(src_pts) else None
