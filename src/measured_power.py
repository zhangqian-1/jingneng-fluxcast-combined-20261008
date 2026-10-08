"""Generator measurements: zero is valid; finite negative power becomes zero."""

from src.input_quality import write_work_log
from src.platform_config import STATION_MEASUREMENT_POINTS, platform_point_name
from src.single_period_models import nonnegative

POWER_POINTS = {
    key
    for points in STATION_MEASUREMENT_POINTS.values()
    for point in points
    for key in (point, platform_point_name(point))
}


def measured_power(value, *, audit=None):
    # Keep null, booleans, strings and nonfinite values separate from shutdown.
    if type(value) not in (int, float):
        return nonnegative(value)
    nonnegative(abs(value))
    if value < 0:
        if audit is not None:
            write_work_log(
                {
                    **audit,
                    "stage": "measured_power_normalization",
                    "policy": "generator_negative_to_zero_v1",
                    "action": "negative_power_to_zero",
                    "original_value": value,
                    "replacement_value": 0.0,
                }
            )
        return 0.0
    return float(value)


def forecast_power_request(body):
    """Copy only frames; do not mutate raw input, weather, IDs or timestamps."""
    if not isinstance(body, dict) or not isinstance(body.get("frames"), list):
        return body
    frames = []
    for frame in body["frames"]:
        if not isinstance(frame, dict):
            frames.append(frame)
            continue
        normalized = dict(frame)
        for key in POWER_POINTS.intersection(frame):
            value = frame[key]
            if type(value) in (int, float) and value < 0:
                try:
                    normalized[key] = measured_power(
                        value,
                        audit={
                            "series": key,
                            "timestamp": frame.get("timestamp"),
                            "basis": "forecast_input",
                        },
                    )
                except ValueError:
                    # Invalid values still follow the existing upstream validation.
                    pass
        frames.append(normalized)
    return {**body, "frames": frames}
