"""Exercise direct display data with real optimization and a persistent store."""
# ruff: noqa: F811 -- imported pytest fixture is injected by name.

from datetime import timedelta

import pytest

from src.platform_adapter import PlatformComputePayload, _output_timestamp
from src.platform_display import display_points
from src.single_period_store import SinglePeriodStore
from tests.test_platform_contract import platform_chain, platform_payload  # noqa: F401


def values(body, field="result_point"):
    return {p["varname"]: p["value"] for p in body[field]}


def advance(chain, minutes=15, demand=1200):
    client, upstream, _, clock = chain
    clock[0] += timedelta(minutes=minutes)
    stamp = clock[0] - timedelta(seconds=1)
    upstream.response["result_point"][0].update(
        timestamp=(stamp + timedelta(minutes=15)).isoformat(), value=demand
    )
    payload = platform_payload(stamp)
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def test_display_math_and_partial_day_are_explicit(platform_chain):
    client, _, _, _ = platform_chain
    body = client.post("/api/v1/fluxcast/compute", json=platform_payload()).json()
    v, s = values(body), values(body, "extra_info")
    assert v["thermalPowerMW"] == pytest.approx(990)
    assert v["renewableAcceptedPowerMW"] == pytest.approx(10)
    assert v["thermalEnergyMWh"] == pytest.approx(247.5)
    assert v["renewableAcceptedDayMWh"] == pytest.approx(2.5)
    assert v["thermalSharePct"] + v["renewableSharePct"] + v["gridSharePct"] == pytest.approx(100)
    assert v["renewableAcceptanceDayPct"] == pytest.approx(100)
    assert v["dayPeriodCount"] == 1 and v["dayExpectedPeriodCount"] == 74
    assert s["daySummaryStatus"] == "部分累计：已计算1/74个时段"
    assert sum(
        v[n]
        for n in (
            "directGenerationCostDayWanYuan",
            "carbonCostDayWanYuan",
            "gridCostDayWanYuan",
            "startStopCostDayWanYuan",
            "curtailCostDayWanYuan",
        )
    ) == pytest.approx(v["objectiveDayWanYuan"])
    assert v["JYRD_adjustmentMW"] == v["JYRD_MW"] - v["JYRD_actualMW"]
    actual = next(p for p in body["result_point"] if p["varname"] == "JYRD_actualMW")
    assert actual["timestamp"] == "2026-09-21 10:00:00"
    assert "baselineDayWanYuan" not in v
    assert "实测事后核算未接通" in s["comparisonDisplayStatus"]


def test_daily_totals_curves_and_retry_use_saved_periods(platform_chain):
    client, _, bridge, _ = platform_chain
    payload = platform_payload()
    first = client.post("/api/v1/fluxcast/compute", json=payload).json()
    second, second_payload = advance(platform_chain)
    one, two = values(first), values(second)
    assert two["dayPeriodCount"] == 2
    assert two["thermalDayMWh"] == pytest.approx(one["thermalEnergyMWh"] + two["thermalEnergyMWh"])
    assert two["objectiveDayWanYuan"] == pytest.approx(
        one["objectiveWanYuan"] + two["objectiveWanYuan"]
    )
    curve = [p for p in second["result_point"] if p["varname"] == "thermalPowerCurveMW"]
    assert [p["value"] for p in curve] == [one["thermalPowerMW"], two["thermalPowerMW"]]
    assert len({p["timestamp"] for p in curve}) == 2
    assert client.post("/api/v1/fluxcast/compute", json=second_payload).json() == second
    # Reopen the store, then replay the old display without including the later period.
    store = SinglePeriodStore(bridge.dispatch.store.path)
    result = bridge.status("platform-20260921T100000Z")
    points, _ = display_points(
        store,
        result,
        PlatformComputePayload(**payload).forecast_request(),
        "2026-09-21 10:15:00",
        lambda v: _output_timestamp(v, "2026-09-21 10:00:00"),
    )
    assert values({"result_point": points})["dayPeriodCount"] == 1


def test_missing_actual_is_not_repaired_and_labeled_as_measurement(platform_chain):
    client, _, _, _ = platform_chain
    payload = platform_payload()
    payload["frames"][-1]["GARD_11MBY0100000BJ01XQ01"] = None
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    v, s = values(response.json()), values(response.json(), "extra_info")
    assert "GARD_actualMW" not in v and "GARD_adjustmentMW" not in v
    assert "缺测" in s["GARD_actualStatus"]
    assert "JFRD_actualMW" in v


def test_zero_denominators_are_undefined_not_hundred_percent(platform_chain):
    client, upstream, _, _ = platform_chain
    upstream.response["result_point"][0]["value"] = 0
    payload = platform_payload()
    for row in payload["renewable_data"]:
        row["predictedPower"] = 0
    response = client.post("/api/v1/fluxcast/compute", json=payload)
    assert response.status_code == 200, response.text
    v, s = values(response.json()), values(response.json(), "extra_info")
    assert (
        not {"thermalSharePct", "renewableSharePct", "gridSharePct", "renewableAcceptanceDayPct"}
        & v.keys()
    )
    assert "为0" in s["powerShareStatus"] and "为0" in s["renewableAcceptanceStatus"]


def test_beijing_midnight_resets_daily_totals_and_keeps_missing_periods_visible(platform_chain):
    client, _, _, _ = platform_chain
    assert client.post("/api/v1/fluxcast/compute", json=platform_payload()).status_code == 200
    # 15:45 UTC observation yields next day's 00:00 Beijing plan.
    midnight, _ = advance(platform_chain, minutes=345)
    v, s = values(midnight), values(midnight, "extra_info")
    assert v["dayPeriodCount"] == v["dayExpectedPeriodCount"] == 1
    assert v["objectiveDayWanYuan"] == v["objectiveWanYuan"]
    assert s["daySummaryStatus"] == "完整"
    later, _ = advance(platform_chain, minutes=30)
    assert values(later)["dayPeriodCount"] == 2
    assert values(later)["dayExpectedPeriodCount"] == 3
    assert "部分累计" in values(later, "extra_info")["daySummaryStatus"]
    assert len([p for p in later["result_point"] if p["varname"] == "thermalPowerCurveMW"]) == 2
