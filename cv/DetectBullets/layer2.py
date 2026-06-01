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

def circle_has_blob_support(circle, contour, expected_radius, mask_shape):
    cx, cy, _ = circle
    outside_tol = expected_radius * CIRCLE_CENTER_OUTSIDE_TOLERANCE_FACTOR
    signed_dist = cv2.pointPolygonTest(contour, (float(cx), float(cy)), True)

    if signed_dist < -outside_tol:
        return False

    x, y, w, h = cv2.boundingRect(contour)
    pad = int(expected_radius * 1.5)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(mask_shape[1], x + w + pad)
    y2 = min(mask_shape[0], y + h + pad)

    roi_w = x2 - x1
    roi_h = y2 - y1
    if roi_w <= 0 or roi_h <= 0:
        return False

    contour_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    shifted_contour = contour - np.array([[[x1, y1]]])
    cv2.drawContours(contour_mask, [shifted_contour], -1, 255, -1)

    ring_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    cv2.circle(
        ring_mask,
        (int(cx - x1), int(cy - y1)),
        int(expected_radius),
        255,
        2
    )

    ring_area = cv2.countNonZero(ring_mask)
    if ring_area == 0:
        return False

    support_area = cv2.countNonZero(cv2.bitwise_and(contour_mask, ring_mask))
    return support_area / ring_area >= CIRCLE_MIN_MASK_SUPPORT_RATIO

def refine_circle_centers_from_gray(circles, gray_image, expected_radius, mask_shape):
    if gray_image is None:
        return circles

    refined = []
    search_radius = max(4, int(expected_radius * 1.45))
    min_area = max(4, int(math.pi * expected_radius**2 * 0.04))
    max_area = max(min_area + 1, int(math.pi * expected_radius**2 * 1.25))

    for cx, cy, r in circles:
        x1 = max(0, int(cx - search_radius))
        y1 = max(0, int(cy - search_radius))
        x2 = min(mask_shape[1], int(cx + search_radius + 1))
        y2 = min(mask_shape[0], int(cy + search_radius + 1))

        if x2 <= x1 or y2 <= y1:
            refined.append((cx, cy, r))
            continue

        roi = gray_image[y1:y2, x1:x2]
        if roi.size == 0:
            refined.append((cx, cy, r))
            continue

        blurred = cv2.GaussianBlur(roi, (3, 3), 0)
        _, dark = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        local_cx = cx - x1
        local_cy = cy - y1
        search_mask = np.zeros_like(dark)
        cv2.circle(search_mask, (int(local_cx), int(local_cy)), search_radius, 255, -1)
        dark = cv2.bitwise_and(dark, search_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dark, 8)
        best_idx = -1
        best_score = -1.0

        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            if area < min_area or area > max_area:
                continue

            bx = stats[idx, cv2.CC_STAT_LEFT]
            by = stats[idx, cv2.CC_STAT_TOP]
            bw = stats[idx, cv2.CC_STAT_WIDTH]
            bh = stats[idx, cv2.CC_STAT_HEIGHT]
            fill_ratio = area / max(1, bw * bh)
            if fill_ratio < 0.18:
                continue

            comp_cx, comp_cy = centroids[idx]
            dist = math.sqrt((comp_cx - local_cx) ** 2 + (comp_cy - local_cy) ** 2)
            score = area - dist * 2.0

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0:
            comp_cx, comp_cy = centroids[best_idx]
            refined.append((int(x1 + comp_cx), int(y1 + comp_cy), r))
        else:
            refined.append((cx, cy, r))

    return refined

