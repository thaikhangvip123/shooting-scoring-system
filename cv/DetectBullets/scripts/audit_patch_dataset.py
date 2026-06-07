from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import cv2


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def image_hash(image) -> str:
    digest = hashlib.sha256()
    digest.update(str(image.shape).encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def infer_split_and_label(path: Path) -> tuple[str, str]:
    split = "unknown"
    label = "unknown"
    for parent in path.parents:
        if parent.name in {"train", "val", "test", "labeled", "raw"}:
            split = parent.name
        if parent.name in {"bullet", "not_bullet"}:
            label = parent.name
    return split, label


def iter_images(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit bullet patch dataset for exact duplicate images.")
    parser.add_argument("--root", default="data/bullet_patch", help="Dataset root to scan.")
    parser.add_argument("--csv", default="", help="Optional CSV output for duplicate groups.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {root}")

    by_hash = defaultdict(list)
    counts = defaultdict(int)
    unreadable = 0

    for path in iter_images(root):
        image = cv2.imread(str(path))
        if image is None:
            unreadable += 1
            continue
        split, label = infer_split_and_label(path)
        counts[(split, label)] += 1
        by_hash[image_hash(image)].append(path)

    duplicate_groups = {digest: paths for digest, paths in by_hash.items() if len(paths) > 1}
    cross_split_groups = {
        digest: paths
        for digest, paths in duplicate_groups.items()
        if len({infer_split_and_label(path)[0] for path in paths}) > 1
    }
    cross_label_groups = {
        digest: paths
        for digest, paths in duplicate_groups.items()
        if len({infer_split_and_label(path)[1] for path in paths}) > 1
    }

    print("Image counts:")
    for (split, label), count in sorted(counts.items()):
        print(f"  {split}/{label}: {count}")
    print(f"Unreadable images: {unreadable}")
    print(f"Unique image hashes: {len(by_hash)}")
    print(f"Duplicate groups: {len(duplicate_groups)}")
    print(f"Cross-split duplicate groups: {len(cross_split_groups)}")
    print(f"Cross-label duplicate groups: {len(cross_label_groups)}")

    if args.csv:
        output_path = Path(args.csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["hash", "split", "label", "path"])
            for digest, paths in sorted(duplicate_groups.items()):
                for path in paths:
                    split, label = infer_split_and_label(path)
                    writer.writerow([digest, split, label, path])
        print(f"Saved duplicate report to: {output_path}")


if __name__ == "__main__":
    main()
