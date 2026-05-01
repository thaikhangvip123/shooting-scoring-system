"""
layer3.py — Layer 3: temporal tracking with Hungarian assignment.

Every frame, raw circle detections from Layer 2 are matched to existing
candidates / confirmed bullets using the Hungarian algorithm (optimal
minimum-cost assignment). Unmatched detections spawn new candidates.
Candidates promoted after `confirm_frames` consistent sightings.

Scoring is cached at promotion time so it's never recomputed.
"""

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from config import CFG
from state import TargetState


# ── Hungarian matching helper ────────────────────────────────────────────────

def _match_hungarian(
        existing_pos:   List[Tuple[float, float]],
        new_detections: List[Tuple],          # (cx, cy, r, ...)
        max_dist:       float,
) -> Tuple[List[Tuple[int, int]], List[int]]:
    """
    Optimal (minimum-cost) 1-to-1 assignment between existing positions
    and new detections, capping cost at `max_dist`.

    Returns:
        matched       — list of (new_idx, existing_idx) pairs within max_dist
        unmatched_new — indices in new_detections with no assignment
    """
    if not existing_pos or not new_detections:
        return [], list(range(len(new_detections)))

    new_pts = np.array([(x, y) for x, y, *_ in new_detections], dtype=float)
    ex_pts  = np.array(existing_pos, dtype=float)

    diffs = new_pts[:, None, :] - ex_pts[None, :, :]        # (N, M, 2)
    cost  = np.sqrt((diffs ** 2).sum(axis=2))               # (N, M)
    cost[cost > max_dist] = 1e9                              # block far pairs

    row_ind, col_ind = linear_sum_assignment(cost)
    matched   = [(r, c) for r, c in zip(row_ind, col_ind)
                 if cost[r, c] < max_dist]
    matched_r = {r for r, _ in matched}
    unmatched = [i for i in range(len(new_detections)) if i not in matched_r]
    return matched, unmatched


# ── Main tracking function ───────────────────────────────────────────────────

def temporal_tracking(
        state:       TargetState,
        raw_circles: List[Tuple[int, int, int]],   # from Layer 2
        now:         float,                         # time.monotonic()
) -> List[Tuple[float, float, int]]:
    """
    Update candidate / confirmed sets and return confirmed bullet positions.

    Steps:
      1. Match raw detections → confirmed bullets (position smoothing)
      2. Match remaining     → existing candidates (count bump)
      3. Promote candidates that reached confirm_frames
      4. Spawn new candidates for unmatched detections
      5. Garbage-collect stale candidates and forgotten confirmed bullets

    Returns:
        List of (cx, cy, radius) for all currently confirmed bullets.
    """
    alpha = 0.2   # exponential smoothing for confirmed bullet positions

    # ── 1. Match raw → confirmed ─────────────────────────────────────────────
    conf_ids  = list(state.confirmed.keys())
    conf_pos  = [state.confirmed[cid]["pos"] for cid in conf_ids]

    matched_conf, remaining_raw_idx = _match_hungarian(
        conf_pos, raw_circles, CFG.match_dist
    )

    for new_i, conf_i in matched_conf:
        cid    = conf_ids[conf_i]
        ox, oy = state.confirmed[cid]["pos"]
        nx, ny, _ = raw_circles[new_i]
        state.confirmed[cid]["pos"]       = (ox * (1 - alpha) + nx * alpha,
                                              oy * (1 - alpha) + ny * alpha)
        state.confirmed[cid]["last_time"] = now

    remaining_raw = [raw_circles[i] for i in remaining_raw_idx]

    # ── 2. Match remaining → candidates ──────────────────────────────────────
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
        state.candidates[cid]["pos"]       = (ox * 0.5 + nx * 0.5,
                                               oy * 0.5 + ny * 0.5)
        state.candidates[cid]["last_time"] = now

        # ── 3. Promote to confirmed ───────────────────────────────────────
        if state.candidates[cid]["count"] >= CFG.confirm_frames:
            cx, cy = state.candidates[cid]["pos"]
            state.confirmed[cid] = {
                "pos":       state.candidates[cid]["pos"],
                "r":         r,
                "last_time": now,
                "score":     0,   # placeholder; will be filled below
            }
            state.compute_and_cache_score(cid)   # fills score in-place
            print(f"  [{state.name}] Bullet #{cid} confirmed at "
                  f"({cx:.0f}, {cy:.0f}) → score {state.confirmed[cid]['score']}")
            del state.candidates[cid]

    # ── 4. Spawn new candidates ───────────────────────────────────────────────
    for new_i in truly_new_idx:
        nx, ny, r = remaining_raw[new_i]
        cid = state.next_id
        state.next_id += 1
        state.candidates[cid] = {
            "pos":       (float(nx), float(ny)),
            "r":         r,
            "count":     1,
            "last_time": now,
        }

    # ── 5. Garbage-collect stale entries ─────────────────────────────────────
    stale_thresh  = now - (CFG.stale_frames / 30.0)   # approx 30 fps
    forget_thresh = now - CFG.forget_secs

    stale_cands = [k for k, v in state.candidates.items()
                   if v["last_time"] < stale_thresh]
    for k in stale_cands:
        del state.candidates[k]

    # Only forget confirmed bullets if they vanish for longer than forget_secs.
    # In practice once a hole is there it stays, so this mainly handles video
    # cuts or target changes.
    stale_conf = [k for k, v in state.confirmed.items()
                  if v["last_time"] < forget_thresh]
    for k in stale_conf:
        del state.confirmed[k]

    return [(v["pos"][0], v["pos"][1], v["r"])
            for v in state.confirmed.values()]