def refine_circle_centers_by_dark_core(circles, gray_image, expected_radius, mask_shape):
    if gray_image is None:
        return circles

    refined = []
    search_radius = max(5, int(expected_radius * 1.25))
    max_shift = expected_radius * 1.05

    for cx, cy, r in circles:
        x1 = max(0, int(cx - search_radius))
        y1 = max(0, int(cy - search_radius))
        x2 = min(mask_shape[1], int(cx + search_radius + 1))
        y2 = min(mask_shape[0], int(cy + search_radius + 1))

        if x2 <= x1 or y2 <= y1:
            refined.append((cx, cy, r))
            continue

        roi = gray_image[y1:y2, x1:x2]
        if roi.size == 0:
            refined.append((cx, cy, r))
            continue

        local_cx = float(cx - x1)
        local_cy = float(cy - y1)
        yy, xx = np.indices(roi.shape)
        dist = np.sqrt((xx - local_cx) ** 2 + (yy - local_cy) ** 2)
        search_mask = dist <= search_radius

        if not np.any(search_mask):
            refined.append((cx, cy, r))
            continue

        local_values = roi[search_mask]
        dark_limit = np.percentile(local_values, 35)
        dark_mask = search_mask & (roi <= dark_limit)

        if np.count_nonzero(dark_mask) < 3:
            refined.append((cx, cy, r))
            continue

        dark_uint8 = np.zeros_like(roi, dtype=np.uint8)
        dark_uint8[dark_mask] = 255

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dark_uint8 = cv2.morphologyEx(dark_uint8, cv2.MORPH_OPEN, kernel)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dark_uint8, 8)
        best_idx = -1
        best_score = -1e9

        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            if area < 3:
                continue

            comp_cx, comp_cy = centroids[idx]
            dist_to_circle = math.sqrt((comp_cx - local_cx) ** 2 + (comp_cy - local_cy) ** 2)
            score = -dist_to_circle + min(area, 20) * 0.08

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx < 0:
            refined.append((cx, cy, r))
            continue

        comp_cx, comp_cy = centroids[best_idx]
        comp_mask = labels == best_idx
        weights = (255 - roi[comp_mask]).astype(np.float32)
        if float(np.sum(weights)) <= 0:
            core_x, core_y = float(comp_cx), float(comp_cy)
        else:
            core_x = float(np.sum(xx[comp_mask] * weights) / np.sum(weights))
            core_y = float(np.sum(yy[comp_mask] * weights) / np.sum(weights))

        shift = math.sqrt((core_x - local_cx) ** 2 + (core_y - local_cy) ** 2)
        if shift > max_shift:
            refined.append((cx, cy, r))
            continue

        refined.append((int(x1 + core_x), int(y1 + core_y), r))

    return refined

def contour_center(contour):
    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        return (
            moments["m10"] / moments["m00"],
            moments["m01"] / moments["m00"]
        )

    x, y, w, h = cv2.boundingRect(contour)
    return (x + w / 2.0, y + h / 2.0)

def constrain_single_circle_to_candidate_center(circles, contour, expected_radius):
    if len(circles) != 1:
        return circles

    prior_x, prior_y = contour_center(contour)
    cx, cy, r = circles[0]
    dist = math.sqrt((cx - prior_x) ** 2 + (cy - prior_y) ** 2)

    if dist > expected_radius * 0.45:
        return [(int(prior_x), int(prior_y), r)]

    blend = 0.65
    return [(
        int(cx * (1.0 - blend) + prior_x * blend),
        int(cy * (1.0 - blend) + prior_y * blend),
        r
    )]

