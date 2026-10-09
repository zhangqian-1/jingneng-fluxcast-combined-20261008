"""Public history ingestion reaches only the day model and preserves its envelope."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

import api
from src.forecast_bridge import ForecastClient
from tests.test_day_forecast_publication import DayModel
from tests.test_single_forecast_bridge import payload


@pytest.fixture
def day_proxy(monkeypatch):
    state = {"received": [], "status": 200, "body": {}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["received"].append(
                (self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            )
            content = state.get("raw", json.dumps(state["body"]).encode())
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    def forbidden():
        pytest.fail("Day-only backfill must not initialize single forecast or dispatch storage")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setattr(api, "get_forecast_bridge", forbidden)
    monkeypatch.setattr(api, "get_day_forecast_recovery", forbidden)
    monkeypatch.setattr(
        api,
        "get_day_forecast_client",
        lambda: ForecastClient(f"http://127.0.0.1:{server.server_port}"),
    )
    try:
        with TestClient(api.app, raise_server_exceptions=False) as client:
            yield client, state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("mode", ["ready", "history", "weather", "invalid", "unavailable"])
def test_day_only_backfill_preserves_upstream_response(day_proxy, mode):
    client, state = day_proxy
    request = payload()["forecast_request"]
    if mode == "ready":
        _, state["body"] = DayModel().request(request)
        state["body"]["result_point"].extend(
            [
                {
                    "varname": "forecastPointCount",
                    "value": 96.0,
                    "timestamp": "2026-09-21T10:00:00Z",
                },
                {
                    "varname": "forecastIntervalMinutes",
                    "value": 15.0,
                    "timestamp": "2026-09-21T10:00:00Z",
                },
            ]
        )
        state["body"]["extra_info"] = [
            {
                "varname": "forecastBatchId",
                "value": "dayahead-test",
                "timestamp": "2026-09-21T10:00:00Z",
            }
        ]
    elif mode in {"history", "weather"}:
        state["body"] = {
            "result_point": [],
            "extra_info": [],
            "event_key": "JNH.Fluxcast.Compute",
            "reason": "history_not_ready" if mode == "history" else "weather_history_not_ready",
            "continuous_points": 96,
            "required_points": 672,
        }
    else:
        state["status"] = 422 if mode == "invalid" else 503
        state["body"] = {"error": "upstream validation or service error", "result_point": []}
    response = client.post("/api/v1/fluxcast/day-forecast/compute", json=request)
    assert response.status_code == state["status"]
    assert response.json() == state["body"]
    assert response.headers["Cache-Control"] == "no-store"
    assert state["received"] == [("/api/v1/fluxcast/compute", request)]


def test_day_only_backfill_rejects_malformed_upstream(day_proxy):
    client, state = day_proxy
    state["raw"] = b"not json"
    response = client.post(
        "/api/v1/fluxcast/day-forecast/compute", json=payload()["forecast_request"]
    )
    assert response.status_code == 502
    assert response.json()["error_code"] == "FORECAST_RESPONSE_INVALID"


def test_day_only_backfill_disconnected_service(monkeypatch):
    monkeypatch.setattr(api, "get_day_forecast_client", lambda: None)
    with TestClient(api.app) as client:
        response = client.post("/api/v1/fluxcast/day-forecast/compute", json={})
    assert response.status_code == 503
    assert response.json()["error_code"] == "DAY_FORECAST_DISABLED"
