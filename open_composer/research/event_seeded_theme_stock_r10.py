from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import StrategySpec

ITER_ID = "mom_event_seeded_theme_stock_r10"
BENCHMARK_SYMBOLS = frozenset({"BIL", "QQQ", "QLD", "TQQQ", "SPY"})
REBALANCE_WEEKDAYS = frozenset({0, 2, 4})
MAXIMUM_PORTFOLIO_STOCKS = 5


@dataclass
class ThemeState:
    theme_id: str
    seed_symbol: str
    formed_position: int
    members: dict[str, int]
    seed_score: float
    state: str = "formation"
    confirmed_position: int | None = None
    last_expansion_position: int | None = None
    failure_streak: int = 0
    cooldown_until: int | None = None
    latest_metrics: dict[str, Any] = field(default_factory=dict)


def validate_r10_spec_pair(d01: StrategySpec, d02: StrategySpec) -> None:
    _validate_r10_d01_contract(d01)
    _validate_r10_d02_contract(d02)
    if d01.universe != d02.universe:
        raise ValueError("R10 deterministic candidates must share the same diagnostic universe")


def _validate_r10_common_contract(spec: StrategySpec, candidate_id: str) -> dict[str, Any]:
    notes = spec.notes.model_dump(mode="json")
    if notes.get("candidate_id") != candidate_id:
        raise ValueError(f"R10 candidate identity mismatch: {candidate_id}")
    if (
        spec.lifecycle != "draft"
        or spec.execution.mode != "manual_signal"
        or spec.execution.broker != "none"
        or notes.get("order_authority") is not False
        or notes.get("broker_writes") is not False
    ):
        raise ValueError(f"R10 broker-free contract mismatch: {candidate_id}")
    if spec.execution.signal_on != "bar_close" or spec.execution.fill_assumption != "next_bar_open":
        raise ValueError(f"R10 decision clock mismatch: {candidate_id}")
    if spec.portfolio.rebalance_schedule != "monday_wednesday_friday":
        raise ValueError(f"R10 rebalance schedule mismatch: {candidate_id}")
    return notes


def _validate_r10_d01_contract(d01: StrategySpec) -> None:
    notes = _validate_r10_common_contract(d01, "R10D01")
    discovery = notes.get("event_theme_discovery")
    if not isinstance(discovery, dict):
        raise ValueError("R10D01 event-theme discovery contract is missing")
    seed = discovery.get("seed")
    expansion = discovery.get("expansion")
    lifecycle = discovery.get("lifecycle")
    if not all(isinstance(value, dict) for value in (seed, expansion, lifecycle)):
        raise ValueError("R10D01 event-theme configuration is incomplete")
    expected_seed = {
        "residual_fit_sessions": 60,
        "minimum_positive_residual_z": 2.25,
        "minimum_relative_volume": 1.75,
        "alternative_positive_gap_z": 2.0,
        "alternative_relative_volume": 1.25,
        "maximum_new_seeds_per_session": 5,
    }
    if seed != expected_seed:
        raise ValueError("R10D01 event-seed contract changed")
    expected_expansion = {
        "link_window_sessions": 60,
        "minimum_positive_seed_lead_lag": 0.20,
        "minimum_residual_correlation": 0.25,
        "minimum_theme_members": 2,
        "maximum_theme_members": 8,
        "maximum_active_themes": 2,
        "semantic_edges": "forward_pit_only",
    }
    if expansion != expected_expansion:
        raise ValueError("R10D01 bounded-expansion contract changed")
    if (
        lifecycle.get("states")
        != ["formation", "confirmed", "expansion", "mature", "exhausted", "cooldown"]
        or lifecycle.get("minimum_confirmation_breadth") != 0.60
        or lifecycle.get("minimum_hold_sessions") != 3
        or lifecycle.get("maximum_member_age_sessions") != 12
        or lifecycle.get("maximum_theme_age_sessions") != 15
        or lifecycle.get("cooldown_sessions") != 5
    ):
        raise ValueError("R10D01 lifecycle contract changed")
    hysteresis = notes.get("hysteresis")
    if not isinstance(hysteresis, dict) or hysteresis != {
        "minimum_hold_sessions": 3,
        "maximum_member_age_sessions": 12,
        "exit_breadth_floor": 0.35,
        "maximum_member_substitutions_per_rebalance": 1,
        "target_drift_trigger": 0.10,
    }:
        raise ValueError("R10D01 portfolio-hysteresis contract changed")
    if (
        discovery.get("price_volume_mode") != "positive_event_seed_bounded_propagation"
        or discovery.get("parent_membership_source") != "daily_frozen_dynamic_parent"
        or discovery.get("semantic_labels_selectable") is not False
    ):
        raise ValueError("R10D01 dynamic-universe identity changed")

    allocation = notes.get("aggressive_allocation")
    if not isinstance(allocation, dict) or allocation != {
        "no_confirmed_theme": {"TQQQ": 1.0},
        "confirmed": {"TQQQ": 0.70, "theme_satellite": 0.30},
        "expansion": {"TQQQ": 0.60, "theme_satellite": 0.40},
        "mature": {"TQQQ": 0.80, "theme_satellite": 0.20},
        "exhausted": {"TQQQ": 1.0},
        "market_stress": {"QQQ": 0.50, "BIL": 0.50},
        "theme_replacement_requires_positive_relative_strength_vs_TQQQ": True,
    }:
        raise ValueError("R10D01 aggressive-allocation contract changed")


