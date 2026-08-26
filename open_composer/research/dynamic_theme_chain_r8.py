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

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import (
    AlpacaSnapshotContract,
    verify_alpaca_contract_snapshot,
)
from open_composer.market_calendar import NEW_YORK
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.etf_structural_r9 import (
    SimulationResult,
    simulate_target_portfolio,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_dynamic_theme_chain_r8"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOCK_DIR = ITERATION_DIR / "lock-set"
SNAPSHOT_CONTRACT_PATH = ITERATION_DIR / "snapshot-contract.json"
SNAPSHOT_DIR = Path("data/research/alpaca_dynamic_theme_chain_r8")
SNAPSHOT_MANIFEST_PATH = SNAPSHOT_DIR / "snapshot-manifest.json"
RUNNER_PATH = Path("open_composer/research/dynamic_theme_chain_r8.py")
TEST_PATH = Path("tests/test_dynamic_theme_chain_r8.py")
SPEC_PATHS = {
    "R8D01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_d01.yaml"),
    "R8D02": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_d02.yaml"),
    "R8M01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_m01.yaml"),
    "R8M02": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_m02.yaml"),
    "R8L01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_l01.yaml"),
    "R8C01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_c01.yaml"),
    "R8F01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_f01.yaml"),
    "R8P01": Path("strategy_specs/drafts/us_dynamic_theme_chain_r8_p01.yaml"),
}
UNIVERSE = (
    "BIL",
    "BOTZ",
    "CIBR",
    "GLD",
    "GRID",
    "IEF",
    "IGV",
    "PAVE",
    "QLD",
    "QQQ",
    "ROBO",
    "SMH",
    "SOXL",
    "SOXX",
    "SPY",
    "TQQQ",
    "URA",
    "XLE",
    "XLI",
    "XLU",
)
D01_CANDIDATE_SYMBOLS = tuple(symbol for symbol in UNIVERSE if symbol not in {"BIL", "QQQ", "SPY"})
THEME_PROXY_SYMBOLS = ("BOTZ", "CIBR", "GRID", "IGV", "PAVE", "ROBO", "SMH", "SOXX", "URA")
LEVERAGED_SYMBOLS = ("QLD", "SOXL", "TQQQ")
REBALANCE_WEEKDAYS = frozenset({0, 2, 4})
EFFECTIVE_TRIAL_COUNT = 8014
PRIMARY_COST_BPS = 20.0


@dataclass(frozen=True)
class PanelData:
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


@dataclass(frozen=True)
class R8FreezeResult:
    preregistration_lock_path: Path
    runner_lock_path: Path


@dataclass(frozen=True)
class R8EvaluationResult:
    evaluation_path: Path
    evaluation_markdown_path: Path
    trial_ledger_path: Path
    target_ledger_path: Path
    payload: dict[str, Any]


def freeze_dynamic_theme_chain_r8(root: Path) -> R8FreezeResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    lock_dir = base / LOCK_DIR
    if lock_dir.exists():
        raise ValueError("R8 lock-set already exists")
    if (base / SNAPSHOT_DIR).exists():
        raise ValueError("R8 snapshot exists before implementation lock")
    if (output / "evaluation-report.json").exists():
        raise ValueError("R8 evaluation already exists")

    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R8 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    _validate_specs(specs)
    snapshot_contract_path = base / SNAPSHOT_CONTRACT_PATH
    snapshot_contract = _load_json(snapshot_contract_path)
    AlpacaSnapshotContract.model_validate(snapshot_contract)

    iteration_inputs = sorted(path for path in output.iterdir() if path.is_file())
    preregistration_extras = [
        base / "reports/research/control/dynamic-theme-alpha-objective-20260801.json",
        base / "reports/harness/source_cards/us_dynamic_theme_chain_r8.jsonl",
        base / "prompts/dynamic_theme_r8_factor_v1.txt",
        base / "capabilities/registry.yaml",
        base / "open_composer/research/factor_library.py",
    ]
    preregistration = {
        "schema_version": 1,
        "lock_contract": "dynamic_theme_chain_r8_preregistration_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "behavior_and_acquisition_contracts_locked_before_first_r8_price_read",
        "iteration_artifacts": [
            _binding(path, base) for path in [*iteration_inputs, *preregistration_extras]
        ],
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "snapshot_contract": _binding(snapshot_contract_path, base),
        "historical_price_read_at_lock": False,
        "model_training_at_lock": False,
        "broker_writes": False,
    }
    implementation_paths = [
        base / RUNNER_PATH,
        base / TEST_PATH,
        base / "open_composer/research/etf_structural_r9.py",
        base / "open_composer/adapters/data/alpaca_snapshot.py",
        base / "open_composer/market_calendar.py",
        base / "open_composer/models/strategy_spec.py",
        base / "open_composer/strategy_versions.py",
        base / "schemas/strategy_spec.schema.json",
        base / "schemas/alpaca_snapshot_contract.schema.json",
        base / "schemas/alpaca_snapshot_manifest.schema.json",
    ]
    runner_lock = {
        "schema_version": 1,
        "lock_contract": "dynamic_theme_chain_r8_runner_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "implementation_locked_before_first_r8_price_read",
        "files": [_binding(path, base) for path in implementation_paths],
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "broker_writes": False,
    }

    lock_dir.mkdir(parents=True, exist_ok=False)
    preregistration_lock_path = lock_dir / "preregistration-lock.json"
    runner_lock_path = lock_dir / "runner-lock.json"
    write_json(preregistration_lock_path, preregistration)
    write_json(runner_lock_path, runner_lock)
    return R8FreezeResult(preregistration_lock_path, runner_lock_path)


def _preflight(root: Path) -> dict[str, Any]:
    base = root.resolve()
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R8 dossier changed after lock: " + ", ".join(validation.blocked))
    preregistration_path = base / LOCK_DIR / "preregistration-lock.json"
    runner_lock_path = base / LOCK_DIR / "runner-lock.json"
    preregistration = _load_json(preregistration_path)
    runner_lock = _load_json(runner_lock_path)
    if preregistration.get("status") != (
        "behavior_and_acquisition_contracts_locked_before_first_r8_price_read"
    ):
        raise ValueError("R8 preregistration lock identity is invalid")
    if runner_lock.get("status") != "implementation_locked_before_first_r8_price_read":
        raise ValueError("R8 runner lock identity is invalid")
    if runner_lock.get("effective_trial_count") != EFFECTIVE_TRIAL_COUNT:
        raise ValueError("R8 effective trial count changed after lock")
    for group in ("iteration_artifacts", "specs"):
        rows = preregistration.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R8 preregistration lock group missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    _verify_binding(base, preregistration.get("snapshot_contract"))
    files = runner_lock.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("R8 runner lock files are missing")
    for row in files:
        _verify_binding(base, row)

    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    _validate_specs(specs)
    locked_specs = {
        str(row.get("candidate_id")): row
        for row in preregistration["specs"]
        if isinstance(row, dict)
    }
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R8 semantic spec changed after lock: {candidate_id}")

    manifest_path = base / SNAPSHOT_MANIFEST_PATH
    manifest = verify_alpaca_contract_snapshot(base, manifest_path)
    contract_binding = preregistration["snapshot_contract"]
    if manifest.get("contract_sha256") != contract_binding.get("sha256"):
        raise AlpacaDataError("R8 snapshot does not bind the locked snapshot contract")
    if manifest.get("request_count") != 80:
        raise AlpacaDataError("R8 snapshot must contain exactly 80 independent requests")
    return {
        "status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "preregistration_lock_path": _relpath(preregistration_path, base),
        "preregistration_lock_sha256": _sha256(preregistration_path),
        "runner_lock_path": _relpath(runner_lock_path, base),
        "runner_lock_sha256": _sha256(runner_lock_path),
        "snapshot_manifest_path": _relpath(manifest_path, base),
        "snapshot_manifest_sha256": _sha256(manifest_path),
    }


