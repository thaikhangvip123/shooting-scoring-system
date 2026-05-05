import numpy as np
import math
from scipy.optimize import linear_sum_assignment
from config import *

def tracking_hungarian(state, raw_circles, frame_idx):
    # Gộp tất cả id đang theo dõi (cả candidates và confirmed)
    tracked_items = {}
    for cid, data in state["candidates"].items(): tracked_items[cid] = data
    for cid, data in state["confirmed"].items(): tracked_items[cid] = data
    
    tracked_ids = list(tracked_items.keys())
    
    if len(tracked_ids) == 0 or len(raw_circles) == 0:
        matches = []
        unmatched_raw = list(range(len(raw_circles)))
    else:
        # TẠO MA TRẬN CHI PHÍ (Cost Matrix)
        cost_matrix = np.zeros((len(tracked_ids), len(raw_circles)), dtype=np.float32)
        for i, tid in enumerate(tracked_ids):
            ox, oy = tracked_items[tid]["pos"]
            for j, (nx, ny, _) in enumerate(raw_circles):
                dist = math.sqrt((nx - ox)**2 + (ny - oy)**2)
                # Phạt Vô cực nếu 2 điểm quá xa nhau -> Không cho ghép cặp
                cost_matrix[i, j] = dist if dist < MATCH_DIST else 999999
                
        # THUẬT TOÁN HUNGARIAN XẾP CẶP TỐI ƯU TOÀN CỤC
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        
        matches = []
        unmatched_raw = set(range(len(raw_circles)))
        for i, j in zip(row_ind, col_ind):
            if cost_matrix[i, j] < MATCH_DIST:
                matches.append((tracked_ids[i], j))
                unmatched_raw.remove(j)
        unmatched_raw = list(unmatched_raw)

    # 1. Cập nhật các cặp đã ghép thành công
    for tid, raw_idx in matches:
        nx, ny, r = raw_circles[raw_idx]
        if tid in state["candidates"]:
            ox, oy = state["candidates"][tid]["pos"]
            state["candidates"][tid]["pos"] = (ox*0.5 + nx*0.5, oy*0.5 + ny*0.5)
            state["candidates"][tid]["last_frame"] = frame_idx
            state["candidates"][tid]["count"] += 1
            if state["candidates"][tid]["count"] >= CONFIRM_FRAMES:
                state["confirmed"][tid] = state["candidates"].pop(tid)
        elif tid in state["confirmed"]:
            ox, oy = state["confirmed"][tid]["pos"]
            state["confirmed"][tid]["pos"] = (ox*0.8 + nx*0.2, oy*0.8 + ny*0.2) # Alpha mượt
            state["confirmed"][tid]["last_frame"] = frame_idx

    # 2. Tạo ID mới cho các viên đạn không ghép được (Đạn dính chùm mới)
    for raw_idx in unmatched_raw:
        nx, ny, r = raw_circles[raw_idx]
        new_id = state["next_id"]; state["next_id"] += 1
        state["candidates"][new_id] = {"pos": (nx, ny), "r": r, "count": 1, "last_frame": frame_idx}

    # 3. Dọn rác
    stale_c = [k for k, v in state["candidates"].items() if frame_idx - v["last_frame"] > STALE_FRAMES]
    for k in stale_c: del state["candidates"][k]
    stale_cf = [k for k, v in state["confirmed"].items() if frame_idx - v["last_frame"] > FORGET_FRAMES]
    for k in stale_cf: del state["confirmed"][k]

    return [(k, v["pos"][0], v["pos"][1], v["r"]) for k, v in state["confirmed"].items()]