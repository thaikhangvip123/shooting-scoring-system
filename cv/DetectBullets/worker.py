import cv2
import numpy as np
import queue
import time
from pathlib import Path

from config import *
from scoring import calculate_score
from layer1 import create_mog2_subtractor, process_layer_1, process_layer_1_mog2
from layer2 import process_layer_2
from layer3 import tracking_hungarian


def put_latest(out_q, item):
    try:
        if out_q.full():
            out_q.get_nowait()
        out_q.put_nowait(item)
    except (queue.Empty, queue.Full):
        pass


def resolve_cnn_model_path():
    if CNN_MODEL_PATH:
        return Path(CNN_MODEL_PATH)
    return Path(__file__).resolve().parent / "models" / "mobilenetv3_bullet.pt"


def create_cnn_classifier():
    if not USE_CNN_CLASSIFIER:
        return None

    try:
        from ml.bullet_classifier import BulletClassifier
    except ModuleNotFoundError as exc:
        print(f"CNN disabled: missing dependency {exc.name}")
        return None

    model_path = resolve_cnn_model_path()
    if not model_path.exists():
        print(f"CNN disabled: model not found at {model_path}")
        return None

    try:
        classifier = BulletClassifier(model_path)
    except Exception as exc:
        print(f"CNN disabled: failed to load model: {exc}")
        return None

    print(
        "CNN classifier enabled "
        f"(input={classifier.input_size}, threshold={classifier.threshold:.3f}, "
        f"crop_scale={CNN_CROP_SCALE:.2f})"
    )
    return classifier


def crop_candidate_context(image_bgr, candidate, crop_size):
    x, y, w, h = cv2.boundingRect(candidate["contour"])
    center_x = x + w // 2
    center_y = y + h // 2
    half = crop_size // 2

    top = center_y - half
    bottom = center_y + half
    left = center_x - half
    right = center_x + half

    if top < 0 or left < 0 or bottom > image_bgr.shape[0] or right > image_bgr.shape[1]:
        return None
    return image_bgr[top:bottom, left:right]


def predict_patches_batch(classifier, patches):
    import torch

    if not patches:
        return []

    tensors = []
    for patch in patches:
        patch_rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
        tensors.append(classifier.transform(patch_rgb))

    x = torch.stack(tensors, dim=0).to(classifier.device)
    with torch.no_grad():
        logits = classifier.model(x)
        probabilities = torch.softmax(logits, dim=1)
        return probabilities[:, classifier.bullet_class_index].detach().cpu().tolist()


def filter_candidates_with_cnn(classifier, image_bgr, candidates):
    if classifier is None or not candidates:
        return candidates

    if CNN_MAX_CANDIDATES_PER_FRAME > 0:
        candidates = sorted(
            candidates,
            key=lambda candidate: cv2.contourArea(candidate["contour"]),
            reverse=True,
        )[:CNN_MAX_CANDIDATES_PER_FRAME]

    crop_size = max(2, int(round(classifier.input_size * CNN_CROP_SCALE)))
    if crop_size % 2:
        crop_size += 1

    patch_rows = []
    for candidate in candidates:
        scored = dict(candidate)
        patch = crop_candidate_context(image_bgr, scored, crop_size)
        if patch is None:
            continue
        patch_rows.append((scored, patch))

    probabilities = predict_patches_batch(classifier, [row[1] for row in patch_rows])
    kept = []
    for (candidate, _patch), probability in zip(patch_rows, probabilities):
        candidate["cnn_probability"] = probability
        if probability >= classifier.threshold:
            kept.append(candidate)

    return kept


def should_run_cnn(frame_idx):
    return CNN_EVERY_N_FRAMES <= 1 or frame_idx % CNN_EVERY_N_FRAMES == 0


def remove_confirmed_from_mask(mask, confirmed_items, radius):
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


