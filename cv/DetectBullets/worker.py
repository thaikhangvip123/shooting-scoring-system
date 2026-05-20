import cv2
import numpy as np
import time

from config import *
from control import get_mode, is_target_active, post_shot_to_backend
from scoring import calculate_score
from layer1 import process_layer_1
from layer2 import process_layer_2
from layer3 import tracking_hungarian

def remove_confirmed_from_mask(mask, confirmed_items, radius):
    """
    Xóa vùng vết đạn đã confirmed khỏi dark_mask.
    Mục tiêu: không chạy lại Hough/RANSAC trên vết cũ.
    """
    clean_mask = mask.copy()

    # Nếu chưa có config này thì mặc định dùng 1.4
    radius_factor = globals().get("CONFIRMED_MASK_RADIUS_FACTOR", 1.0)

    for _, data in confirmed_items.items():
        cx, cy = data["pos"]

        cv2.circle(
            clean_mask,
            (int(cx), int(cy)),
            int(radius * radius_factor),
            0,
            -1
        )

    return clean_mask

def build_sequential_change_mask(prev_gray, current_gray):
    if prev_gray is None:
        return np.zeros(current_gray.shape, dtype=np.uint8)

    new_dark = cv2.subtract(prev_gray, current_gray)
    _, change_mask = cv2.threshold(
        new_dark,
        SEQUENTIAL_DIFF_THRESH,
        255,
        cv2.THRESH_BINARY
    )

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    change_mask = cv2.morphologyEx(change_mask, cv2.MORPH_CLOSE, kernel_close)

    filtered = np.zeros_like(change_mask)
    cnts, _ = cv2.findContours(change_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        if cv2.contourArea(c) >= SEQUENTIAL_MIN_AREA:
            cv2.drawContours(filtered, [c], -1, 255, -1)

    return filtered

def extract_cluster_candidates_with_new_evidence(dark_mask, new_evidence_mask):
    if cv2.countNonZero(new_evidence_mask) == 0:
        return extract_candidates_from_mask(
            remove_confirmed_from_mask(
                dark_mask,
                {},
                EXPECTED_RADIUS
            )
        )

    dilate_size = max(3, int(SEQUENTIAL_DILATE_RADIUS) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_size, dilate_size))
    evidence_zone = cv2.dilate(new_evidence_mask, kernel)

    cnts, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for c in cnts:
        if cv2.contourArea(c) < 400:
            continue

        x, y, w, h = cv2.boundingRect(c)
        contour_mask = np.zeros((h, w), dtype=np.uint8)
        shifted = c - np.array([[[x, y]]])
        cv2.drawContours(contour_mask, [shifted], -1, 255, -1)

        evidence_roi = evidence_zone[y:y + h, x:x + w]
        if cv2.countNonZero(cv2.bitwise_and(contour_mask, evidence_roi)) == 0:
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
                "label": "bullet"
            })

    return candidates

def extract_candidates_from_mask(mask):
    """
    Tạo candidates từ mask đã được xóa vùng confirmed.
    Logic lọc tương tự Layer 1: area + circularity.
    """
    cnts, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
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
                "label": "bullet"
            })

    return candidates

