"""End-to-end HTTP + WebSocket tests against the REAL FastAPI app (TestClient).

NOTE: these need `pip install -e ".[dev]"` (fastapi, httpx). They were NOT executed in the authoring environment
(no network), so treat a failure here as a bug report, and tell me which assertion failed."""
import cv2
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from fakes import FakeDetector, FakeEmbedder, make_engine, make_frame  # noqa: E402
from helpers import Clock, faces_png, make_settings  # noqa: E402

H = {"X-Requested-With": "XMLHttpRequest"}


def _client(tmp_path):
    eng, _ = make_engine(tmp_path / "engine")
    s = make_settings(tmp_path, admin_username="alice", admin_password="a-long-passphrase", allowed_origins=[])
    return TestClient(create_app(s, eng, Clock()))


def _login(c):
    r = c.post("/api/auth/login", json={"username": "alice", "password": "a-long-passphrase"}, headers=H)
    assert r.status_code == 200, r.text
    return c.cookies.get("sa_session")


def test_auth_guards_and_csrf(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        assert c.get("/api/people").status_code == 401
        assert c.post("/api/auth/login", json={"username": "alice", "password": "a-long-passphrase"}).status_code == 403   # no CSRF header
        assert c.post("/api/auth/login", json={"username": "alice", "password": "nope"}, headers=H).status_code == 401
        _login(c)
        assert c.get("/api/auth/me").json()["user"]["username"] == "alice"
        assert c.post("/api/people", json={"person_id": "S1", "full_name": "Ada Lovelace"}).status_code == 403            # mutating w/o header
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        assert c.get("/api/people").status_code == 401


def test_full_workflow(tmp_path):
    with _client(tmp_path) as c:
        token = _login(c)
        r = c.post("/api/people", json={"person_id": "S1", "full_name": "Ada Lovelace", "department": "CS"}, headers=H)
        assert r.status_code == 201 and r.json()["face_status"] == "pending"
        dup = c.post("/api/people", json={"person_id": "S1", "full_name": "Other Person"}, headers=H)
        assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_id"
        files = [("files", (n, d, "image/png")) for n, d in faces_png(1)]
        r = c.post("/api/people/S1/faces", files=files, data={"allow_possible_duplicate": "false"}, headers=H)
        assert r.status_code == 200 and r.json()["person"]["face_status"] == "registered", r.text

        with c.websocket_connect("/ws/live", headers={"cookie": f"sa_session={token}"}) as ws:
            assert ws.receive_json()["type"] == "ready"
            events = []
            for i in range(8):
                ws.send_bytes(cv2.imencode(".png", make_frame([1], seed=800 + i))[1].tobytes())
                msg = ws.receive_json()
                assert msg["type"] == "result"
                events += msg["events"]
            assert len(events) == 1 and events[0]["person_id"] == "S1"

        lst = c.get("/api/attendance").json()
        assert lst["total"] == 1 and lst["items"][0]["source"] == "face"
        assert c.get("/api/dashboard").json()["present_today"] == 1
        csv = c.get("/api/attendance/export", params={"format": "csv"})
        assert csv.status_code == 200 and "S1" in csv.text and "attachment" in csv.headers["content-disposition"]
        assert c.get("/api/attendance/export", params={"format": "xlsx"}).status_code == 200
        rid = lst["items"][0]["id"]
        assert c.patch(f"/api/attendance/{rid}", json={"status": "late"}, headers=H).json()["status"] == "late"
        assert c.delete(f"/api/attendance/{rid}", headers=H).status_code == 200


def test_websocket_requires_login(tmp_path):
    with _client(tmp_path) as c:
        with c.websocket_connect("/ws/live") as ws:
            with pytest.raises(Exception):          # server closes with 4401
                ws.receive_json()
