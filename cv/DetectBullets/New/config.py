import numpy as np

# --- THAY ĐỔI BASE_DIR THÀNH ĐƯỜNG DẪN CỦA BẠN ---
BASE_DIR = "D:/baitapxaml/HK252/DATN" 

VIDEO_PATH = f"{BASE_DIR}/DetectBullet/target2.mp4"

PATH_IPSC_POLY = f"{BASE_DIR}/Main/shooting-scoring-system/cv/Scoring/IPSC/polygon.txt"
PATH_NGUOI_CONT = f"{BASE_DIR}/Main/shooting-scoring-system/cv/Scoring/Nguoi/Nguoi_contours.txt"

# Kích thước và Tọa độ
WIDTH, HEIGHT = 1240, 1754
SCALE_FACTOR = 2480 / WIDTH
MARGIN = 40
EXPECTED_RADIUS = 21  

dst_points = np.array([
    [MARGIN, MARGIN], 
    [WIDTH - MARGIN, MARGIN], 
    [WIDTH - MARGIN, HEIGHT - MARGIN], 
    [MARGIN, HEIGHT - MARGIN]
], dtype=np.float32)

# --- THÔNG SỐ TỐI ƯU MỚI ---
CIRCULARITY_THRESH = 0.6  # Chuẩn độ tròn mới (Bỏ qua overlap)
CONFIRM_FRAMES = 3         # Số frame liên tiếp để xác nhận đạn
STALE_FRAMES = 10          # Frame chờ trước khi xóa candidate
FORGET_FRAMES = 30         # Frame chờ trước khi xóa confirmed
MATCH_DIST = 20            # Bán kính tìm kiếm ghép cặp (Hungarian)
BG_ALPHA = 0.05            # Tốc độ học nền mới (Rolling BG)