def build_sequential_change_mask(prev_gray, current_gray):
    if prev_gray is None:
        return np.zeros(current_gray.shape, dtype=np.uint8)

    new_dark = cv2.subtract(prev_gray, current_gray)
    _, change_mask = cv2.threshold(
        new_dark,
        SEQUENTIAL_DIFF_THRESH,
        255,
        cv2.THRESH_BINARY,
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


def extract_candidates_from_mask(mask):
    cnts, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates = []
    min_area = MOG2_MIN_AREA if USE_MOG2_LAYER1 else LAYER1_CLUSTER_MIN_AREA
    max_area = MOG2_MAX_AREA if USE_MOG2_LAYER1 else None

    for c in cnts:
        contour_area = cv2.contourArea(c)
        if contour_area < min_area:
            continue
        if max_area is not None and contour_area > max_area:
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


def candidate_center(candidate):
    contour = candidate["contour"]
    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        return int(moments["m10"] / moments["m00"]), int(moments["m01"] / moments["m00"])

    x, y, w, h = cv2.boundingRect(contour)
    return x + w // 2, y + h // 2


def filter_candidates_by_mask(candidates, mask):
    if not candidates:
        return []

    kept = []
    height, width = mask.shape[:2]

    for candidate in candidates:
        cx, cy = candidate_center(candidate)
        if 0 <= cx < width and 0 <= cy < height and mask[cy, cx] > 0:
            kept.append(candidate)

    return kept


def extract_cluster_candidates_with_new_evidence(dark_mask, new_evidence_mask):
    if cv2.countNonZero(new_evidence_mask) == 0:
        return extract_candidates_from_mask(
            remove_confirmed_from_mask(
                dark_mask,
                {},
                EXPECTED_RADIUS,
            )
        )

    dilate_size = max(3, int(SEQUENTIAL_DILATE_RADIUS) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_size, dilate_size))
    evidence_zone = cv2.dilate(new_evidence_mask, kernel)

    cnts, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    min_area = MOG2_MIN_AREA if USE_MOG2_LAYER1 else LAYER1_CLUSTER_MIN_AREA
    max_area = MOG2_MAX_AREA if USE_MOG2_LAYER1 else None

    for c in cnts:
        contour_area = cv2.contourArea(c)
        if contour_area < min_area:
            continue
        if max_area is not None and contour_area > max_area:
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
                "label": "bullet",
            })

    return candidates


