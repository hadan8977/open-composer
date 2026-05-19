from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

import pandas as pd

from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.intraday_daily_rotation import (
    _alpha,
    _annualized_from_total,
    _daily_sharpe,
    _max_drawdown_pct,
    _win_pct,
)
from open_composer.research.metadata import (
    combined_data_profile,
    estimate_grid_research_cost,
    hypothesis_ledger,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.research.rotation import _filter_time_window
from open_composer.storage import write_json

from .intraday_daily_rotation import _DailyBars, _load_dataset

HybridObjective = Literal["benchmark_buy_hold_alpha", "risk_adjusted_benchmark_alpha"]
HoldingMode = Literal["open_to_open", "open_to_close"]


@dataclass(frozen=True)
class HybridRouterParams:
    holding_mode: HoldingMode
    momentum_lookback_days: int
    top_n: int
    market_sma_days: int | None
    min_momentum_pct: float
    max_position_weight: float

    @property
    def label(self) -> str:
        gate = "nogate" if self.market_sma_days is None else f"qsm{self.market_sma_days}"
        return (
            f"{self.holding_mode}:lb{self.momentum_lookback_days}_top{self.top_n}_"
            f"{gate}_min{self.min_momentum_pct:g}_w{self.max_position_weight:g}"
        )


@dataclass(frozen=True)
class HybridRouterMetrics:
    days: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float
    traded_days: int
    round_trips: int
    average_selected_count: float
    win_day_pct: float
    benchmark_symbol: str
    benchmark_buy_hold_return_pct: float
    benchmark_buy_hold_annualized_pct: float | None
    alpha_vs_benchmark_buy_hold_annualized_pct: float | None
    market_symbol: str
    market_buy_hold_return_pct: float
    market_buy_hold_annualized_pct: float | None
    alpha_vs_market_buy_hold_annualized_pct: float | None
    equal_weight_buy_hold_return_pct: float
    equal_weight_buy_hold_annualized_pct: float | None
    alpha_vs_equal_weight_buy_hold_annualized_pct: float | None
    best_symbol_buy_hold_pct: float
    best_symbol: str | None
    alpha_vs_best_symbol_buy_hold_pct: float
    exposure_pct: float
    skipped_days: int


@dataclass(frozen=True)
class HybridRouterCandidate:
    rank: int
    params: HybridRouterParams
    score: float
    train: HybridRouterMetrics
    out_of_sample: HybridRouterMetrics
    full_window: HybridRouterMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class HybridRouterWalkForwardSlice:
    fold: int
    params: HybridRouterParams
    train: HybridRouterMetrics
    test: HybridRouterMetrics


@dataclass(frozen=True)
class HybridRouterResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[HybridRouterCandidate]
    walk_forward: list[HybridRouterWalkForwardSlice]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> HybridRouterCandidate:
        return self.candidates[0]


def hybrid_params_from_label(label: str) -> HybridRouterParams:
    try:
        holding_mode, remainder = label.split(":", 1)
        parts = remainder.split("_")
        if len(parts) != 5:
            raise ValueError
        lookback = int(parts[0].removeprefix("lb"))
        top_n = int(parts[1].removeprefix("top"))
        gate = parts[2]
        market_sma = None if gate == "nogate" else int(gate.removeprefix("qsm"))
        min_momentum = float(parts[3].removeprefix("min"))
        weight = float(parts[4].removeprefix("w"))
    except ValueError as exc:
        raise ValueError(f"unsupported hybrid route label: {label}") from exc
    if holding_mode not in {"open_to_open", "open_to_close"}:
        raise ValueError(f"unsupported hybrid holding mode in label: {label}")
    return HybridRouterParams(
        holding_mode=holding_mode,  # type: ignore[arg-type]
        momentum_lookback_days=lookback,
        top_n=top_n,
        market_sma_days=market_sma,
        min_momentum_pct=min_momentum,
        max_position_weight=weight,
    )


@dataclass(frozen=True)
class _DailyHybridDataset:
    symbols: list[str]
    benchmark_symbol: str
    market_symbol: str
    dates: list[str]
    frame: pd.DataFrame
    data_profile: dict[str, Any]


def run_hybrid_adaptive_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    holding_modes: list[HoldingMode] | None = None,
    momentum_lookback_days: list[int] | None = None,
    top_n_values: list[int] | None = None,
    market_sma_days: list[int | None] | None = None,
    min_momentum_pct: list[float] | None = None,
    max_position_weight: list[float] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    walk_forward_top_k: int | None = 20,
    max_candidates: int = 240,
    refresh_data: bool = False,
    objective: HybridObjective = "benchmark_buy_hold_alpha",
) -> HybridRouterResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("hybrid adaptive router requires at least two NASDAQ symbols")
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    dataset = _load_daily_hybrid_dataset(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    params_grid = _build_hybrid_params_grid(
        holding_modes=holding_modes or ["open_to_open", "open_to_close"],
        momentum_lookback_days=momentum_lookback_days or [10, 20, 40, 60, 100],
        top_n_values=top_n_values or [1, 2, 3],
        market_sma_days=market_sma_days or [None, 20, 50, 100],
        min_momentum_pct=min_momentum_pct or [0.0],
        max_position_weight=max_position_weight or [spec.risk.max_position_weight],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started

    stage_started = perf_counter()
    candidates = _evaluate_hybrid_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
        objective=objective,
    )
    stages["evaluate_candidates"] = perf_counter() - stage_started

    walk_params = _walk_forward_params(
        params_grid=params_grid,
        candidates=candidates,
        walk_forward_top_k=walk_forward_top_k,
    )
    research_cost = estimate_grid_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(walk_params),
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=walk_forward_folds,
    ).__dict__

    stage_started = perf_counter()
    walk_forward = _walk_forward_hybrid(
        spec=spec,
        dataset=dataset,
        params_grid=walk_params,
        folds=walk_forward_folds,
        objective=objective,
    )
    stages["walk_forward"] = perf_counter() - stage_started

    report_path = base / "reports" / "research" / f"{spec.name}-hybrid-adaptive-router.md"
    json_path = base / "reports" / "research" / f"{spec.name}-hybrid-adaptive-router.json"
    runtime_seconds = runtime_payload(started_at, stages)
    _write_hybrid_json(
        json_path,
        spec,
        dataset,
        candidates,
        walk_forward,
        start,
        end,
        objective,
        research_cost,
        runtime_seconds,
        params_grid,
    )
    _write_hybrid_report(
        report_path,
        json_path,
        spec,
        dataset,
        candidates,
        walk_forward,
        start,
        end,
        objective,
        research_cost,
        runtime_seconds,
    )
    return HybridRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime_seconds,
        data_profile=dataset.data_profile,
    )


