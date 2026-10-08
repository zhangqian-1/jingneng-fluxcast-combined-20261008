"""Return independent values when data prevents a coupled dispatch solve."""

from datetime import datetime
from types import SimpleNamespace

from src.errors import DispatchServiceError
from src.forecast_bridge import EVENT_KEY, select_target_prediction
from src.input_quality import normalize_series, write_work_log
from src.measured_power import measured_power
from src.platform_adapter import _output_timestamp
from src.platform_config import (
    RENEWABLE_FARM_IDS,
    STATION_MEASUREMENT_POINTS,
    load_renewable_capacities,
)
from src.renewable_provider import LOCAL_TIMEZONE, RenewableInputError, _power
from src.runtime_config import REPOSITORY_ROOT
from src.single_period_models import STEP, utc_time

DEPENDENT_RESULTS = (
    "七站*_MW优化出力、farm_*_MW接纳计划、grid_buy_MW、objectiveYuan、carbonTon、"
    "本轮成本明细、电量、占比、adjustmentMW、planStatus、balanceStatus及包含本轮的累计/曲线"
)


def power_history_usable(request):
    # The existing causal-fill rule requires a valid first observation per channel.
    first = request["frames"][0]
    try:
        for points in STATION_MEASUREMENT_POINTS.values():
            for point in points:
                measured_power(first.get(point))
    except (ValueError, OverflowError):
        return False
    return True


