# 🎯 MODULE NHẬN DIỆN VÀ THEO DÕI VẾT ĐẠN

Hệ thống hoạt động theo mô hình **"Nhà máy lọc đạn"** với 1 luồng thu thập và 3 lớp lọc nhiễu nối tiếp nhau chạy độc lập trên các Thread (Worker).

---

## ⚙️ KIẾN TRÚC LUỒNG XỬ LÝ (PIPELINE FLOW)

### 📍 BƯỚC 0: ĐẦU VÀO & TIỀN XỬ LÝ (`main.py` & `worker.py`)
* **Camera đọc frame:** `main.py` dùng ArUco Marker quét 4 góc để nhận diện các bia (Bia Tròn, IPSC, Bia Người).
* **Phân phối:** Đẩy frame vào hàng đợi (Queue).
* **Bẻ phẳng (Warp Perspective):** `worker.py` bóp méo hình ảnh bia về góc nhìn thẳng 90 độ và khởi tạo Nền động (Rolling Background).

### 🛡️ LAYER 1: BẮT BÓNG ĐEN (`layer1.py`)
* **Nhiệm vụ:** Tìm các vật thể lạ xuất hiện trên bia.
* **Cách hoạt động:** Lấy ảnh hiện tại trừ đi ảnh nền, thu được các vết nứt đen. Dùng Morphological để dán các vết nứt do viền bia gây ra thành một cục đen nguyên khối. Lọc sơ bộ bằng độ tròn (Circularity).
* **Đầu ra:** Danh sách các `candidates` (Cục đen thô, có thể là 1 hoặc nhiều viên đạn dính nhau).

### 🔪 LAYER 2: CHUYÊN GIA BÓC TÁCH (`layer2.py`)
* **Nhiệm vụ:** Mổ xẻ các cục đen để tìm ra tọa độ (x, y) chính xác của từng viên đạn, giải quyết bài toán đạn dính chùm.
* **Cách hoạt động:**
  1. Đo diện tích cục đen để ép "Quota" (VD: Cục to gấp 2 -> Phải có 2 viên).
  2. Dùng thuật toán **Hough Circles** để tìm các tâm rõ ràng.
  3. Nếu thiếu tâm, gọi **RANSAC** (tối ưu hóa bằng Numba) bới móc viền cục đen để mò ra tâm còn thiếu.
  4. Dùng **NMS** (Non-Maximum Suppression) chém bỏ các tâm sinh ra quá sát nhau (chống ảo giác).
* **Đầu ra:** Danh sách tọa độ thô `raw_circles` trong frame hiện tại.

### 🎯 LAYER 3: THEO DÕI VÀ CHỐT SỔ (`layer3.py`)
* **Nhiệm vụ:** Cấp ID cho đạn, theo dõi qua từng frame để loại bỏ nhiễu chớp tắt (ruồi muỗi, bóng râm).
* **Cách hoạt động:**
  1. Dùng thuật toán **Hungarian** để ghép cặp đạn cũ - đạn mới giữa các frame.
  2. Đạn mới xuất hiện bị ném vào "Phòng chờ duyệt" (`candidates`). Nếu nó nằm lỳ ở đó liên tục 5-6 frames (`CONFIRM_FRAMES`), nó mới được thăng cấp lên Đạn Thật (`confirmed`).
  3. Đạn thật được làm mượt tọa độ bằng trung bình động (Alpha Smoothing).
* **Đầu ra:** Danh sách `[ID, x, y, r]` cực kỳ ổn định.

---

## 📂 CẤU TRÚC THƯ MỤC

* `config.py`: Chứa các hằng số, kích thước bia, tham số Tuning (Ngưỡng cắt, số lượng frame xác nhận).
* `state.py`: Quản lý biến trạng thái toàn cục (Dict) của các mục tiêu đang Tracking.
* `layer1.py`: Thuật toán trừ nền và xử lý hình thái học.
* `layer2.py`: Thuật toán chia tách đạn dính chùm (Hough, RANSAC, NMS).
* `layer3.py`: Thuật toán gán nhãn ID, bám sát tọa độ và dọn rác (Hungarian Tracking).
* `scoring.py`: Tính điểm dựa trên khoảng cách (Bia tròn) và đa giác (IPSC, Bia người).
* `worker.py`: Xử lý luồng riêng cho từng bia, gọi lần lượt Layer 1-2-3 và render kết quả.
* `main.py`: Chạy camera, detect ArUco và phân phối công việc cho các Worker.

---

## 🚀 CÀI ĐẶT

Sử dụng lệnh sau để cài đặt toàn bộ thư viện cần thiết nhằm đảm bảo đồng nhất phiên bản với hệ thống Backend:
```bash
pip install -r requirements.txt