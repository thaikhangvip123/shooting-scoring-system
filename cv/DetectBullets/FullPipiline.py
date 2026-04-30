import cv2
import cv2.aruco as aruco
import numpy as np
import os
import io
import math
import random
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ==========================================
# 1. CẤU HÌNH ĐƯỜNG DẪN & THÔNG SỐ
# ==========================================
VIDEO_PATH = "D:/baitapxaml/HK252/DATN/DetectBullet/target.mp4"
LOG_FILE_PATH = "bullet_logs.txt"
EXPECTED_RADIUS = 25  

PATH_IPSC_POLY = "Main/shooting-scoring-system/cv/Scoring/IPSC/polygon.txt"
PATH_NGUOI_CONT = "Main/shooting-scoring-system/cv/Scoring/Nguoi/Nguoi_contours.txt"

TEMPLATE_PATHS = {
    "BIA_TRON": "Main/shooting-scoring-system/cv/DetectBullets/A4_Tron3.png",   
    "BIA_IPSC": "Main/shooting-scoring-system/cv/DetectBullets/A4_IPSC2.png",    
    "BIA_NGUOI": "Main/shooting-scoring-system/cv/DetectBullets/A4_Nguoi2.png"   
}

WIDTH, HEIGHT = 1240, 1754
SCALE_FACTOR = 2480 / WIDTH
MARGIN = 40
A4_WIDTH_MM = 210.0
PIXELS_PER_MM = WIDTH / A4_WIDTH_MM
CENTER_X_PX, CENTER_Y_PX = WIDTH / 2, HEIGHT / 2

dst_points = np.array([[MARGIN, MARGIN], [WIDTH - MARGIN, MARGIN], 
                       [WIDTH - MARGIN, HEIGHT - MARGIN], [MARGIN, HEIGHT - MARGIN]], dtype=np.float32)

# ==========================================
# 2. KHỞI TẠO DỮ LIỆU TÍNH ĐIỂM
# ==========================================
ipsc_polys = []
ipsc_scores = [10, 5, 3, 10, 7]
if os.path.exists(PATH_IPSC_POLY):
    with open(PATH_IPSC_POLY) as f:
        current_poly = []
        for line in f:
            line = line.strip()
            if line == "" or line.startswith("polygon"): continue
            if line == "END":
                ipsc_polys.append(np.array(current_poly, dtype=np.int32))  # fix bug 2: thêm dtype
                current_poly = []
                continue
            x, y = map(int, line.split(","))
            current_poly.append([x, y])
        if current_poly:  # fix bug 1: append polygon cuối nếu file không có dòng END
            ipsc_polys.append(np.array(current_poly, dtype=np.int32))

nguoi_cnts = []
nguoi_scores = [6, 7, 8, 9, 9, 10, 10]
if os.path.exists(PATH_NGUOI_CONT):
    with open(PATH_NGUOI_CONT) as f:
        current_contour = []
        for line in f:
            line = line.strip()
            if line == "": continue
            if line.startswith("contour"):
                if len(current_contour) > 0: nguoi_cnts.append(np.array(current_contour, dtype=np.int32))
                current_contour = []
                continue
            x, y = map(int, line.split(","))
            current_contour.append([x, y])
        if len(current_contour) > 0: nguoi_cnts.append(np.array(current_contour, dtype=np.int32))

tron_center = (1240, 1754)
tron_radii = [897.0, 802.5, 708.0, 613.5, 519.0, 424.5, 330.0, 235.5, 141.0, 51.0]

def calculate_score(target_name, point):
    if target_name == "BIA_TRON":
        dx, dy = point[0] - tron_center[0], point[1] - tron_center[1]
        dist = np.sqrt(dx*dx + dy*dy)
        for i, r in enumerate(reversed(tron_radii)):
            if dist <= r: return 10 - i
        return 0
    elif target_name == "BIA_IPSC":
        for i, poly in enumerate(ipsc_polys):
            if cv2.pointPolygonTest(poly, point, False) >= 0: return ipsc_scores[i]
        return 0
    elif target_name == "BIA_NGUOI":
        best_score = 0; smallest_area = float('inf')
        for i, cnt in enumerate(nguoi_cnts):
            if cv2.pointPolygonTest(cnt, point, False) >= 0:
                area = cv2.contourArea(cnt)
                if area < smallest_area:
                    smallest_area = area
                    best_score = nguoi_scores[i]
        return best_score
    return 0

