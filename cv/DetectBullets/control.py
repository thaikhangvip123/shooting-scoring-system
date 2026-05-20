import json
import threading
import time

from config import BACKEND_HTTP_URL, BACKEND_WS_URL

try:
    import requests
except ImportError:
    requests = None

try:
    import websocket
except ImportError:
    websocket = None


control_state = {
    "mode": "IDLE",
    "active_target": None,
    "session": None,
}
lock = threading.Lock()


def get_mode():
    with lock:
        return control_state["mode"]


def is_target_active(target_name):
    with lock:
        return (
            control_state["mode"] == "SHOOTING"
            and control_state["active_target"] == target_name
        )


def start_session(target_name, session=None):
    with lock:
        control_state["mode"] = "SHOOTING"
        control_state["active_target"] = target_name
        control_state["session"] = session
    print(f"[CV control] Started session for {target_name}")


def complete_session(session=None):
    with lock:
        control_state["mode"] = "COMPLETE"
        control_state["session"] = session
    print("[CV control] Session complete; detection paused")


def reset_cv_state(app_tracked_state, app_bg_state):
    for state in app_tracked_state.values():
        state["candidates"].clear()
        state["confirmed"].clear()
        state["next_id"] = 0
        state["prev_gray"] = None

    for target_name in app_bg_state:
        app_bg_state[target_name] = None


def reset_control(app_tracked_state, app_bg_state, session=None):
    reset_cv_state(app_tracked_state, app_bg_state)
    with lock:
        control_state["mode"] = "IDLE"
        control_state["active_target"] = None
        control_state["session"] = session
    print("[CV control] Reset state; waiting for Start Session")


def _handle_message(message, app_tracked_state, app_bg_state):
    msg_type = message.get("type")
    if msg_type == "cv_start":
        target_name = message.get("target") or "BIA_TRON"
        reset_cv_state(app_tracked_state, app_bg_state)
        start_session(target_name, message.get("session"))
    elif msg_type == "session_reset":
        reset_control(app_tracked_state, app_bg_state, message.get("session"))
    elif msg_type == "session_completed":
        complete_session(message.get("session"))


def connect_control_ws(app_tracked_state, app_bg_state):
    if websocket is None:
        print("[CV control] Missing websocket-client package; dashboard control disabled")
        return

    def on_message(_ws, raw_message):
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        _handle_message(message, app_tracked_state, app_bg_state)

    def on_error(_ws, error):
        print(f"[CV control] WebSocket error: {error}")

    def on_close(_ws, _status_code, _message):
        print("[CV control] WebSocket closed")

    while True:
        try:
            ws = websocket.WebSocketApp(
                BACKEND_WS_URL,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever()
        except Exception as exc:
            print(f"[CV control] WebSocket reconnect after error: {exc}")
        time.sleep(2)


def start_control_listener(app_tracked_state, app_bg_state):
    thread = threading.Thread(
        target=connect_control_ws,
        args=(app_tracked_state, app_bg_state),
        daemon=True,
    )
    thread.start()
    return thread


def post_shot_to_backend(target_name, bullet_id, cx, cy, score, scale_factor):
    if requests is None:
        print("[CV control] Missing requests package; shot not posted")
        return False

    payload = {
        "x_px": float(cx * scale_factor),
        "y_px": float(cy * scale_factor),
        "shotID": int(bullet_id),
        "scores": int(score),
        "metadata": {
            "source": "cv",
            "target_type": target_name.replace("BIA_", ""),
        },
    }

    try:
        response = requests.post(
            f"{BACKEND_HTTP_URL}/shot",
            json=payload,
            timeout=2.0,
        )
        if response.status_code == 409:
            complete_session()
            return False
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"[CV control] Failed to post shot {bullet_id}: {exc}")
        return False
