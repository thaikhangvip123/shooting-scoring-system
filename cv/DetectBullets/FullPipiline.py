"""
FullPipeline_V2.py — Shooting Scoring System (Rebuilt)
=======================================================
Improvements over V1:
  - Dataclass config (all tunable params in one place)
  - CLAHE pre-processing + tuned ArUco DetectorParameters
  - Homography caching (only recompute when markers drift)
  - Rolling background model with confirmed-bullet masking
  - Per-target adaptive thresholds (3-sigma from noise estimate)
  - Layer 2: 3-point circle fit RANSAC + HoughCircles fast-path
  - Confirmed-bullet region masked out of Layer 1 after lock-in
  - Layer 3: KD-tree nearest-neighbour matching + Hungarian assignment
  - Score cached on confirmation (not recomputed every frame)
  - Worker threads: one per target for warp+detect, main thread for display
  - Single px_to_mm() / mm_to_px() coordinate utility
"""

import cv2
import cv2.aruco as aruco
import numpy as np
import os
import io
import math
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ============================================================
# 1. CONFIG DATACLASS
# ============================================================

@dataclass
class PipelineConfig:
    # --- Paths ---
    video_path: str         = "E:/shooting-scoring-system/cv/DetectBullets/target.mp4"
    log_file_path: str      = "E:/shooting-scoring-system/cv/DetectBullets/bullet_logs.txt"
    path_ipsc_poly: str     = "E:/shooting-scoring-system/cv/Scoring/IPSC/polygon.txt"
    path_nguoi_cont: str    = "E:/shooting-scoring-system/cv/Scoring/Nguoi/Nguoi_contours.txt"
    template_paths: Dict[str, str] = field(default_factory=lambda: {
        "BIA_TRON":  "E:/shooting-scoring-system/cv/DetectBullets/A4_Tron3.png",
        "BIA_IPSC":  "E:/shooting-scoring-system/cv/DetectBullets/A4_IPSC2.png",
        "BIA_NGUOI": "E:/shooting-scoring-system/cv/DetectBullets/A4_Nguoi2.png",
    })

    # --- Canvas ---
    width: int              = 1240
    height: int             = 1754
    margin: int             = 40
    a4_width_mm: float      = 210.0

    # --- Bullet geometry ---
    expected_radius: int    = 25          # pixels in warped space

    # --- Background model ---
    bg_alpha: float         = 0.003       # rolling BG update speed (~330 frames to full replace)
    bg_warmup_frames: int   = 10          # frames to collect noise stats before enabling diff
    sigma_mult: float       = 3.2         # threshold = sigma_mult * noise_std

    # --- Layer 1 fallback thresholds (used before noise stats are ready) ---
    dark_thresh_fallback: int  = -35
    bright_thresh_fallback: int = 25

    # --- Layer 2 RANSAC ---
    ransac_iterations: int  = 80
    ransac_inlier_thresh: float = 3.5
    ransac_min_inliers: int = 12          # lowered slightly for partial circles
    ransac_max_bullets: int = 5
    hough_param2: int       = 14          # lower = more sensitive HoughCircles

    # --- Layer 3 tracking ---
    confirm_frames: int     = 5
    stale_frames: int       = 10
    forget_secs: float      = 2.0         # time-based forget (not frame-based)
    match_dist: int         = 15

    # --- Homography ---
    homography_drift_thresh: float = 2.0  # pixels; recompute H only when markers move more

    # --- Display ---
    display_scale: float    = 0.35        # resize warped for display window


CFG = PipelineConfig()

# Derived constants
PIXELS_PER_MM = CFG.width / CFG.a4_width_mm
CENTER_X_PX   = CFG.width / 2
CENTER_Y_PX   = CFG.height / 2
SCALE_FACTOR  = 2480 / CFG.width          # scoring polygon coords were at 2480px

dst_points = np.array([
    [CFG.margin,              CFG.margin],
    [CFG.width  - CFG.margin, CFG.margin],
    [CFG.width  - CFG.margin, CFG.height - CFG.margin],
    [CFG.margin,              CFG.height - CFG.margin],
], dtype=np.float32)


