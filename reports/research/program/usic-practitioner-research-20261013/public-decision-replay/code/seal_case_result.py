"""Bind completed case outputs and inclusive economic resources without new trials."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[4]
OUT = P / "replay-result"


def bind(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def outer_cpu(path):
    text = path.read_text()
    value = sum(
        float(re.search(label + r" time \(seconds\): ([0-9.]+)", text).group(1))
        for label in ("User", "System")
    )
    return {
        "resource": bind(path),
        "outer_inclusive_CPU": value,
        "RSS_KiB": int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)),
        "exit": int(re.search(r"Exit status: (\d+)", text).group(1)),
        "inner_CPU_not_added": True,
    }


def main():
    assert (OUT / "consumed-admission.json").is_file()
    core = json.loads((OUT / "result.json").read_text())
    assert len(core["trajectories"]) == 16
    rows = []
    files = []
    for ordinal, row in enumerate(core["trajectories"]):
        path = ROOT / row["binding"]["path"]
        assert bind(path) == row["binding"]
        obj = json.loads(path.read_text())
        assert len(obj["transaction_costs"]) == 3 and len(obj["mandatory_borrow_stress"]) == 6
        t = obj["trajectory"]
        primary = next(x for x in obj["transaction_costs"] if x["bps_per_filled_side"] == 20)
        rows.append(
            {
                "ordinal": ordinal,
                "case_id": obj["case_id"],
                "method": obj["method"],
                "delay": obj["delay_minutes"],
                "status": t["status"],
                "entry": t.get("entry"),
                "exit": t.get("exit"),
                "Pref": t.get("Pref"),
                "S": t.get("S"),
                "q0": t.get("q0"),
                "original_R0": t.get("R0"),
                "unknown_at_NY": t.get("unknown_at_NY"),
                "primary_20bps_R": primary.get("transaction_adjusted_R"),
                "primary_20bps_fees_USD": primary.get("fee_USD"),
                "actual_borrow_cost": None,
                "source_and_input": row["binding"],
            }
        )
        files.append(path)
    save(
        OUT / "mechanism-results.json",
        {
            "rows": rows,
            "status_counts": dict(Counter(x["status"] for x in rows)),
            "all_fixed_price_cost_borrow_cells_retained": [16, 48, 96],
            "population_stats_private_CAGR": None,
            "pretrade_frozen_risk_budget_not_equal_share_comparison": True,
            "not_source_actual_trades": True,
            "source_selected_seen": True,
            "source_HOD_breakdown_stop_or_SENS_rejection_not_reproduced": True,
        },
    )
    (OUT / "price-trial-ledger.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "trial_id": f"{x['case_id']}-{x['method']}-d{x['delay']}",
                    "iter_id": "usic_public_decision_replay_20261014",
                    "role": "conditional_case_price_mechanism",
                    "promotion_eligible": False,
                    "status": x["status"],
                    "case_id": x["case_id"],
                    "method": x["method"],
                    "delay": x["delay"],
                    "binding": x["source_and_input"],
                }
            )
            + "\n"
            for x in rows
        )
    )
    save(
        OUT / "execution-resource-accounting.json",
        {
            "run": outer_cpu(P / "economic-run-resource.txt"),
            "seal_unknown_setup_CPU_allowance": 5,
            "accounting_note": (
                "Finalseal resource may replace its conservative allowance if measured; "
                "never add the same inner and outer CPU twice."
            ),
            "allocation": json.loads(
                (P / "independent-economic-resource-decision.json").read_text()
            )["allocation"],
            "original_economic_pool_cap": 7200,
            "old_economic_CPU_used": 0,
            "market_new_requests": 0,
            "new_fits_orders": 0,
        },
    )
    files += [
        OUT / name
        for name in (
            "result.json",
            "progress.json",
            "mechanism-results.json",
            "price-trial-ledger.jsonl",
            "consumed-admission.json",
            "execution-resource-accounting.json",
        )
    ]
    files += [
        P / name
        for name in (
            "independent-economic-resource-decision.json",
            "economic-run-resource.txt",
            "economic-run-log.txt",
            "preoutcome-interpretation-boundaries.json",
            "practitioner-mechanism-comparison.json",
        )
    ]
    save(
        OUT / "result-manifest.json",
        {
            "author": "f9add224-744b-471c-b812-c43cc179fa38",
            "reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
            "bindings": [bind(x) for x in files],
            "input_acceptance": bind(P / "acquisition/independent-input-acceptance.json"),
            "source_timelines": bind(P / "inherited-public-decision-timelines.json"),
            "scope": (
                "Complete sixteen conditional case paths with costs and fixed borrow stress, "
                "including invalid/missing/no-fill. No private-account or population return claim."
            ),
            "complete_result_acceptance_pending": True,
            "research_pass": False,
            "paper_ready_pass": False,
        },
    )
    print(
        json.dumps(
            {
                "sealed_price_trajectories": 16,
                "cost_cells": 48,
                "borrow_cells": 96,
                "status_counts": dict(Counter(x["status"] for x in rows)),
            }
        )
    )


if __name__ == "__main__":
    main()
