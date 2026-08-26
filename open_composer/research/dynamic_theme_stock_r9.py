from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import StrategySpec

ITER_ID = "mom_dynamic_theme_stock_r9"
BENCHMARK_SYMBOLS = frozenset({"BIL", "QQQ", "QLD", "TQQQ", "SPY"})
MINIMUM_THEME_BREADTH = 0.40
TOP_MEMBERS_PER_THEME = 3


@dataclass(frozen=True)
class ThemeLayerConfig:
    name: str
    edge_window_sessions: int
    momentum_sessions: tuple[int, int]
    mutual_neighbor_k: int
    minimum_edge_correlation: float


@dataclass(frozen=True)
class ThemeSnapshot:
    themes: tuple[dict[str, Any], ...]
    member_scores: dict[str, float]
    member_theme: dict[str, tuple[str, ...]]
    leadership: dict[str, float]


def validate_r9_spec_pair(d01: StrategySpec, d02: StrategySpec) -> None:
    for candidate_id, spec in {"R9D01": d01, "R9D02": d02}.items():
        notes = spec.notes.model_dump(mode="json")
        if notes.get("candidate_id") != candidate_id:
            raise ValueError(f"R9 candidate identity mismatch: {candidate_id}")
        if (
            spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
        ):
            raise ValueError(f"R9 broker-free contract mismatch: {candidate_id}")
        discovery = notes.get("theme_discovery")
        if not isinstance(discovery, dict):
            raise ValueError(f"R9 theme discovery contract missing: {candidate_id}")
        if (
            discovery.get("price_volume_mode") != "multiscale_residual_lead_lag_communities"
            or discovery.get("parent_membership_source") != "daily_frozen_dynamic_parent"
            or discovery.get("semantic_labels_selectable") is not False
            or discovery.get("membership_recomputed") != "every_decision_session"
        ):
            raise ValueError(f"R9 dynamic theme identity mismatch: {candidate_id}")
        _theme_configs(discovery)
    if d01.universe != d02.universe:
        raise ValueError("R9 deterministic candidates must share the same allowed universe")
    if len(_candidate_symbols(d01)) != 62:
        raise ValueError("R9 diagnostic contract requires exactly 62 stock candidates")
    route = d02.notes.model_dump(mode="json").get("aggressive_beta_core")
    if not isinstance(route, dict):
        raise ValueError("R9D02 aggressive beta contract is missing")
    if route.get("risk_on_weights") != {"TQQQ": 0.75, "theme_satellite": 0.25}:
        raise ValueError("R9D02 risk-on weights changed")
    if float(d02.portfolio.max_symbol_weight or 0.0) != 0.75:
        raise ValueError("R9D02 TQQQ capacity does not match its route contract")