def _load_daily_hybrid_dataset(
    *,
    spec: StrategySpec,
    root: Path,
    symbols: list[str],
    data_source: str,
    feed: str,
    start: str | None,
    end: str | None,
    benchmark_symbol: str,
    market_symbol: str,
    refresh_data: bool,
) -> _DailyHybridDataset:
    intraday = _load_dataset(
        spec=spec,
        root=root,
        symbols=symbols,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    required_symbols = list(
        dict.fromkeys([*intraday.symbols, intraday.benchmark_symbol, intraday.market_symbol])
    )
    frame = _daily_frame_from_intraday(intraday.bars, intraday.dates, required_symbols)
    frame = _filter_time_window(frame, start, end)
    dates = list(frame["date"].astype(str))
    if len(dates) < 120:
        raise ValueError("hybrid adaptive router requires at least 120 common sessions")
    return _DailyHybridDataset(
        symbols=intraday.symbols,
        benchmark_symbol=intraday.benchmark_symbol,
        market_symbol=intraday.market_symbol,
        dates=dates,
        frame=frame,
        data_profile=combined_data_profile(intraday.profiles),
    )


def _daily_frame_from_intraday(
    bars: dict[str, dict[str, _DailyBars]],
    dates: list[str],
    symbols: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date in dates:
        row: dict[str, Any] = {"date": date, "timestamp": pd.Timestamp(date, tz="UTC")}
        for symbol, symbol_bars in bars.items():
            day = symbol_bars.get(date)
            if day is None:
                continue
            row[f"{symbol}_open"] = float(day.opens[0])
            row[f"{symbol}_close"] = float(day.closes[-1])
            row[f"{symbol}_volume"] = float(day.volumes.sum())
        rows.append(row)
    frame = pd.DataFrame(rows)
    required = [column for symbol in symbols for column in (f"{symbol}_open", f"{symbol}_close")]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("daily hybrid frame missing columns: " + ", ".join(missing[:5]))
    return frame.dropna(subset=required).reset_index(drop=True)


def _build_hybrid_params_grid(
    *,
    holding_modes: list[HoldingMode],
    momentum_lookback_days: list[int],
    top_n_values: list[int],
    market_sma_days: list[int | None],
    min_momentum_pct: list[float],
    max_position_weight: list[float],
    max_candidates: int,
) -> list[HybridRouterParams]:
    params: list[HybridRouterParams] = []
    for mode, lookback, top_n, sma, min_mom, weight in product(
        holding_modes,
        momentum_lookback_days,
        top_n_values,
        market_sma_days,
        min_momentum_pct,
        max_position_weight,
    ):
        if lookback < 2:
            raise ValueError("momentum lookback must be at least 2 days")
        if top_n < 1:
            raise ValueError("top_n must be at least 1")
        if sma is not None and sma < 2:
            raise ValueError("market_sma_days must be at least 2")
        params.append(
            HybridRouterParams(
                holding_mode=mode,
                momentum_lookback_days=lookback,
                top_n=top_n,
                market_sma_days=sma,
                min_momentum_pct=min_mom,
                max_position_weight=weight,
            )
        )
    return params[:max_candidates]


def _evaluate_hybrid_candidates(
    *,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params_grid: list[HybridRouterParams],
    out_of_sample_ratio: float,
    objective: HybridObjective,
) -> list[HybridRouterCandidate]:
    split = _split_for_hybrid(len(dataset.dates), out_of_sample_ratio, params_grid)
    rows: list[HybridRouterCandidate] = []
    for params in params_grid:
        train = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=params.momentum_lookback_days + 1,
            end_index=split,
        )
        oos = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=split,
            end_index=len(dataset.dates),
        )
        full = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=params.momentum_lookback_days + 1,
            end_index=len(dataset.dates),
        )
        rows.append(
            HybridRouterCandidate(
                rank=0,
                params=params,
                score=_hybrid_score(train, oos, full, objective),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=_hybrid_quality_flags(train, oos, full),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        HybridRouterCandidate(
            rank=index,
            params=item.params,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for index, item in enumerate(rows, start=1)
    ]


def _walk_forward_params(
    *,
    params_grid: list[HybridRouterParams],
    candidates: list[HybridRouterCandidate],
    walk_forward_top_k: int | None,
) -> list[HybridRouterParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("walk_forward_top_k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _walk_forward_hybrid(
    *,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params_grid: list[HybridRouterParams],
    folds: int,
    objective: HybridObjective,
) -> list[HybridRouterWalkForwardSlice]:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.dates) - max_lookback) // (max(folds, 1) + 1), 20)
    rows: list[HybridRouterWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.dates), test_start + fold_size)
        if test_end - test_start < 20:
            continue
        scored: list[tuple[float, HybridRouterParams]] = []
        for params in params_grid:
            train = _backtest_hybrid_params(
                spec,
                dataset,
                params,
                start_index=max_lookback,
                end_index=test_start,
            )
            scored.append((_walk_score(train, objective), params))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        rows.append(
            HybridRouterWalkForwardSlice(
                fold=fold,
                params=selected,
                train=_backtest_hybrid_params(
                    spec,
                    dataset,
                    selected,
                    start_index=max_lookback,
                    end_index=test_start,
                ),
                test=_backtest_hybrid_params(
                    spec,
                    dataset,
                    selected,
                    start_index=test_start,
                    end_index=test_end,
                ),
            )
        )
    return rows


