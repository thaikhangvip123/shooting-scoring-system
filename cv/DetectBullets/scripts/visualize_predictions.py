from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import cv2

DETECT_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(DETECT_DIR))

from ml.bullet_classifier import BulletClassifier


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def infer_true_label(path: Path) -> str:
    for parent in [path.parent, *path.parents]:
        if parent.name in {"bullet", "not_bullet"}:
            return parent.name
    return "unknown"


def draw_prediction(preview, true_label: str, pred_label: str, probability: float, threshold: float):
    is_correct = true_label == "unknown" or true_label == pred_label
    color = (0, 180, 0) if is_correct else (0, 0, 255)
    cv2.rectangle(preview, (0, 0), (preview.shape[1] - 1, preview.shape[0] - 1), color, 2)

    lines = [
        f"pred: {pred_label} {probability:.2f}",
        f"true: {true_label}",
        f"thr: {threshold:.2f}",
    ]
    y = 18
    for line in lines:
        cv2.putText(preview, line, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
        cv2.putText(preview, line, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        y += 17
    return is_correct


def main() -> None:
    parser = argparse.ArgumentParser(description="Write prediction labels onto patch images")
    parser.add_argument("--model", default="cv/DetectBullets/models/mobilenetv3_bullet.pt")
    parser.add_argument("--input", default="data/bullet_patch/test")
    parser.add_argument("--output", default="cv/DetectBullets/results/prediction_preview")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--clean", action="store_true", help="Remove the output folder before writing previews.")
    args = parser.parse_args()

    model_path = resolve_path(args.model)
    input_dir = resolve_path(args.input)
    output_dir = resolve_path(args.output)
    if not model_path.exists():
        raise FileNotFoundError(f"Model does not exist: {model_path}")
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")

    classifier = BulletClassifier(model_path, threshold=args.threshold)
    threshold = float(classifier.threshold)
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    correct = 0
    errors = 0
    for path in input_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        prob = classifier.predict_patch(image)
        pred = "bullet" if prob >= threshold else "not_bullet"
        true_label = infer_true_label(path)
        preview = image.copy()
        is_correct = draw_prediction(preview, true_label, pred, prob, threshold)
        rel = path.relative_to(input_dir)
        subdir = "correct" if is_correct else "errors"
        dst = output_dir / subdir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dst), preview)
        count += 1
        if is_correct:
            correct += 1
        else:
            errors += 1

    print(f"Threshold: {threshold:.3f}")
    print(f"Wrote {count} preview images to {output_dir}")
    print(f"Correct: {correct}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()
