from backend.services.shot_service import make_shot_id


def test_make_shot_id_uses_session_and_index():
    assert make_shot_id("session-2", 4) == "session-2-shot-04"
    assert make_shot_id("session-12", 15) == "session-12-shot-15"