def _validate_r10_d02_contract(d02: StrategySpec) -> None:
    notes = _validate_r10_common_contract(d02, "R10D02")
    beta = notes.get("beta_state")
    if not isinstance(beta, dict) or beta != {
        "trend_windows_sessions": [40, 100],
        "drawdown_window_sessions": 20,
        "risk_on_weights": {"TQQQ": 1.0},
        "caution_weights": {"TQQQ": 0.70, "QQQ": 0.30},
        "stress_weights": {"QQQ": 0.50, "BIL": 0.50},
        "minimum_state_days": 5,
    }:
        raise ValueError("R10D02 aggressive-beta contract changed")


def compute_r10_d01_targets(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    _validate_r10_d01_contract(spec)
    candidates = validate_r10_runtime_panel(opens, closes, volumes, membership, spec)
    notes = spec.notes.model_dump(mode="json")
    discovery = notes["event_theme_discovery"]
    seed_contract = discovery["seed"]
    expansion_contract = discovery["expansion"]
    lifecycle_contract = discovery["lifecycle"]
    hysteresis_contract = notes["hysteresis"]
    returns = closes.pct_change(fill_method=None)
    gaps = opens / closes.shift(1) - 1.0
    gap_mean = gaps.rolling(60, min_periods=60).mean()
    gap_std = gaps.rolling(60, min_periods=60).std(ddof=0)
    gap_z = (gaps - gap_mean) / gap_std.replace(0.0, np.nan)
    prior_volume_mean = volumes.shift(1).rolling(20, min_periods=20).mean()
    relative_volume = volumes / prior_volume_mean.replace(0.0, np.nan)
    momentum = {window: closes / closes.shift(window) - 1.0 for window in (3, 5, 10, 20)}
    volatility = returns.rolling(20, min_periods=20).std(ddof=0)
    drawdown_10 = closes / closes.rolling(10, min_periods=10).max() - 1.0
    relative_strength = {
        window: momentum[window].sub(momentum[window]["TQQQ"], axis=0) for window in (5, 10)
    }
    qqq_features = _beta_features(closes["QQQ"])

    active_themes: dict[str, ThemeState] = {}
    seed_cooldowns: dict[str, int] = {}
    portfolio_entries: dict[str, int] = {}
    selected_symbols: list[str] = []
    previous_weights = _weights_for_columns(closes.columns, {"TQQQ": 1.0})
    beta_state: str | None = None
    beta_state_age = 0
    rows: list[dict[str, float]] = []
    records: list[dict[str, Any]] = []
    target_sessions: list[pd.Timestamp] = []

    warmup = max(100, int(seed_contract["residual_fit_sessions"]))
    for decision_position in range(warmup, len(closes.index) - 1):
        decision_session = closes.index[decision_position]
        execution_session = closes.index[decision_position + 1]
        residual_window = _residual_window(
            returns,
            candidates=candidates,
            benchmark_symbols=("SPY", "QQQ"),
            decision_position=decision_position,
            window=int(seed_contract["residual_fit_sessions"]),
        )
        eligible = _eligible_symbols(
            candidates,
            decision_session=decision_session,
            membership=membership,
            residual_window=residual_window,
            momentum=momentum,
            relative_strength=relative_strength,
            relative_volume=relative_volume,
            volatility=volatility,
            drawdown_10=drawdown_10,
        )
        residual_z = _latest_residual_z(residual_window)
        seed_rows = _event_seeds(
            eligible,
            decision_session=decision_session,
            returns=returns,
            residual_z=residual_z,
            gap_z=gap_z,
            relative_volume=relative_volume,
            minimum_residual_z=float(seed_contract["minimum_positive_residual_z"]),
            minimum_relative_volume=float(seed_contract["minimum_relative_volume"]),
            minimum_gap_z=float(seed_contract["alternative_positive_gap_z"]),
            alternative_relative_volume=float(seed_contract["alternative_relative_volume"]),
            maximum_seeds=int(seed_contract["maximum_new_seeds_per_session"]),
        )
        seed_symbols_today = {row["symbol"] for row in seed_rows}

        expired_theme_ids: list[str] = []
        for theme_id, theme in sorted(active_themes.items()):
            if theme.state == "cooldown":
                if theme.cooldown_until is not None and decision_position > theme.cooldown_until:
                    expired_theme_ids.append(theme_id)
                continue
            if theme.state == "exhausted":
                theme.state = "cooldown"
                theme.cooldown_until = decision_position + int(
                    lifecycle_contract["cooldown_sessions"]
                )
                seed_cooldowns[theme.seed_symbol] = theme.cooldown_until
                continue
            _advance_theme(
                theme,
                decision_position=decision_position,
                decision_session=decision_session,
                eligible=eligible,
                seed_symbols_today=seed_symbols_today,
                residual_window=residual_window,
                closes=closes,
                momentum=momentum,
                relative_strength=relative_strength,
                relative_volume=relative_volume,
                volatility=volatility,
                lifecycle_contract=lifecycle_contract,
                expansion_contract=expansion_contract,
            )
        for theme_id in expired_theme_ids:
            del active_themes[theme_id]
        seed_cooldowns = {
            symbol: until for symbol, until in seed_cooldowns.items() if decision_position <= until
        }

        occupied_symbols = {
            symbol
            for theme in active_themes.values()
            if theme.state not in {"exhausted", "cooldown"}
            for symbol in theme.members
        }
        live_theme_count = sum(
            theme.state not in {"exhausted", "cooldown"} for theme in active_themes.values()
        )
        for seed_row in seed_rows:
            if live_theme_count >= int(expansion_contract["maximum_active_themes"]):
                break
            seed_symbol = str(seed_row["symbol"])
            if seed_symbol in occupied_symbols or seed_symbol in seed_cooldowns:
                continue
            linked = _linked_members(
                seed_symbol,
                eligible=eligible,
                residual_window=residual_window,
                momentum=momentum,
                relative_strength=relative_strength,
                decision_session=decision_session,
                minimum_lead_lag=float(expansion_contract["minimum_positive_seed_lead_lag"]),
                minimum_correlation=float(expansion_contract["minimum_residual_correlation"]),
                maximum_members=int(expansion_contract["maximum_theme_members"]),
            )
            if len(linked) < int(expansion_contract["minimum_theme_members"]):
                continue
            theme_id = _canonical_hash(
                {
                    "seed_symbol": seed_symbol,
                    "formation_session": decision_session.date().isoformat(),
                }
            )[:16]
            theme = ThemeState(
                theme_id=theme_id,
                seed_symbol=seed_symbol,
                formed_position=decision_position,
                members={symbol: decision_position for symbol in linked},
                seed_score=float(seed_row["seed_score"]),
                last_expansion_position=decision_position,
            )
            theme.latest_metrics = _theme_metrics(
                theme,
                decision_position=decision_position,
                decision_session=decision_session,
                residual_window=residual_window,
                closes=closes,
                momentum=momentum,
                relative_strength=relative_strength,
                relative_volume=relative_volume,
                volatility=volatility,
            )
            active_themes[theme_id] = theme
            occupied_symbols.update(linked)
            live_theme_count += 1

        desired_beta_state = _desired_beta_state(
            close=float(closes.at[decision_session, "QQQ"]),
            sma40=float(qqq_features["sma40"].at[decision_session]),
            sma100=float(qqq_features["sma100"].at[decision_session]),
            momentum20=float(qqq_features["momentum20"].at[decision_session]),
            drawdown20=float(qqq_features["drawdown20"].at[decision_session]),
        )
        beta_state, beta_state_age = _advance_beta_state(
            desired_beta_state,
            current=beta_state,
            state_age=beta_state_age,
            minimum_state_days=5,
        )
        is_rebalance = decision_session.weekday() in REBALANCE_WEEKDAYS
        forced_exits: list[str] = []
        allocation_state = "market_stress" if beta_state == "stress" else "no_confirmed_theme"
        if is_rebalance:
            if beta_state == "stress":
                selected_symbols = []
                portfolio_entries = {}
                weights = _weights_for_columns(closes.columns, {"QQQ": 0.50, "BIL": 0.50})
            else:
                tradable_themes = [
                    theme
                    for theme in active_themes.values()
                    if theme.state in {"confirmed", "expansion", "mature"}
                    and float(theme.latest_metrics.get("mean_relative_strength_5", -math.inf)) > 0
                ]
                tradable_themes.sort(
                    key=lambda theme: (
                        -float(theme.latest_metrics.get("theme_score", -math.inf)),
                        theme.theme_id,
                    )
                )
                desired_symbols, desired_scores = _desired_portfolio_members(
                    tradable_themes,
                    maximum_symbols=min(
                        MAXIMUM_PORTFOLIO_STOCKS,
                        max(int(spec.portfolio.max_symbols_per_day or 1) - 1, 0),
                    ),
                )
                selected_symbols, portfolio_entries, forced_exits = _apply_portfolio_hysteresis(
                    selected_symbols,
                    desired_symbols,
                    portfolio_entries=portfolio_entries,
                    membership=membership.loc[decision_session],
                    decision_position=decision_position,
                    minimum_hold_sessions=int(hysteresis_contract["minimum_hold_sessions"]),
                    maximum_substitutions=int(
                        hysteresis_contract["maximum_member_substitutions_per_rebalance"]
                    ),
                )
                if tradable_themes:
                    allocation_state = tradable_themes[0].state
                satellite_budget = {
                    "confirmed": 0.30,
                    "expansion": 0.40,
                    "mature": 0.20,
                }.get(allocation_state, 0.0)
                weights = _allocate_d01_weights(
                    closes.columns,
                    selected_symbols,
                    desired_scores=desired_scores,
                    volatility=volatility.loc[decision_session],
                    satellite_budget=satellite_budget,
                    maximum_stock_weight=float(notes["maximum_stock_weight"]),
                    maximum_theme_weight=float(notes["maximum_theme_weight"]),
                )
            previous_weights = weights
        else:
            weights = dict(previous_weights)

        theme_rows = [_serialize_theme(theme, closes.index) for theme in active_themes.values()]
        theme_rows.sort(key=lambda row: row["theme_id"])
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R10D01",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "is_rebalance_decision": is_rebalance,
            "eligible_symbol_count": len(eligible),
            "event_seeds": seed_rows,
            "themes": theme_rows,
            "desired_beta_state": desired_beta_state,
            "beta_state": beta_state,
            "beta_state_age": beta_state_age,
            "allocation_state": allocation_state,
            "selected_symbols": list(selected_symbols),
            "forced_exit_symbols": forced_exits,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        rows.append(weights)
        records.append(record)
        target_sessions.append(execution_session)

    if not rows:
        raise ValueError("R10D01 produced no complete targets")
    targets = pd.DataFrame(rows, index=pd.DatetimeIndex(target_sessions), columns=closes.columns)
    _validate_targets(targets, records, closes.index, candidate_id="R10D01")
    return targets, records


def compute_r10_d02_targets(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    _validate_r10_d02_contract(spec)
    validate_r10_runtime_panel(opens, closes, volumes, membership, spec)
    beta_contract = spec.notes.model_dump(mode="json").get("beta_state")
    if not isinstance(beta_contract, dict):
        raise ValueError("R10D02 beta-state contract is missing")
    features = _beta_features(closes["QQQ"])
    current_state: str | None = None
    state_age = 0
    previous_weights = _weights_for_columns(closes.columns, {"BIL": 1.0})
    rows: list[dict[str, float]] = []
    records: list[dict[str, Any]] = []
    target_sessions: list[pd.Timestamp] = []
    for decision_position in range(100, len(closes.index) - 1):
        decision_session = closes.index[decision_position]
        execution_session = closes.index[decision_position + 1]
        desired = _desired_beta_state(
            close=float(closes.at[decision_session, "QQQ"]),
            sma40=float(features["sma40"].at[decision_session]),
            sma100=float(features["sma100"].at[decision_session]),
            momentum20=float(features["momentum20"].at[decision_session]),
            drawdown20=float(features["drawdown20"].at[decision_session]),
        )
        current_state, state_age = _advance_beta_state(
            desired,
            current=current_state,
            state_age=state_age,
            minimum_state_days=int(beta_contract["minimum_state_days"]),
        )
        is_rebalance = decision_session.weekday() in REBALANCE_WEEKDAYS
        if is_rebalance:
            previous_weights = _weights_for_columns(
                closes.columns,
                beta_contract[f"{current_state}_weights"],
            )
        weights = dict(previous_weights)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R10D02",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "is_rebalance_decision": is_rebalance,
            "desired_state": desired,
            "state": current_state,
            "state_age": state_age,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        rows.append(weights)
        records.append(record)
        target_sessions.append(execution_session)
    if not rows:
        raise ValueError("R10D02 produced no complete targets")
    targets = pd.DataFrame(rows, index=pd.DatetimeIndex(target_sessions), columns=closes.columns)
    _validate_targets(targets, records, closes.index, candidate_id="R10D02")
    return targets, records


def validate_r10_runtime_panel(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[str, ...]:
    if closes.empty or closes.index.has_duplicates or not closes.index.is_monotonic_increasing:
        raise ValueError("R10 sessions must be non-empty, unique, and increasing")
    if not opens.index.equals(closes.index) or list(opens.columns) != list(closes.columns):
        raise ValueError("R10 open panel must exactly align with closes")
    if not volumes.index.equals(closes.index) or list(volumes.columns) != list(closes.columns):
        raise ValueError("R10 volume panel must exactly align with closes")
    if not membership.index.equals(closes.index):
        raise ValueError("R10 membership sessions must align with prices")
    if membership.isna().any().any() or not all(
        pd.api.types.is_bool_dtype(dtype) for dtype in membership.dtypes
    ):
        raise ValueError("R10 membership must be complete boolean decision-time data")
    candidates = tuple(map(str, membership.columns))
    if (
        not candidates
        or len(candidates) != len(set(candidates))
        or set(candidates) & BENCHMARK_SYMBOLS
    ):
        raise ValueError("R10 membership candidates must be unique non-benchmark stocks")
    spec_benchmarks = tuple(symbol for symbol in spec.universe if symbol in BENCHMARK_SYMBOLS)
    if set(spec_benchmarks) != set(BENCHMARK_SYMBOLS):
        raise ValueError("R10 StrategySpec must declare every benchmark and reserve symbol")
    if list(closes.columns) != [*candidates, *spec_benchmarks]:
        raise ValueError(
            "R10 panel must contain the dynamic membership candidates followed by spec benchmarks"
        )
    for frame, label in ((opens, "open"), (closes, "close"), (volumes, "volume")):
        values = frame.to_numpy(dtype=float)
        if np.isinf(values).any():
            raise ValueError(f"R10 {label} panel contains infinite values")
    benchmark_columns = list(spec_benchmarks)
    if (
        not np.isfinite(opens[benchmark_columns].to_numpy(dtype=float)).all()
        or not np.isfinite(closes[benchmark_columns].to_numpy(dtype=float)).all()
        or not np.isfinite(volumes[benchmark_columns].to_numpy(dtype=float)).all()
        or (opens[benchmark_columns] <= 0).any().any()
        or (closes[benchmark_columns] <= 0).any().any()
        or (volumes[benchmark_columns] < 0).any().any()
    ):
        raise ValueError("R10 benchmark bars must be finite and valid on every session")
    for symbol in candidates:
        active = membership[symbol]
        if not active.any():
            continue
        if (
            not np.isfinite(opens.loc[active, symbol].to_numpy(dtype=float)).all()
            or not np.isfinite(closes.loc[active, symbol].to_numpy(dtype=float)).all()
            or not np.isfinite(volumes.loc[active, symbol].to_numpy(dtype=float)).all()
            or (opens.loc[active, symbol] <= 0).any()
            or (closes.loc[active, symbol] <= 0).any()
            or (volumes.loc[active, symbol] < 0).any()
        ):
            raise ValueError(f"R10 active membership bar is invalid: {symbol}")
    return candidates


def _residual_window(
    returns: pd.DataFrame,
    *,
    candidates: tuple[str, ...],
    benchmark_symbols: tuple[str, str],
    decision_position: int,
    window: int,
) -> pd.DataFrame:
    start = decision_position - window + 1
    if start < 1:
        return pd.DataFrame(index=returns.index[:0])
    sample = returns.iloc[start : decision_position + 1]
    regressors = sample.loc[:, list(benchmark_symbols)].to_numpy(dtype=float)
    if len(sample) != window or not np.isfinite(regressors).all():
        return pd.DataFrame(index=sample.index)
    complete = [
        symbol for symbol in candidates if np.isfinite(sample[symbol].to_numpy(dtype=float)).all()
    ]
    if not complete:
        return pd.DataFrame(index=sample.index)
    responses = sample.loc[:, complete].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(sample)), regressors])
    coefficients = np.linalg.lstsq(design, responses, rcond=None)[0]
    residuals = responses - design @ coefficients
    return pd.DataFrame(residuals, index=sample.index, columns=complete)


