import argparse
import queue
import threading
import time

import cv2
import cv2.aruco as aruco
import numpy as np

from evaluation import create_detection_recorder_from_env
from state import app_bg_state, app_tracked_state
from worker import target_worker_thread


TARGET_SETS = {
    "BIA_TRON": [0, 1, 2, 3],
    "BIA_IPSC": [4, 5, 6, 7],
    "BIA_NGUOI": [8, 9, 10, 11],
}
MAIN_WINDOW_NAME = "0. NDI Stream - Detection Input"


def parse_args():
    parser = argparse.ArgumentParser(description="Realtime NDI bullet detection")
    parser.add_argument(
        "--ndi-index",
        type=int,
        default=None,
        help="NDI source index. If omitted, the program prints sources and asks you to choose.",
    )
    parser.add_argument(
        "--ndi-name",
        default="",
        help="Select the first NDI source whose name contains this text.",
    )
    parser.add_argument(
        "--ndi-timeout-ms",
        type=int,
        default=5000,
        help="Timeout while waiting for each NDI frame.",
    )
    parser.add_argument(
        "--source-wait-ms",
        type=int,
        default=1000,
        help="Wait interval while searching for NDI sources.",
    )
    parser.add_argument(
        "--video",
        default="",
        help="Optional video file for offline testing.",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=None,
        help="Optional physical camera index for direct webcam testing.",
    )
    parser.add_argument("--width", type=int, default=0, help="Optional camera capture width.")
    parser.add_argument("--height", type=int, default=0, help="Optional camera capture height.")
    parser.add_argument(
        "--input-scale",
        type=float,
        default=1.0,
        help="Upscale frames before detection. Try 1.5 or 2.0 if the NDI feed is small.",
    )
    parser.add_argument(
        "--detect-scale",
        type=float,
        default=1.0,
        help="Scale used only for ArUco detection. 1.0 keeps full input resolution.",
    )
    parser.add_argument("--sharpen", action="store_true", help="Apply mild sharpening before detection.")
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable the main input preview window.",
    )
    return parser.parse_args()


class CvVideoSource:
    def __init__(self, cap, source_label, drop_camera_buffer=False):
        self.cap = cap
        self.source_label = source_label
        self.drop_camera_buffer = drop_camera_buffer

    def is_opened(self):
        return self.cap.isOpened()

    def read(self):
        if self.drop_camera_buffer:
            for _ in range(3):
                if not self.cap.grab():
                    return False, None
            return self.cap.retrieve()
        return self.cap.read()

    def release(self):
        self.cap.release()


class NdiSource:
    def __init__(self, args):
        try:
            import NDIlib as ndi
        except ImportError as exc:
            raise RuntimeError("NDIlib is required for NDI input. Install the NDI Python package in this environment.") from exc

        self.ndi = ndi
        self.finder = None
        self.receiver = None
        self.source_label = "NDI"
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.printed_resolution = False
        self.timeout_ms = args.ndi_timeout_ms

        if not self.ndi.initialize():
            raise RuntimeError("Cannot initialize NDI")

        self.finder = self.ndi.find_create_v2()
        sources = self._wait_for_sources(args.source_wait_ms)
        selected_source = self._select_source(sources, args.ndi_index, args.ndi_name)

        recv_create = self.ndi.RecvCreateV3()
        recv_create.color_format = self.ndi.RECV_COLOR_FORMAT_BGRX_BGRA
        if hasattr(self.ndi, "RECV_BANDWIDTH_HIGHEST"):
            recv_create.bandwidth = self.ndi.RECV_BANDWIDTH_HIGHEST

        self.receiver = self.ndi.recv_create_v3(recv_create)
        self.ndi.recv_connect(self.receiver, selected_source)
        self.source_label = selected_source.ndi_name

    def _wait_for_sources(self, wait_ms):
        print("Dang tim nguon NDI...")
        sources = []
        while not sources:
            self.ndi.find_wait_for_sources(self.finder, wait_ms)
            sources = self.ndi.find_get_current_sources(self.finder)
        print("\nNguon NDI tim thay:")
        for index, source in enumerate(sources):
            print(f"{index}: {source.ndi_name}")
        return sources

    def _select_source(self, sources, source_index, source_name):
        if source_name:
            source_name = source_name.lower()
            for source in sources:
                if source_name in source.ndi_name.lower():
                    return source
            raise RuntimeError(f"No NDI source name contains: {source_name}")

        if source_index is None:
            source_index = int(input("\nChon so nguon NDI: "))

        if source_index < 0 or source_index >= len(sources):
            raise RuntimeError(f"NDI source index out of range: {source_index}")
        return sources[source_index]

    def is_opened(self):
        return self.receiver is not None

    def read(self):
        while True:
            frame_type, video_frame, audio_frame, metadata = self.ndi.recv_capture_v2(self.receiver, self.timeout_ms)
            if frame_type == self.ndi.FRAME_TYPE_VIDEO:
                try:
                    frame = np.copy(video_frame.data)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                finally:
                    self.ndi.recv_free_video_v2(self.receiver, video_frame)
                self._print_stats(frame)
                return True, frame

            if frame_type == self.ndi.FRAME_TYPE_NONE:
                print("Khong nhan duoc frame NDI...")
                return False, None

            if frame_type == self.ndi.FRAME_TYPE_AUDIO:
                self.ndi.recv_free_audio_v2(self.receiver, audio_frame)

    def _print_stats(self, frame):
        if not self.printed_resolution:
            height, width = frame.shape[:2]
            print(f"Resolution nhan duoc: {width}x{height}")
            self.printed_resolution = True

        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 1:
            print(f"FPS nhan duoc: {self.frame_count}")
            self.frame_count = 0
            self.last_fps_time = now

    def release(self):
        if self.receiver is not None:
            self.ndi.recv_destroy(self.receiver)
            self.receiver = None
        if self.finder is not None:
            self.ndi.find_destroy(self.finder)
            self.finder = None
        self.ndi.destroy()