def load_r8_panel(root: Path, manifest_path: Path) -> PanelData:
    base = root.resolve()
    path = manifest_path if manifest_path.is_absolute() else base / manifest_path
    raw_manifest = _read_bound_file(base, path)
    manifest = json.loads(raw_manifest)
    verified = verify_alpaca_contract_snapshot(base, path)
    if _canonical_json_bytes(verified) != _canonical_json_bytes(manifest):
        raise AlpacaDataError("R8 snapshot manifest changed during verification")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 80:
        raise AlpacaDataError("R8 snapshot must contain 20 symbols by four adjustments")
    identities = {
        (str(item.get("symbol")), str(item.get("adjustment")))
        for item in items
        if isinstance(item, dict)
    }
    expected = {
        (symbol, adjustment)
        for symbol in UNIVERSE
        for adjustment in ("raw", "split", "dividend", "all")
    }
    if identities != expected:
        raise AlpacaDataError("R8 snapshot symbol and adjustment coverage is incomplete")

    fields: dict[str, dict[str, pd.Series]] = {name: {} for name in ("open", "close", "volume")}
    shared_sessions: pd.DatetimeIndex | None = None
    selected = sorted(
        (item for item in items if item.get("adjustment") == "all"),
        key=lambda item: str(item["symbol"]),
    )
    for item in selected:
        if (
            item.get("timeframe") != "daily"
            or item.get("feed") != "sip"
            or item.get("session_scope") != "regular"
            or item.get("quality", {}).get("status") != "complete"
        ):
            raise AlpacaDataError("R8 all-adjustment item identity mismatch")
        symbol = str(item["symbol"])
        csv_path = path.parent / str(item.get("output_path") or "")
        payload = _read_bound_file(base, csv_path)
        if hashlib.sha256(payload).hexdigest() != item.get("output_sha256"):
            raise AlpacaDataError(f"R8 normalized CSV hash mismatch: {symbol}")
        frame = pd.read_csv(io.BytesIO(payload))
        required = {"timestamp", "open", "close", "volume"}
        if not required.issubset(frame.columns):
            raise AlpacaDataError(f"R8 normalized CSV fields missing: {symbol}")
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        sessions = pd.DatetimeIndex(
            timestamps.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
        )
        if sessions.has_duplicates or not sessions.is_monotonic_increasing:
            raise AlpacaDataError(f"R8 sessions invalid: {symbol}")
        if shared_sessions is None:
            shared_sessions = sessions
        elif not sessions.equals(shared_sessions):
            raise AlpacaDataError(f"R8 all-adjustment session alignment failed: {symbol}")
        for field in fields:
            values = pd.to_numeric(frame[field], errors="raise").astype(float)
            fields[field][symbol] = pd.Series(values.to_numpy(), index=sessions)
    if shared_sessions is None:
        raise AlpacaDataError("R8 snapshot contains no all-adjustment sessions")
    panels = {
        field: pd.DataFrame(values, index=shared_sessions).loc[:, list(UNIVERSE)]
        for field, values in fields.items()
    }
    if shared_sessions[0] != pd.Timestamp("2018-01-02") or shared_sessions[-1] != pd.Timestamp(
        "2026-08-03"
    ):
        raise AlpacaDataError("R8 snapshot common session boundaries mismatch")
    if any(
        not np.isfinite(panel.to_numpy()).all()
        for panel in (panels["open"], panels["close"], panels["volume"])
    ):
        raise AlpacaDataError("R8 panel contains nonfinite values")
    if (panels["open"] <= 0).any().any() or (panels["close"] <= 0).any().any():
        raise AlpacaDataError("R8 panel contains nonpositive prices")
    if (panels["volume"] < 0).any().any():
        raise AlpacaDataError("R8 panel contains negative volume")
    return PanelData(open=panels["open"], close=panels["close"], volume=panels["volume"])