def _eligible_symbols(
    candidates: tuple[str, ...],
    *,
    decision_session: pd.Timestamp,
    membership: pd.DataFrame,
    residual_window: pd.DataFrame,
    momentum: dict[int, pd.DataFrame],
    relative_strength: dict[int, pd.DataFrame],
    relative_volume: pd.DataFrame,
    volatility: pd.DataFrame,
    drawdown_10: pd.DataFrame,
) -> tuple[str, ...]:
    eligible = []
    for symbol in candidates:
        if (
            not bool(membership.at[decision_session, symbol])
            or symbol not in residual_window.columns
        ):
            continue
        values = [
            *(momentum[window].at[decision_session, symbol] for window in (3, 5, 10, 20)),
            *(relative_strength[window].at[decision_session, symbol] for window in (5, 10)),
            relative_volume.at[decision_session, symbol],
            volatility.at[decision_session, symbol],
            drawdown_10.at[decision_session, symbol],
        ]
        if (
            all(pd.notna(value) and math.isfinite(float(value)) for value in values)
            and float(volatility.at[decision_session, symbol]) > 0
        ):
            eligible.append(symbol)
    return tuple(eligible)


def _latest_residual_z(residual_window: pd.DataFrame) -> dict[str, float]:
    values: dict[str, float] = {}
    for symbol in residual_window.columns:
        series = residual_window[symbol].to_numpy(dtype=float)
        scale = float(np.std(series, ddof=0))
        values[str(symbol)] = float((series[-1] - np.mean(series)) / scale) if scale > 0 else 0.0
    return values


