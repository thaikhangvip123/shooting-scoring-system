# Bullet patch dataset

Use this folder for cropped candidate images used to train MobileNetV3-Small.

```text
raw/                  # unlabelled crops from videos
labeled/
  bullet/
  not_bullet/
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

`raw/` is for automatic crops before manual labeling. Move labelled images to
`labeled/bullet` or `labeled/not_bullet`, then run `split_dataset.py`.

## Current dataset flow

```text
raw video
-> cv/DetectBullets/scripts/collect_patches.py
-> warped target frames
-> cv/DetectBullets/scripts/crop_candidate_patches.py
-> labeled/bullet or labeled/not_bullet patch images
-> cv/DetectBullets/scripts/split_dataset.py
-> train/val/test
```

Example:

```powershell
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\bullet --background data\warped_frames\not_bullet --label bullet
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\not_bullet --background data\warped_frames\not_bullet --label not_bullet --random-negatives 3
```

If bullet videos contain shadows or moving leaf patterns, do not save candidates
directly to `labeled/bullet`. Save them to `raw/`, review manually, then move
real bullet-hole patches to `labeled/bullet` and shadow/noise patches to
`labeled/not_bullet`.

```powershell
python cv\DetectBullets\scripts\crop_candidate_patches.py --input data\warped_frames\bullet --background data\warped_frames\not_bullet --output data\bullet_patch\raw --label none --prefix review_bullet --every 3 --max-area 2500 --min-circularity 0.55
```
