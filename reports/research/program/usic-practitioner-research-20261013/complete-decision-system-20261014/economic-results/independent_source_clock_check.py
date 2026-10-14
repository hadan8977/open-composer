"""Source-clock scientific evidence check only; no native or price-path replay."""
import calendar
from collections import Counter
from datetime import UTC,datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import resource
resource.setrlimit(resource.RLIMIT_CPU,(15,18))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
assert os.sched_getaffinity(0)=={0}
def load(p): return json.loads(p.read_text())
assert load(R/"reports/research/control/owner-compute-hold.json")["research_paused"] is False
task=next(t for t in load(R/"reports/research/control/day-goal.json")["tasks"] if t.get("id")=="MARTIN-COMPLETE-DECISION-SYSTEM-20261014")
assert task["owner"]=="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5" and task["status"]=="running_complete_task"
def bind(p):
    raw=p.read_bytes();return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def walk(x):
    if isinstance(x,dict):
        if "path" in x and "sha256" in x: yield x
        else:
            for a in x.values(): yield from walk(a)
    elif isinstance(x,list):
        for a in x: yield from walk(a)
packet=load(E/"source-clock-scientific-review-packet.json");b=packet["bindings"]
plan=load(R/b["plan"]["path"])
seen=set();checks=[]
for item in list(walk(packet))+list(walk(plan)):
    key=(item["path"],item["sha256"])
    if key in seen: continue
    seen.add(key);p=R/item["path"];assert p.stat().st_size<2_000_000
    actual=bind(p);assert actual["sha256"]==item["sha256"] and ("bytes" not in item or actual["bytes"]==item["bytes"]),item
    checks.append(actual)
def ns(t):
    m=re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z",t)
    assert m,t
    return calendar.timegm(datetime.fromisoformat(m[1]).timetuple())*10**9+int((m[2] or "0").ljust(9,"0"))
result=load(R/b["source_result"]["path"])
cases=[]
for item in packet["actual_source_binaries"]:
    name=Path(item["path"]).name;kind="quotes" if "quotes" in name else "trades"
    day="2024-09-13" if "2024-09-13" in name else "2025-02-11"
    low=ns(day+("T14:01:00Z" if day.startswith("2024") else "T15:29:00Z"));high=low+60*10**9
    payload=json.loads((R/item["path"]).read_bytes(),parse_float=Decimal)
    assert payload.get("next_page_token") is None and set(payload[kind])=={"LMND"}
    rows=payload[kind]["LMND"];times=[ns(x["t"]) for x in rows]
    assert times==sorted(times)
    assert all(low-60*10**9<=t<=high for t in times)
    central=[x for x,t in zip(rows,times) if low<=t<high]
    expected={("2024-09-13","quotes"):(379,135),("2024-09-13","trades"):(129,17),("2025-02-11","quotes"):(52,12),("2025-02-11","trades"):(101,41)}[(day,kind)]
    assert (len(rows),len(central))==expected
    match=next(x for x in result["cases"] if x["id"]==name[:-4])
    assert match["source_rows"]==len(rows) and match["central_missing_bar_minute_source_events"]==len(central)
    assert match["firm_NBBO_certified"] is False and match["coverage_gate_pass"] is False
    out=dict(day=day,kind=kind,source_rows=len(rows),central_events=len(central),source_times_sorted=True,whole_nanoseconds_preserved=True,duplicate_timestamp_extras=len(times)-len(set(times)),central_conditions=sorted({str(c) for x in central for c in x.get("c",[])}))
    if kind=="trades":
        assert all("I" in x["c"] for x in central)
        total=sum(Decimal(str(x["s"])) for x in central)
        assert total==(Decimal(264) if day.startswith("2024") else Decimal(749))
        out.update(all_observed_central_trades_have_I=True,central_trade_size_sum=str(total),condition_groups=[dict(conditions=list(k),count=n) for k,n in sorted(Counter(tuple(x["c"]) for x in central).items())])
    cases.append(out)
assert sum(x["bytes"] for x in packet["actual_source_binaries"])==72163
ledgers=[load(p) for p in (E/"reservations").glob("*.json")]
assert all(x["status"]=="settled" for x in ledgers)
used=sum(Decimal(str(x["charged_CPU"])) for x in ledgers)
assert used==Decimal("3697.01333"),used
assert Decimal("7176.73")-used==Decimal("3479.71667")
source_cpu=load(R/b["source_CPU"]["path"]);assert Decimal(str(source_cpu["charged_CPU"]))==Decimal("26.35")
docs=load(R/b["primarydocs"]["path"]);passages=load(R/b["primarypassages"]["path"])
assert isinstance(docs,str) and isinstance(passages,str)
lines=(docs+"\n"+passages).splitlines()
selected=[]
for i,line in enumerate(lines):
    if any(s in line.lower() for s in ("strictest","empty","odd lot","not outside of the nbbo","round lots")):
        selected.extend(lines[max(0,i-1):min(len(lines),i+2)])
selected=list(dict.fromkeys(selected))
assert "not outside of the NBBO" in passages
verification=dict(packet=bind(E/"source-clock-scientific-review-packet.json"),bindings_checked=checks,actual_source_cases=cases,actual_source_entity_bytes=72163,source_fetch_charge_CPU=26.35,used_original_economic_CPU=str(used),remaining_original_CPU="3479.71667",reported_nonpromotable_source_only=True,whole_market_coverage_proven=False,broker_stop_elected_or_fill_reconstructed=False,old_unknown_paths_healed=False,source_clock_plan_only=True,source_passages_reviewed=selected,new_HTTP_native_implementation_economic_jobs=0,completed=True)
(E/"source-clock-independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
print(json.dumps(dict(status="source_verified",cases=cases,decisive_passages=selected),ensure_ascii=False))
