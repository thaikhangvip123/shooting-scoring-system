"""
report.py — Visual ballistic report (heatmap + cluster analysis) and log writer.

Press [a/b/c] in the main loop to trigger a report for each target.
Press [s] to write a text log entry.
"""

import io
import os
from datetime import datetime
from typing import List

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from config import CFG, CENTER_X_PX, CENTER_Y_PX, PIXELS_PER_MM
from coords import px_to_mm
from state import target_states


# ── Visual report ─────────────────────────────────────────────────────────────

def generate_visual_report(target_name: str) -> None:
    """
    Produce a ballistic analysis plot for `target_name` and display it
    in a new OpenCV window.

    Metrics:
      MRE  — Mean Radial Error (average distance from target centre)
      CEP  — Circular Error Probable / R50 (median radial error)
      K-means clusters (auto-selected k via silhouette score)
    """
    state = target_states[target_name]

    shots_mm: List[List[float]] = []
    with state.lock:
        for v in state.confirmed.values():
            cx, cy = v["pos"]
            xm, ym = px_to_mm(cx, cy)
            shots_mm.append([xm, ym])

    if len(shots_mm) < 2:
        print(f"[{target_name}] Need ≥ 2 confirmed bullets for a report "
              f"(have {len(shots_mm)}).")
        return

    shots_mm = np.array(shots_mm)
    distances = np.linalg.norm(shots_mm, axis=1)
    mre_mm    = float(np.mean(distances))
    r50_mm    = float(np.median(distances))

    # ── Auto-select k via silhouette ─────────────────────────────────────────
    best_k, best_sil = 1, -1.0
    max_k = min(5, len(shots_mm) - 1)
    if len(shots_mm) >= 3:
        for k in range(2, max_k + 1):
            labels_tmp = KMeans(n_clusters=k, random_state=42,
                                n_init=10).fit_predict(shots_mm)
            sc = silhouette_score(shots_mm, labels_tmp)
            if sc > best_sil:
                best_sil, best_k = sc, k
    if best_sil < 0.40:
        best_k = 1

    kmeans  = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels  = kmeans.fit_predict(shots_mm)
    centers = kmeans.cluster_centers_

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_title(
        f"BALLISTIC REPORT — {target_name}\n"
        f"MRE: {mre_mm:.1f} mm  |  CEP (R50): {r50_mm:.1f} mm  |  "
        f"{best_k} cluster(s)",
        fontsize=13, fontweight="bold",
    )

    # Background template image
    tmpl_path = CFG.template_paths.get(target_name, "")
    if os.path.exists(tmpl_path):
        img_bg   = cv2.cvtColor(cv2.imread(tmpl_path), cv2.COLOR_BGR2RGB)
        cx_lim   = CENTER_X_PX   / PIXELS_PER_MM
        cy_lim   = CENTER_Y_PX   / PIXELS_PER_MM
        ax.imshow(img_bg,
                  extent=[-cx_lim, cx_lim, -cy_lim, cy_lim],
                  alpha=0.75)

    # KDE heatmap
    if len(shots_mm) >= 3:
        sns.kdeplot(x=shots_mm[:, 0], y=shots_mm[:, 1],
                    fill=True, cmap="Reds", alpha=0.35,
                    thresh=0.05, ax=ax)

    # Scatter per cluster
    palette = ["#00FFFF", "#FFFF00", "#FF00FF", "#00FF00", "#FFA500"]
    for i in range(best_k):
        c_shots = shots_mm[labels == i]
        ax.scatter(c_shots[:, 0], c_shots[:, 1],
                   color=palette[i % 5], edgecolor="black", s=80, zorder=5)
        ax.scatter(centers[i, 0], centers[i, 1],
                   color=palette[i % 5], marker="X",
                   s=200, edgecolor="black", zorder=6)

    ax.scatter(0, 0, color="red", marker="+", s=200,
               label="Target centre", zorder=7)
    ax.add_patch(plt.Circle(
        (0, 0), r50_mm,
        color="purple", fill=False, linestyle="--",
        linewidth=2, label=f"CEP {r50_mm:.0f} mm",
    ))

    ax.legend(fontsize=9)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)

    img_report = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), 1)
    cv2.imshow(f"Report: {target_name}", img_report)
    print(f"[{target_name}] Ballistic report displayed.")


# ── Text log ──────────────────────────────────────────────────────────────────

def save_log(frame_idx: int) -> None:
    """Append a hit/score summary for all targets to the log file."""
    with open(CFG.log_file_path, "a", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"--- REPORT {ts}  (frame {frame_idx}) ---\n")
        for name, state in target_states.items():
            with state.lock:
                if not state.confirmed:
                    continue
                coords = [
                    (round(v["pos"][0], 1), round(v["pos"][1], 1))
                    for v in state.confirmed.values()
                ]
                total = state.total_score()
                f.write(
                    f"  {name} | hits: {len(coords)} | "
                    f"score: {total} | centres: {coords}\n"
                )
        f.write("-" * 60 + "\n")
    print(f"  Log written → {CFG.log_file_path}")
