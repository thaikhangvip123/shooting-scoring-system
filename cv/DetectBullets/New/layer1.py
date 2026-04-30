import cv2
import numpy as np
from config import *

def process_layer_1(bg_gray, current_gray, dst_points):
    # 1. Trừ nền mượt mà
    dark_diff = cv2.subtract(bg_gray, current_gray)
    _, darkening_mask = cv2.threshold(dark_diff, 35, 255, cv2.THRESH_BINARY)
    
    # 2. Xóa các nhiễu ở ngoài viền giấy
    mask_radius = 350
    for pt in dst_points:
        cv2.circle(darkening_mask, (int(pt[0]), int(pt[1])), mask_radius, 0, -1)
    
    # 3. Morph để tẩy sạch hạt nhiễu
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_CLOSE, kernel_close)
    
    # 4. Tìm Contour và chỉ lọc bằng Độ tròn (Circularity)
    cnts, _ = cv2.findContours(darkening_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    
    for c in cnts:
        if cv2.contourArea(c) < 300: continue
        
        hull = cv2.convexHull(c)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)
        if perimeter == 0: continue
            
        circularity = 4 * np.pi * (area / (perimeter ** 2))
        
        # BỎ HOÀN TOÀN OVERLAP, CHỈ DÙNG ĐỘ TRÒN ĐỂ BẮT VẾT RÁCH
        if circularity >= CIRCULARITY_THRESH:
            candidates.append({"contour": c, "label": "bullet"})
            
    return candidates, darkening_mask