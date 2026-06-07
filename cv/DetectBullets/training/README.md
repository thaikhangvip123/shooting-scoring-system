# MobileNetV3-Small training

This folder trains the bullet-hole candidate classifier used after `layer1.py`
and before `layer2.py`.

## Full command flow

Run these commands from the repository root:

```powershell
cd E:\shooting-scoring-system
```

### 1. Export warped target frames

Use raw UE5/camera video and save homography-warped target images.

Bullet video:

```powershell
python cv\DetectBullets\scripts\collect_patches.py --video C:\path\to\bullet.mp4 --label bullet --output data\warped_frames
```

Clean/not-bullet video:

```powershell
python cv\DetectBullets\scripts\collect_patches.py --video C:\path\to\not_bullet.mp4 --label not_bullet --output data\warped_frames
```

The script prefixes output filenames with the input video name by default, so
new clips do not overwrite previous `frame_000001...` files. Use `--prefix`
when you want to set the name manually:

```powershell
python cv\DetectBullets\scripts\collect_patches.py --video C:\path\to\bullet_02.mp4 --label bullet --output data\warped_frames --prefix bullet_02
```

Optional target-only export:

```powershell
python cv\DetectBullets\scripts\collect_patches.py --video C:\path\to\bullet.mp4 --target BIA_TRON --label bullet --output data\warped_frames
```

If ArUco detection misses too many frames:

```powershell
python cv\DetectBullets\scripts\collect_patches.py --video C:\path\to\bullet.mp4 --label bullet --output data\warped_frames --detect-scale 2.0 --sharpen
```

### 2. Crop classifier patches

Crop `96x96` candidate patches from the warped frames.

Bullet patches:

```powershell
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\bullet --background data\warped_frames\not_bullet --label bullet
```

If the bullet video contains moving shadows, save candidates to `raw` first and
sort them manually. Put real bullet-hole patches into `labeled/bullet`, and put
shadow/noise patches into `labeled/not_bullet` as hard negatives:

```powershell
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\bullet --background data\warped_frames\not_bullet --output data\bullet_patch\raw --label none --prefix review_bullet --every 3 --max-area 2500 --min-circularity 0.55
```

Not-bullet patches:

```powershell
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\not_bullet --background data\warped_frames\not_bullet --label not_bullet --random-negatives 3
```

By default the crop script hashes existing patches in the output folder and
skips exact duplicates. Pass `--allow-duplicates` only if you intentionally
want to keep repeated identical patches.

Patch output:

```text
data/bullet_patch/labeled/bullet
data/bullet_patch/labeled/not_bullet
```

Open and review a few generated patches before training. Move mislabeled crops
between `bullet` and `not_bullet` if needed.

Audit exact duplicates and split leakage:

```powershell
python cv\DetectBullets\scripts\audit_patch_dataset.py --root data\bullet_patch --csv cv\DetectBullets\results\duplicate_patches.csv
```

### 3. Split train/val/test

```powershell
python cv\DetectBullets\scripts\split_dataset.py --source data\bullet_patch\labeled --output data\bullet_patch --clean
```

Output:

```text
data/bullet_patch/train
data/bullet_patch/val
data/bullet_patch/test
```

## Dataset layout

Put cropped patches here:

```text
data/bullet_patch/
  train/
    bullet/
    not_bullet/
  val/
    bullet/
    not_bullet/
  test/
    bullet/
    not_bullet/
```

The folder names are important. The training script stores the actual
`class_to_idx` mapping in the checkpoint, so inference can read the correct
`bullet` class index later.

## Train

```bash
python cv/DetectBullets/training/train_mobilenetv3.py --config cv/DetectBullets/training/config.yaml
```

Continue training from an existing checkpoint:

```bash
python cv/DetectBullets/training/train_mobilenetv3.py --config cv/DetectBullets/training/config.yaml --resume cv/DetectBullets/models/mobilenetv3_bullet.pt
```

Output:

```text
cv/DetectBullets/models/mobilenetv3_bullet.pt
cv/DetectBullets/results/training_history.json
```

The training script uses MobileNetV3-Small fine tuning with augmentation,
optional class weights, AdamW, cosine scheduling, and validation-threshold
tuning. The best checkpoint is selected by validation F1 and stores the
recommended `threshold` for inference.

## Evaluate

```bash
python cv/DetectBullets/training/evaluate.py --config cv/DetectBullets/training/config.yaml --split test
```

By default evaluation uses the threshold stored in the checkpoint. Pass
`--threshold 0.7` to override it.

Write false positives and false negatives to CSV:

```powershell
python cv\DetectBullets\training\evaluate.py --config cv\DetectBullets\training\config.yaml --split test --write-errors
```

Output:

```text
cv/DetectBullets/results/test_metrics.json
cv/DetectBullets/results/test_errors.csv
```

## Visualize Predictions

Create preview images with predicted label, true label, threshold, and green/red
borders for correct/error samples:

```powershell
python cv\DetectBullets\scripts\visualize_predictions.py --model cv\DetectBullets\models\mobilenetv3_bullet.pt --input data\bullet_patch\test --output cv\DetectBullets\results\prediction_preview --clean
```

Output:

```text
cv/DetectBullets/results/prediction_preview/correct
cv/DetectBullets/results/prediction_preview/errors
```

## Export ONNX

```bash
python cv/DetectBullets/training/export_onnx.py --config cv/DetectBullets/training/config.yaml
```

## Realtime use

Load `cv/DetectBullets/models/mobilenetv3_bullet.pt` with
`cv/DetectBullets/ml/bullet_classifier.py`, then filter candidates between
`layer1.py` and `layer2.py`.
