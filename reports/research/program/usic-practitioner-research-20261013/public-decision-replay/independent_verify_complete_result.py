"""Independent audit of the frozen 16 outputs; no author replay import or new trials."""
import hashlib
import json
import os
import re
import resource
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR, getcontext
from pathlib import Path
from zoneinfo import ZoneInfo

resource.setrlimit(resource.RLIMIT_CPU, (55, 60))
assert os.sched_getaffinity(0) == {0}
getcontext().prec = 60
P = Path(__file__).resolve().parent
ROOT = Path.cwd()
O = P / "replay-result"
IT = ROOT / "reports/research/iterations/usic_public_decision_replay_20261014"
NY = ZoneInfo("America/New_York")
checked = {}
counts = Counter()
checks = 0


def require(ok, description):
    global checks
    checks += 1
    assert ok, description


def read(path):
    return json.loads(Path(path).read_text())


def binding(b):
    p = Path(b["path"])
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    require(p.is_relative_to(ROOT), str(p))
    if str(p) not in checked:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        checked[str(p)] = {"sha256": h.hexdigest(), "size_bytes": p.stat().st_size}
    a = checked[str(p)]
    require(a["sha256"] == b["sha256"], f"SHA {p}")
    for k in ("size_bytes", "bytes"):
        if isinstance(b.get(k), int):
            require(b[k] == a["size_bytes"], f"size {p}")
    return p


def bindings_in(x):
    if isinstance(x, dict):
        if isinstance(x.get("path"), str) and "sha256" in x:
            binding(x)
        for v in x.values():
            bindings_in(v)
    elif isinstance(x, list):
        for v in x:
            bindings_in(v)


def decimal_equal(a, b, label):
    require(a is not None and D(a) == b, f"decimal {label}: {a} != {b}")


def grid(day):
    start = datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=NY)
    return [start + timedelta(minutes=i) for i in range(390)]


packet = read(P / "complete-result-review-packet.json")
bindings_in(packet)
manifest = read(O / "result-manifest.json")
bindings_in(manifest)
implementation = read(P / "revisions/native-json-interface/implementation-manifest.json")
bindings_in(implementation)
require(read(P / "revisions/native-json-interface/independent-implementation-review.json")["verdict"] == "approve_implementation", "implementation approval")
require(read(P / "revisions/v2/independent-plan-review.json")["verdict"] == "approve_deep_plan", "science approval")
native = read(P / "final-native-log.txt")
require(native["status"] == "ok" and native["blocked"] == [], "final native actual")
evaluation = read(IT / "evaluation-run/evaluation.json")
receipt = read(IT / "evaluation-run/evaluation-receipt.json")
bindings_in(receipt)
require(receipt["schema_version"] == 1 and receipt["evidence_publication_status"] == "complete", "final publication")
require(evaluation["decision"] == "stop" and evaluation["workflow_pass"], "decision")
for k in ("research_pass", "paper_ready_pass", "promotion_eligible", "broker_activity_allowed", "source_actual_trade_reproduction"):
    require(evaluation[k] is False, k)
