from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader
from torchvision import datasets

ROOT = Path(__file__).resolve().parents[3]
DETECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DETECT_DIR))

from ml.bullet_classifier import create_mobilenetv3_small
from ml.transforms import build_eval_transform, build_train_transform


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_bullet_class_index(dataset: datasets.ImageFolder) -> int:
    if "bullet" not in dataset.class_to_idx or "not_bullet" not in dataset.class_to_idx:
        raise ValueError(
            f"Expected folders named bullet and not_bullet, got {dataset.class_to_idx}."
        )
    return int(dataset.class_to_idx["bullet"])


def count_by_class(dataset: datasets.ImageFolder) -> dict[str, int]:
    idx_to_class = {idx: class_name for class_name, idx in dataset.class_to_idx.items()}
    counts = {class_name: 0 for class_name in dataset.class_to_idx}
    for _, class_idx in dataset.samples:
        counts[idx_to_class[class_idx]] += 1
    return counts


def compute_class_weights(dataset: datasets.ImageFolder, device: torch.device) -> torch.Tensor:
    counts_by_idx = [0] * len(dataset.classes)
    for _, class_idx in dataset.samples:
        counts_by_idx[class_idx] += 1

    total = sum(counts_by_idx)
    weights = [
        total / (len(counts_by_idx) * max(class_count, 1))
        for class_count in counts_by_idx
    ]
    return torch.tensor(weights, dtype=torch.float32, device=device)


def build_model(pretrained: bool):
    try:
        return create_mobilenetv3_small(num_classes=2, pretrained=pretrained)
    except Exception as exc:
        if not pretrained:
            raise
        print(f"Warning: could not load pretrained weights ({exc}). Training from scratch instead.")
        return create_mobilenetv3_small(num_classes=2, pretrained=False)


def build_optimizer(model, optimizer_name: str, lr: float, weight_decay: float):
    optimizer_name = optimizer_name.lower()
    if optimizer_name == "adamw":
        return torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    if optimizer_name == "adam":
        return torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    if optimizer_name == "sgd":
        return torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=weight_decay)
    raise ValueError(f"Unsupported optimizer: {optimizer_name}")


def build_scheduler(optimizer, scheduler_name: str, epochs: int):
    scheduler_name = scheduler_name.lower()
    if scheduler_name in {"", "none"}:
        return None
    if scheduler_name == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))
    raise ValueError(f"Unsupported scheduler: {scheduler_name}")


def load_resume_checkpoint(model, resume_path: Path, expected_input_size: int, train_class_to_idx: dict) -> dict:
    checkpoint = torch.load(resume_path, map_location="cpu")
    state = checkpoint.get("model_state", checkpoint)
    model.load_state_dict(state)

    checkpoint_input_size = checkpoint.get("input_size") or checkpoint.get("img_size")
    if checkpoint_input_size and int(checkpoint_input_size) != expected_input_size:
        print(
            f"Warning: checkpoint input_size={checkpoint_input_size} "
            f"differs from config input_size={expected_input_size}."
        )

    checkpoint_class_to_idx = checkpoint.get("class_to_idx")
    if checkpoint_class_to_idx and checkpoint_class_to_idx != train_class_to_idx:
        raise ValueError(
            "Resume checkpoint class mapping does not match current dataset: "
            f"{checkpoint_class_to_idx} vs {train_class_to_idx}"
        )

    return checkpoint


def train_one_epoch(model, loader, criterion, optimizer, device) -> float:
    model.train()
    total_loss = 0.0

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)

        logits = model(images)
        loss = criterion(logits, labels)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += float(loss.item())

    return total_loss / max(len(loader), 1)


@torch.no_grad()
def evaluate(model, loader, criterion, device) -> dict:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)
        preds = torch.argmax(logits, dim=1)

        total_loss += float(loss.item())
        correct += int((preds == labels).sum().item())
        total += int(labels.numel())

    return {
        "loss": total_loss / max(len(loader), 1),
        "accuracy": correct / max(total, 1),
    }


@torch.no_grad()
def collect_binary_predictions(model, loader, device, bullet_class_index: int) -> tuple[torch.Tensor, torch.Tensor]:
    model.eval()
    all_probs = []
    all_truth = []

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        probs = torch.softmax(logits, dim=1)[:, bullet_class_index]
        truth = (labels == bullet_class_index).long()
        all_probs.append(probs.cpu())
        all_truth.append(truth.cpu())

    return torch.cat(all_probs), torch.cat(all_truth)


