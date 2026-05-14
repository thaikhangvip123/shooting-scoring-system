from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _as_float(row: dict, *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        return float(value)
    return default


def _as_int(row: dict, *keys: str, default: int | None = None) -> int | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        return int(float(value))
    return default


def _normalise_rows(rows: list[dict]) -> list[dict]:
    out = []
    for idx, row in enumerate(rows, start=1):
        x = _as_float(row, "x", "x_mm", "x_gt", "x_pred")
        y = _as_float(row, "y", "y_mm", "y_gt", "y_pred")
        if x is None or y is None:
            raise ValueError(f"Row {idx} is missing x/y fields: {row}")
        out.append(
            {
                "row_id": idx,
                "frame_idx": _as_int(row, "frame_idx"),
                "x": x,
                "y": y,
                "score": _as_int(row, "score"),
                "target_name": row.get("target_name", ""),
                "raw": row,
            }
        )
    return out


def _distance(a: dict, b: dict) -> float:
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2)


def greedy_match(
    truth_rows: list[dict],
    pred_rows: list[dict],
    *,
    distance_threshold: float,
    frame_tolerance: int | None,
) -> tuple[list[tuple[dict, dict, float]], list[dict], list[dict]]:
    candidates: list[tuple[float, int, int]] = []
    for gt_idx, gt in enumerate(truth_rows):
        for pred_idx, pred in enumerate(pred_rows):
            if frame_tolerance is not None and gt["frame_idx"] is not None and pred["frame_idx"] is not None:
                if abs(gt["frame_idx"] - pred["frame_idx"]) > frame_tolerance:
                    continue
            dist = _distance(gt, pred)
            if dist <= distance_threshold:
                candidates.append((dist, gt_idx, pred_idx))

    candidates.sort(key=lambda item: item[0])
    matched_gt = set()
    matched_pred = set()
    matches: list[tuple[dict, dict, float]] = []

    for dist, gt_idx, pred_idx in candidates:
        if gt_idx in matched_gt or pred_idx in matched_pred:
            continue
        matched_gt.add(gt_idx)
        matched_pred.add(pred_idx)
        matches.append((truth_rows[gt_idx], pred_rows[pred_idx], dist))

    unmatched_gt = [truth_rows[i] for i in range(len(truth_rows)) if i not in matched_gt]
    unmatched_pred = [pred_rows[i] for i in range(len(pred_rows)) if i not in matched_pred]
    return matches, unmatched_gt, unmatched_pred


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate bullet detection accuracy from ground-truth and prediction CSV files."
    )
    parser.add_argument("--ground-truth", required=True, help="Path to ground-truth CSV")
    parser.add_argument("--predictions", required=True, help="Path to prediction CSV")
    parser.add_argument(
        "--distance-threshold",
        type=float,
        default=20.0,
        help="Maximum Euclidean distance to count a prediction as correct",
    )
    parser.add_argument(
        "--frame-tolerance",
        type=int,
        default=None,
        help="Optional maximum absolute frame index difference for a valid match",
    )
    args = parser.parse_args()

    gt_rows = _normalise_rows(_read_csv_rows(Path(args.ground_truth)))
    pred_rows = _normalise_rows(_read_csv_rows(Path(args.predictions)))
    matches, unmatched_gt, unmatched_pred = greedy_match(
        gt_rows,
        pred_rows,
        distance_threshold=args.distance_threshold,
        frame_tolerance=args.frame_tolerance,
    )

    tp = len(matches)
    fp = len(unmatched_pred)
    fn = len(unmatched_gt)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    mean_error = sum(dist for _, _, dist in matches) / tp if tp else 0.0

    print("Detection accuracy summary")
    print(f"  Ground truth shots : {len(gt_rows)}")
    print(f"  Predicted shots    : {len(pred_rows)}")
    print(f"  TP                 : {tp}")
    print(f"  FP                 : {fp}")
    print(f"  FN                 : {fn}")
    print(f"  Precision          : {precision:.4f}")
    print(f"  Recall             : {recall:.4f}")
    print(f"  F1-score           : {f1:.4f}")
    print(f"  Mean position err  : {mean_error:.4f}")

    if unmatched_gt:
        print("\nMissed ground-truth rows:")
        for row in unmatched_gt[:10]:
            print(f"  gt#{row['row_id']} frame={row['frame_idx']} x={row['x']:.2f} y={row['y']:.2f}")
        if len(unmatched_gt) > 10:
            print(f"  ... and {len(unmatched_gt) - 10} more")

    if unmatched_pred:
        print("\nUnmatched predictions:")
        for row in unmatched_pred[:10]:
            print(f"  pred#{row['row_id']} frame={row['frame_idx']} x={row['x']:.2f} y={row['y']:.2f}")
        if len(unmatched_pred) > 10:
            print(f"  ... and {len(unmatched_pred) - 10} more")


if __name__ == "__main__":
    main()
