"""Data failures omit dependent results, retaining independent measurements."""

# ruff: noqa: F811
import json

import pytest

from tests.test_platform_contract import platform_chain, platform_payload  # noqa: F401


@pytest.mark.parametrize(
    "damage", ["missing_farm", "empty_farm", "missing_thermal", "two_failures"]
)
def test_partial_data_has_explicit_dependencies(platform_chain, monkeypatch, tmp_path, damage):
    client, upstream, _, _ = platform_chain
    monkeypatch.setenv("WORK_LOG_PATH", str(tmp_path / "partial.jsonl"))
    payload = platform_payload()
    if damage in ("missing_farm", "two_failures"):
        payload["renewable_data"] = [r for r in payload["renewable_data"] if r["farmId"] != 29]
    if damage == "empty_farm":
        for row in payload["renewable_data"]:
            if row["farmId"] == 29:
                row["predictedPower"] = None
    if damage in ("missing_thermal", "two_failures"):
        for frame in payload["frames"]:
            frame["GARD_11MBY0100000BJ01XQ01"] = None
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"event_key", "result_point", "extra_info"}
    values = {p["varname"]: p["value"] for p in body["result_point"]}
    labels = {p["varname"]: p["value"] for p in body["extra_info"]}
    assert labels["calculationStatus"] == "部分结果：未生成优化方案"
    assert values["SZRD_actualMW"] == 0
    assert values["farm_1_available_MW"] == 10
    assert not {"GARD_MW", "farm_1_MW", "grid_buy_MW", "objectiveYuan", "carbonTon"} & values.keys()
    assert "balanceStatus" not in labels and "GARD_planStatus" not in labels
    if damage in ("missing_thermal", "two_failures"):
        assert "GARD_actualMW" not in values and "totalPowerForecast" not in values
        assert "GARD_11MBY0100000BJ01XQ01" in labels["calculationDetail"]
        assert not upstream.calls
    else:
        assert values["totalPowerForecast"] == 1000
    if damage != "missing_thermal":
        assert "farm_29_available_MW" not in values
        assert "farmId=29" in labels["calculationDetail"]
    assert all(type(p["value"]) is float for p in body["result_point"])
    logs = [
        json.loads(line) for line in (tmp_path / "partial.jsonl").read_text("utf-8").splitlines()
    ]
    assert any(r.get("action") == "partial_results" and r.get("unavailable_results") for r in logs)


def test_partial_input_can_be_corrected_then_optimized(platform_chain):
    client, _, _, _ = platform_chain
    bad = platform_payload()
    bad["renewable_data"] = [r for r in bad["renewable_data"] if r["farmId"] != 29]
    assert client.post("/api/v1/fluxcast/compute", json=bad).status_code == 200
    corrected = client.post("/api/v1/fluxcast/compute", json=platform_payload())
    assert corrected.status_code == 200, corrected.text
    assert any(p["varname"] == "objectiveYuan" for p in corrected.json()["result_point"])


def test_stale_partial_request_remains_rejected(platform_chain):
    client, _, _, now = platform_chain
    from datetime import timedelta

    now[0] += timedelta(minutes=16)
    bad = platform_payload()
    bad["renewable_data"] = [r for r in bad["renewable_data"] if r["farmId"] != 29]
    response = client.post("/api/v1/fluxcast/compute", json=bad)
    assert response.status_code == 409
    assert response.json()["result_point"] == []


def test_bad_power_does_not_feed_or_publish_day_model(platform_chain, monkeypatch):
    import api

    class RejectCalls:
        def request(self, *args):
            pytest.fail("Unusable power must not be silently zero-filled by the day model")

    monkeypatch.setattr(api, "get_day_forecast_client", lambda: RejectCalls())
    monkeypatch.setattr(api, "get_day_forecast_recovery", lambda: None)
    client, _, _, _ = platform_chain
    body = platform_payload()
    for frame in body["frames"]:
        frame["GARD_11MBY0100000BJ01XQ01"] = None
    result = client.post("/api/v1/fluxcast/compute", json=body)
    assert result.status_code == 200
    assert not any(
        p["varname"] == "totalPowerForecastDayAhead" for p in result.json()["result_point"]
    )


def test_invalid_retry_does_not_overwrite_completed_result(platform_chain):
    client, _, _, _ = platform_chain
    good = platform_payload()
    first = client.post("/api/v1/fluxcast/compute", json=good)
    assert first.status_code == 200
    bad = platform_payload()
    bad["renewable_data"] = []
    assert client.post("/api/v1/fluxcast/compute", json=bad).status_code == 409
    assert client.post("/api/v1/fluxcast/compute", json=good).json() == first.json()