def _event_seeds(
    eligible: tuple[str, ...],
    *,
    decision_session: pd.Timestamp,
    returns: pd.DataFrame,
    residual_z: dict[str, float],
    gap_z: pd.DataFrame,
    relative_volume: pd.DataFrame,
    minimum_residual_z: float,
    minimum_relative_volume: float,
    minimum_gap_z: float,
    alternative_relative_volume: float,
    maximum_seeds: int,
) -> list[dict[str, Any]]:
    rows = []
    for symbol in eligible:
        raw_return = float(returns.at[decision_session, symbol])
        residual_value = float(residual_z.get(symbol, -math.inf))
        gap_value = float(gap_z.at[decision_session, symbol])
        volume_value = float(relative_volume.at[decision_session, symbol])
        residual_path = (
            residual_value >= minimum_residual_z and volume_value >= minimum_relative_volume
        )
        gap_path = gap_value >= minimum_gap_z and volume_value >= alternative_relative_volume
        if raw_return <= 0 or not (residual_path or gap_path):
            continue
        seed_score = max(
            residual_value / minimum_residual_z,
            gap_value / minimum_gap_z,
        ) + 0.25 * math.log(max(volume_value, 1e-12))
        rows.append(
            {
                "symbol": symbol,
                "seed_score": float(seed_score),
                "residual_z_60": residual_value,
                "gap_z_60": gap_value,
                "relative_volume_20": volume_value,
                "raw_return_1": raw_return,
                "trigger": "residual" if residual_path else "gap",
            }
        )
    rows.sort(key=lambda row: (-float(row["seed_score"]), str(row["symbol"])))
    return rows[:maximum_seeds]


