"""Exact-decimal binding repair only; no author launch or economic execution."""
import ast
import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU,(1,2))
R=Path.cwd()
P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D=P/"revisions/consumer-r5"
assert os.sched_getaffinity(0)=={0}
assert json.loads((R/"reports/research/control/owner-compute-hold.json").read_text())["research_paused"] is False
task=next(t for t in json.loads((R/"reports/research/control/day-goal.json").read_text())["tasks"] if t.get("id")=="MARTIN-COMPLETE-DECISION-SYSTEM-20261014")
assert task["owner"]=="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5" and task["status"]=="running_complete_task"
def bind(p):
    raw=p.read_bytes()
    return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def load(p): return json.loads(p.read_text())
packet=load(D/"review-packet.json")
assert bind(D/"review-packet.json")["sha256"]=="2be08b50186a10830446834a77b9576d8ebde29c85aaa6f0e431f1d44fe6c273"
for k in ("manifest","prior_review","before_code","after_code"):
    b=packet[k];assert bind(R/b["path"])==b,k
old=load(D/"before-consumer-implementation-manifest.json")
new=load(P/"consumer-implementation-manifest.json")
a={b["path"]:b for b in old["files"]};b={b["path"]:b for b in new["files"]}
assert set(a)==set(b)
assert [p for p in a if a[p]!=b[p]]==[packet["after_code"]["path"]]
for k in old:
    if k!="files": assert old[k]==new[k],k
before=(R/packet["before_code"]["path"]).read_text()
after=(R/packet["after_code"]["path"]).read_text()
old_guard='            assert alloc["economic_coreseconds"] <= POOL - lineage["consumed_CPU"]'
new_guard='            assert Decimal(str(alloc["economic_coreseconds"])) <= (\n                Decimal(str(POOL)) - Decimal(str(lineage["consumed_CPU"]))\n            )'
restored=after.replace('from decimal import Decimal\n','',1).replace(new_guard,old_guard,1)
assert restored==before
tree=ast.parse(after)
tests=[n.test for n in ast.walk(tree) if isinstance(n,ast.Assert) and "Decimal" in ast.unparse(n.test)]
assert len(tests)==1
expr=compile(ast.Expression(tests[0]),"actual_decimal_guard","eval")
env=dict(Decimal=Decimal,str=str,POOL=7176.73,lineage=dict(consumed_CPU=1674.98333))
assert eval(expr,dict(env,alloc=dict(economic_coreseconds=5501.74667))) is True
assert eval(expr,dict(env,alloc=dict(economic_coreseconds=5501.74668))) is False
assert 7176.73-1674.98333 < 5501.74667
assert not (P/"economic-results/reservations/martin-feed-probe-20261014.json").exists()
failure_profile=P/"economic-results/feed-probe-prelaunch-resource.txt"
assert "Exit status: 1" in failure_profile.read_text()
verification=dict(exact_one_guard_and_import_only=True,restored_r4_source_sha256=packet["before_code"]["sha256"],actual_AST_expression=ast.unparse(tests[0]),exact_equal_allowed="5501.74667",one_unit_1e5_above_rejected="5501.74668",binary_difference_reproduced=True,no_new_reservation_present=True,actual_failed_prelaunch_CPU=0.33,prelaunch_charge_route="Once within forthcoming180 job launcher5, not added to comparison and not forgiven",unchanged_manifest_keys_reused=True,new_native_inert_price_Frame_runs=0)
(D/"independent-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
review=load(D/"before-consumer-independent-review.json")
oldresource=review["resource"]
review.update(at_utc=datetime.now(UTC).isoformat(),classification="One exact-decimal guard and binding continuation; r4 scientific/implementation/resource conditions inherited unchanged")
review["bindings"]["implementation_manifest"]=packet["manifest"]
review["bindings"]["reviewed_request"]=bind(D/"review-packet.json")
review["bindings"]["archived_r4_review"]=packet["prior_review"]
review["bindings"]["decimal_before_code"]=packet["before_code"]
review["bindings"]["decimal_after_code"]=packet["after_code"]
review["bindings"]["decimal_independent_verification"]=bind(D/"independent-verification.json")
review["bindings"]["failed_prelaunch_profile"]=bind(failure_profile)
review["decimal_diff_acceptance"]=verification
assert review["allocation"]["economic_coreseconds"]==5501.74667 and review["first_execution"]["maximum_inclusive_CPU"]==180
assert review["grant_lineage"]["consumed_CPU"]==1674.98333
review["resource"]=dict(pool="original comparison1000, new bounded metadata review max5; old consumer100 unchanged",inclusive_charge_CPU=3.0,comparison_before_CPU=475.59,comparison_after_CPU=478.59,comparison_remaining_CPU=521.41,actual_profile="revisions/consumer-r5/independent-resource.txt",fresh_cap_MiB=400,affinity=[0],note="Outer actual and smallread/setup/seal/handoff covered once by3 conservative CPU; profile reconciled after exit, not extra charge",author_ledger_mutated=False)
review["prior_resource_receipt_reused"]=oldresource
text=json.dumps(review,ensure_ascii=False,indent=2)+"\n"
(D/"independent-review.json").write_text(text)
(P/"consumer-independent-review.json").write_text(text)
print(json.dumps(dict(canonical=bind(P/"consumer-independent-review.json"),local=bind(D/"independent-review.json"))))
