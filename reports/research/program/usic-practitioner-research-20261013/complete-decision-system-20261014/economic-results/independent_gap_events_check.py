"""Retained two-bar-source QA and isolated parser/entry review; no network."""
import ast
import calendar
from collections import Counter
from datetime import UTC,datetime,timedelta
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
packet=load(E/"gap-events-review-packet.json")
for key,b in packet["bindings"].items():
    assert (R/b["path"]).stat().st_size<2_000_000
    assert bind(R/b["path"])==b,key
b=packet["bindings"]
qa=load(R/b["raw_clock_QA"]["path"])
result=load(R/b["raw_gap_result"]["path"])
proof=[]
for i,(key,day,openhour,gap,n) in enumerate((("raw1","2024-09-13",13,"2024-09-13T14:01:00Z",334),("raw2","2025-02-11",14,"2025-02-11T15:29:00Z",384))):
    payload=json.loads((R/b[key]["path"]).read_bytes(),parse_float=Decimal)
    assert payload.get("next_page_token") is None and set(payload["bars"])=={"LMND"}
    rows=payload["bars"]["LMND"];times=[datetime.fromisoformat(x["t"].replace("Z","+00:00")) for x in rows]
    assert len(rows)==n and len(set(times))==n and times==sorted(times)
    op=datetime.fromisoformat(day+f"T{openhour:02d}:30:00+00:00");close=op+timedelta(minutes=390)
    expected={op+timedelta(minutes=j) for j in range(390)}
    inside=[t for t in times if op<=t<close]
    assert len(inside)==n-1 and set(times)-expected=={close}
    assert datetime.fromisoformat(gap.replace("Z","+00:00")) not in times
    for x,t in zip(rows,times):
        assert t.second==t.microsecond==0
        vals={k:Decimal(str(x[k])) for k in ("o","h","l","c","v","vw")}
        assert all(v.is_finite() for v in vals.values())
        assert vals["l"]>0 and vals["l"]<=min(vals["o"],vals["c"])<=max(vals["o"],vals["c"])<=vals["h"] and vals["v"]>=0
    a=qa["cases"][i]
    assert a["raw_list_rows"]==n and a["RTH_observed_rows"]==n-1 and a["RTH_missing_minutes"]==390-(n-1)
    assert not a["invalid_OHLC_volume_clock_rows"] and not a["duplicate_timestamp_counts"]
    c=next(x for x in result["comparisons"] if x["day"]==day)
    assert c["normalized_rows"]==n-1 and c["exact_overlap_rows"]==n-1 and c["differences"]==[]
    assert c["first_unknown_minute_in_raw"] is False and len(c["previously_missing"])==390-(n-1)
    proof.append(dict(day=day,raw_list_rows=n,unique_rows=n,RTH_rows=n-1,missing=390-(n-1),endpoint_outside_RTH=True,original_gap_still_absent=True))
assert sum(x["RTH_rows"] for x in proof)==716
assert b["raw1"]["bytes"]+b["raw2"]["bytes"]==72029
source=(R/b["code"]["path"]).read_text();tree=ast.parse(source)
funcs=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ("ns","summarize")]
assert len(funcs)==2
namespace=dict(re=re,calendar=calendar,datetime=datetime,Decimal=Decimal,Counter=Counter,json=json)
exec(compile(ast.Module(body=funcs,type_ignores=[]),"bound_parser_only","exec"),namespace)
ns=namespace["ns"];summarize=namespace["summarize"]
assert ns("2024-09-13T14:01:00.000000001Z")-ns("2024-09-13T14:00:59.999999999Z")==2
assert ns("2025-02-11T15:29:59.123456789Z")%10**9==123456789
scope=load(R/b["scope"]["path"]);assert len(scope["requests"])==4
assert sum(q["entity_cap"] for q in scope["requests"])==2500000
q=scope["requests"][0]
def quote(t,bp=10,ap=11,ex="A",c=None): return dict(t=t,bp=bp,ap=ap,bx=ex,ax=ex,bs=1,as_=1,c=c or [])
rows=[quote("2024-09-13T14:00:59.999999999Z"),quote("2024-09-13T14:01:00.000000001Z"),quote("2024-09-13T14:01:00.000000001Z",ex="B",c=["R"]),quote("2024-09-13T14:01:59.999999999Z",bp=12,ap=11),quote("2024-09-13T14:02:00.000000000Z",bp=0),quote("INVALID")]
summary=summarize(rows,q,None)
assert summary["central_missing_bar_minute_source_events"]==3
assert summary["shared_timestamp_extra_rows"]==1 and summary["exact_duplicate_message_extra_rows"]==0
assert summary["crossed_quote_rows"]==1 and summary["nonpositive_price_quote_rows"]==1
assert len(summary["invalid_timestamp_rows"])==1 and summary["complete_requested_interval"] is False
assert summary["firm_NBBO_certified"] is False and summary["coverage_gate_pass"] is False
assert summarize(rows[:-1],q,"MORE")["complete_requested_interval"] is False
main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="main")
main_text=ast.unparse(main)
# Scope promises invalid timestamp prevents later requests, but only page token
# is tested after summarize. This is an actual bound-code difference.
assert "invalid_timestamp_rows" not in main_text
assert "if token:" in main_text
badorder=summarize([rows[3],rows[1]],q,None)
assert badorder["source_timestamp_nondecreasing"] is False and badorder["complete_requested_interval"] is True
allrows=[load(p) for p in (E/"reservations").glob("*.json")]
assert all(x["status"]=="settled" for x in allrows)
used=sum(Decimal(str(x["charged_CPU"])) for x in allrows)
assert used==Decimal("3664.66333")
assert Decimal("7176.73")-used==Decimal("3512.06667")
account=load(P/"cumulative-accounting.json")
assert account["original_market_requests_used"]+account.get("new_market_requests",0)==82
assert 134217728-account["original_market_entity_bytes_used"]-account.get("new_market_entity_bytes",0)==78830229
verification=dict(packet=bind(E/"gap-events-review-packet.json"),checked_bindings=packet["bindings"],raw_list_actual_recalculation=proof,actual_raw_entity_B=72029,reported716_exact_overlaps_accepted_with_bound_comparison_code=True,normalized_parquets_not_reread=True,parser_nanosecond_boundary_and_duplicate_condition_checks=True,synthetic_summary=summary,invalid_timestamp_scope_stop_missing_in_main=True,complete_requested_interval_currently_not_full_shape_or_coverage_check=True,unsorted_counterexample=badorder,used_economic_CPU=str(used),remaining_economic_CPU="3512.06667",market_requests_used=82,market_bytes_remaining=78830229,author_preparation_overrun_retained=0.05,new_HTTP_native_economic_runs=0,completed=True)
(E/"gap-events-independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
print(json.dumps(dict(status="review_complete_with_one_entry_correction",raw=proof,scope_stop_mismatch=True)))
