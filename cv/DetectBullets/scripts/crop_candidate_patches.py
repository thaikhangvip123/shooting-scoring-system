from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


DETECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DETECT_DIR))

from config import dst_points
from layer1 import process_layer_1


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TARGET_NAMES = ("BIA_TRON", "BIA_IPSC", "BIA_NGUOI")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crop 96x96 candidate patches from homography-warped target images. "
            "Use this after collect_patches.py and before split_dataset.py."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Folder containing warped target frames, e.g. data/warped_frames/bullet.",
    )
    parser.add_argument(
        "--background",
        default="",
        help=(
            "Optional folder containing clean warped frames. If omitted, the first image "
            "for each target in --input is used as the reference background."
        ),
    )
    parser.add_argument(
        "--output",
        default="data/bullet_patch/labeled",
        help="Output root. With --label bullet/not_bullet, patches are saved under this label subfolder.",
    )
    parser.add_argument(
        "--label",
        choices=["auto", "bullet", "not_bullet", "none"],
        default="auto",
        help="Patch label folder. auto uses the input folder name when it is bullet/not_bullet.",
    )
    parser.add_argument(
        "--target",
        choices=["all", "BIA_TRON", "BIA_IPSC", "BIA_NGUOI"],
        default="all",
        help="Only crop frames for this target type.",
    )
    parser.add_argument("--patch-size", type=int, default=96, help="Square crop size.")
    parser.add_argument("--every", type=int, default=1, help="Process every Nth image after sorting by filename.")
    parser.add_argument("--max-patches", type=int, default=0, help="Stop after saving this many patches.")
    parser.add_argument(
        "--background-samples",
        type=int,
        default=30,
        help="Maximum clean frames per target used to build a median background.",
    )
    parser.add_argument(
        "--random-negatives",
        type=int,
        default=0,
        help="Also save this many random patches per image. Useful for not_bullet data.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for random negative crops.")
    parser.add_argument("--ext", choices=["png", "jpg"], default="png", help="Output image format.")
    return parser.parse_args()


def iter_images(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)


def detect_target_name(path: Path) -> str:
    name = path.stem.upper()
    for target_name in TARGET_NAMES:
        if target_name in name:
            return target_name
    return "UNKNOWN"


def group_by_target(paths: list[Path], selected_target: str) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        target_name = detect_target_name(path)
        if selected_target != "all" and target_name != selected_target:
            continue
        grouped[target_name].append(path)
    return dict(grouped)


def resolve_label(input_dir: Path, label: str) -> str:
    if label != "auto":
        return "" if label == "none" else label
    if input_dir.name in {"bullet", "not_bullet"}:
        return input_dir.name
    return ""


def make_output_dir(output_root: Path, label: str) -> Path:
    output_dir = output_root / label if label else output_root
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def read_gray_blurred(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    return cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0)


def build_backgrounds(
    input_groups: dict[str, list[Path]],
    background_groups: dict[str, list[Path]],
    sample_limit: int,
) -> dict[str, np.ndarray]:
    backgrounds: dict[str, np.ndarray] = {}

    for target_name, input_paths in input_groups.items():
        source_paths = background_groups.get(target_name) or input_paths[:1]
        if sample_limit > 0:
            source_paths = source_paths[:sample_limit]

        frames = []
        for path in source_paths:
            gray = read_gray_blurred(path)
            if gray is not None:
                frames.append(gray)

        if not frames:
            print(f"Warning: no usable background for {target_name}; skipping this target.")
            continue

        if len(frames) == 1:
            backgrounds[target_name] = frames[0]
        else:
            backgrounds[target_name] = np.median(np.stack(frames, axis=0), axis=0).astype(np.uint8)

        if not background_groups.get(target_name):
            print(
                f"Warning: using first input image as background for {target_name}. "
                "Provide --background with clean/not_bullet warped frames when possible."
            )

    return backgrounds


def crop_centered(image: np.ndarray, center_x: int, center_y: int, patch_size: int) -> np.ndarray | None:
    half = patch_size // 2
    top = center_y - half
    bottom = top + patch_size
    left = center_x - half
    right = left + patch_size

    if top < 0 or left < 0 or bottom > image.shape[0] or right > image.shape[1]:
        return None
    return image[top:bottom, left:right]