def process_layer_2(contour, expected_radius, mask_shape, gray_image=None):
    area = cv2.contourArea(contour)
    expected_area = math.pi * expected_radius**2
    ratio = area / expected_area

    # 1. ƯỚC TÍNH SỐ LƯỢNG ĐẠN DỰA VÀO TỶ LỆ DIỆN TÍCH
    if ratio < 1.45:
        n_est = 1
    elif ratio < 2.2:
        n_est = 2
    elif ratio < 3.3:
        n_est = 3
    elif ratio < 4.2:
        n_est = 4
    else:
        n_est = 5

    raw_found_circles = []

    # 2. FAST-PATH: HOUGH CIRCLES
    # Run Hough only inside a small ROI around the blob. Running it on the full
    # warped target for every contour is one of the biggest FPS costs.
    x, y, w, h = cv2.boundingRect(contour)
    pad = int(expected_radius * 2.0)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(mask_shape[1], x + w + pad)
    y2 = min(mask_shape[0], y + h + pad)

    roi_w = x2 - x1
    roi_h = y2 - y1
    if roi_w <= 0 or roi_h <= 0:
        return []

    blob_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    shifted_contour = contour - np.array([[[x1, y1]]])
    cv2.drawContours(blob_mask, [shifted_contour], -1, 255, -1)

    circles = cv2.HoughCircles(
    blob_mask,
    cv2.HOUGH_GRADIENT,
    dp=HOUGH_DP,
    minDist=expected_radius * HOUGH_MIN_DIST_FACTOR,
    param1=HOUGH_PARAM1,
    param2=HOUGH_PARAM2,
    minRadius=int(expected_radius * HOUGH_MIN_RADIUS_FACTOR),
    maxRadius=int(expected_radius * HOUGH_MAX_RADIUS_FACTOR)
)

    if circles is not None:
        circles = circles[0]

        for i in range(min(len(circles), n_est)):
            c = circles[i]
            raw_found_circles.append(
                (int(c[0] + x1), int(c[1] + y1), expected_radius)
            )

    # 3. RANSAC: TÌM KIẾM CÁC TÂM BỊ THIẾU
    if len(raw_found_circles) < n_est:
        points = np.array([pt[0] for pt in contour], dtype=np.float32)
        num_points = len(points)

        if num_points >= RANSAC_MIN_CONTOUR_POINTS:
            available = np.ones(num_points, dtype=np.bool_)

            # Loại bỏ các điểm contour đã thuộc về circle mà Hough tìm được
            for cx, cy, r in raw_found_circles:
                dists = np.sqrt(
                    (points[:, 0] - cx) ** 2 +
                    (points[:, 1] - cy) ** 2
                )

                used_by_hough = np.abs(dists - expected_radius) <= RANSAC_HOUGH_REMOVE_THRESH
                available = available & (~used_by_hough)

            remaining_est = n_est - len(raw_found_circles)

            for _ in range(remaining_est):
                if np.sum(available) < RANSAC_MIN_AVAILABLE_POINTS:
                    break

                best_circle = None
                best_inliers_count = 0
                best_inliers_mask = None

                avail_indices = np.where(available)[0]

                for _ in range(RANSAC_ITERATIONS):
                    if len(avail_indices) < 2:
                        break

                    idx1, idx2 = random.sample(list(avail_indices), 2)

                    centers = find_circle_centers_numba(
                        points[idx1][0],
                        points[idx1][1],
                        points[idx2][0],
                        points[idx2][1],
                        expected_radius
                    )

                    for cx, cy in centers:
                        dists = np.sqrt(
                            (points[:, 0] - cx) ** 2 +
                            (points[:, 1] - cy) ** 2
                        )

                        inliers_mask = available & (
                            np.abs(dists - expected_radius) <= RANSAC_INLIER_THRESH
                        )

                        inliers_count = np.sum(inliers_mask)

                        if inliers_count > best_inliers_count:
                            best_inliers_count = inliers_count
                            best_circle = (int(cx), int(cy), expected_radius)
                            best_inliers_mask = inliers_mask

                if best_circle is not None and best_inliers_count >= RANSAC_MIN_INLIERS:
                    raw_found_circles.append(best_circle)
                    available = available & (~best_inliers_mask)
                else:
                    break

    # 4. NMS: LOẠI BỎ CÁC TÂM QUÁ GẦN NHAU
    if n_est == 1:
        raw_found_circles = refine_circle_centers_from_gray(
            raw_found_circles,
            gray_image,
            expected_radius,
            mask_shape
        )
        raw_found_circles = constrain_single_circle_to_candidate_center(
            raw_found_circles,
            contour,
            expected_radius
        )
    else:
        raw_found_circles = refine_circle_centers_by_dark_core(
            raw_found_circles,
            gray_image,
            expected_radius,
            mask_shape
        )

    filtered_circles = []

    min_dist = expected_radius * NMS_MIN_DIST_FACTOR

    for new_circle in raw_found_circles:
        nx, ny, nr = new_circle
        is_too_close = False

        for kept_circle in filtered_circles:
            kx, ky, kr = kept_circle
            dist = math.sqrt((nx - kx) ** 2 + (ny - ky) ** 2)

            if dist < min_dist:
                is_too_close = True
                break

        if not is_too_close and circle_has_blob_support(
            new_circle,
            contour,
            expected_radius,
            mask_shape
        ):
            filtered_circles.append(new_circle)

    return filtered_circles