def compute_r9_d01_targets(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    candidates = validate_r9_runtime_panel(closes, volumes, membership, spec)
    discovery = spec.notes.model_dump(mode="json").get("theme_discovery")
    if not isinstance(discovery, dict):
        raise ValueError("R9D01 theme discovery contract is missing")
    fast, propagation = _theme_configs(discovery)
    residual_fit = int(discovery["residual_fit_window_sessions"])
    minimum_members = int(discovery["minimum_theme_members"])
    maximum_members = int(discovery["maximum_theme_members"])
    top_themes = int(discovery["top_themes"])
    hysteresis = spec.notes.model_dump(mode="json").get("hysteresis")
    if not isinstance(hysteresis, dict):
        raise ValueError("R9D01 hysteresis contract is missing")
    minimum_hold = int(hysteresis["minimum_hold_sessions"])
    entry_margin = float(hysteresis["entry_score_margin"])
    maximum_changes = int(hysteresis["max_daily_symbol_changes"])
    maximum_symbols = int(spec.portfolio.max_symbols_per_day or 0)
    if maximum_symbols < 1:
        raise ValueError("R9D01 maximum symbol count is missing")

    returns = closes.pct_change(fill_method=None)
    residuals = rolling_residual_returns(
        returns,
        candidate_symbols=candidates,
        benchmark_symbols=("SPY", "QQQ"),
        window=residual_fit,
    )
    momentum = {window: closes / closes.shift(window) - 1.0 for window in (3, 5, 10, 20)}
    residual_momentum = {
        window: residuals.rolling(window, min_periods=window).sum() for window in (3, 5)
    }
    volume_surprise = volumes / volumes.rolling(10, min_periods=10).mean() - 1.0
    volatility = returns.rolling(20, min_periods=20).std(ddof=0)
    drawdown = closes / closes.rolling(20, min_periods=20).max() - 1.0

    target_rows: list[dict[str, float]] = []
    target_sessions: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    active: dict[str, dict[str, Any]] = {}
    previous_themes: tuple[tuple[str, ...], ...] = ()
    warmup = residual_fit + max(fast.edge_window_sessions, propagation.edge_window_sessions)
    for decision_position in range(warmup, len(closes.index) - 1):
        decision_session = closes.index[decision_position]
        execution_session = closes.index[decision_position + 1]
        eligible = tuple(
            symbol
            for symbol in candidates
            if bool(membership.at[decision_session, symbol])
            and _features_are_finite(
                decision_session,
                symbol,
                momentum,
                volume_surprise,
                volatility,
                drawdown,
            )
        )
        if len(eligible) < minimum_members:
            weights = _reserve_weights(closes.columns)
            snapshot = ThemeSnapshot((), {}, {}, {})
            selected: list[str] = []
            mandatory: list[str] = []
        else:
            snapshot = discover_multiscale_themes(
                residuals=residuals,
                momentum=momentum,
                residual_momentum=residual_momentum,
                volume_surprise=volume_surprise,
                volatility=volatility,
                drawdown=drawdown,
                decision_position=decision_position,
                eligible_symbols=eligible,
                layers=(fast, propagation),
                minimum_members=minimum_members,
                maximum_members=maximum_members,
                top_themes=top_themes,
                previous_themes=previous_themes,
            )
            desired = _desired_members(snapshot, maximum_symbols=maximum_symbols)
            selected, mandatory = _apply_hysteresis(
                desired,
                snapshot=snapshot,
                active=active,
                membership=membership.loc[decision_session],
                execution_position=decision_position + 1,
                minimum_hold=minimum_hold,
                entry_margin=entry_margin,
                maximum_changes=maximum_changes,
                maximum_symbols=maximum_symbols,
            )
            active = _updated_active_state(
                selected,
                snapshot=snapshot,
                active=active,
                execution_position=decision_position + 1,
            )
            weights = _stock_weights(
                columns=closes.columns,
                selected=selected,
                active=active,
                scores=snapshot.member_scores,
                volatility=volatility.loc[decision_session],
                maximum_symbol_weight=float(spec.portfolio.max_symbol_weight or 0.0),
                maximum_theme_weight=float(
                    spec.notes.model_dump(mode="json")["maximum_theme_weight"]
                ),
            )
            previous_themes = tuple(tuple(theme["members"]) for theme in snapshot.themes)

        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R9D01",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "eligible_symbol_count": len(eligible),
            "themes": list(snapshot.themes),
            "selected_symbols": selected,
            "mandatory_hold_symbols": mandatory,
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        target_rows.append(weights)
        target_sessions.append(execution_session)
        records.append(record)
    if not target_rows:
        raise ValueError("R9D01 produced no complete targets")
    targets = pd.DataFrame(
        target_rows,
        index=pd.DatetimeIndex(target_sessions),
        columns=closes.columns,
    )
    _validate_targets(targets, records, closes.index, candidate_id="R9D01")
    return targets, records


def compute_r9_d02_targets(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    d01_spec: StrategySpec,
    d02_spec: StrategySpec,
    *,
    d01_result: tuple[pd.DataFrame, list[dict[str, Any]]] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    validate_r9_spec_pair(d01_spec, d02_spec)
    runtime_candidates = validate_r9_runtime_panel(closes, volumes, membership, d01_spec)
    if d01_result is None:
        d01_targets, d01_records = compute_r9_d01_targets(closes, volumes, membership, d01_spec)
    else:
        d01_targets, d01_records = d01_result
        if list(d01_targets.columns) != list(closes.columns):
            raise ValueError("R9D02 cached D01 target columns do not match the runtime panel")
        _validate_targets(
            d01_targets,
            d01_records,
            closes.index,
            candidate_id="R9D01",
        )
    d01_by_session = {pd.Timestamp(row["execution_session"]): row for row in d01_records}
    route = d02_spec.notes.model_dump(mode="json")["aggressive_beta_core"]
    minimum_state_days = int(route["minimum_state_days"])
    qqq = closes["QQQ"]
    sma40 = qqq.rolling(40, min_periods=40).mean()
    sma60 = qqq.rolling(60, min_periods=60).mean()
    momentum20 = qqq / qqq.shift(20) - 1.0
    drawdown20 = qqq / qqq.rolling(20, min_periods=20).max() - 1.0
    current_state: str | None = None
    state_age = 0
    rows: list[dict[str, float]] = []
    records: list[dict[str, Any]] = []
    for execution_session, d01_weights in d01_targets.iterrows():
        execution_position = closes.index.get_loc(execution_session)
        decision_session = closes.index[execution_position - 1]
        desired_state = _desired_beta_state(
            close=float(qqq.at[decision_session]),
            sma40=float(sma40.at[decision_session]),
            sma60=float(sma60.at[decision_session]),
            momentum20=float(momentum20.at[decision_session]),
            drawdown20=float(drawdown20.at[decision_session]),
        )
        if current_state is None:
            current_state = desired_state
            state_age = 1
        elif desired_state == current_state:
            state_age += 1
        elif state_age >= minimum_state_days:
            current_state = desired_state
            state_age = 1
        else:
            state_age += 1
        route_weights = route[f"{current_state}_weights"]
        weights = {str(symbol): 0.0 for symbol in closes.columns}
        satellite_budget = float(route_weights.get("theme_satellite", 0.0))
        for symbol, value in route_weights.items():
            if symbol != "theme_satellite":
                weights[str(symbol)] += float(value)
        stock_weights = {
            symbol: float(d01_weights[symbol])
            for symbol in runtime_candidates
            if float(d01_weights[symbol]) > 0
        }
        stock_total = math.fsum(stock_weights.values())
        if satellite_budget > 0 and stock_total > 0:
            for symbol, value in stock_weights.items():
                weights[symbol] += satellite_budget * value / stock_total
        else:
            weights["BIL"] += satellite_budget
        _normalize_roundoff(weights)
        d01_record = d01_by_session[execution_session]
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "R9D02",
            "decision_session": decision_session.date().isoformat(),
            "execution_session": execution_session.date().isoformat(),
            "desired_state": desired_state,
            "state": current_state,
            "state_age": state_age,
            "momentum_20": float(momentum20.at[decision_session]),
            "drawdown_20": float(drawdown20.at[decision_session]),
            "selected_theme_symbols": d01_record["selected_symbols"],
            "weights": weights,
        }
        record["target_sha256"] = _canonical_hash(weights)
        rows.append(weights)
        records.append(record)
    targets = pd.DataFrame(rows, index=d01_targets.index, columns=closes.columns)
    _validate_targets(targets, records, closes.index, candidate_id="R9D02")
    return targets, records


def discover_multiscale_themes(
    *,
    residuals: pd.DataFrame,
    momentum: dict[int, pd.DataFrame],
    residual_momentum: dict[int, pd.DataFrame],
    volume_surprise: pd.DataFrame,
    volatility: pd.DataFrame,
    drawdown: pd.DataFrame,
    decision_position: int,
    eligible_symbols: tuple[str, ...],
    layers: tuple[ThemeLayerConfig, ThemeLayerConfig],
    minimum_members: int,
    maximum_members: int,
    top_themes: int,
    previous_themes: tuple[tuple[str, ...], ...] = (),
) -> ThemeSnapshot:
    decision_session = residuals.index[decision_position]
    eligible = list(eligible_symbols)
    feature_values = {
        "residual_3": residual_momentum[3].loc[decision_session, eligible],
        "residual_5": residual_momentum[5].loc[decision_session, eligible],
        "momentum_10": momentum[10].loc[decision_session, eligible],
        "momentum_20": momentum[20].loc[decision_session, eligible],
        "volume": volume_surprise.loc[decision_session, eligible],
        "inverse_volatility": 1.0 / volatility.loc[decision_session, eligible],
        "overheat": -(
            momentum[3].loc[decision_session, eligible]
            / (volatility.loc[decision_session, eligible] * math.sqrt(3.0))
        ),
        "drawdown": drawdown.loc[decision_session, eligible],
    }
    if any(
        not np.isfinite(values.to_numpy(dtype=float)).all() for values in feature_values.values()
    ):
        return ThemeSnapshot((), {}, {}, {})
    ranks = {name: cross_sectional_percentile(values) for name, values in feature_values.items()}

    theme_rows: list[dict[str, Any]] = []
    leadership_by_symbol = {symbol: 0.0 for symbol in eligible}
    for layer in layers:
        start = decision_position - layer.edge_window_sessions + 1
        sample = residuals.iloc[start : decision_position + 1].loc[:, eligible]
        if len(sample) != layer.edge_window_sessions or not np.isfinite(sample.to_numpy()).all():
            continue
        affinity, leadership = residual_affinity(sample)
        for symbol, value in leadership.items():
            leadership_by_symbol[symbol] = max(leadership_by_symbol[symbol], value)
        components = mutual_knn_components(
            affinity,
            k=layer.mutual_neighbor_k,
            threshold=layer.minimum_edge_correlation,
            minimum_members=minimum_members,
            maximum_members=maximum_members,
        )
        short_window, long_window = layer.momentum_sessions
        for members in components:
            breadth = float(
                np.mean(
                    [
                        float(momentum[window].at[decision_session, symbol] > 0)
                        for symbol in members
                        for window in (short_window, long_window)
                    ]
                )
            )
            raw_momentum = float(
                np.mean(
                    [
                        momentum[window].at[decision_session, symbol]
                        for symbol in members
                        for window in (short_window, long_window)
                    ]
                )
            )
            if breadth < MINIMUM_THEME_BREADTH or raw_momentum <= 0:
                continue
            cohesion = _component_cohesion(affinity, members)
            persistence = max((_jaccard(members, prior) for prior in previous_themes), default=0.0)
            if layer.name == "fast":
                score = (
                    0.30 * np.mean([ranks["residual_3"][symbol] for symbol in members])
                    + 0.25 * np.mean([ranks["residual_5"][symbol] for symbol in members])
                    + 0.15 * np.mean([ranks["volume"][symbol] for symbol in members])
                    + 0.15 * breadth
                    + 0.15 * cohesion
                )
            else:
                score = (
                    0.25 * np.mean([ranks["momentum_10"][symbol] for symbol in members])
                    + 0.25 * np.mean([ranks["momentum_20"][symbol] for symbol in members])
                    + 0.20 * breadth
                    + 0.15 * persistence
                    + 0.15 * cohesion
                )
            theme_rows.append(
                {
                    "theme_id": _canonical_hash({"layer": layer.name, "members": list(members)})[
                        :16
                    ],
                    "layer": layer.name,
                    "members": list(members),
                    "score": float(score),
                    "breadth": breadth,
                    "raw_momentum": raw_momentum,
                    "cohesion": cohesion,
                    "persistence": persistence,
                }
            )
    theme_rows.sort(
        key=lambda row: (-float(row["score"]), str(row["layer"]), tuple(row["members"]))
    )
    selected_themes: list[dict[str, Any]] = []
    for row in theme_rows:
        members = tuple(row["members"])
        if any(_jaccard(members, tuple(prior["members"])) > 0.70 for prior in selected_themes):
            continue
        selected_themes.append(row)
        if len(selected_themes) >= top_themes:
            break

    leadership_rank = cross_sectional_percentile(pd.Series(leadership_by_symbol, dtype=float))
    member_scores: dict[str, float] = {}
    member_theme: dict[str, tuple[str, ...]] = {}
    for theme in selected_themes:
        members = tuple(str(symbol) for symbol in theme["members"])
        for symbol in members:
            score = (
                0.15 * ranks["residual_3"][symbol]
                + 0.20 * ranks["residual_5"][symbol]
                + 0.20 * ranks["momentum_10"][symbol]
                + 0.15 * ranks["momentum_20"][symbol]
                + 0.10 * leadership_rank[symbol]
                + 0.10 * ranks["volume"][symbol]
                + 0.05 * ranks["inverse_volatility"][symbol]
                + 0.05 * ranks["overheat"][symbol]
            )
            if score > member_scores.get(symbol, -math.inf):
                member_scores[symbol] = float(score)
                member_theme[symbol] = members
    return ThemeSnapshot(tuple(selected_themes), member_scores, member_theme, leadership_by_symbol)


def rolling_residual_returns(
    returns: pd.DataFrame,
    *,
    candidate_symbols: tuple[str, ...],
    benchmark_symbols: tuple[str, str],
    window: int,
) -> pd.DataFrame:
    required = {*candidate_symbols, *benchmark_symbols}
    if not required.issubset(returns.columns):
        raise ValueError("R9 residual panel is missing required symbols")
    output = pd.DataFrame(np.nan, index=returns.index, columns=list(candidate_symbols), dtype=float)
    for position in range(window, len(returns)):
        sample = returns.iloc[position - window + 1 : position + 1]
        regressors = sample.loc[:, list(benchmark_symbols)].to_numpy(dtype=float)
        responses = sample.loc[:, list(candidate_symbols)].to_numpy(dtype=float)
        if not np.isfinite(regressors).all() or not np.isfinite(responses).all():
            continue
        design = np.column_stack([np.ones(len(sample)), regressors])
        coefficients = np.linalg.lstsq(design, responses, rcond=None)[0]
        output.iloc[position] = responses[-1] - design[-1] @ coefficients
    return output


def residual_affinity(sample: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    symbols = list(map(str, sample.columns))
    values = sample.to_numpy(dtype=float)
    contemporaneous = np.corrcoef(values, rowvar=False)
    contemporaneous = np.nan_to_num(contemporaneous, nan=0.0, posinf=0.0, neginf=0.0)
    lagged_left = _standardize_columns(values[:-1])
    lagged_right = _standardize_columns(values[1:])
    lead_lag = lagged_left.T @ lagged_right / len(lagged_left)
    lag_strength = np.maximum(np.maximum(lead_lag, lead_lag.T), 0.0)
    matrix = 0.70 * np.maximum(contemporaneous, 0.0) + 0.30 * lag_strength
    np.fill_diagonal(matrix, 1.0)
    affinity = pd.DataFrame(matrix, index=symbols, columns=symbols)
    positive_outgoing = np.maximum(lead_lag, 0.0)
    np.fill_diagonal(positive_outgoing, 0.0)
    denominator = max(len(symbols) - 1, 1)
    leadership = {
        symbol: float(positive_outgoing[index].sum() / denominator)
        for index, symbol in enumerate(symbols)
    }
    return affinity, leadership


def mutual_knn_components(
    affinity: pd.DataFrame,
    *,
    k: int,
    threshold: float,
    minimum_members: int,
    maximum_members: int,
) -> tuple[tuple[str, ...], ...]:
    if list(affinity.index) != list(affinity.columns):
        raise ValueError("R9 affinity index and columns must match")
    symbols = sorted(map(str, affinity.columns))
    values = affinity.loc[symbols, symbols].to_numpy(dtype=float, copy=False)
    neighbours: list[set[int]] = []
    for left_index, _symbol in enumerate(symbols):
        ranked = sorted(
            (
                right_index
                for right_index in range(len(symbols))
                if right_index != left_index
                and math.isfinite(float(values[left_index, right_index]))
                and float(values[left_index, right_index]) >= threshold
            ),
            key=lambda right_index: (
                -float(values[left_index, right_index]),
                symbols[right_index],
            ),
        )
        neighbours.append(set(ranked[:k]))
    adjacency = [set() for _ in symbols]
    for left_index, left_neighbours in enumerate(neighbours):
        for right_index in left_neighbours:
            if left_index in neighbours[right_index]:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)
    components: list[tuple[str, ...]] = []
    unseen = set(range(len(symbols)))
    while unseen:
        seed = min(unseen)
        stack = [seed]
        member_indices: set[int] = set()
        while stack:
            current = stack.pop()
            if current in member_indices:
                continue
            member_indices.add(current)
            stack.extend(sorted(adjacency[current] - member_indices, reverse=True))
        unseen -= member_indices
        members = tuple(symbols[index] for index in sorted(member_indices))
        if len(members) < minimum_members:
            continue
        components.extend(
            _bounded_component_groups(
                members,
                affinity,
                minimum_members=minimum_members,
                maximum_members=maximum_members,
            )
        )
    return tuple(sorted(components))


def cross_sectional_percentile(values: pd.Series) -> dict[str, float]:
    numeric = {str(symbol): float(value) for symbol, value in values.items()}
    if not numeric or not all(math.isfinite(value) for value in numeric.values()):
        raise ValueError("R9 cross-sectional rank requires finite values")
    ranked = sorted(numeric, key=lambda symbol: (-numeric[symbol], symbol))
    denominator = max(len(ranked) - 1, 1)
    return {symbol: 1.0 - index / denominator for index, symbol in enumerate(ranked)}


def _theme_configs(discovery: dict[str, Any]) -> tuple[ThemeLayerConfig, ThemeLayerConfig]:
    rows = []
    for key, name in (("fast_layer", "fast"), ("propagation_layer", "propagation")):
        raw = discovery.get(key)
        if not isinstance(raw, dict):
            raise ValueError(f"R9 theme layer is missing: {key}")
        momentum = tuple(map(int, raw.get("momentum_sessions") or ()))
        if len(momentum) != 2:
            raise ValueError(f"R9 theme momentum horizons are invalid: {key}")
        rows.append(
            ThemeLayerConfig(
                name=name,
                edge_window_sessions=int(raw["edge_window_sessions"]),
                momentum_sessions=(momentum[0], momentum[1]),
                mutual_neighbor_k=int(raw["mutual_neighbor_k"]),
                minimum_edge_correlation=float(raw["minimum_edge_correlation"]),
            )
        )
    if rows[0] != ThemeLayerConfig("fast", 10, (3, 5), 5, 0.35):
        raise ValueError("R9 fast theme layer changed")
    if rows[1] != ThemeLayerConfig("propagation", 20, (10, 20), 8, 0.30):
        raise ValueError("R9 propagation theme layer changed")
    return rows[0], rows[1]


def _candidate_symbols(spec: StrategySpec) -> tuple[str, ...]:
    return tuple(symbol for symbol in spec.universe if symbol not in BENCHMARK_SYMBOLS)


def validate_r9_runtime_panel(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[str, ...]:
    """Validate a decision-time panel and return its dynamic stock candidates."""
    _validate_inputs(closes, volumes, membership, spec)
    return tuple(map(str, membership.columns))


def _validate_inputs(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    membership: pd.DataFrame,
    spec: StrategySpec,
) -> None:
    spec_benchmarks = tuple(symbol for symbol in spec.universe if symbol in BENCHMARK_SYMBOLS)
    if set(spec_benchmarks) != set(BENCHMARK_SYMBOLS):
        raise ValueError("R9 StrategySpec must declare every benchmark and reserve symbol")
    if not all(isinstance(symbol, str) and symbol for symbol in membership.columns):
        raise ValueError("R9 membership symbols must be non-empty strings")
    candidates = list(map(str, membership.columns))
    if len(candidates) != len(set(candidates)) or set(candidates) & BENCHMARK_SYMBOLS:
        raise ValueError("R9 membership candidates must be unique non-benchmark stocks")
    expected_columns = [*candidates, *spec_benchmarks]
    if list(closes.columns) != expected_columns:
        raise ValueError(
            "R9 panel columns must contain the decision-time membership candidates "
            "followed by the StrategySpec benchmark symbols"
        )
    if closes.empty or closes.index.has_duplicates or not closes.index.is_monotonic_increasing:
        raise ValueError("R9 sessions must be non-empty, unique, and increasing")
    if not volumes.index.equals(closes.index) or list(volumes.columns) != list(closes.columns):
        raise ValueError("R9 volume panel must exactly align with prices")
    if not membership.index.equals(closes.index):
        raise ValueError("R9 membership must align with sessions and candidate stocks")
    if membership.isna().any().any():
        raise ValueError("R9 membership cannot contain missing values")
    if not all(pd.api.types.is_bool_dtype(dtype) for dtype in membership.dtypes):
        raise ValueError("R9 membership values must be boolean")
    for frame, label in ((closes, "close"), (volumes, "volume")):
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ValueError(f"R9 {label} panel contains nonfinite values")
    if (closes <= 0).any().any() or (volumes < 0).any().any():
        raise ValueError("R9 prices must be positive and volume nonnegative")


def _features_are_finite(
    session: pd.Timestamp,
    symbol: str,
    momentum: dict[int, pd.DataFrame],
    volume_surprise: pd.DataFrame,
    volatility: pd.DataFrame,
    drawdown: pd.DataFrame,
) -> bool:
    values = [
        *(momentum[window].at[session, symbol] for window in (3, 5, 10, 20)),
        volume_surprise.at[session, symbol],
        volatility.at[session, symbol],
        drawdown.at[session, symbol],
    ]
    return (
        all(pd.notna(value) and math.isfinite(float(value)) for value in values)
        and float(volatility.at[session, symbol]) > 0
    )


def _desired_members(snapshot: ThemeSnapshot, *, maximum_symbols: int) -> list[str]:
    desired: list[str] = []
    for theme in snapshot.themes:
        members = sorted(
            map(str, theme["members"]),
            key=lambda symbol: (-snapshot.member_scores[symbol], symbol),
        )
        for symbol in members[:TOP_MEMBERS_PER_THEME]:
            if symbol not in desired:
                desired.append(symbol)
                if len(desired) >= maximum_symbols:
                    return desired
    return desired


def _apply_hysteresis(
    desired: list[str],
    *,
    snapshot: ThemeSnapshot,
    active: dict[str, dict[str, Any]],
    membership: pd.Series,
    execution_position: int,
    minimum_hold: int,
    entry_margin: float,
    maximum_changes: int,
    maximum_symbols: int,
) -> tuple[list[str], list[str]]:
    mandatory = sorted(
        symbol
        for symbol, state in active.items()
        if bool(membership.get(symbol, False))
        and execution_position - int(state["entry_position"]) < minimum_hold
    )
    selected = mandatory[:maximum_symbols]
    current_scores = snapshot.member_scores
    challengers = [symbol for symbol in desired if symbol not in selected]
    for incumbent in sorted(active):
        if incumbent in selected or not bool(membership.get(incumbent, False)):
            continue
        if incumbent not in current_scores or len(selected) >= maximum_symbols:
            continue
        challenger_score = current_scores[challengers[0]] if challengers else -math.inf
        if current_scores[incumbent] + entry_margin >= challenger_score:
            selected.append(incumbent)
            challengers = [symbol for symbol in challengers if symbol != incumbent]
    addition_limit = maximum_symbols if not active else maximum_changes
    additions = 0
    for symbol in desired:
        if len(selected) >= maximum_symbols:
            break
        if symbol in selected:
            continue
        if symbol not in active:
            if additions >= addition_limit:
                continue
            additions += 1
        selected.append(symbol)
    return selected, mandatory


def _updated_active_state(
    selected: list[str],
    *,
    snapshot: ThemeSnapshot,
    active: dict[str, dict[str, Any]],
    execution_position: int,
) -> dict[str, dict[str, Any]]:
    updated = {}
    for symbol in selected:
        prior = active.get(symbol)
        updated[symbol] = {
            "entry_position": (
                int(prior["entry_position"]) if prior is not None else execution_position
            ),
            "score": float(
                snapshot.member_scores.get(
                    symbol,
                    prior.get("score", 0.0) if prior else 0.0,
                )
            ),
            "theme": tuple(
                snapshot.member_theme.get(
                    symbol,
                    tuple(prior.get("theme", (symbol,))) if prior else (symbol,),
                )
            ),
        }
    return updated


def _stock_weights(
    *,
    columns: pd.Index,
    selected: list[str],
    active: dict[str, dict[str, Any]],
    scores: dict[str, float],
    volatility: pd.Series,
    maximum_symbol_weight: float,
    maximum_theme_weight: float,
) -> dict[str, float]:
    weights = {str(symbol): 0.0 for symbol in columns}
    if not selected:
        weights["BIL"] = 1.0
        return weights
    raw = {}
    for symbol in selected:
        vol = float(volatility[symbol])
        score = max(float(scores.get(symbol, active[symbol]["score"])), 0.01)
        if not math.isfinite(vol) or vol <= 0:
            raise ValueError(f"R9 stock volatility is invalid: {symbol}")
        raw[symbol] = score / vol
    total = math.fsum(raw.values())
    for symbol, value in raw.items():
        weights[symbol] = min(value / total, maximum_symbol_weight)
    theme_groups: dict[tuple[str, ...], list[str]] = {}
    for symbol in selected:
        theme_groups.setdefault(tuple(active[symbol]["theme"]), []).append(symbol)
    for members in theme_groups.values():
        theme_weight = math.fsum(weights[symbol] for symbol in members)
        if theme_weight > maximum_theme_weight:
            scale = maximum_theme_weight / theme_weight
            for symbol in members:
                weights[symbol] *= scale
    weights["BIL"] += 1.0 - math.fsum(weights.values())
    _normalize_roundoff(weights)
    return weights


def _desired_beta_state(
    *, close: float, sma40: float, sma60: float, momentum20: float, drawdown20: float
) -> str:
    if not all(math.isfinite(value) for value in (close, sma40, sma60, momentum20, drawdown20)):
        return "stress"
    if drawdown20 <= -0.12 or (close < sma60 and momentum20 <= 0):
        return "stress"
    if close > sma40 > sma60 and momentum20 > 0:
        return "risk_on"
    return "transition"


def _bounded_component_groups(
    members: tuple[str, ...],
    affinity: pd.DataFrame,
    *,
    minimum_members: int,
    maximum_members: int,
) -> list[tuple[str, ...]]:
    if len(members) <= maximum_members:
        return [members]
    affinity_symbols = list(map(str, affinity.columns))
    positions = {symbol: index for index, symbol in enumerate(affinity_symbols)}
    values = affinity.to_numpy(dtype=float, copy=False)
    remaining = set(members)
    groups = []
    while remaining:
        seed = sorted(
            remaining,
            key=lambda symbol: (
                -float(
                    np.mean([values[positions[symbol], positions[other]] for other in remaining])
                ),
                symbol,
            ),
        )[0]
        ranked = sorted(
            (other for other in remaining if other != seed),
            key=lambda other: (
                -float(values[positions[seed], positions[other]]),
                other,
            ),
        )
        group = tuple(sorted([seed, *ranked[: maximum_members - 1]]))
        remaining -= set(group)
        if len(group) >= minimum_members:
            groups.append(group)
    return groups


def _component_cohesion(affinity: pd.DataFrame, members: tuple[str, ...]) -> float:
    if len(members) < 2:
        return 0.0
    values = affinity.loc[list(members), list(members)].to_numpy(dtype=float, copy=False)
    return float(values[np.triu_indices(len(members), k=1)].mean())


def _standardize_columns(values: np.ndarray) -> np.ndarray:
    centered = values - values.mean(axis=0, keepdims=True)
    scale = centered.std(axis=0, keepdims=True)
    return np.divide(centered, scale, out=np.zeros_like(centered), where=scale > 0)


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def _reserve_weights(columns: pd.Index) -> dict[str, float]:
    weights = {str(symbol): 0.0 for symbol in columns}
    weights["BIL"] = 1.0
    return weights


def _normalize_roundoff(weights: dict[str, float]) -> None:
    total = math.fsum(weights.values())
    if not math.isfinite(total) or total <= 0 or total > 1.0 + 1e-10:
        raise ValueError("R9 target allocation is invalid")
    weights["BIL"] = float(weights.get("BIL", 0.0)) + (1.0 - total)


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
        raise ValueError(f"{candidate_id} targets must sum to one")
    positions = {session: position for position, session in enumerate(sessions)}
    for record in records:
        decision = pd.Timestamp(record["decision_session"])
        execution = pd.Timestamp(record["execution_session"])
        if positions[execution] != positions[decision] + 1:
            raise ValueError(f"{candidate_id} target is not next-session executable")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
