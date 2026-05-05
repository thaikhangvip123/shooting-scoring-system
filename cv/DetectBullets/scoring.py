import os
import cv2
import numpy as np
from config import *

ipsc_polys = []
ipsc_scores = [10, 5, 3, 10, 7]
if os.path.exists(PATH_IPSC_POLY):
    with open(PATH_IPSC_POLY) as f:
        current_poly = []
        for line in f:
            line = line.strip()
            if line == "" or line.startswith("polygon"): continue
            if line == "END":
                ipsc_polys.append(np.array(current_poly, dtype=np.int32))
                current_poly = []
                continue
            x, y = map(int, line.split(","))
            current_poly.append([x, y])
        if current_poly:
            ipsc_polys.append(np.array(current_poly, dtype=np.int32))
else:
    print(f"⚠️ Không tìm thấy file {PATH_IPSC_POLY}")

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

# ==========================================
# CẤU HÌNH BIA TRÒN
# ==========================================
# Sửa đổi duy nhất ở dòng này: Trả tâm bia về tọa độ Scale
tron_center = (1240, 1754) 
tron_radii = [897.0, 802.5, 708.0, 613.5, 519.0, 424.5, 330.0, 235.5, 141.0, 51.0]

# ==========================================
# HÀM CHẤM ĐIỂM CHÍNH
# ==========================================
def calculate_score(target_name, point):
    if target_name == "BIA_TRON":
        dx, dy = point[0] - tron_center[0], point[1] - tron_center[1]
        dist = np.sqrt(dx*dx + dy*dy)
        
        # In log ra để debug (bạn có thể xóa dòng print này sau khi test ok)
        # print(f"Distance to center: {dist}") 
        
        for i, r in enumerate(reversed(tron_radii)):
            if dist <= r: return 10 - i
        return 0
        
    # ... (Các phần IPSC và BIA_NGUOI giữ nguyên)
    elif target_name == "BIA_IPSC":
        if not ipsc_polys: return 0
        for i, poly in enumerate(ipsc_polys):
            if cv2.pointPolygonTest(poly, point, False) >= 0: return ipsc_scores[i]
        return 0
    elif target_name == "BIA_NGUOI":
        if not nguoi_cnts: return 0
        best_score = 0; smallest_area = float('inf')
        for i, cnt in enumerate(nguoi_cnts):
            if cv2.pointPolygonTest(cnt, point, False) >= 0:
                area = cv2.contourArea(cnt)
                if area < smallest_area:
                    smallest_area = area; best_score = nguoi_scores[i]
        return best_score
    return 0