Có 2 file DetectBullet và FullPipeline

DetectBullet là để chạy riêng rẻ từng video của từng loại bia để test module detect vết đạn.
FullPipeline là tích hợp thêm phần scoring và visual vào, đặc biệt có thể detect 1 lúc 3 loại bia cùng 1 lúc ( chạy video target.mp4), có thể chạy hơi lâu do chưa tối ưu thuật toán.

Cài thư viện 

pip install opencv-contrib-python numpy matplotlib seaborn scikit-learn

Nhớ sửa lại các đường dẫn cần thiết