require(evaluation["case_results"] == read(O / "mechanism-results.json")["rows"], "report rows")
summary = read(O / "result.json")
require(summary["trajectories"] == read(O / "progress.json"), "progress complete")
require(len(summary["trajectories"]) == 16, "16 inventory")
ledger = [json.loads(x) for x in (O / "price-trial-ledger.jsonl").read_text().splitlines()]
require(len(ledger) == 16, "16 ledger entries")
require((O / "price-trial-ledger.jsonl").read_bytes() == (IT / "evaluation-run/trial-ledger.jsonl").read_bytes(), "native ledger")
cases = [("STUDY_CHPT_PDL", "SBE", "2021-02-22"), ("STUDY_SENS_PDL", "SENS", "2022-01-20"), ("STUDY_TSLA_PREVH", "TSLA", "2025-02-20"), ("STUDY_SMCI_PREVH", "SMCI", "2025-03-26")]
verified = []
for cid, symbol, day in cases:
    component = read(P / f"acquisition/components/{cid}.json")
    require(component["clock"]["date_candidate"] == day, "fixed case date")
    require(component["clock"]["session_close_NY"] == "16:00:00", "bound actual regular close")
    c = component["symbol_components"][symbol]
    minutes = {datetime.fromisoformat(r["timestamp_NY"]): r for r in c["RTH_minutes"]}
    require(len(minutes) == len(c["RTH_minutes"]), "unique accepted minute pointers")
    prior_grid = grid(component["clock"]["prior_session"])
    prior_complete = all(t in minutes and minutes[t]["valid"] for t in prior_grid)
    require(prior_complete == c["prior_RTH_complete"], "prior completeness")
    last = c["prior_last_chartbar"]
    parent_rows = [minutes[t] for t in prior_grid[-30:]]
    require(last["complete"] and all(x["valid"] for x in parent_rows), "last real 30 minute stub")
    low = min(D(x["row"]["l"]) for x in parent_rows)
    high = max(D(x["row"]["h"]) for x in parent_rows)
    decimal_equal(last["l"], low, "parent low")
    decimal_equal(last["h"], high, "parent high")
    require(last["source_refs"] == [x["ref"] for x in parent_rows], "parent source pointers")
    if prior_complete:
        decimal_equal(c["prior_RTH_low"], min(D(minutes[t]["row"]["l"]) for t in prior_grid), "PDL actual prior low")
    for method in ("PDL", "PREVH"):
        for delay in (1, 5):
            name = f"{cid}-{method}-d{delay}"
            output = read(O / f"{name}.json")
            bindings_in(output["source_case_binding"])
            a = output["trajectory"]
            require(output["case_id"] == cid and output["method"] == method and output["delay_minutes"] == delay, name)
            require(output["source_symbol_selection"]["selected_source_symbol"] == symbol, "selected source symbol")
            require(output["not_actual_trader_trade"] is True, "source claim")
            entry = exit_ = None
            unknown = None
            if method == "PDL" and not prior_complete:
                expected = "invalid_input"
                require(a.get("Pref") is None and a.get("q0") is None, "invalid fields retained N/A")
            else:
                pref = ((D(c["prior_RTH_low"]) if method == "PDL" else low) - D(".01")).quantize(D(".01"), rounding=ROUND_FLOOR)
                stop = (high + D(".01")).quantize(D(".01"), rounding=ROUND_CEILING)
                q = int(D(100) // (stop - pref))
                r0 = q * (stop - pref)
                for k, v in (("Pref", pref), ("S", stop), ("R0", r0), ("unused_planned_risk_USD", D(100) - r0)):
                    decimal_equal(a[k], v, name + k)
                require(a["q0"] == q, "frozen integer quantity")
                times = grid(day)
                require(a["activation_NY"] == times[delay].isoformat(), "activation")
                require(a["pending_expiry_NY"] == times[375].isoformat(), "expiry")
                expected = None
                # Audit chronological first event on the accepted fixed grid, independently of author engine.
                for n in range(delay, 390):
                    t = times[n]
                    if entry is None and n >= 375:
                        expected = "no_fill"
                        break
                    row = minutes.get(t)
                    if row is None or not row["valid"]:
                        expected, unknown = "missing", t.isoformat()
                        break
                    bar = row["row"]
                    op, hi, lo, cl = [D(bar[k]) for k in ("o", "h", "l", "c")]
                    if entry is None:
                        if lo > pref and op > pref:
                            continue
                        ep = op if op <= pref else pref
                        entry = (t, ep, row)
                        continue
                    xp = op if op >= stop else stop if hi >= stop else cl if n == 389 else None
                    if xp is not None:
                        why = "protective_open_gap_or_equal" if op >= stop else "protective_touch_proxy" if hi >= stop else "EOD_research_convention"
                        exit_ = (t, xp, row, why)
                        expected = "filled_closed"
                        break
                if unknown:
                    require(a["unknown_at_NY"] == unknown and a["unresolved_state"] == ("held" if entry else "pending"), "first active missing minute")
                if entry:
                    t, ep, row = entry
                    ae = a["entry"]
                    decimal_equal(ae["price"], ep, "entry price")
                    require(ae["minute_start_NY"] == t.isoformat() and ae["source_ref"] == row["ref"], "first trigger time/pointer")
                    require(ae["protection_scheduled_NY"] == (t + timedelta(minutes=1)).isoformat(), "next scheduled protection")
                    require(ae["q0"] == q, "no postfill resizing")
                    require(ae["participation_gt_1pct_observed_minute_volume"] == (D(q) > D(row["row"]["v"]) / 100), "volume flag")
                    require(ae["entry_bar_crosses_stop_while_unprotected"] == (D(row["row"]["h"]) >= stop), "entry bar unprotected")
                    decimal_equal(ae["entry_notional"], q * ep, "entry notional")
                if exit_:
                    t, xp, row, why = exit_
                    ax = a["exit"]
                    decimal_equal(ax["price"], xp, "exit price")
                    require(ax["minute_start_NY"] == t.isoformat() and ax["source_ref"] == row["ref"] and ax["exit_reason"] == why, "exit clock/source/reason")
                    decimal_equal(a["raw_proxy_cashflow"], q * (ep - xp), "gross cash")
            require(a["status"] == expected, f"{name} status {expected}")
            require((a["entry"] is None) == (entry is None) and (a["exit"] is None) == (exit_ is None), "NA trade legs")
            counts[expected] += 1
            fees = output["transaction_costs"]
            stresses = output["mandatory_borrow_stress"]
            require([x["bps_per_filled_side"] for x in fees] == [0, 5, 20], "fee inventory")
            require([(x["bps_per_filled_side"], D(x["assumed_APR"])) for x in stresses] == [(b, apr) for b in (0, 5, 20) for apr in (D(0), D(".20"))], "borrow inventory")
            for f in fees + stresses:
                require(f["status"] == expected and f["primary"] == (f["bps_per_filled_side"] == 20) and f["actual_borrow_cost_unpriced"], "cost identity")
                if expected == "filled_closed":
                    fee = D(q) * (ep + xp) * D(f["bps_per_filled_side"]) / 10000
                    cash = D(q) * (ep - xp)
                    decimal_equal(f["fee_USD"], fee, "fees")
                    decimal_equal(f["transaction_adjusted_R"], (cash - fee) / r0, "transaction R")
                    decimal_equal(f["original_R0"], r0, "original R denominator")
                else:
                    require(f["fee_USD"] is None and f["transaction_adjusted_R"] is None, "NA costs not zero")
                if "assumed_APR" in f:
                    require(f["assumed_calendar_days"] == 1 and f["day_basis"] == 365 and not f["actual_short_tradability_certified"], "borrow assumption")
                    if expected == "filled_closed":
                        charge = D(q) * ep * D(f["assumed_APR"]) / 365
                        decimal_equal(f["borrow_stress_USD"], charge, "borrow charge")
                        decimal_equal(f["stress_R"], (cash - fee - charge) / r0, "borrow R")
                    else:
                        require(f["borrow_stress_USD"] is None and f["stress_R"] is None, "NA borrow not zero")
            er = next(x for x in evaluation["case_results"] if (x["case_id"], x["method"], x["delay"]) == (cid, method, delay))
            require(er["entry"] == a["entry"] and er["exit"] == a["exit"] and er["status"] == expected, "report exact legs/state")
            require(er["primary_20bps_R"] == fees[2]["transaction_adjusted_R"] and er["primary_20bps_fees_USD"] == fees[2]["fee_USD"], "report primary exact")
            verified.append({"id": name, "status": expected, "entry": a["entry"], "exit": a["exit"], "unknown_at_NY": unknown, "primary_20bps_R": fees[2]["transaction_adjusted_R"]})
require(counts == {"filled_closed": 10, "invalid_input": 4, "missing": 2}, "state counts")
accounting = read(O / "final-resource-accounting.json")
actual = D(0)
for j in accounting["jobs"]:
    txt = binding(j["resource"]).read_text()
    user = D(re.search(r"User time \(seconds\): ([0-9.]+)", txt)[1])
    system = D(re.search(r"System time \(seconds\): ([0-9.]+)", txt)[1])
    require(abs(user + system - D(str(j["actual_outer_CPU"]))) < D(".0000001"), "outer resource charge")
    require(int(re.search(r"Exit status: (\d+)", txt)[1]) == j["exit"], "retained actual exit")
    actual += user + system
require(actual == D("18.27"), "inclusive actual total")
require(actual + D(5) == D(str(accounting["charged_CPU"])) == D("23.27"), "economic debit")
require(D(7200) - D("23.27") == D(str(accounting["original_pool_unused_CPU"])), "no reset")
require(accounting["original_pool_unallocated_CPU"] == 7140 and accounting["real_price_replay_runs"] == 1, "one admitted run")
out = {"status": "pass", "author": "f9add224-744b-471c-b812-c43cc179fa38", "reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3", "independent_author_engine_imported": False, "scope": "Fixed 16 previously executed paths only; no new strategy trials; accepted components reused, no raw entity rescan.", "checks": checks, "path_count": 16, "cost_count": 48, "borrow_count": 96, "decimal_precision": 60, "status_counts": dict(counts), "verified_paths": verified, "verified_files": checked, "new_market_source_fit_order_requests": 0, "author_economic_actual_CPU": str(actual), "author_economic_charged_CPU": "23.27", "native_final": native, "CPU_affinity": sorted(os.sched_getaffinity(0)), "inner_CPU_not_additive": resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, "RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(P / "independent-complete-result-verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: out[k] for k in ("status", "checks", "path_count", "cost_count", "borrow_count", "status_counts", "RSS_KiB")}))
