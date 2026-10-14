"""Execute only the independently admitted16 fixed conditional case trajectories."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import subprocess
import time
from pathlib import Path

from case_replay import replay

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[4]
ITERATION = ROOT / "reports/research/iterations/usic_public_decision_replay_20261014"
OUT = P / "replay-result"
AUTHOR = "f9add224-744b-471c-b812-c43cc179fa38"
REVIEWER = "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3"


def bound(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(path, o):
    path.write_text(json.dumps(o, indent=2, allow_nan=False) + "\n")


def check_admission():
    approval = json.loads((P / "independent-economic-resource-decision.json").read_text())
    assert approval["verdict"] == "approve_bounded_case_replay"
    assert (
        approval["author"] == AUTHOR
        and approval["decision_owner"] == REVIEWER
        and AUTHOR != REVIEWER
    )
    assert approval["economic_execution_admitted"] is True
    assert 0 < approval["allocation"]["economic_coreseconds"] <= 7200
    assert approval["allocation"]["CPU"] == 1 and approval["allocation"]["memory_MiB"] <= 900
    for row in approval["bindings"]:
        assert bound(ROOT / row["path"]) == {k: row[k] for k in ("path", "sha256")}
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    assert hold["research_paused"] is False
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    owners = [t for t in day["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH"]
    assert len(owners) == 1 and owners[0]["active_owner"] == AUTHOR
    assert os.sched_getaffinity(0) == {0}
    assert not OUT.exists(), "no_replay_overwrite_or_consumed_budget_reset"
    # Revalidate the actual current native dossier before dependent economic IO.
    result = subprocess.run(
        [str(ROOT / ".venv/bin/oc"), "research", "iteration", "validate", ITERATION.name, "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("current_native_validation_blocked")
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "ok", receipt
    return approval, receipt


def main():
    approval, native = check_admission()
    start = time.process_time()
    limit = approval["allocation"]["economic_coreseconds"]
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 1))
    OUT.mkdir()
    save(
        OUT / "consumed-admission.json",
        {
            "approval": bound(P / "independent-economic-resource-decision.json"),
            "native_current": native,
        },
    )
    summary = json.loads((P / "acquisition/components/component-result.json").read_text())
    case_rules = json.loads((P / "acquisition/case-admissions.json").read_text())
    allrows = []
    for row in summary["cases"]:
        report = json.loads((ROOT / row["binding"]["path"]).read_text())
        cid = row["case_id"]
        selection = case_rules["cases"][cid]
        for method in ("PDL", "PREVH"):
            for delay in (1, 5):
                if selection["conditional_price_replay_admitted"]:
                    comp = report["symbol_components"][selection["selected_source_symbol"]]
                    result = replay(comp, report["clock"]["date_candidate"], method, delay)
                else:
                    # Preserve all nominal cells without constructing fictitious trade returns.
                    state = {
                        "status": "dependency_skipped",
                        "reason": selection["reason"],
                        "entry": None,
                        "exit": None,
                        "R": None,
                    }
                    result = {
                        "trajectory": state,
                        "transaction_costs": [
                            {
                                "bps_per_filled_side": b,
                                "status": "dependency_skipped",
                                "transaction_adjusted_R": None,
                            }
                            for b in (0, 5, 20)
                        ],
                        "mandatory_borrow_stress": [
                            {
                                "bps_per_filled_side": b,
                                "assumed_APR": a,
                                "status": "dependency_skipped",
                                "stress_R": None,
                            }
                            for b in (0, 5, 20)
                            for a in ("0", "0.20")
                        ],
                    }
                result.update(
                    case_id=cid,
                    method=method,
                    delay_minutes=delay,
                    source_case_binding=row["binding"],
                    source_symbol_selection=selection,
                    not_actual_trader_trade=True,
                )
                destination = OUT / f"{cid}-{method}-d{delay}.json"
                save(destination, result)
                allrows.append(
                    {
                        "case_id": cid,
                        "method": method,
                        "delay": delay,
                        "status": result["trajectory"]["status"],
                        "binding": bound(destination),
                    }
                )
                save(OUT / "progress.json", allrows)
    assert len(allrows) == 16
    save(
        OUT / "result.json",
        {
            "research_role": "market_component_method",
            "claim_scope": "conditional_cohort",
            "trajectories": allrows,
            "price_trajectories": 16,
            "transaction_cost_cells": 48,
            "fixed_borrow_stress_cells": 96,
            "source_selected_seen_cases": True,
            "population_expectation_or_private_CAGR_claim": False,
            "research_pass": False,
            "paper_ready_pass": False,
            "new_orders": 0,
            "resource": {
                "inner_CPU_not_double_charged": time.process_time() - start,
                "RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
        },
    )
    print(json.dumps({"price_trajectories": 16, "cost_cells": 48, "borrow_cells": 96, "orders": 0}))


if __name__ == "__main__":
    main()
