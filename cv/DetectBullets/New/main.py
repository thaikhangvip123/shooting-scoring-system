import cv2
import cv2.aruco as aruco
import numpy as np
import queue
import threading
import time

from config import *
from state import app_tracked_state, app_bg_state
from worker import target_worker_thread

if __name__ == '__main__':
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
    target_sets = {"BIA_TRON": [0,1,2,3], "BIA_IPSC": [4,5,6,7], "BIA_NGUOI": [8,9,10,11]}

    input_queues = {name: queue.Queue(maxsize=2) for name in target_sets}
    output_queue = queue.Queue(maxsize=10)

    for name in target_sets.keys():
        t = threading.Thread(
            target=target_worker_thread, 
            args=(name, app_tracked_state[name], app_bg_state, input_queues[name], output_queue)
        )
        t.daemon = True
        t.start()

    cap = cv2.VideoCapture(VIDEO_PATH)
    frame_idx = 0; prev_time = 0
    
    print("🚀 HỆ THỐNG V3 (HUNGARIAN + HOUGH + ROLLING BG) ĐÃ KHỞI ĐỘNG!")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame_idx += 1
        
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time) if prev_time > 0 else 0
        prev_time = curr_time
        
        cv2.putText(frame, f"FPS: {int(fps)}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        
        # Tối ưu ArUco quét siêu tốc
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray_small)
        
        cv2.imshow("0. Camera Chinh (Main View)", cv2.resize(frame, (800, 450)))

        if ids is not None:
            marker_dict = {ids[i][0]: corners[i][0] * 2 for i in range(len(ids))}

            for target_name, id_set in target_sets.items():
                if all(mid in marker_dict for mid in id_set):
                    TL, TR, BL, BR = id_set
                    src_pts = np.array([marker_dict[TL][0], marker_dict[TR][1], marker_dict[BR][2], marker_dict[BL][3]], dtype=np.float32)
                    try:
                        if input_queues[target_name].full(): input_queues[target_name].get_nowait()
                        input_queues[target_name].put_nowait((frame, src_pts, frame_idx))
                    except: pass

        try:
            for _ in range(3):
                t_name, warped_res = output_queue.get_nowait()
                cv2.imshow(f"Scoring: {t_name}", warped_res)
        except queue.Empty: pass

        if cv2.waitKey(1) & 0xFF == ord('q'): break

    for q in input_queues.values(): q.put(None)
    cap.release()
    cv2.destroyAllWindows()