import cv2
import numpy as np

from config import *


def process_layer_1(bg_gray, current_gray, dst_points):
    # 1. Smooth background subtraction
    dark_diff = cv2.subtract(bg_gray, current_gray)
    _, darkening_mask = cv2.threshold(dark_diff, 25, 255, cv2.THRESH_BINARY)

    # 2. Remove noise near the paper border
    mask_radius = 350
    for p in dst_points:
        cv2.circle(darkening_mask, (int(p[0]), int(p[1])), mask_radius, 0, -1)

    kernel = np.ones((5, 5), np.uint8)
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_OPEN, kernel)
    darkening_mask = cv2.morphologyEx(darkening_mask, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(
        darkening_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates = []

    for c in cnts:
        if cv2.contourArea(c) < 600:
            continue

        hull = cv2.convexHull(c)
        area = cv2.contourArea(hull)
        perimeter = cv2.arcLength(hull, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * (area / (perimeter ** 2))

        if circularity >= CIRCULARITY_THRESH:
            candidates.append({"contour": c, "label": "bullet"})

    return candidates, darkening_mask