def draw_candidate_label(warped, candidate):
    if "cnn_probability" not in candidate:
        return

    x, y, _, _ = cv2.boundingRect(candidate["contour"])
    cv2.putText(
        warped,
        f"{candidate['cnn_probability']:.2f}",
        (x, max(20, y - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 0),
        1,
    )


def record_new_confirmed(recorder, frame_idx, target_name, target_state, new_confirmed_ids):
    if recorder is None:
        return

    target_type = target_name.replace("BIA_", "")
    for bullet_id in new_confirmed_ids:
        data = target_state["confirmed"].get(bullet_id)
        if data is None:
            continue

        cx, cy = data["pos"]
        radius = data["r"]
        x_px = float(cx * SCALE_FACTOR)
        y_px = float(cy * SCALE_FACTOR)
        radius_px = float(radius * SCALE_FACTOR)
        score = calculate_score(target_name, (int(x_px), int(y_px)))

        recorder.record(
            frame_idx=frame_idx,
            target_type=target_type,
            bullet_id=bullet_id,
            x_px=x_px,
            y_px=y_px,
            radius=radius_px,
            scores=score,
        )


def suppress_duplicate_raw_circles(raw_circles):
    if not raw_circles:
        return []

    kept = []
    min_dist = EXPECTED_RADIUS * NMS_MIN_DIST_FACTOR

    for circle in raw_circles:
        cx, cy, _ = circle
        duplicate = False

        for kept_circle in kept:
            kx, ky, _ = kept_circle
            dist = ((cx - kx) ** 2 + (cy - ky) ** 2) ** 0.5
            if dist < min_dist:
                duplicate = True
                break

        if not duplicate:
            kept.append(circle)

    return kept


def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q, recorder=None):
    mog2_subtractor = create_mog2_subtractor() if USE_MOG2_LAYER1 else None
    cnn_classifier = create_cnn_classifier()
    mog2_frame_count = 0
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
            target_state["prev_gray"] = warped_gray.copy()

            if mog2_subtractor is not None:
                mog2_frame_count += 1
                mog2_subtractor.apply(warped_gray, learningRate=-1)

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

            put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
            continue

        if USE_MOG2_LAYER1:
            mog2_frame_count += 1
            candidates, dark_mask = process_layer_1_mog2(
                mog2_subtractor,
                warped_gray,
                dst_points,
                mog2_frame_count,
            )
        else:
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

        if USE_MOG2_LAYER1 and mog2_frame_count <= MOG2_WARMUP_FRAMES:
            new_candidates = []
        elif USE_MOG2_LAYER1:
            new_candidates = (
                filter_candidates_by_mask(candidates, new_only_mask)
                if USE_CONFIRMED_MASK_FOR_MOG2_CANDIDATES
                else candidates
            )
        else:
            new_candidates = extract_candidates_from_mask(new_only_mask)

        sequential_mask = build_sequential_change_mask(
            target_state.get("prev_gray"),
            warped_gray,
        )

        if (
            cv2.countNonZero(sequential_mask) > 0
            and not USE_MOG2_LAYER1
            and not (USE_MOG2_LAYER1 and mog2_frame_count <= MOG2_WARMUP_FRAMES)
        ):
            new_candidates = extract_cluster_candidates_with_new_evidence(
                dark_mask,
                sequential_mask,
            )

        new_bg = cv2.addWeighted(
            bg_dict[target_name],
            1.0 - BG_ALPHA,
            warped_gray,
            BG_ALPHA,
            0,
        )
        bg_dict[target_name] = np.where(dark_mask > 0, bg_dict[target_name], new_bg)

        before_cnn_count = len(new_candidates)
        if cnn_classifier is not None:
            if should_run_cnn(frame_idx):
                new_candidates = filter_candidates_with_cnn(cnn_classifier, warped, new_candidates)
            else:
                new_candidates = []

        raw_circles = []
        for cand in new_candidates:
            contour = cand["contour"]
            cv2.drawContours(warped, [contour], -1, (255, 255, 0), 1)
            draw_candidate_label(warped, cand)
            raw_circles.extend(
                process_layer_2(
                    contour,
                    EXPECTED_RADIUS,
                    warped_gray.shape,
                    warped_gray,
                )
            )

        raw_circles = suppress_duplicate_raw_circles(raw_circles)

        prev_confirmed_ids = set(target_state["confirmed"].keys())
        all_display = tracking_hungarian(
            target_state,
            raw_circles,
            frame_idx,
            sequential_mask,
        )
        new_confirmed_ids = set(target_state["confirmed"].keys()) - prev_confirmed_ids
        record_new_confirmed(recorder, frame_idx, target_name, target_state, new_confirmed_ids)

        if cv2.countNonZero(sequential_mask) == 0 or len(raw_circles) > 0:
            target_state["prev_gray"] = warped_gray.copy()

        total_score = 0
        for bullet_id, cx, cy, r in all_display:
            px = (int(cx), int(cy))
            score = calculate_score(target_name, (int(cx * SCALE_FACTOR), int(cy * SCALE_FACTOR)))
            total_score += score

            cv2.circle(warped, px, int(r), (0, 255, 0), 2)
            cv2.circle(warped, px, 3, (0, 0, 0), -1)

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
        if cnn_classifier is not None:
            cv2.putText(
                warped,
                f"CNN: {len(new_candidates)}/{before_cnn_count}",
                (30, 190),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 0),
                2,
            )

        put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