# ============================================================
# 2. COORDINATE UTILITIES
# ============================================================

def px_to_mm(x_px: float, y_px: float) -> Tuple[float, float]:
    """Warped-image pixel → cartesian mm (origin at target centre, Y up)."""
    return (x_px - CENTER_X_PX) / PIXELS_PER_MM, -(y_px - CENTER_Y_PX) / PIXELS_PER_MM

def mm_to_px(x_mm: float, y_mm: float) -> Tuple[float, float]:
    return x_mm * PIXELS_PER_MM + CENTER_X_PX, -y_mm * PIXELS_PER_MM + CENTER_Y_PX

def px_to_score_px(x_px: float, y_px: float) -> Tuple[int, int]:
    """Warped pixel → scoring coordinate space (2480px wide)."""
    return int(x_px * SCALE_FACTOR), int(y_px * SCALE_FACTOR)


# ============================================================
# 3. SCORING DATA LOADER
# ============================================================

ipsc_polys, ipsc_scores = [], [10, 5, 3, 10, 7]
if os.path.exists(CFG.path_ipsc_poly):
    with open(CFG.path_ipsc_poly) as f:
        current_poly: List = []
        for line in f:
            line = line.strip()
            if not line or line.startswith("polygon"): continue
            if line == "END":
                ipsc_polys.append(np.array(current_poly)); current_poly = []
                continue
            x, y = map(int, line.split(","))
            current_poly.append([x, y])

nguoi_cnts, nguoi_scores = [], [6, 7, 8, 9, 9, 10, 10]
if os.path.exists(CFG.path_nguoi_cont):
    with open(CFG.path_nguoi_cont) as f:
        current_contour: List = []
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith("contour"):
                if current_contour:
                    nguoi_cnts.append(np.array(current_contour, dtype=np.int32))
                current_contour = []
                continue
            x, y = map(int, line.split(","))
            current_contour.append([x, y])
        if current_contour:
            nguoi_cnts.append(np.array(current_contour, dtype=np.int32))

tron_center = (CFG.width * SCALE_FACTOR / 2, CFG.height * SCALE_FACTOR / 2)
# Radii in scoring-space pixels (2480px wide canvas)
tron_radii = [897.0, 802.5, 708.0, 613.5, 519.0, 424.5, 330.0, 235.5, 141.0, 51.0]


def calculate_score(target_name: str, point: Tuple[int, int]) -> int:
    if target_name == "BIA_TRON":
        dx, dy = point[0] - tron_center[0], point[1] - tron_center[1]
        dist = math.sqrt(dx * dx + dy * dy)
        for i, r in enumerate(reversed(tron_radii)):
            if dist <= r: return 10 - i
        return 0
    elif target_name == "BIA_IPSC":
        for i, poly in enumerate(ipsc_polys):
            if cv2.pointPolygonTest(poly, (float(point[0]), float(point[1])), False) >= 0:
                return ipsc_scores[i]
        return 0
    elif target_name == "BIA_NGUOI":
        best_score, smallest_area = 0, float("inf")
        for i, cnt in enumerate(nguoi_cnts):
            if cv2.pointPolygonTest(cnt, (float(point[0]), float(point[1])), False) >= 0:
                area = cv2.contourArea(cnt)
                if area < smallest_area:
                    smallest_area = area
                    best_score = nguoi_scores[i]
        return best_score
    return 0


# ============================================================
# 4. PER-TARGET STATE
# ============================================================