def run_dynamic_theme_chain_r8(root: Path) -> R8EvaluationResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    evaluation_path = output / "evaluation-report.json"
    if evaluation_path.exists():
        raise ValueError("R8 one-shot deterministic evaluation already exists")
    preflight = _preflight(base)
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    panel = load_r8_panel(base, base / SNAPSHOT_MANIFEST_PATH)
    d01_targets, d01_records = compute_d01_targets(panel.close, panel.volume, specs["R8D01"])
    d02_targets, d02_records = compute_d02_targets(panel.close, specs["R8D02"])
    targets_by_id = {"R8D01": d01_targets, "R8D02": d02_targets}
    records_by_id = {"R8D01": d01_records, "R8D02": d02_records}

    common_start = max(frame.index.min() for frame in targets_by_id.values())
    common_end = panel.open.index.max()
    windows = _evaluation_windows(panel.open.index, common_start, common_end)
    folds = _development_folds(panel.open.index, windows["development"])
    cost_views = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}

    candidate_payloads: dict[str, dict[str, Any]] = {}
    primary_development_returns: dict[str, pd.Series] = {}
    fold_payloads: dict[str, list[dict[str, Any]]] = {}
    for candidate_id, targets in targets_by_id.items():
        window_results = {}
        for window_name, boundaries in windows.items():
            cost_results, simulations = _run_cost_views(
                panel.open,
                targets,
                start=boundaries["start"],
                end=boundaries["end"],
                cost_views=cost_views,
            )
            window_results[window_name] = cost_results
            if window_name == "development":
                primary_development_returns[candidate_id] = _daily_returns(
                    simulations["primary_20bps"], include_terminal=True
                )
        candidate_folds = []
        for fold in folds:
            simulation = simulate_target_portfolio(
                panel.open,
                targets,
                cost_bps=PRIMARY_COST_BPS,
                start=pd.Timestamp(fold["test_start"]),
                end=pd.Timestamp(fold["test_end"]),
                reserve_symbol="BIL",
            )
            qqq = _simulate_static(
                panel.open,
                {"QQQ": 1.0},
                start=pd.Timestamp(fold["test_start"]),
                end=pd.Timestamp(fold["test_end"]),
                cost_bps=PRIMARY_COST_BPS,
            )
            metrics = _simulation_metric_views(simulation, panel.open)
            qqq_metrics = _simulation_metric_views(qqq, panel.open)
            candidate_folds.append(
                {
                    **fold,
                    "starts_in_cash": True,
                    "liquidates_independently": True,
                    "metrics": metrics,
                    "qqq_benchmark_metrics": qqq_metrics,
                    "qqq_cagr_lift": (
                        metrics["with_terminal"]["cagr"] - qqq_metrics["with_terminal"]["cagr"]
                    ),
                }
            )
        fold_payloads[candidate_id] = candidate_folds
        candidate_payloads[candidate_id] = {
            "strategy_name": specs[candidate_id].name,
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_hash": strategy_content_hash(specs[candidate_id]),
            "target_count": len(targets),
            "first_execution_session": targets.index.min().date().isoformat(),
            "last_execution_session": targets.index.max().date().isoformat(),
            "windows": window_results,
            "folds": candidate_folds,
            "execution_gap_summary": _execution_gap_summary(
                panel.open, panel.close, records_by_id[candidate_id]
            ),
        }

    benchmark_payload = {
        window_name: _benchmark_family(
            panel.open,
            start=boundaries["start"],
            end=boundaries["end"],
            cost_views=cost_views,
        )
        for window_name, boundaries in windows.items()
    }
    dsr = {
        candidate_id: deflated_sharpe_probability(returns, EFFECTIVE_TRIAL_COUNT)
        for candidate_id, returns in primary_development_returns.items()
    }
    pbo = cscv_probability_backtest_overfitting(primary_development_returns, block_count=8)

    for candidate_id, candidate in candidate_payloads.items():
        full_primary = candidate["windows"]["full"]["primary_20bps"]["with_terminal"]
        lockbox_primary = candidate["windows"]["lockbox"]["primary_20bps"]["with_terminal"]
        stress = candidate["windows"]["full"]["severe_40bps"]["with_terminal"]
        qqq_primary = benchmark_payload["full"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"][
            "with_terminal"
        ]
        tqqq_primary = benchmark_payload["full"]["TQQQ_buy_hold"]["cost_views"]["primary_20bps"][
            "with_terminal"
        ]
        positive_lift_folds = sum(
            float(row["qqq_cagr_lift"]) > 0 for row in fold_payloads[candidate_id]
        )
        gates = _research_gates(
            candidate_id=candidate_id,
            metrics=full_primary,
            lockbox_metrics=lockbox_primary,
            stress_metrics=stress,
            qqq_metrics=qqq_primary,
            tqqq_metrics=tqqq_primary,
            positive_lift_folds=positive_lift_folds,
            dsr=dsr[candidate_id],
            pbo=pbo,
            d02_metrics=candidate_payloads["R8D02"]["windows"]["full"]["primary_20bps"][
                "with_terminal"
            ],
        )
        reserve_gates = _tier0_reserve_gates(full_primary, qqq_primary)
        candidate["positive_qqq_lift_fold_count"] = positive_lift_folds
        candidate["deflated_sharpe"] = dsr[candidate_id]
        candidate["research_gates"] = gates
        candidate["research_pass"] = all(row["pass"] for row in gates)
        candidate["tier0_reserve_gates"] = reserve_gates
        candidate["tier0_reserve_pass"] = all(row["pass"] for row in reserve_gates)

    selected_research = sorted(
        candidate_id
        for candidate_id, payload in candidate_payloads.items()
        if payload["research_pass"]
    )
    selected_tier0 = sorted(
        candidate_id
        for candidate_id, payload in candidate_payloads.items()
        if payload["tier0_reserve_pass"]
    )
    implementation_contract = _implementation_contract(
        panel,
        targets_by_id,
        records_by_id,
        folds,
        preflight,
    )
    workflow_pass = all(implementation_contract["checks"].values())
    research_pass = workflow_pass and bool(selected_research)
    if research_pass:
        decision = "continue_to_stage_e_and_broker_free_tier0"
    elif workflow_pass and selected_tier0:
        decision = "continue_stage_e_with_tier0_reserve_only"
    elif workflow_pass:
        decision = "continue_to_stage_e_diagnostic_only"
    else:
        decision = "stop_r8_implementation_failure"

    target_ledger_path = output / "target-ledger.jsonl"
    trial_ledger_path = output / "trial-ledger.jsonl"
    fold_results_path = output / "fold-results.json"
    benchmark_results_path = output / "benchmark-results.json"
    implementation_path = output / "implementation-contract.json"
    _write_jsonl(target_ledger_path, [*d01_records, *d02_records])
    _write_jsonl(
        trial_ledger_path,
        [
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "spec_hash": candidate["spec_hash"],
                "snapshot_manifest_sha256": preflight["snapshot_manifest_sha256"],
                "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
                "research_pass": candidate["research_pass"],
                "tier0_reserve_pass": candidate["tier0_reserve_pass"],
                "windows": candidate["windows"],
                "folds": candidate["folds"],
            }
            for candidate_id, candidate in candidate_payloads.items()
        ],
    )
    write_json(
        fold_results_path,
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "folds": folds,
            "candidate_results": fold_payloads,
            "pbo": pbo,
        },
    )
    write_json(
        benchmark_results_path,
        {"schema_version": 1, "iter_id": ITER_ID, "windows": benchmark_payload},
    )
    write_json(implementation_path, implementation_contract)

    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "strategy_name": "us_dynamic_theme_chain_r8",
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "order_authority": False,
        "broker_writes": False,
        "selected_research_candidate_ids": selected_research,
        "selected_tier0_reserve_candidate_ids": selected_tier0,
        "stage_e_training_authorized": workflow_pass,
        "historical_llm_paths": "dependency_skipped",
        "preflight": preflight,
        "data": {
            "provider": "alpaca",
            "feed": "sip",
            "adjustment_used": "all",
            "independent_adjustments_verified": ["raw", "split", "dividend", "all"],
            "symbol_count": len(panel.open.columns),
            "session_count": len(panel.open),
            "first_session": panel.open.index.min().date().isoformat(),
            "last_session": panel.open.index.max().date().isoformat(),
            "fallback_used": False,
        },
        "evaluation_windows": windows,
        "cost_views_bps": cost_views,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "candidates": candidate_payloads,
        "benchmarks": benchmark_payload,
        "pbo": pbo,
        "implementation_contract": implementation_contract,
        "artifacts": {
            "target_ledger_path": _relpath(target_ledger_path, base),
            "target_ledger_sha256": _sha256(target_ledger_path),
            "trial_ledger_path": _relpath(trial_ledger_path, base),
            "trial_ledger_sha256": _sha256(trial_ledger_path),
            "fold_results_path": _relpath(fold_results_path, base),
            "fold_results_sha256": _sha256(fold_results_path),
            "benchmark_results_path": _relpath(benchmark_results_path, base),
            "benchmark_results_sha256": _sha256(benchmark_results_path),
            "implementation_contract_path": _relpath(implementation_path, base),
            "implementation_contract_sha256": _sha256(implementation_path),
        },
        "next_stage": {
            "M01_M02_training_allowed": workflow_pass,
            "historical_L01_C01_P01_allowed": False,
            "tier0_broker_free_observation_allowed": bool(selected_tier0),
            "paper_orders_allowed": False,
        },
    }
    write_json(evaluation_path, payload)
    evaluation_markdown_path = output / "evaluation-report.md"
    evaluation_markdown_path.write_text(_render_evaluation_markdown(payload), encoding="utf-8")
    return R8EvaluationResult(
        evaluation_path=evaluation_path,
        evaluation_markdown_path=evaluation_markdown_path,
        trial_ledger_path=trial_ledger_path,
        target_ledger_path=target_ledger_path,
        payload=payload,
    )