# ==========================================
# 3. CORE LOGIC: TRACKING 3 TẦNG
# ==========================================
tracked_bullets = {
    "BIA_TRON":  {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_IPSC":  {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_NGUOI": {"candidates": {}, "confirmed": {}, "next_id": 0},
}

def temporal_tracking(target_name, raw_circles, frame_idx, confirm_frames=5, stale_frames=10, forget_frames=30, match_dist=15):
    state = tracked_bullets[target_name]
    alpha = 0.2; used_raw = set()

    for cid, cdata in list(state["confirmed"].items()):
        ox, oy = cdata["pos"]
        for j, (nx, ny, r) in enumerate(raw_circles):
            if j in used_raw: continue
            if math.sqrt((nx - ox)**2 + (ny - oy)**2) < match_dist:
                state["confirmed"][cid]["pos"] = (ox * (1 - alpha) + nx * alpha, oy * (1 - alpha) + ny * alpha)
                state["confirmed"][cid]["last_frame"] = frame_idx
                used_raw.add(j)
                break

    for j, (nx, ny, r) in enumerate(raw_circles):
        if j in used_raw: continue
        matched_id = None
        for cid, cdata in state["candidates"].items():
            ox, oy = cdata["pos"]
            if math.sqrt((nx - ox)**2 + (ny - oy)**2) < match_dist:
                matched_id = cid; break

        if matched_id is not None:
            state["candidates"][matched_id]["count"] += 1
            ox, oy = state["candidates"][matched_id]["pos"]
            state["candidates"][matched_id]["pos"] = (ox * 0.5 + nx * 0.5, oy * 0.5 + ny * 0.5)
            state["candidates"][matched_id]["last_frame"] = frame_idx
            if state["candidates"][matched_id]["count"] >= confirm_frames:
                state["confirmed"][matched_id] = {"pos": state["candidates"][matched_id]["pos"], "r": r, "last_frame": frame_idx}
                del state["candidates"][matched_id]
        else:
            cid = state["next_id"]; state["next_id"] += 1
            state["candidates"][cid] = {"pos": (nx, ny), "r": r, "count": 1, "last_frame": frame_idx}

    stale_cands = [k for k, v in state["candidates"].items() if frame_idx - v["last_frame"] > stale_frames]
    for k in stale_cands: del state["candidates"][k]
    stale_conf = [k for k, v in state["confirmed"].items() if frame_idx - v["last_frame"] > forget_frames]
    for k in stale_conf: del state["confirmed"][k]

    return [(v["pos"][0], v["pos"][1], v["r"]) for v in state["confirmed"].values()]

def process_layer_1_signed_diff(bg_gray, current_gray, dst_points, margin, dark_thresh=-35, bright_thresh=25):
    bg_int = bg_gray.astype(np.int16); curr_int = current_gray.astype(np.int16)
    signed_diff = curr_int - bg_int
    darkening_mask = np.where(signed_diff < dark_thresh, 255, 0).astype(np.uint8)
    brightening_mask = np.where(signed_diff > bright_thresh, 255, 0).astype(np.uint8)
    
    # Mask vừa vặn để che ArUco
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
        if cv2.contourArea(c) < 500: continue
        hull = cv2.convexHull(c)
        if cv2.contourArea(hull) == 0 or cv2.arcLength(hull, True) == 0: continue
        circularity = 4 * np.pi * (cv2.contourArea(hull) / (cv2.arcLength(hull, True)**2))
        if circularity < 0.85: continue # Tùy chỉnh theo nhu cầu
        
        blob_mask = np.zeros_like(darkening_mask)
        cv2.drawContours(blob_mask, [hull], -1, 255, -1)
        dense_cnts, _ = cv2.findContours(blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not dense_cnts: continue
        
        overlap = cv2.bitwise_and(blob_mask, brightening_mask)
        if cv2.countNonZero(blob_mask) > 0 and (cv2.countNonZero(overlap)/cv2.countNonZero(blob_mask)) >= 0.20: continue
        candidates.append({"contour": dense_cnts[0], "label": "bullet_candidate"})
        
    return candidates, darkening_mask

def find_circle_centers(p1, p2, R):
    dx = p2[0] - p1[0]; dy = p2[1] - p1[1]; dist = math.sqrt(dx**2 + dy**2)
    if dist > 2 * R or dist == 0: return []
    mid_x, mid_y = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    h = math.sqrt(max(0, R**2 - (dist / 2)**2))
    rx, ry = -dy * (h / dist), dx * (h / dist)
    return [(mid_x + rx, mid_y + ry), (mid_x - rx, mid_y - ry)]

def process_layer_2_ransac(contour, expected_radius):
    points = [tuple(pt[0]) for pt in contour]
    if len(points) < 10: return []
    n_est = min(5, max(1, int(round(cv2.contourArea(contour) / (math.pi * expected_radius**2)))))
    found_circles = []; remaining_set = set(points)
    
    for _ in range(n_est):
        if len(remaining_set) < 10: break
        best_circle = None; best_inliers = []; current_list = list(remaining_set)
        for _ in range(100):
            sample = random.sample(current_list, 2)
            for cx, cy in find_circle_centers(sample[0], sample[1], expected_radius):
                inliers = [pt for pt in current_list if abs(math.sqrt((pt[0]-cx)**2 + (pt[1]-cy)**2) - expected_radius) <= 3.0]
                if len(inliers) > len(best_inliers):
                    best_inliers = inliers; best_circle = (int(cx), int(cy), expected_radius)
        if best_circle and len(best_inliers) > 15:
            found_circles.append(best_circle)
            remaining_set -= set(best_inliers)
            
    return found_circles

# ==========================================
# 4. HÀM XUẤT BÁO CÁO HEATMAP (VISUAL REPORT)
# ==========================================
def get_shots_mm(target_name):
    """ Quy đổi tọa độ từ Bộ nhớ Tầng 3 sang hệ mm để vẽ biểu đồ """
    shots_mm = []
    for data in tracked_bullets[target_name]["confirmed"].values():
        cX, cY = data["pos"]
        x_mm = (cX - CENTER_X_PX) / PIXELS_PER_MM
        y_mm = -(cY - CENTER_Y_PX) / PIXELS_PER_MM
        shots_mm.append([x_mm, y_mm])
    return np.array(shots_mm)

def generate_visual_report(target_name):
    shots_mm = get_shots_mm(target_name)
    if len(shots_mm) < 2:
        print(f"⚠️ {target_name}: Chưa đủ số lượng đạn để phân tích (Cần ít nhất 2 viên)!")
        return

    print(f"\n📊 Đang tạo báo cáo phân tích cho {target_name}...")
    distances = np.linalg.norm(shots_mm, axis=1)
    mre_mm = np.mean(distances)
    r50_mm = np.median(distances)

    best_k = 1; best_score = -1; max_k = min(5, len(shots_mm) - 1)
    if len(shots_mm) >= 3:
        for k in range(2, max_k + 1):
            kmeans_temp = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels_temp = kmeans_temp.fit_predict(shots_mm)
            score = silhouette_score(shots_mm, labels_temp)
            if score > best_score: best_score = score; best_k = k
    if best_score < 0.40: best_k = 1

    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    shot_labels = kmeans.fit_predict(shots_mm)
    cluster_centers = kmeans.cluster_centers_

    fig, ax = plt.subplots(figsize=(8, 11)) 
    ax.set_title(f"BÁO CÁO ĐẠN ĐẠO - {target_name}\nMRE: {mre_mm:.1f}mm | CEP(R50): {r50_mm:.1f}mm | {best_k} Cụm", fontsize=14, fontweight='bold')

    if os.path.exists(TEMPLATE_PATHS.get(target_name, "")):
        img_bg = cv2.imread(TEMPLATE_PATHS[target_name])
        img_bg = cv2.cvtColor(img_bg, cv2.COLOR_BGR2RGB)
        cart_xmin, cart_xmax = -(CENTER_X_PX / PIXELS_PER_MM), (WIDTH - CENTER_X_PX) / PIXELS_PER_MM
        cart_ymin, cart_ymax = -(HEIGHT - CENTER_Y_PX) / PIXELS_PER_MM, CENTER_Y_PX / PIXELS_PER_MM
        ax.imshow(img_bg, extent=[cart_xmin, cart_xmax, cart_ymin, cart_ymax], alpha=0.8)

    sns.kdeplot(x=shots_mm[:, 0], y=shots_mm[:, 1], fill=True, cmap="Reds", alpha=0.4, thresh=0.05, ax=ax)
    colors = ['#00FFFF', '#FFFF00', '#FF00FF', '#00FF00', '#FFA500']
    for i in range(best_k):
        c_shots = shots_mm[shot_labels == i]
        ax.scatter(c_shots[:, 0], c_shots[:, 1], color=colors[i%5], edgecolor='black', s=80)
        ax.scatter(cluster_centers[i, 0], cluster_centers[i, 1], color=colors[i%5], marker='X', s=200, edgecolor='black')

    ax.scatter(0, 0, color='red', marker='+', s=200, label='Tâm bia chuẩn')
    ax.add_patch(plt.Circle((0, 0), r50_mm, color='purple', fill=False, linestyle='--', linewidth=2))

    buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight'); buf.seek(0); plt.close()
    img_report = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), 1)
    cv2.imshow(f"Report: {target_name}", img_report)