def _linked_members(
    seed_symbol: str,
    *,
    eligible: tuple[str, ...],
    residual_window: pd.DataFrame,
    momentum: dict[int, pd.DataFrame],
    relative_strength: dict[int, pd.DataFrame],
    decision_session: pd.Timestamp,
    minimum_lead_lag: float,
    minimum_correlation: float,
    maximum_members: int,
) -> list[str]:
    if seed_symbol not in residual_window.columns:
        return []
    seed = residual_window[seed_symbol].to_numpy(dtype=float)
    rows: list[tuple[str, float]] = []
    for symbol in eligible:
        if symbol == seed_symbol or symbol not in residual_window.columns:
            continue
        member = residual_window[symbol].to_numpy(dtype=float)
        lead_lag = _correlation(seed[:-1], member[1:])
        contemporaneous = _correlation(seed[-20:], member[-20:])
        if lead_lag < minimum_lead_lag and contemporaneous < minimum_correlation:
            continue
        momentum_3 = float(momentum[3].at[decision_session, symbol])
        residual_momentum_3 = float(member[-3:].sum())
        if momentum_3 <= 0 and residual_momentum_3 <= 0:
            continue
        link_score = (
            0.55 * max(lead_lag, 0.0)
            + 0.25 * max(contemporaneous, 0.0)
            + 0.10 * max(float(relative_strength[5].at[decision_session, symbol]), 0.0)
            + 0.10 * max(momentum_3, 0.0)
        )
        rows.append((symbol, float(link_score)))
    rows.sort(key=lambda row: (-row[1], row[0]))
    return [seed_symbol, *[symbol for symbol, _score in rows[: maximum_members - 1]]]


