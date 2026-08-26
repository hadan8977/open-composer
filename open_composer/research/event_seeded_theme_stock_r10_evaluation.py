from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.dynamic_theme_stock_r9_evaluation import (
    _artifact_ref,
    _benchmark_family,
    _binding,
    _build_price_bindings,
    _daily_returns,
    _equal_weight_selected_theme_targets,
    _evaluate_folds,
    _load_json,
    _run_cost_views,
    _sha256,
    _split_contract,
    _verify_binding,
    _write_jsonl,
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
    development_folds,
    load_r9_stage_d_panel,
)
from open_composer.research.event_seeded_theme_stock_r10 import (
    compute_r10_d01_targets,
    compute_r10_d02_targets,
    validate_r10_spec_pair,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_event_seeded_theme_stock_r10"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
STAGE_D_LOCK_PATH = ITERATION_DIR / "lock-set/stage-d-lock.json"
STAGE_D_REPORT_PATH = ITERATION_DIR / "stage-d-development-report.json"
RUNNER_PATH = Path("open_composer/research/event_seeded_theme_stock_r10_evaluation.py")
TARGET_PATH = Path("open_composer/research/event_seeded_theme_stock_r10.py")
TEST_PATHS = (
    Path("tests/test_event_seeded_theme_stock_r10.py"),
    Path("tests/test_event_seeded_theme_stock_r10_evaluation.py"),
)
SHARED_EVALUATION_PATH = Path("open_composer/research/dynamic_theme_stock_r9_evaluation.py")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_event_seeded_theme_stock_r10_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R10D01", "d01"),
        ("R10D02", "d02"),
        ("R10M01", "m01"),
        ("R10M02", "m02"),
        ("R10L01", "l01"),
        ("R10C01", "c01"),
        ("R10F01", "f01"),
        ("R10P01", "p01"),
    )
}
EFFECTIVE_TRIAL_COUNT = 8030
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
STAGE_D_LOCK_STATUS = (
    "development_only_implementation_and_data_locked_before_first_r10_historical_target_calculation"
)


@dataclass(frozen=True)
class R10StageDResult:
    report_path: Path
    markdown_path: Path
    payload: dict[str, Any]


def freeze_event_seeded_theme_stock_r10_stage_d(root: Path) -> Path:
    base = root.resolve()
    lock_path = base / STAGE_D_LOCK_PATH
    if lock_path.exists():
        raise ValueError("R10 Stage D lock already exists")
    if (base / STAGE_D_REPORT_PATH).exists():
        raise ValueError("R10 Stage D result exists before its implementation lock")

    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R10 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r10_spec_pair(specs["R10D01"], specs["R10D02"])
    price_files, source_files = _build_price_bindings(base, specs["R10D01"])
    split = _split_contract(price_files, base)

    iteration_files = sorted(
        path
        for path in (base / ITERATION_DIR).iterdir()
        if path.is_file() and path.name != "decision-record.md"
    )
    preregistration_files = [
        *iteration_files,
        base / "reports/harness/source_cards/us_event_seeded_theme_stock_r10.jsonl",
        base / "capabilities/registry.yaml",
        base / "open_composer/research/factor_library.py",
    ]
    implementation_files = [
        base / TARGET_PATH,
        base / RUNNER_PATH,
        *(base / path for path in TEST_PATHS),
        base / SHARED_EVALUATION_PATH,
        base / "open_composer/research/etf_structural_r9.py",
        base / "open_composer/models/strategy_spec.py",
        base / "open_composer/strategy_versions.py",
        base / "schemas/strategy_spec.schema.json",
    ]
    lock = {
        "schema_version": 1,
        "lock_contract": "event_seeded_theme_stock_r10_stage_d_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": STAGE_D_LOCK_STATUS,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "preregistration_files": [_binding(path, base) for path in preregistration_files],
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "implementation_files": [_binding(path, base) for path in implementation_files],
        "source_files": source_files,
        "price_files": price_files,
        "split": split,
        "historical_file_format_inspected_before_lock": True,
        "historical_candidate_targets_or_metrics_computed_before_lock": False,
        "lockbox_numeric_fields_materialized": False,
        "model_training_before_lock": False,
        "order_authority": False,
        "broker_writes": False,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=False)
    write_json(lock_path, lock)
    return lock_path


