from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.config import ensure_dir
from open_composer.market_calendar import NEW_YORK
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_spy_dual_trend_core_r8"
STRATEGY_NAME = "us_spy_dual_trend_core_r8"
SPEC_PATH = Path("strategy_specs/drafts/us_spy_dual_trend_core_r8.yaml")
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/alpaca_spy_dual_trend_r8")
LOOKBACK = 126
TARGET_WEIGHT = 0.4


@dataclass(frozen=True)
class SimulationResult:
    daily: pd.DataFrame
    trades: list[dict[str, Any]]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class R8EvaluationResult:
    evaluation_path: Path
    evaluation_markdown_path: Path
    trial_ledger_path: Path
    state_path: Path
    fold_path: Path
    payload: dict[str, Any]


def compute_target_states(close: pd.Series, lookback: int = LOOKBACK) -> pd.DataFrame:
    values = pd.to_numeric(close, errors="raise").astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("close contains nonfinite values")
    moving_average = values.rolling(lookback, min_periods=lookback).mean()
    momentum = values / values.shift(lookback) - 1.0
    valid = moving_average.notna() & momentum.notna()
    decision = ((values > moving_average) & (momentum > 0)).where(valid)
    target = decision.shift(1)
    return pd.DataFrame(
        {
            "close": values,
            "sma": moving_average,
            "momentum": momentum,
            "decision_state": decision,
            "target_state": target,
        }
    )


def simulate_entry_only_target(
    opens: pd.Series,
    target_states: pd.Series,
    *,
    cost_bps: float,
    target_weight: float = TARGET_WEIGHT,
) -> SimulationResult:
    if len(opens) != len(target_states) or len(opens) < 2:
        raise ValueError(
            "simulation requires aligned open and target series with at least two rows"
        )
    prices = pd.to_numeric(opens, errors="raise").astype(float)
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any():
        raise ValueError("simulation opens must be finite and positive")
    if target_states.isna().any():
        raise ValueError("simulation target states must be complete")
    targets = target_states.astype(bool)
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative")
    if not 0 < target_weight <= 1:
        raise ValueError("target_weight must be in (0, 1]")

    rate = cost_bps / 10_000.0
    cash = 1.0
    shares = 0.0
    previous_equity = 1.0
    daily_rows = []
    trades = []
    total_turnover = 0.0
    max_weight = 0.0
    for position, (index, price_raw) in enumerate(prices.items()):
        price = float(price_raw)
        pretrade_equity = cash + shares * price
        _require_finite_positive(pretrade_equity, "pretrade equity")
        pretrade_weight = shares * price / pretrade_equity
        max_weight = max(max_weight, pretrade_weight)
        desired_on = bool(targets.loc[index])
        action = "hold"
        trade_notional = 0.0
        trade_cost = 0.0
        if desired_on and shares == 0.0:
            action = "entry"
            trade_notional = pretrade_equity * target_weight
            trade_cost = trade_notional * rate
            shares = trade_notional / price
            cash -= trade_notional + trade_cost
        elif not desired_on and shares > 0.0:
            action = "exit"
            trade_notional = shares * price
            trade_cost = trade_notional * rate
            cash += trade_notional - trade_cost
            shares = 0.0
        if action != "hold":
            turnover = trade_notional / pretrade_equity
            total_turnover += turnover
            trades.append(
                {
                    "timestamp": _index_value(index),
                    "action": action,
                    "price": price,
                    "notional": trade_notional,
                    "turnover": turnover,
                    "cost": trade_cost,
                    "terminal": False,
                }
            )

        terminal_cost = 0.0
        if position == len(prices) - 1 and shares > 0.0:
            terminal_pretrade = cash + shares * price
            terminal_notional = shares * price
            terminal_cost = terminal_notional * rate
            terminal_turnover = terminal_notional / terminal_pretrade
            total_turnover += terminal_turnover
            cash += terminal_notional - terminal_cost
            shares = 0.0
            trades.append(
                {
                    "timestamp": _index_value(index),
                    "action": "terminal_exit",
                    "price": price,
                    "notional": terminal_notional,
                    "turnover": terminal_turnover,
                    "cost": terminal_cost,
                    "terminal": True,
                }
            )
        equity = cash + shares * price
        _require_finite_positive(equity, "posttrade equity")
        posttrade_weight = shares * price / equity
        max_weight = max(max_weight, posttrade_weight)
        daily_return = equity / previous_equity - 1.0
        if not math.isfinite(daily_return):
            raise ValueError("simulation produced nonfinite daily return")
        daily_rows.append(
            {
                "timestamp": _index_value(index),
                "open": price,
                "target_state": desired_on,
                "action": action,
                "pretrade_weight": pretrade_weight,
                "posttrade_weight": posttrade_weight,
                "trade_cost": trade_cost,
                "terminal_cost": terminal_cost,
                "daily_return": daily_return,
                "equity": equity,
            }
        )
        previous_equity = equity
    daily = pd.DataFrame(daily_rows)
    metrics = _performance_metrics(
        daily["daily_return"],
        daily["equity"],
        total_turnover=total_turnover,
        max_weight=max_weight,
        trades=trades,
    )
    return SimulationResult(daily=daily, trades=trades, metrics=metrics)