def _run_cost_views(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_views: dict[str, float],
) -> tuple[dict[str, Any], dict[str, SimulationResult]]:
    results = {}
    simulations = {}
    for view_name, cost_bps in cost_views.items():
        simulation = simulate_target_portfolio(
            opens,
            targets,
            cost_bps=cost_bps,
            start=start,
            end=end,
            reserve_symbol="BIL",
        )
        simulations[view_name] = simulation
        results[view_name] = _simulation_metric_views(simulation, opens)
    return results, simulations


def _simulation_metric_views(
    simulation: SimulationResult,
    opens: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "with_terminal": _rich_performance_metrics(
            simulation,
            opens,
            include_terminal=True,
        ),
        "without_terminal": _rich_performance_metrics(
            simulation,
            opens,
            include_terminal=False,
        ),
    }


def _rich_performance_metrics(
    simulation: SimulationResult,
    opens: pd.DataFrame,
    *,
    include_terminal: bool,
) -> dict[str, Any]:
    daily = simulation.daily.copy()
    terminal_events = [event for event in simulation.events if event["terminal"]]
    turnover = float(simulation.metrics["total_reported_one_way_turnover"])
    cumulative_cost_factor = float(simulation.metrics["cumulative_cost_factor"])
    if not include_terminal and terminal_events:
        terminal = terminal_events[-1]
        factor = float(terminal["cost_factor"])
        daily.loc[daily.index[-1], "cost_factor"] /= factor
        daily.loc[daily.index[-1], "net_factor"] /= factor
        daily.loc[daily.index[-1], "net_return"] = (
            float(daily.loc[daily.index[-1], "net_factor"]) - 1.0
        )
        daily.loc[daily.index[-1], "equity"] /= factor
        turnover -= float(terminal["reported_one_way_turnover"])
        cumulative_cost_factor /= factor
    returns = pd.to_numeric(daily["net_return"], errors="raise").astype(float)
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    if returns.empty or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("R8 performance returns must be finite and non-empty")
    interval_start = pd.to_datetime(daily["interval_start"])
    interval_end = pd.to_datetime(daily["interval_end"])
    bil_returns = pd.Series(
        [
            float(opens.at[end, "BIL"] / opens.at[start, "BIL"] - 1.0)
            for start, end in zip(interval_start, interval_end, strict=True)
        ],
        index=returns.index,
    )
    tqqq_returns = pd.Series(
        [
            float(opens.at[end, "TQQQ"] / opens.at[start, "TQQQ"] - 1.0)
            for start, end in zip(interval_start, interval_end, strict=True)
        ],
        index=returns.index,
    )
    excess = returns - bil_returns
    excess_std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    sharpe = float(excess.mean() / excess_std * math.sqrt(252.0)) if excess_std > 0 else 0.0
    years = len(returns) / 252.0
    final_equity = float(equity.iloc[-1])
    cagr = final_equity ** (1.0 / years) - 1.0
    full_curve = pd.concat([pd.Series([1.0]), equity], ignore_index=True)
    drawdown = full_curve / full_curve.cummax() - 1.0
    max_drawdown = float(drawdown.min())
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
        "total_reported_one_way_turnover": turnover,
        "annualized_reported_one_way_turnover": turnover / years,
        "maximum_drifted_weight": float(simulation.metrics["maximum_drifted_weight"]),
        "average_risk_asset_exposure": float(simulation.daily["risk_exposure"].mean()),
        "nonzero_rebalance_count": sum(not event["terminal"] for event in simulation.events),
        "terminal_liquidation_included": include_terminal,
        "terminal_liquidation_count": len(terminal_events) if include_terminal else 0,
        "cumulative_cost_factor": cumulative_cost_factor,
    }


def _daily_returns(simulation: SimulationResult, *, include_terminal: bool) -> pd.Series:
    daily = simulation.daily.copy()
    if not include_terminal:
        terminal_events = [event for event in simulation.events if event["terminal"]]
        if terminal_events:
            factor = float(terminal_events[-1]["cost_factor"])
            daily.loc[daily.index[-1], "net_factor"] /= factor
            daily.loc[daily.index[-1], "net_return"] = (
                float(daily.loc[daily.index[-1], "net_factor"]) - 1.0
            )
    index = pd.DatetimeIndex(pd.to_datetime(daily["interval_end"]))
    return pd.Series(daily["net_return"].to_numpy(dtype=float), index=index)


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
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_views: dict[str, float],
) -> dict[str, Any]:
    definitions = {
        "TQQQ_buy_hold": {"TQQQ": 1.0},
        "QQQ_buy_hold": {"QQQ": 1.0},
        "SPY_buy_hold": {"SPY": 1.0},
        "equal_weight_fixed_universe": {symbol: 1.0 / len(UNIVERSE) for symbol in UNIVERSE},
        "equal_weight_theme_proxies": {
            symbol: 1.0 / len(THEME_PROXY_SYMBOLS) for symbol in THEME_PROXY_SYMBOLS
        },
        "BIL_buy_hold": {"BIL": 1.0},
    }
    output = {}
    for benchmark_id, weights in definitions.items():
        output[benchmark_id] = {
            "weights": weights,
            "cost_views": {
                view_name: _simulation_metric_views(
                    _simulate_static(
                        opens,
                        weights,
                        start=start,
                        end=end,
                        cost_bps=cost_bps,
                    ),
                    opens,
                )
                for view_name, cost_bps in cost_views.items()
            },
        }
    symbol_results = {
        symbol: {
            view_name: _simulation_metric_views(
                _simulate_static(
                    opens,
                    {symbol: 1.0},
                    start=start,
                    end=end,
                    cost_bps=cost_bps,
                ),
                opens,
            )
            for view_name, cost_bps in cost_views.items()
        }
        for symbol in UNIVERSE
    }
    best_symbol = max(
        UNIVERSE,
        key=lambda symbol: (
            symbol_results[symbol]["primary_20bps"]["with_terminal"]["cagr"],
            symbol,
        ),
    )
    output["ex_post_best_symbol"] = {
        "symbol": best_symbol,
        "selection_use": "report_only",
        "cost_views": symbol_results[best_symbol],
    }
    return output


def _evaluation_windows(
    sessions: pd.DatetimeIndex,
    common_start: pd.Timestamp,
    common_end: pd.Timestamp,
) -> dict[str, dict[str, pd.Timestamp]]:
    selected = sessions[(sessions >= common_start) & (sessions <= common_end)]
    if len(selected) < 1261:
        raise ValueError("R8 common window is too short for development and lockbox contracts")
    lockbox_start = selected[-253]
    return {
        "development": {"start": selected[0], "end": lockbox_start},
        "lockbox": {"start": lockbox_start, "end": selected[-1]},
        "full": {"start": selected[0], "end": selected[-1]},
    }


