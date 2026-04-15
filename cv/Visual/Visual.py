import cv2
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ==========================================
# 1. ĐỌC ẢNH VÀ THIẾT LẬP HỆ TỌA ĐỘ (mm)
# ==========================================
image_path = 'D:/baitapxaml/HK252/DATN/A4_Tron2.png' #Sửa lại đường dẫn cho loại bia
img_bgr = cv2.imread(image_path)
if img_bgr is None:
    print(f"Lỗi: Không tìm thấy file {image_path}. Vui lòng kiểm tra lại đường dẫn!")
    exit()

h_p, w_p, _ = img_bgr.shape
img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

# Thiết lập hệ quy chiếu dựa trên chiều rộng giấy A4 (210mm)
width_mm = 210.0
height_mm = h_p / (w_p / width_mm) 
pixels_per_mm = w_p / width_mm
mm_per_pixel = 1.0 / pixels_per_mm

# Đặt tâm bia chính xác ở giữa bức ảnh
center_p = (int(w_p / 2), int(h_p / 2))

# ==========================================
# 2. GIẢ LẬP BẮN SÚNG (Bắn tự nhiên 1 lượt 30 viên)
# ==========================================
num_shots = 30
# Không cố định seed để mỗi lần chạy bạn sẽ thấy một kịch bản đạn văng khác nhau
# np.random.seed(42) 

# Xạ thủ nhắm vào tâm (0,0) và nã liên tục 30 viên.
# Độ rung tay tự nhiên làm đạn tản mát quanh tâm với sai số khoảng 25mm.
# Giả sử xạ thủ có thói quen bóp cò hơi giật sang phải (+10mm) và chếch lên (+5mm)
shots_x = np.random.normal(loc=10, scale=25, size=num_shots)
shots_y = np.random.normal(loc=5, scale=25, size=num_shots)

shots_mm = np.column_stack((shots_x, shots_y))

# Chuyển tọa độ đạn (mm) ra (pixel) để vẽ lên ảnh gốc test thử
shots_pixels = np.column_stack((center_p[0] + (shots_mm[:,0] * pixels_per_mm),
                                 center_p[1] - (shots_mm[:,1] * pixels_per_mm))).astype(np.int32)

# Vẽ chấm đạn xanh đơn giản lên ảnh gốc 
img_with_shots_p = img_bgr.copy()
for shot_p in shots_pixels:
    cv2.circle(img_with_shots_p, tuple(shot_p), 8, (0, 255, 0), -1) 

# ==========================================
# 3. THUẬT TOÁN PHÂN TÍCH ĐẠN ĐẠO (AI AUTO-DETECT)
# ==========================================
# [CHỈ SỐ 1 & 2]: Sai lệch xuyên tâm (MRE) và Độ chụm (CEP/R50)
distances = np.linalg.norm(shots_mm, axis=1)
mre_mm = np.mean(distances)
r50_mm = np.median(distances)

# [CHỈ SỐ 3]: TỰ ĐỘNG PHÂN CỤM (AUTO K-MEANS + SILHOUETTE SCORE)
max_k = min(5, len(shots_mm) - 1) # Giới hạn test tối đa 5 cụm đạn
best_k = 1
best_score = -1

# AI bắt đầu chạy thử nghiệm để tìm ra số nhóm đạn hợp lý nhất
if len(shots_mm) >= 3:
    for k in range(2, max_k + 1):
        kmeans_temp = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels_temp = kmeans_temp.fit_predict(shots_mm)
        score = silhouette_score(shots_mm, labels_temp)
        
        if score > best_score:
            best_score = score
            best_k = k

# Ngưỡng chặn: Nếu đạn quá rời rạc (score < 0.4), AI quyết định gộp tất cả thành 1 nhóm duy nhất
if best_score < 0.40:
    best_k = 1
    best_score = 0.0

print(f"\n🤖 AI K-Means Nhận diện: Xạ thủ bắn thành {best_k} nhóm (Độ tự tin Silhouette: {best_score:.2f})")
print(f"📊 MRE: {mre_mm:.1f}mm | CEP(R50): {r50_mm:.1f}mm")

