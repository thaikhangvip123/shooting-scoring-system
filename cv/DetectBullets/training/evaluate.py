from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader
from torchvision import datasets

ROOT = Path(__file__).resolve().parents[3]
DETECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DETECT_DIR))

from ml.bullet_classifier import create_mobilenetv3_small
from ml.transforms import build_eval_transform


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_checkpoint(path: Path) -> dict:
    checkpoint = torch.load(path, map_location="cpu")
    if "model_state" not in checkpoint:
        raise ValueError(f"Expected training checkpoint with model_state, got: {path}")
    return checkpoint


def get_required_class_indices(dataset: datasets.ImageFolder, checkpoint: dict) -> tuple[int, int]:
    if "bullet" not in dataset.class_to_idx or "not_bullet" not in dataset.class_to_idx:
        raise ValueError(f"Expected bullet/not_bullet folders, got: {dataset.class_to_idx}")

    checkpoint_class_to_idx = checkpoint.get("class_to_idx")
    if checkpoint_class_to_idx and checkpoint_class_to_idx != dataset.class_to_idx:
        raise ValueError(
            "Dataset class mapping does not match checkpoint class mapping: "
            f"{dataset.class_to_idx} vs {checkpoint_class_to_idx}"
        )

    model_bullet_index = int(checkpoint.get("bullet_class_index", dataset.class_to_idx["bullet"]))
    dataset_bullet_index = int(dataset.class_to_idx["bullet"])
    return model_bullet_index, dataset_bullet_index


@torch.no_grad()
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trained bullet classifier")
    parser.add_argument("--config", default="cv/DetectBullets/training/config.yaml")
    parser.add_argument("--model", default="")
    parser.add_argument("--split", choices=["val", "test"], default="test")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--write-errors",
        action="store_true",
        help="Write false positive/false negative file paths to CSV.",
    )
    args = parser.parse_args()

    cfg = load_config(resolve_path(args.config))
    model_path = resolve_path(args.model or cfg["output"]["model_path"])
    split_dir = resolve_path(cfg["dataset"][f"{args.split}_dir"])
    results_dir = resolve_path(cfg["output"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint(model_path)
    input_size = int(checkpoint.get("input_size", cfg["model"].get("input_size", 96)))
    threshold = float(args.threshold if args.threshold is not None else checkpoint.get("threshold", 0.7))

    dataset = datasets.ImageFolder(split_dir, transform=build_eval_transform(input_size))
    model_bullet_index, dataset_bullet_index = get_required_class_indices(dataset, checkpoint)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_mobilenetv3_small(num_classes=2, pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    tp = fp = tn = fn = 0
    error_rows = []
    sample_offset = 0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        probs = torch.softmax(logits, dim=1)[:, model_bullet_index]
        preds = (probs >= threshold).long()
        truth = (labels == dataset_bullet_index).long()

        tp += int(((preds == 1) & (truth == 1)).sum().item())
        fp += int(((preds == 1) & (truth == 0)).sum().item())
        tn += int(((preds == 0) & (truth == 0)).sum().item())
        fn += int(((preds == 0) & (truth == 1)).sum().item())

        if args.write_errors:
            probs_cpu = probs.cpu()
            preds_cpu = preds.cpu()
            truth_cpu = truth.cpu()
            for batch_idx, (prob, pred, actual) in enumerate(zip(probs_cpu, preds_cpu, truth_cpu)):
                if int(pred.item()) == int(actual.item()):
                    continue
                sample_path, class_idx = dataset.samples[sample_offset + batch_idx]
                true_label = "bullet" if int(actual.item()) == 1 else "not_bullet"
                pred_label = "bullet" if int(pred.item()) == 1 else "not_bullet"
                error_rows.append(
                    {
                        "path": sample_path,
                        "true_label": true_label,
                        "folder_label": dataset.classes[class_idx],
                        "pred_label": pred_label,
                        "bullet_probability": float(prob.item()),
                    }
                )
        sample_offset += labels.numel()

    total = tp + fp + tn + fn
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    accuracy = (tp + tn) / max(total, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    metrics = {
        "split": args.split,
        "model_path": str(model_path),
        "split_dir": str(split_dir),
        "threshold": threshold,
        "class_to_idx": dataset.class_to_idx,
        "model_bullet_class_index": model_bullet_index,
        "dataset_bullet_class_index": dataset_bullet_index,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

    output_path = results_dir / f"{args.split}_metrics.json"
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print(json.dumps(metrics, indent=2))
    print(f"Saved metrics to: {output_path}")

    if args.write_errors:
        errors_path = results_dir / f"{args.split}_errors.csv"
        with errors_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["path", "true_label", "folder_label", "pred_label", "bullet_probability"],
            )
            writer.writeheader()
            writer.writerows(error_rows)
        print(f"Saved errors to: {errors_path}")


if __name__ == "__main__":
    main()