def _advance_theme(
    theme: ThemeState,
    *,
    decision_position: int,
    decision_session: pd.Timestamp,
    eligible: tuple[str, ...],
    seed_symbols_today: set[str],
    residual_window: pd.DataFrame,
    closes: pd.DataFrame,
    momentum: dict[int, pd.DataFrame],
    relative_strength: dict[int, pd.DataFrame],
    relative_volume: pd.DataFrame,
    volatility: pd.DataFrame,
    lifecycle_contract: dict[str, Any],
    expansion_contract: dict[str, Any],
) -> None:
    maximum_member_age = int(lifecycle_contract["maximum_member_age_sessions"])
    minimum_hold = int(lifecycle_contract["minimum_hold_sessions"])
    eligible_set = set(eligible)
    removed = [
        symbol
        for symbol, entry_position in theme.members.items()
        if symbol not in eligible_set
        or (
            decision_position - entry_position > maximum_member_age
            and decision_position - entry_position >= minimum_hold
        )
    ]
    for symbol in removed:
        theme.members.pop(symbol, None)
    if theme.seed_symbol not in eligible_set or theme.seed_symbol not in theme.members:
        theme.state = "exhausted"
        theme.latest_metrics = {"reason": "seed_ineligible_or_expired"}
        return

    linked = _linked_members(
        theme.seed_symbol,
        eligible=eligible,
        residual_window=residual_window,
        momentum=momentum,
        relative_strength=relative_strength,
        decision_session=decision_session,
        minimum_lead_lag=float(expansion_contract["minimum_positive_seed_lead_lag"]),
        minimum_correlation=float(expansion_contract["minimum_residual_correlation"]),
        maximum_members=int(expansion_contract["maximum_theme_members"]),
    )
    added = []
    for symbol in linked:
        if len(theme.members) >= int(expansion_contract["maximum_theme_members"]):
            break
        if symbol not in theme.members:
            theme.members[symbol] = decision_position
            added.append(symbol)
    post_confirmation_seed = bool(
        theme.confirmed_position is not None
        and (set(theme.members) & seed_symbols_today) - {theme.seed_symbol}
    )
    if added or post_confirmation_seed:
        theme.last_expansion_position = decision_position

    metrics = _theme_metrics(
        theme,
        decision_position=decision_position,
        decision_session=decision_session,
        residual_window=residual_window,
        closes=closes,
        momentum=momentum,
        relative_strength=relative_strength,
        relative_volume=relative_volume,
        volatility=volatility,
    )
    metrics["added_symbols"] = added
    theme.latest_metrics = metrics
    age = decision_position - theme.formed_position
    confirmation_ok = (
        len(theme.members) >= int(expansion_contract["minimum_theme_members"])
        and float(metrics["breadth_3"]) >= float(lifecycle_contract["minimum_confirmation_breadth"])
        and float(metrics["mean_relative_strength_5"]) > 0
        and not bool(metrics["seed_reversal"])
    )
    theme.failure_streak = 0 if confirmation_ok else theme.failure_streak + 1
    if age >= int(lifecycle_contract["maximum_theme_age_sessions"]):
        theme.state = "exhausted"
        return
    if theme.state == "formation":
        if age >= 1 and confirmation_ok:
            theme.state = "confirmed"
            theme.confirmed_position = decision_position
        elif age >= 3 and not confirmation_ok:
            theme.state = "exhausted"
        return
    if theme.failure_streak >= 2 or bool(metrics["seed_reversal"]):
        theme.state = "exhausted"
        return
    if (
        theme.confirmed_position is not None
        and (added or post_confirmation_seed)
        and decision_position > theme.confirmed_position
    ):
        theme.state = "expansion"
        return
    if age >= 8 or (
        theme.state == "expansion"
        and theme.last_expansion_position is not None
        and decision_position - theme.last_expansion_position >= 3
    ):
        theme.state = "mature"


