"""Reuse the upstream measured-power service against the published calendar batch only."""

from pathlib import Path

from src.vendor.dayahead.contract import POINTS
from src.vendor.dayahead.storage import Store


def append_day_results(body, publisher, request, state, format_time):
    # A sidecar keeps measurement persistence separate from the optimizer's schema.
    path = Path(publisher.store.path)
    observations = Store(path.with_name(path.stem + "-day-observations.sqlite3"))
    published = publisher.published_source(request)
    if published is not None:
        source, received_at = published
        observations.archive(source, first_seen=received_at)
        if state in ("published", "replayed"):
            body["result_point"].extend(
                {**p, "timestamp": format_time(p["timestamp"])}
                for p in source["result_point"]
                if p["varname"] != "totalPowerForecast"
            )
            body["extra_info"].extend(
                {**p, "timestamp": format_time(p["timestamp"])}
                for p in source.get("extra_info", [])
            )
    frame = request["frames"][-1]
    measured = observations.receive(
        {
            "point_table": list(POINTS),
            "frames": [{k: v for k, v in frame.items() if k in POINTS or k == "timestamp"}],
        }
    )
    for group in ("result_point", "extra_info"):
        body[group].extend({**p, "timestamp": format_time(p["timestamp"])} for p in measured[group])