class TargetState:
    """All mutable state for a single target."""

    def __init__(self, name: str):
        self.name = name

        # Background model
        self.bg_float:   Optional[np.ndarray] = None   # float32 rolling BG
        self.noise_std:  float = 20.0                  # estimated noise sigma
        self.noise_ready: bool = False
        self.warmup_diffs: List[np.ndarray] = []
        self.warmup_count: int = 0

        # Homography cache
        self.H_cached:   Optional[np.ndarray] = None
        self.H_src_prev: Optional[np.ndarray] = None

        # Tracking
        self.candidates: Dict[int, dict] = {}
        self.confirmed:  Dict[int, dict] = {}
        self.next_id:    int = 0

        # Thread safety
        self.lock = threading.Lock()

        # Latest rendered frame for display
        self.display_frame: Optional[np.ndarray] = None
        self.result_ready  = threading.Event()

    # ---- Homography cache ------------------------------------------

    def get_homography(self, src_pts: np.ndarray) -> Optional[np.ndarray]:
        if self.H_src_prev is not None:
            drift = np.max(np.linalg.norm(src_pts - self.H_src_prev, axis=1))
            if drift < CFG.homography_drift_thresh and self.H_cached is not None:
                return self.H_cached
        H, mask = cv2.findHomography(src_pts, dst_points, cv2.RANSAC, 3.0)
        if H is None:
            return self.H_cached  # keep old if new one fails
        self.H_cached  = H
        self.H_src_prev = src_pts.copy()
        return H

    # ---- Background model ------------------------------------------

    def update_background(self, warped_gray: np.ndarray):
        if self.bg_float is None:
            self.bg_float = warped_gray.astype(np.float32)
            return

        # Collect warmup frames to estimate noise
        if not self.noise_ready:
            diff = warped_gray.astype(np.float32) - self.bg_float
            self.warmup_diffs.append(diff)
            self.warmup_count += 1
            if self.warmup_count >= CFG.bg_warmup_frames:
                stack = np.stack(self.warmup_diffs, axis=0)
                self.noise_std = float(np.std(stack))
                self.noise_ready = True
                self.warmup_diffs.clear()
                print(f"  [{self.name}] Noise σ = {self.noise_std:.1f} → "
                      f"thresholds dark={-CFG.sigma_mult*self.noise_std:.1f} "
                      f"bright=+{CFG.sigma_mult*self.noise_std:.1f}")
            return  # don't update BG during warmup

        # Build mask: do NOT update BG under confirmed bullet holes
        bullet_mask = np.zeros(warped_gray.shape, dtype=bool)
        for v in self.confirmed.values():
            cx, cy = int(v["pos"][0]), int(v["pos"][1])
            rr = CFG.expected_radius + 12
            y0, y1 = max(0, cy - rr), min(warped_gray.shape[0], cy + rr)
            x0, x1 = max(0, cx - rr), min(warped_gray.shape[1], cx + rr)
            bullet_mask[y0:y1, x0:x1] = True

        update_region = ~bullet_mask
        fg = warped_gray.astype(np.float32)
        self.bg_float[update_region] = (
            self.bg_float[update_region] * (1.0 - CFG.bg_alpha)
            + fg[update_region] * CFG.bg_alpha
        )

    def get_bg_u8(self) -> Optional[np.ndarray]:
        if self.bg_float is None:
            return None
        return np.clip(self.bg_float, 0, 255).astype(np.uint8)

    def get_thresholds(self) -> Tuple[float, float]:
        if self.noise_ready:
            t = CFG.sigma_mult * self.noise_std
            return -t, t
        return float(CFG.dark_thresh_fallback), float(CFG.bright_thresh_fallback)


target_states: Dict[str, TargetState] = {
    "BIA_TRON":  TargetState("BIA_TRON"),
    "BIA_IPSC":  TargetState("BIA_IPSC"),
    "BIA_NGUOI": TargetState("BIA_NGUOI"),
}


# ============================================================
# 5. ARUCO SETUP — TUNED PARAMETERS
# ============================================================

aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

params = aruco.DetectorParameters()
# Larger adaptive window range → handles blur and perspective better
params.adaptiveThreshWinSizeMin   = 3
params.adaptiveThreshWinSizeMax   = 53
params.adaptiveThreshWinSizeStep  = 4
params.minMarkerPerimeterRate     = 0.02    # detect small/far markers
params.maxMarkerPerimeterRate     = 4.0
params.approxPolyDPEps            = 0.04
params.perspectiveRemoveIgnoredMarginPerCell = 0.13
params.errorCorrectionRate        = 0.6

detector = aruco.ArucoDetector(aruco_dict, params)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

target_sets = {
    "BIA_TRON":  [0, 1, 2, 3],
    "BIA_IPSC":  [4, 5, 6, 7],
    "BIA_NGUOI": [8, 9, 10, 11],
}


