import cv2
import cv2.aruco as aruco
import numpy as np
import queue
import threading
import time

from config import *
from control import get_mode, is_target_active, start_control_listener
from state import app_tracked_state, app_bg_state
from worker import target_worker_thread


if __name__ == '__main__':
    cv2.setNumThreads(CV2_NUM_THREADS)
    start_control_listener(app_tracked_state, app_bg_state)

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())

    target_sets = {
        "BIA_TRON": [0, 1, 2, 3],
        "BIA_IPSC": [4, 5, 6, 7],
        "BIA_NGUOI": [8, 9, 10, 11]
    }

    # Queue maxsize=1 giúp realtime hơn: nếu worker chậm thì bỏ frame cũ
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
                output_queue
            )
        )
        t.daemon = True
        t.start()

    cap = cv2.VideoCapture(VIDEO_PATH)

    frame_idx = 0
    prev_time = 0

    # Lưu marker gần nhất để không cần detect ArUco mỗi frame
    last_marker_dict = None

    print("🚀 HỆ THỐNG V3 (HUNGARIAN + HOUGH + ROLLING BG) ĐÃ KHỞI ĐỘNG!")
    print(f"⚡ ArUco detect every {ARUCO_DETECT_EVERY_N_FRAMES} frame(s)")

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
            3
        )

        # =========================================================
        # 1. CHỈ DETECT ARUCO MỖI N FRAME
        # =========================================================
        if frame_idx % ARUCO_DETECT_EVERY_N_FRAMES == 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

            corners, ids, rejected = detector.detectMarkers(gray_small)

            if ids is not None:
                last_marker_dict = {
                    ids[i][0]: corners[i][0] * 2
                    for i in range(len(ids))
                }

        # =========================================================
        # 2. DÙNG LẠI MARKER GẦN NHẤT ĐỂ XỬ LÝ TARGET
        # =========================================================
        if get_mode() == "SHOOTING" and last_marker_dict is not None:
            marker_dict = last_marker_dict

            for target_name, id_set in target_sets.items():
                if not is_target_active(target_name):
                    continue

                if all(mid in marker_dict for mid in id_set):
                    TL, TR, BL, BR = id_set

                    src_pts = np.array([
                        marker_dict[TL][0],  # top-left marker corner
                        marker_dict[TR][1],  # top-right marker corner
                        marker_dict[BR][2],  # bottom-right marker corner
                        marker_dict[BL][3]   # bottom-left marker corner
                    ], dtype=np.float32)

                    try:
                        # Nếu queue đầy thì bỏ frame cũ để giữ realtime
                        if input_queues[target_name].full():
                            input_queues[target_name].get_nowait()

                        input_queues[target_name].put_nowait(
                            (frame, src_pts, frame_idx)
                        )

                    except queue.Empty:
                        pass

                    except queue.Full:
                        pass

        # =========================================================
        # 3. HIỂN THỊ CAMERA CHÍNH
        # =========================================================
        cv2.imshow(
            "0. Camera Chinh (Main View)",
            cv2.resize(frame, (800, 450))
        )

        # =========================================================
        # 4. LẤY OUTPUT TỪ WORKER ĐỂ HIỂN THỊ
        # =========================================================
        try:
            while True:
                t_name, warped_res = output_queue.get_nowait()
                cv2.imshow(f"Scoring: {t_name}", warped_res)

        except queue.Empty:
            pass

        # Nhấn q để thoát
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Dừng worker
    for q in input_queues.values():
        q.put(None)

    cap.release()
    cv2.destroyAllWindows()
