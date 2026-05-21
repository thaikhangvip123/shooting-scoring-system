import queue
import time

import cv2
import numpy as np

from config import *
from layer1 import process_layer_1
from layer2 import process_layer_2
from layer3 import tracking_hungarian
from scoring import calculate_score


def put_latest(out_q, item):
    try:
        if out_q.full():
            out_q.get_nowait()
        out_q.put_nowait(item)
    except (queue.Empty, queue.Full):
        pass


def remove_confirmed_from_mask(mask, confirmed_items, radius):
    clean_mask = mask.copy()
    radius_factor = globals().get("CONFIRMED_MASK_RADIUS_FACTOR", 1.0)

    for data in confirmed_items.values():
        cx, cy = data["pos"]
        cv2.circle(clean_mask, (int(cx), int(cy)), int(radius * radius_factor), 0, -1)

    return clean_mask


def build_sequential_change_mask(prev_gray, current_gray):
    if prev_gray is None:
        return np.zeros(current_gray.shape, dtype=np.uint8)

    new_dark = cv2.subtract(prev_gray, current_gray)
    _, change_mask = cv2.threshold(new_dark, SEQUENTIAL_DIFF_THRESH, 255, cv2.THRESH_BINARY)

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_CLOSE, kernel_close)

    filtered = np.zeros_like(change_mask)
    cnts, _ = cv2.findContours(change_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in cnts:
        if cv2.contourArea(contour) >= SEQUENTIAL_MIN_AREA:
            cv2.drawContours(filtered, [contour], -1, 255, -1)

    return filtered


def extract_cluster_candidates_with_new_evidence(dark_mask, new_evidence_mask):
    if cv2.countNonZero(new_evidence_mask) == 0:
        return extract_candidates_from_mask(remove_confirmed_from_mask(dark_mask, {}, EXPECTED_RADIUS))

    dilate_size = max(3, int(SEQUENTIAL_DILATE_RADIUS) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_size, dilate_size))
    evidence_zone = cv2.dilate(new_evidence_mask, kernel)

    cnts, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for contour in cnts:
        if cv2.contourArea(contour) < 400:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        contour_mask = np.zeros((h, w), dtype=np.uint8)
        shifted = contour - np.array([[[x, y]]])
        cv2.drawContours(contour_mask, [shifted], -1, 255, -1)

        evidence_roi = evidence_zone[y:y + h, x:x + w]
        if cv2.countNonZero(cv2.bitwise_and(contour_mask, evidence_roi)) == 0:
            continue

        hull = cv2.convexHull(contour)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * (area / (perimeter ** 2))
        if circularity >= CIRCULARITY_THRESH:
            candidates.append({"contour": contour, "label": "bullet"})

    return candidates


def extract_candidates_from_mask(mask):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for contour in cnts:
        if cv2.contourArea(contour) < 400:
            continue

        hull = cv2.convexHull(contour)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * (area / (perimeter ** 2))
        if circularity >= CIRCULARITY_THRESH:
            candidates.append({"contour": contour, "label": "bullet"})

    return candidates


def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q, recorder=None):
    print(f"Worker {target_name} ready")

    while True:
        item = in_q.get()
        if item is None:
            break

        worker_start = time.time()
        frame, src_pts, frame_idx = item

        H, _ = cv2.findHomography(src_pts, dst_points)
        warped = cv2.warpPerspective(frame, H, (WIDTH, HEIGHT))
        warped_gray = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        if bg_dict[target_name] is None:
            bg_dict[target_name] = warped_gray
            target_state["prev_gray"] = warped_gray.copy()

            worker_elapsed = time.time() - worker_start
            worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0
            cv2.putText(warped, f"Worker FPS: {worker_fps:.1f}", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
            put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
            continue

        candidates, dark_mask = process_layer_1(bg_dict[target_name], warped_gray, dst_points)
        new_only_mask = remove_confirmed_from_mask(dark_mask, target_state["confirmed"], EXPECTED_RADIUS)
        new_candidates = extract_candidates_from_mask(new_only_mask)

        sequential_mask = build_sequential_change_mask(target_state.get("prev_gray"), warped_gray)
        if cv2.countNonZero(sequential_mask) > 0:
            new_candidates = extract_cluster_candidates_with_new_evidence(dark_mask, sequential_mask)

        new_bg = cv2.addWeighted(bg_dict[target_name], 1.0 - BG_ALPHA, warped_gray, BG_ALPHA, 0)
        bg_dict[target_name] = np.where(dark_mask > 0, bg_dict[target_name], new_bg)

        raw_circles = []
        for cand in new_candidates:
            contour = cand["contour"]
            cv2.drawContours(warped, [contour], -1, (255, 255, 0), 1)
            raw_circles.extend(process_layer_2(contour, EXPECTED_RADIUS, warped_gray.shape))

        prev_confirmed_ids = set(target_state["confirmed"].keys())
        all_display = tracking_hungarian(target_state, raw_circles, frame_idx, sequential_mask)
        new_confirmed_ids = set(target_state["confirmed"].keys()) - prev_confirmed_ids

        if cv2.countNonZero(sequential_mask) == 0 or len(raw_circles) > 0:
            target_state["prev_gray"] = warped_gray.copy()

        total_score = 0
        for bullet_id, cx, cy, r in all_display:
            px = (int(cx), int(cy))
            x_px = float(cx * SCALE_FACTOR)
            y_px = float(cy * SCALE_FACTOR)
            radius_px = float(r * SCALE_FACTOR)
            target_type = target_name.replace("BIA_", "")
            score = calculate_score(target_name, (int(x_px), int(y_px)))
            total_score += score

            if recorder is not None and bullet_id in new_confirmed_ids:
                recorder.record(
                    frame_idx=frame_idx,
                    target_type=target_type,
                    bullet_id=bullet_id,
                    x_px=x_px,
                    y_px=y_px,
                    radius=radius_px,
                    scores=score,
                )

            cv2.circle(warped, px, int(r), (0, 255, 0), 2)
            cv2.circle(warped, px, 3, (0, 0, 0), -1)

        worker_elapsed = time.time() - worker_start
        worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0

        cv2.putText(warped, f"Hits: {len(all_display)} | Total: {total_score}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        cv2.putText(warped, f"Worker FPS: {worker_fps:.1f}", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
        cv2.putText(
            warped,
            f"Candidates: {len(candidates)} -> New: {len(new_candidates)} | Raw: {len(raw_circles)}",
            (30, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 0, 0),
            2,
        )

        put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
