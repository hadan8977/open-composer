"""Only E1 small source-entry diff and remaining74CPU acceptance."""
import ast
import hashlib
import json
from pathlib import Path
from datetime import UTC,datetime
from decimal import Decimal
import os
import resource
resource.setrlimit(resource.RLIMIT_CPU,(2,3))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
assert os.sched_getaffinity(0)=={0}
def load(p): return json.loads(p.read_text())
assert load(R/"reports/research/control/owner-compute-hold.json")["research_paused"] is False
task=next(t for t in load(R/"reports/research/control/day-goal.json")["tasks"] if t.get("id")=="MARTIN-COMPLETE-DECISION-SYSTEM-20261014")
assert task["owner"]=="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5" and task["status"]=="running_complete_task"
def bind(p):
    raw=p.read_bytes();return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
packet=load(E/"gap-events-E1-review-packet.json");b=packet["bindings"]
for k,item in b.items(): assert bind(R/item["path"])==item,k
before=(R/b["before"]["path"]).read_text();after=(R/b["code"]["path"]).read_text()
expected=before.replace("complete_requested_interval=","page_no_token_and_valid_timestamp_parse=")
expected=expected.replace("            results.append(\n","            summary = summarize(rows, query, token)\n            results.append(\n",1)
expected=expected.replace("**summarize(rows, query, token),","**summary,",1)
branch='            if summary["invalid_timestamp_rows"]:\n                attempt["status"] = "unresolved_clock_no_followup"\n                ledger["stop_reason"] = "unresolved_clock"\n                save(ledger_path, ledger)\n                break\n'
expected=expected.replace("            if token:\n",branch+"            if token:\n",1)
assert ast.dump(ast.parse(expected),include_attributes=False)==ast.dump(ast.parse(after),include_attributes=False)
before_tree=ast.parse(before);after_tree=ast.parse(after)
functions=lambda tree:{n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
assert ast.dump(functions(before_tree)["ns"])==ast.dump(functions(after_tree)["ns"])
main=functions(after_tree)["main"]
matching=[x for x in ast.walk(main) if isinstance(x,ast.If) and ast.unparse(x.test)=="summary['invalid_timestamp_rows']"]
assert len(matching)==1
# Execute the actual small stop branch in isolation. No main/import/client.
loop=ast.For(target=ast.Name(id="i",ctx=ast.Store()),iter=ast.Call(func=ast.Name(id="range",ctx=ast.Load()),args=[ast.Constant(4)],keywords=[]),body=[ast.AugAssign(target=ast.Name(id="calls",ctx=ast.Store()),op=ast.Add(),value=ast.Constant(1)),matching[0]],orelse=[])
module=ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[]))
inert=[]
for invalid in ([dict(index=0)],[]):
    writes=[]
    env=dict(summary=dict(invalid_timestamp_rows=invalid),attempt={},ledger={},ledger_path="INERT_ONLY",save=lambda p,x:writes.append(dict(x)),calls=0)
    exec(compile(module,"actual_E1_branch_only","exec"),env)
    assert env["calls"]==(1 if invalid else 4)
    if invalid: assert env["ledger"]["stop_reason"]=="unresolved_clock" and writes and env["attempt"]["status"]=="unresolved_clock_no_followup"
    inert.append(dict(invalid=bool(invalid),branch_iterations=env["calls"],real_HTTP=0))