def binary_metrics(probs: torch.Tensor, truth: torch.Tensor, threshold: float) -> dict:
    preds = (probs >= threshold).long()
    tp = int(((preds == 1) & (truth == 1)).sum().item())
    fp = int(((preds == 1) & (truth == 0)).sum().item())
    tn = int(((preds == 0) & (truth == 0)).sum().item())
    fn = int(((preds == 0) & (truth == 1)).sum().item())

    total = tp + fp + tn + fn
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    accuracy = (tp + tn) / max(total, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def find_best_threshold(probs: torch.Tensor, truth: torch.Tensor) -> dict:
    best = None
    for threshold in np.linspace(0.05, 0.95, 91):
        metrics = binary_metrics(probs, truth, float(threshold))
        if best is None or metrics["f1"] > best["f1"]:
            best = metrics
    return best or binary_metrics(probs, truth, 0.7)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train MobileNetV3-Small bullet classifier")
    parser.add_argument("--config", default="cv/DetectBullets/training/config.yaml")
    parser.add_argument(
        "--resume",
        default="",
        help="Optional checkpoint path to continue fine tuning from an existing model.",
    )
    args = parser.parse_args()

    cfg = load_config(resolve_path(args.config))
    set_seed(int(cfg["training"].get("seed", 42)))

    input_size = int(cfg["model"].get("input_size", 96))
    batch_size = int(cfg["training"].get("batch_size", 32))
    num_workers = int(cfg["training"].get("num_workers", 2))
    epochs = int(cfg["training"].get("epochs", 30))
    lr = float(cfg["training"].get("learning_rate", 1e-4))
    optimizer_name = str(cfg["training"].get("optimizer", "adamw"))
    weight_decay = float(cfg["training"].get("weight_decay", 1e-4))
    scheduler_name = str(cfg["training"].get("scheduler", "cosine"))
    label_smoothing = float(cfg["training"].get("label_smoothing", 0.0))

    train_dir = resolve_path(cfg["dataset"]["train_dir"])
    val_dir = resolve_path(cfg["dataset"]["val_dir"])
    model_path = resolve_path(cfg["output"]["model_path"])
    results_dir = resolve_path(cfg["output"]["results_dir"])
    resume_path_config = cfg["model"].get("resume_path", "")
    resume_path = resolve_path(args.resume or resume_path_config) if (args.resume or resume_path_config) else None
    model_path.parent.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    train_ds = datasets.ImageFolder(train_dir, transform=build_train_transform(input_size))
    val_ds = datasets.ImageFolder(val_dir, transform=build_eval_transform(input_size))
    bullet_class_index = get_bullet_class_index(train_ds)
    if val_ds.class_to_idx != train_ds.class_to_idx:
        raise ValueError(f"Train/val class mapping mismatch: {train_ds.class_to_idx} vs {val_ds.class_to_idx}")
    if len(train_ds) == 0 or len(val_ds) == 0:
        raise ValueError(f"Train/val dataset must not be empty: train={len(train_ds)}, val={len(val_ds)}")

    print(f"class_to_idx={train_ds.class_to_idx}")
    print(f"train counts={count_by_class(train_ds)}")
    print(f"val counts={count_by_class(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(pretrained=bool(cfg["model"].get("pretrained", True)))
    resume_checkpoint = None
    if resume_path:
        if not resume_path.exists():
            raise FileNotFoundError(f"Resume checkpoint does not exist: {resume_path}")
        resume_checkpoint = load_resume_checkpoint(
            model=model,
            resume_path=resume_path,
            expected_input_size=input_size,
            train_class_to_idx=train_ds.class_to_idx,
        )
        print(f"Resumed model weights from: {resume_path}")
        if "threshold" in resume_checkpoint:
            print(f"Previous checkpoint threshold={float(resume_checkpoint['threshold']):.3f}")
    model.to(device)

    class_weights = None
    if bool(cfg["training"].get("class_weights", True)):
        class_weights = compute_class_weights(train_ds, device)
        print(f"class_weights={class_weights.detach().cpu().tolist()}")

    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=label_smoothing)
    optimizer = build_optimizer(model, optimizer_name=optimizer_name, lr=lr, weight_decay=weight_decay)
    scheduler = build_scheduler(optimizer, scheduler_name=scheduler_name, epochs=epochs)

    best_f1 = -1.0
    history = []

    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_metrics = evaluate(model, val_loader, criterion, device)
        val_probs, val_truth = collect_binary_predictions(model, val_loader, device, bullet_class_index)
        threshold_metrics = find_best_threshold(val_probs, val_truth)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "threshold": threshold_metrics["threshold"],
            "threshold_accuracy": threshold_metrics["accuracy"],
            "threshold_precision": threshold_metrics["precision"],
            "threshold_recall": threshold_metrics["recall"],
            "threshold_f1": threshold_metrics["f1"],
            "learning_rate": optimizer.param_groups[0]["lr"],
        }
        history.append(row)
        print(
            f"Epoch {epoch:03d}/{epochs} "
            f"train_loss={train_loss:.4f} "
            f"val_loss={val_metrics['loss']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} "
            f"best_thr={threshold_metrics['threshold']:.2f} "
            f"f1={threshold_metrics['f1']:.4f} "
            f"precision={threshold_metrics['precision']:.4f} "
            f"recall={threshold_metrics['recall']:.4f}"
        )

        if threshold_metrics["f1"] > best_f1:
            best_f1 = threshold_metrics["f1"]
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "class_to_idx": train_ds.class_to_idx,
                    "bullet_class_index": bullet_class_index,
                    "input_size": input_size,
                    "threshold": threshold_metrics["threshold"],
                    "val_metrics": threshold_metrics,
                    "model_name": "mobilenetv3_small",
                    "resumed_from": str(resume_path) if resume_path else "",
                },
                model_path,
            )

        if scheduler is not None:
            scheduler.step()

    with (results_dir / "training_history.json").open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)

    print(f"Saved best model to: {model_path}")


if __name__ == "__main__":
    main()