# Chốt số lượng cụm (best_k) và tiến hành phân cụm lần cuối
kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
shot_labels = kmeans.fit_predict(shots_mm)
cluster_centers = kmeans.cluster_centers_

# ==========================================
# 4. TRỰC QUAN HÓA BÁO CÁO (HEATMAP & C50)
# ==========================================
fig, ax = plt.subplots(figsize=(10, 10))
ax.set_title(f"BÁO CÁO ĐẠN ĐẠO: MRE: {mre_mm:.1f}mm | CEP(R50): {r50_mm:.1f}mm\nPhát hiện: {best_k} nhóm đạn", fontsize=14, fontweight='bold')

# Thiết lập giới hạn khung vẽ khớp với kích thước thật của giấy (đơn vị mm)
cartesian_xmin = -(center_p[0] * mm_per_pixel)
cartesian_xmax = (w_p - center_p[0]) * mm_per_pixel
cartesian_ymin = -(h_p - center_p[1]) * mm_per_pixel
cartesian_ymax = center_p[1] * mm_per_pixel

ax.imshow(img_rgb, extent=[cartesian_xmin, cartesian_xmax, cartesian_ymin, cartesian_ymax], alpha=0.9)

# [CHỈ SỐ 4]: Vẽ Heatmap (Mật độ phân bố)
sns.kdeplot(x=shots_mm[:, 0], y=shots_mm[:, 1], fill=True, cmap="Reds", alpha=0.3, thresh=0.05, ax=ax, zorder=7)

# Bảng màu cho tối đa 5 nhóm đạn
color_palette = ['#00FFFF', '#FFFF00', '#FF00FF', '#00FF00', '#FFA500'] 

for i in range(best_k):
    cluster_shots = shots_mm[shot_labels == i]
    # Vẽ đạn của từng nhóm
    ax.scatter(cluster_shots[:, 0], cluster_shots[:, 1], color=color_palette[i % len(color_palette)], edgecolor='black', s=80, zorder=8, label=f'Nhóm đạn {i+1}')
    # Vẽ tâm tác động của từng nhóm (dấu X)
    ax.scatter(cluster_centers[i, 0], cluster_centers[i, 1], color=color_palette[i % len(color_palette)], marker='X', s=250, edgecolor='black', zorder=10)

# Vẽ Vòng R50/CEP & Tâm bia chính
ax.scatter(0, 0, color='red', marker='+', s=200, zorder=9, label='Tâm bia chuẩn')
circle_r50 = plt.Circle((0, 0), r50_mm, color='purple', fill=False, linestyle='--', linewidth=3, zorder=9, label=f'Vòng CEP/R50 ({r50_mm:.1f}mm)')
ax.add_patch(circle_r50)

# Hiển thị chú giải và căn chỉnh lưới
ax.legend(loc='upper right', framealpha=0.9)
ax.set_xlim(cartesian_xmin, cartesian_xmax)
ax.set_ylim(cartesian_ymin, cartesian_ymax)
ax.set_aspect('equal', adjustable='box') 
ax.set_xlabel("Trục X (Cartesian mm)")
ax.set_ylabel("Trục Y (Cartesian mm)")
plt.grid(True, linestyle=':', alpha=0.6)

# ==========================================
# 5. XUẤT FILE BASE64 & HIỂN THỊ LÊN MÀN HÌNH
# ==========================================
buf = io.BytesIO()
plt.savefig(buf, format='png', bbox_inches='tight')
buf.seek(0)
plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
plt.close() 

# Lưu chuỗi Base64 thành file ảnh để kiểm tra
with open("kq_bia_nguoi_analysis.png", "wb") as fh:
    fh.write(base64.b64decode(plot_url))

print("✅ Đã xử lý xong và tạo file ảnh báo cáo: kq_bia_nguoi_analysis.png")

# Hiển thị bằng OpenCV để trực quan
cv2.imshow("1. Anh Bia Goc (Moc Data)", img_with_shots_p)
kq_anal_img = cv2.imread("kq_bia_nguoi_analysis.png")
cv2.imshow("2. Bao Cao Phan Tich Chuyen Sau (AI Auto-Detect)", kq_anal_img)

cv2.waitKey(0)
cv2.destroyAllWindows()