def _backtest_hybrid_params(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> HybridRouterMetrics:
    frame = dataset.frame
    start_index = max(start_index, _effective_lookback(params))
    end_index = min(end_index, len(frame) - (1 if params.holding_mode == "open_to_open" else 0))
    returns: list[float] = []
    selected_counts: list[int] = []
    equity_curve = [start_equity]
    equity = start_equity
    traded_days = 0
    round_trips = 0
    skipped_days = 0
    max_names_by_weight = max(1, int(1 / params.max_position_weight))
    effective_top_n = min(params.top_n, max_names_by_weight, spec.risk.max_trades_per_day)
    for index in range(start_index, end_index):
        selected = _hybrid_selected_symbols(dataset, index, params, effective_top_n)
        if not selected:
            strategy_return = 0.0
            skipped_days += 1
        else:
            weight = min(params.max_position_weight, 1 / len(selected))
            strategy_return = sum(
                weight * _symbol_holding_return(dataset, symbol, index, params.holding_mode, spec)
                for symbol in selected
            )
            traded_days += 1
            round_trips += len(selected)
        selected_counts.append(len(selected))
        returns.append(strategy_return)
        equity *= 1 + strategy_return
        equity_curve.append(equity)
    period_dates = dataset.dates[start_index:end_index]
    total_return_pct = (equity / start_equity - 1) * 100
    benchmark_buy_hold = _daily_buy_hold_return(
        dataset,
        dataset.benchmark_symbol,
        start_index,
        end_index,
    )
    market_buy_hold = _daily_buy_hold_return(
        dataset,
        dataset.market_symbol,
        start_index,
        end_index,
    )
    equal_weight_buy_hold = mean(
        _daily_buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    )
    universe_returns = {
        symbol: _daily_buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = _annualized_from_total(total_return_pct, len(returns))
    benchmark_annualized = _annualized_from_total(benchmark_buy_hold, len(returns))
    market_annualized = _annualized_from_total(market_buy_hold, len(returns))
    equal_weight_annualized = _annualized_from_total(equal_weight_buy_hold, len(returns))
    return HybridRouterMetrics(
        days=len(returns),
        start_date=period_dates[0] if period_dates else None,
        end_date=period_dates[-1] if period_dates else None,
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        sharpe_ratio=_daily_sharpe(returns),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        traded_days=traded_days,
        round_trips=round_trips,
        average_selected_count=mean(selected_counts) if selected_counts else 0.0,
        win_day_pct=_win_pct(returns),
        benchmark_symbol=dataset.benchmark_symbol,
        benchmark_buy_hold_return_pct=benchmark_buy_hold,
        benchmark_buy_hold_annualized_pct=benchmark_annualized,
        alpha_vs_benchmark_buy_hold_annualized_pct=_alpha(annualized, benchmark_annualized),
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=market_buy_hold,
        market_buy_hold_annualized_pct=market_annualized,
        alpha_vs_market_buy_hold_annualized_pct=_alpha(annualized, market_annualized),
        equal_weight_buy_hold_return_pct=equal_weight_buy_hold,
        equal_weight_buy_hold_annualized_pct=equal_weight_annualized,
        alpha_vs_equal_weight_buy_hold_annualized_pct=_alpha(annualized, equal_weight_annualized),
        best_symbol_buy_hold_pct=best_return,
        best_symbol=best_symbol,
        alpha_vs_best_symbol_buy_hold_pct=total_return_pct - best_return,
        exposure_pct=(traded_days / len(returns) * 100) if returns else 0.0,
        skipped_days=skipped_days,
    )


def _hybrid_selected_symbols(
    dataset: _DailyHybridDataset,
    index: int,
    params: HybridRouterParams,
    top_n: int,
) -> list[str]:
    frame = dataset.frame
    if params.market_sma_days is not None:
        market_close = frame[f"{dataset.market_symbol}_close"]
        if index < params.market_sma_days:
            return []
        market_sma = float(market_close.iloc[index - params.market_sma_days : index].mean())
        if float(market_close.iloc[index - 1]) <= market_sma:
            return []
    previous_index = index - 1 - params.momentum_lookback_days
    current_index = index - 1
    if previous_index < 0:
        return []
    scores: list[tuple[float, str]] = []
    for symbol in dataset.symbols:
        previous = float(frame[f"{symbol}_close"].iloc[previous_index])
        current = float(frame[f"{symbol}_close"].iloc[current_index])
        if previous <= 0:
            continue
        momentum = (current / previous - 1) * 100
        if momentum >= params.min_momentum_pct:
            scores.append((momentum, symbol))
    scores.sort(reverse=True)
    return [symbol for _, symbol in scores[:top_n]]


def _symbol_holding_return(
    dataset: _DailyHybridDataset,
    symbol: str,
    index: int,
    holding_mode: HoldingMode,
    spec: StrategySpec,
) -> float:
    frame = dataset.frame
    if holding_mode == "open_to_close":
        exit_price = float(frame[f"{symbol}_close"].iloc[index])
    else:
        exit_price = float(frame[f"{symbol}_open"].iloc[index + 1])
    entry = float(frame[f"{symbol}_open"].iloc[index])
    if entry <= 0:
        return 0.0
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    return (exit_price * (1 - cost_rate)) / (entry * (1 + cost_rate)) - 1


def _daily_buy_hold_return(
    dataset: _DailyHybridDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    frame = dataset.frame
    if end_index <= start_index:
        return 0.0
    start = float(frame[f"{symbol}_open"].iloc[start_index])
    end = float(frame[f"{symbol}_close"].iloc[end_index - 1])
    return ((end / start) - 1) * 100 if start > 0 else 0.0


def _split_for_hybrid(
    frame_len: int,
    ratio: float,
    params_grid: list[HybridRouterParams],
) -> int:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _effective_lookback(params: HybridRouterParams) -> int:
    return max(params.momentum_lookback_days + 1, (params.market_sma_days or 0) + 1)


def _objective_alpha(metrics: HybridRouterMetrics, objective: HybridObjective) -> float:
    base = metrics.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0
    if objective == "risk_adjusted_benchmark_alpha":
        return base + (metrics.sharpe_ratio or 0.0) * 10 - abs(min(metrics.max_drawdown_pct, 0))
    return base


def _walk_score(metrics: HybridRouterMetrics, objective: HybridObjective) -> float:
    return _objective_alpha(metrics, objective) + (metrics.sharpe_ratio or 0.0) * 5


def _hybrid_score(
    train: HybridRouterMetrics,
    oos: HybridRouterMetrics,
    full: HybridRouterMetrics,
    objective: HybridObjective,
) -> float:
    raw_train_alpha = train.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0
    raw_oos_alpha = oos.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0
    raw_full_alpha = full.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0
    train_alpha = _objective_alpha(train, objective)
    oos_alpha = _objective_alpha(oos, objective)
    full_alpha = _objective_alpha(full, objective)
    consistency_penalty = abs(train_alpha - oos_alpha) * 0.12
    drawdown_penalty = abs(min(oos.max_drawdown_pct, 0.0)) * 0.35
    sparse_penalty = max(0, 40 - oos.traded_days) * 1.0
    score = (
        min(train_alpha, oos_alpha, full_alpha) * 0.7
        + oos_alpha * 0.6
        + (oos.sharpe_ratio or 0.0) * 12
        - consistency_penalty
        - drawdown_penalty
        - sparse_penalty
    )
    if min(raw_train_alpha, raw_oos_alpha, raw_full_alpha) <= 0:
        score -= 10_000
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        score -= 1_000
    if oos.traded_days < 40:
        score -= 1_000
    if oos.max_drawdown_pct <= -30:
        score -= 1_000
    return score


def _hybrid_quality_flags(
    train: HybridRouterMetrics,
    oos: HybridRouterMetrics,
    full: HybridRouterMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_tqqq_buy_hold")
    if (oos.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_tqqq_buy_hold")
    if (full.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_tqqq_buy_hold")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        flags.append("oos_low_sharpe")
    if oos.traded_days < 40:
        flags.append("oos_low_traded_days")
    if oos.max_drawdown_pct <= -30:
        flags.append("oos_large_drawdown")
    if full.alpha_vs_best_symbol_buy_hold_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def _acceptance_gate(
    candidate: HybridRouterCandidate,
    walk_forward: list[HybridRouterWalkForwardSlice],
    objective: HybridObjective,
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_benchmark_buy_hold_annualized_pct for item in walk_forward]
    positive_wf = sum((value or -100.0) > 0 for value in wf_alphas)
    fold_count = len(wf_alphas)
    train_alpha = candidate.train.alpha_vs_benchmark_buy_hold_annualized_pct
    oos_alpha = candidate.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct
    full_alpha = candidate.full_window.alpha_vs_benchmark_buy_hold_annualized_pct
    passed = (
        (train_alpha or -100.0) > 0
        and (oos_alpha or -100.0) > 0
        and (full_alpha or -100.0) > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.7
        and candidate.out_of_sample.traded_days >= 40
        and candidate.out_of_sample.max_drawdown_pct > -30
        and fold_count > 0
        and positive_wf == fold_count
    )
    return {
        "passed": passed,
        "objective": objective,
        "train_alpha_vs_tqqq_buy_hold_annualized_pct": train_alpha,
        "oos_alpha_vs_tqqq_buy_hold_annualized_pct": oos_alpha,
        "full_alpha_vs_tqqq_buy_hold_annualized_pct": full_alpha,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_traded_days": candidate.out_of_sample.traded_days,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": fold_count,
        "quality_flags": candidate.quality_flags,
    }


def _pass_status(
    candidate: HybridRouterCandidate,
    walk_forward: list[HybridRouterWalkForwardSlice],
    objective: HybridObjective,
) -> dict[str, Any]:
    gate = _acceptance_gate(candidate, walk_forward, objective)
    blockers = [
        "draft/manual_signal strategy only",
        "Alpaca IEX/cache evidence is not consolidated live SIP evidence",
        "hybrid portfolio target mapping is research-only until Nautilus parity is added",
        "news/LLM features are advisory until PIT marginal-lift evidence exists",
    ]
    return {
        "workflow_pass": True,
        "research_pass": bool(gate["passed"]),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_ready_blockers": blockers,
    }


def _write_hybrid_json(
    path: Path,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    candidates: list[HybridRouterCandidate],
    walk_forward: list[HybridRouterWalkForwardSlice],
    start: str | None,
    end: str | None,
    objective: HybridObjective,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    params_grid: list[HybridRouterParams],
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "mode": "hybrid_adaptive_router",
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective="positive annualized Alpha versus TQQQ buy-and-hold",
            hypothesis=(
                "A hybrid route that combines market-regime scanning with overnight/swing "
                "NASDAQ momentum can beat TQQQ buy-and-hold more consistently than a "
                "flat-at-close intraday-only strategy."
            ),
            constraints=_assumptions(spec, dataset),
        ),
        "search_space": search_space(
            family="hybrid_adaptive_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "signal uses previous confirmed close",
                "fill uses next regular-session open",
                "commission and slippage applied on each entry and exit",
                "long-only",
                "NASDAQ basket only",
            ],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis="Hybrid routing improves annualized Alpha versus TQQQ buy-and-hold.",
            visible_evidence=["train metrics", "OOS metrics", "walk-forward folds"],
            hidden_evidence=[],
            counterevidence=candidates[0].quality_flags,
            conclusion="passed"
            if _acceptance_gate(candidates[0], walk_forward, objective)["passed"]
            else "failed",
        ),
        "selection_objective": objective,
        "research_cost": research_cost,
        "runtime_seconds": runtime_seconds,
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward, objective),
        "pass_status": _pass_status(candidates[0], walk_forward, objective),
        "assumptions": _assumptions(spec, dataset),
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_hybrid_report(
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    candidates: list[HybridRouterCandidate],
    walk_forward: list[HybridRouterWalkForwardSlice],
    start: str | None,
    end: str | None,
    objective: HybridObjective,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    gate = _acceptance_gate(candidates[0], walk_forward, objective)
    lines = [
        f"# Hybrid Adaptive Router Research: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbols: {', '.join(dataset.symbols)}",
        f"- Market scanner symbol: `{dataset.market_symbol}`",
        f"- Benchmark symbol: `{dataset.benchmark_symbol}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Data as-of: `{dataset.data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{dataset.data_profile.get('provider') or 'mixed'}` / "
        f"`{dataset.data_profile.get('feed') or 'mixed'}`",
        f"- Data source mode: `{dataset.data_profile.get('source_mode') or 'mixed'}`",
        "- Signal timing: rank at previous confirmed close; fill at next regular-session open.",
        "- Holding modes searched: `open_to_open`, `open_to_close`.",
        f"- Commission/slippage per fill: `{spec.costs.commission_pct:g}%` / "
        f"`{spec.costs.slippage_bps:g} bps`.",
        "- Acceptance requires train, OOS, and full-window annualized Alpha vs TQQQ buy-hold > 0.",
        "",
        "## Assumptions",
        "",
        *[f"- {item}" for item in _assumptions(spec, dataset)],
        "",
        "## Research Cost",
        "",
        f"- Candidates evaluated: `{research_cost['candidate_count']}`",
        f"- Walk-forward candidates: `{research_cost['walk_forward_candidate_count']}`",
        f"- Estimated backtest passes: `{research_cost['estimated_total_backtest_passes']}`",
        f"- Runtime total seconds: `{runtime_seconds['total']:.2f}`",
        "",
        "## Acceptance Gate",
        "",
        *[f"- {key}: `{value}`" for key, value in gate.items()],
        "",
        "## Top Candidates",
        "",
    ]
    for item in candidates[:10]:
        flags = ", ".join(item.quality_flags) if item.quality_flags else "none"
        lines.extend(
            [
                f"### Rank {item.rank}: {item.params.label}",
                "",
                f"- Score: `{item.score:.2f}`",
                f"- Quality flags: `{flags}`",
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
            "## Interpretation Notes",
            "",
            "- This strategy is no longer constrained to flat-at-close intraday trading.",
            "- Positive TQQQ buy-hold Alpha is mandatory in train, OOS, and full-window gates.",
            "- Open-to-open returns include overnight risk and require separate execution parity "
            "before paper automation.",
            "- Cache/IEX data remains research evidence until data and paper-readiness gates pass.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _assumptions(spec: StrategySpec, dataset: _DailyHybridDataset) -> list[str]:
    return [
        "Momentum ranking uses closes visible before the entry session.",
        "Entry fill is modeled at the next regular-session open.",
        "Open-to-open mode exits/rebalances at the following regular-session open.",
        "Open-to-close mode exits at the same regular-session close.",
        f"Commission is {spec.costs.commission_pct:.4g}% per fill.",
        f"Slippage is {spec.costs.slippage_bps:.4g} bps per fill.",
        f"Universe is restricted to: {', '.join(dataset.symbols)}.",
        f"Benchmark stress test is {dataset.benchmark_symbol} buy-and-hold.",
        f"Market regime scanner is {dataset.market_symbol}.",
        f"Max per-symbol weight is bounded by spec risk ({spec.risk.max_position_weight:.2f}).",
        "No LLM/news feature is used inside the execution loop for this first hybrid pass.",
    ]


def _metric_lines(label: str, metrics: HybridRouterMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} annualized: `{_fmt(metrics.annualized_return_pct)}%`",
        f"- {label} Alpha vs TQQQ buy-hold annualized: "
        f"`{_fmt(metrics.alpha_vs_benchmark_buy_hold_annualized_pct)}%`",
        f"- {label} TQQQ buy-hold annualized: `{_fmt(metrics.benchmark_buy_hold_annualized_pct)}%`",
        f"- {label} Alpha vs {metrics.market_symbol} buy-hold annualized: "
        f"`{_fmt(metrics.alpha_vs_market_buy_hold_annualized_pct)}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} traded days / round trips: `{metrics.traded_days}/{metrics.round_trips}`",
        f"- {label} exposure: `{metrics.exposure_pct:.2f}%`",
        f"- {label} ex-post best buy-hold: "
        f"`{metrics.best_symbol} {metrics.best_symbol_buy_hold_pct:.2f}%`",
    ]


def _candidate_payload(candidate: HybridRouterCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: HybridRouterWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _params_grid_ranges(params_grid: list[HybridRouterParams]) -> dict[str, list[Any]]:
    return {
        "holding_mode": sorted({item.holding_mode for item in params_grid}),
        "momentum_lookback_days": sorted({item.momentum_lookback_days for item in params_grid}),
        "top_n": sorted({item.top_n for item in params_grid}),
        "market_sma_days": sorted(
            {item.market_sma_days for item in params_grid},
            key=lambda value: -1 if value is None else value,
        ),
        "min_momentum_pct": sorted({item.min_momentum_pct for item in params_grid}),
        "max_position_weight": sorted({item.max_position_weight for item in params_grid}),
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
