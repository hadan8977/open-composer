"""Read and reconcile the completed fixed fit; no inference, fit or model selection."""

import argparse
import csv
import datetime
import hashlib
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = (
    Path(__file__).resolve().parents[5]
    / "reports/research/program/day-goal-20261011-2/dlsa-first-training-batch-runtime"
    / "modal-next-fold-continuation"
)
sys.path.insert(0, str(BASE / "result-preparation"))
from matched_baseline_accounting import reconcile_baselines  # noqa: E402
from result_bindings import (  # noqa: E402
    admission_bindings,
    expected_artifacts,
    verify_actual_inputs,
)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.process_time()
    here = Path(__file__).resolve().parent
    root = next(p for p in here.parents if (p / "scripts/modal_budget.py").exists())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-id", required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    args = parser.parse_args()
    fit_id = args.fit_id
    handoff = read(args.handoff.resolve())
    assert handoff["fit_id"] == fit_id
    snapshot_path = Path(handoff["snapshot_receipt"]["path"])
    assert sha(snapshot_path) == handoff["snapshot_receipt"]["sha256"]
    snapshot = read(snapshot_path)
    science = Path(handoff["local_science_root"])
    admission, code = admission_bindings(BASE)
    assert fit_id in admission["fit_ids"]
    config = next(
        r for r in read(code / "training-configs.json")["candidates"] if r["fit_id"] == fit_id
    )
    assert config["holding_days"] == 1, "H5 needs separate payoff-objective accounting"
    stream = config["stream"]
    for item in admission["verified_small_bindings"]:
        if item["group"] == "code":
            path = code / item["path"]
            assert path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
    assert len(snapshot["artifacts"]) == len(expected_artifacts(fit_id, 1))
    assert {x["path"] for x in snapshot["artifacts"]} == expected_artifacts(fit_id, 1)
    assert 0 < snapshot["total_bytes"] <= admission["output_limits"]["returned_artifact_cap_bytes"]
    for item in snapshot["artifacts"]:
        path = snapshot_path.parent / item["path"]
        assert path.resolve().is_relative_to(snapshot_path.parent)
        assert path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
    assert sum(i["bytes"] for i in snapshot["artifacts"]) == snapshot["total_bytes"]
    fit = read(science / "fit/result.json")
    replay = read(science / "replay/result.json")
    for result in (fit, replay):
        assert result["fit_id"] == fit_id
        assert result["plan_sha256"] == admission["scientific_plan_sha256"]
        assert result["configs_sha256"] == admission["scientific_configs_sha256"]
        assert result["canonical_version"] and result["strict_deterministic_mode_at_result"]
        assert not result["market_alpha_or_paper"]
    assert fit["status"] == "matched_source_model_fitted"
    assert fit_id in {"A07-fold10", "A08-fold10"}
    prior_updates = 61 if fit_id == "A07-fold10" else 0
    current_updates = 800 - prior_updates
    assert fit["optimizer_updates"] == 800
    assert fit["empirical_optimizer_updates"] == current_updates
    assert fit["empirical_optimizer_updates_this_attempt"] == current_updates
    assert fit["Adam_updates_attempted_this_process"] == current_updates
    assert fit["Adam_updates_completed_finite_this_process"] == current_updates
    if prior_updates:
        old = (
            BASE
            / "attempts/dlsa-fold10-sixfits-attempt02-20261012/partial"
            / "fold10-matched-training/A07-fold10"
        )
        assert (science / "input-manifest.json").read_bytes() == (
            old / "input-manifest.json"
        ).read_bytes()
        assert (
            (science / "fit/training-steps.jsonl")
            .read_bytes()
            .startswith((old / "fit/training-steps.jsonl").read_bytes())
        )
        assert (science / "fit/validation-epoch0.pt").read_bytes() == (
            old / "fit/validation-epoch0.pt"
        ).read_bytes()

    assert fit["epoch"] == 99 and not fit["H5_backward_warning_events"]
    assert replay["status"] == "fixed_source_snapshots_and_final99_episode_replayed"
    assert replay["original_train_return_refers_epoch90"]
    assert replay["final_eval_refers_epoch99"]
    assert not replay["future_validation_used_for_selection"]
    assert not replay["pooled406_continuous_NAV_allowed"]
    assert replay["empirical_optimizer_updates"] == 0
    verify_actual_inputs(BASE, science, config)
    input_manifest = read(science / "input-manifest.json")
    replay_input = read(science / "replay-input-manifest.json")
    assert replay_input["native_fit_input_manifest_sha256"] == sha(science / "input-manifest.json")
    assert input_manifest["files"] == replay_input["files"]
    assert input_manifest["selection_allowed"] is False
    steps = [json.loads(line) for line in (science / "fit/training-steps.jsonl").open()]
    assert len(steps) == 800
    for index, row in enumerate(steps):
        assert (row["epoch"], row["batch"], row["optimizer_update"]) == (
            index // 8,
            index % 8,
            index + 1,
        )
        assert row["rows"] == (95 if index % 8 == 7 else 125)
        assert math.isfinite(row["loss"])
        timings = row["timings"]
        assert timings["whole_batch_bmm"]
        assert timings["optimization_rows"] == row["rows"]
        assert all(
            math.isfinite(timings[k]) and timings[k] >= 0
            for k in (
                "forward_projection_loss_seconds",
                "backward_seconds",
                "Adam_seconds",
                "total_update_seconds",
                "CPU_process_seconds",
            )
        )
    validation = read(science / "replay/source-validation-epoch0-90-and-final99.json")
    assert [x["epoch"] for x in validation] == [*range(0, 100, 10), 99]
    for row in validation:
        name = f"validation-epoch{row['epoch']}.pt" if row["epoch"] != 99 else "final-epoch99.pt"
        assert row["snapshot_sha256"] == sha(science / "fit" / name)
        assert not row["selection_allowed"]
        assert row["is_final99_replay"] == (row["epoch"] == 99)
        assert math.isclose(row["source_loss"], -row["source_Sharpe"], abs_tol=1e-12)
        assert math.isclose(
            row["source_mean"] / row["source_std"], row["source_Sharpe"], rel_tol=2e-7
        )
    targets = np.load(science / "replay/final-stock-targets.npy", allow_pickle=False)
    assert targets.shape == (125, 2434) and targets.dtype == np.float32
    assert np.isfinite(targets).all()
    gross_notional = np.abs(targets).sum(axis=1)
    assert np.allclose(gross_notional, 1, atol=3e-7, rtol=0)
    turnover = np.zeros(125, dtype=np.float32)
    turnover[1:] = np.abs(targets[1:] - targets[:-1]).sum(axis=1)
    short = np.abs(np.minimum(targets, 0)).sum(axis=1)
    grouped = defaultdict(list)
    with (science / "replay/episode-daily-ledger.csv").open() as handle:
        for row in csv.DictReader(handle):
            assert row["fold"] == "10" and row["stream"] == stream
            grouped[(row["profile"], row["cost"])].append(row)
    profiles = {"SOURCE_RESET", "CONTINUOUS_TARGET_DIAGNOSTIC"}
    costs = {"ZERO": (0, 0), "SOURCE_NATIVE": (0.0005, 0.0001), "DOUBLE_SOURCE": (0.001, 0.0002)}
    assert set(grouped) == {(p, c) for p in profiles for c in costs}
    summaries = []
    gross_reference = None
    max_short_delta = 0.0
    for (profile, cost), values in sorted(grouped.items()):
        assert [int(x["sample_index"]) for x in values] == list(range(2250, 2375))
        tc, hc = costs[cost]
        net_values, gross_values = [], []
        for i, row in enumerate(values):
            charged = float(turnover[i])
            if i == 0 and profile == "CONTINUOUS_TARGET_DIAGNOSTIC":
                charged = float(gross_notional[0])
            reported = (
                float(turnover[1:].mean()) if i == 0 and profile == "SOURCE_RESET" else charged
            )
            assert math.isclose(float(row["charged_turnover"]), charged, abs_tol=3e-7)
            assert math.isclose(float(row["reported_turnover"]), reported, abs_tol=3e-7)
            diff = abs(float(row["short_notional"]) - float(short[i]))
            max_short_delta = max(max_short_delta, diff)
            assert diff <= 3e-7
            assert math.isclose(float(row["transaction_cost"]), tc * charged, abs_tol=1e-9)
            assert math.isclose(
                float(row["short_cost"]), hc * float(row["short_notional"]), abs_tol=1e-9
            )
            net, gross = float(row["net"]), float(row["gross"])
            assert math.isfinite(net) and math.isfinite(gross)
            assert math.isclose(
                net, gross - float(row["transaction_cost"]) - float(row["short_cost"]), abs_tol=1e-9
            )
            net_values.append(net)
            gross_values.append(gross)
        if gross_reference is None:
            gross_reference = gross_values
        assert gross_values == gross_reference
        summaries.append(
            {
                "profile": profile,
                "cost": cost,
                "rows": 125,
                "daily_net_mean_bps": statistics.mean(net_values) * 10000,
                "fixed_episode_compounded_method_return": math.prod(1 + x for x in net_values) - 1,
                "annualized_profitability_claim": False,
            }
        )
    trained_cost = config["training_costs"]
    source_objective = [
        float(r["gross"])
        - trained_cost["trans_cost"] * float(r["charged_turnover"])
        - trained_cost["hold_cost"] * float(r["short_notional"])
        for r in grouped[("SOURCE_RESET", "ZERO")]
    ]
    assert math.isclose(
        statistics.mean(source_objective) * 252,
        validation[-1]["source_mean"],
        rel_tol=1e-6,
        abs_tol=1e-7,
    )
    assert math.isclose(
        statistics.stdev(source_objective) * math.sqrt(252),
        validation[-1]["source_std"],
        rel_tol=1e-6,
        abs_tol=1e-7,
    )
    baseline = reconcile_baselines(BASE, grouped)
    output = {
        "utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "verdict": "author_H1_accounting_verified_independent_Root_acceptance_pending",
        "author": "c14e62bb-2981-472d-adf1-32f3675b7612",
        "reviewer": None,
        "independent_Root_scientific_acceptance_pending": True,
        "snapshot": {"path": str(snapshot_path.relative_to(root)), "sha256": sha(snapshot_path)},
        "root_admission_sha256": sha(BASE / "r2/Root-final-runtime-admission.json"),
        "matched_fold10_baseline_accounting": baseline,
        "artifacts_verified": len(snapshot["artifacts"]),
        "bytes_verified": snapshot["total_bytes"],
        "original_scientific_fit_id": fit_id,
        "original_training_costs": trained_cost,
        "full_fits_delta": 1,
        "epochs_completed": 100,
        "optimizer_updates_completed_finite": 800,
        "prior_native_updates_restored": prior_updates,
        "current_finite_updates": current_updates,
        "old_Root_acceptance_slot_reused": False,
        "fixed_snapshots_verified": 11,
        "last_epoch_selected_in_advance": 99,
        "prior_failed_call_optimizer_exposure": admission["prior_partial_optimizer_exposure"],
        "model_state_load_replay_evidence": (
            "Bound replay loaded every checkpoint with weights_only=True and exact "
            "fit/epoch/input hash checks; Root does not load or infer again."
        ),
        "whole_125x7_plus95_batches_per_epoch": True,
        "ledger_rows_reconciled": 750,
        "targets_shape": list(targets.shape),
        "maximum_CPU_vs_GPU_short_reduction_difference": max_short_delta,
        "method_results": summaries,
        "resource": {
            "fit_CPU_seconds": fit["CPU_seconds"],
            "fit_wall_seconds": fit["wall_seconds"],
            "replay_CPU_seconds": replay["CPU_seconds"],
            "replay_wall_seconds": replay["wall_seconds"],
            "fit_process_lifetime_max_RSS_GiB": fit["peak_RSS_KiB_process"] / 1024**2,
            "declared_container_memory_GiB": 32,
            "actual_container_cgroup_memory": None,
            "actual_kernel_memory_capacity_unverified": True,
            "fits_in_16GiB_host_claim": False,
            "GPU_max_allocated_bytes": fit["CUDA_max_memory_allocated"],
            "GPU_max_reserved_bytes": fit["CUDA_max_memory_reserved"],
            "author_verification_CPU_seconds": time.process_time() - started,
        },
        "workflow_pass_scoped": True,
        "research_pass": False,
        "ml_contribution_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "economic_package_delta": 0,
        "real_account_performance": None,
        "new_fits_in_verification": 0,
        "limits": [
            "Anonymous perturbed data; dates, permanent IDs and causal input identity unknown.",
            "One125row episode of24 fixed fits; no pooled NAV or market selection.",
            "Uses the selected-in-advance original loss; other fixed fits remain separate.",
            "Counters verified; kernel memory capacity and final billing remain unestablished.",
        ],
    }
    target = args.handoff.resolve().parent / f"author-{stream}-accounting-verification.json"
    with target.open("x") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "path": str(target.relative_to(root)),
                "sha256": sha(target),
                "CPU_seconds": output["resource"]["author_verification_CPU_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