def open_source(args):
    if args.video:
        cap = cv2.VideoCapture(args.video)
        source = CvVideoSource(cap, args.video)
    elif args.camera is not None:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        source_label = f"camera:{args.camera}"
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if args.width > 0:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        if args.height > 0:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        source = CvVideoSource(cap, source_label, drop_camera_buffer=True)
    else:
        source = NdiSource(args)

    if not source.is_opened():
        raise RuntimeError(f"Cannot open input source: {source.source_label}")
    return source


def preprocess_frame(frame, args):
    if args.input_scale <= 0:
        raise ValueError("--input-scale must be greater than 0")
    if args.input_scale != 1.0:
        interpolation = cv2.INTER_CUBIC if args.input_scale > 1.0 else cv2.INTER_AREA
        frame = cv2.resize(frame, (0, 0), fx=args.input_scale, fy=args.input_scale, interpolation=interpolation)
    if args.sharpen:
        blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
        frame = cv2.addWeighted(frame, 1.6, blurred, -0.6, 0)
    return frame


def detect_aruco(detector, frame, detect_scale):
    if detect_scale <= 0:
        raise ValueError("--detect-scale must be greater than 0")
    detect_frame = frame
    if detect_scale != 1.0:
        interpolation = cv2.INTER_CUBIC if detect_scale > 1.0 else cv2.INTER_AREA
        detect_frame = cv2.resize(frame, (0, 0), fx=detect_scale, fy=detect_scale, interpolation=interpolation)

    gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
    if corners is not None and detect_scale != 1.0:
        corners = [corner / detect_scale for corner in corners]
    return corners, ids, rejected


def replace_queue_item(q, item):
    try:
        if q.full():
            q.get_nowait()
        q.put_nowait(item)
    except queue.Full:
        pass


def main():
    args = parse_args()
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
    recorder = create_detection_recorder_from_env()

    input_queues = {name: queue.Queue(maxsize=1) for name in TARGET_SETS}
    output_queue = queue.Queue(maxsize=len(TARGET_SETS))
    latest_outputs = {name: None for name in TARGET_SETS}

    for name in TARGET_SETS:
        thread = threading.Thread(
            target=target_worker_thread,
            args=(name, app_tracked_state[name], app_bg_state, input_queues[name], output_queue, recorder),
            daemon=True,
        )
        thread.start()

    source = open_source(args)
    if not args.no_preview:
        cv2.namedWindow(MAIN_WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(MAIN_WINDOW_NAME, 1920, 1080)

    frame_idx = 0
    prev_time = 0
    print(f"\nDang nhan tu: {source.source_label}")
    print("Nhan Q de thoat.")

    try:
        while source.is_opened():
            ret, frame = source.read()
            if not ret:
                continue

            frame = preprocess_frame(frame, args)
            frame_idx += 1

            curr_time = time.time()
            fps = 1 / (curr_time - prev_time) if prev_time > 0 else 0
            prev_time = curr_time

            cv2.putText(frame, f"FPS: {int(fps)}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            corners, ids, _ = detect_aruco(detector, frame, args.detect_scale)

            if not args.no_preview:
                cv2.imshow(MAIN_WINDOW_NAME, frame)

            if ids is not None:
                marker_dict = {ids[i][0]: corners[i][0] for i in range(len(ids))}
                for target_name, id_set in TARGET_SETS.items():
                    if all(marker_id in marker_dict for marker_id in id_set):
                        top_left, top_right, bottom_left, bottom_right = id_set
                        src_pts = np.array(
                            [
                                marker_dict[top_left][0],
                                marker_dict[top_right][1],
                                marker_dict[bottom_right][2],
                                marker_dict[bottom_left][3],
                            ],
                            dtype=np.float32,
                        )
                        replace_queue_item(input_queues[target_name], (frame, src_pts, frame_idx))

            try:
                while True:
                    target_name, warped_result = output_queue.get_nowait()
                    latest_outputs[target_name] = warped_result
            except queue.Empty:
                pass

            for target_name, warped_result in latest_outputs.items():
                if warped_result is not None:
                    cv2.imshow(f"Scoring: {target_name}", warped_result)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        for q in input_queues.values():
            replace_queue_item(q, None)
        source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