def run_spy_dual_trend_r8(root: Path) -> R8EvaluationResult:
    output = root / ITERATION_DIR
    paths = {
        "evaluation": output / "evaluation-report.json",
        "evaluation_md": output / "evaluation-report.md",
        "trial": output / "trial-ledger.jsonl",
        "states": output / "signal-states.csv",
        "folds": output / "fold-results.json",
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing:
        raise ValueError(f"R8 evaluation is immutable and already exists: {existing[0]}")
    spec_path = root / SPEC_PATH
    spec = load_strategy_spec(spec_path)
    spec_hash = strategy_content_hash(spec)
    gates = _load_json(root / ITERATION_DIR / "evaluation-gates.json")
    trial_contract = _load_json(root / ITERATION_DIR / "cumulative-trial-contract.json")
    if trial_contract.get("conservative_DSR_governance_N") != 8002:
        raise ValueError("R8 cumulative trial contract must freeze primary DSR N=8002")
    if trial_contract.get("sensitivity_DSR_governance_N") != 4664:
        raise ValueError("R8 cumulative trial contract must freeze sensitivity DSR N=4664")
    data_manifest = _validate_bundle(root)
    spy = load_ohlcv_for_spec(spec, root)
    daily_panel = _daily_panel(root, data_manifest)
    if list(_session_dates(spy)) != list(daily_panel["session"]):
        raise ValueError("StrategySpec SPY data does not match the immutable daily panel")

    states = compute_target_states(spy["close"].reset_index(drop=True))
    eligible = states["target_state"].notna()
    if int(eligible.sum()) < 252:
        raise ValueError("R8 has fewer than 252 eligible execution sessions")
    evaluation_panel = daily_panel.loc[eligible.to_numpy()].reset_index(drop=True)
    evaluation_states = states.loc[eligible].reset_index(drop=True)
    target = evaluation_states["target_state"].astype(bool)

    cost_results = {}
    simulations = {}
    for cost_bps in [5.0, 10.0, 20.0]:
        simulation = simulate_entry_only_target(
            evaluation_panel["SPY_open"],
            target,
            cost_bps=cost_bps,
        )
        simulations[cost_bps] = simulation
        cost_results[f"{cost_bps:g}bps"] = simulation.metrics
    folds = _fold_evaluations(evaluation_panel["SPY_open"], target, cost_bps=10.0)
    benchmarks = _benchmarks(evaluation_panel, cost_bps=10.0)
    cross_feed = _cross_feed_report(root, spy, states)
    primary = simulations[10.0]
    dsr = {
        "N8002": _deflated_sharpe(primary.daily["daily_return"], 8002),
        "N4664_sensitivity": _deflated_sharpe(primary.daily["daily_return"], 4664),
    }
    checks = _gate_checks(
        gates,
        primary.metrics,
        simulations[20.0].metrics,
        folds,
        benchmarks,
        cross_feed,
        dsr,
    )
    historical_pass = all(check["pass"] for check in checks)
    decision = "continue_to_formal_forward_observation" if historical_pass else "stop_R8D01"
    payload = {
        "schema_version": 1,
        "report_type": "spy_dual_trend_r8_evaluation",
        "generated_at": datetime.now(UTC).isoformat(),
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "candidate_id": "R8D01",
        "spec_path": SPEC_PATH.as_posix(),
        "spec_hash": spec_hash,
        "data_window": {
            "source_start": daily_panel["session"].iloc[0],
            "source_end": daily_panel["session"].iloc[-1],
            "source_sessions": len(daily_panel),
            "evaluation_start": evaluation_panel["session"].iloc[0],
            "evaluation_end": evaluation_panel["session"].iloc[-1],
            "evaluation_sessions": len(evaluation_panel),
            "historical_visibility": "exposed_robustness_only",
        },
        "data_manifest": {
            "path": (DATA_DIR / "snapshot-manifest.json").as_posix(),
            "sha256": _sha256_file(root / DATA_DIR / "snapshot-manifest.json"),
            "contract_sha256": data_manifest["contract_sha256"],
            "request_count": data_manifest["request_count"],
        },
        "cost_results": cost_results,
        "folds_10bps": folds,
        "benchmarks_10bps": benchmarks,
        "cross_feed": cross_feed,
        "deflated_sharpe": dsr,
        "gate_checks": checks,
        "historical_robustness_pass": historical_pass,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "decision": decision,
        "decision_reason": (
            "All preregistered historical gates passed; continue only to forward observation."
            if historical_pass
            else "At least one preregistered historical gate failed; do not tune or promote R8D01."
        ),
        "remaining_mandatory_gates": [
            "20 completed strategy-and-policy-bound forward sessions beginning 2026-07-20",
            "30 matched TCA observations",
            "Python and Nautilus execution parity",
            "promotion, paper safety, and explicit paper-order authorization",
        ],
        "artifact_bindings": _artifact_bindings(root),
        "model_training": False,
        "parameter_search": False,
        "broker_orders_authorized": False,
    }
    ensure_dir(output)
    states_output = pd.concat(
        [
            daily_panel[["session", "SPY_open", "SPY_close"]],
            states[["sma", "momentum", "decision_state", "target_state"]],
        ],
        axis=1,
    )
    states_output.to_csv(paths["states"], index=False, lineterminator="\n")
    write_json(paths["folds"], {"iter_id": ITER_ID, "folds": folds})
    write_json(paths["evaluation"], payload)
    paths["evaluation_md"].write_text(_render_markdown(payload), encoding="utf-8")
    trial_row = {
        "iter_id": ITER_ID,
        "candidate_id": "R8D01",
        "spec_hash": spec_hash,
        "data_manifest_sha256": payload["data_manifest"]["sha256"],
        "parameter_set": {"lookback_sessions": 126, "target_weight": 0.4},
        "cost_results": cost_results,
        "folds_10bps": folds,
        "deflated_sharpe": dsr,
        "historical_robustness_pass": historical_pass,
        "research_pass": False,
        "paper_ready_pass": False,
        "decision": decision,
    }
    paths["trial"].write_text(
        json.dumps(trial_row, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return R8EvaluationResult(
        evaluation_path=paths["evaluation"],
        evaluation_markdown_path=paths["evaluation_md"],
        trial_ledger_path=paths["trial"],
        state_path=paths["states"],
        fold_path=paths["folds"],
        payload=payload,
    )


def _daily_panel(root: Path, manifest: dict[str, Any]) -> pd.DataFrame:
    frames = []
    for symbol in ["SPY", "QQQ", "XLK", "BIL"]:
        item = _manifest_item(manifest, symbol, "daily", "all")
        path = root / DATA_DIR / str(item["output_path"])
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        frame["session"] = _session_dates(frame)
        selected = frame[["session", "open", "close"]].rename(
            columns={"open": f"{symbol}_open", "close": f"{symbol}_close"}
        )
        frames.append(selected)
    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="session", how="inner", validate="one_to_one")
    expected = int(_manifest_item(manifest, "SPY", "daily", "all")["row_count"])
    if len(panel) != expected:
        raise ValueError("daily benchmark panel does not have an exact shared session set")
    numeric = panel.drop(columns="session").to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("daily benchmark panel contains nonfinite values")
    return panel


def _fold_evaluations(
    opens: pd.Series,
    target: pd.Series,
    *,
    cost_bps: float,
) -> list[dict[str, Any]]:
    folds = []
    for fold_number, positions in enumerate(np.array_split(np.arange(len(opens)), 4), start=1):
        selected_opens = opens.iloc[positions].reset_index(drop=True)
        selected_target = target.iloc[positions].reset_index(drop=True)
        simulation = simulate_entry_only_target(
            selected_opens,
            selected_target,
            cost_bps=cost_bps,
        )
        terminal_trades = sum(bool(trade["terminal"]) for trade in simulation.trades)
        folds.append(
            {
                "fold": fold_number,
                "start_position": int(positions[0]),
                "end_position": int(positions[-1]),
                "session_count": len(positions),
                "metrics": simulation.metrics,
                "entry_trade_count": sum(trade["action"] == "entry" for trade in simulation.trades),
                "terminal_liquidation_count": terminal_trades,
                "starts_in_cash": True,
                "liquidates_independently": True,
            }
        )
    return folds


def _benchmarks(panel: pd.DataFrame, *, cost_bps: float) -> dict[str, Any]:
    always_on = pd.Series(True, index=panel.index)
    spy_full = simulate_entry_only_target(
        panel["SPY_open"], always_on, cost_bps=cost_bps, target_weight=1.0
    ).metrics
    spy_matched = simulate_entry_only_target(
        panel["SPY_open"], always_on, cost_bps=cost_bps, target_weight=0.4
    ).metrics
    result = {
        "SPY_same_symbol_buy_and_hold": spy_full,
        "SPY_40_percent_plus_60_percent_cash_buy_and_hold": spy_matched,
        "equal_weight_single_symbol_universe_SPY": {
            **spy_full,
            "alias_of": "SPY_same_symbol_buy_and_hold",
        },
    }
    for symbol, name in [
        ("QQQ", "QQQ_growth_proxy"),
        ("XLK", "XLK_sector_proxy"),
        ("BIL", "BIL_cash_proxy"),
    ]:
        result[name] = simulate_entry_only_target(
            panel[f"{symbol}_open"],
            always_on,
            cost_bps=cost_bps,
            target_weight=1.0,
        ).metrics
    result["uninvested_cash"] = {
        "total_return_pct": 0.0,
        "annualized_return_pct": 0.0,
        "annualized_sharpe": 0.0,
        "max_drawdown_pct": 0.0,
        "session_count": len(panel),
    }
    result["ex_post_best_symbol_not_applicable_single_symbol"] = {
        "status": "not_applicable",
        "reason": "The selectable universe contains only SPY.",
    }
    return result


def _cross_feed_report(root: Path, sip: pd.DataFrame, sip_states: pd.DataFrame) -> dict[str, Any]:
    iex_path = root / "data/research/alpaca_multiscale_r6/spy_1d_alpaca_iex_all.csv"
    receipt_path = root / "data/research/alpaca_multiscale_r6/refresh-receipt.json"
    receipt = _load_json(receipt_path)
    receipt_row = next(
        (
            row
            for row in receipt.get("rows", [])
            if row.get("symbol") == "SPY" and row.get("timeframe") == "1d"
        ),
        None,
    )
    if not isinstance(receipt_row, dict) or receipt_row.get("sha256") != _sha256_file(iex_path):
        raise ValueError("IEX cross-feed source does not match its refresh receipt")
    iex = pd.read_csv(iex_path)
    iex["timestamp"] = pd.to_datetime(iex["timestamp"], utc=True, errors="raise")
    if not np.isfinite(iex[["open", "close"]].to_numpy(dtype=float)).all():
        raise ValueError("IEX cross-feed source contains nonfinite values")
    iex_states = compute_target_states(iex["close"])
    sip_compare = pd.DataFrame(
        {
            "session": _session_dates(sip),
            "sip_open": sip["open"].to_numpy(),
            "sip_close": sip["close"].to_numpy(),
            "sip_target": sip_states["target_state"].to_numpy(),
        }
    )
    iex_compare = pd.DataFrame(
        {
            "session": _session_dates(iex),
            "iex_open": iex["open"].to_numpy(),
            "iex_close": iex["close"].to_numpy(),
            "iex_target": iex_states["target_state"].to_numpy(),
        }
    )
    common = sip_compare.merge(iex_compare, on="session", validate="one_to_one").dropna()
    if common.empty:
        raise ValueError("SIP and IEX cross-feed comparison has no complete common sessions")
    target_match = common["sip_target"].astype(bool) == common["iex_target"].astype(bool)
    sip_transition = (
        common["sip_target"].astype(bool).ne(common["sip_target"].astype(bool).shift(1))
    )
    iex_transition = (
        common["iex_target"].astype(bool).ne(common["iex_target"].astype(bool).shift(1))
    )
    close_diff = (common["iex_close"] / common["sip_close"] - 1.0).abs() * 10_000.0
    open_diff = (common["iex_open"] / common["sip_open"] - 1.0).abs() * 10_000.0
    return {
        "status": "verified_overlap",
        "common_start": common["session"].iloc[0],
        "common_end": common["session"].iloc[-1],
        "common_sessions": len(common),
        "target_state_agreement": float(target_match.mean()),
        "target_state_mismatch_count": int((~target_match).sum()),
        "transition_mismatch_count": int((sip_transition != iex_transition).sum()),
        "median_absolute_close_difference_bps": float(close_diff.median()),
        "p99_absolute_close_difference_bps": float(close_diff.quantile(0.99)),
        "median_absolute_open_difference_bps": float(open_diff.median()),
        "p99_absolute_open_difference_bps": float(open_diff.quantile(0.99)),
        "iex_path": iex_path.relative_to(root).as_posix(),
        "iex_sha256": _sha256_file(iex_path),
        "iex_receipt_path": receipt_path.relative_to(root).as_posix(),
        "iex_receipt_sha256": _sha256_file(receipt_path),
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
    expected_max_standard = (1 - gamma) * normal.inv_cdf(
        1 - 1 / trial_count
    ) + gamma * normal.inv_cdf(1 - 1 / (trial_count * math.e))
    expected_daily = expected_max_standard / math.sqrt(len(values) - 1)
    skew = float(values.skew())
    kurtosis = float(values.kurt()) + 3.0
    denominator_term = 1 - skew * observed_daily + ((kurtosis - 1) / 4.0) * observed_daily**2
    if not math.isfinite(denominator_term) or denominator_term <= 0:
        probability = 0.0
    else:
        statistic = (
            (observed_daily - expected_daily)
            * math.sqrt(len(values) - 1)
            / math.sqrt(denominator_term)
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


def _gate_checks(
    gates: dict[str, Any],
    primary: dict[str, Any],
    severe: dict[str, Any],
    folds: list[dict[str, Any]],
    benchmarks: dict[str, Any],
    cross_feed: dict[str, Any],
    dsr: dict[str, Any],
) -> list[dict[str, Any]]:
    performance = gates["historical_performance_gates"]
    cross = gates["cross_feed_gates"]
    matched = benchmarks["SPY_40_percent_plus_60_percent_cash_buy_and_hold"]
    positive_folds = sum(fold["metrics"]["total_return_pct"] > 0 for fold in folds)
    raw_checks = [
        (
            "net_total_return_10bps",
            primary["total_return_pct"] > performance["net_total_return_pct_10bps_min_exclusive"],
            primary["total_return_pct"],
            performance["net_total_return_pct_10bps_min_exclusive"],
        ),
        (
            "net_sharpe_10bps",
            primary["annualized_sharpe"] >= performance["net_annualized_sharpe_10bps_min"],
            primary["annualized_sharpe"],
            performance["net_annualized_sharpe_10bps_min"],
        ),
        (
            "net_max_drawdown_10bps",
            primary["max_drawdown_pct"] >= performance["net_max_drawdown_pct_10bps_min"],
            primary["max_drawdown_pct"],
            performance["net_max_drawdown_pct_10bps_min"],
        ),
        (
            "positive_net_folds_10bps",
            positive_folds >= performance["positive_net_fold_count_10bps_min"],
            positive_folds,
            performance["positive_net_fold_count_10bps_min"],
        ),
        (
            "net_total_return_20bps",
            severe["total_return_pct"] > performance["net_total_return_pct_20bps_min_exclusive"],
            severe["total_return_pct"],
            performance["net_total_return_pct_20bps_min_exclusive"],
        ),
        (
            "matched_40_60_sharpe_delta",
            primary["annualized_sharpe"] - matched["annualized_sharpe"]
            >= performance["matched_40_60_buy_hold_sharpe_delta_min"],
            primary["annualized_sharpe"] - matched["annualized_sharpe"],
            performance["matched_40_60_buy_hold_sharpe_delta_min"],
        ),
        (
            "matched_40_60_drawdown_delta",
            primary["max_drawdown_pct"] - matched["max_drawdown_pct"]
            >= performance["matched_40_60_buy_hold_drawdown_delta_min_pct"],
            primary["max_drawdown_pct"] - matched["max_drawdown_pct"],
            performance["matched_40_60_buy_hold_drawdown_delta_min_pct"],
        ),
        (
            "deflated_sharpe_probability_N8002",
            dsr["N8002"]["probability"] >= performance["deflated_sharpe_probability_min"],
            dsr["N8002"]["probability"],
            performance["deflated_sharpe_probability_min"],
        ),
        (
            "cross_feed_common_sessions",
            cross_feed["common_sessions"] >= cross["minimum_common_sessions"],
            cross_feed["common_sessions"],
            cross["minimum_common_sessions"],
        ),
        (
            "cross_feed_target_state_agreement",
            cross_feed["target_state_agreement"] >= cross["target_state_agreement_min"],
            cross_feed["target_state_agreement"],
            cross["target_state_agreement_min"],
        ),
        (
            "cross_feed_transition_mismatches",
            cross_feed["transition_mismatch_count"] <= cross["transition_mismatch_count_max"],
            cross_feed["transition_mismatch_count"],
            cross["transition_mismatch_count_max"],
        ),
        (
            "cross_feed_median_close_difference_bps",
            cross_feed["median_absolute_close_difference_bps"]
            <= cross["median_absolute_close_difference_bps_max"],
            cross_feed["median_absolute_close_difference_bps"],
            cross["median_absolute_close_difference_bps_max"],
        ),
        (
            "cross_feed_p99_close_difference_bps",
            cross_feed["p99_absolute_close_difference_bps"]
            <= cross["p99_absolute_close_difference_bps_max"],
            cross_feed["p99_absolute_close_difference_bps"],
            cross["p99_absolute_close_difference_bps_max"],
        ),
    ]
    checks = [
        {"name": name, "pass": bool(passed), "actual": actual, "threshold": threshold}
        for name, passed, actual, threshold in raw_checks
    ]
    checks.extend(
        {
            "name": f"fold_{fold['fold']}_independent_terminal_accounting",
            "pass": fold["terminal_liquidation_count"] in {0, 1}
            and fold["starts_in_cash"]
            and fold["liquidates_independently"],
            "actual": fold["terminal_liquidation_count"],
            "threshold": "0_if_flat_else_1",
        }
        for fold in folds
    )
    return checks


def _performance_metrics(
    returns: pd.Series,
    equity: pd.Series,
    *,
    total_turnover: float,
    max_weight: float,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    curve = pd.to_numeric(equity, errors="raise").astype(float)
    if not np.isfinite(values.to_numpy()).all() or not np.isfinite(curve.to_numpy()).all():
        raise ValueError("performance inputs contain nonfinite values")
    standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    sharpe = (
        float(values.mean() / standard_deviation * math.sqrt(252.0))
        if standard_deviation > 0
        else 0.0
    )
    final_equity = float(curve.iloc[-1])
    annualized = final_equity ** (252.0 / len(curve)) - 1.0
    full_curve = pd.concat([pd.Series([1.0]), curve], ignore_index=True)
    drawdown = full_curve / full_curve.cummax() - 1.0
    return {
        "session_count": len(curve),
        "total_return_pct": (final_equity - 1.0) * 100.0,
        "annualized_return_pct": annualized * 100.0,
        "annualized_volatility_pct": standard_deviation * math.sqrt(252.0) * 100.0,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "positive_session_pct": float((values > 0).mean() * 100.0),
        "total_turnover": total_turnover,
        "maximum_drifted_weight": max_weight,
        "order_count": len(trades),
        "entry_count": sum(trade["action"] == "entry" for trade in trades),
        "exit_count": sum(trade["action"] in {"exit", "terminal_exit"} for trade in trades),
        "terminal_liquidation_count": sum(bool(trade["terminal"]) for trade in trades),
        "total_cost": sum(float(trade["cost"]) for trade in trades),
    }


def _validate_bundle(root: Path) -> dict[str, Any]:
    manifest_path = root / DATA_DIR / "snapshot-manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("provider") != "alpaca" or manifest.get("immutable") is not True:
        raise AlpacaDataError("R8 data manifest is not an immutable Alpaca snapshot")
    contract_path = root / str(manifest.get("contract_path") or "")
    if manifest.get("contract_sha256") != _sha256_file(contract_path):
        raise AlpacaDataError("R8 data contract hash mismatch")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 7:
        raise AlpacaDataError("R8 data manifest requires exactly seven snapshot items")
    for item in items:
        if not isinstance(item, dict):
            raise AlpacaDataError("R8 data manifest item must be an object")
        path = root / DATA_DIR / str(item.get("output_path") or "")
        if item.get("output_sha256") != _sha256_file(path):
            raise AlpacaDataError(f"R8 data item hash mismatch: {path}")
        quality = item.get("quality")
        if not isinstance(quality, dict) or quality.get("status") != "complete":
            raise AlpacaDataError(f"R8 data item quality is not complete: {path}")
    return manifest


def _manifest_item(
    manifest: dict[str, Any],
    symbol: str,
    timeframe: str,
    adjustment: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in manifest["items"]
        if item.get("symbol") == symbol
        and item.get("timeframe") == timeframe
        and item.get("adjustment") == adjustment
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one manifest item for {symbol} {timeframe} {adjustment}")
    return matches[0]


def _artifact_bindings(root: Path) -> dict[str, dict[str, str]]:
    paths = {
        "fixed_candidate": root / ITERATION_DIR / "fixed-candidate-contract.json",
        "data_contract": root / ITERATION_DIR / "data-contract.json",
        "cost_contract": root / ITERATION_DIR / "cost-contract.json",
        "holdout_contract": root / ITERATION_DIR / "holdout-contract.json",
        "cumulative_trial_contract": root / ITERATION_DIR / "cumulative-trial-contract.json",
        "evaluation_gates": root / ITERATION_DIR / "evaluation-gates.json",
        "knowledge_assessment": root / ITERATION_DIR / "knowledge-assessment.json",
    }
    return {
        name: {"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path)}
        for name, path in paths.items()
    }


def _session_dates(frame: pd.DataFrame) -> pd.Series:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return timestamps.dt.tz_convert(NEW_YORK).dt.date.astype(str)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_finite_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")


def _index_value(index: Any) -> str:
    return index.isoformat() if hasattr(index, "isoformat") else str(index)


def _render_markdown(payload: dict[str, Any]) -> str:
    primary = payload["cost_results"]["10bps"]
    failed = [check["name"] for check in payload["gate_checks"] if not check["pass"]]
    return "\n".join(
        [
            "# SPY Dual-Trend Core R8 Evaluation",
            "",
            f"- Decision: `{payload['decision']}`",
            f"- Historical robustness pass: `{payload['historical_robustness_pass']}`",
            f"- Workflow pass: `{payload['workflow_pass']}`",
            f"- Research pass: `{payload['research_pass']}`",
            f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
            f"- Paper-ready pass: `{payload['paper_ready_pass']}`",
            (
                f"- Evaluation window: `{payload['data_window']['evaluation_start']}` to "
                f"`{payload['data_window']['evaluation_end']}`"
            ),
            f"- Net return at 10 bps: `{primary['total_return_pct']:.6f}%`",
            f"- Annualized Sharpe at 10 bps: `{primary['annualized_sharpe']:.6f}`",
            f"- Maximum drawdown at 10 bps: `{primary['max_drawdown_pct']:.6f}%`",
            f"- Failed gates: `{failed or 'none'}`",
            "",
            (
                "Historical SIP is exposed robustness evidence, not an untouched lockbox. "
                "No broker order is authorized."
            ),
            "",
        ]
    )