def _theme_metrics(
    theme: ThemeState,
    *,
    decision_position: int,
    decision_session: pd.Timestamp,
    residual_window: pd.DataFrame,
    closes: pd.DataFrame,
    momentum: dict[int, pd.DataFrame],
    relative_strength: dict[int, pd.DataFrame],
    relative_volume: pd.DataFrame,
    volatility: pd.DataFrame,
) -> dict[str, Any]:
    members = [symbol for symbol in sorted(theme.members) if symbol in residual_window.columns]
    if not members:
        return {
            "age_sessions": decision_position - theme.formed_position,
            "breadth_3": 0.0,
            "mean_relative_strength_5": -1.0,
            "seed_reversal": True,
            "theme_score": -1.0,
            "member_scores": {},
        }
    residual_momentum_3 = {
        symbol: float(residual_window[symbol].iloc[-3:].sum()) for symbol in members
    }
    formation_session = closes.index[theme.formed_position]
    retention = {
        symbol: float(
            closes.at[decision_session, symbol] / closes.at[formation_session, symbol] - 1.0
        )
        for symbol in members
    }
    feature_values = {
        "retention": retention,
        "residual_3": residual_momentum_3,
        "momentum_5": {
            symbol: float(momentum[5].at[decision_session, symbol]) for symbol in members
        },
        "momentum_10": {
            symbol: float(momentum[10].at[decision_session, symbol]) for symbol in members
        },
        "rs_5": {
            symbol: float(relative_strength[5].at[decision_session, symbol]) for symbol in members
        },
        "rs_10": {
            symbol: float(relative_strength[10].at[decision_session, symbol]) for symbol in members
        },
        "volume": {
            symbol: float(relative_volume.at[decision_session, symbol]) for symbol in members
        },
        "inverse_volatility": {
            symbol: 1.0 / float(volatility.at[decision_session, symbol]) for symbol in members
        },
    }
    ranks = {name: _percentile_rank(values) for name, values in feature_values.items()}
    weights = {
        "retention": 0.20,
        "residual_3": 0.20,
        "momentum_5": 0.15,
        "momentum_10": 0.15,
        "rs_5": 0.10,
        "rs_10": 0.10,
        "volume": 0.05,
        "inverse_volatility": 0.05,
    }
    member_scores = {
        symbol: float(math.fsum(weights[name] * ranks[name][symbol] for name in weights))
        for symbol in members
    }
    breadth = float(
        np.mean([float(momentum[3].at[decision_session, symbol] > 0) for symbol in members])
    )
    mean_rs5 = float(
        np.mean([relative_strength[5].at[decision_session, symbol] for symbol in members])
    )
    seed_reversal = bool(
        float(momentum[3].at[decision_session, theme.seed_symbol]) < 0
        and residual_momentum_3.get(theme.seed_symbol, -math.inf) < 0
    )
    theme_score = float(
        np.mean(list(member_scores.values()))
        + 0.15 * breadth
        + 0.10 * max(mean_rs5, -0.10)
        + 0.05 * theme.seed_score
    )
    return {
        "age_sessions": decision_position - theme.formed_position,
        "breadth_3": breadth,
        "mean_relative_strength_5": mean_rs5,
        "seed_reversal": seed_reversal,
        "theme_score": theme_score,
        "member_scores": member_scores,
    }


def _desired_portfolio_members(
    themes: list[ThemeState], *, maximum_symbols: int
) -> tuple[list[str], dict[str, float]]:
    scores: dict[str, float] = {}
    for theme in themes:
        for symbol, score in theme.latest_metrics.get("member_scores", {}).items():
            scores[symbol] = max(float(score), scores.get(symbol, -math.inf))
    desired = sorted(scores, key=lambda symbol: (-scores[symbol], symbol))[:maximum_symbols]
    return desired, scores


def _apply_portfolio_hysteresis(
    current: list[str],
    desired: list[str],
    *,
    portfolio_entries: dict[str, int],
    membership: pd.Series,
    decision_position: int,
    minimum_hold_sessions: int,
    maximum_substitutions: int,
) -> tuple[list[str], dict[str, int], list[str]]:
    forced = sorted(symbol for symbol in current if not bool(membership.get(symbol, False)))
    surviving = [symbol for symbol in current if symbol not in forced]
    if not current:
        selected = list(desired)
    else:
        mandatory = [
            symbol
            for symbol in surviving
            if decision_position - int(portfolio_entries.get(symbol, decision_position))
            < minimum_hold_sessions
        ]
        removable = [
            symbol for symbol in surviving if symbol not in desired and symbol not in mandatory
        ]
        removed = set(removable[:maximum_substitutions])
        selected = [symbol for symbol in surviving if symbol not in removed]
        available = [symbol for symbol in desired if symbol not in selected]
        addition_limit = maximum_substitutions + len(forced)
        for symbol in available[:addition_limit]:
            selected.append(symbol)
        target_size = max(len(desired), len(mandatory))
        if len(selected) > target_size:
            protected = set(mandatory)
            trim_candidates = [symbol for symbol in reversed(selected) if symbol not in protected]
            while len(selected) > target_size and trim_candidates:
                selected.remove(trim_candidates.pop(0))
    selected = [symbol for symbol in selected if bool(membership.get(symbol, False))]
    selected = sorted(
        dict.fromkeys(selected),
        key=lambda symbol: desired.index(symbol) if symbol in desired else len(desired),
    )
    updated_entries = {
        symbol: int(portfolio_entries.get(symbol, decision_position)) for symbol in selected
    }
    return selected, updated_entries, forced


def _allocate_d01_weights(
    columns: pd.Index,
    selected: list[str],
    *,
    desired_scores: dict[str, float],
    volatility: pd.Series,
    satellite_budget: float,
    maximum_stock_weight: float,
    maximum_theme_weight: float,
) -> dict[str, float]:
    budget = min(max(satellite_budget, 0.0), maximum_theme_weight)
    weights = {str(symbol): 0.0 for symbol in columns}
    if selected and budget > 0:
        raw = {
            symbol: max(float(desired_scores.get(symbol, 0.0)), 0.01)
            / max(float(volatility[symbol]), 1e-8)
            for symbol in selected
        }
        stock_weights = _capped_proportional_weights(
            raw,
            budget=budget,
            cap=maximum_stock_weight,
        )
        for symbol, value in stock_weights.items():
            weights[symbol] = value
    stock_total = math.fsum(weights[symbol] for symbol in selected)
    weights["TQQQ"] = 1.0 - stock_total
    _normalize_weights(weights)
    return weights


