from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, time
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.config import ensure_dir
from open_composer.market_calendar import NEW_YORK
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_etf_structural_family_r9"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SPEC_PATHS = (
    Path("strategy_specs/drafts/us_etf_structural_momentum_r9_d01.yaml"),
    Path("strategy_specs/drafts/us_etf_structural_momentum_r9_d02.yaml"),
    Path("strategy_specs/drafts/us_etf_structural_momentum_r9_d03.yaml"),
    Path("strategy_specs/drafts/us_etf_structural_momentum_r9.yaml"),
)
PROMOTION_CANDIDATE_ID = "R9D04"
TRIAL_COUNT = 8006


@dataclass(frozen=True)
class SimulationResult:
    daily: pd.DataFrame
    events: list[dict[str, Any]]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class R9EvaluationResult:
    evaluation_path: Path
    evaluation_markdown_path: Path
    trial_ledger_path: Path
    target_ledger_path: Path
    payload: dict[str, Any]


def run_etf_structural_r9(root: Path) -> R9EvaluationResult:
    output = root / ITERATION_DIR
    preflight = _preflight(root)
    specs = [load_strategy_spec(root / path) for path in SPEC_PATHS]
    daily_manifest_path = root / preflight["daily_manifest_path"]
    opens, closes, daily_manifest = _load_daily_panel(daily_manifest_path)

    targets_by_id: dict[str, pd.DataFrame] = {}
    target_records: list[dict[str, Any]] = []
    target_checks = []
    for spec in specs:
        candidate_id = _candidate_id(spec)
        targets, records = compute_monthly_targets(closes, spec)
        checks = _target_contract_checks(opens, targets, records, spec)
        if not all(check["pass"] for check in checks):
            failed = [check["name"] for check in checks if not check["pass"]]
            raise ValueError(f"{candidate_id} target contract failed: {', '.join(failed)}")
        targets_by_id[candidate_id] = targets
        target_records.extend(records)
        target_checks.extend(checks)

    first_targets = [frame.index.min() for frame in targets_by_id.values() if not frame.empty]
    if len(first_targets) != len(targets_by_id):
        raise ValueError("every R9 candidate must produce at least one complete target")
    common_start = max(first_targets)
    common_end = opens.index.max()
    if common_start >= common_end:
        raise ValueError("R9 evaluation window is empty")

    holdout = _load_json(output / "holdout-contract.json")
    folds = holdout.get("outer_folds")
    if not isinstance(folds, list) or len(folds) != 4:
        raise ValueError("R9 requires exactly four frozen outer folds")

    cost_views = {"gross_0bps": 0.0, "primary_10bps": 10.0, "stress_20bps": 20.0}
    report_only_cost_views = {"severe_report_only_35bps": 35.0}
    candidates: dict[str, dict[str, Any]] = {}
    fold_return_series: dict[str, list[pd.Series]] = {}
    ledger_rows: list[dict[str, Any]] = []
    fold_payload: dict[str, Any] = {}
    for spec in specs:
        candidate_id = _candidate_id(spec)
        targets = targets_by_id[candidate_id]
        cost_results: dict[str, dict[str, Any]] = {}
        primary_simulation: SimulationResult | None = None
        for view_name, bps in {**cost_views, **report_only_cost_views}.items():
            simulation = simulate_target_portfolio(
                opens,
                targets,
                cost_bps=bps,
                start=common_start,
                end=common_end,
                reserve_symbol="BIL",
            )
            cost_results[view_name] = simulation.metrics
            if view_name == "primary_10bps":
                primary_simulation = simulation
        if primary_simulation is None:
            raise AssertionError("primary R9 simulation missing")

        candidate_folds = []
        fold_return_series[candidate_id] = []
        for fold in folds:
            fold_id = str(fold["id"])
            simulation = simulate_target_portfolio(
                opens,
                targets,
                cost_bps=10.0,
                start=pd.Timestamp(str(fold["start"])),
                end=pd.Timestamp(str(fold["end"])),
                reserve_symbol="BIL",
            )
            candidate_folds.append(
                {
                    "fold_id": fold_id,
                    "start": str(fold["start"]),
                    "end": str(fold["end"]),
                    "starts_in_cash": True,
                    "liquidates_independently": True,
                    "metrics": simulation.metrics,
                }
            )
            fold_return_series[candidate_id].append(simulation.daily["net_return"])
        fold_payload[candidate_id] = candidate_folds
        candidates[candidate_id] = {
            "strategy_name": spec.name,
            "spec_path": _relpath(root / SPEC_PATHS[specs.index(spec)], root),
            "spec_hash": strategy_content_hash(spec),
            "promotion_eligible": candidate_id == PROMOTION_CANDIDATE_ID,
            "cost_views": cost_results,
            "folds": candidate_folds,
            "target_count": len(targets),
            "first_execution_session": targets.index.min().date().isoformat(),
            "last_execution_session": targets.index.max().date().isoformat(),
            "primary_event_count": len(primary_simulation.events),
        }
        ledger_rows.append(
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "strategy_name": spec.name,
                "spec_hash": strategy_content_hash(spec),
                "promotion_eligible": candidate_id == PROMOTION_CANDIDATE_ID,
                "data_manifest_sha256": preflight["daily_manifest_sha256"],
                "candidate_manifest_sha256": preflight["candidate_manifest_sha256"],
                "metrics": cost_results,
                "fold_metrics": candidate_folds,
            }
        )

    benchmark_results = _benchmark_family(opens, common_start, common_end)
    promotion_primary = candidates[PROMOTION_CANDIDATE_ID]["cost_views"]["primary_10bps"]
    promotion_stress = candidates[PROMOTION_CANDIDATE_ID]["cost_views"]["stress_20bps"]
    promotion_daily = simulate_target_portfolio(
        opens,
        targets_by_id[PROMOTION_CANDIDATE_ID],
        cost_bps=10.0,
        start=common_start,
        end=common_end,
        reserve_symbol="BIL",
    ).daily
    dsr = _deflated_sharpe(promotion_daily["net_return"], TRIAL_COUNT)
    pbo = _probability_backtest_overfitting(fold_return_series)
    intraday_shadow = _intraday_execution_shadow(
        root,
        preflight,
        targets_by_id[PROMOTION_CANDIDATE_ID],
    )

    implementation_contract = {
        "valid": all(check["pass"] for check in target_checks),
        "checks": target_checks,
        "daily_panel_symbol_count": len(opens.columns),
        "daily_panel_session_count": len(opens),
        "daily_panel_first_session": opens.index.min().date().isoformat(),
        "daily_panel_last_session": opens.index.max().date().isoformat(),
        "all_prices_finite_positive": bool(
            np.isfinite(opens.to_numpy()).all()
            and np.isfinite(closes.to_numpy()).all()
            and (opens.to_numpy() > 0).all()
            and (closes.to_numpy() > 0).all()
        ),
        "folds_start_in_cash_and_liquidate_independently": all(
            row["starts_in_cash"]
            and row["liquidates_independently"]
            and row["metrics"]["terminal_liquidation_count"] in {0, 1}
            for rows in fold_payload.values()
            for row in rows
        ),
    }
    if not all(
        [
            implementation_contract["valid"],
            implementation_contract["all_prices_finite_positive"],
            implementation_contract["folds_start_in_cash_and_liquidate_independently"],
        ]
    ):
        raise ValueError("R9 implementation contract failed")

    benchmark_gate_ids = [
        "SPY_same_symbol_buy_and_hold",
        "equal_weight_full_universe",
        "equal_weight_sector_etfs",
        "BIL_cash_proxy",
        "uninvested_cash",
    ]
    benchmark_sharpe = max(
        float(benchmark_results[benchmark_id]["annualized_sharpe"])
        for benchmark_id in benchmark_gate_ids
    )
    positive_folds = sum(
        float(row["metrics"]["total_return_pct"]) > 0
        for row in fold_payload[PROMOTION_CANDIDATE_ID]
    )
    gate_checks = [
        _gate("implementation_contract_valid", implementation_contract["valid"], True),
        _gate(
            "primary_net_return_positive",
            promotion_primary["total_return_pct"] > 0,
            ">0",
            promotion_primary["total_return_pct"],
        ),
        _gate(
            "stress_net_return_positive",
            promotion_stress["total_return_pct"] > 0,
            ">0",
            promotion_stress["total_return_pct"],
        ),
        _gate("positive_independent_folds", positive_folds >= 3, 3, positive_folds),
        _gate(
            "maximum_drawdown_floor",
            promotion_primary["max_drawdown_pct"] >= -20.0,
            -20.0,
            promotion_primary["max_drawdown_pct"],
        ),
        _gate(
            "benchmark_sharpe_delta",
            promotion_primary["annualized_sharpe"] - benchmark_sharpe >= 0.0,
            0.0,
            promotion_primary["annualized_sharpe"] - benchmark_sharpe,
        ),
        _gate("cumulative_trial_count", TRIAL_COUNT >= 8006, 8006, TRIAL_COUNT),
        _gate(
            "cumulative_dsr_probability",
            dsr["probability"] >= 0.95,
            0.95,
            dsr["probability"],
        ),
        _gate("pbo", pbo["probability"] <= 0.20, "<=0.20", pbo["probability"]),
        _gate(
            "annualized_turnover",
            promotion_primary["annualized_reported_one_way_turnover"] <= 3.0,
            "<=3.0",
            promotion_primary["annualized_reported_one_way_turnover"],
        ),
        _gate(
            "intraday_shadow_selection_prohibited",
            intraday_shadow["selection_prohibited"]
            and intraday_shadow["same_target_hash"]
            and intraday_shadow["holding_changes_forbidden"],
            True,
        ),
    ]
    research_pass = all(check["pass"] for check in gate_checks)
    decision = "continue_to_broker_free_forward_observation" if research_pass else "stop_r9"

    ensure_dir(output)
    target_ledger_path = output / "target-ledger.jsonl"
    trial_ledger_path = output / "trial-ledger.jsonl"
    fold_path = output / "fold-results.json"
    benchmark_path = output / "benchmark-results.json"
    implementation_path = output / "implementation-contract.json"
    intraday_path = output / "intraday-execution-shadow.json"
    _write_jsonl(target_ledger_path, target_records)
    _write_jsonl(trial_ledger_path, ledger_rows)
    write_json(fold_path, {"schema_version": 1, "iter_id": ITER_ID, "folds": fold_payload})
    write_json(
        benchmark_path,
        {"schema_version": 1, "iter_id": ITER_ID, "benchmarks": benchmark_results},
    )
    write_json(implementation_path, implementation_contract)
    write_json(intraday_path, intraday_shadow)

    evaluation_path = output / "evaluation-report.json"
    evaluation_markdown_path = output / "evaluation-report.md"
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "strategy_name": "us_etf_structural_momentum_r9",
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "order_authority": False,
        "selected_candidate_ids": [PROMOTION_CANDIDATE_ID] if research_pass else [],
        "historical_evidence_status": "exposed_robustness_not_independent_lockbox",
        "evaluation_window": {
            "start": common_start.date().isoformat(),
            "end": common_end.date().isoformat(),
        },
        "preflight": preflight,
        "data": {
            "provider": daily_manifest["provider"],
            "feed": "sip",
            "adjustment": "all",
            "symbol_count": len(opens.columns),
            "session_count": len(opens),
            "first_session": opens.index.min().date().isoformat(),
            "last_session": opens.index.max().date().isoformat(),
            "fallback_used": False,
        },
        "candidates": candidates,
        "benchmarks": benchmark_results,
        "benchmark_gate_sharpe": benchmark_sharpe,
        "deflated_sharpe": dsr,
        "pbo": pbo,
        "intraday_execution_shadow": intraday_shadow,
        "implementation_contract": implementation_contract,
        "gate_checks": gate_checks,
        "artifacts": {
            "trial_ledger_path": _relpath(trial_ledger_path, root),
            "trial_ledger_sha256": _sha256_file(trial_ledger_path),
            "target_ledger_path": _relpath(target_ledger_path, root),
            "target_ledger_sha256": _sha256_file(target_ledger_path),
            "fold_results_path": _relpath(fold_path, root),
            "fold_results_sha256": _sha256_file(fold_path),
            "benchmark_results_path": _relpath(benchmark_path, root),
            "benchmark_results_sha256": _sha256_file(benchmark_path),
            "implementation_contract_path": _relpath(implementation_path, root),
            "implementation_contract_sha256": _sha256_file(implementation_path),
            "intraday_shadow_path": _relpath(intraday_path, root),
            "intraday_shadow_sha256": _sha256_file(intraday_path),
        },
        "forward_requirements": {
            "earliest_observation_session": "2026-07-20",
            "minimum_bound_sessions": 20,
            "minimum_matched_tca_observations": 30,
            "strategy_change_resets_observation_count": True,
            "explicit_user_confirmation_required_before_order_authorization": True,
        },
    }
    write_json(evaluation_path, payload)
    evaluation_markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    _update_search_space_outputs(root, trial_ledger_path, evaluation_path)
    return R9EvaluationResult(
        evaluation_path=evaluation_path,
        evaluation_markdown_path=evaluation_markdown_path,
        trial_ledger_path=trial_ledger_path,
        target_ledger_path=target_ledger_path,
        payload=payload,
    )


