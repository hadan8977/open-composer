"""Independent bounded H5 reception; no model loads, inference, training or replay."""

import csv
import hashlib
import json
import math
import resource
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
D = ROOT / "reports/research/program/day-goal-20261013/dlsa/deepening"
F = D / "runtime/attempts/dlsa-fold10-native-A09A10-cont01-20261013/fetched"
OUT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def main():
    start = time.monotonic()
    final = read(D / "final-manifest.json")
    result = read(D / "result.json")
    budget = read(D / "terminal-budget-review-packet.json")
    bindings = []
    for row in final["files"]:
        p = ROOT / row["path"]
        assert p.stat().st_size == row["bytes"] and sha(p) == row["sha256"], row["path"]
        bindings.append(row)
    transport = read(F / "transport-manifest.json")
    assert transport["returncode"] == 0
    for row in transport["artifacts"]:
        p = F / row["path"]
        p.resolve().relative_to(F.resolve())
        assert p.stat().st_size == row["bytes"] and sha(p) == row["sha256"]
    runtime = read(F / "runtime-receipt.json")
    continuation = read(F / "fold10-matched-training/continuation-receipt.json")
    assert runtime["returncode"] == 0 and runtime["new_completed_batch_notifications"] == 1600
    assert continuation["executed_through_fit_id"] == "A10-fold10"
    assert continuation["old_outputs_immutable"]
    assert {tuple(x.values()) for x in continuation["completed"]} == {
        ("A09-fold10", "fit"),
        ("A09-fold10", "replay"),
        ("A10-fold10", "fit"),
        ("A10-fold10", "replay"),
    }
    fit_checks = []
    for fit in ["A09-fold10", "A10-fold10"]:
        folder = F / "fold10-matched-training" / fit
        native = read(folder / "fit/result.json")
        author = read(D / f"author-{fit[:3]}-accounting-verification.json")
        assert native["epoch"] == 99 and native["optimizer_updates"] == 800
        steps = [
            json.loads(x) for x in (folder / "fit/training-steps.jsonl").read_text().splitlines()
        ]
        assert len(steps) == 800
        assert [s["optimizer_update"] for s in steps] == list(range(1, 801))
        assert all(math.isfinite(s["loss"]) for s in steps)
        assert all(s["epoch"] == i // 8 and s["batch"] == i % 8 for i, s in enumerate(steps))
        assert all(s["rows"] == (95 if s["batch"] == 7 else 125) for s in steps)
        assert author["epochs_completed"] == 100
        assert author["fixed_snapshots_verified"] == 11
        assert author["last_epoch_selected_in_advance"] == 99
        targets = np.load(folder / "replay/final-stock-targets.npy", allow_pickle=False)
        assert list(targets.shape) == author["targets_shape"]
        assert np.isfinite(targets).all()
        norm_error = float(np.max(np.abs(np.sum(np.abs(targets), axis=1) - 1)))
        assert norm_error < 1e-5
        h1 = list(csv.DictReader((folder / "replay/episode-daily-ledger.csv").open()))
        assert len(h1) == 750
        net_error = max(
            abs(
                float(r["net"])
                - (float(r["gross"]) - float(r["transaction_cost"]) - float(r["short_cost"]))
            )
            for r in h1
        )
        assert net_error < 1e-10
        source_rows = [
            r
            for r in h1
            if r["profile"] == "CONTINUOUS_TARGET_DIAGNOSTIC" and r["cost"] == "SOURCE_NATIVE"
        ]
        assert len(source_rows) == 125
        turnover_error = max(
            abs(float(r["transaction_cost"]) - 0.0005 * float(r["charged_turnover"]))
            for r in source_rows
        )
        short_error = max(
            abs(float(r["short_cost"]) - 0.0001 * float(r["short_notional"])) for r in source_rows
        )
        assert turnover_error < 1e-10 and short_error < 1e-10
        observed_shorts = np.sum(np.maximum(-targets.astype(np.float64), 0), axis=1)
        assert (
            max(
                abs(observed_shorts[i] - float(source_rows[i]["short_notional"]))
                for i in range(125)
            )
            < 1e-6
        )
        h5 = read(folder / "replay/SOURCE_H5-payoffs-nonNAV.json")
        assert all(len(x) == 125 and x[:5] == [0] * 5 for x in h5.values())
        delta5 = np.abs(targets[5:].astype(np.float64) - targets[:-5].astype(np.float64)).sum(
            axis=1
        )
        h5_cost_expected = (0.0005 * delta5 + 0.0001 * observed_shorts[5:]) / 5
        h5_fee_error = float(
            np.max(
                np.abs(
                    np.asarray(h5["ZERO"])[5:]
                    - np.asarray(h5["SOURCE_NATIVE"])[5:]
                    - h5_cost_expected
                )
            )
        )
        assert h5_fee_error < 1e-7
        fit_checks.append(
            {
                "fit_id": fit,
                "epoch": 99,
                "finite_updates": len(steps),
                "snapshot_count_reused_author_verified": 11,
                "target_shape": list(targets.shape),
                "L1_norm_max_error": norm_error,
                "H1_rows": len(h1),
                "H1_net_identity_max_error": net_error,
                "H1_turnover_fee_max_error": turnover_error,
                "H1_short_fee_max_error": short_error,
                "H5_lag5_and_short_fee_max_error": h5_fee_error,
                "H5_first5zeros_and_five25row_phases": True,
                "gross_H5_not_reinferred": True,
            }
        )
    terminal = read(D / "provider-terminal-observation.json")
    assert terminal["matching_rows"][0]["state"] == "stopped"
    assert terminal["matching_rows"][0]["tasks"] == "0"
    assert result["counts"]["accepted_start_and_still_authoritative"] == {
        "fits": 10,
        "updates": 8000,
    }
    assert budget["function_wall_seconds"] < budget["new_call_function_seconds_cap"]
    assert budget["observed_call_billed_USD"] <= budget["call_total_worst_USD_preserved"]
    assert not budget["reservation_release_or_settlement"]
    usage = resource.getrusage(resource.RUSAGE_SELF)
    receipt = {
        "command": "accept_h5.py",
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "wall_seconds": time.monotonic() - start,
        "max_rss_kib": usage.ru_maxrss,
        "CPU_limit_seconds": 120,
        "memory_limit_mib": 512,
        "fits_run": 0,
        "model_loads_or_inference_or_replay": 0,
        "source_requests": 0,
    }
    assert receipt["cpu_seconds"] < 120 and receipt["max_rss_kib"] < 512 * 1024
    acceptance = {
        "task_id": "DAY3-DLSA-DEEPENING",
        "author": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
        "reviewer": "f9add224-744b-471c-b812-c43cc179fa38",
        "as_of_utc": datetime.now(UTC).isoformat(),
        "verdict": (
            "accept_completed_original_A09_A10_method_results_with_nonNAV_and_runtime_limits"
        ),
        "author_reviewer_independent": True,
        "actual_fit_checks": fit_checks,
        "artifact_bindings_rechecked": len(bindings),
        "transport_files_checked": len(transport["artifacts"]),
        "final_manifest": {
            "path": str((D / "final-manifest.json").relative_to(ROOT)),
            "sha256": sha(D / "final-manifest.json"),
        },
        "terminal_budget": {
            "path": str((D / "terminal-budget-review-packet.json").relative_to(ROOT)),
            "sha256": sha(D / "terminal-budget-review-packet.json"),
        },
        "counts": {
            "authoritative_retained": {"fits": 10, "updates": 8000},
            "new_independently_received": {"fits": 2, "updates": 1600},
            "Root_may_accept_complete_evidence_total": {"fits": 12, "updates": 9600},
            "authoritative_counts_modified_by_reviewer": False,
        },
        "source_clock_interpretation": (
            "Original H5 anchored residual-coefficient overlapping product payoff, "
            "lag5 endpoint target fees and short penalty divided by5; "
            "initial5zeros and interleaved phases. "
            "Not self-financing daily NAV or fixed stock5dayholding. "
            "H1 common target accounting separate."
        ),
        "limits": [
            "Perturbed anonymous inputs; no marketAlpha or paper readiness",
            "No independent second gross-H5 model inference; reuse bound actual source replay",
            "800CUDAwarning contexts/93000warnings perfit; deterministic algorithm not guaranteed",
            "SDK32GiB/RSS28.36GiB do not prove kernelmemorycap or16GiB suitability",
            "One seed/two125rowepisodes; original24fitstudy incomplete; no automatic extra fits",
            "Observed bill1.87739304USD not final invoice; reservations/margins retained",
        ],
        "resource_receipt": receipt,
        "workflow_pass_scoped": True,
        "research_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "real_market_return": None,
        "new_orders": 0,
        "next_action": "Continue bridge acquisition; H5 receipt is not data task final.",
    }
    (D / "independent-H5-result-acceptance.json").write_text(
        json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n"
    )
    (OUT / "H5-reception-resource-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "verdict": acceptance["verdict"],
                "resource": receipt,
                "fits_received": 2,
                "authoritative_fits_retained": 10,
            }
        )
    )


if __name__ == "__main__":
    main()