# ==========================================
# 5. VÒNG LẶP CHÍNH (REAL-TIME SYSTEM)
# ==========================================
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
target_sets = {"BIA_TRON": [0,1,2,3], "BIA_IPSC": [4,5,6,7], "BIA_NGUOI": [8,9,10,11]}

cap = cv2.VideoCapture(VIDEO_PATH)
bg_grays = {}; frame_idx = 0

print("🚀 HỆ THỐNG FULL MODULE SẴN SÀNG!")
print("Phím chức năng: [a] Báo cáo Tròn | [b] Báo cáo IPSC | [c] Báo cáo Người | [s] Lưu Log | [q] Thoát")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    frame_idx += 1

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
    cv2.imshow("0. Camera Chinh (Main View)", cv2.resize(frame, (800, 450)))

    if ids is not None:
        marker_dict = {ids[i][0]: corners[i][0] for i in range(len(ids))}

        for target_name, id_set in target_sets.items():
            if all(mid in marker_dict for mid in id_set):
                
                TL, TR, BL, BR = id_set
                src_pts = np.array([marker_dict[TL][0], marker_dict[TR][1], marker_dict[BR][2], marker_dict[BL][3]], dtype=np.float32)

                H, _ = cv2.findHomography(src_pts, dst_points)
                warped = cv2.warpPerspective(frame, H, (WIDTH, HEIGHT))
                warped_gray = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (7, 7), 0)

                if target_name not in bg_grays:
                    bg_grays[target_name] = warped_gray
                    print(f"🎯 Đã khóa nền cho: {target_name}")
                    continue 

                # --- 1. DETECT ĐẠN (3 TẦNG) ---
                candidates, dark_mask = process_layer_1_signed_diff(bg_grays[target_name], warped_gray, dst_points, MARGIN)
                
                raw_circles = []
                for cand in candidates:
                    cv2.drawContours(warped, [cand["contour"]], -1, (255, 255, 255), 1)
                    raw_circles.extend(process_layer_2_ransac(cand["contour"], EXPECTED_RADIUS))

                all_display = temporal_tracking(target_name, raw_circles, frame_idx)
                
                # --- 2. TÍNH ĐIỂM & VẼ HIỂN THỊ ---
                total_score = 0
                for (cx, cy, r) in all_display:
                    px = (int(cx), int(cy))
                    virtual_point = (int(cx * SCALE_FACTOR), int(cy * SCALE_FACTOR))
                    score = calculate_score(target_name, virtual_point)
                    total_score += score
                    
                    # Vẽ vết đạn (Vòng xanh lá, tâm đỏ)
                    cv2.circle(warped, px, int(r), (0, 255, 0), 2)
                    cv2.circle(warped, px, 3, (0, 0, 255), -1)
                    # Ghi điểm trực tiếp lên vết đạn
                    cv2.putText(warped, str(score), (px[0] + int(r) + 5, px[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)

                cv2.putText(warped, f"Hits: {len(all_display)} | Total: {total_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                cv2.imshow(f"Scoring: {target_name}", cv2.resize(warped, (400, 566)))

    # --- BẮT SỰ KIỆN BÀN PHÍM ---
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): break
    elif key == ord('a'): generate_visual_report("BIA_TRON")
    elif key == ord('b'): generate_visual_report("BIA_IPSC")
    elif key == ord('c'): generate_visual_report("BIA_NGUOI")
    elif key == ord('s'):
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"--- BÁO CÁO LÚC {timestamp} (Frame: {frame_idx}) ---\n")
            for target, data in tracked_bullets.items():
                if data["confirmed"]:
                    coords = [(round(v["pos"][0], 1), round(v["pos"][1], 1)) for v in data["confirmed"].values()]
                    total_pts = sum([calculate_score(target, (int(x*SCALE_FACTOR), int(y*SCALE_FACTOR))) for x,y in coords])
                    f.write(f"Bia: {target} | Hits: {len(coords)} | Score: {total_pts} | Tâm: {coords}\n")
            f.write("-" * 50 + "\n")
        print(f"✅ Đã lưu log vết đạn + điểm số vào {LOG_FILE_PATH}")

cap.release()
cv2.destroyAllWindows()