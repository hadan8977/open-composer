"""Bounded independent static/source and inert prototype audit, no market prices."""
import hashlib
import importlib
import json
import os
import resource
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (65, 70))
assert os.sched_getaffinity(0) == {0}
ROOT = Path.cwd()
P = Path(__file__).resolve().parent
verified = {}


def read(path):
    return json.loads(Path(path).read_text())


def check(b):
    p = Path(b["path"])
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    assert p.is_relative_to(ROOT)
    if str(p) not in verified:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        verified[str(p)] = {"sha256": h.hexdigest(), "bytes": p.stat().st_size}
    assert verified[str(p)]["sha256"] == b["sha256"], str(p)
    if "bytes" in b:
        assert verified[str(p)]["bytes"] == b["bytes"], str(p)


packet = read(P / "independent-review-packet.json")
for b in packet["bindings"] + packet["primary_sources"]:
    check(b)
for b in read(P / "design-bindings.json").values():
    if isinstance(b, dict) and "sha256" in b:
        check(b)
catalog = read(P / "mechanism-catalog.json")
for u in catalog["units"]:
    check(u["snapshot"])
plan = read(P / "scientific-plan.json")
assert plan["author"] == "7c7b1f3d-b962-4bbe-a2eb-87578888a8d5"
assert plan["resource_contract"]["current_economic_permission"] is False
inv = read(P / "input-inventory.json")
nov = []
for v in inv.values():
    if isinstance(v, list):
        for row in v:
            if isinstance(row, dict) and row.get("year") == 2024 and row.get("month") == 11:
                nov.append(row)
assert len(nov) == 6
assert {r["symbol"] for r in nov} == {"COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"}
assert all(len(r["observed"]) == 1 for r in nov)
# These inputs are identified but NOT price-read, rehashed or independently accepted here.
sys.path.insert(0, str(P / "code"))
tests = importlib.import_module("test_decision_system")
f = tests.frame()
b = tests.book()
probes = {}
for candidate in ("P_FEEDBACK", "P_SYSTEM"):
    s = tests.system(candidate)
    o = s.step(f, b)[0]
    probes[candidate] = {"price_cap": o.price_cap, "reference": o.reference, "quantity": o.quantity, "eligible_after": o.eligible_after.isoformat(), "frame_end": f.end.isoformat()}
s = tests.system("P_HOLD")
o = s.step(f, b)[0]
s.entry_report(f.symbol, f.end + timedelta(seconds=1), filled=True, price=10, quantity=o.quantity)
f2 = replace(f, start=f.end + timedelta(minutes=1), end=f.end + timedelta(minutes=2), close=10.8, low=10.5)
trim = s.step(f2, b)[0]
held = s.states[f.symbol].quantity
s.exit_report(f.symbol, trim.eligible_after, held)
probes["oversized_trim_report"] = {"intent_quantity": trim.quantity, "held_before": held, "reported_quantity": held, "accepted": True, "held_after": s.states[f.symbol].quantity}
s = tests.system("P_HOLD")
o = s.step(f, b)[0]
filled_at = f.end + timedelta(seconds=1)
s.entry_report(f.symbol, filled_at, filled=True, price=10, quantity=o.quantity)
s.exit_report(f.symbol, f.end - timedelta(days=1), o.quantity, stopout=True)
probes["pre_fill_stopout_report"] = {"fill_at": filled_at.isoformat(), "stopout_at": (f.end-timedelta(days=1)).isoformat(), "accepted": True}
s = tests.system("P_HOLD")
o = s.step(f, b)[0]
s.entry_report(f.symbol, f.end+timedelta(seconds=1), filled=True, price=10, quantity=1)
probes["partial_entry_report"] = {"submitted_quantity": o.quantity, "reported_filled_quantity": 1, "pending_after": s.states[f.symbol].pending, "held_after": s.states[f.symbol].quantity, "remaining_order_fate_represented": False}
camp = read(ROOT / plan["candidate_and_trial_contract"]["campaign"])
source_excerpt = []
def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)
for fn in ("primary-open-01.json", "primary-passages-01.json", "interview-retained-passages.json"):
    for text in strings(read(P / "sources" / fn)):
        for line in text.splitlines():
            if line.startswith(tuple(f"L{n}:" for n in (185, 203, 218, 229, 230, 231, 247, 264, 366, 373, 374, 375, 377, 378, 387, 527, 532, 558, 559, 619, 623, 625, 628, 633))):
                source_excerpt.append({"file": fn, "line": line})
out = {"status": "completed", "author": plan["author"], "reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3", "verified_files": verified, "bound_file_mismatches": 0, "november_fixed_input_metadata": nov, "price_payload_read": False, "prototype_inert_probes": probes, "source_passages": source_excerpt, "campaign_exposure_budget": camp["exposure_budgets"], "scientific_verdict_not_inferred_from_hashes": True, "actual_CPU_affinity": sorted(os.sched_getaffinity(0)), "inner_CPU_not_additive": resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, "RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "new_source_market_fit_economic_calls": 0}
(P / "independent-plan-verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"verified_files": len(verified), "probes": probes, "november_bindings": [{"symbol": x["symbol"], "observed": x["observed"]} for x in nov], "source_passages": source_excerpt, "campaign_exposure_budget": camp["exposure_budgets"]}, ensure_ascii=False))
