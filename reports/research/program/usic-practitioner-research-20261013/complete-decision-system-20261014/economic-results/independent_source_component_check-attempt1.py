"""Affected implementation review: pure/inert only; no real-source native replay."""
import ast
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
resource.setrlimit(resource.RLIMIT_CPU,(45,49))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
sys.path[:0]=[str(E),str(P/"code")]
import consumer_admission as gate
authority=gate.authority();assert os.sched_getaffinity(0)=={0}
def load(p): return json.loads(p.read_text())
def bind(p):
    assert p.stat().st_size<2_000_000
    raw=p.read_bytes();return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def walk(x):
    if isinstance(x,dict):
        if "path" in x and "sha256" in x: yield x
        else:
            for v in x.values(): yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)
packet=load(E/"source-clock-component-review-packet.json");manifest=load(R/packet["bindings"]["implementation"]["path"])
contract=load(R/packet["bindings"]["fixtures"]["path"])
seen=set();checked=[]
for item in list(walk(packet))+list(walk(manifest))+list(walk(contract)):
    k=(item["path"],item["sha256"])
    if k in seen: continue
    seen.add(k);actual=bind(R/item["path"])
    assert actual["sha256"]==item["sha256"] and ("bytes" not in item or actual["bytes"]==item["bytes"]),item
    checked.append(actual)
assert len(contract["fixtures"])==12 and len({f["id"] for f in contract["fixtures"]})==12
assert sum(f["initial_R0_status"]=="positive" for f in contract["fixtures"])==10
for f in contract["fixtures"]:
    r0=Decimal(f["quantity"])*(Decimal(f["initial_reference"])-Decimal(f["stop"]))
    assert r0==Decimal(f["original_submitted_R0"])
    assert (r0>0)==(f["initial_R0_status"]=="positive")
    assert f["quantity"] in (1,25) and f["synthetic_L2_depth_shares"]==100
    assert f["entry_submit_ns"]==f["first_source_quote"]["event_ns"]+10000
rows=[load(p) for p in (E/"reservations").glob("*.json")]
assert all(x["status"]=="settled" for x in rows)
used=sum(Decimal(str(x["charged_CPU"])) for x in rows)
assert used==Decimal("3746.73333")
assert Decimal("7176.73")-used==Decimal("3429.99667")
offline=sum(Decimal(str(load(R/x["path"])["charged_CPU"])) for x in packet["resources"]["receipts"])
assert offline==Decimal("49.72")
v=dict(packet=bind(E/"source-clock-component-review-packet.json"),bindings_checked=checked,fixture_count=12,positive_R0=10,invalid_R0=2,used_CPU=str(used),remaining_CPU="3429.99667",offline200_actual="49.72",offline200_unused="150.28",checks=[],real_source_native_engines=0,new_HTTP=0)
def save(): (E/"source-clock-component-independent-verification.json").write_text(json.dumps(v,indent=2)+"\n")
save()
import source_clock as sc
from source_clock_native import run_component
base=sc.ns("2024-01-02T14:30:00Z")
q=sc.Observation(kind="quotes",event_ns=base,source_ordinal=0,timestamp="synthetic",conditions=("R",),tape="C",source_entity_sha="synthetic",raw_message="synthetic",bid=Decimal("10"),ask=Decimal("10.02"),bid_size_raw_units=Decimal(1),ask_size_raw_units=Decimal(1))
t=sc.Observation(kind="trades",event_ns=base+20,source_ordinal=0,timestamp="synthetic",conditions=("I",),tape="C",source_entity_sha="synthetic",raw_message="synthetic",price=Decimal("10.01"),trade_size_raw_units=Decimal(1))
setup=sc.StopSetup(Decimal("10.02"),base+1,base+2,25,10**9)
for name,quotes,trades,expected in [
    ("observed_not_broker",(q,),(t,),"observed_necessary_price_conditions_only"),
    ("crossed_invalidates",(q,replace(q,event_ns=base+10,source_ordinal=1,bid=Decimal("11"))),(t,),"unknown_crossed_quote"),
    ("zero_invalidates",(q,replace(q,event_ns=base+10,source_ordinal=1,bid=Decimal("0"))),(t,),"unknown_nonpositive_quote"),
    ("unsupported_invalidates",(q,replace(q,event_ns=base+10,source_ordinal=1,conditions=("X",))),(t,),"unknown_unsupported_quote_qualification"),
    ("same_ns",(q,replace(q,event_ns=t.event_ns,source_ordinal=1)),(t,),"unknown_cross_stream_same_ns_order"),
    ("no_initial",(),(t,),"unknown_no_initial_bbo"),
    ("age",(q,),(replace(t,event_ns=base+10**9+1),),"unknown_stale_observation"),
]:
    result=sc.stop_reference(quotes,trades,setup)[0]
    assert result.reason==expected and result.broker_stop_election.startswith("unknown")
    if name=="observed_not_broker": assert result.observed_price_reference is True and result.certified_then_nbbo_necessary_condition is None
    v["checks"].append(name)
