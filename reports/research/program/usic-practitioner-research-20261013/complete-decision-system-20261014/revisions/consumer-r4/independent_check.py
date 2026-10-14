"""Bounded affected r4 checks. Synthetic data only; no native CLI or market files."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from decimal import Decimal
from types import SimpleNamespace as NS
import tempfile

resource.setrlimit(resource.RLIMIT_CPU, (48, 52))
R = Path.cwd()
P = R / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D = P / "revisions/consumer-r4"
sys.path.insert(0, str(P / "code"))
import consumer_admission as gate
authority = gate.authority()
assert os.sched_getaffinity(0) == {0}

def load(p): return json.loads(p.read_text())
def bind(p):
    assert p.stat().st_size < 2_000_000, p
    with p.open("rb") as f: sha = hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
def recurse(x):
    if isinstance(x,dict):
        if "path" in x and "sha256" in x: yield x
        else:
            for v in x.values(): yield from recurse(v)
    elif isinstance(x,list):
        for v in x: yield from recurse(v)

packet = load(D / "review-packet.json")
manifest = load(P / "consumer-implementation-manifest.json")
assert bind(P / "consumer-implementation-manifest.json") == packet["manifest"]
assert packet["manifest"]["sha256"] == "d51957a4b32803fdd32a5092cbef2ead8ee08ec51277e5c8a49529c5e2edf2d0"
old = load(D / "before-consumer-implementation-manifest.json")
prior = {b["path"]:b for b in recurse(old)}
fresh = []
inherited = []
for b in recurse(manifest):
    if prior.get(b["path"]) == b:
        inherited.append(b)
    else:
        actual = bind(R / b["path"])
        assert actual["sha256"] == b["sha256"] and ("bytes" not in b or actual["bytes"] == b["bytes"]), b
        fresh.append(actual)
for b in recurse(packet):
    actual=bind(R / b["path"])
    assert actual["sha256"] == b["sha256"] and ("bytes" not in b or actual["bytes"] == b["bytes"]), b
frames=load(P / "frame-preparation-result.json")
assert len(frames["outputs"])==25
assert {Path(b["path"]).name[:7] for b in frames["outputs"]} == {"2023-12"}|{f"{y}-{m:02d}" for y in (2024,2025) for m in range(1,13)}
job=load(R / frames["manifest"]["path"])
for b in job["files"]:
    now=bind(R / b["path"])
    if now != b:
        match=[s for s in manifest["prepared_frame_provenance_substitutions"] if s["source"]==b]
        assert len(match)==1 and match[0]["role"]=="admission_only_no_feature_change"
        assert bind(R / match[0]["archived"]["path"])==match[0]["archived"]
        assert b["sha256"]==match[0]["archived"]["sha256"]
        assert b["path"].endswith("/code/consumer_admission.py")
ledgers=[load(p) for p in (P / "economic-results/reservations").glob("*.json")]
assert len(ledgers)==2 and all(r["status"]=="settled" for r in ledgers)
consumed=sum(Decimal(str(r["charged_CPU"])) for r in ledgers)
assert consumed==Decimal("1674.98333")
assert Decimal("7176.73")-consumed==Decimal("5501.74667")
assert not Path("/proc/1493044").exists(), "old PID unexpectedly exists; inspect before relying on exit"
verification=dict(packet=bind(D/"review-packet.json"),manifest=packet["manifest"],fresh_small_bindings=fresh,inherited_not_rehashed=inherited,
                 frames25_inventory_only=True,large_Frame_and_input_values_not_read=True,actual_authority=authority["task"],
                 consumed_CPU=str(consumed),remaining_original_CPU="5501.74667",old_PID_absent=True,synthetic_checks=[])
def save(): (D/"independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
save()

from verify_feed_reuse import source, replay
from nautilus_policy_adapter import FrameDecoder, decode_frame, MartinBoundaryData
from native_events import causal_activity
from native_engine import make_engine
from decision_system import read_parameters
from test_decision_system import SPEC, frame
from dataclasses import asdict

decoder=FrameDecoder()
base=json.loads(json.dumps(asdict(frame()),default=lambda x:x.isoformat()))
for change in ({},{"first_retest":False},{"trigger_price_eligible":False},{"minute":1,"duration":5}):
    row=dict(base,**change)
    assert decoder.decode(row)==decode_frame(row)
row=json.loads(json.dumps(base));row["anchors"][0]["past_touches"]+=1
assert decoder.decode(row)==decode_frame(row)
verification["synthetic_checks"].append("5 full-field decoder equality checks")
for route,case,scenario in [("market",{},"O-H-L-C"),("market",{},"O-L-H-C"),("capped",{"partial":True},"O-H-L-C"),("market",{"missing":True,"split":True},"O-L-H-C")]:
    a=replay(source(**case),route,False,scenario)
    b=replay(source(**case),route,True,scenario)
    assert a==b,(route,case,scenario,[k for k in a if a[k]!=b[k]])
    verification["synthetic_checks"].append(dict(paired_reference_reuse=True,route=route,case=case,scenario=scenario))
    save()

# Actual grouped-mark callback must retain original quote-only effects even
# with a pre-existing unacknowledged partial and a differing boundary session.
engine,strategy=make_engine(read_parameters(SPEC),"P_SYSTEM","market",20,dict(spec="inert",input="inert",contract="inert"))
try:
    strategy.runtime_active_symbols={"SOFI"}
    strategy.session=8;strategy.month="2024-01"
    strategy.partial_fills["inert_pending"]=dict(quantity=1)
    event=MartinBoundaryData(stage="inactive_marks",frames_json=json.dumps([dict(symbol="LMND",price=12.3456)]),session_ordinal=9,month="2024-02",ts_event=100,ts_init=100)
    strategy.on_data(event)
    assert strategy.marks["LMND"]==12.3456
    assert (strategy.session,strategy.month)==(8,"2024-01") and not strategy.book.path_unknown
    assert "inert_pending" in strategy.partial_fills
    verification["synthetic_checks"].append("Grouped inactive mark retains session/month and partial state; does not advance firstunknown")
finally: engine.dispose()

# Envelope retains all native or controller exposures, even on flat policy
# disagreement; missing daily leadership remains fail-open in the morning.
def state(**kw): return NS(**dict(quantity=0,pending=None,pending_exit=None,protective=None,**kw))
symbol=lambda s:NS(instrument_id=NS(symbol=NS(value=s)))
stub=NS(policy=NS(states={"HELD":NS(quantity=1,pending=None,pending_exit=None,protective=None)}),
        cache=NS(positions_open=lambda:[symbol("NATIVEPOS")],orders_open=lambda:[symbol("NATIVEORDER")]),
        staged_entries={"x":NS(symbol="STAGEDBUY")},staged_exits={"x":NS(symbol="STAGEDEXIT")},cancel_then_sell={"x":NS(symbol="CANCELSELL")},
        config=NS(parameters={"entry_cutoff_minute":120}),ids={"MISSINGLEADER":1},runtime_prior_leadership={})
row=dict(minute=121,session="2024-01-02",start="2024-01-02T16:31:00+00:00")
assert causal_activity(stub,row,afternoon=True)=={"HELD","NATIVEPOS","NATIVEORDER","STAGEDBUY","STAGEDEXIT","CANCELSELL"}
assert "MISSINGLEADER" in causal_activity(stub,dict(row,minute=2),afternoon=False)
verification["synthetic_checks"].append("Exposure unions and missing-leadership morning fail-open")

# Settlement must preserve actual overrun, not throw away evidence or reset
# the original pool. This fixture has no relation to the author ledger.
oldP,oldusage=gate.P,gate.usage
try:
    with tempfile.TemporaryDirectory() as tmp:
        gate.P=Path(tmp)
        folder=gate.P/"economic-results/reservations";folder.mkdir(parents=True)
        (gate.P/"cumulative-accounting.json").write_text(json.dumps(dict(new_measured_economic_CPU=0)))
        row=dict(status="admitted",runtime_actual_CPU=0,runtime_CPU_upper=0,empirical_CPU_upper=10,launcher_unknown_CPU=5)
        (folder/"inert.json").write_text(json.dumps(row))
        gate.usage=lambda:(6,1)
        gate.settle("inert","inert_failed")
        settled=load(folder/"inert.json")
        assert settled["charged_CPU"]==12 and settled["empirical_cap_overrun_CPU"]==2 and settled["status"]=="settled"
        try: gate.settle("inert","duplicate")
        except AssertionError: pass
        else: raise AssertionError("duplicate settle accepted")
finally: gate.P,gate.usage=oldP,oldusage
verification["synthetic_checks"].append("Overrun charged honestly; duplicate settlement refused")
verification["completed"]=True
verification["actual_own_CPU"]=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
verification["RSS_KiB"]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
save()
print(json.dumps(dict(status="passed",checks=verification["synthetic_checks"],own_CPU=verification["actual_own_CPU"])))