def run_event_seeded_theme_stock_r10_stage_d(root: Path) -> R10StageDResult:
    base = root.resolve()
    report_path = base / STAGE_D_REPORT_PATH
    if report_path.exists():
        raise ValueError("R10 Stage D development diagnostic is one-shot")
    preflight = _stage_d_preflight(base)
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    d01_spec = specs["R10D01"]
    d02_spec = specs["R10D02"]
    panel = load_r9_stage_d_panel(base, preflight["lock"])

    d01_targets, d01_records = compute_r10_d01_targets(
        panel.open,
        panel.close,
        panel.volume,
        panel.membership,
        d01_spec,
    )
    d02_targets, d02_records = compute_r10_d02_targets(
        panel.open,
        panel.close,
        panel.volume,
        panel.membership,
        d02_spec,
    )
    targets_by_id = {"R10D01": d01_targets, "R10D02": d02_targets}
    records_by_id = {"R10D01": d01_records, "R10D02": d02_records}
    common_start = max(frame.index.min() for frame in targets_by_id.values())
    common_end = panel.open.index.max()
    evaluation_sessions = panel.open.index[
        (panel.open.index >= common_start) & (panel.open.index <= common_end)
    ]
    folds = development_folds(evaluation_sessions)

    candidate_results: dict[str, dict[str, Any]] = {}
    primary_returns: dict[str, pd.Series] = {}
    fold_results: dict[str, list[dict[str, Any]]] = {}
    for candidate_id, targets in targets_by_id.items():
        cost_results, simulations = _run_cost_views(
            panel.open,
            targets,
            start=common_start,
            end=common_end,
        )
        primary_returns[candidate_id] = _daily_returns(simulations["primary_20bps"])
        rows = _evaluate_folds(panel.open, targets, folds)
        fold_results[candidate_id] = rows
        candidate_results[candidate_id] = {
            "strategy_name": specs[candidate_id].name,
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_semantic_sha256": strategy_content_hash(specs[candidate_id]),
            "target_count": len(targets),
            "first_execution_session": targets.index.min().date().isoformat(),
            "last_execution_session": targets.index.max().date().isoformat(),
            "cost_views": cost_results,
            "folds": rows,
        }

    selected_theme_targets = _equal_weight_selected_theme_targets(
        d01_targets,
        tuple(map(str, panel.membership.columns)),
    )
    benchmarks = _benchmark_family(
        panel.open,
        selected_theme_targets,
        tuple(map(str, panel.membership.columns)),
        start=common_start,
        end=common_end,
    )
    benchmarks["equal_weight_selected_theme"]["construction"] = (
        "equal weight among each R10D01 session's selected event-theme stocks"
    )
    dsr = {
        candidate_id: deflated_sharpe_probability(returns, EFFECTIVE_TRIAL_COUNT)
        for candidate_id, returns in primary_returns.items()
    }
    pbo = cscv_probability_backtest_overfitting(primary_returns, block_count=8)
    pbo["method"] = "eight_block_CSCV_deterministic_R10_stage_D_provisional"
    pbo["status"] = "provisional_until_R10M01_R10M02_are_frozen"
    qqq_metrics = benchmarks["QQQ_buy_hold"]["cost_views"]["primary_20bps"]
    tqqq_metrics = benchmarks["TQQQ_buy_hold"]["cost_views"]["primary_20bps"]
    d02_metrics = candidate_results["R10D02"]["cost_views"]["primary_20bps"]
    theme_diagnostics = _event_theme_diagnostics(d01_records)
    for candidate_id, candidate in candidate_results.items():
        metrics = candidate["cost_views"]["primary_20bps"]
        severe = candidate["cost_views"]["severe_40bps"]
        positive_lift_folds = sum(float(row["qqq_cagr_lift"]) > 0 for row in candidate["folds"])
        gates = _development_performance_gates(
            candidate_id=candidate_id,
            metrics=metrics,
            severe_metrics=severe,
            qqq_metrics=qqq_metrics,
            tqqq_metrics=tqqq_metrics,
            positive_lift_folds=positive_lift_folds,
            dsr=dsr[candidate_id],
            pbo=pbo,
            d02_metrics=d02_metrics,
            theme_diagnostics=theme_diagnostics,
        )
        candidate["positive_qqq_lift_fold_count"] = positive_lift_folds
        candidate["deflated_sharpe"] = dsr[candidate_id]
        candidate["development_performance_gates"] = gates
        candidate["development_performance_pass"] = all(row["pass"] for row in gates)
        candidate["research_pass"] = False
        candidate["paper_ready_pass"] = False

    stock_columns = list(panel.membership.columns)
    implementation_checks = {
        "prebacktest_dossier_pass": preflight["dossier_status"] == "ok",
        "exact_diagnostic_stock_count": panel.membership.shape[1] == 62,
        "development_only_numeric_materialization": panel.metadata["lockbox_values_loaded"]
        is False,
        "next_session_target_semantics": all(
            len(records) == len(targets_by_id[candidate_id])
            for candidate_id, records in records_by_id.items()
        ),
        "event_seeds_observed": theme_diagnostics["event_seed_count"] > 0,
        "target_weights_sum_to_one": all(
            np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)
            for targets in targets_by_id.values()
        ),
        "d01_stock_weight_cap": float(d01_targets[stock_columns].max().max()) <= 0.15 + 1e-12,
        "d01_theme_budget_cap": float(d01_targets[stock_columns].sum(axis=1).max()) <= 0.40 + 1e-12,
        "d02_stock_independence": not bool((d02_targets[stock_columns] > 0).any().any()),
        "broker_writes_false": True,
    }
    workflow_pass = all(implementation_checks.values())
    d01_development_pass = bool(candidate_results["R10D01"]["development_performance_pass"])
    stage_e_training_authorized = workflow_pass and d01_development_pass
    decision = (
        "stop_r10_implementation_failure"
        if not workflow_pass
        else "continue_to_fold_local_ml_diagnostic"
        if stage_e_training_authorized
        else "stop_r10_deterministic_no_lift"
    )
    methodology_blockers = [
        "historical_PIT_membership_missing",
        "inactive_and_delisted_securities_missing",
        "terminal_delisting_returns_missing",
        "historical_PIT_narrative_packets_missing",
    ]

    output = base / ITERATION_DIR
    target_path = output / "stage-d-target-ledger.jsonl"
    trial_path = output / "stage-d-trial-ledger.jsonl"
    fold_path = output / "stage-d-fold-results.json"
    benchmark_path = output / "stage-d-benchmark-results.json"
    implementation_path = output / "stage-d-implementation-contract.json"
    _write_jsonl(target_path, [*d01_records, *d02_records])
    _write_jsonl(
        trial_path,
        [
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "stage": "D_development_rejection_only",
                "candidate_id": candidate_id,
                "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
                "development_performance_pass": candidate["development_performance_pass"],
                "research_pass": False,
                "cost_views": candidate["cost_views"],
                "folds": candidate["folds"],
            }
            for candidate_id, candidate in candidate_results.items()
        ],
    )
    write_json(
        fold_path,
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "stage": "D_development_rejection_only",
            "folds": folds,
            "candidate_results": fold_results,
            "pbo": pbo,
        },
    )
    write_json(benchmark_path, {"schema_version": 1, "iter_id": ITER_ID, "benchmarks": benchmarks})
    implementation_contract = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "stage": "D_development_rejection_only",
        "checks": implementation_checks,
        "workflow_pass": workflow_pass,
        "lockbox_values_loaded": False,
        "order_authority": False,
        "broker_writes": False,
    }
    write_json(implementation_path, implementation_contract)

    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "report_type": "event_seeded_theme_stock_r10_stage_d_development_diagnostic",
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "order_authority": False,
        "broker_writes": False,
        "development_performance_candidate_ids": sorted(
            candidate_id
            for candidate_id, candidate in candidate_results.items()
            if candidate["development_performance_pass"]
        ),
        "methodology_blockers": methodology_blockers,
        "stage_e_training_authorized": stage_e_training_authorized,
        "lockbox": {
            **preflight["lock"]["split"],
            "numeric_values_accessed": False,
            "access_count": 0,
        },
        "data": panel.metadata,
        "evaluation_window": {
            "start": common_start.date().isoformat(),
            "end": common_end.date().isoformat(),
            "market_session_count": len(evaluation_sessions),
            "historical_scope": "current_survivor_diagnostic_rejection_evidence_only",
        },
        "cost_views_bps": COST_VIEWS,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "event_theme_diagnostics": theme_diagnostics,
        "candidates": candidate_results,
        "benchmarks": benchmarks,
        "pbo": pbo,
        "implementation_contract": implementation_contract,
        "artifacts": {
            "stage_d_lock": _artifact_ref(base / STAGE_D_LOCK_PATH, base),
            "target_ledger": _artifact_ref(target_path, base),
            "trial_ledger": _artifact_ref(trial_path, base),
            "fold_results": _artifact_ref(fold_path, base),
            "benchmark_results": _artifact_ref(benchmark_path, base),
            "implementation_contract": _artifact_ref(implementation_path, base),
        },
        "next_stage": {
            "R10M01_R10M02_fold_local_training_allowed": stage_e_training_authorized,
            "historical_R10L01_R10C01_R10P01_allowed": False,
            "lockbox_access_allowed_before_model_freeze": False,
            "forward_dynamic_parent_observation_required": True,
            "paper_orders_allowed": False,
        },
    }
    write_json(report_path, payload)
    markdown_path = output / "stage-d-development-report.md"
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return R10StageDResult(report_path=report_path, markdown_path=markdown_path, payload=payload)


