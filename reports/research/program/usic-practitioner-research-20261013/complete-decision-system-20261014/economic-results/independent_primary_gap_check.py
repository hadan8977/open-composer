"""Small primary-result and bounded gap-entry check; no strategy/provider call."""
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
from datetime import UTC,datetime
from decimal import Decimal

resource.setrlimit(resource.RLIMIT_CPU,(28,30))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
assert os.sched_getaffinity(0)=={0}
def load(p): return json.loads(p.read_text())
assert load(R/"reports/research/control/owner-compute-hold.json")["research_paused"] is False
task=next(t for t in load(R/"reports/research/control/day-goal.json")["tasks"] if t.get("id")=="MARTIN-COMPLETE-DECISION-SYSTEM-20261014")
assert task["owner"]=="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5" and task["status"]=="running_complete_task"
def bind(p):
    with p.open("rb") as f: sha=hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
def walk(x):
    if isinstance(x,dict):
        if "path" in x and "sha256" in x: yield x
        else:
            for a in x.values(): yield from walk(a)
    elif isinstance(x,list):
        for a in x: yield from walk(a)
packet=load(E/"primary-result-and-gap-review-packet.json")
checked=[]
for b in walk(packet):
    p=R/b["path"];assert p.stat().st_size<2_000_000,p
    actual=bind(p);assert actual["sha256"]==b["sha256"] and ("bytes" not in b or actual["bytes"]==b["bytes"]),b
    checked.append(actual)
interpret=load(R/packet["interpretation"]["path"])
addendum=load(R/packet["addendum"]["path"])
inputmeta=load(R/packet["existing_input"]["path"])
scope=load(R/packet["gap_scope"]["path"])
assert len(scope["requests"])==2 and scope["request_upper"]==2 and scope["entity_upper"]==400000
assert scope["prospective_input_CPU_upper"]==80
assert [q["day"] for q in scope["requests"]]==["2024-09-13","2025-02-11"]
for q in scope["requests"]:
    assert q["params"]["symbols"]=="LMND" and q["params"]["timeframe"]=="1Min"
    assert q["params"]["adjustment"]=="raw" and q["params"]["feed"]=="sip" and q["params"]["asof"]=="-"
    row=next(x for x in inputmeta["sessions"] if x.get("symbol")=="LMND" and x.get("day")==q["day"])
    assert q["first_unknown_utc"] in row["missing"],row
