"""
main.py — Entry point for the shooting scoring system.

Usage:
    python main.py

Key bindings:
    [a]  Ballistic report — BIA_TRON
    [b]  Ballistic report — BIA_IPSC
    [c]  Ballistic report — BIA_NGUOI
    [s]  Save text log
    [r]  Reset all background models (use after lighting change)
    [d]  Toggle debug overlay (shows dark-diff mask)
    [q]  Quit
"""

import time
from concurrent.futures import ThreadPoolExecutor

import cv2

from config import CFG, TARGET_SETS
from state import target_states
from aruco_utils import detect_markers
from worker import process_target
from report import generate_visual_report, save_log


def reset_all_backgrounds() -> None:
    """Clear background model and homography cache for every target."""
    for st in target_states.values():
        with st.lock:
            st.bg_float      = None
            st.noise_ready   = False
            st.warmup_diffs  = []
            st.warmup_count  = 0
            st.H_cached      = None
            st.H_src_prev    = None
    print("  All background models reset.")


def main() -> None:
    cap = cv2.VideoCapture(CFG.video_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {CFG.video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"  Video: {CFG.video_path}  ({fps:.1f} fps)")
    print("  Keys: [a] Report Tron  [b] Report IPSC  [c] Report Nguoi")
    print("        [s] Save log  [r] Reset BG  [d] Debug mask  [q] Quit")

    executor  = ThreadPoolExecutor(max_workers=3)
    frame_idx = 0
    show_debug = False

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        now = time.monotonic()

        # ── ArUco detection ───────────────────────────────────────────────────
        marker_dict = detect_markers(frame)

        # ── Camera preview ────────────────────────────────────────────────────
        preview = cv2.resize(
            frame,
            (min(800, frame.shape[1]), min(450, frame.shape[0])),
        )
        # Overlay which markers were found
        if marker_dict:
            ids_found = sorted(marker_dict.keys())
            cv2.putText(preview, f"Markers: {ids_found}",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2)
        cv2.imshow("Camera", preview)

        # ── Submit per-target workers ─────────────────────────────────────────
        for target_name, id_set in TARGET_SETS.items():
            if all(mid in marker_dict for mid in id_set):
                executor.submit(
                    process_target,
                    target_name,
                    frame.copy(),
                    marker_dict.copy(),
                    frame_idx,
                    now,
                )

        # ── Display latest processed frames ───────────────────────────────────
        for name, state in target_states.items():
            if state.display_frame is not None:
                win_title = f"Result: {name}"
                cv2.imshow(win_title, state.display_frame)

                # Optional: show dark-diff debug overlay in a separate window
                if show_debug:
                    with state.lock:
                        bg_u8 = state.get_bg_u8()
                    if bg_u8 is not None:
                        cv2.imshow(f"BG: {name}",
                                   cv2.resize(bg_u8, (0, 0),
                                              fx=CFG.display_scale,
                                              fy=CFG.display_scale))

        # ── Key handling ──────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if   key == ord("q"):
            break
        elif key == ord("s"):
            save_log(frame_idx)
        elif key == ord("a"):
            generate_visual_report("BIA_TRON")
        elif key == ord("b"):
            generate_visual_report("BIA_IPSC")
        elif key == ord("c"):
            generate_visual_report("BIA_NGUOI")
        elif key == ord("d"):
            show_debug = not show_debug
            print(f"  Debug overlay {'ON' if show_debug else 'OFF'}")
        elif key == ord("r"):
            reset_all_backgrounds()

    executor.shutdown(wait=False)
    cap.release()
    cv2.destroyAllWindows()
    print("  Pipeline stopped.")


if __name__ == "__main__":
    main()
