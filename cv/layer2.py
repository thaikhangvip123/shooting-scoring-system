"""
layer2.py — Layer 2 detection: circle fitting on candidate blobs.

Two-stage approach:
  Fast path  — HoughCircles on the blob mask (single bullet, clean hole)
  Fallback   — 3-point RANSAC (overlapping holes, partial circles, angled shots)

Both return a list of (cx, cy, radius) tuples in warped-image coordinates.
"""

import math
import random
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import CFG


# ── Radius search range (applied to both methods) ───────────────────────────
_R    = CFG.expected_radius
_R_LO = _R - 7
_R_HI = _R + 8


# ── 3-point circle fit ───────────────────────────────────────────────────────

def _circle_from_3pts(p1, p2, p3) -> Optional[Tuple[float, float, float]]:
    """
    Fit a unique circle through three non-collinear points.
    Returns (cx, cy, r) or None if the points are (nearly) collinear.
    """
    ax, ay = float(p1[0]), float(p1[1])
    bx, by = float(p2[0]), float(p2[1])
    cx, cy = float(p3[0]), float(p3[1])

    D = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(D) < 1e-6:
        return None

    ux = ((ax**2 + ay**2) * (by - cy) +
          (bx**2 + by**2) * (cy - ay) +
          (cx**2 + cy**2) * (ay - by)) / D
    uy = ((ax**2 + ay**2) * (cx - bx) +
          (bx**2 + by**2) * (ax - cx) +
          (cx**2 + cy**2) * (bx - ax)) / D
    r = math.sqrt((ax - ux) ** 2 + (ay - uy) ** 2)
    return ux, uy, r


# ── HoughCircles fast path ───────────────────────────────────────────────────

def _hough_circles(blob_mask: np.ndarray) -> List[Tuple[int, int, int]]:
    """
    Try HoughCircles on a binary blob mask.
    Returns list of (cx, cy, radius) or [] if none found.
    """
    circles = cv2.HoughCircles(
        blob_mask,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=int(_R * 1.5),
        param1=50,
        param2=CFG.hough_param2,
        minRadius=_R_LO,
        maxRadius=_R_HI,
    )
    if circles is None:
        return []
    return [(int(x), int(y), _R)
            for x, y, _ in np.round(circles[0]).astype(int)]


# ── 3-point RANSAC fallback ──────────────────────────────────────────────────

def _ransac_circles(contour: np.ndarray) -> List[Tuple[int, int, int]]:
    """
    Iterative 3-point RANSAC to find up to `ransac_max_bullets` circles
    in a (potentially multi-hole) contour point cloud.

    After each consensus set is found, its inliers are removed so the next
    iteration can find the next bullet hole.
    """
    points = [tuple(pt[0]) for pt in contour]
    if len(points) < 10:
        return []

    area  = cv2.contourArea(contour)
    n_est = min(CFG.ransac_max_bullets,
                max(1, int(round(area / (math.pi * _R ** 2)))))

    found: List[Tuple[int, int, int]] = []
    remaining = list(points)

    for _ in range(n_est):
        if len(remaining) < 10:
            break

        best_circle:  Optional[Tuple[int, int, int]] = None
        best_inliers: List = []

        for _ in range(CFG.ransac_iterations):
            if len(remaining) < 3:
                break

            sample = random.sample(remaining, 3)
            fit    = _circle_from_3pts(*sample)
            if fit is None:
                continue

            fx, fy, fr = fit
            # Reject fitted circles whose radius is too far from expected
            if abs(fr - _R) > _R * 0.5:
                continue

            inliers = [
                pt for pt in remaining
                if abs(math.sqrt((pt[0] - fx) ** 2 +
                                 (pt[1] - fy) ** 2) - _R)
                   <= CFG.ransac_inlier_thresh
            ]
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_circle  = (int(fx), int(fy), _R)

        if best_circle and len(best_inliers) >= CFG.ransac_min_inliers:
            found.append(best_circle)
            inlier_set = set(best_inliers)
            remaining  = [p for p in remaining if p not in inlier_set]

    return found


# ── Public entry point ───────────────────────────────────────────────────────

def process_layer_2(contour:   np.ndarray,
                    blob_mask: Optional[np.ndarray] = None
                    ) -> List[Tuple[int, int, int]]:
    """
    Fit circles to a candidate blob.

    Args:
        contour:   dense contour from Layer 1 (CHAIN_APPROX_NONE)
        blob_mask: filled binary mask of the same blob (used for HoughCircles)

    Returns:
        List of (cx, cy, radius) in warped-image pixels.
        Empty list if no circle found with sufficient support.
    """
    # Fast path first — works well for single clean holes
    if blob_mask is not None:
        result = _hough_circles(blob_mask)
        if result:
            return result

    # Fallback — handles overlapping holes and partial circles
    return _ransac_circles(contour)