def compute_monthly_targets(
    closes: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    config = spec.portfolio.etf_structural
    if config is None:
        raise ValueError("R9 target generation requires portfolio.etf_structural")
    values = closes.astype(float)
    if values.empty or not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        raise ValueError("R9 closes must be finite and positive")
    if not values.index.is_monotonic_increasing or values.index.has_duplicates:
        raise ValueError("R9 close sessions must be unique and increasing")

    lookbacks = {
        config.core_trend.fast_sma_sessions,
        config.core_trend.slow_sma_sessions,
        config.core_trend.momentum_sessions,
        config.diversifier_trend.fast_sma_sessions,
        config.diversifier_trend.slow_sma_sessions,
        config.diversifier_trend.momentum_sessions,
        config.sector_relative.fast_momentum_sessions,
        config.sector_relative.slow_momentum_sessions,
        config.sector_relative.trend_sma_sessions,
    }
    if config.risk_overlay is not None:
        lookbacks.add(config.risk_overlay.recovery_sma_sessions)
    sma = {window: values.rolling(window, min_periods=window).mean() for window in lookbacks}
    momentum = {window: values / values.shift(window) - 1.0 for window in lookbacks}

    risk = config.risk_overlay
    volatility: pd.Series | None = None
    drawdown_state: pd.Series | None = None
    if risk is not None:
        reference = values[risk.volatility_reference_symbol]
        volatility = np.log(reference).diff().rolling(
            risk.volatility_lookback_sessions,
            min_periods=risk.volatility_lookback_sessions,
        ).std(ddof=1) * math.sqrt(risk.annualization_sessions)
        draw_reference = values[risk.drawdown_reference_symbol]
        rolling_peak = draw_reference.rolling(
            risk.drawdown_lookback_sessions,
            min_periods=risk.drawdown_lookback_sessions,
        ).max()
        drawdown = draw_reference / rolling_peak - 1.0
        recovery_sma = sma[risk.recovery_sma_sessions][risk.drawdown_reference_symbol]
        active = False
        states = []
        for session in values.index:
            draw = drawdown.loc[session]
            recovery = recovery_sma.loc[session]
            if pd.notna(draw) and float(draw) <= risk.drawdown_trigger:
                active = True
            elif active and pd.notna(recovery) and draw_reference.loc[session] > recovery:
                active = False
            states.append(active)
        drawdown_state = pd.Series(states, index=values.index, dtype=bool)

    month = values.index.to_period("M")
    decision_positions = [
        position
        for position in range(len(values.index) - 1)
        if position == len(values.index) - 1 or month[position] != month[position + 1]
    ]
    target_rows: list[dict[str, float]] = []
    target_index: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    previous_sector_selection: list[str] = []
    for position in decision_positions:
        decision_session = values.index[position]
        execution_session = values.index[position + 1]
        required_symbols = [config.core_symbol]
        if "diversifiers" in config.enabled_sleeves:
            required_symbols.extend(config.diversifier_symbols)
        if "sectors" in config.enabled_sleeves:
            required_symbols.extend(config.sector_relative.symbols)
            required_symbols.append(config.sector_relative.benchmark_symbol)
        required_values = []
        for symbol in required_symbols:
            rule = (
                config.diversifier_trend
                if symbol in config.diversifier_symbols
                else config.core_trend
            )
            required_values.extend(
                [
                    sma[rule.fast_sma_sessions].at[decision_session, symbol],
                    sma[rule.slow_sma_sessions].at[decision_session, symbol],
                    momentum[rule.momentum_sessions].at[decision_session, symbol],
                ]
            )
        if "sectors" in config.enabled_sleeves:
            for symbol in config.sector_relative.symbols:
                required_values.extend(
                    [
                        momentum[config.sector_relative.fast_momentum_sessions].at[
                            decision_session, symbol
                        ],
                        momentum[config.sector_relative.slow_momentum_sessions].at[
                            decision_session, symbol
                        ],
                        sma[config.sector_relative.trend_sma_sessions].at[decision_session, symbol],
                    ]
                )
            required_values.extend(
                [
                    momentum[config.sector_relative.fast_momentum_sessions].at[
                        decision_session, config.sector_relative.benchmark_symbol
                    ],
                    momentum[config.sector_relative.slow_momentum_sessions].at[
                        decision_session, config.sector_relative.benchmark_symbol
                    ],
                ]
            )
        if risk is not None:
            required_values.extend(
                [
                    volatility.loc[decision_session] if volatility is not None else np.nan,
                    sma[risk.recovery_sma_sessions].at[
                        decision_session, risk.drawdown_reference_symbol
                    ],
                ]
            )
        if not all(pd.notna(value) and math.isfinite(float(value)) for value in required_values):
            continue

        weights = {symbol: 0.0 for symbol in values.columns}
        core_votes = _trend_votes(
            values,
            sma,
            momentum,
            decision_session,
            config.core_symbol,
            config.core_trend,
        )
        if core_votes >= config.core_trend.required_positive_votes:
            weights[config.core_symbol] = config.core_budget

        active_diversifiers: list[str] = []
        if "diversifiers" in config.enabled_sleeves:
            slot_weight = config.diversifier_budget / len(config.diversifier_symbols)
            for symbol in config.diversifier_symbols:
                votes = _trend_votes(
                    values,
                    sma,
                    momentum,
                    decision_session,
                    symbol,
                    config.diversifier_trend,
                )
                if votes >= config.diversifier_trend.required_positive_votes:
                    weights[symbol] = slot_weight
                    active_diversifiers.append(symbol)

        selected_sectors: list[str] = []
        sector_scores: dict[str, float] = {}
        if "sectors" in config.enabled_sleeves:
            benchmark = config.sector_relative.benchmark_symbol
            fast = config.sector_relative.fast_momentum_sessions
            slow = config.sector_relative.slow_momentum_sessions
            eligible = []
            for symbol in config.sector_relative.symbols:
                fast_relative = (
                    momentum[fast].at[decision_session, symbol]
                    - momentum[fast].at[decision_session, benchmark]
                )
                slow_relative = (
                    momentum[slow].at[decision_session, symbol]
                    - momentum[slow].at[decision_session, benchmark]
                )
                score = float((fast_relative + slow_relative) / 2.0)
                sector_scores[symbol] = score
                if (
                    values.at[decision_session, symbol]
                    > sma[config.sector_relative.trend_sma_sessions].at[decision_session, symbol]
                ):
                    eligible.append(symbol)
            ranked = sorted(eligible, key=lambda symbol: (-sector_scores[symbol], symbol))
            rank = {symbol: index + 1 for index, symbol in enumerate(ranked)}
            retained = sorted(
                [
                    symbol
                    for symbol in previous_sector_selection
                    if rank.get(symbol, math.inf) <= config.sector_relative.hold_rank
                ],
                key=lambda symbol: (rank[symbol], symbol),
            )
            selected_sectors = retained[: config.sector_relative.top_n]
            for symbol in ranked:
                if len(selected_sectors) >= config.sector_relative.top_n:
                    break
                if symbol not in selected_sectors:
                    selected_sectors.append(symbol)
            sector_slot = config.sector_budget / config.sector_relative.top_n
            for symbol in selected_sectors:
                weights[symbol] = sector_slot
            previous_sector_selection = list(selected_sectors)

        volatility_scale = 1.0
        drawdown_scale = 1.0
        if risk is not None and volatility is not None and drawdown_state is not None:
            realized = float(volatility.loc[decision_session])
            if realized >= risk.high_volatility_threshold:
                volatility_scale = risk.high_exposure_scale
            elif realized >= risk.medium_volatility_threshold:
                volatility_scale = risk.medium_exposure_scale
            if bool(drawdown_state.loc[decision_session]):
                drawdown_scale = risk.drawdown_exposure_scale
            for symbol in values.columns:
                if symbol != config.reserve_symbol:
                    weights[symbol] *= volatility_scale
            weights[config.core_symbol] *= drawdown_scale
            for symbol in config.sector_relative.symbols:
                weights[symbol] *= drawdown_scale

        allocated = math.fsum(weights.values())
        if allocated > 1 + 1e-12:
            raise ValueError(f"{config.candidate_id} target exceeds 100 percent")
        weights[config.reserve_symbol] += 1.0 - allocated
        if not all(math.isfinite(value) and value >= -1e-12 for value in weights.values()):
            raise ValueError(f"{config.candidate_id} generated an invalid target")
        target_rows.append(weights)
        target_index.append(execution_session)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": config.candidate_id,
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "core_positive_votes": core_votes,
            "active_diversifiers": active_diversifiers,
            "selected_sectors": selected_sectors,
            "sector_scores": sector_scores,
            "volatility_scale": volatility_scale,
            "drawdown_scale": drawdown_scale,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(record["weights"])
        records.append(record)

    targets = pd.DataFrame(
        target_rows, index=pd.DatetimeIndex(target_index), columns=values.columns
    )
    if targets.empty:
        raise ValueError(f"{config.candidate_id} produced no complete monthly targets")
    return targets.astype(float), records


def simulate_target_portfolio(
    marks: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    cost_bps: float,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    reserve_symbol: str = "BIL",
) -> SimulationResult:
    prices = marks.astype(float)
    if prices.empty or len(prices) < 2:
        raise ValueError("simulation requires at least two mark sessions")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("simulation marks must be finite and positive")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("simulation sessions must be unique and increasing")
    if list(targets.columns) != list(prices.columns):
        raise ValueError("simulation target symbols must exactly match mark symbols")
    if targets.index.has_duplicates or not targets.index.is_monotonic_increasing:
        raise ValueError("simulation targets must be unique and increasing")
    if not np.isfinite(targets.to_numpy()).all():
        raise ValueError("simulation targets contain nonfinite values")
    target_sums = targets.sum(axis=1).to_numpy()
    if (target_sums < -1e-12).any() or (target_sums > 1 + 1e-10).any():
        raise ValueError("simulation target sums must remain between zero and one")
    if (targets.to_numpy() < -1e-12).any():
        raise ValueError("simulation targets cannot be negative")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative")

    selected_start = pd.Timestamp(start) if start is not None else prices.index.min()
    selected_end = pd.Timestamp(end) if end is not None else prices.index.max()
    window = prices.loc[(prices.index >= selected_start) & (prices.index <= selected_end)]
    if len(window) < 2:
        raise ValueError("simulation window requires at least two sessions")
    rate = cost_bps / 10_000.0
    current = np.zeros(len(window.columns), dtype=float)
    equity = 1.0
    daily_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    total_reported_turnover = 0.0
    cost_factors: list[float] = []
    maximum_weight = 0.0
    first_session = window.index[0]
    prior_targets = targets.loc[targets.index <= first_session]
    initial_target = prior_targets.iloc[-1] if not prior_targets.empty else None

    for position in range(len(window.index) - 1):
        session = window.index[position]
        next_session = window.index[position + 1]
        maximum_weight = max(maximum_weight, float(np.max(current)))
        target: pd.Series | None = None
        reason = ""
        if session in targets.index:
            selected = targets.loc[session]
            if isinstance(selected, pd.DataFrame):
                raise ValueError("duplicate target session")
            target = selected
            reason = "scheduled_rebalance"
        elif position == 0 and initial_target is not None:
            target = initial_target
            reason = "independent_boundary_entry"
        cost_factor = 1.0
        traded_notional = 0.0
        if target is not None:
            target_values = target.to_numpy(dtype=float)
            traded_notional = float(np.abs(target_values - current).sum())
            cost_factor = 1.0 - traded_notional * rate
            if not math.isfinite(cost_factor) or cost_factor <= 0:
                raise ValueError("simulation cost factor is nonpositive")
            current = target_values.copy()
            maximum_weight = max(maximum_weight, float(np.max(current)))
            if traded_notional > 1e-15:
                reported_turnover = 0.5 * traded_notional
                total_reported_turnover += reported_turnover
                cost_factors.append(cost_factor)
                events.append(
                    {
                        "session": session.date().isoformat(),
                        "reason": reason,
                        "traded_notional_fraction": traded_notional,
                        "reported_one_way_turnover": reported_turnover,
                        "cost_factor": cost_factor,
                        "terminal": False,
                    }
                )
        asset_returns = (
            window.iloc[position + 1].to_numpy(dtype=float)
            / window.iloc[position].to_numpy(dtype=float)
            - 1.0
        )
        if not np.isfinite(asset_returns).all() or (asset_returns <= -1).any():
            raise ValueError("simulation produced invalid asset returns")
        gross_return = float(np.dot(current, asset_returns))
        gross_factor = 1.0 + gross_return
        if not math.isfinite(gross_factor) or gross_factor <= 0:
            raise ValueError("simulation gross factor is nonpositive")
        net_factor = cost_factor * gross_factor
        equity *= net_factor
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("simulation equity is invalid")
        current = current * (1.0 + asset_returns) / gross_factor
        if not np.isfinite(current).all() or (current < -1e-12).any():
            raise ValueError("simulation drifted weights are invalid")
        maximum_weight = max(maximum_weight, float(np.max(current)))
        risk_exposure = float(
            sum(
                weight
                for symbol, weight in zip(window.columns, current, strict=True)
                if symbol != reserve_symbol
            )
        )
        daily_rows.append(
            {
                "interval_start": session.date().isoformat(),
                "interval_end": next_session.date().isoformat(),
                "gross_return": gross_return,
                "cost_factor": cost_factor,
                "net_factor": net_factor,
                "net_return": net_factor - 1.0,
                "equity": equity,
                "risk_exposure": risk_exposure,
            }
        )

    terminal_notional = float(np.abs(current).sum())
    terminal_count = 0
    if terminal_notional > 1e-15:
        terminal_factor = 1.0 - terminal_notional * rate
        if not math.isfinite(terminal_factor) or terminal_factor <= 0:
            raise ValueError("terminal liquidation cost factor is nonpositive")
        total_reported_turnover += 0.5 * terminal_notional
        cost_factors.append(terminal_factor)
        equity *= terminal_factor
        last = daily_rows[-1]
        last["cost_factor"] *= terminal_factor
        last["net_factor"] *= terminal_factor
        last["net_return"] = last["net_factor"] - 1.0
        last["equity"] = equity
        events.append(
            {
                "session": window.index[-1].date().isoformat(),
                "reason": "terminal_liquidation",
                "traded_notional_fraction": terminal_notional,
                "reported_one_way_turnover": 0.5 * terminal_notional,
                "cost_factor": terminal_factor,
                "terminal": True,
            }
        )
        current = np.zeros_like(current)
        terminal_count = 1

    daily = pd.DataFrame(daily_rows)
    metrics = _performance_metrics(
        daily,
        events,
        total_reported_turnover=total_reported_turnover,
        maximum_weight=maximum_weight,
        terminal_count=terminal_count,
        cumulative_cost_factor=math.prod(cost_factors) if cost_factors else 1.0,
    )
    return SimulationResult(daily=daily, events=events, metrics=metrics)


def _preflight(root: Path) -> dict[str, Any]:
    validation = validate_iteration_dossier(ITER_ID, root, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R9 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    output = root / ITERATION_DIR
    lock_path = output / "preregistration-lock.json"
    lock = _load_json(lock_path)
    if lock.get("iter_id") != ITER_ID or not str(lock.get("status") or "").startswith(
        "behavior_and_acquisition_contracts_locked"
    ):
        raise ValueError("R9 preregistration lock identity is invalid")
    for binding in lock.get("artifacts", []):
        _verify_file_binding(root, binding)
    for binding in lock.get("specs", []):
        path = _verify_file_binding(
            root,
            {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
        )
        spec = load_strategy_spec(path)
        if strategy_content_hash(spec) != binding.get("semantic_sha256"):
            raise ValueError(f"R9 semantic spec hash mismatch: {binding.get('path')}")

    runner_lock_path = output / "runner-lock.json"
    runner_lock = _load_json(runner_lock_path)
    if runner_lock.get("iter_id") != ITER_ID or runner_lock.get("status") != (
        "implementation_locked_before_first_r9_price_calculation"
    ):
        raise ValueError("R9 runner lock identity is invalid")
    for binding in runner_lock.get("files", []):
        _verify_file_binding(root, binding)

    binding_path = output / "data-snapshot-binding.json"
    binding = _load_json(binding_path)
    daily = binding.get("daily_candidate_bundle")
    intraday = binding.get("intraday_30m_full_universe_bundle")
    if not isinstance(daily, dict) or daily.get("status") != "verified_complete":
        raise ValueError("R9 daily snapshot binding is not verified")
    if not isinstance(intraday, dict) or intraday.get("status") != (
        "verified_complete_selection_prohibited"
    ):
        raise ValueError("R9 full-universe intraday snapshot binding is not verified")
    daily_manifest_path = root / str(daily.get("manifest_path") or "")
    intraday_manifest_path = root / str(intraday.get("manifest_path") or "")
    if _sha256_file(daily_manifest_path) != daily.get("manifest_sha256"):
        raise ValueError("R9 daily snapshot binding hash mismatch")
    if _sha256_file(intraday_manifest_path) != intraday.get("manifest_sha256"):
        raise ValueError("R9 intraday snapshot binding hash mismatch")
    verify_alpaca_contract_snapshot(root, daily_manifest_path)
    verify_alpaca_contract_snapshot(root, intraday_manifest_path)
    candidate_manifest_path = output / "candidate-manifest.json"
    return {
        "status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "preregistration_lock_path": _relpath(lock_path, root),
        "preregistration_lock_sha256": _sha256_file(lock_path),
        "candidate_manifest_path": _relpath(candidate_manifest_path, root),
        "candidate_manifest_sha256": _sha256_file(candidate_manifest_path),
        "runner_lock_path": _relpath(runner_lock_path, root),
        "runner_lock_sha256": _sha256_file(runner_lock_path),
        "data_snapshot_binding_path": _relpath(binding_path, root),
        "data_snapshot_binding_sha256": _sha256_file(binding_path),
        "daily_manifest_path": _relpath(daily_manifest_path, root),
        "daily_manifest_sha256": _sha256_file(daily_manifest_path),
        "intraday_manifest_path": _relpath(intraday_manifest_path, root),
        "intraday_manifest_sha256": _sha256_file(intraday_manifest_path),
    }


def _load_daily_panel(
    manifest_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = _load_json(manifest_path)
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 14:
        raise AlpacaDataError("R9 daily manifest must contain exactly 14 items")
    opens: dict[str, pd.Series] = {}
    closes: dict[str, pd.Series] = {}
    expected_sessions: list[str] | None = None
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("timeframe") != "daily"
            or item.get("feed") != "sip"
            or item.get("adjustment") != "all"
        ):
            raise AlpacaDataError("R9 daily manifest identity mismatch")
        symbol = str(item["symbol"])
        path = manifest_path.parent / str(item["output_path"])
        frame = pd.read_csv(path)
        parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        sessions = pd.DatetimeIndex(parsed.dt.tz_convert(NEW_YORK).dt.date)
        if sessions.has_duplicates or not sessions.is_monotonic_increasing:
            raise AlpacaDataError(f"R9 daily sessions invalid for {symbol}")
        quality_sessions = item.get("quality", {}).get("complete_sessions")
        if expected_sessions is None:
            expected_sessions = list(quality_sessions)
        elif list(quality_sessions) != expected_sessions:
            raise AlpacaDataError("R9 daily complete-session lists differ")
        opens[symbol] = pd.Series(
            pd.to_numeric(frame["open"], errors="raise").to_numpy(), index=sessions
        )
        closes[symbol] = pd.Series(
            pd.to_numeric(frame["close"], errors="raise").to_numpy(), index=sessions
        )
    open_panel = pd.DataFrame(opens).sort_index(axis=1)
    close_panel = pd.DataFrame(closes).reindex_like(open_panel)
    if open_panel.isna().any().any() or close_panel.isna().any().any():
        raise AlpacaDataError("R9 daily panel is not strict and complete")
    return open_panel, close_panel, manifest


def _load_intraday_marks(manifest_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    manifest = _load_json(manifest_path)
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 14:
        raise AlpacaDataError("R9 intraday manifest must contain exactly 14 items")
    marks_0930: dict[str, pd.Series] = {}
    marks_1030: dict[str, pd.Series] = {}
    for item in items:
        if item.get("timeframe") != "30m" or item.get("adjustment") != "raw":
            raise AlpacaDataError("R9 intraday manifest identity mismatch")
        symbol = str(item["symbol"])
        frame = pd.read_csv(manifest_path.parent / str(item["output_path"]))
        parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        local = parsed.dt.tz_convert(NEW_YORK)
        session = pd.DatetimeIndex(local.dt.date)
        local_time = local.dt.time
        values = pd.to_numeric(frame["open"], errors="raise")
        for mark, destination in [(time(9, 30), marks_0930), (time(10, 30), marks_1030)]:
            mask = local_time == mark
            selected_sessions = session[mask]
            if selected_sessions.has_duplicates:
                raise AlpacaDataError(f"duplicate {mark} intraday mark for {symbol}")
            destination[symbol] = pd.Series(values.loc[mask].to_numpy(), index=selected_sessions)
    panel_0930 = pd.DataFrame(marks_0930).sort_index(axis=1)
    panel_1030 = pd.DataFrame(marks_1030).reindex(columns=panel_0930.columns)
    common = panel_0930.index.intersection(panel_1030.index)
    panel_0930 = panel_0930.loc[common]
    panel_1030 = panel_1030.loc[common]
    if panel_0930.isna().any().any() or panel_1030.isna().any().any():
        raise AlpacaDataError("R9 intraday mark panels are incomplete")
    return panel_0930, panel_1030


def _intraday_execution_shadow(
    root: Path,
    preflight: dict[str, Any],
    targets: pd.DataFrame,
) -> dict[str, Any]:
    mark_0930, mark_1030 = _load_intraday_marks(root / preflight["intraday_manifest_path"])
    common_start = mark_0930.index.min()
    common_end = mark_0930.index.max()
    aligned_targets = targets.reindex(columns=mark_0930.columns)
    target_hash = _canonical_hash(
        [
            {
                "execution_session": index.date().isoformat(),
                "weights": {symbol: float(value) for symbol, value in row.items()},
            }
            for index, row in aligned_targets.loc[aligned_targets.index <= common_end].iterrows()
        ]
    )
    at_open = simulate_target_portfolio(
        mark_0930,
        aligned_targets,
        cost_bps=10.0,
        start=common_start,
        end=common_end,
        reserve_symbol="BIL",
    )
    delayed = simulate_target_portfolio(
        mark_1030,
        aligned_targets,
        cost_bps=10.0,
        start=common_start,
        end=common_end,
        reserve_symbol="BIL",
    )
    first_hour = mark_1030 / mark_0930 - 1.0
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "shadow_id": "R9X03_30M_FULL_UNIVERSE",
        "status": "descriptive_selection_prohibited",
        "selection_prohibited": True,
        "holding_changes_forbidden": True,
        "same_target_hash": True,
        "target_sha256_0930": target_hash,
        "target_sha256_1030": target_hash,
        "common_start": common_start.date().isoformat(),
        "common_end": common_end.date().isoformat(),
        "common_sessions": len(mark_0930),
        "symbol_count": len(mark_0930.columns),
        "mark_0930_metrics": at_open.metrics,
        "mark_1030_metrics": delayed.metrics,
        "sharpe_delta_1030_minus_0930": delayed.metrics["annualized_sharpe"]
        - at_open.metrics["annualized_sharpe"],
        "return_delta_pct_1030_minus_0930": delayed.metrics["total_return_pct"]
        - at_open.metrics["total_return_pct"],
        "first_hour_return_bps": {
            "median": float(first_hour.stack().median() * 10_000.0),
            "p05": float(first_hour.stack().quantile(0.05) * 10_000.0),
            "p95": float(first_hour.stack().quantile(0.95) * 10_000.0),
        },
        "limitations": [
            "Raw intraday bars omit cash distributions and are used only for a paired "
            "timing diagnostic.",
            "The 09:30 SIP bar is not proven to equal every primary-exchange official "
            "opening auction.",
            "No intraday result may select, filter, resize, or promote the daily candidate.",
        ],
    }


def _benchmark_family(
    opens: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    columns = list(opens.columns)
    sector_symbols = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]

    def static(weights: dict[str, float]) -> dict[str, Any]:
        row = {symbol: float(weights.get(symbol, 0.0)) for symbol in columns}
        targets = pd.DataFrame([row], index=pd.DatetimeIndex([start]), columns=columns)
        return simulate_target_portfolio(
            opens,
            targets,
            cost_bps=10.0,
            start=start,
            end=end,
            reserve_symbol="BIL",
        ).metrics

    results = {
        "SPY_same_symbol_buy_and_hold": static({"SPY": 1.0}),
        "equal_weight_full_universe": static({symbol: 1.0 / len(columns) for symbol in columns}),
        "equal_weight_sector_etfs": static(
            {symbol: 1.0 / len(sector_symbols) for symbol in sector_symbols}
        ),
        "QQQ_growth_proxy": static({"QQQ": 1.0}),
        "BIL_cash_proxy": static({"BIL": 1.0}),
        "uninvested_cash": static({}),
    }
    symbol_results = {symbol: static({symbol: 1.0}) for symbol in columns}
    best_symbol = max(
        symbol_results,
        key=lambda symbol: (symbol_results[symbol]["total_return_pct"], symbol),
    )
    results["ex_post_best_symbol_report_only"] = {
        **symbol_results[best_symbol],
        "symbol": best_symbol,
        "selection_use": "report_only",
    }
    return results


def _target_contract_checks(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    records: list[dict[str, Any]],
    spec: StrategySpec,
) -> list[dict[str, Any]]:
    config = spec.portfolio.etf_structural
    if config is None:
        raise ValueError("target checks require ETF structural config")
    session_position = {session: position for position, session in enumerate(opens.index)}
    exact_next = all(
        session_position[pd.Timestamp(record["execution_session"])]
        == session_position[pd.Timestamp(record["decision_session"])] + 1
        for record in records
    )
    month_end = all(
        opens.index[session_position[pd.Timestamp(record["decision_session"])]].to_period("M")
        != opens.index[session_position[pd.Timestamp(record["decision_session"])] + 1].to_period(
            "M"
        )
        for record in records
    )
    core_max = float(targets[config.core_symbol].max())
    return [
        _gate(
            f"{config.candidate_id}_target_rows_finite", np.isfinite(targets.to_numpy()).all(), True
        ),
        _gate(
            f"{config.candidate_id}_target_sums",
            bool(np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)),
            1.0,
        ),
        _gate(
            f"{config.candidate_id}_targets_nonnegative",
            bool((targets >= -1e-12).all().all()),
            True,
        ),
        _gate(f"{config.candidate_id}_exact_next_session_execution", exact_next, True),
        _gate(f"{config.candidate_id}_calendar_month_end_decisions", month_end, True),
        _gate(
            f"{config.candidate_id}_core_target_cap",
            core_max <= config.core_budget + 1e-12,
            config.core_budget,
            core_max,
        ),
    ]


def _trend_votes(
    closes: pd.DataFrame,
    sma: dict[int, pd.DataFrame],
    momentum: dict[int, pd.DataFrame],
    session: pd.Timestamp,
    symbol: str,
    rule: Any,
) -> int:
    return sum(
        [
            closes.at[session, symbol] > sma[rule.fast_sma_sessions].at[session, symbol],
            closes.at[session, symbol] > sma[rule.slow_sma_sessions].at[session, symbol],
            momentum[rule.momentum_sessions].at[session, symbol] > 0,
        ]
    )


def _performance_metrics(
    daily: pd.DataFrame,
    events: list[dict[str, Any]],
    *,
    total_reported_turnover: float,
    maximum_weight: float,
    terminal_count: int,
    cumulative_cost_factor: float,
) -> dict[str, Any]:
    returns = pd.to_numeric(daily["net_return"], errors="raise").astype(float)
    if returns.empty or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("performance returns must be finite and non-empty")
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    if not np.isfinite(equity.to_numpy()).all() or (equity <= 0).any():
        raise ValueError("performance equity must be finite and positive")
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0
    full_curve = pd.concat([pd.Series([1.0]), equity], ignore_index=True)
    drawdown = full_curve / full_curve.cummax() - 1.0
    years = len(returns) / 252.0
    final_equity = float(equity.iloc[-1])
    return {
        "market_interval_count": len(returns),
        "total_return_pct": (final_equity - 1.0) * 100.0,
        "annualized_return_pct": (final_equity ** (1.0 / years) - 1.0) * 100.0,
        "annualized_volatility_pct": std * math.sqrt(252.0) * 100.0,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "positive_interval_pct": float((returns > 0).mean() * 100.0),
        "total_reported_one_way_turnover": total_reported_turnover,
        "annualized_reported_one_way_turnover": total_reported_turnover / years,
        "maximum_drifted_weight": maximum_weight,
        "average_risk_asset_exposure": float(daily["risk_exposure"].mean()),
        "nonzero_rebalance_count": sum(not event["terminal"] for event in events),
        "terminal_liquidation_count": terminal_count,
        "cumulative_cost_factor": cumulative_cost_factor,
    }


def _deflated_sharpe(returns: pd.Series, trial_count: int) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if trial_count < 2 or len(values) < 3 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("DSR requires finite returns, at least three sessions, and N>=2")
    standard_deviation = float(values.std(ddof=1))
    if standard_deviation <= 0:
        return {
            "trial_count": trial_count,
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


def _probability_backtest_overfitting(
    fold_returns: dict[str, list[pd.Series]],
) -> dict[str, Any]:
    candidate_ids = sorted(fold_returns)
    fold_count = len(next(iter(fold_returns.values())))
    if fold_count != 4 or any(len(rows) != fold_count for rows in fold_returns.values()):
        raise ValueError("R9 PBO requires four folds for every candidate")
    partitions = []
    overfit_count = 0
    for train_indices in combinations(range(fold_count), fold_count // 2):
        test_indices = tuple(index for index in range(fold_count) if index not in train_indices)
        train_sharpes = {
            candidate_id: _series_sharpe(
                pd.concat([fold_returns[candidate_id][index] for index in train_indices])
            )
            for candidate_id in candidate_ids
        }
        selected = max(candidate_ids, key=lambda item: (train_sharpes[item], item))
        test_sharpes = {
            candidate_id: _series_sharpe(
                pd.concat([fold_returns[candidate_id][index] for index in test_indices])
            )
            for candidate_id in candidate_ids
        }
        ranked = sorted(candidate_ids, key=lambda item: (-test_sharpes[item], item))
        rank = ranked.index(selected) + 1
        overfit = rank > len(candidate_ids) / 2
        overfit_count += int(overfit)
        partitions.append(
            {
                "train_folds": [index + 1 for index in train_indices],
                "test_folds": [index + 1 for index in test_indices],
                "selected_candidate_id": selected,
                "selected_oos_rank": rank,
                "overfit": overfit,
            }
        )
    return {
        "method": "chronological_four_fold_combinatorial_diagnostic",
        "partition_count": len(partitions),
        "overfit_partition_count": overfit_count,
        "probability": overfit_count / len(partitions),
        "partitions": partitions,
        "limitations": (
            "Four exposed chronological folds provide a coarse diagnostic, not an "
            "independent lockbox."
        ),
    }


def _series_sharpe(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("Sharpe input contains nonfinite returns")
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return float(values.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0


def _candidate_id(spec: StrategySpec) -> str:
    config = spec.portfolio.etf_structural
    if config is None:
        raise ValueError(f"{spec.name} has no ETF structural configuration")
    return config.candidate_id


def _gate(
    name: str,
    passed: Any,
    threshold: Any,
    actual: Any | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "pass": bool(passed),
        "actual": bool(passed) if actual is None else _json_value(actual),
        "threshold": _json_value(threshold),
    }


def _verify_file_binding(root: Path, binding: dict[str, Any]) -> Path:
    path = root / str(binding.get("path") or "")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("R9 binding escapes repository root") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    if _sha256_file(path) != binding.get("sha256"):
        raise ValueError(f"R9 file binding mismatch: {binding.get('path')}")
    return path


def _update_search_space_outputs(root: Path, trial_path: Path, evaluation_path: Path) -> None:
    path = root / ITERATION_DIR / "search-space.json"
    payload = _load_json(path)
    payload["trial_ledger_paths"] = [_relpath(trial_path, root)]
    payload["evaluation_report_paths"] = [_relpath(evaluation_path, root)]
    write_json(path, payload)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ETF Structural Momentum R9",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- Paper ready pass: `{payload['paper_ready_pass']}`",
        f"- Data: `{payload['data']['first_session']}` through `{payload['data']['last_session']}`",
        "",
        "## Candidates",
        "",
        "| Candidate | Net return 10bps | Sharpe | Max drawdown | Turnover/year |",
        "|---|---:|---:|---:|---:|",
    ]
    for candidate_id, row in payload["candidates"].items():
        metrics = row["cost_views"]["primary_10bps"]
        lines.append(
            f"| {candidate_id} | {metrics['total_return_pct']:.3f}% | "
            f"{metrics['annualized_sharpe']:.3f} | {metrics['max_drawdown_pct']:.3f}% | "
            f"{metrics['annualized_reported_one_way_turnover']:.3f} |"
        )
    lines.extend(["", "## Gates", ""])
    lines.extend(
        f"- `{'pass' if check['pass'] else 'fail'}` {check['name']}: "
        f"actual `{check['actual']}`, threshold `{check['threshold']}`"
        for check in payload["gate_checks"]
    )
    lines.extend(
        [
            "",
            "## Intraday Shadow",
            "",
            "The 09:30 versus 10:30 result uses the identical daily target schedule "
            "on raw SIP 30-minute marks. It is selection-prohibited and does not "
            "affect promotion.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        "".join(
            json.dumps(
                _json_value(row),
                allow_nan=False,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        _json_value(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