def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q):
    print(f"🚀 Worker {target_name} đã sẵn sàng!")

    while True:
        item = in_q.get()
        if item is None:
            break

        worker_start = time.time()

        frame, src_pts, frame_idx = item
        if get_mode() != "SHOOTING" or not is_target_active(target_name):
            continue

        H, _ = cv2.findHomography(src_pts, dst_points)
        warped = cv2.warpPerspective(frame, H, (WIDTH, HEIGHT))
        warped_gray = cv2.GaussianBlur(
            cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY),
            (5, 5),
            0
        )

        # 1. KHỞI TẠO NỀN (FRAME ĐẦU TIÊN)
        if bg_dict[target_name] is None:
            bg_dict[target_name] = warped_gray
            target_state["prev_gray"] = warped_gray.copy()

            worker_elapsed = time.time() - worker_start
            worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0

            cv2.putText(
                warped,
                f"Worker FPS: {worker_fps:.1f}",
                (30, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 0, 0),
                2
            )

            out_q.put((target_name, cv2.resize(warped, (400, 566))))
            continue

        # 2. CHẠY LAYER 1 ĐỂ LẤY DARK MASK BAN ĐẦU
        candidates, dark_mask = process_layer_1(
            bg_dict[target_name],
            warped_gray,
            dst_points
        )

        # 3. XÓA VÙNG ĐÃ CONFIRMED KHỎI MASK
        # Đây là bước quan trọng để tránh chạy lại Layer 2 trên vết đạn cũ.
        new_only_mask = remove_confirmed_from_mask(
            dark_mask,
            target_state["confirmed"],
            EXPECTED_RADIUS
        )

        # 4. TẠO LẠI CANDIDATES CHỈ TỪ VÙNG MỚI
        new_candidates = extract_candidates_from_mask(new_only_mask)

        sequential_mask = build_sequential_change_mask(
            target_state.get("prev_gray"),
            warped_gray
        )

        if cv2.countNonZero(sequential_mask) > 0:
            new_candidates = extract_cluster_candidates_with_new_evidence(
                dark_mask,
                sequential_mask
            )

        # 5. HỌC NỀN ĐỘNG
        # Vẫn dùng dark_mask gốc, không dùng new_only_mask.
        # Vì dark_mask gốc chứa cả vết cũ và vết mới, giúp nền không học nhầm vết đạn.
        new_bg = cv2.addWeighted(
            bg_dict[target_name],
            1.0 - BG_ALPHA,
            warped_gray,
            BG_ALPHA,
            0
        )

        bg_dict[target_name] = np.where(
            dark_mask > 0,
            bg_dict[target_name],
            new_bg
        )

        # 6. CHẠY LAYER 2 CHỈ TRÊN CANDIDATE MỚI
        raw_circles = []

        for cand in new_candidates:
            contour = cand["contour"]

            # Vẽ viền màu Cyan cho candidate mới chưa confirm
            cv2.drawContours(
                warped,
                [contour],
                -1,
                (255, 255, 0),
                1
            )

            raw_circles.extend(
                process_layer_2(
                    contour,
                    EXPECTED_RADIUS,
                    warped_gray.shape
                )
            )

        # 7. CHẠY LAYER 3 (HUNGARIAN TRACKING)
        prev_confirmed_ids = set(target_state["confirmed"].keys())
        all_display = tracking_hungarian(
            target_state,
            raw_circles,
            frame_idx,
            sequential_mask
        )
        new_confirmed_ids = set(target_state["confirmed"].keys()) - prev_confirmed_ids

        if cv2.countNonZero(sequential_mask) == 0 or len(raw_circles) > 0:
            target_state["prev_gray"] = warped_gray.copy()

        # 8. TÍNH ĐIỂM & VẼ KẾT QUẢ CHÍNH THỨC
        total_score = 0

        for bullet_id, cx, cy, r in all_display:
            px = (int(cx), int(cy))

            score = calculate_score(
                target_name,
                (int(cx * SCALE_FACTOR), int(cy * SCALE_FACTOR))
            )

            total_score += score

            if bullet_id in new_confirmed_ids:
                post_shot_to_backend(
                    target_name,
                    bullet_id,
                    cx,
                    cy,
                    score,
                    SCALE_FACTOR
                )

            # Vết đạn đã tracking thành công: vòng xanh + tâm đen
            cv2.circle(warped, px, int(r), (0, 255, 0), 2)
            cv2.circle(warped, px, 3, (0, 0, 0), -1)

            # Ghi điểm
            # cv2.putText(
            #     warped,
            #     str(score),
            #     (px[0] + int(r), px[1] - 5),
            #     cv2.FONT_HERSHEY_SIMPLEX,
            #     1.2,
            #     (0, 0, 0),
            #     5
            # )

            # cv2.putText(
            #     warped,
            #     str(score),
            #     (px[0] + int(r), px[1] - 5),
            #     cv2.FONT_HERSHEY_SIMPLEX,
            #     1.2,
            #     (255, 255, 255),
            #     2
            # )

        # 9. TÍNH WORKER FPS
        worker_elapsed = time.time() - worker_start
        worker_fps = 1.0 / worker_elapsed if worker_elapsed > 0 else 0

        # 10. VẼ THÔNG TIN DEBUG
        cv2.putText(
            warped,
            f"Hits: {len(all_display)} | Total: {total_score}",
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (0, 0, 255),
            3
        )

        cv2.putText(
            warped,
            f"Worker FPS: {worker_fps:.1f}",
            (30, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 0, 0),
            2
        )

        cv2.putText(
            warped,
            f"Candidates: {len(candidates)} -> New: {len(new_candidates)} | Raw: {len(raw_circles)}",
            (30, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 0, 0),
            2
        )

        out_q.put((target_name, cv2.resize(warped, (400, 566))))
