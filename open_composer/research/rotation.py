from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path
from statistics import mean
from typing import Any, Literal

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.expressions import evaluate_expression, prepare_factor_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json

RotationObjective = Literal["equal_weight_alpha", "primary_alpha"]


@dataclass(frozen=True)
class RotationParams:
    lookback_bars: int
    rebalance_bars: int
    top_n: int
    min_momentum_pct: float
    primary_hold_margin_pct: float | None = None
    primary_min_momentum_pct: float | None = None

    @property
    def label(self) -> str:
        label = (
            f"lb{self.lookback_bars}_reb{self.rebalance_bars}_"
            f"top{self.top_n}_min{self.min_momentum_pct:g}"
        )
        if self.primary_hold_margin_pct is not None:
            label += f"_anchor{self.primary_hold_margin_pct:g}"
            if self.primary_min_momentum_pct is not None:
                label += f"_pmin{self.primary_min_momentum_pct:g}"
        return label


@dataclass(frozen=True)
class RotationMetrics:
    bars: int
    start_timestamp: str | None
    end_timestamp: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float
    rebalances: int
    trades: int
    average_turnover_pct: float
    equal_weight_buy_hold_pct: float
    alpha_vs_equal_weight_pct: float
    primary_buy_hold_pct: float
    alpha_vs_primary_pct: float
    best_symbol_buy_hold_pct: float
    best_symbol: str | None
    alpha_vs_best_symbol_pct: float
    feature_eligible_bar_pct: float | None = None


@dataclass(frozen=True)
class RotationCandidate:
    rank: int
    params: RotationParams
    score: float
    train: RotationMetrics
    out_of_sample: RotationMetrics
    full_window: RotationMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class WalkForwardSlice:
    fold: int
    params: RotationParams
    train: RotationMetrics
    test: RotationMetrics


@dataclass(frozen=True)
class RotationResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[RotationCandidate]
    walk_forward: list[WalkForwardSlice]

    @property
    def best(self) -> RotationCandidate:
        return self.candidates[0]


def run_rotation_research(
    spec_path: Path,
    root: Path | None = None,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    lookback_bars: list[int] | None = None,
    rebalance_bars: list[int] | None = None,
    top_n_values: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    max_candidates: int = 200,
    refresh_data: bool = False,
    feature_gate: bool = False,
    start: str | None = None,
    end: str | None = None,
    objective: RotationObjective = "equal_weight_alpha",
    primary_hold_margin_pct: list[float] | None = None,
    primary_min_momentum_pct: list[float] | None = None,
) -> RotationResearchResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        msg = "rotation research requires at least two symbols"
        raise ValueError(msg)
    if spec.timeframe not in {"5m", "15m", "1h", "daily", "weekly"}:
        msg = "rotation research supports 5m, 15m, 1h, daily, or weekly StrategySpecs"
        raise ValueError(msg)
    feature_factor_names = _feature_factor_names(spec)
    if feature_factor_names and not feature_gate:
        msg = (
            "rotation research detected LLM/feature_packet factors "
            f"({', '.join(feature_factor_names)}); pass --feature-gate to use replayable "
            "point-in-time feature gates, or use a pure price StrategySpec"
        )
        raise ValueError(msg)

    selected_feed = feed or spec.data.feed or data_feed()
    frame = _load_universe_frame(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        refresh_data=refresh_data,
        feature_gate=feature_gate,
        start=start,
        end=end,
    )
    params_grid = _build_params_grid(
        lookback_bars or [21, 42, 63, 126],
        rebalance_bars or [5, 10, 21],
        top_n_values or [1, 2, 3],
        min_momentum_pct or [0.0, 5.0, 10.0],
        max_candidates=max_candidates,
        primary_hold_margin_pct=primary_hold_margin_pct,
        primary_min_momentum_pct=primary_min_momentum_pct,
    )
    candidates = _evaluate_candidates(
        spec=spec,
        frame=frame,
        symbols=universe,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
        objective=objective,
    )
    walk_forward = _walk_forward(
        spec=spec,
        frame=frame,
        symbols=universe,
        params_grid=params_grid,
        folds=walk_forward_folds,
        objective=objective,
    )
    report_path = base / "reports" / "research" / f"{spec.name}-rotation-research.md"
    json_path = base / "reports" / "research" / f"{spec.name}-rotation-research.json"
    _write_rotation_json(
        json_path, spec, universe, candidates, walk_forward, feature_gate, start, end, objective
    )
    _write_rotation_report(
        report_path,
        json_path,
        spec,
        universe,
        candidates,
        walk_forward,
        feature_gate,
        start,
        end,
        objective,
    )
    return RotationResearchResult(
        report_path=report_path,
        json_path=json_path,
        candidates=candidates,
        walk_forward=walk_forward,
    )


