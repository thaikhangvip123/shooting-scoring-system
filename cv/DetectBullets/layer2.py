import math
import random

import cv2
import numpy as np
from numba import njit

from config import *


@njit(fastmath=True, nogil=True)
def find_circle_centers_numba(p1_x, p1_y, p2_x, p2_y, R):
    dx, dy = p2_x - p1_x, p2_y - p1_y
    dist = math.sqrt(dx ** 2 + dy ** 2)
    if dist > 2 * R or dist == 0:
        return np.zeros((0, 2), dtype=np.float32)

    mid_x, mid_y = (p1_x + p2_x) / 2.0, (p1_y + p2_y) / 2.0
    h_sq = R ** 2 - (dist / 2.0) ** 2
    if h_sq < 0:
        h_sq = 0.0

    h = math.sqrt(h_sq)
    rx, ry = -dy * (h / dist), dx * (h / dist)
    res = np.empty((2, 2), dtype=np.float32)
    res[0, 0], res[0, 1] = mid_x + rx, mid_y + ry
    res[1, 0], res[1, 1] = mid_x - rx, mid_y - ry
    return res


def process_layer_2(contour, expected_radius, mask_shape):
    area = cv2.contourArea(contour)
    expected_area = math.pi * expected_radius ** 2
    ratio = area / expected_area

    # Estimate bullet count from contour area.
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

    # 1. Fast path: Hough circles.
    blob_mask = np.zeros(mask_shape, dtype=np.uint8)
    cv2.drawContours(blob_mask, [contour], -1, 255, -1)

    circles = cv2.HoughCircles(
        blob_mask,
        cv2.HOUGH_GRADIENT,
        dp=HOUGH_DP,
        minDist=expected_radius * HOUGH_MIN_DIST_FACTOR,
        param1=HOUGH_PARAM1,
        param2=HOUGH_PARAM2,
        minRadius=int(expected_radius * HOUGH_MIN_RADIUS_FACTOR),
        maxRadius=int(expected_radius * HOUGH_MAX_RADIUS_FACTOR),
    )

    if circles is not None:
        circles = circles[0]
        for i in range(min(len(circles), n_est)):
            c = circles[i]
            raw_found_circles.append((int(c[0]), int(c[1]), expected_radius))

    # 2. RANSAC: recover missing centers when bullets overlap.
    if len(raw_found_circles) < n_est:
        points = np.array([pt[0] for pt in contour], dtype=np.float32)
        num_points = len(points)

        if num_points >= RANSAC_MIN_CONTOUR_POINTS:
            available = np.ones(num_points, dtype=np.bool_)

            for cx, cy, _ in raw_found_circles:
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
                        expected_radius,
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

    # 3. NMS: remove duplicate centers that are too close.
    filtered_circles = []
    min_dist = expected_radius * NMS_MIN_DIST_FACTOR

    for new_circle in raw_found_circles:
        nx, ny, _ = new_circle
        is_too_close = False

        for kept_circle in filtered_circles:
            kx, ky, _ = kept_circle
            dist = math.sqrt((nx - kx) ** 2 + (ny - ky) ** 2)

            if dist < min_dist:
                is_too_close = True
                break

        if not is_too_close:
            filtered_circles.append(new_circle)

    return filtered_circles
