# Biến dùng chung để lưu trạng thái đạn và nền động
app_tracked_state = {
    "BIA_TRON": {"candidates": {}, "confirmed": {}, "next_id": 0, "prev_gray": None},
    "BIA_IPSC": {"candidates": {}, "confirmed": {}, "next_id": 0, "prev_gray": None},
    "BIA_NGUOI": {"candidates": {}, "confirmed": {}, "next_id": 0, "prev_gray": None}
}
app_bg_state = {"BIA_TRON": None, "BIA_IPSC": None, "BIA_NGUOI": None}


def reset_target_state(target_name):
    state = app_tracked_state[target_name]
    state["candidates"].clear()
    state["confirmed"].clear()
    state["next_id"] = 0
    state["prev_gray"] = None
    app_bg_state[target_name] = None


def reset_all_detection_state():
    for target_name in app_tracked_state:
        reset_target_state(target_name)
