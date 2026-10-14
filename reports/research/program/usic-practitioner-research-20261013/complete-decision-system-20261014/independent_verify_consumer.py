"""Independent bounded bindings and native inert checks, no market strategy run."""
import ast
import hashlib
import json
import os
import resource
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (50, 55))
assert os.sched_getaffinity(0) == {0}
P = Path(__file__).resolve().parent
ROOT = Path.cwd()
checked = {}
errors = []


def read(path):
    return json.loads(Path(path).read_text())


def verify(binding):
    path = Path(binding["path"]).resolve()
    key = str(path)
    if key not in checked:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b""):
                h.update(chunk)
        checked[key] = {"sha256": h.hexdigest(), "bytes": path.stat().st_size}
    if checked[key]["sha256"] != binding["sha256"] or ("bytes" in binding and checked[key]["bytes"] != binding["bytes"]):
        errors.append({"binding": binding, "actual": checked[key]})


def walk(x):
    if isinstance(x, dict):
        if "path" in x and isinstance(x.get("sha256"), str):
            verify(x)
        for v in x.values():
            walk(v)
    elif isinstance(x, list):
        for v in x:
            walk(v)


walk(read(P/"consumer-review-packet.json"))
walk(read(P/"consumer-implementation-manifest.json"))
inputs = read(P/"complete-input-v2-result.json")
for b in inputs["outputs"] + inputs["auxiliary_outputs"]:
    verify(b)
assert len(inputs["outputs"]) == 25
prefix = read(P/"inputs/frames-v2/completed-shards.json")
for b in prefix:
    verify(b)
walk(read(P/"frame-cache-verification.json"))
cmd = [str(ROOT/".venv/bin/python"), "-m", "pytest", "-q", str(P/"code/test_decision_system.py"), str(P/"code/test_consumer_protocol.py"), str(P/"code/test_nautilus_consumer.py"), "--junitxml="+str(P/"independent-consumer-tests.xml")]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
(P/"independent-consumer-tests.log").write_text(result.stdout+"\n"+result.stderr)
print(result.stdout[-1800:], flush=True)
assert result.returncode == 0
sys.path.insert(0, str(P/"code"))
import test_nautilus_consumer as t
from nautilus_trader.model.identifiers import ClientId

engine, strategy = t.make_engine()
ns = int(t.T.timestamp()*1e9)
row = dict(frame=asdict(t.frame()), leadership_score=1, prior_dollar_volume=1e7)
quotes = [t.quote("SOFI", ns-1), t.quote("SOFI", ns+4), t.quote("SOFI", ns+100_000_000_000, 9.5)]
engine.add_data([t.bookdata("SOFI", x.ts_event-1, x.bid_price.as_double()) for x in quotes])
engine.add_data(quotes)
engine.add_data([t.pack("close", ns+1, [row]), t.pack("open_exits", ns+5), t.pack("open_entries", ns+6), t.pack("missing", ns+60_000_000_000, ["SOFI"]), t.pack("mark", ns+120_000_000_000, {"daily_close": True})], client_id=ClientId("MARTIN"))
engine.run()
unknown = {"path_unknown": strategy.book.path_unknown, "closed_R_after_unknown": strategy.book.closed_R, "fills_after_missing": [x for x in strategy.audit if x["action"] == "native_full_fill" and x["native_at_ns"] > ns+60_000_000_000], "held_after": strategy.policy.states["SOFI"].quantity}
engine.dispose()
prep = ast.parse((P/"code/prepare_frames.py").read_text())
calls = sorted({ast.unparse(x.func) for x in ast.walk(prep) if isinstance(x, ast.Call)})
out = {"status": "review_checks_complete", "files_verified": checked, "binding_errors": errors, "normalized_months": 25, "prepared_prefix_shards": len(prefix), "pytest_returncode": result.returncode, "unknown_path_probe": unknown, "prepare_frames_static_calls": calls, "no_actual_market_strategy_or_fit_run": True, "CPU_affinity": [0]}
(P/"independent-consumer-verification.json").write_text(json.dumps(out, indent=2)+"\n")
print(json.dumps({"verified": len(checked), "errors": errors, "unknown_probe": unknown, "prefix": len(prefix)}))
