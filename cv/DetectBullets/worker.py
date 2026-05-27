import cv2
import numpy as np
import queue
from pathlib import Path
from config import *
from scoring import calculate_score
from layer1 import process_layer_1
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

    crop_size = max(2, int(round(classifier.input_size * CNN_CROP_SCALE)))
    if crop_size % 2:
        crop_size += 1

    scored_candidates = []
    patch_rows = []
    for candidate in candidates:
        scored = dict(candidate)
        patch = crop_candidate_context(image_bgr, scored, crop_size)
        if patch is None:
            continue
        patch_rows.append((scored, patch))
        scored_candidates.append(scored)

    probabilities = predict_patches_batch(classifier, [row[1] for row in patch_rows])
    kept = []
    for (candidate, _patch), probability in zip(patch_rows, probabilities):
        candidate["cnn_probability"] = probability
        if probability >= classifier.threshold:
            kept.append(candidate)

    return kept

def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q, recorder=None):
    cnn_classifier = create_cnn_classifier()
    print(f"🚀 Worker {target_name} đã sẵn sàng!")

    while True:
        item = in_q.get()
        if item is None: break 
        frame, src_pts, frame_idx = item

        H, _ = cv2.findHomography(src_pts, dst_points)
        warped = cv2.warpPerspective(frame, H, (WIDTH, HEIGHT))
        warped_gray = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        # 1. KHỞI TẠO NỀN (FRAME ĐẦU TIÊN)
        if bg_dict[target_name] is None:
            bg_dict[target_name] = warped_gray
            put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
            continue 

        # 2. CHẠY LAYER 1 TRƯỚC ĐỂ TÌM MẶT NẠ VẾT ĐẠN (NÉ VẾT ĐẠN RA)
        candidates, dark_mask = process_layer_1(bg_dict[target_name], warped_gray, dst_points)
        layer1_candidate_count = len(candidates)
        candidates = filter_candidates_with_cnn(cnn_classifier, warped, candidates)
        
        # 3. HỌC NỀN ĐỘNG (THÔNG MINH)
        # Tính toán nền mới tạm thời
        new_bg = cv2.addWeighted(bg_dict[target_name], 1.0 - BG_ALPHA, warped_gray, BG_ALPHA, 0)
        # Dùng np.where: Nơi nào CÓ vết đạn đen (dark_mask > 0) -> Giữ nền CŨ. 
        # Nơi nào là giấy sạch -> Cập nhật nền MỚI.
        bg_dict[target_name] = np.where(dark_mask > 0, bg_dict[target_name], new_bg)

        # 4. CHẠY LAYER 2 (RANSAC / HOUGH)
        raw_circles = []
        for cand in candidates:
            # Vẽ viền màu Cyan cho các candidate chưa confirm
            cv2.drawContours(warped, [cand["contour"]], -1, (255, 255, 0), 1)
            if "cnn_probability" in cand:
                x, y, _, _ = cv2.boundingRect(cand["contour"])
                cv2.putText(
                    warped,
                    f"{cand['cnn_probability']:.2f}",
                    (x, max(20, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 0),
                    1,
                )
            raw_circles.extend(process_layer_2(cand["contour"], EXPECTED_RADIUS, warped_gray.shape))

        # 5. CHẠY LAYER 3 (HUNGARIAN TRACKING)
        prev_confirmed_ids = set(target_state["confirmed"].keys())
        all_display = tracking_hungarian(target_state, raw_circles, frame_idx)
        new_confirmed_ids = set(target_state["confirmed"].keys()) - prev_confirmed_ids
        
        # 6. TÍNH ĐIỂM & VẼ KẾT QUẢ CHÍNH THỨC
        total_score = 0
        for (bullet_id, cx, cy, r) in all_display:
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
            
            # Vết đạn đã Tracking thành công sẽ có màu Xanh Lá + Tâm đen
            cv2.circle(warped, px, int(r), (0, 255, 0), 2)
            cv2.circle(warped, px, 3, (0, 0, 0), -1)
            
            # Ghi số điểm (Chữ trắng viền đen để không bị chìm màu)
            cv2.putText(warped, str(score), (px[0]+int(r), px[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,0), 5)
            cv2.putText(warped, str(score), (px[0]+int(r), px[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,255), 2)

        cv2.putText(warped, f"Hits: {len(all_display)} | Total: {total_score}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
        if cnn_classifier is not None:
            cv2.putText(
                warped,
                f"CNN: {len(candidates)}/{layer1_candidate_count}",
                (30, 105),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 0),
                2,
            )
        put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
