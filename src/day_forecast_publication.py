"""Publish one complete Beijing calendar-day curve through the dispatch response."""

from __future__ import annotations

import json
import math
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from src.day_forecast_contract import validate_day_response
from src.errors import DispatchServiceError
from src.forecast_bridge import EVENT_KEY
from src.input_quality import write_work_log
from src.single_period_models import STEP, utc_time

DAY_VARNAME = "totalPowerForecastDayAhead"
BEIJING = ZoneInfo("Asia/Shanghai")


def validate_curve(body, anchor):
    if body.get("event_key") != EVENT_KEY:
        raise ValueError("event_key")
    points = body.get("result_point")
    if points == [] and body.get("reason") in ("history_not_ready", "weather_history_not_ready"):
        return [], body["reason"]
    validate_day_response(body)
    points = [p for p in points if p["varname"] == "totalPowerForecast"]
    checked = []
    for n, point in enumerate(points):
        stamp = anchor + (n + 1) * STEP
        if (
            point["varname"] != "totalPowerForecast"
            or utc_time(point["timestamp"]) != stamp
            or type(point["value"]) not in (float, int)
            or not math.isfinite(point["value"])
            or point["value"] < 0
        ):
            raise ValueError("invalid prediction axis or value")
        checked.append(
            {"varname": DAY_VARNAME, "timestamp": stamp.isoformat(), "value": float(point["value"])}
        )
    return checked, "ready"


class DayForecastPublisher:
    def __init__(self, client, store, *, recovery=None):
        self.client, self.store = client, store
        self.recovery = recovery
        with store.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS day_forecast_curve "
                "(day TEXT PRIMARY KEY, anchor TEXT NOT NULL, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS day_forecast_publication "
                "(day TEXT PRIMARY KEY, anchor TEXT NOT NULL, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS day_forecast_source "
                "(day TEXT PRIMARY KEY, body TEXT NOT NULL, received_at REAL NOT NULL)"
            )

    def _save_curve(self, day, identity, curve, body):
        with self.store.connection() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO day_forecast_curve VALUES (?, ?, ?)",
                (day, identity, json.dumps(curve, allow_nan=False)),
            ).rowcount
            if inserted:
                db.execute(
                    "INSERT INTO day_forecast_source VALUES (?, ?, ?)",
                    (
                        day,
                        json.dumps(body, allow_nan=False),
                        datetime.now(timezone.utc).timestamp(),
                    ),
                )

    def published_source(self, request):
        day = utc_time(request["frames"][-1]["timestamp"]).astimezone(BEIJING).date().isoformat()
        with self.store.connection() as db:
            row = db.execute(
                "SELECT s.body, s.received_at FROM day_forecast_source s "
                "JOIN day_forecast_publication p ON p.day=s.day WHERE s.day=?",
                (day,),
            ).fetchone()
        # Old cached curves lack trustworthy generation metadata; never fabricate it.
        return (json.loads(row[0]), row[1]) if row else None

    def observe(self, request):
        anchor = utc_time(request["frames"][-1]["timestamp"])
        identity = anchor.isoformat()
        # Always feed history, including while the optimizer is warming.
        # The unmodified model needs seven days and must never be backdated after
        # it has consumed later observations. Only its midnight-aligned output
        # is eligible for the calendar-day display; rolling curves are not stitched.
        try:
            status, body = self.client.request(request)
            if status != 200:
                raise DispatchServiceError(502, "DAY_FORECAST_UPSTREAM_ERROR", "全天预测服务未成功")
            curve, model_status = validate_curve(body, anchor)
            start = (anchor + STEP).astimezone(BEIJING)
            if curve and start.time() == time(0):
                self._save_curve(start.date().isoformat(), identity, curve, body)
        except DispatchServiceError:
            model_status = "unavailable"
        except (KeyError, TypeError, ValueError, OverflowError):
            model_status = "invalid_response"
        if self.recovery is not None:
            local_start = anchor.astimezone(BEIJING).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            day = local_start.date().isoformat()
            with self.store.connection() as db:
                exists = db.execute(
                    "SELECT 1 FROM day_forecast_curve WHERE day=?", (day,)
                ).fetchone()
            if not exists:
                model_status = self._recover(day, local_start - STEP)
        return model_status

    def _recover(self, day, cutoff):
        body = self.recovery.recover(day)
        reason = body.get("reason")
        if body.get("result_point") == [] and reason in (
            "recovery_history_not_ready",
            "recovery_weather_history_not_ready",
            "recovery_unavailable",
            "recovery_invalid_response",
        ):
            state = reason
        else:
            try:
                curve, _ = validate_curve(body, cutoff.astimezone(timezone.utc))
                if not curve:
                    raise ValueError("Empty recovery result")
                self._save_curve(day, cutoff.astimezone(timezone.utc).isoformat(), curve, body)
                state = "recovered"
            except (KeyError, TypeError, ValueError, OverflowError):
                state = "recovery_invalid_response"
        write_work_log(
            {
                "stage": "day_forecast_recovery",
                "action": state,
                "day": day,
                "history_cutoff": cutoff.isoformat(),
                "history": body.get("recovery_info"),
            }
        )
        return state

    def process(self, request, *, successful, now, model_status=None):
        anchor = utc_time(request["frames"][-1]["timestamp"])
        local = anchor.astimezone(BEIJING)
        day, identity = local.date().isoformat(), anchor.isoformat()
        with self.store.connection() as db:
            published = db.execute(
                "SELECT anchor, body FROM day_forecast_publication WHERE day=?", (day,)
            ).fetchone()
        if successful and published and published[0] == identity:
            return json.loads(published[1]), "replayed"
        if model_status is None:
            model_status = self.observe(request)

        if not successful:
            result, state = [], "optimization_pending"
        elif published:
            result, state = [], "already_published"
        elif local.date() != now.astimezone(BEIJING).date():
            result, state = [], "outside_publication_day"
        elif anchor > now:
            result, state = [], "future_observation"
        else:
            # The transaction is the cross-process arbiter: at most one anchor
            # owns this day's batch. Replay the winner on response-loss retries.
            with self.store.connection() as db:
                existing = db.execute(
                    "SELECT anchor, body FROM day_forecast_publication WHERE day=?", (day,)
                ).fetchone()
                candidate = db.execute(
                    "SELECT body FROM day_forecast_curve WHERE day=?", (day,)
                ).fetchone()
                if existing:
                    result, state = (
                        (json.loads(existing[1]), "replayed")
                        if existing[0] == identity
                        else ([], "already_published")
                    )
                elif candidate:
                    db.execute(
                        "INSERT INTO day_forecast_publication VALUES (?, ?, ?)",
                        (day, identity, candidate[0]),
                    )
                    result, state = json.loads(candidate[0]), "published"
                else:
                    result, state = (
                        [],
                        "day_curve_missing" if model_status == "ready" else model_status,
                    )
        write_work_log(
            {
                "stage": "day_forecast_publication",
                "action": state,
                "model_status": model_status,
                "day": day,
                "anchor": anchor.astimezone(timezone.utc).isoformat(),
                "points": len(result),
            }
        )
        return result, state
