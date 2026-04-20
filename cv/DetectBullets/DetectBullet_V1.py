import cv2
import cv2.aruco as aruco
import numpy as np
import os
import math
import random
from datetime import datetime # Thêm thư viện để lấy thời gian thực

# ==========================================
# 1. CẤU HÌNH ĐƯỜNG DẪN & THÔNG SỐ LÕI
# ==========================================
VIDEO_PATH = "D:/baitapxaml/HK252/DATN/DetectBullet/IPSC.mp4"
EXPECTED_RADIUS = 25  
LOG_FILE_PATH = "bullet_logs.txt" # Thêm đường dẫn file log

# ==========================================
# BỘ NHỚ TẦNG 3: TEMPORAL TRACKING (CÓ CƠ CHẾ "QUÊN")
# ==========================================
tracked_bullets = {
    "BIA_TRON":  {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_IPSC":  {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_NGUOI": {"candidates": {}, "confirmed": {}, "next_id": 0},
}

# ĐÃ SỬA match_dist=15 (0.6 * EXPECTED_RADIUS) để chống nuốt đạn dính chùm
def temporal_tracking(target_name, raw_circles, frame_idx, confirm_frames=5, stale_frames=10, forget_frames=30, match_dist=15):
    """
    TẦNG 3 NÂNG CẤP: 
    - forget_frames: Số frame vắng mặt để XÓA vết đạn đã Confirmed (Sửa lỗi nhớ dai false positive).
    """
    state = tracked_bullets[target_name]
    alpha = 0.2
    used_raw = set()

    # 1. Ưu tiên map raw_circles với các vết đạn ĐÃ XÁC NHẬN (Confirmed)
    for cid, cdata in list(state["confirmed"].items()):
        ox, oy = cdata["pos"]
        for j, (nx, ny, r) in enumerate(raw_circles):
            if j in used_raw: continue
            if math.sqrt((nx - ox)**2 + (ny - oy)**2) < match_dist:
                # Làm mượt EMA
                smooth_x = ox * (1 - alpha) + nx * alpha
                smooth_y = oy * (1 - alpha) + ny * alpha
                state["confirmed"][cid]["pos"] = (smooth_x, smooth_y)
                state["confirmed"][cid]["last_frame"] = frame_idx
                used_raw.add(j)
                break

    # 2. Map các raw_circles còn thừa với các Ứng viên (Candidates)
    for j, (nx, ny, r) in enumerate(raw_circles):
        if j in used_raw: continue
        matched_id = None
        for cid, cdata in state["candidates"].items():
            ox, oy = cdata["pos"]
            if math.sqrt((nx - ox)**2 + (ny - oy)**2) < match_dist:
                matched_id = cid
                break

        if matched_id is not None:
            state["candidates"][matched_id]["count"] += 1
            ox, oy = state["candidates"][matched_id]["pos"]
            state["candidates"][matched_id]["pos"] = (ox * 0.5 + nx * 0.5, oy * 0.5 + ny * 0.5)
            state["candidates"][matched_id]["last_frame"] = frame_idx

            if state["candidates"][matched_id]["count"] >= confirm_frames:
                # Chuyển lên Confirmed
                state["confirmed"][matched_id] = {
                    "pos": state["candidates"][matched_id]["pos"],
                    "r": r,
                    "last_frame": frame_idx
                }
                del state["candidates"][matched_id]
        else:
            cid = state["next_id"]
            state["next_id"] += 1
            state["candidates"][cid] = {
                "pos": (nx, ny), "r": r,
                "count": 1, "last_frame": frame_idx
            }

    # 3. QUÉT RÁC & SỬA SAI (GARBAGE COLLECTION)
    # Xóa candidates lâu không thấy
    stale_cands = [k for k, v in state["candidates"].items() if frame_idx - v["last_frame"] > stale_frames]
    for k in stale_cands: del state["candidates"][k]

    # FIX LỖI NHỚ DAI: Xóa Confirmed nếu vắng mặt > forget_frames (ví dụ 30 frames ~ 1 giây)
    stale_conf = [k for k, v in state["confirmed"].items() if frame_idx - v["last_frame"] > forget_frames]
    for k in stale_conf: del state["confirmed"][k]

    # Trả về tọa độ để vẽ
    return [(v["pos"][0], v["pos"][1], v["r"]) for v in state["confirmed"].values()]

# ==========================================
# 2. HÀM TẦNG 1 (ĐÃ FIX LỖI CHE ARUCO)
# ==========================================
def process_layer_1_signed_diff(bg_gray, current_gray, dst_points, margin, dark_thresh=-35, bright_thresh=25):
    bg_int = bg_gray.astype(np.int16)
    curr_int = current_gray.astype(np.int16)
    signed_diff = curr_int - bg_int
    
    darkening_mask = np.where(signed_diff < dark_thresh, 255, 0).astype(np.uint8)
    brightening_mask = np.where(signed_diff > bright_thresh, 255, 0).astype(np.uint8)
    
    # --- BƯỚC FIX LỖI: CHE MASK ARUCO TẬN GỐC ---
    # Tô đen 4 góc TRƯỚC khi làm Morphology hay findContours
    mask_radius = 350
    for pt in dst_points:
        cv2.circle(darkening_mask, (int(pt[0]), int(pt[1])), mask_radius, 0, -1)
        cv2.circle(brightening_mask, (int(pt[0]), int(pt[1])), mask_radius, 0, -1)
    
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_OPEN, kernel_open)
    
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    darkening_mask = cv2.dilate(darkening_mask, kernel_dilate, iterations=1)
    
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_CLOSE, kernel_close)
    
    cnts, _ = cv2.findContours(darkening_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 500: continue
            
        perimeter = cv2.arcLength(c, True)
        if perimeter == 0: continue
        
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0: continue
        
        hull_perimeter = cv2.arcLength(hull, True)
        if hull_perimeter == 0: continue
        
        circularity = 4 * np.pi * (hull_area / (hull_perimeter * hull_perimeter))
        if circularity < 0.85:
            candidates.append({"contour": hull, "label": "shadow_candidate", "area": hull_area})
            continue

        blob_mask = np.zeros_like(darkening_mask)
        cv2.drawContours(blob_mask, [hull], -1, 255, -1)
        
        dense_cnts, _ = cv2.findContours(blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not dense_cnts: continue
        dense_contour = dense_cnts[0]

        overlap = cv2.bitwise_and(blob_mask, brightening_mask)
        overlap_area = cv2.countNonZero(overlap)
        blob_pixel_count = cv2.countNonZero(blob_mask)
        overlap_ratio = overlap_area / blob_pixel_count if blob_pixel_count > 0 else 0
        
        label = "shadow_candidate" if overlap_ratio >= 0.20 else "bullet_candidate"
        candidates.append({"contour": dense_contour, "label": label, "area": hull_area})
        
    return candidates, darkening_mask, brightening_mask

# ==========================================
# 3. HÀM TẦNG 2: FIXED-RADIUS RANSAC
# ==========================================
def find_circle_centers(p1, p2, R):
    x1, y1 = p1; x2, y2 = p2
    dx = x2 - x1; dy = y2 - y1
    dist_sq = dx**2 + dy**2
    dist = math.sqrt(dist_sq)

    if dist > 2 * R or dist == 0: return []

    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2
    h_sq = R**2 - (dist / 2)**2
    if h_sq < 0: h_sq = 0
    h = math.sqrt(h_sq)

    rx = -dy * (h / dist)
    ry = dx * (h / dist)
    return [(mid_x + rx, mid_y + ry), (mid_x - rx, mid_y - ry)]

def process_layer_2_ransac(contour, expected_radius, max_iterations=100, inlier_thresh=3.0):
    points = [tuple(pt[0]) for pt in contour]
    if len(points) < 10: return []

    area = cv2.contourArea(contour)
    expected_area = math.pi * (expected_radius ** 2)
    n_est = max(1, int(round(area / expected_area)))
    n_est = min(n_est, 5) 
    
    found_circles = []
    remaining_set = set(points)

    for i in range(n_est):
        if len(remaining_set) < 10: break

        best_circle = None
        best_inliers = []
        current_remaining_list = list(remaining_set)

        for _ in range(max_iterations):
            sample = random.sample(current_remaining_list, 2)
            possible_centers = find_circle_centers(sample[0], sample[1], expected_radius)
            
            for cx, cy in possible_centers:
                inliers = []
                for pt in current_remaining_list:
                    dist = math.sqrt((pt[0] - cx)**2 + (pt[1] - cy)**2)
                    if abs(dist - expected_radius) <= inlier_thresh:
                        inliers.append(pt)

                if len(inliers) > len(best_inliers):
                    best_inliers = inliers
                    best_circle = (int(cx), int(cy), expected_radius)

        if best_circle is not None and len(best_inliers) > 15:
            found_circles.append(best_circle)
            inlier_set = set(best_inliers)
            remaining_set -= inlier_set

    return found_circles

# ==========================================
# 4. CẤU HÌNH NHẬN DIỆN ARUCO & HOMOGRAPHY
# ==========================================
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
parameters = aruco.DetectorParameters()
detector = aruco.ArucoDetector(aruco_dict, parameters)

target_sets = {"BIA_TRON": [0,1,2,3], "BIA_IPSC": [4,5,6,7], "BIA_NGUOI": [8,9,10,11]}
WIDTH, HEIGHT = 1240, 1754
MARGIN = 40
dst_points = np.array([[MARGIN, MARGIN], [WIDTH - MARGIN, MARGIN], [WIDTH - MARGIN, HEIGHT - MARGIN], [MARGIN, HEIGHT - MARGIN]], dtype=np.float32)

# ==========================================
# 5. VÒNG LẶP REAL-TIME
# ==========================================
cap = cv2.VideoCapture(VIDEO_PATH)
bg_grays = {}

print("🚀 Hệ thống Full 3 Tầng V3.1 (Giữ nguyên cấu trúc + Thêm Save Log) đã sẵn sàng...")
print("Nhấn 's' để lưu tọa độ vết đạn. Nhấn 'q' để thoát.")
frame_idx = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    frame_idx += 1

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
    cv2.imshow("0. Camera Chinh", cv2.resize(frame, (800, 450)))

    if ids is not None:
        marker_dict = {ids[i][0]: corners[i][0] for i in range(len(ids))}

        for target_name, id_set in target_sets.items():
            if all(mid in marker_dict for mid in id_set):
                
                TL, TR, BL, BR = id_set
                src_points = np.array([marker_dict[TL][0], marker_dict[TR][1], marker_dict[BR][2], marker_dict[BL][3]], dtype=np.float32)

                H, _ = cv2.findHomography(src_points, dst_points)
                warped = cv2.warpPerspective(frame, H, (WIDTH, HEIGHT))
                warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
                warped_gray = cv2.GaussianBlur(warped_gray, (7, 7), 0)

                if target_name not in bg_grays:
                    bg_grays[target_name] = warped_gray
                    print(f"🎯 Đã khóa nền cho: {target_name}.")
                    continue 

                # --- CHẠY TẦNG 1 (Đã truyền dst_points và MARGIN vào để mask tận gốc) ---
                candidates, dark_mask, bright_mask = process_layer_1_signed_diff(
                    bg_grays[target_name], warped_gray, dst_points, MARGIN
                )
                
                raw_circles = []
                
                for cand in candidates:
                    c = cand["contour"]
                    label = cand["label"]
                    
                    if label == "bullet_candidate":
                        cv2.drawContours(warped, [c], -1, (255, 255, 255), 1)
                        circles = process_layer_2_ransac(c, EXPECTED_RADIUS)
                        raw_circles.extend(circles)
                        
                    elif label == "shadow_candidate":
                        M = cv2.moments(c)
                        if M["m00"] != 0:
                            cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                            cv2.circle(warped, (cX, cY), 25, (0, 255, 255), 3)

                # --- CHẠY TẦNG 3 ---
                # Đã sửa match_dist = 15 tương ứng với đạn 25 để không nuốt đạn dính chùm
                all_display = temporal_tracking(
                    target_name, raw_circles, frame_idx,
                    confirm_frames=5, stale_frames=10, forget_frames=30, match_dist=15 
                )
                
                # Vẽ hiển thị
                for (cx, cy, r) in all_display:
                    cv2.circle(warped, (int(cx), int(cy)), int(r), (0, 255, 0), 2)     
                    cv2.circle(warped, (int(cx), int(cy)), 3, (0, 0, 255), -1)         
                    cv2.putText(warped, "Dan", (int(cx) - 15, int(cy) - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                cv2.imshow(f"TANG 1 - Vung Toi - {target_name}", cv2.resize(dark_mask, (400, 566)))
                cv2.imshow(f"Result (Full Pipeline V3): {target_name}", cv2.resize(warped, (400, 566)))

    # XỬ LÝ PHÍM BẤM
    key = cv2.waitKey(20) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        # --- LOGIC LƯU FILE LOG KHI NHẤN 'S' ---
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"--- BÁO CÁO LÚC {timestamp} (Khung hình: {frame_idx}) ---\n")
            for target, data in tracked_bullets.items():
                if data["confirmed"]:
                    coords = [(round(v["pos"][0], 1), round(v["pos"][1], 1)) for v in data["confirmed"].values()]
                    f.write(f"Bia: {target} | Tổng số đạn: {len(coords)} | Tọa độ tâm: {coords}\n")
            f.write("-" * 50 + "\n")
        print(f"✅ Đã ghi tọa độ vào file: {LOG_FILE_PATH}")

cap.release()
cv2.destroyAllWindows()