import cv2
import numpy as np
from config import *


def create_mog2_subtractor():
    return cv2.createBackgroundSubtractorMOG2(
        history=MOG2_HISTORY,
        varThreshold=MOG2_VAR_THRESHOLD,
        detectShadows=MOG2_DETECT_SHADOWS,
    )


def _remove_marker_regions(mask, dst_points):
    for pt in dst_points:
        cv2.circle(mask, (int(pt[0]), int(pt[1])), LAYER1_MARKER_MASK_RADIUS, 0, -1)


def _contours_to_candidates(mask, min_area, max_area=None):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for c in cnts:
        raw_area = cv2.contourArea(c)
        if raw_area < min_area:
            continue
        if max_area is not None and raw_area > max_area:
            continue

        hull = cv2.convexHull(c)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * (area / (perimeter ** 2))

        if circularity >= CIRCULARITY_THRESH:
            candidates.append({"contour": c, "label": "bullet"})

    return candidates


def _expand_candidates_to_expected_radius(candidates, mask_shape):
    expanded = []
    radius = max(3, int(EXPECTED_RADIUS * MOG2_EXPAND_RADIUS_FACTOR))

    for cand in candidates:
        contour = cand["contour"]
        moments = cv2.moments(contour)

        if moments["m00"] != 0:
            cx = int(moments["m10"] / moments["m00"])
            cy = int(moments["m01"] / moments["m00"])
        else:
            x, y, w, h = cv2.boundingRect(contour)
            cx = x + w // 2
            cy = y + h // 2

        contour_mask = np.zeros(mask_shape, dtype=np.uint8)
        cv2.circle(contour_mask, (cx, cy), radius, 255, -1)
        cnts, _ = cv2.findContours(
            contour_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if cnts:
            expanded.append({"contour": cnts[0], "label": cand["label"]})

    return expanded


def process_layer_1(bg_gray, current_gray, dst_points):
    dark_diff = cv2.subtract(bg_gray, current_gray)
    _, darkening_mask = cv2.threshold(dark_diff, 20, 255, cv2.THRESH_BINARY)

    _remove_marker_regions(darkening_mask, dst_points)

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, LAYER1_OPEN_KERNEL)
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, LAYER1_CLOSE_KERNEL)
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_CLOSE, kernel_close)

    candidates = _contours_to_candidates(darkening_mask, min_area=LAYER1_MIN_AREA)

    return candidates, darkening_mask


def process_layer_1_mog2(subtractor, current_gray, dst_points, frame_count):
    learning_rate = -1 if frame_count <= MOG2_WARMUP_FRAMES else 0
    fg_mask = subtractor.apply(current_gray, learningRate=learning_rate)

    _, binary = cv2.threshold(
        fg_mask,
        MOG2_FOREGROUND_THRESH,
        255,
        cv2.THRESH_BINARY,
    )

    background = subtractor.getBackgroundImage()
    if background is not None:
        dark_diff = cv2.subtract(background, current_gray)
        _, dark_mask = cv2.threshold(
            dark_diff,
            MOG2_DARK_DIFF_THRESH,
            255,
            cv2.THRESH_BINARY,
        )
        binary = cv2.bitwise_and(binary, dark_mask)

    _remove_marker_regions(binary, dst_points)

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MOG2_OPEN_KERNEL)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MOG2_CLOSE_KERNEL)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)

    if frame_count <= MOG2_WARMUP_FRAMES:
        return [], cleaned

    candidates = _contours_to_candidates(
        cleaned,
        min_area=MOG2_MIN_AREA,
        max_area=MOG2_MAX_AREA,
    )

    if MOG2_EXPAND_TO_EXPECTED_RADIUS:
        candidates = _expand_candidates_to_expected_radius(
            candidates,
            cleaned.shape,
        )

    return candidates, cleaned
