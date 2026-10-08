"""Validate the delivered 96-step response without confusing statistics with predictions."""

from src.vendor.dayahead.contract import forecast_curve, forecast_metadata


def validate_day_response(body):
    curve = forecast_curve(body)
    forecast_metadata(body)
    expected = {"forecastPointCount": 96.0, "forecastIntervalMinutes": 15.0}
    seen = set()
    for point in body["result_point"]:
        name = point["varname"]
        if name in expected:
            if name in seen or point["value"] != expected[name]:
                raise ValueError("Invalid forecast statistics")
            seen.add(name)
    return curve
