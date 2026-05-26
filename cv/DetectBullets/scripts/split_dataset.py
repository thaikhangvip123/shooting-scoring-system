from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def iter_images(folder: Path):
    if not folder.exists():
        raise FileNotFoundError(f"Missing class folder: {folder}")
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def clean_split_dirs(output: Path) -> None:
    for split in ["train", "val", "test"]:
        for class_name in ["bullet", "not_bullet"]:
            dst_dir = output / split / class_name
            if not dst_dir.exists():
                continue
            for path in dst_dir.iterdir():
                if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                    path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Split bullet patch dataset into train/val/test")
    parser.add_argument("--source", default="data/bullet_patch/labeled")
    parser.add_argument("--output", default="data/bullet_patch")
    parser.add_argument("--train", type=float, default=0.7)
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--test", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing image files from train/val/test before copying the new split.",
    )
    args = parser.parse_args()

    total_ratio = args.train + args.val + args.test
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError("train + val + test must equal 1.0")

    source = Path(args.source)
    output = Path(args.output)
    random.seed(args.seed)

    if args.clean:
        clean_split_dirs(output)

    summary = Counter()
    for class_name in ["bullet", "not_bullet"]:
        images = list(iter_images(source / class_name))
        if not images:
            raise ValueError(f"No images found in {source / class_name}")
        random.shuffle(images)

        n = len(images)
        train_end = int(n * args.train)
        val_end = train_end + int(n * args.val)
        splits = {
            "train": images[:train_end],
            "val": images[train_end:val_end],
            "test": images[val_end:],
        }

        for split, paths in splits.items():
            dst_dir = output / split / class_name
            dst_dir.mkdir(parents=True, exist_ok=True)
            for path in paths:
                shutil.copy2(path, dst_dir / path.name)
            summary[(split, class_name)] = len(paths)
            print(f"{split}/{class_name}: {len(paths)}")

    print(f"Total images: {sum(summary.values())}")


if __name__ == "__main__":
    main()