def _farm_available(records, farm, target, capacity, now):
    """Use the original per-day, per-farm time/capacity/fill rules independently."""
    rows = [
        r
        for r in records
        if type(r.get("farmId")) is int
        and r.get("farmId") == farm
        and type(r.get("timeSeries")) is int
        and r.get("timeSeries") == 1
    ]
    if not rows:
        raise RenewableInputError(f"farmId={farm}缺少timeSeries=1数据")
    batches = {r.get("batch") for r in rows if isinstance(r.get("batch"), str)}
    all_batches = {
        r.get("batch")
        for r in records
        if r.get("timeSeries") == 1 and isinstance(r.get("batch"), str)
    }
    if len(batches) != 1 or len(all_batches) != 1:
        raise RenewableInputError(f"farmId={farm}预测批次缺失或混合，不能确定有效预测")
    indexed = {}
    for row in rows:
        for key in ("batch", "predictedTime"):
            raw = row.get(key)
            if not isinstance(raw, str) or len(raw) != 12 or not raw.isdigit():
                raise RenewableInputError(f"farmId={farm}的{key}格式无效")
        issued = datetime.strptime(row["batch"], "%Y%m%d%H%M").replace(tzinfo=LOCAL_TIMEZONE)
        if issued > now:
            raise RenewableInputError(f"farmId={farm}预测批次晚于当前时间")
        end = datetime.strptime(row["predictedTime"], "%Y%m%d%H%M").replace(tzinfo=LOCAL_TIMEZONE)
        if end.minute % 15 or end in indexed:
            raise RenewableInputError(f"farmId={farm}预测时间错位或重复：{row['predictedTime']}")
        indexed[end] = row.get("predictedPower")
    day = target.astimezone(LOCAL_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    ends = [day + (n + 1) * STEP for n in range(96)]
    if not set(ends).issubset(indexed):
        raise RenewableInputError(f"farmId={farm}未完整覆盖目标日96时段")
    previous = None
    if day in indexed:
        try:
            previous = (_power(indexed[day], farm, 0, capacity), (day - STEP).isoformat())
        except RenewableInputError:
            pass
    series, _ = normalize_series(
        [indexed[end] for end in ends],
        [(end - STEP).isoformat() for end in ends],
        lambda v, n: _power(v, farm, n, capacity),
        series=f"farm_{farm}_predictedPower",
        previous=previous,
        initial_upper_limit=capacity,
        context={"basis": "independent_available_forecast"},
    )
    return series[ends.index(target.astimezone(LOCAL_TIMEZONE) + STEP)]


def partial_response(payload, bridge, cause):
    request = payload.forecast_request()
    observed = utc_time(request["frames"][-1]["timestamp"])
    now = bridge.dispatch.clock()
    if observed > now or now >= observed + STEP:
        raise DispatchServiceError(409, "ACTUAL_TIME_INVALID", "断面不在当前有效计算窗口")
    snapshot = "platform-" + observed.strftime("%Y%m%dT%H%M%SZ")
    with bridge.dispatch.store.connection() as db:
        previous = bridge.dispatch.store.latest_actual(db, snapshot)
        if bridge.dispatch.store.inputs(db, snapshot):
            # An invalid changed retry must never replace an already accepted snapshot.
            raise DispatchServiceError(
                409, "PARTIAL_INPUT_CONFLICT", "该断面已有归档，不能用异常请求覆盖"
            )
    if previous and utc_time(previous["timestamp"]) >= observed:
        raise DispatchServiceError(409, "ACTUAL_OUT_OF_ORDER", "不接受旧断面")
    target = observed + STEP
    template = payload.frames[-1]["timestamp"]
    stamp = _output_timestamp(target, template)
    actual_stamp = _output_timestamp(observed, template)
    numbers, strings, issues = [], [], []

    def n(key, value, timestamp=stamp):
        numbers.append({"varname": key, "timestamp": timestamp, "value": float(value)})

    def s(key, value):
        strings.append({"varname": key, "timestamp": stamp, "value": value})

    def issue(source, reason, unavailable):
        issues.append({"input": source, "reason": reason, "unavailable_results": unavailable})

    first, last = request["frames"][0], request["frames"][-1]
    for code, points in STATION_MEASUREMENT_POINTS.items():
        valid, power, adjusted = True, 0.0, False
        for point in points:
            try:
                value = measured_power(last.get(point))
                power += value
                adjusted |= last[point] < 0
            except (ValueError, OverflowError):
                valid = False
                issue(point, f"末帧{actual_stamp}缺失或不是有限数值", [f"{code}_actualMW"])
            try:
                measured_power(first.get(point))
            except (ValueError, OverflowError):
                issue(
                    point,
                    f"首帧{first['timestamp']}缺失或无效，无历史值可前填",
                    ["totalPowerForecast", "totalPowerForecastDayAhead", DEPENDENT_RESULTS],
                )
        if valid:
            n(f"{code}_actualMW", power, actual_stamp)
            s(f"{code}_actualStatus", "实测有效（负功率归零）" if adjusted else "实测有效")
        else:
            s(f"{code}_actualStatus", "缺测：未返回实测值及出力调整")
    capacities = load_renewable_capacities(REPOSITORY_ROOT / "config/renewable_capacities.json")
    for farm in RENEWABLE_FARM_IDS:
        try:
            value = _farm_available(payload.renewable_data, farm, target, capacities[farm], now)
            n(f"farm_{farm}_available_MW", value)
        except (ValueError, TypeError, OverflowError) as exc:
            issue(f"farmId={farm}", str(exc), [f"farm_{farm}_available_MW", DEPENDENT_RESULTS])
    if power_history_usable(request):
        try:
            status, forecast = bridge.client.request(request)
            if status != 200:
                raise ValueError(f"预测服务HTTP {status}")
            value = select_target_prediction(forecast, SimpleNamespace(timestamp=observed))
            if value is None:
                raise ValueError(f"预测未就绪：{forecast.get('reason', 'unknown')}")
            if bridge.dispatch.clock() >= target:
                raise DispatchServiceError(
                    409, "FORECAST_DEADLINE_PASSED", "预测完成时目标时段已开始"
                )
            n("totalPowerForecast", value)
        except DispatchServiceError as exc:
            if exc.http_status == 409:
                raise
            issue("单点预测", exc.detail, ["totalPowerForecast", DEPENDENT_RESULTS])
        except ValueError as exc:
            issue("单点预测", str(exc), ["totalPowerForecast", DEPENDENT_RESULTS])
    s("calculationStatus", "部分结果：未生成优化方案")
    detail = "；".join(f"{i['input']}：{i['reason']}" for i in issues)
    s("calculationDetail", detail or cause.detail)
    s(
        "unavailableResults",
        DEPENDENT_RESULTS
        + "；"
        + "；".join(
            name
            for item in issues
            for name in item["unavailable_results"]
            if name != DEPENDENT_RESULTS
        ),
    )
    write_work_log(
        {
            "stage": "platform_partial_results",
            "action": "partial_results",
            "snapshot_id": snapshot,
            "original_error": cause.detail,
            "input_issues": issues,
            "returned_results": [p["varname"] for p in numbers],
            "unavailable_results": [DEPENDENT_RESULTS, *[i["unavailable_results"] for i in issues]],
        }
    )
    return {"event_key": EVENT_KEY, "result_point": numbers, "extra_info": strings}