def _development_folds(
    sessions: pd.DatetimeIndex,
    window: dict[str, pd.Timestamp],
) -> list[dict[str, Any]]:
    selected = sessions[(sessions >= window["start"]) & (sessions <= window["end"])]
    minimum_train = 756
    purge = 10
    first_test_position = minimum_train + purge
    test_interval_count = len(selected) - 1 - first_test_position
    if test_interval_count < 4 * 126:
        raise ValueError("R8 development window cannot support four minimum-size folds")
    base_count, remainder = divmod(test_interval_count, 4)
    counts = [base_count + int(index < remainder) for index in range(4)]
    folds = []
    cursor = first_test_position
    for index, count in enumerate(counts, start=1):
        end_position = cursor + count
        train_end_position = cursor - purge - 1
        folds.append(
            {
                "fold_id": f"F{index}",
                "train_start": selected[0].date().isoformat(),
                "train_end": selected[train_end_position].date().isoformat(),
                "purge_sessions": purge,
                "embargo_sessions": 10,
                "test_start": selected[cursor].date().isoformat(),
                "test_end": selected[end_position].date().isoformat(),
                "test_interval_count": count,
            }
        )
        cursor = end_position
    if cursor != len(selected) - 1:
        raise AssertionError("R8 fold allocation did not consume the development window")
    return folds


