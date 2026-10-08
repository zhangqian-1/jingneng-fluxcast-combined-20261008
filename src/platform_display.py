"""Direct display values, calculated from immutable dispatch archives.

This module does not optimize or invent actual/reference measurements. Daily
totals cover the selected Beijing plan day up to the current effective period.
The first response freezes its source periods so retries cannot double count
or change after later periods arrive.
"""

from __future__ import annotations

import json
import math
from zoneinfo import ZoneInfo

from src.errors import DispatchServiceError
from src.measured_power import measured_power
from src.platform_config import RENEWABLE_FARM_IDS, STATION_CODES, STATION_MEASUREMENT_POINTS
from src.runtime_config import REPOSITORY_ROOT
from src.single_period_models import STEP, utc_time
from src.station_labels import STATION_NAMES

DISPLAY_VERSION = "20261006-v2"
BEIJING = ZoneInfo("Asia/Shanghai")
ENERGY = {
    "thermalEnergyMWh": "thermalMWh",
    "renewableAcceptedEnergyMWh": "renewableAcceptedMWh",
    "gridBuyEnergyMWh": "gridBuyMWh",
    "renewableAvailableEnergyMWh": "renewableForecastMWh",
    "curtailEnergyMWh": "curtailMWh",
}
DAILY = {
    "thermalDayMWh": ("thermalMWh", 1),
    "renewableAcceptedDayMWh": ("renewableAcceptedMWh", 1),
    "gridBuyDayMWh": ("gridBuyMWh", 1),
    "renewableAvailableDayMWh": ("renewableForecastMWh", 1),
    "curtailDayMWh": ("curtailMWh", 1),
    "carbonDayTon": ("carbonTon", 1),
    "objectiveDayWanYuan": ("objectiveYuan", 10000),
    "directGenerationCostDayWanYuan": ("directGenerationCostYuan", 10000),
    "carbonCostDayWanYuan": ("carbonCostYuan", 10000),
    "gridCostDayWanYuan": ("gridCostYuan", 10000),
    "startStopCostDayWanYuan": ("startStopCostYuan", 10000),
    "curtailCostDayWanYuan": ("curtailCostYuan", 10000),
}


def point(name, timestamp, value):
    if not isinstance(value, str):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"Invalid display value: {name}")
        value = float(value)
    return {"varname": name, "timestamp": timestamp, "value": value}


def _power(result):
    values = {p["varname"]: p["value"] for p in result["result_point"]}
    thermal = sum(values[f"{c}_MW"] for c in STATION_CODES)
    accepted = sum(values[f"farm_{f}_MW"] for f in RENEWABLE_FARM_IDS)
    return values, thermal, accepted


