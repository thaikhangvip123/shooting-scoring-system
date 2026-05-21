from datetime import datetime, timezone

from backend.models.shot import ShotRecord


def test_shot_record_storage_dict_is_minimal():
    record = ShotRecord(
        id="session-2-shot-04",
        x_px=1243.0,
        y_px=1754.0,
        radius_px=3.0,
        score=10,
        ring="X",
        timestamp=datetime(2026, 5, 20, tzinfo=timezone.utc),
        session_id="session-2",
        metadata={
            "target_type": "tron",
            "shot_index": 4,
            "eval": {"backend_received_at_ms": 1779307114649},
        },
    )

    assert record.to_storage_dict() == {
        "shot_id": "session-2-shot-04",
        "score": 10,
        "session_id": "session-2",
        "target_type": "TRON",
    }


def test_minimal_storage_dict_can_be_read_back():
    record = ShotRecord.from_dict({
        "shot_id": "shot-123",
        "score": 10,
        "session_id": "session-2",
        "target_type": "IPSC",
    })

    assert record.id == "shot-123"
    assert record.score == 10
    assert record.session_id == "session-2"
    assert record.metadata == {"target_type": "IPSC"}
