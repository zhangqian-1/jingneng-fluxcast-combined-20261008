"""Platform's agreed flat request must drive prediction and one real optimization."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from src.errors import DispatchServiceError
from src.forecast_bridge import ForecastDispatchBridge
from src.platform_adapter import COST_DETAIL_NAMES, _comparison_points, _display_detail_points
from src.platform_config import RENEWABLE_FARM_IDS, STATION_CODES, platform_point_name
from src.single_period_models import SingleReferencePlan
from src.single_period_service import SinglePeriodService
from tests.test_single_forecast_bridge import Upstream, prediction

UTC = timezone.utc


def platform_payload(stamp=datetime(2026, 9, 21, 10, tzinfo=UTC), style="space"):
    points = json.loads(
        (Path(__file__).resolve().parents[1] / "config/forecast_measurement_points.json").read_text(
            "utf-8"
        )
    )["point_table"]
    points = [platform_point_name(p) for p in points]

    def format_time(value):
        if style == "space":
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.isoformat().replace("+00:00", "Z") if style == "z" else value.isoformat()

    frames = [
        {"timestamp": format_time(stamp - timedelta(minutes=15 * n)), **dict.fromkeys(points, 0.0)}
        for n in reversed(range(96))
    ]
    target = stamp + timedelta(minutes=15)
    local = timezone(timedelta(hours=8))
    day = target.astimezone(local).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        {
            "farmId": farm,
            "predictedTime": (day + timedelta(minutes=15 * (n + 1))).strftime("%Y%m%d%H%M"),
            "predictedPower": 10.0 if farm == 1 else 0.0,
            "timeSeries": 1,
            "batch": (day - timedelta(days=1) + timedelta(hours=8)).strftime("%Y%m%d%H%M"),
        }
        for farm in RENEWABLE_FARM_IDS
        for n in range(96)
    ]
    return {"point_table": points, "frames": frames, "renewable_data": rows}


@pytest.fixture
def platform_chain(monkeypatch, tmp_path):
    now = [datetime(2026, 9, 21, 10, 0, 1, tzinfo=UTC)]
    upstream = Upstream(prediction())
    bridge = ForecastDispatchBridge(
        upstream, SinglePeriodService(tmp_path / "platform.sqlite3", clock=lambda: now[0])
    )
    monkeypatch.setattr(api, "get_forecast_bridge", lambda: bridge)
    with TestClient(api.app, raise_server_exceptions=False) as client:
        yield client, upstream, bridge, now


@pytest.mark.parametrize(
    "style,expected",
    [
        ("space", "2026-09-21 10:15:00"),
        ("z", "2026-09-21T10:15:00Z"),
        ("offset", "2026-09-21T10:15:00+00:00"),
    ],
)
def test_agreed_flat_contract_drives_real_solver(platform_chain, style, expected):
    client, upstream, bridge, _ = platform_chain
    payload = platform_payload(style=style)
    original = deepcopy(payload)
    result = client.post("/api/v1/fluxcast/compute", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert set(body) == {"event_key", "result_point", "extra_info"}
    assert body["event_key"] == "JNH.Fluxcast.Compute"
    points = body["result_point"]
    assert len(points) == 153
    assert len({(p["varname"], p["timestamp"]) for p in points}) == len(points)
    assert all(type(p["value"]) is float for p in points)
    assert all(p["timestamp"] == expected for p in points if not p["varname"].endswith("_actualMW"))
    values = {p["varname"]: p["value"] for p in points}
    assert values["totalPowerForecast"] == upstream.response["result_point"][0]["value"]
    assert set(values) >= (
        {f"{code}_MW" for code in STATION_CODES}
        | {f"farm_{farm}_MW" for farm in RENEWABLE_FARM_IDS}
        | {"grid_buy_MW", "totalPowerForecast", "objectiveYuan", "carbonTon"}
        | set(COST_DETAIL_NAMES)
        | {f"farm_{farm}_available_MW" for farm in RENEWABLE_FARM_IDS}
    )
    assert values["objectiveYuan"] > 0 and values["carbonTon"] > 0
    assert sum(
        v for k, v in values.items() if k.endswith("_MW") and not k.endswith("_available_MW")
    ) == pytest.approx(1000.0)
    assert values["farm_1_MW"] == 10.0
    extra = body["extra_info"]
    assert len(extra) == 71
    assert all(set(p) == {"varname", "timestamp", "value"} for p in extra)
    assert all(type(p["value"]) is str and p["timestamp"] == expected for p in extra)
    strings = {p["varname"]: p["value"] for p in extra}
    assert len(strings) == len(extra)
    assert not (strings.keys() & values.keys())
    assert strings["balanceStatus"] == "供需平衡"
    with bridge.dispatch.store.connection() as db:
        saved = bridge.dispatch.store.result(db, "platform-20260921T100000Z")
    assert {code: strings[f"{code}_planStatus"] for code in STATION_CODES} == {
        code: "运行" if saved["thermal_running"][code] else "停机" for code in STATION_CODES
    }
    assert sum(values[n] for n in COST_DETAIL_NAMES) == pytest.approx(values["objectiveYuan"])
    assert {n: values[n] for n in COST_DETAIL_NAMES} == {
        n: saved["step_metrics"][n] for n in COST_DETAIL_NAMES
    }
    assert [values[f"farm_{f}_available_MW"] for f in RENEWABLE_FARM_IDS] == [
        r[0] for r in saved["_audit"]["renewable_available_mw"]
    ]
    assert values["farm_1_available_MW"] == 10.0
    assert payload == original
    sent = upstream.calls[0]
    assert set(sent) == {"point_table", "frames"}
    assert "JYRD_LOADCTL:GTMWSEL1_1.OUT" in sent["point_table"]
    assert "JYRD_QIXIANGYI:RIN7.MEAS" in sent["frames"][0]
    assert sent["frames"][-1]["timestamp"] == "2026-09-21 10:00:00"
    assert client.post("/api/v1/fluxcast/compute", json=payload).json() == body
    assert len(upstream.calls) == 1
    with bridge.dispatch.store.connection() as db:
        stored = bridge.dispatch.store.latest_actual(db, "unused")
    assert stored["renewable_mw"] is None  # Do not fabricate measurements from forecasts.
    assert stored["state_basis"] == "power_history_estimate"


@pytest.mark.parametrize("invalid", [None, True, float("nan"), -1.0])
def test_missing_or_invalid_selected_forecast_is_not_fabricated(
    platform_chain, monkeypatch, invalid
):
    client, _, bridge, _ = platform_chain
    payload = platform_payload()
    compute = bridge.compute

    def damaged(request):
        return {**compute(request), "selected_demand_mw": invalid}

    monkeypatch.setattr(bridge, "compute", damaged)
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 503
    assert response.json()["error_code"] == "PLATFORM_RESULT_INVALID"
    assert response.json()["result_point"] == response.json()["extra_info"] == []


def test_only_time_series_one_is_consumed(platform_chain):
    client, _, _, _ = platform_chain
    payload = platform_payload()
    extra = deepcopy(payload["renewable_data"])
    for row in extra:
        row.update(timeSeries=2, predictedPower=999999.0)
    payload["renewable_data"] += extra
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    assert (
        next(p["value"] for p in response.json()["result_point"] if p["varname"] == "farm_1_MW")
        == 10.0
    )


def test_extra_platform_measurements_do_not_break_vendor_contract(platform_chain):
    client, upstream, _, _ = platform_chain
    payload = platform_payload()
    payload["point_table"].append("GARD_EXTRA_OBSERVATION")
    for frame in payload["frames"]:
        frame["GARD_EXTRA_OBSERVATION"] = 12.0
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    sent = upstream.calls[0]
    assert len(sent["point_table"]) == 35
    assert all("GARD_EXTRA_OBSERVATION" not in f for f in sent["frames"])
    assert payload["frames"][0]["GARD_EXTRA_OBSERVATION"] == 12.0


@pytest.mark.parametrize(
    "damage",
    [
        "missing_farm",
        "mixed_batch",
        "duplicate",
        "no_day_one",
        "bad_axis",
        "missing_point",
        "null_thermal",
    ],
)
def test_invalid_flat_inputs_never_publish_fake_power(platform_chain, damage):
    client, upstream, _, _ = platform_chain
    payload = platform_payload()
    if damage == "missing_farm":
        payload["renewable_data"] = [r for r in payload["renewable_data"] if r["farmId"] != 29]
    elif damage == "mixed_batch":
        payload["renewable_data"][0]["batch"] = "202609190800"
    elif damage == "duplicate":
        payload["renewable_data"].append(deepcopy(payload["renewable_data"][0]))
    elif damage == "no_day_one":
        for row in payload["renewable_data"]:
            row["timeSeries"] = 2
    elif damage == "bad_axis":
        payload["frames"][1]["timestamp"] = payload["frames"][0]["timestamp"]
    elif damage == "missing_point":
        payload["point_table"].remove("GARD_11MBY0100000BJ01XQ01")
    else:
        for frame in payload["frames"]:
            frame["GARD_11MBY0100000BJ01XQ01"] = None
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    if damage in ("bad_axis", "missing_point"):
        assert response.status_code == 422, response.text
        assert response.json()["result_point"] == []
        assert not upstream.calls
    else:
        assert response.status_code == 200, response.text
        names = {p["varname"] for p in response.json()["result_point"]}
        assert "SZRD_actualMW" in names and "GARD_MW" not in names
        assert any(p["varname"] == "calculationStatus" for p in response.json()["extra_info"])


def test_flat_cold_start_returns_empty_results(platform_chain):
    client, upstream, _, _ = platform_chain
    upstream.response = {
        "event_key": "JNH.Fluxcast.Compute",
        "result_point": [],
        "reason": "history_not_ready",
    }
    response = client.post("/api/v1/fluxcast/compute", json=platform_payload())
    assert response.status_code == 202, response.text
    assert response.json()["result_point"] == []
    assert response.json()["reason"] == "history_not_ready"
    assert response.json()["extra_info"] == []


def test_platform_schema_requires_only_original_three_fields():
    doc = TestClient(api.app).get("/openapi.json").json()
    assert "/api/v1/fluxcast/compute" in doc["paths"]
    ref = doc["paths"]["/api/v1/fluxcast/compute"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"].split("/")[-1]
    assert set(doc["components"]["schemas"][ref]["required"]) == {
        "point_table",
        "frames",
        "renewable_data",
    }


def test_same_long_table_in_different_order_is_idempotent(platform_chain):
    client, upstream, _, _ = platform_chain
    body = platform_payload()
    first = client.post("/api/v1/fluxcast/compute", json=body)
    assert first.status_code == 200
    body["point_table"].reverse()
    body["renewable_data"].reverse()
    second = client.post("/api/v1/fluxcast/compute", json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(upstream.calls) == 1


def test_previous_day_tail_cannot_fill_a_missing_forecast_day(platform_chain):
    client, upstream, _, now = platform_chain
    stamp = datetime(2026, 9, 21, 15, 45, tzinfo=UTC)
    now[0] = stamp + timedelta(seconds=1)
    body = platform_payload(stamp)
    for row in body["renewable_data"]:
        end = datetime.strptime(row["predictedTime"], "%Y%m%d%H%M") - timedelta(days=1)
        row["predictedTime"] = end.strftime("%Y%m%d%H%M")
    response = client.post("/api/v1/fluxcast/compute", json=body)
    assert response.status_code == 200, response.text
    names = {p["varname"] for p in response.json()["result_point"]}
    assert "farm_1_available_MW" not in names and "GARD_MW" not in names
    # This fixture also holds an old single-step forecast; neither old source is reused.
    assert "totalPowerForecast" not in names
    assert "SZRD_actualMW" in names


def test_utc_fractional_timestamp_keeps_its_original_precision(platform_chain):
    client, _, _, _ = platform_chain
    body = platform_payload()
    for frame in body["frames"]:
        frame["timestamp"] += ".000"
    response = client.post("/api/v1/fluxcast/compute", json=body)
    assert response.status_code == 200, response.text
    assert {p["timestamp"] for p in response.json()["result_point"]} == {
        "2026-09-21 10:15:00.000",
        "2026-09-21 10:00:00.000",
    }
    assert {p["timestamp"] for p in response.json()["extra_info"]} == {"2026-09-21 10:15:00.000"}


def test_changed_payload_cannot_replace_published_snapshot(platform_chain):
    client, upstream, _, _ = platform_chain
    body = platform_payload()
    assert client.post("/api/v1/fluxcast/compute", json=body).status_code == 200
    body["frames"][3]["GARD_11MBY0100000BJ01XQ01"] = 0.5
    response = client.post("/api/v1/fluxcast/compute", json=body)
    assert response.status_code == 409, response.text
    assert response.json()["result_point"] == []
    assert response.json()["extra_info"] == []
    assert len(upstream.calls) == 1


def test_sliding_window_keeps_observed_state_anchor(platform_chain):
    client, upstream, bridge, now = platform_chain
    assert client.post("/api/v1/fluxcast/compute", json=platform_payload()).status_code == 200
    with bridge.dispatch.store.connection() as db:
        previous = bridge.dispatch.store.latest_actual(db, "unused")
    stamp = datetime(2026, 9, 21, 10, 15, tzinfo=UTC)
    now[0] = stamp + timedelta(seconds=1)
    for point in upstream.response["result_point"]:
        point["timestamp"] = (
            datetime.fromisoformat(point["timestamp"]) + timedelta(minutes=15)
        ).isoformat()
    response = client.post("/api/v1/fluxcast/compute", json=platform_payload(stamp))
    assert response.status_code == 200, response.text
    with bridge.dispatch.store.connection() as db:
        current = bridge.dispatch.store.latest_actual(db, "unused")
    assert current["thermal_state"] == previous["thermal_state"]


def test_rejects_old_station_query_instead_of_returning_wrong_scope(platform_chain):
    client, upstream, _, _ = platform_chain
    response = client.post("/api/v1/fluxcast/compute?source_id=2", json=platform_payload())
    assert response.status_code == 422, response.text
    assert not upstream.calls


@pytest.mark.parametrize("damage", ["missing_weather", "invalid_predicted_time"])
def test_model_input_requirements_fail_as_clear_client_errors(platform_chain, damage):
    client, upstream, _, _ = platform_chain
    body = platform_payload()
    if damage == "missing_weather":
        body["point_table"].remove("JYRD_QIXIANGYI:RIN7_MEAS")
    else:
        body["renewable_data"][0]["predictedTime"] = []
    response = client.post("/api/v1/fluxcast/compute", json=body)
    if damage == "missing_weather":
        assert response.status_code == 422, response.text
        assert response.json()["result_point"] == []
        assert not upstream.calls
    else:
        assert response.status_code == 200, response.text
        names = {p["varname"] for p in response.json()["result_point"]}
        assert "farm_1_available_MW" not in names and "farm_2_available_MW" in names


@pytest.mark.parametrize("status", ["expired", "superseded", "waiting_inputs"])
def test_unpublished_status_has_no_string_advice(platform_chain, monkeypatch, status):
    client, _, bridge, _ = platform_chain
    monkeypatch.setattr(bridge, "compute", lambda _: {"status": status})
    response = client.post("/api/v1/fluxcast/compute", json=platform_payload())
    assert response.status_code == (202 if status == "waiting_inputs" else 409)
    assert response.json()["result_point"] == response.json()["extra_info"] == []


@pytest.mark.parametrize("http_status", [502, 503])
def test_upstream_and_solver_errors_have_no_string_advice(platform_chain, monkeypatch, http_status):
    client, _, bridge, _ = platform_chain

    def fail(_):
        raise DispatchServiceError(http_status, "TEST_UNAVAILABLE", "服务暂不可用")

    monkeypatch.setattr(bridge, "compute", fail)
    response = client.post("/api/v1/fluxcast/compute", json=platform_payload())
    assert response.status_code == http_status
    assert response.json()["result_point"] == response.json()["extra_info"] == []


@pytest.mark.parametrize("damage", ["missing", "string", "number"])
def test_invalid_plan_state_is_not_presented_as_running(platform_chain, monkeypatch, damage):
    client, _, bridge, _ = platform_chain
    assert client.post("/api/v1/fluxcast/compute", json=platform_payload()).status_code == 200
    with bridge.dispatch.store.connection() as db:
        saved = bridge.dispatch.store.result(db, "platform-20260921T100000Z")
    if damage == "missing":
        del saved["thermal_running"]["GARD"]
    else:
        saved["thermal_running"]["GARD"] = "false" if damage == "string" else 0
    monkeypatch.setattr(bridge, "compute", lambda _: saved)
    response = client.post("/api/v1/fluxcast/compute", json=platform_payload())
    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "PLATFORM_RESULT_INVALID"
    assert response.json()["result_point"] == response.json()["extra_info"] == []


def test_invalid_json_has_empty_extra_info(platform_chain):
    client, _, _, _ = platform_chain
    response = client.post(
        "/api/v1/fluxcast/compute", content="{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["result_point"] == response.json()["extra_info"] == []


@pytest.mark.parametrize("damage", ["missing_cost", "bad_sum", "short_farms", "nan", "bool"])
def test_invalid_display_details_are_rejected(damage):
    metrics = dict.fromkeys(COST_DETAIL_NAMES, 1.0)
    result = {"step_metrics": {**metrics, "objectiveYuan": 5.0}}
    audit = {"renewable_available_mw": [[10.0] for _ in RENEWABLE_FARM_IDS]}
    if damage == "missing_cost":
        del result["step_metrics"][COST_DETAIL_NAMES[0]]
    elif damage == "bad_sum":
        result["step_metrics"]["objectiveYuan"] = 99.0
    elif damage == "short_farms":
        audit["renewable_available_mw"].pop()
    else:
        audit["renewable_available_mw"][0][0] = float("nan") if damage == "nan" else True
    with pytest.raises(DispatchServiceError, match="成本明细或新能源可用预测"):
        _display_detail_points(result, audit, "2026-09-21 10:15:00")


def test_available_power_is_effective_same_farm_input(platform_chain):
    client, _, bridge, _ = platform_chain
    payload = platform_payload()
    # Bad target value carries that farm's preceding valid prediction, not raw 999999.
    target = "202609211830"  # end of Beijing 18:15-18:30 target interval
    next(
        row
        for row in payload["renewable_data"]
        if row["farmId"] == 1 and row["predictedTime"] == target
    )["predictedPower"] = 999999.0
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    values = {p["varname"]: p["value"] for p in response.json()["result_point"]}
    assert values["farm_1_available_MW"] == 10.0
    assert values["farm_2_available_MW"] == 0.0
    with bridge.dispatch.store.connection() as db:
        archive = bridge.dispatch.store.result(db, "platform-20260921T100000Z")
    assert archive["_audit"]["renewable_available_mw"][0][0] == values["farm_1_available_MW"]


def test_existing_valid_reference_comparison_is_returned(platform_chain):
    client, _, bridge, _ = platform_chain
    payload = platform_payload()
    first = client.post("/api/v1/fluxcast/compute", json=payload)
    assert first.status_code == 200
    first_values = {p["varname"]: p["value"] for p in first.json()["result_point"]}
    assert "baselineCostYuan" not in first_values and "costSavingYuan" not in first_values
    snapshot = "platform-20260921T100000Z"
    with bridge.dispatch.store.connection() as db:
        saved = bridge.dispatch.store.result(db, snapshot)
    plan = SingleReferencePlan.model_validate(
        {
            "snapshot_id": snapshot,
            "plan_id": "valid-same-period-plan",
            "issued_at": "2026-09-21T10:00:00Z",
            "frames": [
                {
                    "timestamp": saved["effective_at"],
                    "thermal_mw": {c: first_values[f"{c}_MW"] for c in STATION_CODES},
                    "thermal_running": saved["thermal_running"],
                    "renewable_mw": {
                        str(f): first_values[f"farm_{f}_MW"] for f in RENEWABLE_FARM_IDS
                    },
                    "grid_buy_mw": first_values["grid_buy_MW"],
                }
            ],
        }
    )
    assert bridge.dispatch.submit("reference_plan", plan)["comparison"]["status"] == "available"
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    values = {p["varname"]: p["value"] for p in response.json()["result_point"]}
    assert len(values) == 160
    assert values["baselineCostYuan"] == pytest.approx(values["objectiveYuan"])
    assert values["costSavingYuan"] == pytest.approx(0.0, abs=0.01)
    assert all(values[k] == v for k, v in first_values.items())


@pytest.mark.parametrize(
    "saved,valid", [(5.0, True), (-5.0, True), (float("nan"), False), (True, False), (999.0, False)]
)
def test_saving_can_be_negative_but_must_reconcile(saved, valid):
    base = 15.0 if saved == 5.0 else 5.0
    result = {
        "step_metrics": {"objectiveYuan": 10.0},
        "comparison": {
            "status": "available",
            "step_metrics": {"baselineCostYuan": base, "costSavingYuan": saved},
        },
    }
    if valid:
        points = _comparison_points(result, "2026-09-21 10:15:00")
        assert points[1]["value"] == saved
    else:
        with pytest.raises(DispatchServiceError):
            _comparison_points(result, "2026-09-21 10:15:00")
