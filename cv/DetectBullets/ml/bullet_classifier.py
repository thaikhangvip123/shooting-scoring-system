from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import torch
from torchvision import models

try:
    from .transforms import build_cv_inference_transform
except ImportError:
    from transforms import build_cv_inference_transform


@dataclass
class CandidatePrediction:
    candidate: dict
    probability: float
    patch: object | None = None


def create_mobilenetv3_small(num_classes: int = 2, pretrained: bool = False):
    weights = models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
    model = models.mobilenet_v3_small(weights=weights)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = torch.nn.Linear(in_features, num_classes)
    return model


class BulletClassifier:
    def __init__(
        self,
        model_path: str | Path,
        input_size: int = 96,
        threshold: float | None = None,
        device: str | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.input_size = int(input_size)
        self.threshold = float(threshold) if threshold is not None else None
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.transform = build_cv_inference_transform(self.input_size)
        self.bullet_class_index = 1
        self.model = self._load_model()

    def _load_model(self):
        checkpoint = torch.load(self.model_path, map_location=self.device)
        img_size = checkpoint.get("input_size") or checkpoint.get("img_size")
        if img_size:
            self.input_size = int(img_size)
            self.transform = build_cv_inference_transform(self.input_size)
        self.bullet_class_index = int(checkpoint.get("bullet_class_index", 1))
        if self.threshold is None:
            self.threshold = float(checkpoint.get("threshold", 0.7))

        model = create_mobilenetv3_small(num_classes=2, pretrained=False)
        state = checkpoint.get("model_state", checkpoint)
        model.load_state_dict(state)
        model.to(self.device)
        model.eval()
        return model

    def predict_patch(self, patch_bgr) -> float:
        patch_rgb = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2RGB)
        x = self.transform(patch_rgb).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(x)
            probabilities = torch.softmax(logits, dim=1)
            return float(probabilities[0, self.bullet_class_index].item())

    def crop_candidate_patch(self, image_bgr, candidate: dict):
        contour = candidate["contour"]
        x, y, w, h = cv2.boundingRect(contour)
        cx = x + w // 2
        cy = y + h // 2
        half = self.input_size // 2

        top = cy - half
        bottom = cy + half
        left = cx - half
        right = cx + half

        if top < 0 or left < 0 or bottom > image_bgr.shape[0] or right > image_bgr.shape[1]:
            return None
        return image_bgr[top:bottom, left:right]

    def filter_candidates(self, image_bgr, candidates: Iterable[dict]) -> list[dict]:
        kept = []
        for candidate in candidates:
            patch = self.crop_candidate_patch(image_bgr, candidate)
            if patch is None:
                continue
            probability = self.predict_patch(patch)
            if probability >= self.threshold:
                candidate = dict(candidate)
                candidate["cnn_probability"] = probability
                kept.append(candidate)
        return kept