def _build_base(result, rows, request, timestamp, format_time):
    local = utc_time(result["effective_at"]).astimezone(BEIJING)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    expected = int((local - start) / STEP) + 1
    metrics = result["step_metrics"]
    values, thermal, accepted = _power(result)
    demand = result["selected_demand_mw"]
    observed = request["frames"][-1]
    numbers, strings = [], []

    def n(name, value, stamp=timestamp):
        numbers.append(point(name, stamp, value))

    def s(name, value):
        strings.append(point(name, timestamp, value))

    s("displaySchemaVersion", DISPLAY_VERSION)
    s("currentPeriodLabel", f"{local:%Y-%m-%d %H:%M}—{local + STEP:%Y-%m-%d %H:%M}")
    s("dailyPeriodLabel", f"{start:%Y-%m-%d %H:%M}—{local + STEP:%Y-%m-%d %H:%M}")
    s(
        "actualTimeLabel",
        utc_time(observed["timestamp"]).astimezone(BEIJING).strftime("%Y-%m-%d %H:%M"),
    )
    s(
        "daySummaryStatus",
        "完整" if len(rows) == expected else f"部分累计：已计算{len(rows)}/{expected}个时段",
    )
    s("peakGridBuyStatus", "未提供：峰段起止及统计规则未约定")
    s("renewableDisplayLabel", "绿色消纳")
    n("dayPeriodCount", len(rows))
    n("dayExpectedPeriodCount", expected)
    n("renewableFarmCount", len(RENEWABLE_FARM_IDS))
    n("thermalPowerMW", thermal)
    n("renewableAcceptedPowerMW", accepted)
    n("renewableAvailablePowerMW", metrics["renewableForecastMWh"] * 4)
    n("curtailPowerMW", metrics["curtailMWh"] * 4)
    n("objectiveWanYuan", metrics["objectiveYuan"] / 10000)
    for name, source in ENERGY.items():
        n(name, metrics[source])
    for name, source in DAILY.items():
        n(name, sum(r["step_metrics"][source[0]] for r in rows) / source[1])
    if demand > 0:
        n("thermalSharePct", 100 * thermal / demand)
        n("renewableSharePct", 100 * accepted / demand)
        n("gridSharePct", 100 * values["grid_buy_MW"] / demand)
    s("powerShareStatus", "有效" if demand > 0 else "—：供电需求为0")
    available_day = sum(r["step_metrics"]["renewableForecastMWh"] for r in rows)
    if available_day > 0:
        n(
            "renewableAcceptanceDayPct",
            100 * sum(r["step_metrics"]["renewableAcceptedMWh"] for r in rows) / available_day,
        )
    s("renewableAcceptanceStatus", "有效" if available_day > 0 else "—：累计有效可用电量为0")

    for code in STATION_CODES:
        s(f"{code}_stationName", STATION_NAMES[code])
        raw = [observed.get(p) for p in STATION_MEASUREMENT_POINTS[code]]
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in raw)
        if valid:
            measured = sum(measured_power(v) for v in raw)
            n(f"{code}_actualMW", measured, format_time(observed["timestamp"]))
            n(f"{code}_adjustmentMW", values[f"{code}_MW"] - measured)
        s(
            f"{code}_actualStatus",
            ("实测有效（负功率归零）" if any(v < 0 for v in raw) else "实测有效")
            if valid
            else "缺测：未返回实测值及出力调整",
        )
        n(f"{code}_dayMWh", sum(_power(r)[0][f"{code}_MW"] * 0.25 for r in rows))

    farms = json.loads((REPOSITORY_ROOT / "config/renewable_capacities.json").read_text("utf-8"))[
        "farms"
    ]
    # Preserve the screenshot's first five rows; append the remaining configured IDs.
    order = [1, 16, 19, 8, 2] + [f for f in RENEWABLE_FARM_IDS if f not in (1, 16, 19, 8, 2)]
    for farm in farms:
        f = farm["farm_id"]
        s(f"farm_{f}_stationName", farm["station_name"])
        s(f"farm_{f}_displayOrder", f"{order.index(f) + 1:02d}")
        n(f"farm_{f}_capacityMW", farm["capacity_mw"])
        n(f"farm_{f}_id", f)
    s("farm_1_capacityStatus", "配置150.8 MW；现场容量与上游超限预测口径未核实")
    for row in rows:
        stamp = format_time(row["effective_at"])
        powers, gas, renew = _power(row)
        for name, value in {
            "thermalPowerCurveMW": gas,
            "renewablePowerCurveMW": renew,
            "gridBuyPowerCurveMW": powers["grid_buy_MW"],
            "dispatchDemandCurveMW": row["selected_demand_mw"],
            **{f"{c}_powerCurveMW": powers[f"{c}_MW"] for c in STATION_CODES},
        }.items():
            n(name, value, stamp)
    return {"result_point": numbers, "extra_info": strings}