author=load(R/b["author_verification"]["path"])
assert [x["transport_calls"] for x in author["actual_edited_main_branch_checks"]]==[1,4]
offline=load(R/b["offline_actual_receipt"]["path"])
assert offline["status"]=="settled" and Decimal(str(offline["charged_CPU"]))==Decimal("6")
rows=[load(p) for p in (E/"reservations").glob("*.json")]
assert all(x["status"]=="settled" for x in rows)
assert sum(Decimal(str(x["charged_CPU"])) for x in rows)==Decimal("3670.66333")
assert Decimal("7176.73")-Decimal("3670.66333")==Decimal("3506.06667")
assert not (E/"gap-events").exists()
prior=load(R/b["before_review"]["path"])
assert bind(P/"consumer-independent-review.json")==prior["bindings"]["canonical"]
verification=dict(packet=bind(E/"gap-events-E1-review-packet.json"),new_code=b["code"],old_code=b["before"],exact_expected_AST_only=True,ns_AST_unchanged=True,actual_stop_branch_inert_checks=inert,author_full_edited_main_inert_evidence_verified=True,partial_saved_before_stop=True,other_token_error_cap_guards_unchanged=True,old_input_scope_unchanged=True,offline_settled_charge_CPU=6,proposed80_remaining_CPU=74,canonical_unchanged=True,new_HTTP_native_data_scans=0)
(E/"gap-events-E1-independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
res=dict(pool="original comparison1000 / existingr6 remaining30.52",inclusive_charge_CPU=3,comparison_before_CPU=528.07,comparison_after_CPU=531.07,comparison_remaining_CPU=468.93,r6_80_used_CPU=52.48,r6_80_remaining_CPU=27.52,profile="economic-results/gap-events-E1-independent-resource.txt",note="Outer actual and smallread/setup/seal/handoff covered once by3CPU; no author ledger mutation",CPU=1,fresh_cap_MiB=400,affinity=[0])
review=dict(schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=packet["author"],reviewer=packet["reviewer"],verdict="approve_bounded_gap_microstructure_witness",economic_execution_admitted=False,
bindings=dict(code=b["code"],scope=b["scope"],transport=prior["bindings"]["transport"],rawproof=prior["bindings"]["rawproof"],docs=prior["bindings"]["docs"],source_cards=prior["bindings"]["source_cards"],canonical=prior["bindings"]["canonical"],implementation=prior["bindings"]["implementation"],archived_E1_review=b["before_review"],archived_before_code=b["before"],E1_packet=bind(E/"gap-events-E1-review-packet.json"),settledoffline_receipt=b["offline_actual_receipt"],E1_author_inert_evidence=b["author_verification"],E1_independent_verification=bind(E/"gap-events-E1-independent-verification.json")),
allocation=dict(requests=4,entity_bytes=2500000,prospective_input_CPU=74,CPU=1,memory_MiB=900),
lineage=dict(original_task_pool_CPU=7176.73,total_consumed_CPU=3670.66333,remaining_before_new_reservation_CPU=3506.06667,maximum_remaining_after74_reservation_CPU=3432.06667,proposed_source_dependency_total_CPU=80,offline_actual_CPU=6,source_execution_remaining_CPU=74,no_reset=True,old_preparation_consumed_CPU=2000.05,old_preparation_overrun_CPU=0.05,old_preparation_not_reclassified=True,market_requests_used=82,market_remaining_before=14,market_remaining_after_maximum=10,market_entity_remaining_before_B=78830229,market_entity_remaining_after2500000_reservation_B=76330229),
E1_resolution="Actual corrected stop branch independently checked: invalid+nulltoken stops after one iteration with ledger reason; valid same-timestamp distinct messages allowed. Author actual-main inert records1/4 stub calls accepted as fixtures only. Partial/raw saved before stop; parser AST unchanged. Renamed page_no_token_and_valid_timestamp_parse is only token/parse status, never coverage certification.",corrections=[],
conditions=[
"Only four exact LMND quotes/trades windows in bound scope: prior minute plus firstmissing minute on2024-09-13 and2025-02-11. Single page each; quotes1M each, trades250k each, total2.5MB. No retries/redirects/followup pages or wider dates/symbols.",
"Create one unique existing-original-pool reservation, runtime0 and at most74 prospective-input/empirical CPU including native,IO,setup,failures,unknown and postexit costs. Current native/owner/hold/exactbinding/fresh900M/CPU0 gates precede factory/GET. Canonicalr6 is unchanged; this is a narrow source exception, not a new economic grant.",
"Keep all original message bytes and nanosecond timestamp strings, conditions,crossed/zero quotes, repeated timestamps. Inclusive end belongs to queried sourcewindow but is outside central missing minute. Invalid timestamp saves raw/partial/ledger and stops further calls, as do token/error/cap boundaries.",
"Neither null pagination nor positive messages proves uninterrupted feed, firmNBBO, executable size/fill, trade-condition eligibility or historicalfirstvisibility. Ordering/out-of-query diagnostics and coverage_gate_pass=false remain meaningful. Empty/partial responses do not establish no trades or harmless clock skip.",
"No native quote/trade injection, synthetic bars, Frame/source override, signal capability change, fit,PnL/account replay,padding or old-path resurrection. Any later typed input/clock/scientific change requires its relevant bound affected acceptance.",
"6 offlineCPU plus this maximum74 remain inside the same proposed80 and original residual. Retain all old preparation costs and0.05 overrun. Author serially settles actual and unknown exactlyonce; reviewer has not changed ledgers.",
],
source_value_judgment="Now useful and bounded: measure event activity at the two demonstrated raw-bar holes before investing in typed-price coverage or additional strategy reruns. Four prior unknown outcomes and incomplete mother question stay open.",canonical_r6_unchanged=True,mother_question_complete=False,current_native_pass_asserted=False,reviewer_GET_started=False,resource=res)
(E/"gap-events-independent-review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(bind(E/"gap-events-independent-review.json")))