def _capped_proportional_weights(
    raw: dict[str, float], *, budget: float, cap: float
) -> dict[str, float]:
    remaining = set(raw)
    result = {symbol: 0.0 for symbol in raw}
    remaining_budget = min(budget, cap * len(raw))
    while remaining and remaining_budget > 1e-15:
        denominator = math.fsum(raw[symbol] for symbol in remaining)
        if denominator <= 0:
            break
        capped = []
        for symbol in sorted(remaining):
            proposed = remaining_budget * raw[symbol] / denominator
            if proposed >= cap - result[symbol] - 1e-15:
                allocation = cap - result[symbol]
                result[symbol] += allocation
                remaining_budget -= allocation
                capped.append(symbol)
        if not capped:
            for symbol in remaining:
                result[symbol] += remaining_budget * raw[symbol] / denominator
            remaining_budget = 0.0
        else:
            remaining -= set(capped)
    return result


def _beta_features(qqq: pd.Series) -> dict[str, pd.Series]:
    return {
        "sma40": qqq.rolling(40, min_periods=40).mean(),
        "sma100": qqq.rolling(100, min_periods=100).mean(),
        "momentum20": qqq / qqq.shift(20) - 1.0,
        "drawdown20": qqq / qqq.rolling(20, min_periods=20).max() - 1.0,
    }


def _desired_beta_state(
    *, close: float, sma40: float, sma100: float, momentum20: float, drawdown20: float
) -> str:
    if not all(math.isfinite(value) for value in (close, sma40, sma100, momentum20, drawdown20)):
        return "stress"
    if drawdown20 <= -0.12 or (close < sma100 and momentum20 <= 0):
        return "stress"
    if close > sma40 > sma100 and momentum20 > 0:
        return "risk_on"
    return "caution"


def _advance_beta_state(
    desired: str,
    *,
    current: str | None,
    state_age: int,
    minimum_state_days: int,
) -> tuple[str, int]:
    if current is None:
        return desired, 1
    if desired == current:
        return current, state_age + 1
    if state_age >= minimum_state_days:
        return desired, 1
    return current, state_age + 1


def _serialize_theme(theme: ThemeState, sessions: pd.DatetimeIndex) -> dict[str, Any]:
    return {
        "theme_id": theme.theme_id,
        "seed_symbol": theme.seed_symbol,
        "formation_session": sessions[theme.formed_position].date().isoformat(),
        "state": theme.state,
        "members": sorted(theme.members),
        "confirmed_session": (
            sessions[theme.confirmed_position].date().isoformat()
            if theme.confirmed_position is not None
            else None
        ),
        "cooldown_until_session": (
            sessions[min(theme.cooldown_until, len(sessions) - 1)].date().isoformat()
            if theme.cooldown_until is not None
            else None
        ),
        **theme.latest_metrics,
    }


def _weights_for_columns(columns: pd.Index, allocation: dict[str, float]) -> dict[str, float]:
    weights = {str(symbol): 0.0 for symbol in columns}
    for symbol, value in allocation.items():
        if symbol not in weights:
            raise ValueError(f"R10 allocation symbol is missing from panel: {symbol}")
        weights[symbol] = float(value)
    _normalize_weights(weights)
    return weights


def _normalize_weights(weights: dict[str, float]) -> None:
    if not all(math.isfinite(value) and value >= -1e-12 for value in weights.values()):
        raise ValueError("R10 target weights must be finite and nonnegative")
    total = math.fsum(weights.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("R10 target allocation is empty")
    if abs(total - 1.0) > 1e-10:
        if "BIL" not in weights or total > 1.0 + 1e-10:
            raise ValueError("R10 target allocation does not sum to one")
        weights["BIL"] += 1.0 - total


def _percentile_rank(values: dict[str, float]) -> dict[str, float]:
    if not values or not all(math.isfinite(value) for value in values.values()):
        raise ValueError("R10 rank values must be finite")
    ranked = sorted(values, key=lambda symbol: (-values[symbol], symbol))
    denominator = max(len(ranked) - 1, 1)
    return {symbol: 1.0 - index / denominator for index, symbol in enumerate(ranked)}


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 3 or len(left) != len(right):
        return 0.0
    left_scale = float(np.std(left, ddof=0))
    right_scale = float(np.std(right, ddof=0))
    if left_scale <= 0 or right_scale <= 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _validate_targets(
    targets: pd.DataFrame,
    records: list[dict[str, Any]],
    sessions: pd.DatetimeIndex,
    *,
    candidate_id: str,
) -> None:
    if targets.index.has_duplicates or not targets.index.is_monotonic_increasing:
        raise ValueError(f"{candidate_id} target sessions must be unique and increasing")
    if not np.isfinite(targets.to_numpy(dtype=float)).all() or (targets < -1e-12).any().any():
        raise ValueError(f"{candidate_id} targets must be finite and nonnegative")
    if not np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0):
        raise ValueError(f"{candidate_id} targets must sum to one")
    positions = {session: position for position, session in enumerate(sessions)}
    if len(records) != len(targets):
        raise ValueError(f"{candidate_id} target/record count mismatch")
    for record in records:
        decision = pd.Timestamp(record["decision_session"])
        execution = pd.Timestamp(record["execution_session"])
        if positions[execution] != positions[decision] + 1:
            raise ValueError(f"{candidate_id} target is not next-session executable")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
