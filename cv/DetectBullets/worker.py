import cv2
import numpy as np
import queue
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

def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q, recorder=None):
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
        put_latest(out_q, (target_name, cv2.resize(warped, (400, 566))))