def _load_universe_frame(
    *,
    spec: StrategySpec,
    root: Path,
    symbols: list[str],
    data_source: str,
    feed: str,
    refresh_data: bool,
    feature_gate: bool,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for symbol in symbols:
        frame = fetch_ohlcv(
            root=root,
            symbol=symbol,
            timeframe=spec.timeframe,
            start=None,
            end=None,
            source=data_source,
            feed=feed,
            use_cache=not refresh_data,
        )
        selected = frame[["timestamp", "open", "close"]].copy()
        selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True)
        selected = selected.sort_values("timestamp").drop_duplicates("timestamp")
        if feature_gate:
            eligible = _feature_eligible_mask(spec, selected, root, symbol)
            selected["feature_eligible"] = eligible.astype(bool)
        selected = selected.rename(
            columns={
                "open": f"{symbol}_open",
                "close": f"{symbol}_close",
                "feature_eligible": f"{symbol}_feature_eligible",
            }
        )
        merged = selected if merged is None else merged.merge(selected, on="timestamp", how="inner")
    if merged is None or merged.empty:
        msg = "no overlapping OHLCV rows were available for rotation research"
        raise ValueError(msg)
    merged = _filter_time_window(merged.sort_values("timestamp"), start, end)
    if merged.empty:
        msg = "no OHLCV rows remained after applying the requested research window"
        raise ValueError(msg)
    return merged.reset_index(drop=True)


