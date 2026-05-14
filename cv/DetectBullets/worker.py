import time

import cv2
import numpy as np

from config import *
from layer1 import process_layer_1
from layer2 import process_layer_2
from layer3 import tracking_hungarian
from scoring import calculate_score


def remove_confirmed_from_mask(mask, confirmed_items, radius):
    """
    Remove already confirmed bullet regions from the dark mask so Layer 2 only
    runs on new candidates.
    """
    clean_mask = mask.copy()
    radius_factor = globals().get("CONFIRMED_MASK_RADIUS_FACTOR", 1.0)

    for _, data in confirmed_items.items():
        cx, cy = data["pos"]
        cv2.circle(
            clean_mask,
            (int(cx), int(cy)),
            int(radius * radius_factor),
            0,
            -1,
        )

    return clean_mask


def extract_candidates_from_mask(mask):
    cnts, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates = []

    for c in cnts:
        if cv2.contourArea(c) < 400:
            continue

        hull = cv2.convexHull(c)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)

        if perimeter == 0:
            continue

        circularity = 4 * np.pi * (area / (perimeter ** 2))

        if circularity >= CIRCULARITY_THRESH:
            candidates.append({
                "contour": c,
                "label": "bullet",
            })

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
        warped_gray = cv2.GaussianBlur(
            cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY),
            (5, 5),
            0,
        )

        if bg_dict[target_name] is None:
            bg_dict[target_name] = warped_gray

            worker_elapsed = time.time() - worker_start
            worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0

            cv2.putText(
                warped,
                f"Worker FPS: {worker_fps:.1f}",
                (30, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 0, 0),
                2,
            )

            out_q.put((target_name, cv2.resize(warped, (400, 566))))
            continue

        candidates, dark_mask = process_layer_1(
            bg_dict[target_name],
            warped_gray,
            dst_points,
        )

        new_only_mask = remove_confirmed_from_mask(
            dark_mask,
            target_state["confirmed"],
            EXPECTED_RADIUS,
        )
        new_candidates = extract_candidates_from_mask(new_only_mask)

        new_bg = cv2.addWeighted(
            bg_dict[target_name],
            1.0 - BG_ALPHA,
            warped_gray,
            BG_ALPHA,
            0,
        )
        bg_dict[target_name] = np.where(
            dark_mask > 0,
            bg_dict[target_name],
            new_bg,
        )

        raw_circles = []

        for cand in new_candidates:
            contour = cand["contour"]
            cv2.drawContours(
                warped,
                [contour],
                -1,
                (255, 255, 0),
                1,
            )
            raw_circles.extend(
                process_layer_2(
                    contour,
                    EXPECTED_RADIUS,
                    warped_gray.shape,
                )
            )

        prev_confirmed_ids = set(target_state["confirmed"].keys())
        all_display = tracking_hungarian(
            target_state,
            raw_circles,
            frame_idx,
        )
        new_confirmed_ids = set(target_state["confirmed"].keys()) - prev_confirmed_ids

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

            cv2.putText(
                warped,
                str(score),
                (px[0] + int(r), px[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 0, 0),
                5,
            )
            cv2.putText(
                warped,
                str(score),
                (px[0] + int(r), px[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (255, 255, 255),
                2,
            )

        worker_elapsed = time.time() - worker_start
        worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0

        cv2.putText(
            warped,
            f"Hits: {len(all_display)} | Total: {total_score}",
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (0, 0, 255),
            3,
        )
        cv2.putText(
            warped,
            f"Worker FPS: {worker_fps:.1f}",
            (30, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 0, 0),
            2,
        )
        cv2.putText(
            warped,
            f"Candidates: {len(candidates)} -> New: {len(new_candidates)} | Raw: {len(raw_circles)}",
            (30, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 0, 0),
            2,
        )

        out_q.put((target_name, cv2.resize(warped, (400, 566))))
