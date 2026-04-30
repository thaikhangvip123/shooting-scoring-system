import cv2
import numpy as np
import math
import random
from numba import njit
from config import *

@njit(fastmath=True, nogil=True)
def find_circle_centers_numba(p1_x, p1_y, p2_x, p2_y, R):
    dx, dy = p2_x - p1_x, p2_y - p1_y
    dist = math.sqrt(dx**2 + dy**2)
    if dist > 2 * R or dist == 0: return np.zeros((0, 2), dtype=np.float32)
    mid_x, mid_y = (p1_x + p2_x) / 2.0, (p1_y + p2_y) / 2.0
    h_sq = R**2 - (dist / 2.0)**2
    if h_sq < 0: h_sq = 0.0
    h = math.sqrt(h_sq)
    rx, ry = -dy * (h / dist), dx * (h / dist)
    res = np.empty((2, 2), dtype=np.float32)
    res[0, 0], res[0, 1] = mid_x + rx, mid_y + ry
    res[1, 0], res[1, 1] = mid_x - rx, mid_y - ry
    return res

def process_layer_2(contour, expected_radius, mask_shape):
    area = cv2.contourArea(contour)
    expected_area = math.pi * expected_radius**2
    ratio = area / expected_area
    
    # 1. ƯỚC TÍNH SỐ LƯỢNG ĐẠN DỰA VÀO TỶ LỆ DIỆN TÍCH
    if ratio < 1.3:
        n_est = 1
    elif ratio < 1.75:   
        n_est = 2
    elif ratio < 2.3:    
        n_est = 3
    elif ratio < 2.8:    
        n_est = 4
    else:
        n_est = 5
        
    raw_found_circles = []

    # 2. FAST-PATH: HOUGH CIRCLES
    blob_mask = np.zeros(mask_shape, dtype=np.uint8)
    cv2.drawContours(blob_mask, [contour], -1, 255, -1)
    
    circles = cv2.HoughCircles(
        blob_mask, cv2.HOUGH_GRADIENT, dp=1.2, 
        minDist=expected_radius*1.0, 
        param1=50, param2=10, 
        minRadius=int(expected_radius*0.6), maxRadius=int(expected_radius*1.4)
    )
    
    if circles is not None:
        circles = circles[0]
        for i in range(min(len(circles), n_est)):
            c = circles[i]
            raw_found_circles.append((int(c[0]), int(c[1]), expected_radius))

    # 3. RANSAC: TÌM KIẾM CÁC TÂM BỊ THIẾU
    if len(raw_found_circles) < n_est:
        points = np.array([pt[0] for pt in contour], dtype=np.float32)
        num_points = len(points)
        
        if num_points >= 10: 
            available = np.ones(num_points, dtype=np.bool_)
            
            # Khóa các điểm ảnh đã thuộc về các tâm Hough tìm được
            for cx, cy, r in raw_found_circles:
                dists = np.sqrt((points[:, 0] - cx)**2 + (points[:, 1] - cy)**2)
                available = available & ~(np.abs(dists - expected_radius) <= 5.0)

            remaining_est = n_est - len(raw_found_circles)
            
            for _ in range(remaining_est):
                if np.sum(available) < 10: break
                
                best_circle = None; best_inliers_count = 0; best_inliers_mask = None
                avail_indices = np.where(available)[0]
                
                for _ in range(50):
                    if len(avail_indices) < 2: break
                    idx1, idx2 = random.sample(list(avail_indices), 2)
                    centers = find_circle_centers_numba(points[idx1][0], points[idx1][1], points[idx2][0], points[idx2][1], expected_radius)
                    
                    for cx, cy in centers:
                        dists = np.sqrt((points[:, 0] - cx)**2 + (points[:, 1] - cy)**2)
                        inliers_mask = available & (np.abs(dists - expected_radius) <= 3.0)
                        inliers_count = np.sum(inliers_mask)
                        
                        if inliers_count > best_inliers_count:
                            best_inliers_count = inliers_count
                            best_circle = (int(cx), int(cy), expected_radius)
                            best_inliers_mask = inliers_mask

                if best_circle and best_inliers_count > 6: 
                    raw_found_circles.append(best_circle)
                    available = available & (~best_inliers_mask)
                else:
                    break 

    # ---------------------------------------------------------
    # 4. BỘ LỌC NMS: LOẠI BỎ CÁC TÂM SINH RA DO NHIỄU/PHÌNH TO
    # ---------------------------------------------------------
    filtered_circles = []
    
    # Quy định: 2 tâm cách nhau dưới 40% bán kính đạn thì bị coi là 1 viên (lọc bỏ viên bị trùng)
    MIN_DIST = expected_radius * 0.7 

    for new_circle in raw_found_circles:
        nx, ny, nr = new_circle
        is_too_close = False
        
        for kept_circle in filtered_circles:
            kx, ky, kr = kept_circle
            dist = math.sqrt((nx - kx)**2 + (ny - ky)**2)
            
            if dist < MIN_DIST:
                is_too_close = True
                break 
                
        if not is_too_close:
            filtered_circles.append(new_circle)

    return filtered_circles