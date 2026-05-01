"""
config.py — All tunable parameters in one place.
Edit this file to tune detection without touching pipeline logic.
"""

from dataclasses import dataclass, field
from typing import Dict
import numpy as np


@dataclass
class PipelineConfig:
    # ------------------------------------------------------------------ Paths
    video_path: str       = "E:/shooting-scoring-system/cv/DetectBullets/target.mp4"
    log_file_path: str    = "E:/shooting-scoring-system/cv/DetectBullets/bullet_logs.txt"
    path_ipsc_poly: str   = "E:/shooting-scoring-system/cv/Scoring/IPSC/polygon.txt"
    path_nguoi_cont: str  = "E:/shooting-scoring-system/cv/Scoring/Nguoi/Nguoi_contours.txt"
    template_paths: Dict[str, str] = field(default_factory=lambda: {
        "BIA_TRON":  "E:/shooting-scoring-system/cv/DetectBullets/A4_Tron3.png",
        "BIA_IPSC":  "E:/shooting-scoring-system/cv/DetectBullets/A4_IPSC2.png",
        "BIA_NGUOI": "E:/shooting-scoring-system/cv/DetectBullets/A4_Nguoi2.png",
    })

    # --------------------------------------------------------------- Canvas
    width: int            = 1240
    height: int           = 1754
    margin: int           = 40
    a4_width_mm: float    = 210.0

    # --------------------------------------------------------- Bullet geometry
    expected_radius: int  = 25   # pixels in warped space

    # ------------------------------------------------------- Background model
    # Lower alpha = slower BG update = less likely to "learn" a bullet hole
    bg_alpha: float       = 0.003
    # How many frames to collect before noise stats are usable
    bg_warmup_frames: int = 5    # was 10 — faster start-up
    # threshold = sigma_mult × noise_std  (lower = more sensitive)
    sigma_mult: float     = 2.8  # was 3.2

    # ---- Layer 1 fallback thresholds (used before noise stats are ready) ---
    # Make these aggressive so we catch holes even during warmup
    dark_thresh_fallback: int   = -28   # was -35
    bright_thresh_fallback: int = 28    # was 25

    # ------------------------------------------------------- Layer 1 contour
    # Minimum blob area to consider (pixels²) — filter out tiny noise
    min_blob_area: int    = 400   # was 500
    # Circularity threshold: >= this → bullet_candidate, else shadow_candidate
    # Real bullet holes are very circular (0.7–1.0).
    # Lowered to 0.55 to handle partial/angled holes.
    circularity_threshold: float = 0.55  # was 0.85 with broken overlap check

    # ---------------------------------------------------- Layer 2 RANSAC
    ransac_iterations: int      = 80
    ransac_inlier_thresh: float = 3.5
    ransac_min_inliers: int     = 8    # was 12 — handles partial circles
    ransac_max_bullets: int     = 5
    hough_param2: int           = 10   # was 14 — more sensitive HoughCircles

    # --------------------------------------------------- Layer 3 tracking
    confirm_frames: int   = 4    # was 5 — confirm slightly faster
    stale_frames: int     = 10
    forget_secs: float    = 2.0
    match_dist: int       = 15

    # ---------------------------------------------------- Homography cache
    homography_drift_thresh: float = 2.0   # px; only recompute when markers move

    # --------------------------------------------------------------- Display
    display_scale: float  = 0.35


# ── Singleton ──────────────────────────────────────────────────────────────
CFG = PipelineConfig()

# ── Derived constants (do not edit — computed from CFG) ───────────────────
PIXELS_PER_MM = CFG.width / CFG.a4_width_mm
CENTER_X_PX   = CFG.width  / 2.0
CENTER_Y_PX   = CFG.height / 2.0
SCALE_FACTOR  = 2480 / CFG.width   # scoring polygons were drawn at 2480 px wide

# Warp destination corners (inside the margin)
DST_POINTS = np.array([
    [CFG.margin,               CFG.margin],
    [CFG.width  - CFG.margin,  CFG.margin],
    [CFG.width  - CFG.margin,  CFG.height - CFG.margin],
    [CFG.margin,               CFG.height - CFG.margin],
], dtype=np.float32)

# ArUco marker ID sets per target
TARGET_SETS = {
    "BIA_TRON":  [0, 1, 2, 3],
    "BIA_IPSC":  [4, 5, 6, 7],
    "BIA_NGUOI": [8, 9, 10, 11],
}
