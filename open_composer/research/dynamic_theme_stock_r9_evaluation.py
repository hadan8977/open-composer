from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from open_composer.market_calendar import NEW_YORK
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.dynamic_theme_stock_r9 import (
    BENCHMARK_SYMBOLS,
    compute_r9_d01_targets,
    compute_r9_d02_targets,
    validate_r9_spec_pair,
)
from open_composer.research.etf_structural_r9 import (
    SimulationResult,
    simulate_target_portfolio,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_dynamic_theme_stock_r9"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
STAGE_D_LOCK_PATH = ITERATION_DIR / "lock-set/stage-d-lock.json"
STAGE_D_REPORT_PATH = ITERATION_DIR / "stage-d-development-report.json"
DIAGNOSTIC_MANIFEST_PATH = Path(
    "reports/research/iterations/mom_stock_intraday_codesign_q1/daily-panel-manifest.json"
)
RUNNER_PATH = Path("open_composer/research/dynamic_theme_stock_r9_evaluation.py")
TARGET_PATH = Path("open_composer/research/dynamic_theme_stock_r9.py")
TEST_PATHS = (
    Path("tests/test_dynamic_theme_stock_r9.py"),
    Path("tests/test_dynamic_theme_stock_r9_evaluation.py"),
)
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_dynamic_theme_stock_r9_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R9D01", "d01"),
        ("R9D02", "d02"),
        ("R9M01", "m01"),
        ("R9M02", "m02"),
        ("R9L01", "l01"),
        ("R9C01", "c01"),
        ("R9F01", "f01"),
        ("R9P01", "p01"),
    )
}
EXTENDED_BENCHMARK_MANIFESTS = {
    symbol: Path(f"data/cache/manifests/{symbol.lower()}_daily_longbridge_nasdaq_basic.json")
    for symbol in ("QQQ", "QLD", "TQQQ")
}
LOCKBOX_SESSION_COUNT = 252
EFFECTIVE_TRIAL_COUNT = 8022
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
STAGE_D_LOCK_STATUS = (
    "development_only_implementation_and_data_locked_before_first_r9_historical_target_calculation"
)


@dataclass(frozen=True)
class R9DiagnosticPanel:
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    membership: pd.DataFrame
    metadata: dict[str, Any]


@dataclass(frozen=True)
class R9StageDResult:
    report_path: Path
    markdown_path: Path
    payload: dict[str, Any]


