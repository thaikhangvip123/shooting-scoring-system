from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
import yaml

ROOT = Path(__file__).resolve().parents[3]
DETECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DETECT_DIR))

from ml.bullet_classifier import create_mobilenetv3_small


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export bullet classifier to ONNX")
    parser.add_argument("--config", default="cv/DetectBullets/training/config.yaml")
    parser.add_argument("--model", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cfg = load_config(resolve_path(args.config))
    model_path = resolve_path(args.model or cfg["output"]["model_path"])
    output_path = resolve_path(args.output or cfg["output"]["onnx_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = torch.load(model_path, map_location="cpu")
    input_size = int(checkpoint.get("input_size", cfg["model"].get("input_size", 96)))
    model = create_mobilenetv3_small(num_classes=2, pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    dummy = torch.randn(1, 3, input_size, input_size)
    torch.onnx.export(
        model,
        dummy,
        output_path,
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    print(f"Saved ONNX model to: {output_path}")


if __name__ == "__main__":
    main()
