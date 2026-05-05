# Biến dùng chung để lưu trạng thái đạn và nền động
app_tracked_state = {
    "BIA_TRON": {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_IPSC": {"candidates": {}, "confirmed": {}, "next_id": 0},
    "BIA_NGUOI": {"candidates": {}, "confirmed": {}, "next_id": 0}
}
app_bg_state = {"BIA_TRON": None, "BIA_IPSC": None, "BIA_NGUOI": None}