def _build_params_grid(
    lookbacks: list[int],
    rebalances: list[int],
    top_ns: list[int],
    min_momentum_values: list[float],
    *,
    max_candidates: int,
    primary_hold_margin_pct: list[float] | None = None,
    primary_min_momentum_pct: list[float] | None = None,
) -> list[RotationParams]:
    if max_candidates < 1:
        msg = "--max-candidates must be at least 1"
        raise ValueError(msg)
    anchor_values: list[float | None] = (
        [None] if primary_hold_margin_pct is None else list(primary_hold_margin_pct)
    )
    primary_min_values: list[float | None] = (
        [None] if primary_min_momentum_pct is None else list(primary_min_momentum_pct)
    )
    total = prod(
        [
            len(lookbacks),
            len(rebalances),
            len(top_ns),
            len(min_momentum_values),
            len(anchor_values),
            len(primary_min_values),
        ]
    )
    if total > max_candidates:
        msg = (
            f"rotation grid would create {total} candidates; "
            f"raise --max-candidates above {total} or narrow the grid"
        )
        raise ValueError(msg)
    params: list[RotationParams] = []
    for lookback, rebalance, top_n, min_momentum, anchor, primary_min in product(
        lookbacks, rebalances, top_ns, min_momentum_values, anchor_values, primary_min_values
    ):
        if anchor is None and primary_min is not None:
            continue
        if lookback < 2:
            raise ValueError("lookback bars must be at least 2")
        if rebalance < 1:
            raise ValueError("rebalance bars must be at least 1")
        if top_n < 1:
            raise ValueError("top_n must be at least 1")
        params.append(
            RotationParams(
                lookback_bars=lookback,
                rebalance_bars=rebalance,
                top_n=top_n,
                min_momentum_pct=min_momentum,
                primary_hold_margin_pct=anchor,
                primary_min_momentum_pct=primary_min,
            )
        )
    return params


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    frame: pd.DataFrame,
    symbols: list[str],
    params_grid: list[RotationParams],
    out_of_sample_ratio: float,
    objective: RotationObjective,
) -> list[RotationCandidate]:
    split = _split_index(
        frame, out_of_sample_ratio, max(item.lookback_bars for item in params_grid)
    )
    candidates: list[RotationCandidate] = []
    for params in params_grid:
        train_frame = frame.iloc[:split].copy()
        oos_start = max(0, split - params.lookback_bars - 1)
        oos_frame = frame.iloc[oos_start:].copy().reset_index(drop=True)
        train = _backtest_rotation(spec, train_frame, symbols, params)
        oos = _backtest_rotation(
            spec,
            oos_frame,
            symbols,
            params,
            evaluation_start_index=split - oos_start,
        )
        full = _backtest_rotation(spec, frame, symbols, params)
        flags = _quality_flags(train, oos, full)
        candidates.append(
            RotationCandidate(
                rank=0,
                params=params,
                score=_score_rotation_candidate(train, objective),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=flags,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return [
        RotationCandidate(
            rank=rank,
            params=item.params,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for rank, item in enumerate(candidates, start=1)
    ]


def _walk_forward(
    *,
    spec: StrategySpec,
    frame: pd.DataFrame,
    symbols: list[str],
    params_grid: list[RotationParams],
    folds: int,
    objective: RotationObjective,
) -> list[WalkForwardSlice]:
    folds = max(folds, 1)
    max_lookback = max(item.lookback_bars for item in params_grid)
    fold_size = max((len(frame) - max_lookback) // (folds + 1), 2)
    slices: list[WalkForwardSlice] = []
    for fold in range(1, folds + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        train_frame = frame.iloc[:test_start].copy()
        train_scores = [
            (
                _score_rotation_candidate(
                    _backtest_rotation(spec, train_frame, symbols, params), objective
                ),
                params,
            )
            for params in params_grid
        ]
        train_scores.sort(key=lambda item: item[0], reverse=True)
        selected_params = train_scores[0][1]
        warm_start = max(0, test_start - selected_params.lookback_bars - 1)
        test_frame = frame.iloc[warm_start:test_end].copy().reset_index(drop=True)
        slices.append(
            WalkForwardSlice(
                fold=fold,
                params=selected_params,
                train=_backtest_rotation(spec, train_frame, symbols, selected_params),
                test=_backtest_rotation(
                    spec,
                    test_frame,
                    symbols,
                    selected_params,
                    evaluation_start_index=test_start - warm_start,
                ),
            )
        )
    return slices


def _backtest_rotation(
    spec: StrategySpec,
    frame: pd.DataFrame,
    symbols: list[str],
    params: RotationParams,
    start_equity: float = 100_000.0,
    evaluation_start_index: int = 0,
) -> RotationMetrics:
    if len(frame) <= params.lookback_bars + 1:
        return _empty_metrics(frame, symbols)
    evaluation_start_index = max(
        params.lookback_bars,
        min(evaluation_start_index, len(frame) - 1),
    )
    commission_rate = spec.costs.commission_pct / 100
    slippage_rate = spec.costs.slippage_bps / 10_000
    transaction_cost_rate = commission_rate + slippage_rate
    cash = start_equity
    shares = {symbol: 0.0 for symbol in symbols}
    equity_curve: list[float] = []
    turnovers: list[float] = []
    rebalances = 0
    trades = 0

    for index in range(evaluation_start_index, len(frame)):
        close_equity = cash + sum(
            shares[symbol] * float(frame[f"{symbol}_close"].iloc[index]) for symbol in symbols
        )
        equity_curve.append(close_equity)
        if index >= len(frame) - 1:
            continue
        if (index - params.lookback_bars) % params.rebalance_bars != 0:
            continue

        selected = _selected_symbols(frame, symbols, index, params)
        weights = {symbol: 1.0 / len(selected) for symbol in selected} if selected else {}
        next_index = index + 1
        execution_equity = cash + sum(
            shares[symbol] * float(frame[f"{symbol}_open"].iloc[next_index]) for symbol in symbols
        )
        if execution_equity <= 0:
            continue
        trade_notional = 0.0
        new_shares: dict[str, float] = {}
        for symbol in symbols:
            open_price = float(frame[f"{symbol}_open"].iloc[next_index])
            current_notional = shares[symbol] * open_price
            target_notional = execution_equity * weights.get(symbol, 0.0)
            delta_notional = target_notional - current_notional
            if abs(delta_notional) > 1e-8:
                trades += 1
                trade_notional += abs(delta_notional)
            new_shares[symbol] = target_notional / open_price if open_price > 0 else 0.0
        costs = trade_notional * transaction_cost_rate
        cash = (
            execution_equity
            - sum(
                new_shares[symbol] * float(frame[f"{symbol}_open"].iloc[next_index])
                for symbol in symbols
            )
            - costs
        )
        shares = new_shares
        turnovers.append((trade_notional / execution_equity) * 100)
        rebalances += 1

    final_equity = cash + sum(
        shares[symbol] * float(frame[f"{symbol}_close"].iloc[-1]) for symbol in symbols
    )
    if not equity_curve or abs(equity_curve[-1] - final_equity) > 1e-8:
        equity_curve.append(final_equity)
    total_return_pct = (final_equity / start_equity - 1) * 100
    metrics = build_performance_metrics(equity_curve, spec.timeframe)
    benchmark_start = min(evaluation_start_index + 1, len(frame) - 1)
    benchmark = _benchmarks(frame, symbols, benchmark_start, total_return_pct)
    eligible_pct = (
        _feature_eligible_bar_pct(frame, symbols) if _has_feature_columns(frame) else None
    )
    return RotationMetrics(
        bars=len(frame) - evaluation_start_index,
        start_timestamp=frame["timestamp"].iloc[benchmark_start].isoformat(),
        end_timestamp=frame["timestamp"].iloc[-1].isoformat(),
        total_return_pct=total_return_pct,
        annualized_return_pct=metrics.annualized_return_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        rebalances=rebalances,
        trades=trades,
        average_turnover_pct=mean(turnovers) if turnovers else 0.0,
        feature_eligible_bar_pct=eligible_pct,
        **benchmark,
    )


def _selected_symbols(
    frame: pd.DataFrame,
    symbols: list[str],
    index: int,
    params: RotationParams,
) -> list[str]:
    scores: list[tuple[float, str]] = []
    previous_index = index - params.lookback_bars
    raw_momentum: dict[str, float] = {}
    for symbol in symbols:
        eligible_column = f"{symbol}_feature_eligible"
        if eligible_column in frame.columns and not bool(frame[eligible_column].iloc[index]):
            continue
        current = float(frame[f"{symbol}_close"].iloc[index])
        previous = float(frame[f"{symbol}_close"].iloc[previous_index])
        if previous <= 0:
            continue
        momentum_pct = (current / previous - 1) * 100
        raw_momentum[symbol] = momentum_pct
        if momentum_pct >= params.min_momentum_pct:
            scores.append((momentum_pct, symbol))
    scores.sort(reverse=True)
    if params.primary_hold_margin_pct is not None and symbols:
        anchored = _anchored_selection(symbols[0], scores, raw_momentum, params)
        if anchored:
            return anchored
    return [symbol for _, symbol in scores[: params.top_n]]


def _anchored_selection(
    primary: str,
    scores: list[tuple[float, str]],
    raw_momentum: dict[str, float],
    params: RotationParams,
) -> list[str]:
    primary_momentum = raw_momentum.get(primary)
    if primary_momentum is None:
        return [symbol for _, symbol in scores[: params.top_n]]
    primary_floor = (
        params.primary_min_momentum_pct
        if params.primary_min_momentum_pct is not None
        else params.min_momentum_pct
    )
    if primary_momentum < primary_floor:
        return [symbol for _, symbol in scores[: params.top_n]]
    if not scores:
        return [primary]
    margin = params.primary_hold_margin_pct or 0.0
    best_momentum, best_symbol = scores[0]
    if best_symbol != primary and best_momentum - primary_momentum >= margin:
        selected = [symbol for _, symbol in scores[: params.top_n]]
    else:
        selected = [primary]
        for _, symbol in scores:
            if symbol != primary and len(selected) < params.top_n:
                selected.append(symbol)
    return selected


def _benchmarks(
    frame: pd.DataFrame,
    symbols: list[str],
    start_index: int,
    total_return_pct: float,
) -> dict[str, float | str | None]:
    returns: dict[str, float] = {}
    for symbol in symbols:
        start = float(frame[f"{symbol}_open"].iloc[start_index])
        end = float(frame[f"{symbol}_close"].iloc[-1])
        returns[symbol] = ((end / start) - 1) * 100 if start > 0 else 0.0
    equal_weight = mean(returns.values()) if returns else 0.0
    primary = returns.get(symbols[0], 0.0)
    best_symbol = max(returns, key=returns.get) if returns else None
    best = returns[best_symbol] if best_symbol else 0.0
    return {
        "equal_weight_buy_hold_pct": equal_weight,
        "alpha_vs_equal_weight_pct": total_return_pct - equal_weight,
        "primary_buy_hold_pct": primary,
        "alpha_vs_primary_pct": total_return_pct - primary,
        "best_symbol_buy_hold_pct": best,
        "best_symbol": best_symbol,
        "alpha_vs_best_symbol_pct": total_return_pct - best,
    }


def _empty_metrics(frame: pd.DataFrame, symbols: list[str]) -> RotationMetrics:
    return RotationMetrics(
        bars=len(frame),
        start_timestamp=frame["timestamp"].iloc[0].isoformat() if len(frame) else None,
        end_timestamp=frame["timestamp"].iloc[-1].isoformat() if len(frame) else None,
        total_return_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        max_drawdown_pct=0.0,
        rebalances=0,
        trades=0,
        average_turnover_pct=0.0,
        equal_weight_buy_hold_pct=0.0,
        alpha_vs_equal_weight_pct=0.0,
        primary_buy_hold_pct=0.0,
        alpha_vs_primary_pct=0.0,
        best_symbol_buy_hold_pct=0.0,
        best_symbol=symbols[0] if symbols else None,
        alpha_vs_best_symbol_pct=0.0,
    )


def _split_index(frame: pd.DataFrame, out_of_sample_ratio: float, max_lookback: int) -> int:
    split = int(len(frame) * (1 - out_of_sample_ratio))
    split = max(split, max_lookback + 3)
    return min(split, len(frame) - 2)


def _score_rotation_candidate(
    metrics: RotationMetrics,
    objective: RotationObjective = "equal_weight_alpha",
) -> float:
    sharpe = metrics.sharpe_ratio or 0.0
    alpha = (
        metrics.alpha_vs_primary_pct
        if objective == "primary_alpha"
        else metrics.alpha_vs_equal_weight_pct
    )
    return (
        alpha
        + sharpe * 10
        - abs(min(metrics.max_drawdown_pct, 0.0)) * 0.25
        - metrics.average_turnover_pct * 0.03
    )


def _quality_flags(
    train: RotationMetrics,
    oos: RotationMetrics,
    full: RotationMetrics,
) -> list[str]:
    flags: list[str] = []
    if train.rebalances < 5:
        flags.append("low_train_rebalance_count")
    if oos.rebalances < 3:
        flags.append("low_oos_rebalance_count")
    if oos.alpha_vs_equal_weight_pct <= 0:
        flags.append("oos_no_alpha_vs_equal_weight")
    if oos.alpha_vs_primary_pct <= 0:
        flags.append("oos_no_alpha_vs_primary")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if full.alpha_vs_primary_pct <= 0:
        flags.append("full_window_no_alpha_vs_primary")
    if full.alpha_vs_best_symbol_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    if (
        full.feature_eligible_bar_pct is not None
        and full.feature_eligible_bar_pct < 25
        and oos.alpha_vs_equal_weight_pct > 0
    ):
        flags.append("sparse_feature_coverage")
    return flags


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak <= 0:
            continue
        drawdown = (value / peak - 1) * 100
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _write_rotation_json(
    path: Path,
    spec: StrategySpec,
    symbols: list[str],
    candidates: list[RotationCandidate],
    walk_forward: list[WalkForwardSlice],
    feature_gate: bool,
    start: str | None,
    end: str | None,
    objective: RotationObjective,
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": spec.name,
        "symbols": symbols,
        "candidate_count": len(candidates),
        "mode": "llm_feature_gated_rotation" if feature_gate else "pure_price_rotation",
        "research_window": {"start": start, "end": end},
        "selection_objective": _objective_label(objective),
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward, objective),
        "assumptions": _assumptions(spec),
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_forward_payload(item) for item in walk_forward],
    }
    write_json(path, payload)
    return path


def _write_rotation_report(
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    symbols: list[str],
    candidates: list[RotationCandidate],
    walk_forward: list[WalkForwardSlice],
    feature_gate: bool,
    start: str | None,
    end: str | None,
    objective: RotationObjective,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Rotation Research: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbols: {', '.join(symbols)}",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Mode: `{'llm_feature_gated_rotation' if feature_gate else 'pure_price_rotation'}`",
        "- Point-in-time ranking: only current and historical closes are used.",
        "- Signal timing: rank at confirmed bar close; rebalance at next bar open.",
        f"- Selection objective: {_objective_label(objective)}",
        "- This is research-only portfolio evidence; no paper orders are emitted.",
        "",
        "## Assumptions",
        "",
        *[f"- {item}" for item in _assumptions(spec)],
        "",
        "## Acceptance Gate",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _acceptance_gate(candidates[0], walk_forward, objective).items()
        ],
        "",
        "## Top Candidates",
        "",
    ]
    for item in candidates[:10]:
        quality_flags = ", ".join(item.quality_flags) if item.quality_flags else "none"
        lines.extend(
            [
                f"### Rank {item.rank}: {item.params.label}",
                "",
                f"- Score: `{item.score:.2f}`",
                f"- Quality flags: `{quality_flags}`",
                *_metric_lines("Train", item.train),
                *_metric_lines("Out of sample", item.out_of_sample),
                *_metric_lines("Full window", item.full_window),
                "",
            ]
        )
    lines.extend(["## Walk Forward", ""])
    if not walk_forward:
        lines.append("- No walk-forward slices were available.")
    for item in walk_forward:
        lines.extend(
            [
                f"### Fold {item.fold}: {item.params.label}",
                "",
                *_metric_lines("Train selected", item.train),
                *_metric_lines("Test", item.test),
                "",
            ]
        )
    lines.extend(
        [
            "## Overfit Notes",
            "",
            "- Best parameters are selected from the training window, not from OOS.",
            "- Walk-forward folds reselect parameters only from prior bars.",
            "- `best_symbol_buy_hold_pct` is an ex-post benchmark, not a tradable target.",
            "- A candidate with positive Alpha versus equal-weight but negative Alpha versus the "
            "ex-post best symbol should be treated as sector rotation evidence, not proof that "
            "the model can identify the single future winner.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _assumptions(spec: StrategySpec) -> list[str]:
    assumptions = [
        "Only current and historical close prices are used for ranking.",
        "Signals are confirmed at bar close and filled at the next bar open.",
        "Common timestamps are inner-joined across the universe to avoid missing-data selection.",
        f"Commission is {spec.costs.commission_pct:.4g}% per fill.",
        f"Slippage is {spec.costs.slippage_bps:.4g} bps per fill.",
        "No LLM is called inside the rotation backtest loop.",
    ]
    feature_factors = _feature_factor_names(spec)
    if feature_factors:
        assumptions.append(
            "Feature-gated rotation uses saved point-in-time feature packets only: "
            + ", ".join(feature_factors)
        )
    return assumptions


def _metric_lines(label: str, metrics: RotationMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} Alpha vs equal-weight: `{metrics.alpha_vs_equal_weight_pct:.2f}%`",
        f"- {label} Alpha vs primary: `{metrics.alpha_vs_primary_pct:.2f}%`",
        f"- {label} Alpha vs ex-post best symbol: `{metrics.alpha_vs_best_symbol_pct:.2f}%`",
        f"- {label} Sharpe: `{_format_optional(metrics.sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} rebalances/trades: `{metrics.rebalances}/{metrics.trades}`",
        f"- {label} feature eligible bars: `{_format_optional(metrics.feature_eligible_bar_pct)}%`",
        f"- {label} equal-weight buy-hold: `{metrics.equal_weight_buy_hold_pct:.2f}%`",
        (
            f"- {label} ex-post best buy-hold: "
            f"`{metrics.best_symbol} {metrics.best_symbol_buy_hold_pct:.2f}%`"
        ),
    ]


def _candidate_payload(candidate: RotationCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": _metrics_payload(candidate.train),
        "out_of_sample": _metrics_payload(candidate.out_of_sample),
        "full_window": _metrics_payload(candidate.full_window),
    }


def _walk_forward_payload(item: WalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": _metrics_payload(item.train),
        "test": _metrics_payload(item.test),
    }


def _metrics_payload(metrics: RotationMetrics) -> dict[str, Any]:
    return metrics.__dict__


def _acceptance_gate(
    candidate: RotationCandidate,
    walk_forward: list[WalkForwardSlice],
    objective: RotationObjective,
) -> dict[str, Any]:
    oos_alpha = _objective_alpha(candidate.out_of_sample, objective)
    wf_alphas = [_objective_alpha(item.test, objective) for item in walk_forward]
    positive_wf = sum(value > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    passed = (
        oos_alpha > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and candidate.out_of_sample.rebalances >= 3
        and wf_count > 0
        and positive_wf == wf_count
    )
    return {
        "passed": passed,
        "objective": objective,
        "oos_objective_alpha_pct": oos_alpha,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_rebalances": candidate.out_of_sample.rebalances,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _objective_alpha(metrics: RotationMetrics, objective: RotationObjective) -> float:
    if objective == "primary_alpha":
        return metrics.alpha_vs_primary_pct
    return metrics.alpha_vs_equal_weight_pct


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _objective_label(objective: RotationObjective) -> str:
    if objective == "primary_alpha":
        return (
            "train score prioritizes Alpha versus the primary symbol buy-and-hold; "
            "OOS and walk-forward are validation evidence"
        )
    return (
        "train score prioritizes Alpha versus equal-weight buy-and-hold; "
        "OOS and walk-forward are validation evidence"
    )


def _filter_time_window(
    frame: pd.DataFrame,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    filtered = frame.copy()
    if start:
        filtered = filtered[filtered["timestamp"] >= _utc_timestamp(start)]
    if end:
        filtered = filtered[filtered["timestamp"] <= _utc_timestamp(end)]
    return filtered


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _feature_factor_names(spec: StrategySpec) -> list[str]:
    return sorted(
        name
        for name, factor in spec.factors.items()
        if factor.source in {"llm_feature", "feature_packet"}
    )


def _feature_eligible_mask(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path,
    symbol: str,
) -> pd.Series:
    feature_factors = {
        name: factor
        for name, factor in spec.factors.items()
        if factor.source in {"llm_feature", "feature_packet"}
    }
    if not feature_factors:
        return pd.Series([True] * len(frame), index=frame.index)
    prepared = prepare_factor_frame(
        frame,
        feature_factors,
        root=root,
        symbol=symbol,
        require_feature_symbol=True,
    )
    feature_rules = _feature_rules(spec)
    if feature_rules:
        result = [
            evaluate_expression(rule, prepared).fillna(False).astype(bool) for rule in feature_rules
        ]
        eligible = result[0]
        for item in result[1:]:
            eligible = eligible & item
        return eligible.fillna(False).astype(bool)
    return _feature_values_differ_from_defaults(prepared, feature_factors)


def _feature_rules(spec: StrategySpec) -> list[str]:
    names = set(_feature_factor_names(spec))
    return [rule for rule in spec.entry.all if any(name in rule for name in names)]


def _feature_values_differ_from_defaults(
    frame: pd.DataFrame,
    feature_factors: dict[str, Any],
) -> pd.Series:
    eligible = pd.Series([True] * len(frame), index=frame.index)
    for name, factor in feature_factors.items():
        eligible = eligible & (frame[name] != getattr(factor, "default", 0.0))
    return eligible.fillna(False).astype(bool)


def _has_feature_columns(frame: pd.DataFrame) -> bool:
    return any(column.endswith("_feature_eligible") for column in frame.columns)


def _feature_eligible_bar_pct(frame: pd.DataFrame, symbols: list[str]) -> float:
    columns = [f"{symbol}_feature_eligible" for symbol in symbols]
    existing = [column for column in columns if column in frame.columns]
    if not existing or len(frame) == 0:
        return 0.0
    eligible = frame[existing].astype(bool).any(axis=1)
    return (float(eligible.sum()) / len(frame)) * 100
