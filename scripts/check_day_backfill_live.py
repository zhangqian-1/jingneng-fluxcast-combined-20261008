"""Exercise seven public day-only history batches in a disposable combined container."""

import argparse
import csv
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ROUTE = "/api/v1/fluxcast/day-forecast/compute"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, encoding="utf-8").strip()


def protected_files(container):
    code = """import hashlib,json
from pathlib import Path
roots=[Path('/opt/forecast-single/runtime'),Path('/app/runtime')]
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                  for root in roots for p in root.rglob('*')
                  if p.is_file() and 'logs' not in p.relative_to(root).parts}))
"""
    return json.loads(docker("exec", container, "/usr/local/bin/python", "-c", code))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    container = "day-backfill-check-" + uuid.uuid4().hex[:10]
    docker("run", "-d", "--name", container, "-p", "127.0.0.1::8000", args.image)
    try:
        port = docker("port", container, "8000/tcp").rsplit(":", 1)[1]
        base = "http://127.0.0.1:" + port
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                with urlopen(base + "/health", timeout=5) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Temporary container did not start")

        before = protected_files(container)
        with (ROOT / "docs/forecast-measurement-points.csv").open(encoding="utf-8-sig") as stream:
            points = [row["raw_name"] for row in csv.DictReader(stream)]
        tables = []
        for path in (ROOT / "data").rglob("*.csv"):
            fields = set(pd.read_csv(path, nrows=0).columns)
            selected = [p for p in points if p in fields]
            if selected and "ts" in fields:
                frame = pd.read_csv(path, usecols=["ts", *selected])
                frame.index = pd.to_datetime(frame.pop("ts")).dt.tz_localize("Asia/Shanghai")
                tables.append(frame)
        history = pd.concat(tables, axis=1).sort_index()

        def post(body):
            request = Request(
                base + ROUTE,
                data=json.dumps(body, allow_nan=False).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                response = urlopen(request, timeout=180)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)

        invalid_status, _ = post({"point_table": [], "frames": []})
        assert invalid_status == 400, invalid_status
        reports = []
        for day in range(7):
            start = pd.Timestamp("2025-10-06", tz="Asia/Shanghai") + pd.Timedelta(days=day)
            axis = pd.date_range(start, periods=96, freq="15min")
            frames = json.loads(history.loc[axis, points].to_json(orient="records"))
            for stamp, frame in zip(axis, frames, strict=True):
                frame["timestamp"] = stamp.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
            status, body = post({"point_table": points, "frames": frames})
            assert status == 200, body
            curve = [p for p in body["result_point"] if p["varname"] == "totalPowerForecast"]
            if day < 6:
                assert not curve and body["reason"] == "history_not_ready", body
                assert body["continuous_points"] == 96 * (day + 1), body
            else:
                assert len(curve) == 96, body
                assert len(body["result_point"]) == 98, body
                assert any(p["varname"] == "forecastBatchId" for p in body["extra_info"])
                assert pd.Timestamp(curve[0]["timestamp"]) == axis[-1] + pd.Timedelta(minutes=15)
            reports.append(
                {
                    "batch": day + 1,
                    "status": status,
                    "points": len(curve),
                    "reason": body.get("reason"),
                }
            )
            print(json.dumps(reports[-1]), flush=True)
        assert protected_files(container) == before, "Single/dispatch state changed during backfill"
        report = {
            "passed": True,
            "image_id": docker("inspect", container, "--format", "{{.Image}}"),
            "route": ROUTE,
            "batches": reports,
            "single_and_dispatch_unchanged": True,
            "full_day_response_preserved": True,
            "invalid_request_status": invalid_status,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", container], check=True)


if __name__ == "__main__":
    main()