calendar=sorted({x["day"] for x in inputmeta["sessions"] if "2024-01-02"<=x.get("day","")<="2024-09-12"})
assert len(calendar)==176
common_end=int(datetime(2024,9,12,20,tzinfo=UTC).timestamp())*10**9-2
verification=dict(packet=bind(E/"primary-result-and-gap-review-packet.json"),checked_small_bindings=checked,common_calendar_sessions=len(calendar),results={},sampled_logs=[],whole_log_or_Frame_scan=False,full176_NAV_metric_replay=False,new_HTTP=0,new_strategy_execution=0)
def save(): (E/"primary-independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
save()
for cid,b in packet["result_bindings"].items():
    result=load(R/b["path"]);case=interpret["cases"][cid];metric=interpret["common_known_daily_prefix"][cid]
    assert result["cell"]["cell_id"]==cid and result["status"]=="unknown_continuous_path"
    assert all(result[k] is None for k in ("closed_attempt_R","open_positions","terminal_cash","terminal_equity"))
    assert result["full_source_clock_complete"] is False and result["paper_ready_pass"] is False
    unknown=result["first_unknown"];last=result["last_known_account"]
    assert unknown["at_ns"]-last["at_ns"]==4
    assert last==unknown["last_known_NAV"]
    assert unknown["quantities"]["LMND"]==(21 if False else 28 if cid.startswith("P_EMA") else 25)
    dt=datetime.fromtimestamp(unknown["at_ns"]//10**9,UTC).isoformat()
    expect="2024-09-13T14:01:00+00:00" if cid.startswith("P_EMA") else "2025-02-11T15:29:00+00:00"
    assert dt==expect and case["first_unknown_utc"]==expect
    closed=result["known_prefix_closed_attempt_R"]
    assert closed==unknown["known_prefix_closed_R"] and len(closed)==(21 if cid.startswith("P_EMA") else 9)
    assert case["known_closed_attempts"]==len(closed) and abs(case["known_closed_R_sum"]-sum(closed))<1e-12
    assert case["full_period_return"] is None and case["holding_conclusions_after_unknown"] is None
    assert metric["sessions"]==176 and metric["full_period_performance"] is False and metric["Sharpe_excess_BIL"] is None
    fills=[x for x in case["known_fill_tape"] if datetime.fromisoformat(x["at"].replace("Z","+00:00"))<=datetime(2024,9,12,20,tzinfo=UTC)]
    fees=sum(Decimal(str(x["fee"])) for x in fills)
    adds=addendum["matched_fill_counts"][cid]
    assert len(fills)==adds["common_known_prefix_fill_events"]
    assert fees==Decimal(str(adds["common_known_prefix_fees_USD"]))
    buys=sum(len(x["intent_id"])==24 and "-" not in x["intent_id"] for x in fills)
    assert buys==adds["buy_fill_events"] and len(fills)-buys==adds["sell_fill_events"]
    folder=E/cid
    # One requested endpoint neighborhood, not the whole176-session NAV history.
    navpath=folder/"2024-09-NAV.jsonl.gz";n=0;endpoint=None
    with gzip.open(navpath,"rt") as f:
        for line in f:
            n+=1;x=json.loads(line)
            if x["at_ns"]==common_end: endpoint=x;break
            if x["at_ns"]>common_end: break
    assert endpoint and endpoint["daily_close"] is True
    assert abs(endpoint["equity"]/20000-1-metric["marked_return"])<1e-12
    verification["sampled_logs"].append(dict(path=str(navpath.relative_to(R)),binding=bind(navpath),rows_read_to_endpoint=n,scope="September prefix only through common endpoint"))
    # Only the month containing the firstunknown, stop at its first witness.
    auditpath=folder/(expect[:7]+"-audit.jsonl.gz");n=0;witness=None
    with gzip.open(auditpath,"rt") as f:
        for line in f:
            n+=1;x=json.loads(line)
            if x["action"]=="first_unknown": witness=x;break
    assert witness and witness["first_unknown"]==unknown
    verification["sampled_logs"].append(dict(path=str(auditpath.relative_to(R)),binding=bind(auditpath),rows_read_to_unknown=n,scope="firstunknown-month audit through first witness only"))
    verification["results"][cid]=dict(first_unknown_utc=dt,first_unknown_ns=unknown["at_ns"],quantity_LMND=unknown["quantities"]["LMND"],own_prefix_closed_attempts=len(closed),common_prefix_fill_events=len(fills),common_prefix_fees=str(fees),common_endpoint_equity=endpoint["equity"],common_marked_return=metric["marked_return"],full_return=None)
    save()
ledgers=[load(p) for p in (E/"reservations").glob("*.json")]
assert all(x["status"]=="settled" for x in ledgers)
used=sum(Decimal(str(x["charged_CPU"])) for x in ledgers)
assert used==Decimal("3641.68333"),used
assert Decimal("7176.73")-used==Decimal("3535.04667")
trial=[json.loads(x) for x in (E/"trial-ledger.jsonl").read_text().splitlines()]
starts=[x for x in trial if x["status"]=="started"]
assert len(starts)==5 and len({x["cell_id"] for x in starts})==4
assert sum(x["status"]=="unknown_continuous_path" for x in trial)==4
account=load(P/"cumulative-accounting.json")
assert account["original_market_requests_used"]+account.get("new_market_requests",0)==80
assert 134217728-account["original_market_entity_bytes_used"]-account.get("new_market_entity_bytes",0)==78902258
code=(R/packet["gap_code"]["path"]).read_text();ast.parse(code)
assert code.index('approval =')<code.index('claim_launch(job')<code.index('native_admission(job)')<code.index('_load_env()')
assert code.index('save(account_path, account)')<code.index('body, meta = bounded_get(')
assert 'follow_redirects=False' in (R/packet["transport"]["path"]).read_text()
verification.update(completed=True,used_economic_CPU=str(used),remaining_economic_CPU="3535.04667",market_requests_used=80,market_entity_remaining=78902258,physical_account_starts=5,distinct_definitions=4,unknown_outcomes=4,full_valid_return_count=0,scope_code_static_acceptance=True,grant_not_executed=True)
u=resource.getrusage(resource.RUSAGE_SELF);verification["own_CPU"]=u.ru_utime+u.ru_stime;verification["RSS_KiB"]=u.ru_maxrss
save()
print(json.dumps(dict(status="passed",own_CPU=verification["own_CPU"],cases=verification["results"])))
