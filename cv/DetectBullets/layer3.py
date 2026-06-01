import numpy as np
import math
import cv2
from scipy.optimize import linear_sum_assignment
from config import *


def has_new_evidence(raw_circle, new_evidence_mask):
    if new_evidence_mask is None:
        return False

    nx, ny, r = raw_circle
    probe_radius = max(3, int(r * 0.55))
    x1 = max(0, int(nx) - probe_radius)
    y1 = max(0, int(ny) - probe_radius)
    x2 = min(new_evidence_mask.shape[1], int(nx) + probe_radius + 1)
    y2 = min(new_evidence_mask.shape[0], int(ny) + probe_radius + 1)

    if x1 >= x2 or y1 >= y2:
        return False

    roi = new_evidence_mask[y1:y2, x1:x2]
    probe = np.zeros(roi.shape, dtype=np.uint8)
    cv2.circle(probe, (int(nx) - x1, int(ny) - y1), probe_radius, 255, -1)
    evidence_area = cv2.countNonZero(cv2.bitwise_and(roi, probe))
    return evidence_area >= NEW_EVIDENCE_DUPLICATE_MIN_AREA


def is_duplicate_confirmed(raw_circle, confirmed_items, new_evidence_mask=None):
    nx, ny, _ = raw_circle
    for data in confirmed_items.values():
        ox, oy = data["pos"]
        dist = math.sqrt((nx - ox) ** 2 + (ny - oy) ** 2)
        if dist < CONFIRMED_STRICT_DUPLICATE_DIST:
            return True
        if dist < CONFIRMED_DUPLICATE_DIST:
            if has_new_evidence(raw_circle, new_evidence_mask):
                continue
            return True
    return False


def tracking_hungarian(state, raw_circles, frame_idx, new_evidence_mask=None):
    tracked_items = {}
    for cid, data in state["candidates"].items():
        tracked_items[cid] = data
    for cid, data in state["confirmed"].items():
        confirmed_frame = data.get("confirmed_frame", frame_idx)
        confirmed_age = frame_idx - confirmed_frame
        if confirmed_age <= CONFIRMED_SMOOTH_FRAMES:
            tracked_items[cid] = data

    tracked_ids = list(tracked_items.keys())

    if len(tracked_ids) == 0 or len(raw_circles) == 0:
        matches = []
        unmatched_raw = list(range(len(raw_circles)))
    else:
        cost_matrix = np.zeros((len(tracked_ids), len(raw_circles)), dtype=np.float32)
        for i, tid in enumerate(tracked_ids):
            ox, oy = tracked_items[tid]["pos"]
            for j, (nx, ny, _) in enumerate(raw_circles):
                dist = math.sqrt((nx - ox) ** 2 + (ny - oy) ** 2)
                cost_matrix[i, j] = dist if dist < MATCH_DIST else 999999

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matches = []
        unmatched_raw = set(range(len(raw_circles)))
        for i, j in zip(row_ind, col_ind):
            if cost_matrix[i, j] < MATCH_DIST:
                matches.append((tracked_ids[i], j))
                unmatched_raw.remove(j)
        unmatched_raw = list(unmatched_raw)

    for tid, raw_idx in matches:
        nx, ny, r = raw_circles[raw_idx]
        if tid in state["candidates"]:
            ox, oy = state["candidates"][tid]["pos"]
            state["candidates"][tid]["pos"] = (ox * 0.5 + nx * 0.5, oy * 0.5 + ny * 0.5)
            state["candidates"][tid]["last_frame"] = frame_idx
            state["candidates"][tid]["count"] += 1
            if state["candidates"][tid]["count"] >= CONFIRM_FRAMES:
                state["confirmed"][tid] = state["candidates"].pop(tid)
                state["confirmed"][tid]["confirmed_frame"] = frame_idx
        elif tid in state["confirmed"]:
            confirmed_frame = state["confirmed"][tid].get("confirmed_frame", frame_idx)
            confirmed_age = frame_idx - confirmed_frame
            if confirmed_age <= CONFIRMED_SMOOTH_FRAMES:
                ox, oy = state["confirmed"][tid]["pos"]
                state["confirmed"][tid]["pos"] = (ox * 0.8 + nx * 0.2, oy * 0.8 + ny * 0.2)
                state["confirmed"][tid]["last_frame"] = frame_idx

    for raw_idx in unmatched_raw:
        if is_duplicate_confirmed(raw_circles[raw_idx], state["confirmed"], new_evidence_mask):
            continue

        nx, ny, r = raw_circles[raw_idx]
        new_id = state["next_id"]
        state["next_id"] += 1
        state["candidates"][new_id] = {"pos": (nx, ny), "r": r, "count": 1, "last_frame": frame_idx}

    stale_c = [k for k, v in state["candidates"].items() if frame_idx - v["last_frame"] > STALE_FRAMES]
    for k in stale_c:
        del state["candidates"][k]
    stale_cf = [k for k, v in state["confirmed"].items() if frame_idx - v["last_frame"] > FORGET_FRAMES]
    for k in stale_cf:
        del state["confirmed"][k]

    return [(k, v["pos"][0], v["pos"][1], v["r"]) for k, v in state["confirmed"].items()]