def freeze_dynamic_theme_stock_r9_stage_d(root: Path) -> Path:
    base = root.resolve()
    lock_path = base / STAGE_D_LOCK_PATH
    if lock_path.exists():
        raise ValueError("R9 Stage D lock already exists")
    if (base / STAGE_D_REPORT_PATH).exists():
        raise ValueError("R9 Stage D result exists before its implementation lock")

    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R9 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r9_spec_pair(specs["R9D01"], specs["R9D02"])
    price_files, source_files = _build_price_bindings(base, specs["R9D01"])
    split = _split_contract(price_files, base)

    iteration_files = sorted(
        path
        for path in (base / ITERATION_DIR).iterdir()
        if path.is_file() and path.name != "decision-record.md"
    )
    preregistration_files = [
        *iteration_files,
        base / "reports/harness/source_cards/us_dynamic_theme_stock_r9.jsonl",
        base / "capabilities/registry.yaml",
        base / "open_composer/research/factor_library.py",
    ]
    implementation_files = [
        base / TARGET_PATH,
        base / RUNNER_PATH,
        *(base / path for path in TEST_PATHS),
        base / "open_composer/research/etf_structural_r9.py",
        base / "open_composer/models/strategy_spec.py",
        base / "open_composer/strategy_versions.py",
        base / "schemas/strategy_spec.schema.json",
    ]
    lock = {
        "schema_version": 1,
        "lock_contract": "dynamic_theme_stock_r9_stage_d_v1",
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


def run_dynamic_theme_stock_r9_stage_d(root: Path) -> R9StageDResult:
    base = root.resolve()
    report_path = base / STAGE_D_REPORT_PATH
    if report_path.exists():
        raise ValueError("R9 Stage D development diagnostic is one-shot")
    preflight = _stage_d_preflight(base)
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    d01_spec = specs["R9D01"]
    d02_spec = specs["R9D02"]
    panel = load_r9_stage_d_panel(base, preflight["lock"])

    d01_targets, d01_records = compute_r9_d01_targets(
        panel.close,
        panel.volume,
        panel.membership,
        d01_spec,
    )
    d02_targets, d02_records = compute_r9_d02_targets(
        panel.close,
        panel.volume,
        panel.membership,
        d01_spec,
        d02_spec,
        d01_result=(d01_targets, d01_records),
    )
    targets_by_id = {"R9D01": d01_targets, "R9D02": d02_targets}
    records_by_id = {"R9D01": d01_records, "R9D02": d02_records}
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
    dsr = {
        candidate_id: deflated_sharpe_probability(returns, EFFECTIVE_TRIAL_COUNT)
        for candidate_id, returns in primary_returns.items()
    }
    pbo = cscv_probability_backtest_overfitting(primary_returns, block_count=8)
    qqq_metrics = benchmarks["QQQ_buy_hold"]["cost_views"]["primary_20bps"]
    tqqq_metrics = benchmarks["TQQQ_buy_hold"]["cost_views"]["primary_20bps"]
    d02_metrics = candidate_results["R9D02"]["cost_views"]["primary_20bps"]
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
        )
        candidate["positive_qqq_lift_fold_count"] = positive_lift_folds
        candidate["deflated_sharpe"] = dsr[candidate_id]
        candidate["development_performance_gates"] = gates
        candidate["development_performance_pass"] = all(row["pass"] for row in gates)
        candidate["research_pass"] = False
        candidate["paper_ready_pass"] = False

    implementation_checks = {
        "prebacktest_dossier_pass": preflight["dossier_status"] == "ok",
        "exact_diagnostic_stock_count": panel.membership.shape[1] == 62,
        "development_only_numeric_materialization": panel.metadata["lockbox_values_loaded"]
        is False,
        "next_session_target_semantics": all(
            len(records) == len(targets_by_id[candidate_id])
            for candidate_id, records in records_by_id.items()
        ),
        "dynamic_theme_membership_observed": any(row["selected_symbols"] for row in d01_records),
        "target_weights_sum_to_one": all(
            np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)
            for targets in targets_by_id.values()
        ),
        "broker_writes_false": True,
    }
    workflow_pass = all(implementation_checks.values())
    methodology_blockers = [
        "historical_PIT_membership_missing",
        "inactive_and_delisted_securities_missing",
        "terminal_delisting_returns_missing",
        "historical_PIT_narrative_packets_missing",
    ]
    selected_development = sorted(
        candidate_id
        for candidate_id, candidate in candidate_results.items()
        if candidate["development_performance_pass"]
    )

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
                "stage": "D_development_only",
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
            "stage": "D_development_only",
            "folds": folds,
            "candidate_results": fold_results,
            "pbo": pbo,
        },
    )
    write_json(benchmark_path, {"schema_version": 1, "iter_id": ITER_ID, "benchmarks": benchmarks})
    implementation_contract = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "stage": "D_development_only",
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
        "report_type": "dynamic_theme_stock_r9_stage_d_development_diagnostic",
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": (
            "continue_to_fold_local_ml_development"
            if workflow_pass
            else "stop_r9_implementation_failure"
        ),
        "workflow_pass": workflow_pass,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "order_authority": False,
        "broker_writes": False,
        "development_performance_candidate_ids": selected_development,
        "methodology_blockers": methodology_blockers,
        "stage_e_training_authorized": workflow_pass,
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
            "R9M01_R9M02_fold_local_training_allowed": workflow_pass,
            "historical_R9L01_R9C01_R9P01_allowed": False,
            "lockbox_access_allowed_before_model_freeze": False,
            "tier0_forward_observation_allowed": False,
            "paper_orders_allowed": False,
        },
    }
    write_json(report_path, payload)
    markdown_path = output / "stage-d-development-report.md"
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return R9StageDResult(report_path=report_path, markdown_path=markdown_path, payload=payload)