def crop_candidate_patch(image: np.ndarray, contour: np.ndarray, patch_size: int) -> tuple[np.ndarray, int, int] | None:
    x, y, w, h = cv2.boundingRect(contour)
    center_x = x + w // 2
    center_y = y + h // 2
    patch = crop_centered(image, center_x, center_y, patch_size)
    if patch is None:
        return None
    return patch, center_x, center_y


def save_patch(output_dir: Path, patch: np.ndarray, stem: str, suffix: str, ext: str) -> Path:
    path = output_dir / f"{stem}_{suffix}.{ext}"
    cv2.imwrite(str(path), patch)
    return path


def save_random_negatives(
    image: np.ndarray,
    output_dir: Path,
    stem: str,
    patch_size: int,
    count: int,
    ext: str,
) -> int:
    if count <= 0:
        return 0

    height, width = image.shape[:2]
    if height < patch_size or width < patch_size:
        return 0

    half = patch_size // 2
    saved = 0
    for idx in range(count):
        center_x = random.randint(half, width - half)
        center_y = random.randint(half, height - half)
        patch = crop_centered(image, center_x, center_y, patch_size)
        if patch is None:
            continue
        save_patch(output_dir, patch, stem, f"rand_{idx:03d}_x{center_x:04d}_y{center_y:04d}", ext)
        saved += 1
    return saved


def main() -> None:
    args = parse_args()
    if args.patch_size <= 0 or args.patch_size % 2 != 0:
        raise ValueError("--patch-size must be a positive even number.")
    if args.every <= 0:
        raise ValueError("--every must be greater than 0.")

    random.seed(args.seed)

    input_dir = Path(args.input)
    if not input_dir.exists():
        raise RuntimeError(f"Input folder does not exist: {input_dir}")

    label = resolve_label(input_dir, args.label)
    output_dir = make_output_dir(Path(args.output), label)

    input_paths = iter_images(input_dir)
    input_groups = group_by_target(input_paths, args.target)
    if not input_groups:
        raise RuntimeError(f"No warped images found in {input_dir} for target={args.target}")

    background_groups: dict[str, list[Path]] = {}
    if args.background:
        background_dir = Path(args.background)
        if not background_dir.exists():
            raise RuntimeError(f"Background folder does not exist: {background_dir}")
        background_groups = group_by_target(iter_images(background_dir), args.target)

    backgrounds = build_backgrounds(input_groups, background_groups, args.background_samples)

    saved_candidates = 0
    saved_random = 0
    processed = 0
    skipped_without_background = 0

    for target_name, paths in input_groups.items():
        background_gray = backgrounds.get(target_name)
        if background_gray is None:
            skipped_without_background += len(paths)
            continue

        for image_index, path in enumerate(paths):
            if image_index % args.every != 0:
                continue

            image = cv2.imread(str(path))
            if image is None:
                continue

            current_gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0)
            candidates, _ = process_layer_1(background_gray, current_gray, dst_points)
            processed += 1

            for candidate_index, candidate in enumerate(candidates):
                cropped = crop_candidate_patch(image, candidate["contour"], args.patch_size)
                if cropped is None:
                    continue
                patch, center_x, center_y = cropped
                suffix = f"cand_{candidate_index:03d}_x{center_x:04d}_y{center_y:04d}"
                save_patch(output_dir, patch, path.stem, suffix, args.ext)
                saved_candidates += 1

                if args.max_patches and (saved_candidates + saved_random) >= args.max_patches:
                    print(f"Processed warped images: {processed}")
                    print(f"Saved candidate patches: {saved_candidates}")
                    print(f"Saved random patches: {saved_random}")
                    print(f"Output folder: {output_dir}")
                    return

            saved_random += save_random_negatives(
                image=image,
                output_dir=output_dir,
                stem=path.stem,
                patch_size=args.patch_size,
                count=args.random_negatives,
                ext=args.ext,
            )

            if args.max_patches and (saved_candidates + saved_random) >= args.max_patches:
                print(f"Processed warped images: {processed}")
                print(f"Saved candidate patches: {saved_candidates}")
                print(f"Saved random patches: {saved_random}")
                print(f"Output folder: {output_dir}")
                return

    print(f"Processed warped images: {processed}")
    print(f"Skipped images without background: {skipped_without_background}")
    print(f"Saved candidate patches: {saved_candidates}")
    print(f"Saved random patches: {saved_random}")
    print(f"Output folder: {output_dir}")


if __name__ == "__main__":
    main()
