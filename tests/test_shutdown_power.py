"""Offline generators can report zero or finite negative auxiliary consumption."""
# ruff: noqa: F811 -- imported fixtures are injected by pytest.

import json

import pytest

from src.platform_adapter import PlatformComputePayload, _actual_from_history
from src.platform_config import STATION_MEASUREMENT_POINTS, platform_point_name
from tests.test_forecast_http import http_chain  # noqa: F401
from tests.test_platform_contract import platform_chain, platform_payload  # noqa: F401


@pytest.mark.parametrize("power", [0.0, -0.25])
def test_all_offline_generators_are_accepted(platform_chain, power):
    client, _, bridge, _ = platform_chain
    payload = platform_payload()
    for frame in payload["frames"]:
        for points in STATION_MEASUREMENT_POINTS.values():
            for point in points:
                frame[platform_point_name(point)] = power
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    values = {p["varname"]: p["value"] for p in response.json()["result_point"]}
    labels = {p["varname"]: p["value"] for p in response.json()["extra_info"]}
    for code in STATION_MEASUREMENT_POINTS:
        assert values[f"{code}_actualMW"] == 0
        assert values[f"{code}_adjustmentMW"] == values[f"{code}_MW"]
        if power < 0:
            assert "负功率归零" in labels[f"{code}_actualStatus"]
    with bridge.dispatch.store.connection() as db:
        actual = bridge.dispatch.store.inputs(db, "platform-20260921T100000Z")["actuals"]
    assert not any(s["running"] for s in actual["thermal_state"].values())


def test_shutdown_negative_does_not_hold_previous_generation(monkeypatch, tmp_path):
    log = tmp_path / "quality.jsonl"
    monkeypatch.setenv("WORK_LOG_PATH", str(log))
    payload = platform_payload()
    point = STATION_MEASUREMENT_POINTS["JFRD"][0]
    for frame in payload["frames"][:-1]:
        frame[point] = 120.0
    payload["frames"][-1][point] = -0.8
    actual = _actual_from_history(
        PlatformComputePayload(**payload).forecast_request(), "shutdown", "Asia/Shanghai"
    )
    assert actual.thermal_mw["JFRD"] == 0
    assert not actual.thermal_state["JFRD"].running
    assert actual.thermal_state["JFRD"].stops_today == 1
    records = [json.loads(s) for s in log.read_text("utf-8").splitlines()]
    assert any(
        r.get("original_value") == -0.8
        and r.get("action") == "negative_power_to_zero"
        and r.get("replacement_value") == 0
        for r in records
    )


def test_each_generator_is_clamped_before_station_sum(platform_chain):
    client, _, _, _ = platform_chain
    payload = platform_payload()
    positive, negative, _ = STATION_MEASUREMENT_POINTS["GARD"]
    for frame in payload["frames"]:
        frame[positive], frame[negative] = 100.0, -0.5
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    values = {p["varname"]: p["value"] for p in response.json()["result_point"]}
    assert values["GARD_actualMW"] == 100.0


def test_reported_screenshot_values(http_chain):
    client, state = http_chain
    payload = platform_payload()
    for frame in payload["frames"]:
        frame.update(
            {
                "SZRD_10DCS02FA133": 0,
                "SZRD_10DCS02FA134": 0,
                "JQRD_11MBL11CT010XQ01": 17.76,
                "JQRD_10CBA00FA108XQ93": -0.2,
            }
        )
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    sent = state["received"][0][1]["frames"][-1]
    assert sent["JQRD_11MBL11CT010XQ01"] == 17.76
    assert sent["JQRD_10CBA00FA108XQ93"] == 0
    assert sent["SZRD_10DCS02FA133"] == sent["SZRD_10DCS02FA134"] == 0
    values = {p["varname"]: p["value"] for p in response.json()["result_point"]}
    assert values["SZRD_actualMW"] == values["JQRD_actualMW"] == 0


@pytest.mark.parametrize("path", ["/api/v1/fluxcast/compute", "/api/v1/fluxcast/forecast/compute"])
def test_forecast_wire_clamps_power_but_preserves_weather(http_chain, path):
    client, state = http_chain
    payload = platform_payload()
    power = STATION_MEASUREMENT_POINTS["JYRD"][0]
    power_keys = {platform_point_name(p) for ps in STATION_MEASUREMENT_POINTS.values() for p in ps}
    weather = next(p for p in payload["point_table"] if p not in power_keys)
    for frame in payload["frames"]:
        frame[platform_point_name(power)] = -0.5
        frame[weather] = -5.0
    if path.endswith("forecast/compute"):
        payload = PlatformComputePayload(**payload).forecast_request()
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    sent = state["received"][0][1]
    assert all(f[power] == 0 and f[weather] == -5 for f in sent["frames"])
    assert (
        payload["frames"][0][
            power if path.endswith("forecast/compute") else platform_point_name(power)
        ]
        == -0.5
    )