def load_r9_stage_d_panel(root: Path, lock: dict[str, Any]) -> R9DiagnosticPanel:
    base = root.resolve()
    price_files = lock.get("price_files")
    if not isinstance(price_files, list) or not price_files:
        raise ValueError("R9 Stage D price bindings are missing")
    common = _common_sessions(price_files, base)
    split = _split_payload(common)
    if split != lock.get("split"):
        raise ValueError("R9 Stage D timestamp split changed after lock")
    development = common[: int(split["development_session_count"])]
    symbols = [str(row["symbol"]) for row in price_files]
    fields: dict[str, dict[str, pd.Series]] = {name: {} for name in ("open", "close", "volume")}
    for binding in price_files:
        symbol = str(binding["symbol"])
        frame = _read_development_price_frame(base, binding, development)
        for field in fields:
            fields[field][symbol] = frame[field]
    panels = {field: pd.DataFrame(values, index=development) for field, values in fields.items()}
    if any(list(panel.columns) != symbols for panel in panels.values()):
        raise ValueError("R9 Stage D panel symbol order changed")
    candidates = [symbol for symbol in symbols if symbol not in BENCHMARK_SYMBOLS]
    membership = pd.DataFrame(True, index=development, columns=candidates, dtype=bool)
    return R9DiagnosticPanel(
        open=panels["open"],
        close=panels["close"],
        volume=panels["volume"],
        membership=membership,
        metadata={
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "adjusted_requested": True,
            "stock_count": len(candidates),
            "benchmark_count": len(symbols) - len(candidates),
            "development_session_count": len(development),
            "first_development_session": development.min().date().isoformat(),
            "last_development_session": development.max().date().isoformat(),
            "membership_mode": "current_survivor_snapshot_all_true_diagnostic_only",
            "historical_PIT_membership": False,
            "lockbox_values_loaded": False,
            "fallback_used": False,
        },
    )


def development_folds(sessions: pd.DatetimeIndex) -> list[dict[str, Any]]:
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("R9 development sessions must be unique and increasing")
    minimum_train = 252
    purge = 10
    first_test_position = minimum_train + purge
    test_interval_count = len(sessions) - 1 - first_test_position
    if test_interval_count < 4 * 63:
        raise ValueError("R9 development data cannot support four 63-interval folds")
    base_count, remainder = divmod(test_interval_count, 4)
    counts = [base_count + int(index < remainder) for index in range(4)]
    rows = []
    cursor = first_test_position
    for index, count in enumerate(counts, start=1):
        end_position = cursor + count
        train_end_position = cursor - purge - 1
        rows.append(
            {
                "fold_id": f"F{index}",
                "train_start": sessions[0].date().isoformat(),
                "train_end": sessions[train_end_position].date().isoformat(),
                "purge_sessions": purge,
                "embargo_sessions": 10,
                "test_start": sessions[cursor].date().isoformat(),
                "test_end": sessions[end_position].date().isoformat(),
                "test_interval_count": count,
            }
        )
        cursor = end_position
    if cursor != len(sessions) - 1:
        raise AssertionError("R9 fold allocation did not consume the development window")
    return rows


def deflated_sharpe_probability(returns: pd.Series, trial_count: int) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if trial_count < 2 or len(values) < 3 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("R9 DSR requires finite returns, three sessions, and N>=2")
    standard_deviation = float(values.std(ddof=1))
    if standard_deviation <= 0:
        return {
            "trial_count": trial_count,
            "session_count": len(values),
            "probability": 0.0,
            "observed_annualized_sharpe": 0.0,
            "expected_max_annualized_sharpe_under_null": None,
        }
    observed_daily = float(values.mean() / standard_deviation)
    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max_standard = (1 - gamma) * normal.inv_cdf(1 - 1 / trial_count) + gamma * (
        normal.inv_cdf(1 - 1 / (trial_count * math.e))
    )
    expected_daily = expected_max_standard / math.sqrt(len(values) - 1)
    skew = float(values.skew())
    kurtosis = float(values.kurt()) + 3.0
    denominator = 1 - skew * observed_daily + ((kurtosis - 1) / 4.0) * observed_daily**2
    probability = 0.0
    if math.isfinite(denominator) and denominator > 0:
        statistic = (
            (observed_daily - expected_daily) * math.sqrt(len(values) - 1) / math.sqrt(denominator)
        )
        probability = normal.cdf(statistic)
    return {
        "trial_count": trial_count,
        "session_count": len(values),
        "probability": probability,
        "observed_annualized_sharpe": observed_daily * math.sqrt(252.0),
        "expected_max_annualized_sharpe_under_null": expected_daily * math.sqrt(252.0),
        "return_skew": skew,
        "return_kurtosis": kurtosis,
    }


