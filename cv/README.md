# Shooting Scoring System — Refactored Pipeline

## File layout

```
shooting_pipeline/
├── config.py        ← ALL tunable parameters (edit here first)
├── coords.py        ← px↔mm↔scoring-space conversions
├── scoring.py       ← load polygon/contour data, calculate_score()
├── state.py         ← TargetState + global registry
├── aruco_utils.py   ← CLAHE + ArUco detector, marker helpers
├── layer1.py        ← signed BG diff → candidate blobs
├── layer2.py        ← HoughCircles fast-path + 3-pt RANSAC
├── layer3.py        ← Hungarian temporal tracking, score caching
├── worker.py        ← per-target thread: warp → L1 → L2 → L3 → draw
├── report.py        ← ballistic heatmap + text log
└── main.py          ← video loop, key bindings, thread pool
```

Run with:
```
python main.py
```

---

## Key changes from FullPipeline_V2 (single file)

### Bug fix — Layer 1 classification
`overlap_ratio >= 0.20` was classifying nearly every real bullet hole as a
**shadow** (yellow circle) instead of a **bullet_candidate**. The reason:
bullet rims naturally produce a bright edge right next to the dark hole,
so the bright mask always overlapped the dark blob.

**Fix:** removed the overlap check entirely. Classification now uses
**circularity only** (`circularity_threshold = 0.55` in config.py).
Real holes are circular; smears/shadows are elongated.

### Visible drawing
- Shadow blobs → **RED double-ring** (was single thin yellow circle)
- Confirmed bullets → **green ring + white score** with black shadow stroke
  so text is readable on both light and dark paper
- Candidates (not yet confirmed) → thin **cyan ring**

### Faster warmup
`bg_warmup_frames = 5` (was 10), `sigma_mult = 2.8` (was 3.2) →
detects faster on short test clips.

### Lower RANSAC / Hough thresholds
`ransac_min_inliers = 8` (was 12), `hough_param2 = 10` (was 14) →
catches partial circles from angled shots.

---

## Tuning guide (edit config.py)

| Problem | Parameter to change |
|---|---|
| Lots of false positives | Raise `sigma_mult` (3.0–3.5) |
| Misses real holes | Lower `sigma_mult` (2.5–2.8) |
| Detects too slowly | Lower `confirm_frames` (3–4) |
| Phantom bullets between shots | Raise `confirm_frames` (5–6) |
| Circles wrong size | Adjust `expected_radius` |
| Shadows not filtered | Raise `circularity_threshold` (0.65–0.75) |
| Partial holes missed | Lower `circularity_threshold` (0.45–0.55) |

---

## Debug tips

Press **[d]** while running to toggle the background model overlay —
you'll see the rolling BG for each target and can verify it's not
"learning" bullet holes (it should stay as the clean target paper).

If Hits stays 0:
1. Check the Camera window — are all 4 ArUco markers detected?
   The overlay shows `Markers: [0,1,2,3,...]` if detection works.
2. Check the Result window — do you see any red double-rings or cyan rings?
   If yes, Layer 1 is working but Layer 3 hasn't confirmed yet (wait a few frames).
   If no circles at all, BG warmup may still be running (orange "Warming up..." text).
3. Press [r] to reset the BG and try again after a big lighting change.
