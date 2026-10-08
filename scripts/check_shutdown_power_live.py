"""Verify the reported shutdown values through the real combined-image API.

Use an isolated verification container warmed by check_forecast_bridge_live.py.
Advances its test history by 15 minutes; never target a production container.
"""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.container.startswith("fluxcast-single-verify-"):
        raise ValueError("Only an isolated verification container is allowed")
    harness = """import json, os, socket, sys, tempfile, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uvicorn
import api
from src.forecast_bridge import ForecastClient, ForecastDispatchBridge
from src.single_period_service import SinglePeriodService

body=json.load(sys.stdin)
for frame in body['frames']:
    shifted=datetime.fromisoformat(frame['timestamp'])+timedelta(minutes=15)
    frame['timestamp']=shifted.strftime('%Y-%m-%d %H:%M:%S')
    frame.update(SZRD_10DCS02FA133=0.0, SZRD_10DCS02FA134=0.0,
                 JQRD_11MBL11CT010XQ01=17.76, JQRD_10CBA00FA108XQ93=-0.2)
observed=datetime.fromisoformat(body['frames'][-1]['timestamp']).replace(tzinfo=timezone.utc)
folder=Path(tempfile.mkdtemp(prefix='shutdown-verification-',dir='/app/runtime'))
os.environ['WORK_LOG_PATH']=str(folder/'work.jsonl')
bridge=ForecastDispatchBridge(ForecastClient(os.environ['FORECAST_BASE_URL'],timeout=120),
    SinglePeriodService(folder/'state.sqlite3',clock=lambda:observed+timedelta(seconds=1)))
api.get_forecast_bridge=lambda:bridge
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(api.app,log_level='error',lifespan='off'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
for _ in range(200):
    if server.started:break
    time.sleep(0.025)
assert server.started
try:
    def send():
        req=Request('http://127.0.0.1:'+str(port)+'/api/v1/fluxcast/compute',
                    data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=180) as response:
                assert response.status==200
                return json.load(response)
        except HTTPError as exc:raise RuntimeError(exc.read().decode()) from exc
    def advance():
        global observed
        observed += timedelta(minutes=15)
        for frame in body['frames']:
            shifted=datetime.fromisoformat(frame['timestamp'])+timedelta(minutes=15)
            frame['timestamp']=shifted.strftime('%Y-%m-%d %H:%M:%S')
    result=send()
    advance()
    body['renewable_data']=[r for r in body['renewable_data'] if r['farmId']!=29]
    partial=send()
    names={p['varname'] for p in partial['result_point']}
    assert {'SZRD_actualMW','farm_1_available_MW','totalPowerForecast'} <= names
    assert not {'GARD_MW','grid_buy_MW','farm_29_available_MW','objectiveYuan'} & names
    assert any(p['varname']=='calculationStatus' for p in partial['extra_info'])
    advance()
    for frame in body['frames']:frame['GARD_11MBY0100000BJ01XQ01']=None
    missing=send()
    names={p['varname'] for p in missing['result_point']}
    assert {'SZRD_actualMW','farm_1_available_MW'} <= names
    assert not {'GARD_actualMW','totalPowerForecast','GARD_MW'} & names
finally:
    server.should_exit=True;thread.join(timeout=5)
values={p['varname']:p['value'] for p in result['result_point']}
labels={p['varname']:p['value'] for p in result['extra_info']}
assert values['SZRD_actualMW']==0
assert labels['SZRD_actualStatus']=='实测有效'
assert '负功率归零' in labels['JQRD_actualStatus']
assert labels['balanceStatus']=='供需平衡'
records=[json.loads(line) for line in (folder/'work.jsonl').read_text().splitlines()]
clamps=[r for r in records if r.get('series')=='JQRD_10CBA00FA108XQ93'
        and r.get('action')=='negative_power_to_zero']
assert any(r.get('basis')=='forecast_input' for r in clamps)
assert any(r.get('basis')=='thermal_power_history' for r in clamps)
assert all(r['original_value']==-0.2 and r['replacement_value']==0 for r in clamps)
print(json.dumps({'passed':True,'zero_power_accepted':True,'negative_generator_clamped':True,
                 'real_single_and_day_models':True,'real_optimizer_completed':True,
                 'partial_results_verified':True,
                 'numeric_points':len(result['result_point']),'production_modified':False}))
"""
    process = subprocess.run(
        ["docker", "exec", "-i", args.container, "/app/.venv/bin/python", "-c", harness],
        input=args.request.read_text("utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=240,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr)
    report = json.loads(process.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
