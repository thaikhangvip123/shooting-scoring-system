import queue
import threading
import time

import cv2
import cv2.aruco as aruco
import numpy as np

from config import *
from evaluation import create_detection_recorder_from_env
from state import app_bg_state, app_tracked_state
from worker import target_worker_thread


if __name__ == "__main__":
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())

    target_sets = {
        "BIA_TRON": [0, 1, 2, 3],
        "BIA_IPSC": [4, 5, 6, 7],
        "BIA_NGUOI": [8, 9, 10, 11],
    }

    recorder = create_detection_recorder_from_env()

    # A size of 1 keeps realtime behavior: if workers lag, old frames are dropped.
    input_queues = {name: queue.Queue(maxsize=1) for name in target_sets}
    output_queue = queue.Queue(maxsize=10)

    for name in target_sets.keys():
        t = threading.Thread(
            target=target_worker_thread,
            args=(
                name,
                app_tracked_state[name],
                app_bg_state,
                input_queues[name],
                output_queue,
                recorder,
            ),
        )
        t.daemon = True
        t.start()

    cap = cv2.VideoCapture(VIDEO_PATH)

    frame_idx = 0
    prev_time = 0
    last_marker_dict = None

    print("Detection system V3 started: Hungarian + Hough + rolling background")
    print(f"ArUco detect every {ARUCO_DETECT_EVERY_N_FRAMES} frame(s)")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        curr_time = time.time()
        fps = 1 / (curr_time - prev_time) if prev_time > 0 else 0
        prev_time = curr_time

        cv2.putText(
            frame,
            f"FPS: {int(fps)}",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 0),
            3,
        )

        if frame_idx % ARUCO_DETECT_EVERY_N_FRAMES == 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray_small)

            if ids is not None:
                last_marker_dict = {
                    ids[i][0]: corners[i][0] * 2
                    for i in range(len(ids))
                }

        if last_marker_dict is not None:
            marker_dict = last_marker_dict

            for target_name, id_set in target_sets.items():
                if all(mid in marker_dict for mid in id_set):
                    tl, tr, bl, br = id_set

                    src_pts = np.array([
                        marker_dict[tl][0],
                        marker_dict[tr][1],
                        marker_dict[br][2],
                        marker_dict[bl][3],
                    ], dtype=np.float32)

                    try:
                        if input_queues[target_name].full():
                            input_queues[target_name].get_nowait()

                        input_queues[target_name].put_nowait(
                            (frame, src_pts, frame_idx)
                        )
                    except queue.Empty:
                        pass
                    except queue.Full:
                        pass

        cv2.imshow(
            "0. Camera Chinh (Main View)",
            cv2.resize(frame, (800, 450)),
        )

        try:
            while True:
                t_name, warped_res = output_queue.get_nowait()
                cv2.imshow(f"Scoring: {t_name}", warped_res)
        except queue.Empty:
            pass

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for q in input_queues.values():
        q.put(None)

    cap.release()
    cv2.destroyAllWindows()
