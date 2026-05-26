from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import cv2.aruco as aruco
import numpy as np


DETECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DETECT_DIR))

from config import HEIGHT, WIDTH, dst_points


TARGET_SETS = {
    "BIA_TRON": [0, 1, 2, 3],
    "BIA_IPSC": [4, 5, 6, 7],
    "BIA_NGUOI": [8, 9, 10, 11],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect homography-warped target frames from a raw video. "
            "The ArUco marker layout matches cv/DetectBullets/main.py."
        )
    )
    parser.add_argument("--video", required=True, help="Input raw video path.")
    parser.add_argument(
        "--output",
        default="data/bullet_patch/raw",
        help="Output folder for warped target images.",
    )
    parser.add_argument(
        "--target",
        choices=["all", "BIA_TRON", "BIA_IPSC", "BIA_NGUOI"],
        default="all",
        help="Which target to export from each frame.",
    )
    parser.add_argument(
        "--label",
        choices=["bullet", "not_bullet"],
        default="",
        help="Optional label subfolder for organizing source videos.",
    )
    parser.add_argument("--every", type=int, default=1, help="Process every Nth video frame.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after saving this many warped images.")
    parser.add_argument(
        "--input-scale",
        type=float,
        default=1.0,
        help="Scale video frames before ArUco detection and warping.",
    )
    parser.add_argument(
        "--detect-scale",
        type=float,
        default=1.0,
        help="Scale used only for ArUco detection. Corner coordinates are mapped back automatically.",
    )
    parser.add_argument("--sharpen", action="store_true", help="Apply mild sharpening before ArUco detection.")
    parser.add_argument("--ext", choices=["png", "jpg"], default="png", help="Output image format.")
    return parser.parse_args()


def preprocess_frame(frame: np.ndarray, input_scale: float, sharpen: bool) -> np.ndarray:
    if input_scale <= 0:
        raise ValueError("--input-scale must be greater than 0")
    if input_scale != 1.0:
        interpolation = cv2.INTER_CUBIC if input_scale > 1.0 else cv2.INTER_AREA
        frame = cv2.resize(frame, (0, 0), fx=input_scale, fy=input_scale, interpolation=interpolation)
    if sharpen:
        blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
        frame = cv2.addWeighted(frame, 1.6, blurred, -0.6, 0)
    return frame


def detect_aruco(detector: aruco.ArucoDetector, frame: np.ndarray, detect_scale: float):
    if detect_scale <= 0:
        raise ValueError("--detect-scale must be greater than 0")

    detect_frame = frame
    if detect_scale != 1.0:
        interpolation = cv2.INTER_CUBIC if detect_scale > 1.0 else cv2.INTER_AREA
        detect_frame = cv2.resize(frame, (0, 0), fx=detect_scale, fy=detect_scale, interpolation=interpolation)

    gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
    if corners is not None and detect_scale != 1.0:
        corners = [corner / detect_scale for corner in corners]
    return corners, ids, rejected


def get_target_source_points(marker_dict: dict[int, np.ndarray], marker_ids: list[int]) -> np.ndarray | None:
    if not all(marker_id in marker_dict for marker_id in marker_ids):
        return None

    top_left, top_right, bottom_left, bottom_right = marker_ids
    return np.array(
        [
            marker_dict[top_left][0],
            marker_dict[top_right][1],
            marker_dict[bottom_right][2],
            marker_dict[bottom_left][3],
        ],
        dtype=np.float32,
    )


def selected_targets(target: str) -> dict[str, list[int]]:
    if target == "all":
        return TARGET_SETS
    return {target: TARGET_SETS[target]}


def build_output_dir(base: str, label: str) -> Path:
    output_dir = Path(base)
    if label:
        output_dir = output_dir / label
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main() -> None:
    args = parse_args()
    output_dir = build_output_dir(args.output, args.label)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
    targets = selected_targets(args.target)

    frame_idx = 0
    saved = 0
    missed = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_idx += 1
            if frame_idx % args.every != 0:
                continue

            frame = preprocess_frame(frame, args.input_scale, args.sharpen)
            corners, ids, _ = detect_aruco(detector, frame, args.detect_scale)
            if ids is None:
                missed += len(targets)
                continue

            marker_dict = {int(ids[i][0]): corners[i][0] for i in range(len(ids))}

            for target_name, marker_ids in targets.items():
                src_pts = get_target_source_points(marker_dict, marker_ids)
                if src_pts is None:
                    missed += 1
                    continue

                homography, _ = cv2.findHomography(src_pts, dst_points)
                if homography is None:
                    missed += 1
                    continue

                warped = cv2.warpPerspective(frame, homography, (WIDTH, HEIGHT))
                filename = f"frame_{frame_idx:06d}_{target_name}.{args.ext}"
                cv2.imwrite(str(output_dir / filename), warped)
                saved += 1

                if args.max_frames and saved >= args.max_frames:
                    return
    finally:
        cap.release()
        print(f"Saved {saved} warped frames to {output_dir}")
        print(f"Missing target detections: {missed}")


if __name__ == "__main__":
    main()