def _event_theme_diagnostics(records: list[dict[str, Any]]) -> dict[str, Any]:
    event_seed_count = sum(len(row.get("event_seeds", [])) for row in records)
    states_by_theme: dict[str, list[str]] = {}
    selected_symbols: set[str] = set()
    for row in records:
        selected_symbols.update(map(str, row.get("selected_symbols", [])))
        for theme in row.get("themes", []):
            theme_id = str(theme["theme_id"])
            states_by_theme.setdefault(theme_id, []).append(str(theme["state"]))
    active_states = {"confirmed", "expansion", "mature"}
    confirmed_lengths = [
        sum(state in active_states for state in states)
        for states in states_by_theme.values()
        if any(state in active_states for state in states)
    ]
    return {
        "event_seed_count": event_seed_count,
        "formed_theme_count": len(states_by_theme),
        "confirmed_theme_count": len(confirmed_lengths),
        "median_confirmed_lifecycle_sessions": (
            float(np.median(confirmed_lengths)) if confirmed_lengths else 0.0
        ),
        "maximum_confirmed_lifecycle_sessions": max(confirmed_lengths, default=0),
        "selected_symbol_count": len(selected_symbols),
        "selected_symbols": sorted(selected_symbols),
    }


def _development_performance_gates(
    *,
    candidate_id: str,
    metrics: dict[str, Any],
    severe_metrics: dict[str, Any],
    qqq_metrics: dict[str, Any],
    tqqq_metrics: dict[str, Any],
    positive_lift_folds: int,
    dsr: dict[str, Any],
    pbo: dict[str, Any],
    d02_metrics: dict[str, Any],
    theme_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    required_cagr = max(0.25, 0.85 * float(tqqq_metrics["cagr"]))
    gates = [
        _gate("net_cagr", metrics["cagr"] >= required_cagr, required_cagr, metrics["cagr"]),
        _gate(
            "qqq_cagr_delta",
            metrics["cagr"] - qqq_metrics["cagr"] >= 0.08,
            0.08,
            metrics["cagr"] - qqq_metrics["cagr"],
        ),
        _gate("maximum_drawdown", metrics["max_drawdown"] >= -0.65, -0.65, metrics["max_drawdown"]),
        _gate(
            "annualized_sharpe_excess_BIL",
            metrics["annualized_sharpe_excess_BIL"] >= 0.80,
            0.80,
            metrics["annualized_sharpe_excess_BIL"],
        ),
        _gate("mar", metrics["mar"] is not None and metrics["mar"] >= 0.40, 0.40, metrics["mar"]),
        _gate(
            "tqqq_up_capture", metrics["tqqq_up_capture"] >= 0.80, 0.80, metrics["tqqq_up_capture"]
        ),
        _gate(
            "tqqq_down_capture",
            metrics["tqqq_down_capture"] <= 0.90,
            "<=0.90",
            metrics["tqqq_down_capture"],
        ),
        _gate("positive_qqq_lift_folds", positive_lift_folds >= 3, 3, positive_lift_folds),
        _gate("dsr_probability", dsr["probability"] >= 0.75, 0.75, dsr["probability"]),
        _gate("pbo_probability", pbo["probability"] <= 0.40, "<=0.40", pbo["probability"]),
        _gate(
            "severe_cost_total_return",
            severe_metrics["total_return"] > 0,
            ">0",
            severe_metrics["total_return"],
        ),
        _gate(
            "annualized_one_way_turnover",
            metrics["annualized_reported_one_way_turnover"] <= 30.0,
            "<=30.0",
            metrics["annualized_reported_one_way_turnover"],
        ),
    ]
    if candidate_id == "R10D01":
        gates.extend(
            [
                _gate(
                    "median_confirmed_lifecycle_sessions",
                    theme_diagnostics["median_confirmed_lifecycle_sessions"] >= 3.0,
                    3.0,
                    theme_diagnostics["median_confirmed_lifecycle_sessions"],
                ),
                _gate(
                    "d01_cagr_exceeds_d02",
                    metrics["cagr"] > d02_metrics["cagr"],
                    f">{d02_metrics['cagr']}",
                    metrics["cagr"],
                ),
            ]
        )
    return gates


def _stage_d_preflight(root: Path) -> dict[str, Any]:
    validation = validate_iteration_dossier(ITER_ID, root=root, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R10 dossier changed after lock: " + ", ".join(validation.blocked))
    lock_path = root / STAGE_D_LOCK_PATH
    lock = _load_json(lock_path)
    if lock.get("status") != STAGE_D_LOCK_STATUS:
        raise ValueError("R10 Stage D lock identity is invalid")
    if lock.get("effective_trial_count") != EFFECTIVE_TRIAL_COUNT:
        raise ValueError("R10 effective trial count changed")
    for group in (
        "preregistration_files",
        "specs",
        "implementation_files",
        "source_files",
        "price_files",
    ):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R10 Stage D lock group is missing: {group}")
        for row in rows:
            _verify_binding(root, row)
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r10_spec_pair(specs["R10D01"], specs["R10D02"])
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R10 semantic spec changed after lock: {candidate_id}")
    split = _split_contract(lock["price_files"], root)
    if split != lock.get("split"):
        raise ValueError("R10 data split changed after lock")
    return {
        "dossier_status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "lock_path": STAGE_D_LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "lock": lock,
    }


def _gate(name: str, passed: bool, threshold: Any, value: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "value": value}


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Event-Seeded Theme Stock R10 Stage D",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{str(payload['workflow_pass']).lower()}`",
        "- Research pass: `false` (current-survivor rejection diagnostic only)",
        "- LLM contribution pass: `false`",
        "- Paper-ready pass: `false`",
        "- Holdout access count: `0`",
        "",
        "| Candidate | CAGR | Sharpe excess BIL | Max drawdown | MAR | Turnover | Pass |",
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["cost_views"]["primary_20bps"]
        lines.append(
            f"| {candidate_id} | {metrics['cagr_pct']:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown_pct']:.2f}% | {metrics['mar']:.3f} | "
            f"{metrics['annualized_reported_one_way_turnover']:.2f}x | "
            f"{str(candidate['development_performance_pass']).lower()} |"
        )
    tqqq = payload["benchmarks"]["TQQQ_buy_hold"]["cost_views"]["primary_20bps"]
    qqq = payload["benchmarks"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"]
    lines.extend(
        [
            "",
            f"Matched TQQQ CAGR: `{tqqq['cagr_pct']:.2f}%`; QQQ CAGR: `{qqq['cagr_pct']:.2f}%`.",
            "",
            "CAGR is geometric. All metrics use the development window, next-open execution, "
            "20 bps per one-way target-weight turnover, and terminal liquidation. The fixed "
            "current-survivor panel can reject the method but cannot establish Alpha, promotion, "
            "or Paper readiness.",
            "",
        ]
    )
    return "\n".join(lines)


def report_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("R10 report must be a JSON object")
    return {
        "decision": payload["decision"],
        "workflow_pass": payload["workflow_pass"],
        "stage_e_training_authorized": payload["stage_e_training_authorized"],
        "candidate_metrics": {
            candidate_id: candidate["cost_views"]["primary_20bps"]
            for candidate_id, candidate in payload["candidates"].items()
        },
    }
