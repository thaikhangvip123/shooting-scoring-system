"""
backend/tests/test_shots_router.py
Integration tests for the shots REST API using FastAPI TestClient.
Firebase is bypassed via USE_FIREBASE=false (in-memory store).
"""

import os
os.environ["USE_FIREBASE"] = "false"

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


SAMPLE_SHOT = {
    "x_px": 1240.0,
    "y_px": 1754.0,
    "timestamp": "2026-05-06T10:30:45Z",
    "session_id": "test-session",
    "metadata": {"target_type": "TRON"},
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_post_shot_returns_201():
    r = client.post("/shot", json=SAMPLE_SHOT)
    assert r.status_code == 201
    body = r.json()
    assert body["x_px"] == 1240.0
    assert body["y_px"] == 1754.0
    assert "score" in body
    assert "ring"  in body
    assert "id"    in body
    assert body["score"] in range(0, 11)


def test_post_shot_scores_correctly():
    # X-ring shot (near centre)
    r = client.post("/shot", json={
        "x_px": 1240.5,
        "y_px": 1754.3,
        "timestamp": "2026-05-06T10:31:45Z",
        "metadata": {"target_type": "TRON"},
    })
    assert r.status_code == 201
    assert r.json()["score"] == 10
    assert r.json()["ring"]  == "X"


def test_post_shot_miss():
    # Way outside outermost ring
    r = client.post("/shot", json={
        "x_px": 300.0,
        "y_px": 0.0,
        "timestamp": "2026-05-06T10:32:45Z",
        "metadata": {"target_type": "TRON"},
    })
    assert r.status_code == 201
    assert r.json()["score"] == 0
    assert r.json()["ring"]  == "M"


def test_get_latest():
    client.post("/shot", json={
        "x_px": 1245.0,
        "y_px": 1759.0,
        "timestamp": "2026-05-06T10:33:45Z",
        "metadata": {"target_type": "TRON"},
    })
    r = client.get("/latest")
    assert r.status_code == 200
    assert r.json() is not None


def test_get_history():
    r = client.get("/history?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert "shots"  in body
    assert "total"  in body
    assert isinstance(body["shots"], list)


def test_stats_endpoint():
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert "cep_mm"      in body
    assert "r50_mm"      in body
    assert "group_size_mm" in body
    assert "avg_score"   in body


def test_heatmap_endpoint():
    r = client.get("/heatmap?resolution=20")
    assert r.status_code == 200
    body = r.json()
    assert body["resolution"] == 20
    assert len(body["grid"])  == 20
    assert len(body["grid"][0]) == 20


def test_delete_shots():
    client.post("/shot", json={
        "x_px": 1241.0,
        "y_px": 1755.0,
        "timestamp": "2026-05-06T10:34:45Z",
        "metadata": {"target_type": "TRON"},
    })
    r = client.delete("/shots")
    assert r.status_code == 204
    r2 = client.get("/latest")
    assert r2.json() is None


def test_invalid_payload_rejected():
    r = client.post("/shot", json={"x_px": "bad", "y_px": 0})
    assert r.status_code == 422


def test_post_ipsc_pixel_shot_scores_polygon():
    r = client.post(
        "/shot",
        json={
            "x_px": 1200.0,
            "y_px": 1500.0,
            "timestamp": "2026-05-06T10:35:45Z",
            "metadata": {"target_type": "IPSC"},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["metadata"]["target_type"] == "IPSC"
    assert body["score"] > 0


def test_post_nguoi_pixel_shot_scores_contour():
    r = client.post(
        "/shot",
        json={
            "x_px": 1225.0,
            "y_px": 1200.0,
            "timestamp": "2026-05-06T10:36:45Z",
            "metadata": {"target_type": "NGUOI"},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["metadata"]["target_type"] == "NGUOI"
    assert body["score"] > 0
