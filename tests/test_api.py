import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.integrations.capture import CaptureResult
from app.main import create_app


class RecordingCapture:
    mode = "test"

    def __init__(self, *, start_ok=True, stop_ok=True):
        self.start_ok = start_ok
        self.stop_ok = stop_ok
        self.start_calls = 0
        self.stop_calls = 0

    def start(self, blind_sample_no):
        self.start_calls += 1
        return CaptureResult(self.start_ok, error="启动失败" if not self.start_ok else None)

    def stop(self, blind_sample_no):
        self.stop_calls += 1
        return CaptureResult(self.stop_ok, error="结束失败" if not self.stop_ok else None)


class FakeLims:
    def __init__(self):
        self.payloads = []

    async def push_results(self, payload, idempotency_key):
        self.payloads.append((payload, idempotency_key))


def make_client(tmp_path, capture=None, lims=None):
    settings = Settings(
        db_path=tmp_path / "test.db",
        lims_result_url="http://unused",
        capture_backend="mock",
    )
    app = create_app(
        settings,
        capture_adapter=capture or RecordingCapture(),
        lims_client=lims or FakeLims(),
    )
    return TestClient(app), settings.db_path


def test_frontend_static_assets_are_served(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "LIMS / SCADA 设备对接联调" in page.text
        assert client.get("/styles.css").status_code == 200
        assert client.get("/app.js").status_code == 200


def test_work_order_loop_and_idempotent_result_update(tmp_path):
    lims = FakeLims()
    client, db_path = make_client(tmp_path, lims=lims)
    work_order = {
        "order_no": "WO-1",
        "experimenter_id": "EMP-1",
        "project_name": "钢材成分检测",
        "samples": [{"sample_no": "S-1", "sample_name": "样品1"}],
        "test_items": ["Fe"],
    }
    with client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/api/work-orders", json=work_order).json()["duplicate"] is False
        assert client.post("/api/work-orders", json=work_order).json()["duplicate"] is True
        assert client.get("/api/scada/work-orders?experimenter_id=EMP-1").json()["count"] == 1
        result = {
            "order_no": "WO-1",
            "results": [{"sample_no": "S-1", "test_item": "Fe", "value": 96.2, "unit": "%"}],
            "finished": True,
        }
        assert client.post("/api/scada/results", json=result).status_code == 200
        result["results"][0]["value"] = 96.3
        assert client.post("/api/scada/results", json=result).status_code == 200
        assert client.post("/api/work-orders/WO-1/push-to-lims").status_code == 200
        assert lims.payloads[0][0]["results"][0]["value"] == "96.3"
        assert lims.payloads[0][1] == "WO-1"
        payload = client.get("/api/work-orders/WO-1/results").json()
        assert payload["status"] == "pushed"
        assert payload["results"][0]["pushed_to_lims"] == 1
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_results").fetchone()[0] == 1


def test_detection_start_stop_is_idempotent_and_matches_sample(tmp_path):
    capture = RecordingCapture()
    client, db_path = make_client(tmp_path, capture=capture)
    with client:
        client.post(
            "/api/work-orders",
            json={
                "order_no": "WO-2",
                "experimenter_id": "EMP-2",
                "samples": [{"sample_no": "BLIND-1"}],
            },
        )
        start = client.post("/startTest", json={"blindSampleNo": "BLIND-1"})
        assert start.status_code == 200
        assert start.json() == {"code": "0010", "response": None, "message": "成功"}
        assert client.post("/startTest", json={"blindSampleNo": "BLIND-1"}).json()["code"] == "0010"
        assert capture.start_calls == 1
        stop = client.post("/stopTest", json={"blindSampleNo": "BLIND-1"})
        assert stop.json() == {"code": "0010", "response": None, "message": "成功"}
        assert client.post("/stopTest", json={"blindSampleNo": "BLIND-1"}).json()["code"] == "0010"
        assert capture.stop_calls == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status, started_at, ended_at, sample_id, capture_mode FROM detection_sessions"
        ).fetchone()
        assert row[0] == "stopped"
        assert row[1].endswith("Z") and row[2].endswith("Z")
        assert row[3] is not None
        assert row[4] == "test"


def test_detection_can_be_independent_and_business_failure_uses_code_500(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        assert client.post("/stopTest", json={"blindSampleNo": "UNKNOWN"}).json() == {
            "code": "500",
            "response": None,
            "message": "未找到正在进行的检测",
        }
        assert client.post("/startTest", json={"blindSampleNo": "STANDALONE"}).json()["code"] == "0010"
        assert client.post("/stopTest", json={"blindSampleNo": "STANDALONE"}).json()["code"] == "0010"


def test_detection_validation_and_capture_failure(tmp_path):
    failing = RecordingCapture(start_ok=False)
    client, _ = make_client(tmp_path, capture=failing)
    with client:
        assert client.post("/startTest", json={}).status_code == 422
        assert client.post("/startTest", json={"blindSampleNo": "  "}).status_code == 422
        assert client.post(
            "/startTest", json={"blindSampleNo": "S-1", "extra": "forbidden"}
        ).status_code == 422
        response = client.post("/startTest", json={"blindSampleNo": "S-1"})
        assert response.status_code == 200
        assert response.json()["code"] == "500"
        assert failing.start_calls == 1


def test_stop_capture_failure_does_not_mark_session_stopped(tmp_path):
    failing = RecordingCapture(stop_ok=False)
    client, db_path = make_client(tmp_path, capture=failing)
    with client:
        client.post("/startTest", json={"blindSampleNo": "S-2"})
        response = client.post("/stopTest", json={"blindSampleNo": "S-2"})
        assert response.json()["code"] == "500"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT status FROM detection_sessions").fetchone()[0] == "recording"