def cscv_probability_backtest_overfitting(
    returns_by_candidate: dict[str, pd.Series],
    *,
    block_count: int,
) -> dict[str, Any]:
    candidate_ids = sorted(returns_by_candidate)
    if len(candidate_ids) < 2 or block_count != 8:
        raise ValueError("R9 PBO requires at least two candidates and exactly eight blocks")
    aligned = pd.concat(
        [returns_by_candidate[candidate_id].rename(candidate_id) for candidate_id in candidate_ids],
        axis=1,
        join="inner",
    ).dropna()
    if aligned.empty or not np.isfinite(aligned.to_numpy()).all():
        raise ValueError("R9 PBO return panel is empty or nonfinite")
    blocks = [pd.DatetimeIndex(index) for index in np.array_split(aligned.index, block_count)]
    if (
        any(len(block) == 0 for block in blocks)
        or max(map(len, blocks)) - min(map(len, blocks)) > 1
    ):
        raise ValueError("R9 PBO block construction failed")
    losses = []
    partitions = []
    for train_indices in combinations(range(block_count), block_count // 2):
        test_indices = tuple(index for index in range(block_count) if index not in train_indices)
        train_index = pd.DatetimeIndex(np.concatenate([blocks[index] for index in train_indices]))
        test_index = pd.DatetimeIndex(np.concatenate([blocks[index] for index in test_indices]))
        train_scores = {
            candidate_id: _series_sharpe(aligned.loc[train_index, candidate_id])
            for candidate_id in candidate_ids
        }
        best_score = max(train_scores.values())
        winners = sorted(
            candidate_id
            for candidate_id, score in train_scores.items()
            if math.isclose(score, best_score, rel_tol=0.0, abs_tol=1e-12)
        )
        test_scores = {
            candidate_id: _series_sharpe(aligned.loc[test_index, candidate_id])
            for candidate_id in candidate_ids
        }
        midranks = _descending_midranks(test_scores)
        midpoint = (len(candidate_ids) + 1) / 2.0
        winner_losses = [
            1.0 if midranks[winner] > midpoint else 0.0 if midranks[winner] < midpoint else 0.5
            for winner in winners
        ]
        loss = float(np.mean(winner_losses))
        losses.append(loss)
        partitions.append(
            {
                "in_sample_blocks": [f"B{index + 1:02d}" for index in train_indices],
                "out_of_sample_blocks": [f"B{index + 1:02d}" for index in test_indices],
                "in_sample_winners": winners,
                "out_of_sample_midranks": midranks,
                "overfit_loss": loss,
            }
        )
    return {
        "method": "eight_block_CSCV_deterministic_stage_D_provisional",
        "status": "provisional_until_R9M01_R9M02_are_frozen",
        "block_count": block_count,
        "partition_count": len(partitions),
        "probability": float(np.mean(losses)),
        "candidate_ids": candidate_ids,
        "partitions": partitions,
    }


def _stage_d_preflight(root: Path) -> dict[str, Any]:
    validation = validate_iteration_dossier(ITER_ID, root=root, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R9 dossier changed after lock: " + ", ".join(validation.blocked))
    lock_path = root / STAGE_D_LOCK_PATH
    lock = _load_json(lock_path)
    if lock.get("status") != STAGE_D_LOCK_STATUS:
        raise ValueError("R9 Stage D lock identity is invalid")
    if lock.get("effective_trial_count") != EFFECTIVE_TRIAL_COUNT:
        raise ValueError("R9 effective trial count changed")
    for group in (
        "preregistration_files",
        "specs",
        "implementation_files",
        "source_files",
        "price_files",
    ):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R9 Stage D lock group is missing: {group}")
        for row in rows:
            _verify_binding(root, row)
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R9 semantic spec changed after lock: {candidate_id}")
    split = _split_contract(lock["price_files"], root)
    if split != lock.get("split"):
        raise ValueError("R9 data split changed after lock")
    return {
        "dossier_status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "lock_path": STAGE_D_LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "lock": lock,
    }


def _build_price_bindings(
    root: Path,
    spec: StrategySpec,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = root / DIAGNOSTIC_MANIFEST_PATH
    manifest = _load_json(manifest_path)
    candidates = [symbol for symbol in spec.universe if symbol not in BENCHMARK_SYMBOLS]
    if manifest.get("selected_symbols") != candidates or manifest.get("selected_count") != 62:
        raise ValueError("R9 diagnostic manifest does not match the 62-stock preregistration")
    row_by_symbol = {
        str(row.get("symbol")): row for row in manifest.get("rows", []) if isinstance(row, dict)
    }
    price_files = []
    for symbol in candidates:
        row = row_by_symbol.get(symbol)
        if not row or row.get("quality_pass") is not True:
            raise ValueError(f"R9 diagnostic stock is unavailable: {symbol}")
        binding = {
            **_binding(root / str(row["cache_path"]), root),
            "symbol": symbol,
            "role": "current_survivor_stock_diagnostic",
        }
        if binding["sha256"] != row.get("content_sha256"):
            raise ValueError(f"R9 diagnostic stock hash mismatch: {symbol}")
        price_files.append(binding)

    benchmark_inputs = {
        str(row.get("symbol")): row
        for row in manifest.get("benchmark_inputs", [])
        if isinstance(row, dict)
    }
    for symbol in ("BIL", "SPY"):
        row = benchmark_inputs.get(symbol)
        if not row or row.get("runtime_input_eligible") is not True:
            raise ValueError(f"R9 diagnostic benchmark is unavailable: {symbol}")
        binding = {
            **_binding(root / str(row["cache_path"]), root),
            "symbol": symbol,
            "role": "benchmark_or_reserve",
        }
        if binding["sha256"] != row.get("cache_sha256"):
            raise ValueError(f"R9 diagnostic benchmark hash mismatch: {symbol}")
        price_files.append(binding)

    source_files = [_binding(manifest_path, root)]
    extended: dict[str, dict[str, Any]] = {}
    for symbol, relative_manifest in EXTENDED_BENCHMARK_MANIFESTS.items():
        source_binding = {**_binding(root / relative_manifest, root), "symbol": symbol}
        source_files.append(source_binding)
        source = _load_json(root / relative_manifest)
        if (
            source.get("symbol") != symbol
            or source.get("provider") != "longbridge"
            or source.get("feed") != "nasdaq_basic"
            or source.get("timeframe") != "daily"
            or source.get("request_params", {}).get("adjusted") is not True
        ):
            raise ValueError(f"R9 extended benchmark manifest identity mismatch: {symbol}")
        extended[symbol] = {
            **_binding(Path(str(source["cache_path"])), root),
            "symbol": symbol,
            "role": "benchmark_or_leveraged_core",
        }

    by_symbol = {str(row["symbol"]): row for row in price_files}
    by_symbol.update(extended)
    ordered = [by_symbol[symbol] for symbol in spec.universe]
    if len(ordered) != len(spec.universe):
        raise ValueError("R9 price bindings do not cover the StrategySpec panel")
    return ordered, source_files


def _split_contract(price_files: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    return _split_payload(_common_sessions(price_files, root))


def _common_sessions(price_files: list[dict[str, Any]], root: Path) -> pd.DatetimeIndex:
    common: pd.DatetimeIndex | None = None
    for binding in price_files:
        sessions = _timestamp_index(_read_bound_bytes(root, binding))
        common = sessions if common is None else common.intersection(sessions, sort=False)
    if common is None or common.has_duplicates or not common.is_monotonic_increasing:
        raise ValueError("R9 common diagnostic sessions are invalid")
    if len(common) <= LOCKBOX_SESSION_COUNT + 400:
        raise ValueError("R9 diagnostic panel is too short for development and lockbox")
    return common


def _split_payload(common: pd.DatetimeIndex) -> dict[str, Any]:
    development = common[:-LOCKBOX_SESSION_COUNT]
    lockbox = common[-LOCKBOX_SESSION_COUNT:]
    return {
        "split_contract": "last_252_common_sessions_numerically_sealed_v1",
        "full_common_session_count": len(common),
        "full_first_session": common.min().date().isoformat(),
        "full_last_session": common.max().date().isoformat(),
        "full_sessions_sha256": _session_hash(common),
        "development_session_count": len(development),
        "development_first_session": development.min().date().isoformat(),
        "development_last_session": development.max().date().isoformat(),
        "development_sessions_sha256": _session_hash(development),
        "lockbox_session_count": len(lockbox),
        "lockbox_first_session": lockbox.min().date().isoformat(),
        "lockbox_last_session": lockbox.max().date().isoformat(),
        "lockbox_sessions_sha256": _session_hash(lockbox),
        "lockbox_numeric_access_count": 0,
    }


def _read_development_price_frame(
    root: Path,
    binding: dict[str, Any],
    development: pd.DatetimeIndex,
) -> pd.DataFrame:
    payload = _read_bound_bytes(root, binding)
    sessions = _timestamp_index(payload)
    end = development.max()
    row_count = int(np.searchsorted(sessions.to_numpy(), end.to_datetime64(), side="right"))
    frame = pd.read_csv(
        io.BytesIO(payload),
        usecols=["timestamp", "open", "close", "volume"],
        nrows=row_count,
    )
    frame_sessions = _normalize_timestamps(frame["timestamp"])
    numeric = pd.DataFrame(
        {
            field: pd.to_numeric(frame[field], errors="raise").astype(float).to_numpy()
            for field in ("open", "close", "volume")
        },
        index=frame_sessions,
    ).reindex(development)
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError(f"R9 development values are missing or nonfinite: {binding['symbol']}")
    if (numeric[["open", "close"]] <= 0).any().any() or (numeric["volume"] < 0).any():
        raise ValueError(f"R9 development values violate price/volume bounds: {binding['symbol']}")
    return numeric


def _timestamp_index(payload: bytes) -> pd.DatetimeIndex:
    timestamps = pd.read_csv(io.BytesIO(payload), usecols=["timestamp"])["timestamp"]
    sessions = _normalize_timestamps(timestamps)
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("R9 source timestamps must be unique and increasing")
    return sessions


def _normalize_timestamps(values: pd.Series) -> pd.DatetimeIndex:
    timestamps = pd.to_datetime(values, utc=True, errors="raise")
    return pd.DatetimeIndex(timestamps.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize())


def _run_cost_views(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[dict[str, Any], dict[str, SimulationResult]]:
    metrics = {}
    simulations = {}
    for view_name, cost_bps in COST_VIEWS.items():
        simulation = simulate_target_portfolio(
            opens,
            targets,
            cost_bps=cost_bps,
            start=start,
            end=end,
            reserve_symbol="BIL",
        )
        simulations[view_name] = simulation
        metrics[view_name] = _performance_metrics(simulation, opens)
    return metrics, simulations


def _performance_metrics(simulation: SimulationResult, opens: pd.DataFrame) -> dict[str, Any]:
    daily = simulation.daily
    returns = pd.to_numeric(daily["net_return"], errors="raise").astype(float)
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    if returns.empty or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("R9 performance returns must be finite and non-empty")
    starts = pd.DatetimeIndex(pd.to_datetime(daily["interval_start"]))
    ends = pd.DatetimeIndex(pd.to_datetime(daily["interval_end"]))
    bil_returns = pd.Series(
        opens.loc[ends, "BIL"].to_numpy() / opens.loc[starts, "BIL"].to_numpy() - 1.0,
        index=returns.index,
    )
    tqqq_returns = pd.Series(
        opens.loc[ends, "TQQQ"].to_numpy() / opens.loc[starts, "TQQQ"].to_numpy() - 1.0,
        index=returns.index,
    )
    excess = returns - bil_returns
    excess_std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    sharpe = float(excess.mean() / excess_std * math.sqrt(252.0)) if excess_std > 0 else 0.0
    years = len(returns) / 252.0
    final_equity = float(equity.iloc[-1])
    cagr = final_equity ** (1.0 / years) - 1.0
    full_curve = pd.concat([pd.Series([1.0]), equity], ignore_index=True)
    max_drawdown = float((full_curve / full_curve.cummax() - 1.0).min())
    volatility = float(returns.std(ddof=1) * math.sqrt(252.0)) if len(returns) > 1 else 0.0
    up_mask = tqqq_returns > 0
    down_mask = tqqq_returns < 0
    up_capture = (
        float(returns[up_mask].mean() / tqqq_returns[up_mask].mean())
        if up_mask.any() and float(tqqq_returns[up_mask].mean()) != 0
        else 0.0
    )
    down_capture = (
        float(returns[down_mask].mean() / tqqq_returns[down_mask].mean())
        if down_mask.any() and float(tqqq_returns[down_mask].mean()) != 0
        else 0.0
    )
    return {
        "market_interval_count": len(returns),
        "total_return": final_equity - 1.0,
        "total_return_pct": (final_equity - 1.0) * 100.0,
        "cagr": cagr,
        "cagr_pct": cagr * 100.0,
        "annualized_volatility": volatility,
        "annualized_volatility_pct": volatility * 100.0,
        "annualized_sharpe_excess_BIL": sharpe,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100.0,
        "mar": cagr / abs(max_drawdown) if max_drawdown < 0 else None,
        "tqqq_up_capture": up_capture,
        "tqqq_down_capture": down_capture,
        "positive_interval_pct": float((returns > 0).mean() * 100.0),
        "total_reported_one_way_turnover": float(
            simulation.metrics["total_reported_one_way_turnover"]
        ),
        "annualized_reported_one_way_turnover": float(
            simulation.metrics["annualized_reported_one_way_turnover"]
        ),
        "nonzero_rebalance_count": int(simulation.metrics["nonzero_rebalance_count"]),
        "terminal_liquidation_included": True,
    }


def _daily_returns(simulation: SimulationResult) -> pd.Series:
    index = pd.DatetimeIndex(pd.to_datetime(simulation.daily["interval_end"]))
    return pd.Series(simulation.daily["net_return"].to_numpy(dtype=float), index=index)


def _simulate_static(
    opens: pd.DataFrame,
    weights: dict[str, float],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
) -> SimulationResult:
    row = {symbol: float(weights.get(symbol, 0.0)) for symbol in opens.columns}
    targets = pd.DataFrame([row], index=pd.DatetimeIndex([start]), columns=opens.columns)
    return simulate_target_portfolio(
        opens,
        targets,
        cost_bps=cost_bps,
        start=start,
        end=end,
        reserve_symbol="BIL",
    )


def _benchmark_family(
    opens: pd.DataFrame,
    selected_theme_targets: pd.DataFrame,
    candidates: tuple[str, ...],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    definitions = {
        "TQQQ_buy_hold": {"TQQQ": 1.0},
        "QQQ_buy_hold": {"QQQ": 1.0},
        "SPY_buy_hold": {"SPY": 1.0},
        "BIL_buy_hold": {"BIL": 1.0},
        "equal_weight_current_parent": {symbol: 1.0 / len(candidates) for symbol in candidates},
    }
    output = {}
    for benchmark_id, weights in definitions.items():
        output[benchmark_id] = {
            "weights": weights,
            "cost_views": {
                view_name: _performance_metrics(
                    _simulate_static(
                        opens,
                        weights,
                        start=start,
                        end=end,
                        cost_bps=cost_bps,
                    ),
                    opens,
                )
                for view_name, cost_bps in COST_VIEWS.items()
            },
        }
    output["equal_weight_selected_theme"] = {
        "construction": "equal weight among each R9D01 session's selected dynamic-theme stocks",
        "cost_views": _run_cost_views(
            opens,
            selected_theme_targets,
            start=start,
            end=end,
        )[0],
    }
    symbol_results = {
        symbol: {
            view_name: _performance_metrics(
                _simulate_static(
                    opens,
                    {symbol: 1.0},
                    start=start,
                    end=end,
                    cost_bps=cost_bps,
                ),
                opens,
            )
            for view_name, cost_bps in COST_VIEWS.items()
        }
        for symbol in candidates
    }
    best_symbol = max(
        candidates,
        key=lambda symbol: (
            symbol_results[symbol]["primary_20bps"]["cagr"],
            symbol,
        ),
    )
    output["ex_post_best_symbol"] = {
        "symbol": best_symbol,
        "selection_use": "report_only",
        "cost_views": symbol_results[best_symbol],
    }
    return output


def _equal_weight_selected_theme_targets(
    d01_targets: pd.DataFrame,
    candidates: tuple[str, ...],
) -> pd.DataFrame:
    rows = []
    for _, target in d01_targets.iterrows():
        selected = [symbol for symbol in candidates if float(target[symbol]) > 0]
        row = {str(symbol): 0.0 for symbol in d01_targets.columns}
        if selected:
            for symbol in selected:
                row[symbol] = 1.0 / len(selected)
        else:
            row["BIL"] = 1.0
        rows.append(row)
    return pd.DataFrame(rows, index=d01_targets.index, columns=d01_targets.columns)


def _evaluate_folds(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    folds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for fold in folds:
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        simulation = simulate_target_portfolio(
            opens,
            targets,
            cost_bps=20.0,
            start=start,
            end=end,
            reserve_symbol="BIL",
        )
        qqq = _simulate_static(opens, {"QQQ": 1.0}, start=start, end=end, cost_bps=20.0)
        metrics = _performance_metrics(simulation, opens)
        qqq_metrics = _performance_metrics(qqq, opens)
        rows.append(
            {
                **fold,
                "starts_in_cash": True,
                "liquidates_independently": True,
                "metrics": metrics,
                "qqq_benchmark_metrics": qqq_metrics,
                "qqq_cagr_lift": metrics["cagr"] - qqq_metrics["cagr"],
            }
        )
    return rows


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
    ]
    if candidate_id == "R9D01":
        gates.append(
            _gate(
                "d01_cagr_exceeds_d02",
                metrics["cagr"] > d02_metrics["cagr"],
                f">{d02_metrics['cagr']}",
                metrics["cagr"],
            )
        )
    return gates


def _series_sharpe(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return (
        float(values.mean() / standard_deviation * math.sqrt(252.0))
        if standard_deviation > 0
        else 0.0
    )


def _descending_midranks(scores: dict[str, float]) -> dict[str, float]:
    ordered = sorted(scores, key=lambda candidate_id: (-scores[candidate_id], candidate_id))
    ranks: dict[str, float] = {}
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and math.isclose(
            scores[ordered[end]], scores[ordered[cursor]], rel_tol=0.0, abs_tol=1e-12
        ):
            end += 1
        midrank = (cursor + 1 + end) / 2.0
        for candidate_id in ordered[cursor:end]:
            ranks[candidate_id] = midrank
        cursor = end
    return ranks


def _gate(name: str, passed: bool, threshold: Any, value: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "value": value}


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = _regular_file(root, path)
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _verify_binding(root: Path, binding: dict[str, Any]) -> Path:
    path = _regular_file(root, root / str(binding.get("path") or ""))
    if path.stat().st_size != binding.get("size_bytes") or _sha256(path) != binding.get("sha256"):
        raise ValueError(f"R9 locked file changed: {binding.get('path')}")
    return path


def _read_bound_bytes(root: Path, binding: dict[str, Any]) -> bytes:
    path = _verify_binding(root, binding)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != binding.get("sha256"):
        raise ValueError(f"R9 bound file changed while reading: {binding.get('path')}")
    return payload


def _regular_file(root: Path, path: Path) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R9 path leaves repository: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R9 path is not a regular file: {candidate}")
    return resolved


def _artifact_ref(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.resolve().relative_to(root).as_posix(), "sha256": _sha256(path)}


def _session_hash(sessions: pd.DatetimeIndex) -> str:
    return hashlib.sha256(
        "\n".join(session.date().isoformat() for session in sessions).encode()
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# R9 Dynamic Theme Stock Stage D",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{str(payload['workflow_pass']).lower()}`",
        "- Research pass: `false` (current-survivor diagnostic only)",
        "- Lockbox access count: `0`",
        (
            f"- Development window: `{payload['evaluation_window']['start']}` "
            f"to `{payload['evaluation_window']['end']}`"
        ),
        f"- Effective trial count for DSR: `{payload['effective_trial_count']}`",
        "",
        "| Candidate | CAGR | Sharpe excess BIL | Max drawdown | MAR | Performance gates |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["cost_views"]["primary_20bps"]
        lines.append(
            f"| {candidate_id} | {metrics['cagr_pct']:.3f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown_pct']:.3f}% | {metrics['mar']:.3f} | "
            f"{str(candidate['development_performance_pass']).lower()} |"
        )
    lines.extend(
        [
            "",
            (
                "These metrics use a fixed current-survivor diagnostic panel. They may "
                "reject the method but cannot establish deployable historical Alpha or "
                "paper readiness."
            ),
            "",
        ]
    )
    return "\n".join(lines)
