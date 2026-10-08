"""New vendor contract integrates without changing any dispatch values or errors."""

import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api
from src.day_forecast_contract import validate_day_response
from src.day_forecast_publication import DayForecastPublisher, validate_curve
from src.day_observations import append_day_results
from src.forecast_bridge import ForecastDispatchBridge
from src.single_period_service import SinglePeriodService
from src.single_period_store import SinglePeriodStore
from src.vendor.dayahead.contract import POINTS
from src.vendor.dayahead.result_contract import forecast_response
from tests.test_day_forecast_publication import ANCHOR, MIDNIGHT_ANCHOR, DayModel, request_at
from tests.test_platform_contract import platform_payload
from tests.test_single_forecast_bridge import Upstream, prediction


class DeliveredModel(DayModel):
    def request(self, payload):
        status, result = super().request(payload)
        if result["result_point"]:
            result = forecast_response(
                result["result_point"],
                generated_at=MIDNIGHT_ANCHOR + timedelta(seconds=1),
                batch_id="dayahead-" + "1" * 32,
            )
        return status, result


def setup_published(tmp_path, received_at=None):
    publisher = DayForecastPublisher(DeliveredModel(), SinglePeriodStore(tmp_path / "state.db"))
    received_at = received_at or MIDNIGHT_ANCHOR + timedelta(seconds=2)
    with patch("src.day_forecast_publication.datetime") as clock:
        clock.now.return_value = received_at
        publisher.observe(request_at(MIDNIGHT_ANCHOR))
    daily, state = publisher.process(
        request_at(ANCHOR), successful=True, now=ANCHOR + timedelta(seconds=1), model_status="ready"
    )
    assert len(daily) == 96 and state == "published"
    return publisher


def measured_request(stamp=ANCHOR):
    return {"frames": [{"timestamp": stamp.isoformat(), **dict.fromkeys(POINTS, 10.0)}]}


def append(publisher, request=None, state="already_published"):
    body = {"result_point": [], "extra_info": []}
    append_day_results(body, publisher, request or measured_request(), state, lambda s: s)
    return body


def values(body):
    return {p["varname"]: p["value"] for p in body["result_point"] + body["extra_info"]}


def test_98_numeric_entries_are_exactly_96_predictions_plus_statistics():
    _, body = DeliveredModel().request(request_at(MIDNIGHT_ANCHOR))
    curve, status = validate_curve(body, MIDNIGHT_ANCHOR)
    assert status == "ready" and len(curve) == 96 and len(body["result_point"]) == 98
    assert {p["varname"] for p in curve} == {"totalPowerForecastDayAhead"}


@pytest.mark.parametrize("damage", ["count", "unknown", "metadata", "type", "duplicate"])
def test_bad_new_contract_is_not_silently_accepted(damage):
    _, body = DeliveredModel().request(request_at(MIDNIGHT_ANCHOR))
    if damage == "count":
        body["result_point"][-2]["value"] = 95
    elif damage == "unknown":
        body["result_point"][-2]["varname"] = "wrong"
    elif damage == "metadata":
        body["extra_info"][0]["value"] = "bad-id"
    elif damage == "type":
        body["extra_info"][0]["value"] = 1
    else:
        body["result_point"].append(deepcopy(body["result_point"][-1]))
    with pytest.raises(ValueError):
        validate_day_response(body)


def test_fixed_calendar_batch_survives_restart_and_rolling_prediction(tmp_path):
    publisher = setup_published(tmp_path)
    body = append(publisher, state="published")
    result = values(body)
    # Beijing 08:30 is the 35th point of the calendar curve (index 34).
    assert result["totalPowerDeviation"] == 1534 - 190
    assert result["totalPowerActual"] == 190
    assert result["forecastPointCount"] == 96
    assert result["forecastBatchId"] == "dayahead-" + "1" * 32
    publisher.client.damage = lambda b: b["result_point"][0].update(value=9999.0)
    publisher.observe(request_at(ANCHOR))
    fresh = DayForecastPublisher(publisher.client, SinglePeriodStore(publisher.store.path))
    assert values(append(fresh))["totalPowerDeviation"] == 1534 - 190
    assert "forecastPointCount" not in values(append(fresh))
    assert len(publisher.client.calls) == 2  # original call frequency is preserved


def test_late_recovery_cannot_invent_earlier_deviation(tmp_path):
    publisher = setup_published(tmp_path, received_at=ANCHOR + timedelta(seconds=2))
    current = values(append(publisher))
    assert current["totalPowerActual"] == 190
    assert "totalPowerDeviation" not in current
    future = values(append(publisher, measured_request(ANCHOR + timedelta(minutes=15))))
    assert future["totalPowerDeviation"] == 1535 - 190


def test_raw_negative_and_missing_values_reuse_vendor_rules(tmp_path):
    publisher = setup_published(tmp_path)
    request = measured_request()
    request["frames"][0][POINTS[0]] = -5
    assert values(append(publisher, request))["totalPowerActual"] == 180
    request["frames"][0][POINTS[0]] = None
    result = values(append(publisher, request))
    assert "totalPowerActual" not in result and "totalPowerDeviation" not in result
    assert "GARD_powerActual" not in result and result["JXRD_powerActual"] == 50
    assert result["dataStatus"] == "incomplete"
    assert not any(name.endswith("_powerShare") for name in result)
    assert "null" in result["message"]


def test_old_cached_curve_without_provenance_only_returns_actual(tmp_path):
    publisher = setup_published(tmp_path)
    with publisher.store.connection() as db:
        db.execute("DELETE FROM day_forecast_source")
    result = values(append(publisher))
    assert result["totalPowerActual"] == 190 and "totalPowerDeviation" not in result


def test_added_actuals_do_not_change_dispatch_response(tmp_path, monkeypatch):
    single = Upstream(prediction())
    single.response["result_point"][0]["timestamp"] = (ANCHOR + timedelta(minutes=15)).isoformat()
    bridge = ForecastDispatchBridge(
        single,
        SinglePeriodService(tmp_path / "api.db", clock=lambda: ANCHOR + timedelta(seconds=1)),
    )
    monkeypatch.setattr(api, "get_forecast_bridge", lambda: bridge)
    payload = platform_payload(ANCHOR, style="z")
    original = deepcopy(payload)
    with TestClient(api.app) as client:
        before = client.post("/api/v1/fluxcast/compute", json=payload)
        monkeypatch.setattr(api, "get_day_forecast_client", lambda: DeliveredModel())
        after = client.post("/api/v1/fluxcast/compute", json=payload)
    assert before.status_code == after.status_code == 200
    assert payload == original
    for group in ("result_point", "extra_info"):
        assert after.json()[group][: len(before.json()[group])] == before.json()[group]
        keys = [(p["varname"], p["timestamp"]) for p in after.json()[group]]
        assert len(keys) == len(set(keys))
    assert values(after.json())["totalPowerActual"] == 0
    assert values(after.json())["totalPowerForecast"] == 1000


def test_health_accepts_delivered_response(monkeypatch):
    import io

    from src.container_runtime import check_service

    _, body = DeliveredModel().request(request_at(MIDNIGHT_ANCHOR))

    def fetch(*args, **kwargs):
        stream = io.BytesIO(json.dumps(body).encode())
        stream.status = 200
        return stream

    monkeypatch.setattr("src.container_runtime.urlopen", fetch)
    assert check_service("http://internal", 96)