assert sc.ns("2024-01-02T14:30:00.123456789Z")-base==123456789
assert sc.classify_absent_bar((t,),base,base+100,base+99,page_parse_valid=True,token=None).state=="unresolved_absence"
assert sc.classify_absent_bar((t,),base,base+100,base+100,page_parse_valid=True,token=None).state=="source_not_emitted_with_actual_condition_evidence"
assert not sc.no_bar_boundary(base,unacknowledged_partial=True).new_frame
spec=R/"strategy_specs/drafts/martin_complete_system_20261014.yaml"
native=[]
for qty,depth,missing,offset in [(1,100,None,0),(25,100,None,0),(25,1,None,0),(25,100,base+10**9,0),(1,100,None,123456789)]:
    qb=replace(q,event_ns=base+offset)
    quotes=(qb,replace(qb,event_ns=base+offset+2*10**9,source_ordinal=1,bid=Decimal("9.8"),ask=Decimal("9.82")),replace(qb,event_ns=base+offset+3*10**9,source_ordinal=2,bid=Decimal("9.5"),ask=Decimal("9.52")))
    f=dict(id=f"INDEPENDENT_SYNTH__{qty}_{depth}_{missing}_{offset}",quantity=qty,initial_reference="10.02",stop="9.9",initial_R0_status="positive",entry_submit_ns=base+offset+10000,synthetic_L2_depth_shares=depth,first_unresolved_price_ns=missing)
    before=repr(quotes)
    out=run_component(quotes,f,spec,provenance="fully_synthetic_inert")
    assert repr(quotes)==before and out["native_engines"]==1
    assert out["native_reports"][0]["ns"]==f["entry_submit_ns"]
    if missing is None:
        assert out["quantity"]==0 and not out["unknown"] and len(out["closed_R"])==1
        reports=out["native_reports"];actual_qty=Decimal(reports[0]["quantity"])
        assert actual_qty==(1 if depth==1 else qty)
        fee=sum(Decimal(r["commission"].split()[0]) for r in reports)
        dollars=sum(Decimal(r["price"])*Decimal(r["quantity"]) for r in reports[1:])-Decimal(reports[0]["price"])*actual_qty-fee
        assert abs(Decimal(str(out["native_cash"]))-Decimal(20000)-dollars)<Decimal("1e-5")
        assert abs(Decimal(str(out["closed_R"][0]))-dollars/Decimal(str(out["initial_R0"])))<Decimal("1e-9")
        if depth==1: assert any(x["action"]=="terminal_partial_cancel_ack" for x in out["audit"])
    else:
        assert out["unknown"] and out["quantity"]==qty and out["native_cash"] is None
        assert out["closed_R"]==out["firstunknown"]["known_prefix_closed_R"]==[]
        assert out["feedback_after"]==out["firstunknown"]["feedback"] and out["snapshots"]==[]
    native.append(dict(quantity=qty,depth=depth,missing=missing,ns_offset=offset,entry_actual_ns=out["native_reports"][0]["ns"],result=out))
v["synthetic_native"]=native;v["synthetic_native_engines"]=5
bad=dict(f,stop="10.02",initial_R0_status="invalid_nonpositive_R0")
assert run_component(quotes,bad,spec,provenance="fully_synthetic_inert")["native_engines"]==0
try: run_component((),contract["fixtures"][0],spec,provenance="separately_admitted_real_source_component")
except ValueError as e: assert str(e)=="actual_source_requires_independent_component_native_admission"
else: raise AssertionError("unguarded real-source library allowed")
driver=ast.parse((E/"probe_source_clock.py").read_text())
main=next(x for x in driver.body if isinstance(x,ast.FunctionDef) and x.name=="main")
assert "empirical_limit(" not in ast.unparse(main)
admit=ast.parse((P/"code/consumer_admission.py").read_text())
na=next(x for x in admit.body if isinstance(x,ast.FunctionDef) and x.name=="native_admission")
calls=[n.func.id for n in ast.walk(na) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
assert "empirical_limit" in calls
# Pure arithmetic witness to the existing helper: before native child0 gives
# own hard173 for180; after actual child30 it must be143. No CPU is burned.
v["resource_rearm_evidence"]=dict(reserved_inclusive_CPU=180,launcher_unknown=5,before_native_child_CPU=0,own_hard_before_native=173,illustrative_native_child_CPU=30,correct_own_hard_after_native=143,driver_rearm_after_native_missing=True,library_phase_does_not_rearm=True,already_existing_helper="consumer_admission.empirical_limit")
v["completed"]=True;u=resource.getrusage(resource.RUSAGE_SELF);v["own_CPU"]=u.ru_utime+u.ru_stime;v["RSS_KiB"]=u.ru_maxrss
save()
print(json.dumps(dict(status="semantic_checks_pass_resource_rearm_needed",synthetic_engines=5,own_CPU=v["own_CPU"])))