def _comparison_display(rows, current, timestamp):
    numbers, strings = [], []
    matching = []
    for row in rows:
        comparison = row.get("comparison", {})
        if comparison.get("status") != "available":
            continue
        metrics = comparison["step_metrics"]
        base, saving = metrics["baselineCostYuan"], metrics["costSavingYuan"]
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (base, saving))
            or base < 0
        ):
            raise ValueError("Invalid reference comparison")
        if not math.isclose(
            base - row["step_metrics"]["objectiveYuan"], saving, abs_tol=0.01, rel_tol=1e-8
        ):
            raise ValueError("Reference costs do not reconcile")
        matching.append((base, saving))
        if row["snapshot_id"] == current:
            numbers.extend(
                [
                    point("baselineWanYuan", timestamp, base / 10000),
                    point("costSavingWanYuan", timestamp, saving / 10000),
                ]
            )
    if matching and len(matching) == len(rows):
        base = sum(v[0] for v in matching)
        saving = sum(v[1] for v in matching)
        numbers.extend(
            [
                point("baselineDayWanYuan", timestamp, base / 10000),
                point("costSavingDayWanYuan", timestamp, saving / 10000),
            ]
        )
        if base > 0:
            numbers.append(point("costSavingDayPct", timestamp, 100 * saving / base))
        state = "原计划比较有效" if base > 0 else "—：累计基准成本为0，比例无定义"
    else:
        state = "—：累计时段缺少有效原计划比较；实测事后核算未接通"
    strings.append(point("comparisonDisplayStatus", timestamp, state))
    return numbers, strings


def display_points(store, result, request, timestamp, format_time):
    """Serialize/freeze source membership in the same durable dispatch database."""
    try:
        snapshot = result["snapshot_id"]
        effective = utc_time(result["effective_at"])
        start = effective.astimezone(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)
        with store.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS platform_display (snapshot_id TEXT, "
                "version TEXT, body TEXT NOT NULL, PRIMARY KEY(snapshot_id,version))"
            )
            cached = db.execute(
                "SELECT body FROM platform_display WHERE snapshot_id=? AND version=?",
                (snapshot, DISPLAY_VERSION),
            ).fetchone()
            if cached:
                record = json.loads(cached[0])
                rows = [store.result(db, identity) for identity in record["sources"]]
                base = record["display"]
            else:
                rows = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT r.body FROM rolling_result r WHERE EXISTS "
                        "(SELECT 1 FROM rolling_input i WHERE i.snapshot_id=r.snapshot_id "
                        "AND i.kind='platform_request') AND "
                        "julianday(json_extract(r.body,'$.effective_at')) "
                        "BETWEEN julianday(?) AND julianday(?) "
                        "ORDER BY julianday(json_extract(r.body,'$.effective_at'))",
                        (start.isoformat(), effective.isoformat()),
                    )
                ]
                if not rows or snapshot not in {r["snapshot_id"] for r in rows}:
                    raise ValueError("Missing saved display period")
                stamps = [utc_time(r["effective_at"]) for r in rows]
                if len(set(stamps)) != len(stamps):
                    raise ValueError("Duplicate display periods")
                for row in rows:
                    origin = store.inputs(db, row["snapshot_id"])["forecast_origin"]
                    row["selected_demand_mw"] = origin["selected_demand_mw"]
                base = _build_base(result, rows, request, timestamp, format_time)
                record = {"sources": [r["snapshot_id"] for r in rows], "display": base}
                db.execute(
                    "INSERT INTO platform_display VALUES (?,?,?)",
                    (
                        snapshot,
                        DISPLAY_VERSION,
                        json.dumps(record, ensure_ascii=False, allow_nan=False),
                    ),
                )
            more, strings = _comparison_display(rows, snapshot, timestamp)
        return (
            [{**p, "timestamp": format_time(p["timestamp"])} for p in base["result_point"]] + more,
            [{**p, "timestamp": format_time(p["timestamp"])} for p in base["extra_info"]] + strings,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DispatchServiceError(
            503, "PLATFORM_RESULT_INVALID", "界面汇总数据无效，不能生成展示值"
        ) from exc
