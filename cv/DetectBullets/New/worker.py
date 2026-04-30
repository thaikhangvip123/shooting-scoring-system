import cv2
import numpy as np
from config import *
from scoring import calculate_score
from layer1 import process_layer_1
from layer2 import process_layer_2
from layer3 import tracking_hungarian

def target_worker_thread(target_name, target_state, bg_dict, in_q, out_q):
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
            out_q.put((target_name, cv2.resize(warped, (400, 566))))
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
        all_display = tracking_hungarian(target_state, raw_circles, frame_idx)
        
        # 6. TÍNH ĐIỂM & VẼ KẾT QUẢ CHÍNH THỨC
        total_score = 0
        for (cx, cy, r) in all_display:
            px = (int(cx), int(cy))
            score = calculate_score(target_name, (int(cx * SCALE_FACTOR), int(cy * SCALE_FACTOR)))
            total_score += score
            
            # Vết đạn đã Tracking thành công sẽ có màu Xanh Lá + Tâm đen
            cv2.circle(warped, px, int(r), (0, 255, 0), 2)
            cv2.circle(warped, px, 3, (0, 0, 0), -1)
            
            # Ghi số điểm (Chữ trắng viền đen để không bị chìm màu)
            cv2.putText(warped, str(score), (px[0]+int(r), px[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,0), 5)
            cv2.putText(warped, str(score), (px[0]+int(r), px[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,255), 2)

        cv2.putText(warped, f"Hits: {len(all_display)} | Total: {total_score}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
        out_q.put((target_name, cv2.resize(warped, (400, 566))))