def is_valid_quad(pts: np.ndarray, min_area: float = 8000.0) -> bool:
    """Sanity check: source points form a proper convex quadrilateral."""
    hull = cv2.convexHull(pts.reshape(-1, 1, 2).astype(np.float32))
    return float(cv2.contourArea(hull)) > min_area


# ============================================================
# 6. LAYER 1 — SIGNED DIFF + MORPHOLOGY
# ============================================================

def build_confirmed_exclusion_mask(shape: Tuple[int, int],
                                   confirmed: Dict[int, dict]) -> np.ndarray:
    """Binary mask = 255 where confirmed bullets already sit (exclude from search)."""
    mask = np.zeros(shape, dtype=np.uint8)
    for v in confirmed.values():
        cx, cy = int(v["pos"][0]), int(v["pos"][1])
        cv2.circle(mask, (cx, cy), CFG.expected_radius + 15, 255, -1)
    return mask


def process_layer_1(state: TargetState,
                    warped_gray: np.ndarray
                    ) -> Tuple[List[dict], np.ndarray]:
    """
    Returns list of candidate dicts {contour, label, area}
    and the darkening mask (for debug display).
    """
    bg_u8 = state.get_bg_u8()
    if bg_u8 is None:
        return [], np.zeros_like(warped_gray)

    dark_t, bright_t = state.get_thresholds()

    bg_int   = bg_u8.astype(np.int16)
    curr_int = warped_gray.astype(np.int16)
    diff     = curr_int - bg_int

    darkening_mask  = np.where(diff < dark_t,   255, 0).astype(np.uint8)
    brightening_mask = np.where(diff > bright_t, 255, 0).astype(np.uint8)

    # --- Mask ArUco corner regions ---
    aruco_mask_r = CFG.margin * 2
    for pt in dst_points:
        cv2.circle(darkening_mask,   (int(pt[0]), int(pt[1])), aruco_mask_r, 0, -1)
        cv2.circle(brightening_mask, (int(pt[0]), int(pt[1])), aruco_mask_r, 0, -1)

    # --- Mask confirmed bullets (don't re-detect already-found holes) ---
    excl = build_confirmed_exclusion_mask(warped_gray.shape, state.confirmed)
    darkening_mask  = cv2.bitwise_and(darkening_mask,  cv2.bitwise_not(excl))
    brightening_mask = cv2.bitwise_and(brightening_mask, cv2.bitwise_not(excl))

    # --- Morphology ---
    k_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k_dil   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))

    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_OPEN, k_open)
    darkening_mask = cv2.dilate(darkening_mask, k_dil, iterations=1)
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_CLOSE, k_close)

    cnts, _ = cv2.findContours(darkening_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: List[dict] = []

    for c in cnts:
        area = cv2.contourArea(c)
        if area < 500:
            continue

        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue

        hull_perimeter = cv2.arcLength(hull, True)
        if hull_perimeter == 0:
            continue

        circularity = 4 * math.pi * (hull_area / (hull_perimeter ** 2))

        if circularity < 0.85:
            candidates.append({"contour": hull, "label": "shadow_candidate", "area": hull_area})
            continue

        blob_mask = np.zeros_like(darkening_mask)
        cv2.drawContours(blob_mask, [hull], -1, 255, -1)
        dense_cnts, _ = cv2.findContours(blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not dense_cnts:
            continue
        dense_contour = dense_cnts[0]

        overlap      = cv2.bitwise_and(blob_mask, brightening_mask)
        overlap_area = cv2.countNonZero(overlap)
        blob_pixels  = cv2.countNonZero(blob_mask)
        overlap_ratio = overlap_area / blob_pixels if blob_pixels > 0 else 0

        label = "shadow_candidate" if overlap_ratio >= 0.20 else "bullet_candidate"
        candidates.append({"contour": dense_contour, "label": label, "area": hull_area})

    return candidates, darkening_mask


# ============================================================
# 7. LAYER 2 — HOUGH FAST-PATH + 3-POINT RANSAC
# ============================================================

def circle_from_3pts(p1, p2, p3) -> Optional[Tuple[float, float, float]]:
    """Fit a circle through 3 points. Returns (cx, cy, r) or None."""
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
    r = math.sqrt((ax - ux)**2 + (ay - uy)**2)
    return ux, uy, r


def process_layer_2(contour: np.ndarray,
                    blob_mask: Optional[np.ndarray] = None
                    ) -> List[Tuple[int, int, int]]:
    """
    Fast-path: HoughCircles on the blob mask.
    Fallback: 3-point RANSAC for overlapping / partial circles.
    Returns list of (cx, cy, radius) in warped-image coordinates.
    """
    R      = CFG.expected_radius
    r_lo   = R - 7
    r_hi   = R + 8

    # --- Fast path: HoughCircles ---
    if blob_mask is not None:
        circles = cv2.HoughCircles(
            blob_mask,
            cv2.HOUGH_GRADIENT, dp=1,
            minDist=int(R * 1.5),
            param1=50,
            param2=CFG.hough_param2,
            minRadius=r_lo,
            maxRadius=r_hi,
        )
        if circles is not None:
            result = []
            for x, y, r in np.round(circles[0]).astype(int):
                result.append((int(x), int(y), R))
            return result

    # --- Fallback: 3-point RANSAC ---
    points = [tuple(pt[0]) for pt in contour]
    if len(points) < 10:
        return []

    area     = cv2.contourArea(contour)
    n_est    = min(CFG.ransac_max_bullets,
                   max(1, int(round(area / (math.pi * R ** 2)))))

    found_circles: List[Tuple[int, int, int]] = []
    remaining = list(points)

    for _ in range(n_est):
        if len(remaining) < 10:
            break

        best_circle  = None
        best_inliers: List = []

        for _ in range(CFG.ransac_iterations):
            if len(remaining) < 3:
                break
            sample = random.sample(remaining, 3)
            fit = circle_from_3pts(sample[0], sample[1], sample[2])
            if fit is None:
                continue
            fx, fy, fr = fit

            # Fast reject: fitted radius must be close to expected
            if abs(fr - R) > R * 0.5:
                continue

            inliers = [
                pt for pt in remaining
                if abs(math.sqrt((pt[0] - fx)**2 + (pt[1] - fy)**2) - R)
                   <= CFG.ransac_inlier_thresh
            ]
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_circle  = (int(fx), int(fy), R)

        if best_circle and len(best_inliers) >= CFG.ransac_min_inliers:
            found_circles.append(best_circle)
            inlier_set = set(best_inliers)
            remaining  = [p for p in remaining if p not in inlier_set]

    return found_circles


# ============================================================
# 8. LAYER 3 — KD-TREE TEMPORAL TRACKING
# ============================================================

def _match_hungarian(existing_pos: List[Tuple[float, float]],
                     new_detections: List[Tuple],
                     max_dist: float
                     ) -> Tuple[List[Tuple[int, int]], List[int]]:
    """
    Hungarian-optimal assignment between existing positions and new detections.
    Returns: (matched pairs (new_idx, exist_idx), unmatched new indices)
    """
    if not existing_pos or not new_detections:
        return [], list(range(len(new_detections)))

    new_pts = np.array([(x, y) for x, y, *_ in new_detections], dtype=float)
    ex_pts  = np.array(existing_pos, dtype=float)

    # Cost matrix: Euclidean distances, cap at large value for pairs > max_dist
    diffs = new_pts[:, None, :] - ex_pts[None, :, :]           # (N_new, N_ex, 2)
    cost  = np.sqrt((diffs ** 2).sum(axis=2))                   # (N_new, N_ex)
    cost[cost > max_dist] = 1e9

    row_ind, col_ind = linear_sum_assignment(cost)
    matched   = [(r, c) for r, c in zip(row_ind, col_ind) if cost[r, c] < max_dist]
    matched_r = {r for r, _ in matched}
    unmatched = [i for i in range(len(new_detections)) if i not in matched_r]
    return matched, unmatched


def temporal_tracking(state: TargetState,
                      raw_circles: List[Tuple[int, int, int]],
                      now: float) -> List[Tuple[float, float, int]]:
    """
    Layer 3: candidate promotion with Hungarian matching.
    now = time.monotonic() timestamp for time-based forget.
    Returns confirmed bullet positions as (cx, cy, r).
    """
    alpha = 0.2

    # ---- 1. Match raw_circles → confirmed (priority) ----
    conf_ids  = list(state.confirmed.keys())
    conf_pos  = [state.confirmed[cid]["pos"] for cid in conf_ids]
    matched_conf, remaining_raw_idx = _match_hungarian(
        conf_pos, raw_circles, CFG.match_dist
    )
    used_raw = set()
    for new_i, conf_i in matched_conf:
        cid     = conf_ids[conf_i]
        ox, oy  = state.confirmed[cid]["pos"]
        nx, ny, r = raw_circles[new_i]
        state.confirmed[cid]["pos"]        = (ox * (1-alpha) + nx * alpha,
                                               oy * (1-alpha) + ny * alpha)
        state.confirmed[cid]["last_time"]  = now
        used_raw.add(new_i)

    remaining_raw = [raw_circles[i] for i in remaining_raw_idx]

    # ---- 2. Match remaining → candidates ----
    cand_ids = list(state.candidates.keys())
    cand_pos = [state.candidates[cid]["pos"] for cid in cand_ids]
    matched_cand, truly_new_idx = _match_hungarian(
        cand_pos, remaining_raw, CFG.match_dist
    )
    for new_i, cand_i in matched_cand:
        cid = cand_ids[cand_i]
        state.candidates[cid]["count"] += 1
        ox, oy = state.candidates[cid]["pos"]
        nx, ny, r = remaining_raw[new_i]
        state.candidates[cid]["pos"]       = (ox * 0.5 + nx * 0.5, oy * 0.5 + ny * 0.5)
        state.candidates[cid]["last_time"] = now

        if state.candidates[cid]["count"] >= CFG.confirm_frames:
            # Promote to confirmed; cache score immediately
            cx, cy = state.candidates[cid]["pos"]
            score_pt = px_to_score_px(cx, cy)
            score = calculate_score(state.name, score_pt)
            state.confirmed[cid] = {
                "pos":       state.candidates[cid]["pos"],
                "r":         r,
                "last_time": now,
                "score":     score,
            }
            del state.candidates[cid]

    # New detections with no match → spawn candidates
    for new_i in truly_new_idx:
        nx, ny, r = remaining_raw[new_i]
        cid = state.next_id; state.next_id += 1
        state.candidates[cid] = {
            "pos":       (nx, ny),
            "r":         r,
            "count":     1,
            "last_time": now,
        }

    # ---- 3. Garbage-collect stale entries ----
    stale_thresh = now - (CFG.stale_frames / 30.0)   # approx 30 fps
    forget_thresh = now - CFG.forget_secs

    for k in [k for k, v in state.candidates.items() if v["last_time"] < stale_thresh]:
        del state.candidates[k]
    for k in [k for k, v in state.confirmed.items() if v["last_time"] < forget_thresh]:
        del state.confirmed[k]

    return [(v["pos"][0], v["pos"][1], v["r"]) for v in state.confirmed.values()]


# ============================================================
# 9. PER-TARGET WORKER
# ============================================================

def process_target(target_name: str,
                   frame: np.ndarray,
                   marker_dict: Dict[int, np.ndarray],
                   frame_idx: int,
                   now: float):
    """
    Full pipeline for one target: warp → BG update → L1 → L2 → L3 → draw.
    Runs in a worker thread. Writes result into state.display_frame.
    """
    state   = target_states[target_name]
    id_set  = target_sets[target_name]
    TL, TR, BL, BR = id_set

    src_pts = np.array([
        marker_dict[TL][0],
        marker_dict[TR][1],
        marker_dict[BR][2],
        marker_dict[BL][3],
    ], dtype=np.float32)

    if not is_valid_quad(src_pts):
        return

    # --- Homography (cached) ---
    H = state.get_homography(src_pts)
    if H is None:
        return

    warped      = cv2.warpPerspective(frame, H, (CFG.width, CFG.height))
    warped_gray = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (7, 7), 0)

    with state.lock:
        state.update_background(warped_gray)

        # Not yet ready to detect (still warming up noise estimate)
        if not state.noise_ready:
            disp = cv2.resize(warped, (0, 0), fx=CFG.display_scale, fy=CFG.display_scale)
            state.display_frame = disp
            state.result_ready.set()
            return

        # --- Layer 1 ---
        candidates, dark_mask = process_layer_1(state, warped_gray)

        # --- Layer 2 ---
        raw_circles: List[Tuple[int, int, int]] = []
        for cand in candidates:
            c     = cand["contour"]
            label = cand["label"]
            cv2.drawContours(warped, [c], -1, (200, 200, 200), 1)

            if label == "bullet_candidate":
                # Build a blob mask for HoughCircles fast-path
                blob_mask = np.zeros(warped_gray.shape, dtype=np.uint8)
                cv2.drawContours(blob_mask, [c], -1, 255, -1)
                circles = process_layer_2(c, blob_mask)
                raw_circles.extend(circles)
            elif label == "shadow_candidate":
                M = cv2.moments(c)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    cv2.circle(warped, (cX, cY), 25, (0, 255, 255), 2)

        # --- Layer 3 ---
        all_display = temporal_tracking(state, raw_circles, now)

        # --- Draw confirmed bullets with cached scores ---
        total_score = sum(v["score"] for v in state.confirmed.values())
        for (cx, cy, r) in all_display:
            px = (int(cx), int(cy))
            score = state.confirmed.get(
                next((k for k, v in state.confirmed.items()
                      if abs(v["pos"][0]-cx)<1), None),
                {}
            ).get("score", 0)
            cv2.circle(warped, px, int(r),  (0, 255, 0), 2)
            cv2.circle(warped, px, 3,       (0, 0, 255), -1)
            cv2.putText(warped, str(score),
                        (px[0] + int(r) + 5, px[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 50, 50), 2)

        cv2.putText(warped,
                    f"Hits: {len(all_display)}  Score: {total_score}",
                    (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)

        disp = cv2.resize(warped, (0, 0), fx=CFG.display_scale, fy=CFG.display_scale)
        state.display_frame = disp
        state.result_ready.set()


# ============================================================
# 10. VISUAL REPORT (HEATMAP)
# ============================================================

def generate_visual_report(target_name: str):
    state = target_states[target_name]
    shots_mm = []
    for v in state.confirmed.values():
        cx, cy = v["pos"]
        xm, ym = px_to_mm(cx, cy)
        shots_mm.append([xm, ym])

    if len(shots_mm) < 2:
        print(f"  [{target_name}] Need ≥ 2 confirmed bullets for report.")
        return

    shots_mm = np.array(shots_mm)
    distances = np.linalg.norm(shots_mm, axis=1)
    mre_mm    = float(np.mean(distances))
    r50_mm    = float(np.median(distances))

    best_k = 1; best_score = -1
    max_k = min(5, len(shots_mm) - 1)
    if len(shots_mm) >= 3:
        for k in range(2, max_k + 1):
            labels_tmp = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(shots_mm)
            sc = silhouette_score(shots_mm, labels_tmp)
            if sc > best_score:
                best_score, best_k = sc, k
    if best_score < 0.40:
        best_k = 1

    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(shots_mm)
    centers = kmeans.cluster_centers_

    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_title(
        f"BALLISTIC REPORT — {target_name}\n"
        f"MRE: {mre_mm:.1f}mm  |  CEP(R50): {r50_mm:.1f}mm  |  {best_k} cluster(s)",
        fontsize=13, fontweight="bold"
    )

    tmpl = CFG.template_paths.get(target_name, "")
    if os.path.exists(tmpl):
        img_bg = cv2.cvtColor(cv2.imread(tmpl), cv2.COLOR_BGR2RGB)
        cx_lim = CENTER_X_PX / PIXELS_PER_MM
        cy_lim = CENTER_Y_PX / PIXELS_PER_MM
        ax.imshow(img_bg,
                  extent=[-cx_lim, cx_lim, -cy_lim, cy_lim],
                  alpha=0.75)

    sns.kdeplot(x=shots_mm[:, 0], y=shots_mm[:, 1],
                fill=True, cmap="Reds", alpha=0.35, thresh=0.05, ax=ax)
    colors = ["#00FFFF", "#FFFF00", "#FF00FF", "#00FF00", "#FFA500"]
    for i in range(best_k):
        c_shots = shots_mm[labels == i]
        ax.scatter(c_shots[:, 0], c_shots[:, 1],
                   color=colors[i % 5], edgecolor="black", s=80, zorder=5)
        ax.scatter(centers[i, 0], centers[i, 1],
                   color=colors[i % 5], marker="X", s=200, edgecolor="black", zorder=6)

    ax.scatter(0, 0, color="red", marker="+", s=200, label="Target centre", zorder=7)
    ax.add_patch(plt.Circle((0, 0), r50_mm,
                             color="purple", fill=False,
                             linestyle="--", linewidth=2, label=f"CEP {r50_mm:.0f}mm"))
    ax.legend(fontsize=9)
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight"); buf.seek(0); plt.close()
    img_report = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), 1)
    cv2.imshow(f"Report: {target_name}", img_report)
    print(f"  [{target_name}] Report shown.")


# ============================================================
# 11. LOGGING
# ============================================================

def save_log(frame_idx: int):
    with open(CFG.log_file_path, "a", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"--- REPORT {ts} (Frame: {frame_idx}) ---\n")
        for name, state in target_states.items():
            with state.lock:
                if state.confirmed:
                    coords = [(round(v["pos"][0], 1), round(v["pos"][1], 1))
                              for v in state.confirmed.values()]
                    total  = sum(v["score"] for v in state.confirmed.values())
                    f.write(f"Bia: {name} | Hits: {len(coords)} | "
                            f"Score: {total} | Centres: {coords}\n")
        f.write("-" * 50 + "\n")
    print(f"  Log saved → {CFG.log_file_path}")


# ============================================================
# 12. MAIN LOOP
# ============================================================

def main():
    cap = cv2.VideoCapture(CFG.video_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {CFG.video_path}")
        return

    fps_probe = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"  Video FPS: {fps_probe:.1f}")
    print("  Keys: [a] Report Tron  [b] Report IPSC  [c] Report Nguoi")
    print("        [s] Save log     [r] Reset BG      [q] Quit")

    executor   = ThreadPoolExecutor(max_workers=3)
    frame_idx  = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        now = time.monotonic()

        # --- ArUco detection on CLAHE-equalised gray ---
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_eq = clahe.apply(gray)
        corners, ids, _ = detector.detectMarkers(gray_eq)

        cv2.imshow("Camera (main view)",
                   cv2.resize(frame, (min(800, frame.shape[1]),
                                      min(450, frame.shape[0]))))

        if ids is not None:
            marker_dict = {ids[i][0]: corners[i][0] for i in range(len(ids))}

            for target_name, id_set in target_sets.items():
                if all(mid in marker_dict for mid in id_set):
                    executor.submit(
                        process_target,
                        target_name, frame.copy(), marker_dict.copy(),
                        frame_idx, now
                    )

        # --- Display latest rendered results ---
        for name, state in target_states.items():
            if state.display_frame is not None:
                cv2.imshow(f"Result: {name}", state.display_frame)

        # --- Key handling ---
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s"):
            save_log(frame_idx)
        elif key == ord("a"):
            generate_visual_report("BIA_TRON")
        elif key == ord("b"):
            generate_visual_report("BIA_IPSC")
        elif key == ord("c"):
            generate_visual_report("BIA_NGUOI")
        elif key == ord("r"):
            # Reset all background models (useful after big lighting change)
            for st in target_states.values():
                with st.lock:
                    st.bg_float     = None
                    st.noise_ready  = False
                    st.warmup_diffs = []
                    st.warmup_count = 0
                    st.H_cached     = None
                    st.H_src_prev   = None
            print("  Background models reset.")

    executor.shutdown(wait=False)
    cap.release()
    cv2.destroyAllWindows()
    print("  Pipeline stopped.")


if __name__ == "__main__":
    main()