def deflated_sharpe_probability(returns: pd.Series, trial_count: int) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if trial_count < 2 or len(values) < 3 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("R8 DSR requires finite returns, three sessions, and N>=2")
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
    if not math.isfinite(denominator) or denominator <= 0:
        probability = 0.0
    else:
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
        raise ValueError("R8 PBO requires at least two candidates and exactly eight blocks")
    aligned = pd.concat(
        [returns_by_candidate[candidate_id].rename(candidate_id) for candidate_id in candidate_ids],
        axis=1,
        join="inner",
    ).dropna()
    if aligned.empty or not np.isfinite(aligned.to_numpy()).all():
        raise ValueError("R8 PBO return panel is empty or nonfinite")
    blocks = [pd.DatetimeIndex(index) for index in np.array_split(aligned.index, block_count)]
    if (
        any(len(block) == 0 for block in blocks)
        or max(map(len, blocks)) - min(map(len, blocks)) > 1
    ):
        raise ValueError("R8 PBO block construction failed")
    partitions = []
    losses = []
    for train_indices in combinations(range(block_count), block_count // 2):
        test_indices = tuple(index for index in range(block_count) if index not in train_indices)
        train = aligned.loc[
            pd.DatetimeIndex(np.concatenate([blocks[index] for index in train_indices]))
        ]
        test = aligned.loc[
            pd.DatetimeIndex(np.concatenate([blocks[index] for index in test_indices]))
        ]
        train_scores = {
            candidate_id: _series_sharpe(train[candidate_id]) for candidate_id in candidate_ids
        }
        best_score = max(train_scores.values())
        winners = sorted(
            candidate_id
            for candidate_id, score in train_scores.items()
            if math.isclose(score, best_score, rel_tol=0.0, abs_tol=1e-12)
        )
        test_scores = {
            candidate_id: _series_sharpe(test[candidate_id]) for candidate_id in candidate_ids
        }
        midranks = _descending_midranks(test_scores)
        winner_losses = []
        midpoint = (len(candidate_ids) + 1) / 2.0
        for winner in winners:
            rank = midranks[winner]
            winner_losses.append(1.0 if rank > midpoint else 0.0 if rank < midpoint else 0.5)
        partition_loss = float(np.mean(winner_losses))
        losses.append(partition_loss)
        partitions.append(
            {
                "in_sample_blocks": [f"B{index + 1:02d}" for index in train_indices],
                "out_of_sample_blocks": [f"B{index + 1:02d}" for index in test_indices],
                "in_sample_winners": winners,
                "out_of_sample_midranks": midranks,
                "overfit_loss": partition_loss,
            }
        )
    return {
        "method": "eight_block_CSCV_all_directional_four_block_combinations",
        "block_count": block_count,
        "partition_count": len(partitions),
        "probability": float(np.mean(losses)),
        "candidate_ids": candidate_ids,
        "partitions": partitions,
    }


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


def _series_sharpe(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return (
        float(values.mean() / standard_deviation * math.sqrt(252.0))
        if standard_deviation > 0
        else 0.0
    )


def _research_gates(
    *,
    candidate_id: str,
    metrics: dict[str, Any],
    lockbox_metrics: dict[str, Any],
    stress_metrics: dict[str, Any],
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
        _gate("maximum_drawdown", metrics["max_drawdown"] >= -0.55, -0.55, metrics["max_drawdown"]),
        _gate(
            "annualized_sharpe_excess_BIL",
            metrics["annualized_sharpe_excess_BIL"] >= 1.0,
            1.0,
            metrics["annualized_sharpe_excess_BIL"],
        ),
        _gate("mar", metrics["mar"] is not None and metrics["mar"] >= 0.5, 0.5, metrics["mar"]),
        _gate(
            "tqqq_up_capture", metrics["tqqq_up_capture"] >= 0.85, 0.85, metrics["tqqq_up_capture"]
        ),
        _gate(
            "tqqq_down_capture",
            metrics["tqqq_down_capture"] <= 0.75,
            "<=0.75",
            metrics["tqqq_down_capture"],
        ),
        _gate("positive_qqq_lift_folds", positive_lift_folds >= 3, 3, positive_lift_folds),
        _gate("dsr_probability", dsr["probability"] >= 0.75, 0.75, dsr["probability"]),
        _gate("pbo_probability", pbo["probability"] <= 0.40, "<=0.40", pbo["probability"]),
        _gate(
            "severe_cost_total_return",
            stress_metrics["total_return"] > 0,
            ">0",
            stress_metrics["total_return"],
        ),
        _gate(
            "lockbox_total_return",
            lockbox_metrics["total_return"] > 0,
            ">0",
            lockbox_metrics["total_return"],
        ),
    ]
    if candidate_id == "R8D01":
        gates.append(
            _gate(
                "d01_cagr_exceeds_d02",
                metrics["cagr"] > d02_metrics["cagr"],
                f">{d02_metrics['cagr']}",
                metrics["cagr"],
            )
        )
    return gates


def _tier0_reserve_gates(
    metrics: dict[str, Any],
    qqq_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _gate("reserve_net_cagr", metrics["cagr"] >= 0.20, 0.20, metrics["cagr"]),
        _gate(
            "reserve_qqq_cagr_delta",
            metrics["cagr"] - qqq_metrics["cagr"] >= 0.04,
            0.04,
            metrics["cagr"] - qqq_metrics["cagr"],
        ),
        _gate(
            "reserve_mar",
            metrics["mar"] is not None and metrics["mar"] >= 0.60,
            0.60,
            metrics["mar"],
        ),
        _gate(
            "reserve_primary_cost_positive",
            metrics["total_return"] > 0,
            ">0",
            metrics["total_return"],
        ),
    ]


def _execution_gap_summary(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for record in records:
        decision = pd.Timestamp(record["decision_session"])
        execution = pd.Timestamp(record["execution_session"])
        weights = record["weights"]
        invested = [symbol for symbol, weight in weights.items() if symbol != "BIL" and weight > 0]
        if not invested:
            continue
        gaps = {
            symbol: float(opens.at[execution, symbol] / closes.at[decision, symbol] - 1.0)
            for symbol in invested
        }
        rows.append(
            {
                "execution_session": execution.date().isoformat(),
                "weighted_gap": math.fsum(
                    float(weights[symbol]) * gaps[symbol] for symbol in invested
                ),
                "maximum_absolute_symbol_gap": max(abs(value) for value in gaps.values()),
                "leveraged_weight": math.fsum(
                    float(weights[symbol]) for symbol in LEVERAGED_SYMBOLS
                ),
            }
        )
    return {
        "observation_count": len(rows),
        "mean_weighted_gap": float(np.mean([row["weighted_gap"] for row in rows])) if rows else 0.0,
        "worst_weighted_gap": min((row["weighted_gap"] for row in rows), default=0.0),
        "maximum_absolute_symbol_gap": max(
            (row["maximum_absolute_symbol_gap"] for row in rows), default=0.0
        ),
        "mean_leveraged_weight": float(np.mean([row["leveraged_weight"] for row in rows]))
        if rows
        else 0.0,
    }


def _implementation_contract(
    panel: PanelData,
    targets: dict[str, pd.DataFrame],
    records: dict[str, list[dict[str, Any]]],
    folds: list[dict[str, Any]],
    preflight: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "preflight_ok": preflight.get("status") == "ok",
        "twenty_symbol_panel": list(panel.open.columns) == list(UNIVERSE),
        "panel_alignment": panel.open.index.equals(panel.close.index)
        and panel.open.index.equals(panel.volume.index),
        "finite_positive_prices": bool(
            np.isfinite(panel.open.to_numpy()).all()
            and np.isfinite(panel.close.to_numpy()).all()
            and (panel.open.to_numpy() > 0).all()
            and (panel.close.to_numpy() > 0).all()
        ),
        "target_sums": all(
            np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)
            for frame in targets.values()
        ),
        "target_nonnegative": all((frame >= -1e-12).all().all() for frame in targets.values()),
        "next_session_mwf": all(
            pd.Timestamp(row["execution_session"]).weekday() in REBALANCE_WEEKDAYS
            for rows in records.values()
            for row in rows
        ),
        "d01_symbol_cap": bool(
            (targets["R8D01"].drop(columns="BIL").max(axis=1) <= 0.60 + 1e-12).all()
        ),
        "d01_leveraged_cap": bool(
            (targets["R8D01"].loc[:, list(LEVERAGED_SYMBOLS)].sum(axis=1) <= 0.75 + 1e-12).all()
        ),
        "d02_strong_weights": all(
            row["state"] != "strong_risk_on"
            or (
                math.isclose(row["weights"]["TQQQ"], 0.65)
                and math.isclose(row["weights"]["QLD"], 0.35)
            )
            for row in records["R8D02"]
        ),
        "four_independent_folds": len(folds) == 4
        and all(int(fold["test_interval_count"]) >= 126 for fold in folds),
    }
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "valid": all(checks.values()),
        "checks": checks,
        "panel_session_count": len(panel.open),
        "panel_first_session": panel.open.index.min().date().isoformat(),
        "panel_last_session": panel.open.index.max().date().isoformat(),
    }


def _gate(name: str, passed: bool, threshold: Any, value: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "value": value}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _render_evaluation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Evaluation: {ITER_ID}",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        (
            "- Tier 0 reserve: `"
            f"{', '.join(payload['selected_tier0_reserve_candidate_ids']) or 'none'}`"
        ),
        "- Paper authority: `false`",
        "",
        "| Candidate | CAGR | Sharpe | MDD | MAR | QQQ lift | DSR | Tier 0 | Research |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    qqq = payload["benchmarks"]["full"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"][
        "with_terminal"
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["windows"]["full"]["primary_20bps"]["with_terminal"]
        lines.append(
            "| "
            f"{candidate_id} | {metrics['cagr_pct']:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown_pct']:.2f}% | "
            f"{metrics['mar'] if metrics['mar'] is not None else 0.0:.3f} | "
            f"{(metrics['cagr'] - qqq['cagr']) * 100:.2f}pp | "
            f"{candidate['deflated_sharpe']['probability']:.3f} | "
            f"{candidate['tier0_reserve_pass']} | {candidate['research_pass']} |"
        )
    lines.extend(
        [
            "",
            (
                "CAGR is geometric. All table values use the matched full window, "
                "20 bps per one-way notional, next-open execution, and terminal liquidation."
            ),
            (
                "Historical LLM paths remain dependency-skipped; no broker or Paper order "
                "was submitted."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def compute_d01_targets(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    _validate_target_inputs(closes, volumes)
    notes = spec.notes.model_dump(mode="json")
    contract = notes.get("graph_contract")
    if not isinstance(contract, dict):
        raise ValueError("R8D01 graph contract is missing")
    candidate_symbols = tuple(map(str, contract.get("candidate_symbols") or []))
    if candidate_symbols != D01_CANDIDATE_SYMBOLS:
        raise ValueError("R8D01 candidate symbol contract mismatch")
    residual_window = int(contract["residual_window_sessions"])
    graph_window = int(contract["graph_window_sessions"])
    threshold = float(contract["minimum_positive_edge_correlation"])
    minimum_breadth = float(contract["minimum_theme_breadth"])
    holding_sessions = int(contract["target_holding_sessions"])
    top_n = int(spec.portfolio.max_symbols_per_day)
    returns = closes.pct_change(fill_method=None)
    residuals = rolling_residual_returns(
        returns,
        candidate_symbols=candidate_symbols,
        market_symbol=str(contract["market_residual_symbol"]),
        technology_symbol=str(contract["technology_residual_symbol"]),
        window=residual_window,
    )
    momentum = {window: closes / closes.shift(window) - 1.0 for window in (5, 10, 20)}
    volume_ratio = volumes / volumes.rolling(10, min_periods=10).mean()
    volume_momentum = momentum[10] * volume_ratio
    volatility = returns.rolling(20, min_periods=20).std(ddof=0)

    target_rows: list[dict[str, float]] = []
    target_index: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    active: dict[str, dict[str, Any]] = {}
    for decision_position, execution_position in _scheduled_positions(closes.index):
        decision_session = closes.index[decision_position]
        execution_session = closes.index[execution_position]
        graph_slice = residuals.iloc[decision_position - graph_window + 1 : decision_position + 1]
        if len(graph_slice) != graph_window or not np.isfinite(graph_slice.to_numpy()).all():
            continue
        feature_values = {
            "momentum_5": momentum[5].loc[decision_session, list(candidate_symbols)],
            "momentum_10": momentum[10].loc[decision_session, list(candidate_symbols)],
            "momentum_20": momentum[20].loc[decision_session, list(candidate_symbols)],
            "volume_momentum_10": volume_momentum.loc[decision_session, list(candidate_symbols)],
            "inverse_volatility": 1.0 / volatility.loc[decision_session, list(candidate_symbols)],
        }
        if any(
            not np.isfinite(series.to_numpy(dtype=float)).all()
            for series in feature_values.values()
        ):
            continue
        ranks = {
            name: cross_sectional_percentile(series) for name, series in feature_values.items()
        }
        correlations = graph_slice.corr()
        components = connected_components(correlations, threshold=threshold)
        eligible_components: list[dict[str, Any]] = []
        symbol_scores: dict[str, float] = {}
        symbol_themes: dict[str, tuple[str, ...]] = {}
        for members in components:
            breadth = float(
                np.mean(
                    [
                        float(momentum[window].at[decision_session, symbol] > 0)
                        for symbol in members
                        for window in (5, 10, 20)
                    ]
                )
            )
            if breadth < minimum_breadth:
                continue
            member_scores = {}
            for symbol in members:
                score = (
                    0.25 * ranks["momentum_5"][symbol]
                    + 0.25 * ranks["momentum_10"][symbol]
                    + 0.20 * ranks["momentum_20"][symbol]
                    + 0.10 * ranks["volume_momentum_10"][symbol]
                    + 0.10 * breadth
                    + 0.10 * ranks["inverse_volatility"][symbol]
                )
                member_scores[symbol] = float(score)
                symbol_scores[symbol] = float(score)
                symbol_themes[symbol] = members
            eligible_components.append(
                {
                    "members": members,
                    "breadth": breadth,
                    "theme_score": float(np.mean(list(member_scores.values()))),
                    "member_scores": member_scores,
                }
            )
        eligible_components.sort(
            key=lambda row: (-float(row["theme_score"]), tuple(row["members"]))
        )
        ranked_symbols = sorted(
            symbol_scores,
            key=lambda symbol: (
                -float(
                    next(
                        row["theme_score"]
                        for row in eligible_components
                        if symbol in row["members"]
                    )
                ),
                -symbol_scores[symbol],
                symbol,
            ),
        )
        mandatory = sorted(
            symbol
            for symbol, state in active.items()
            if execution_position - int(state["entry_position"]) < holding_sessions
        )
        selected = list(mandatory)
        for symbol in ranked_symbols:
            if len(selected) >= top_n:
                break
            if symbol not in selected:
                selected.append(symbol)

        selected_state: dict[str, dict[str, Any]] = {}
        for symbol in selected:
            prior = active.get(symbol)
            selected_state[symbol] = {
                "entry_position": (
                    int(prior["entry_position"]) if prior is not None else execution_position
                ),
                "theme": (
                    symbol_themes[symbol]
                    if symbol in symbol_themes
                    else tuple(prior["theme"])
                    if prior is not None
                    else (symbol,)
                ),
            }
        active = selected_state
        weights = _d01_weights(
            columns=closes.columns,
            selected=selected,
            active=active,
            symbol_scores=symbol_scores,
            volatility=volatility.loc[decision_session],
            max_symbol_weight=float(spec.portfolio.max_symbol_weight),
            max_theme_weight=float(contract["maximum_theme_weight"]),
            max_leveraged_weight=float(contract["maximum_total_leveraged_etf_weight"]),
        )
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R8D01",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "eligible_components": eligible_components,
            "selected_symbols": selected,
            "selected_theme_map": {symbol: list(active[symbol]["theme"]) for symbol in selected},
            "mandatory_hold_symbols": mandatory,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        target_rows.append(weights)
        target_index.append(execution_session)
        records.append(record)
    if not target_rows:
        raise ValueError("R8D01 produced no complete targets")
    targets = pd.DataFrame(
        target_rows, index=pd.DatetimeIndex(target_index), columns=closes.columns
    )
    _validate_targets(targets, records, closes.index, candidate_id="R8D01")
    return targets, records


def compute_d02_targets(
    closes: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    _validate_target_inputs(closes, None)
    notes = spec.notes.model_dump(mode="json")
    contract = notes.get("route_contract")
    if not isinstance(contract, dict):
        raise ValueError("R8D02 route contract is missing")
    reference = str(contract["risk_on_reference"])
    trend = closes[reference].rolling(100, min_periods=100).mean()
    momentum = closes[reference] / closes[reference].shift(20) - 1.0
    rolling_peak = closes[reference].rolling(20, min_periods=20).max()
    drawdown = closes[reference] / rolling_peak - 1.0
    trigger = -float(contract["hard_drawdown_trigger_pct"]) / 100.0
    target_rows: list[dict[str, float]] = []
    target_index: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    for decision_position, execution_position in _scheduled_positions(closes.index):
        decision_session = closes.index[decision_position]
        execution_session = closes.index[execution_position]
        values = (
            trend.at[decision_session],
            momentum.at[decision_session],
            drawdown.at[decision_session],
        )
        if not all(pd.notna(value) and math.isfinite(float(value)) for value in values):
            continue
        trend_positive = bool(closes.at[decision_session, reference] > trend.at[decision_session])
        momentum_positive = bool(momentum.at[decision_session] > 0)
        drawdown_value = float(drawdown.at[decision_session])
        positive_votes = int(trend_positive) + int(momentum_positive)
        weights = {symbol: 0.0 for symbol in closes.columns}
        if drawdown_value <= trigger or positive_votes == 0:
            state = "stress"
            weights["BIL"] = 1.0
        elif positive_votes == 1:
            state = "moderate_risk_on"
            weights["QQQ"] = 1.0
        else:
            state = "strong_risk_on"
            weights["TQQQ"] = float(contract["tqqq_weight"])
            weights["QLD"] = float(contract["qld_weight"])
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R8D02",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "state": state,
            "trend_positive": trend_positive,
            "momentum_20": float(momentum.at[decision_session]),
            "drawdown_20": drawdown_value,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        target_rows.append(weights)
        target_index.append(execution_session)
        records.append(record)
    if not target_rows:
        raise ValueError("R8D02 produced no complete targets")
    targets = pd.DataFrame(
        target_rows, index=pd.DatetimeIndex(target_index), columns=closes.columns
    )
    _validate_targets(targets, records, closes.index, candidate_id="R8D02")
    return targets, records


def rolling_residual_returns(
    returns: pd.DataFrame,
    *,
    candidate_symbols: tuple[str, ...],
    market_symbol: str,
    technology_symbol: str,
    window: int,
) -> pd.DataFrame:
    required = {*candidate_symbols, market_symbol, technology_symbol}
    if not required.issubset(returns.columns):
        raise ValueError("residual return panel is missing required symbols")
    output = pd.DataFrame(np.nan, index=returns.index, columns=list(candidate_symbols), dtype=float)
    for position in range(window, len(returns)):
        sample = returns.iloc[position - window + 1 : position + 1]
        regressors = sample[[market_symbol, technology_symbol]].to_numpy(dtype=float)
        responses = sample[list(candidate_symbols)].to_numpy(dtype=float)
        if not np.isfinite(regressors).all() or not np.isfinite(responses).all():
            continue
        design = np.column_stack([np.ones(len(sample)), regressors])
        coefficients = np.linalg.lstsq(design, responses, rcond=None)[0]
        output.iloc[position] = responses[-1] - design[-1] @ coefficients
    return output


def connected_components(correlations: pd.DataFrame, *, threshold: float) -> list[tuple[str, ...]]:
    if list(correlations.index) != list(correlations.columns):
        raise ValueError("correlation matrix index and columns must match")
    symbols = sorted(map(str, correlations.columns))
    adjacency = {symbol: set() for symbol in symbols}
    for left_index, left in enumerate(symbols):
        for right in symbols[left_index + 1 :]:
            value = float(correlations.at[left, right])
            if math.isfinite(value) and value >= threshold:
                adjacency[left].add(right)
                adjacency[right].add(left)
    components: list[tuple[str, ...]] = []
    unseen = set(symbols)
    while unseen:
        seed = min(unseen)
        stack = [seed]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in members:
                continue
            members.add(current)
            stack.extend(sorted(adjacency[current] - members, reverse=True))
        unseen -= members
        if len(members) >= 2:
            components.append(tuple(sorted(members)))
    return sorted(components)


def cross_sectional_percentile(values: pd.Series) -> dict[str, float]:
    numeric = {str(symbol): float(value) for symbol, value in values.items()}
    if not numeric or not all(math.isfinite(value) for value in numeric.values()):
        raise ValueError("cross-sectional rank values must be finite and non-empty")
    ranked = sorted(numeric, key=lambda symbol: (-numeric[symbol], symbol))
    denominator = max(len(ranked) - 1, 1)
    return {symbol: 1.0 - index / denominator for index, symbol in enumerate(ranked)}


def _d01_weights(
    *,
    columns: pd.Index,
    selected: list[str],
    active: dict[str, dict[str, Any]],
    symbol_scores: dict[str, float],
    volatility: pd.Series,
    max_symbol_weight: float,
    max_theme_weight: float,
    max_leveraged_weight: float,
) -> dict[str, float]:
    weights = {str(symbol): 0.0 for symbol in columns}
    if not selected:
        weights["BIL"] = 1.0
        return weights
    raw = {}
    for symbol in selected:
        score = max(float(symbol_scores.get(symbol, 0.01)), 0.01)
        vol = float(volatility[symbol])
        if not math.isfinite(vol) or vol <= 0:
            raise ValueError(f"R8D01 volatility is invalid: {symbol}")
        raw[symbol] = score / vol
    total = math.fsum(raw.values())
    for symbol, value in raw.items():
        weights[symbol] = min(value / total, max_symbol_weight)
    theme_groups: dict[tuple[str, ...], list[str]] = {}
    for symbol in selected:
        theme_groups.setdefault(tuple(active[symbol]["theme"]), []).append(symbol)
    for members in theme_groups.values():
        theme_weight = math.fsum(weights[symbol] for symbol in members)
        if theme_weight > max_theme_weight:
            scale = max_theme_weight / theme_weight
            for symbol in members:
                weights[symbol] *= scale
    leveraged_weight = math.fsum(weights[symbol] for symbol in LEVERAGED_SYMBOLS)
    if leveraged_weight > max_leveraged_weight:
        scale = max_leveraged_weight / leveraged_weight
        for symbol in LEVERAGED_SYMBOLS:
            weights[symbol] *= scale
    allocated = math.fsum(weights.values())
    if allocated > 1.0 + 1e-12:
        raise ValueError("R8D01 target exceeds total capital")
    weights["BIL"] += 1.0 - allocated
    return weights


def _scheduled_positions(index: pd.DatetimeIndex) -> list[tuple[int, int]]:
    return [
        (position, position + 1)
        for position in range(len(index) - 1)
        if index[position + 1].weekday() in REBALANCE_WEEKDAYS
    ]


def _validate_target_inputs(closes: pd.DataFrame, volumes: pd.DataFrame | None) -> None:
    if list(closes.columns) != list(UNIVERSE):
        raise ValueError("R8 target panel columns must match the frozen universe")
    if closes.empty or not closes.index.is_monotonic_increasing or closes.index.has_duplicates:
        raise ValueError("R8 close sessions must be non-empty, unique, and increasing")
    if not np.isfinite(closes.to_numpy()).all() or (closes <= 0).any().any():
        raise ValueError("R8 closes must be finite and positive")
    if volumes is not None:
        if not volumes.index.equals(closes.index) or list(volumes.columns) != list(closes.columns):
            raise ValueError("R8 volume panel must exactly align with closes")
        if not np.isfinite(volumes.to_numpy()).all() or (volumes < 0).any().any():
            raise ValueError("R8 volume must be finite and nonnegative")


def _validate_targets(
    targets: pd.DataFrame,
    records: list[dict[str, Any]],
    sessions: pd.DatetimeIndex,
    *,
    candidate_id: str,
) -> None:
    if targets.index.has_duplicates or not targets.index.is_monotonic_increasing:
        raise ValueError(f"{candidate_id} target sessions must be unique and increasing")
    if not np.isfinite(targets.to_numpy()).all() or (targets < -1e-12).any().any():
        raise ValueError(f"{candidate_id} targets must be finite and nonnegative")
    if not np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0):
        raise ValueError(f"{candidate_id} target weights must sum to one")
    positions = {session: position for position, session in enumerate(sessions)}
    for record in records:
        decision = pd.Timestamp(record["decision_session"])
        execution = pd.Timestamp(record["execution_session"])
        if positions[execution] != positions[decision] + 1:
            raise ValueError(f"{candidate_id} target is not next-session executable")
        if execution.weekday() not in REBALANCE_WEEKDAYS:
            raise ValueError(f"{candidate_id} target violates the M/W/F schedule")


def _validate_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R8 spec set is incomplete")
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        if notes.get("candidate_id") != candidate_id:
            raise ValueError(f"R8 candidate identity mismatch: {candidate_id}")
        if (
            spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
        ):
            raise ValueError(f"R8 broker-free lifecycle contract mismatch: {candidate_id}")
        if (
            spec.portfolio.cross_sectional_execution_profile != "dynamic_theme_mwf_bil_reserve"
            or spec.portfolio.rebalance_schedule != "monday_wednesday_friday"
            or spec.portfolio.reserve_symbol != "BIL"
        ):
            raise ValueError(f"R8 portfolio execution contract mismatch: {candidate_id}")
    d01 = specs["R8D01"].notes.model_dump(mode="json")["graph_contract"]
    if (
        tuple(d01["candidate_symbols"]) != D01_CANDIDATE_SYMBOLS
        or d01["edge_rule"] != "correlation_greater_than_or_equal_to_threshold"
        or float(d01["minimum_positive_edge_correlation"]) != 0.35
    ):
        raise ValueError("R8D01 graph identity mismatch")
    d02 = specs["R8D02"].notes.model_dump(mode="json")["route_contract"]
    if (
        float(d02["tqqq_weight"]) != 0.65
        or float(d02["qld_weight"]) != 0.35
        or float(d02["maximum_total_leveraged_etf_weight"]) != 1.0
    ):
        raise ValueError("R8D02 aggressive beta contract mismatch")


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = _regular_repo_file(root, path)
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _verify_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("R8 file binding is missing")
    path = _regular_repo_file(root, root / str(binding.get("path") or ""))
    if path.stat().st_size != binding.get("size_bytes") or _sha256(path) != binding.get("sha256"):
        raise ValueError(f"R8 locked file changed: {binding.get('path')}")
    return path


def _regular_repo_file(root: Path, path: Path) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R8 path leaves repository: {candidate}") from exc
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"R8 path contains a symlink: {candidate}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R8 path resolves outside repository: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R8 path is not a regular file: {candidate}")
    return resolved


def _read_bound_file(root: Path, path: Path) -> bytes:
    resolved = _regular_repo_file(root, path)
    before = resolved.stat()
    payload = resolved.read_bytes()
    after = resolved.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"R8 file changed while reading: {resolved}")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
