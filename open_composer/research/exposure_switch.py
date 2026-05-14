from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.json_utils import json_safe_sorted_values
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.metadata import (
    frame_data_profile,
    hypothesis_ledger,
    research_brief,
    search_space,
)
from open_composer.storage import write_json


@dataclass(frozen=True)
class ExposureSwitchParams:
    fast_bars: int
    slow_bars: int
    momentum_bars: int
    min_momentum_pct: float
    volatility_bars: int
    max_volatility_pct: float | None
    drawdown_bars: int
    max_drawdown_pct: float | None
    base_exposure: float
    risk_on_exposure: float
    risk_off_exposure: float
    financing_rate_pct: float

    @property
    def label(self) -> str:
        vol = "none" if self.max_volatility_pct is None else f"{self.max_volatility_pct:g}"
        dd = "none" if self.max_drawdown_pct is None else f"{self.max_drawdown_pct:g}"
        return (
            f"f{self.fast_bars}_s{self.slow_bars}_m{self.momentum_bars}_"
            f"min{self.min_momentum_pct:g}_v{self.volatility_bars}_{vol}_"
            f"dd{self.drawdown_bars}_{dd}_base{self.base_exposure:g}_"
            f"on{self.risk_on_exposure:g}_off{self.risk_off_exposure:g}_"
            f"fin{self.financing_rate_pct:g}"
        )


@dataclass(frozen=True)
class ExposureSwitchMetrics:
    bars: int
    start_timestamp: str | None
    end_timestamp: str | None
    total_return_pct: float
    buy_hold_return_pct: float
    alpha_vs_buy_hold_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    buy_hold_sharpe_ratio: float | None
    max_drawdown_pct: float
    buy_hold_max_drawdown_pct: float
    average_exposure: float
    max_exposure: float
    exposure_changes: int
    financing_cost_pct: float


@dataclass(frozen=True)
class ExposureSwitchCandidate:
    rank: int
    params: ExposureSwitchParams
    score: float
    train: ExposureSwitchMetrics
    out_of_sample: ExposureSwitchMetrics
    full_window: ExposureSwitchMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class ExposureSwitchWalkForwardSlice:
    fold: int
    params: ExposureSwitchParams
    train: ExposureSwitchMetrics
    test: ExposureSwitchMetrics


@dataclass(frozen=True)
class ExposureSwitchResearchCost:
    candidate_count: int
    walk_forward_candidate_count: int
    walk_forward_top_k: int | None
    walk_forward_folds: int
    estimated_candidate_evaluation_passes: int
    estimated_walk_forward_validation_passes: int
    estimated_walk_forward_selected_passes: int
    estimated_total_backtest_passes: int
    cost_model: str


@dataclass(frozen=True)
class ExposureSwitchResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[ExposureSwitchCandidate]
    walk_forward: list[ExposureSwitchWalkForwardSlice]
    research_cost: ExposureSwitchResearchCost
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> ExposureSwitchCandidate:
        return self.candidates[0]


def run_exposure_switch_research(
    spec_path: Path,
    root: Path | None = None,
    symbol: str | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    fast_bars: list[int] | None = None,
    slow_bars: list[int] | None = None,
    momentum_bars: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    volatility_bars: list[int] | None = None,
    max_volatility_pct: list[float | None] | None = None,
    drawdown_bars: list[int] | None = None,
    max_drawdown_pct: list[float | None] | None = None,
    base_exposure: list[float] | None = None,
    risk_on_exposure: list[float] | None = None,
    risk_off_exposure: list[float] | None = None,
    financing_rate_pct: list[float] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    max_candidates: int = 200,
    refresh_data: bool = False,
    start: str | None = None,
    end: str | None = None,
    walk_forward_top_k: int | None = None,
) -> ExposureSwitchResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    stage_started = perf_counter()
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_symbol = (symbol or spec.primary_symbol).upper()
    selected_feed = feed or spec.data.feed or data_feed()
    frame = fetch_ohlcv(
        root=base,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        start=None,
        end=None,
        source=data_source,
        feed=selected_feed,
        use_cache=not refresh_data,
    )
    frame = _filter_time_window(_normalize_timestamps(frame), start, end)
    if len(frame) < 8:
        raise ValueError("exposure switch research requires at least 8 bars after filtering")
    data_profile = frame_data_profile(
        frame,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        provider=data_source,
        feed=selected_feed,
        source_mode="cache" if not refresh_data else "live_fetch",
    )
    stages["load_data"] = perf_counter() - stage_started
    stage_started = perf_counter()
    params_grid = _build_params_grid(
        fast_bars or [3, 5, 8],
        slow_bars or [13, 21, 34],
        momentum_bars or [3, 5, 10],
        min_momentum_pct or [0.0, 5.0],
        volatility_bars or [5, 10],
        max_volatility_pct or [None, 12.0, 18.0],
        drawdown_bars or [5, 10],
        max_drawdown_pct or [None, 18.0, 25.0],
        base_exposure or [1.0],
        risk_on_exposure or [1.25, 1.5],
        risk_off_exposure or [0.0, 0.5, 1.0],
        financing_rate_pct or [5.0, 8.0],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started
    stage_started = perf_counter()
    candidates = _evaluate_candidates(
        frame=frame,
        timeframe=spec.timeframe,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    stages["evaluate_candidates"] = perf_counter() - stage_started
    walk_forward_params = _walk_forward_params(
        params_grid=params_grid,
        candidates=candidates,
        walk_forward_top_k=walk_forward_top_k,
    )
    research_cost = _estimate_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(walk_forward_params),
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=walk_forward_folds,
    )
    stage_started = perf_counter()
    walk_forward = _walk_forward(
        frame=frame,
        timeframe=spec.timeframe,
        params_grid=walk_forward_params,
        folds=walk_forward_folds,
    )
    stages["walk_forward"] = perf_counter() - stage_started
    report_path = base / "reports" / "research" / f"{spec.name}-exposure-switch-research.md"
    json_path = base / "reports" / "research" / f"{spec.name}-exposure-switch-research.json"
    stages["write_reports"] = 0.0
    runtime_seconds = _runtime_payload(started_at, stages)
    write_started = perf_counter()
    _write_outputs(
        report_path=report_path,
        json_path=json_path,
        strategy_name=spec.name,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        start=start,
        end=end,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime_seconds,
        data_profile=data_profile,
        params_grid=params_grid,
    )
    stages["write_reports"] = perf_counter() - write_started
    final_runtime_seconds = _runtime_payload(started_at, stages)
    _write_outputs(
        report_path=report_path,
        json_path=json_path,
        strategy_name=spec.name,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        start=start,
        end=end,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=final_runtime_seconds,
        data_profile=data_profile,
        params_grid=params_grid,
    )
    return ExposureSwitchResearchResult(
        report_path,
        json_path,
        candidates,
        walk_forward,
        research_cost,
        final_runtime_seconds,
        data_profile,
    )


def _build_params_grid(
    fast_values: list[int],
    slow_values: list[int],
    momentum_values: list[int],
    min_momentum_values: list[float],
    volatility_values: list[int],
    max_volatility_values: list[float | None],
    drawdown_values: list[int],
    max_drawdown_values: list[float | None],
    base_values: list[float],
    risk_on_values: list[float],
    risk_off_values: list[float],
    financing_values: list[float],
    *,
    max_candidates: int,
) -> list[ExposureSwitchParams]:
    total = prod(
        [
            len(fast_values),
            len(slow_values),
            len(momentum_values),
            len(min_momentum_values),
            len(volatility_values),
            len(max_volatility_values),
            len(drawdown_values),
            len(max_drawdown_values),
            len(base_values),
            len(risk_on_values),
            len(risk_off_values),
            len(financing_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"exposure switch grid would create {total} candidates; raise --max-candidates "
            f"above {total} or narrow the grid"
        )
    params: list[ExposureSwitchParams] = []
    for item in product(
        fast_values,
        slow_values,
        momentum_values,
        min_momentum_values,
        volatility_values,
        max_volatility_values,
        drawdown_values,
        max_drawdown_values,
        base_values,
        risk_on_values,
        risk_off_values,
        financing_values,
    ):
        (
            fast,
            slow,
            momentum,
            min_momentum,
            volatility,
            max_volatility,
            drawdown,
            max_drawdown,
            base,
            risk_on,
            risk_off,
            financing,
        ) = item
        if min(fast, slow, momentum, volatility, drawdown) < 1:
            continue
        if fast >= slow:
            continue
        if min(base, risk_on, risk_off) < 0:
            continue
        if risk_on < base:
            continue
        if risk_off > base:
            continue
        if financing < 0:
            continue
        params.append(
            ExposureSwitchParams(
                fast_bars=fast,
                slow_bars=slow,
                momentum_bars=momentum,
                min_momentum_pct=min_momentum,
                volatility_bars=volatility,
                max_volatility_pct=max_volatility,
                drawdown_bars=drawdown,
                max_drawdown_pct=max_drawdown,
                base_exposure=base,
                risk_on_exposure=risk_on,
                risk_off_exposure=risk_off,
                financing_rate_pct=financing,
            )
        )
    if not params:
        raise ValueError("exposure switch grid produced no valid candidates")
    return params


def _evaluate_candidates(
    *,
    frame: pd.DataFrame,
    timeframe: str,
    params_grid: list[ExposureSwitchParams],
    out_of_sample_ratio: float,
) -> list[ExposureSwitchCandidate]:
    split = _split_index(frame, out_of_sample_ratio, _max_warmup(params_grid))
    rows: list[ExposureSwitchCandidate] = []
    for params in params_grid:
        train = _backtest_exposure_switch(frame.iloc[:split].copy(), timeframe, params)
        oos_start = max(0, split - _warmup(params) - 1)
        oos = _backtest_exposure_switch(
            frame.iloc[oos_start:].copy().reset_index(drop=True),
            timeframe,
            params,
            evaluation_start_index=split - oos_start,
        )
        full = _backtest_exposure_switch(frame, timeframe, params)
        rows.append(
            ExposureSwitchCandidate(
                rank=0,
                params=params,
                score=_score_candidate(train),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=_quality_flags(train, oos, full),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        ExposureSwitchCandidate(
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
    params_grid: list[ExposureSwitchParams],
    candidates: list[ExposureSwitchCandidate],
    walk_forward_top_k: int | None,
) -> list[ExposureSwitchParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _params_grid_ranges(params_grid: list[ExposureSwitchParams]) -> dict[str, list[Any]]:
    keys = [
        "fast_bars",
        "slow_bars",
        "momentum_bars",
        "min_momentum_pct",
        "volatility_bars",
        "max_volatility_pct",
        "drawdown_bars",
        "max_drawdown_pct",
        "base_exposure",
        "risk_on_exposure",
        "risk_off_exposure",
        "financing_rate_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _estimate_research_cost(
    *,
    candidate_count: int,
    walk_forward_candidate_count: int,
    walk_forward_top_k: int | None,
    walk_forward_folds: int,
) -> ExposureSwitchResearchCost:
    effective_folds = max(walk_forward_folds, 1)
    candidate_passes = candidate_count * 3
    walk_forward_validation_passes = walk_forward_candidate_count * effective_folds
    walk_forward_selected_passes = effective_folds * 2
    return ExposureSwitchResearchCost(
        candidate_count=candidate_count,
        walk_forward_candidate_count=walk_forward_candidate_count,
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=effective_folds,
        estimated_candidate_evaluation_passes=candidate_passes,
        estimated_walk_forward_validation_passes=walk_forward_validation_passes,
        estimated_walk_forward_selected_passes=walk_forward_selected_passes,
        estimated_total_backtest_passes=(
            candidate_passes + walk_forward_validation_passes + walk_forward_selected_passes
        ),
        cost_model=(
            "candidate_count * 3 train/oos/full passes + "
            "walk_forward_candidate_count * folds validation passes + 2 selected passes per fold"
        ),
    )


def _runtime_payload(started_at: float, stages: dict[str, float]) -> dict[str, Any]:
    return {
        "total": round(perf_counter() - started_at, 6),
        "stages": {key: round(value, 6) for key, value in stages.items()},
    }


def _walk_forward(
    *,
    frame: pd.DataFrame,
    timeframe: str,
    params_grid: list[ExposureSwitchParams],
    folds: int,
) -> list[ExposureSwitchWalkForwardSlice]:
    folds = max(folds, 1)
    max_warmup = _max_warmup(params_grid)
    fold_size = max((len(frame) - max_warmup) // (folds + 1), 2)
    slices: list[ExposureSwitchWalkForwardSlice] = []
    for fold in range(1, folds + 1):
        test_start = max_warmup + fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        train_frame = frame.iloc[:test_start].copy().reset_index(drop=True)
        selection_split = _split_index(train_frame, 0.2, max_warmup)
        scored: list[tuple[float, ExposureSwitchParams, ExposureSwitchMetrics]] = []
        for params in params_grid:
            validation_start = max(0, selection_split - _warmup(params) - 1)
            validation = _backtest_exposure_switch(
                train_frame.iloc[validation_start:].copy().reset_index(drop=True),
                timeframe,
                params,
                evaluation_start_index=selection_split - validation_start,
            )
            scored.append((_score_candidate(validation), params, validation))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        warm_start = max(0, test_start - _warmup(selected) - 1)
        test = _backtest_exposure_switch(
            frame.iloc[warm_start:test_end].copy().reset_index(drop=True),
            timeframe,
            selected,
            evaluation_start_index=test_start - warm_start,
        )
        slices.append(
            ExposureSwitchWalkForwardSlice(
                fold=fold,
                params=selected,
                train=_backtest_exposure_switch(train_frame, timeframe, selected),
                test=test,
            )
        )
    return slices


def _backtest_exposure_switch(
    frame: pd.DataFrame,
    timeframe: str,
    params: ExposureSwitchParams,
    *,
    start_equity: float = 100_000.0,
    evaluation_start_index: int = 0,
) -> ExposureSwitchMetrics:
    if len(frame) < 2:
        return _empty_metrics(frame)
    working = _indicator_frame(frame, params)
    evaluation_start_index = max(1, min(evaluation_start_index, len(working) - 1))
    equity = start_equity
    buy_hold_equity = start_equity
    equity_curve = [equity]
    buy_hold_curve = [buy_hold_equity]
    exposures: list[float] = []
    exposure_changes = 0
    previous_exposure: float | None = None
    financing_cost = 0.0
    financing_per_bar = _financing_per_bar(params.financing_rate_pct, timeframe)
    open_values = working["open"].astype(float).to_numpy()
    close_values = working["close"].astype(float).to_numpy()
    fast_ema = working["fast_ema"].astype(float).to_numpy()
    slow_ema = working["slow_ema"].astype(float).to_numpy()
    momentum = working["momentum_pct"].astype(float).to_numpy()
    volatility = working["realized_vol_pct"].astype(float).to_numpy()
    drawdown = working["window_drawdown_pct"].astype(float).to_numpy()
    for idx in range(evaluation_start_index, len(working)):
        next_price = open_values[idx + 1] if idx + 1 < len(working) else close_values[idx]
        exposure = _target_exposure_from_arrays(
            index=idx - 1,
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            momentum=momentum,
            volatility=volatility,
            drawdown=drawdown,
            params=params,
        )
        period_return = (next_price / open_values[idx]) - 1
        financing_drag = max(exposure - 1.0, 0.0) * financing_per_bar
        period_financing = equity * financing_drag
        equity = max(equity * (1 + exposure * period_return) - period_financing, 0.0)
        buy_hold_equity *= 1 + period_return
        equity_curve.append(equity)
        buy_hold_curve.append(buy_hold_equity)
        financing_cost += period_financing
        exposures.append(exposure)
        if previous_exposure is not None and exposure != previous_exposure:
            exposure_changes += 1
        previous_exposure = exposure
        if equity <= 0:
            break
    metrics = build_performance_metrics(equity_curve, timeframe)
    buy_hold_metrics = build_performance_metrics(buy_hold_curve, timeframe)
    total_return_pct = (equity / start_equity - 1) * 100
    buy_hold_return_pct = (buy_hold_equity / start_equity - 1) * 100
    evaluation_frame = working.iloc[evaluation_start_index:].copy()
    return ExposureSwitchMetrics(
        bars=len(evaluation_frame),
        start_timestamp=evaluation_frame["timestamp"].iloc[0].isoformat()
        if len(evaluation_frame)
        else None,
        end_timestamp=evaluation_frame["timestamp"].iloc[-1].isoformat()
        if len(evaluation_frame)
        else None,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        alpha_vs_buy_hold_pct=total_return_pct - buy_hold_return_pct,
        annualized_return_pct=metrics.annualized_return_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        buy_hold_sharpe_ratio=buy_hold_metrics.sharpe_ratio,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        buy_hold_max_drawdown_pct=_max_drawdown_pct(buy_hold_curve),
        average_exposure=sum(exposures) / len(exposures) if exposures else 0.0,
        max_exposure=max(exposures) if exposures else 0.0,
        exposure_changes=exposure_changes,
        financing_cost_pct=(financing_cost / start_equity) * 100,
    )


def _indicator_frame(frame: pd.DataFrame, params: ExposureSwitchParams) -> pd.DataFrame:
    working = frame.copy().reset_index(drop=True)
    close = working["close"].astype(float)
    returns = close.pct_change()
    working["fast_ema"] = close.ewm(span=params.fast_bars, adjust=False).mean()
    working["slow_ema"] = close.ewm(span=params.slow_bars, adjust=False).mean()
    working["momentum_pct"] = close.pct_change(params.momentum_bars) * 100
    working["realized_vol_pct"] = returns.rolling(params.volatility_bars).std() * 100
    rolling_high = close.rolling(params.drawdown_bars).max()
    working["window_drawdown_pct"] = (close / rolling_high - 1) * 100
    return working


def _target_exposure_from_arrays(
    *,
    index: int,
    fast_ema: np.ndarray,
    slow_ema: np.ndarray,
    momentum: np.ndarray,
    volatility: np.ndarray,
    drawdown: np.ndarray,
    params: ExposureSwitchParams,
) -> float:
    trend_ok = fast_ema[index] >= slow_ema[index]
    momentum_value = momentum[index] if not np.isnan(momentum[index]) else 0.0
    momentum_ok = momentum_value >= params.min_momentum_pct
    volatility_ok = True
    if params.max_volatility_pct is not None and not np.isnan(volatility[index]):
        volatility_ok = volatility[index] <= params.max_volatility_pct
    drawdown_ok = True
    if params.max_drawdown_pct is not None and not np.isnan(drawdown[index]):
        drawdown_ok = abs(min(drawdown[index], 0.0)) <= params.max_drawdown_pct
    if trend_ok and momentum_ok and volatility_ok and drawdown_ok:
        return params.risk_on_exposure
    if not trend_ok or not drawdown_ok:
        return params.risk_off_exposure
    return params.base_exposure


def _target_exposure(row: pd.Series, params: ExposureSwitchParams) -> float:
    trend_ok = float(row["fast_ema"]) >= float(row["slow_ema"])
    momentum = float(row["momentum_pct"]) if pd.notna(row["momentum_pct"]) else 0.0
    momentum_ok = momentum >= params.min_momentum_pct
    volatility_ok = True
    if params.max_volatility_pct is not None and pd.notna(row["realized_vol_pct"]):
        volatility_ok = float(row["realized_vol_pct"]) <= params.max_volatility_pct
    drawdown_ok = True
    if params.max_drawdown_pct is not None and pd.notna(row["window_drawdown_pct"]):
        drawdown_ok = abs(min(float(row["window_drawdown_pct"]), 0.0)) <= params.max_drawdown_pct
    if trend_ok and momentum_ok and volatility_ok and drawdown_ok:
        return params.risk_on_exposure
    if not trend_ok or not drawdown_ok:
        return params.risk_off_exposure
    return params.base_exposure


def _score_candidate(metrics: ExposureSwitchMetrics) -> float:
    sharpe = metrics.sharpe_ratio or 0.0
    buy_hold_sharpe = metrics.buy_hold_sharpe_ratio or 0.0
    relative_sharpe = sharpe - buy_hold_sharpe
    drawdown_magnitude = abs(min(metrics.max_drawdown_pct, 0.0))
    buy_hold_drawdown_magnitude = abs(min(metrics.buy_hold_max_drawdown_pct, 0.0))
    drawdown_expansion = max(drawdown_magnitude - buy_hold_drawdown_magnitude, 0.0)
    drawdown_penalty = drawdown_magnitude * 0.15 + drawdown_expansion * 0.5
    exposure_change_penalty = metrics.exposure_changes * 0.1
    return (
        metrics.alpha_vs_buy_hold_pct
        + relative_sharpe * 15
        + sharpe * 3
        - drawdown_penalty
        - exposure_change_penalty
    )


def _quality_flags(
    train: ExposureSwitchMetrics,
    oos: ExposureSwitchMetrics,
    full: ExposureSwitchMetrics,
) -> list[str]:
    flags: list[str] = []
    if train.alpha_vs_buy_hold_pct > 0 and oos.alpha_vs_buy_hold_pct <= 0:
        flags.append("train_oos_alpha_decay")
    if oos.alpha_vs_buy_hold_pct <= 0:
        flags.append("oos_no_alpha_vs_buy_hold")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if (
        oos.sharpe_ratio is not None
        and oos.buy_hold_sharpe_ratio is not None
        and oos.sharpe_ratio < oos.buy_hold_sharpe_ratio
    ):
        flags.append("oos_sharpe_below_buy_hold")
    if full.alpha_vs_buy_hold_pct <= 0:
        flags.append("full_window_no_alpha_vs_buy_hold")
    if _drawdown_expanded(oos.max_drawdown_pct, oos.buy_hold_max_drawdown_pct, multiple=1.5):
        flags.append("oos_drawdown_expansion")
    if _drawdown_expanded(full.max_drawdown_pct, full.buy_hold_max_drawdown_pct, multiple=1.5):
        flags.append("full_window_drawdown_expansion")
    if full.exposure_changes < 1:
        flags.append("single_exposure_path")
    return flags


def _acceptance_gate(
    candidate: ExposureSwitchCandidate,
    walk_forward: list[ExposureSwitchWalkForwardSlice],
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_buy_hold_pct for item in walk_forward]
    positive_wf = sum(value > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    passed = (
        candidate.out_of_sample.alpha_vs_buy_hold_pct > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and (
            candidate.out_of_sample.buy_hold_sharpe_ratio is None
            or (candidate.out_of_sample.sharpe_ratio or 0.0)
            >= candidate.out_of_sample.buy_hold_sharpe_ratio
        )
        and wf_count > 0
        and positive_wf == wf_count
        and not {
            "oos_drawdown_expansion",
            "full_window_drawdown_expansion",
            "single_exposure_path",
        }.intersection(candidate.quality_flags)
    )
    return {
        "passed": passed,
        "objective": "dynamic_exposure_alpha_vs_unlevered_buy_hold",
        "oos_alpha_vs_buy_hold_pct": candidate.out_of_sample.alpha_vs_buy_hold_pct,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_buy_hold_sharpe_ratio": candidate.out_of_sample.buy_hold_sharpe_ratio,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "oos_buy_hold_max_drawdown_pct": candidate.out_of_sample.buy_hold_max_drawdown_pct,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _write_outputs(
    *,
    report_path: Path,
    json_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    candidates: list[ExposureSwitchCandidate],
    walk_forward: list[ExposureSwitchWalkForwardSlice],
    research_cost: ExposureSwitchResearchCost,
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
    params_grid: list[ExposureSwitchParams],
) -> None:
    _write_json(
        json_path,
        strategy_name,
        symbol,
        timeframe,
        start,
        end,
        candidates,
        walk_forward,
        research_cost,
        runtime_seconds,
        data_profile,
        params_grid,
    )
    _write_report(
        report_path,
        json_path,
        strategy_name,
        symbol,
        timeframe,
        start,
        end,
        candidates,
        walk_forward,
        research_cost,
        runtime_seconds,
        data_profile,
    )


def _write_json(
    path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    candidates: list[ExposureSwitchCandidate],
    walk_forward: list[ExposureSwitchWalkForwardSlice],
    research_cost: ExposureSwitchResearchCost,
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
    params_grid: list[ExposureSwitchParams],
) -> Path:
    payload = {
        "strategy_name": strategy_name,
        "mode": "dynamic_exposure_switch_research",
        "symbol": symbol,
        "timeframe": timeframe,
        "research_window": {"start": start, "end": end},
        "data_profile": data_profile,
        "research_brief": research_brief(
            strategy_name=strategy_name,
            objective="dynamic exposure Alpha versus unlevered buy-and-hold",
            hypothesis=(
                "Point-in-time trend, momentum, volatility, and drawdown filters can improve "
                "risk-adjusted exposure versus unlevered buy-and-hold."
            ),
            constraints=[
                "Exposure uses indicators known at the previous bar close.",
                "Fills occur at current bar open and mark at next bar open or final close.",
                "This command emits research reports only and no paper/live orders.",
            ],
        ),
        "search_space": search_space(
            family="dynamic_exposure_switch",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=["fast_bars < slow_bars", "risk_on >= base >= risk_off"],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis="Dynamic exposure improves OOS Alpha without hidden future data.",
            visible_evidence=["training score", "OOS metrics", "walk-forward folds"],
            hidden_evidence=[],
            counterevidence=candidates[0].quality_flags,
            conclusion=(
                "passed" if _acceptance_gate(candidates[0], walk_forward)["passed"] else "failed"
            ),
        ),
        "research_cost": research_cost.__dict__,
        "runtime_seconds": runtime_seconds,
        "selection_objective": (
            "training score selects a point-in-time exposure switching rule; final OOS and "
            "walk-forward validate Alpha, Sharpe, and drawdown versus unlevered buy-and-hold; "
            "each walk-forward fold chooses on a trailing validation slice inside its "
            "training prefix"
        ),
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward),
        "assumptions": [
            "Exposure for each bar is chosen from indicators available at the previous bar close.",
            (
                "Exposure is filled at the current bar open and marked at the next bar open, "
                "or final close."
            ),
            "Financing drag is charged per bar on exposure above 1x.",
            "This research command emits no paper or live orders.",
        ],
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_forward_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_report(
    path: Path,
    json_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    candidates: list[ExposureSwitchCandidate],
    walk_forward: list[ExposureSwitchWalkForwardSlice],
    research_cost: ExposureSwitchResearchCost,
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Exposure Switch Research: {strategy_name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbol: `{symbol}`",
        f"- Timeframe: `{timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{data_profile.get('provider') or 'unknown'}` / "
        f"`{data_profile.get('feed') or 'unknown'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        "- Objective: dynamic exposure Alpha over unlevered buy-and-hold with risk gates.",
        "- Anti-leakage: each bar's exposure uses only indicators known at the prior bar close.",
        (
            "- Walk-forward fold selection uses a trailing validation slice inside the "
            "training prefix."
        ),
        "",
        "## Research Cost",
        "",
        f"- Candidates evaluated: `{research_cost.candidate_count}`",
        f"- Walk-forward candidates: `{research_cost.walk_forward_candidate_count}`",
        f"- Walk-forward top-K filter: `{research_cost.walk_forward_top_k or 'off'}`",
        f"- Walk-forward folds: `{research_cost.walk_forward_folds}`",
        (f"- Estimated backtest passes: `{research_cost.estimated_total_backtest_passes}`"),
        (f"- Candidate evaluation passes: `{research_cost.estimated_candidate_evaluation_passes}`"),
        (
            "- Walk-forward validation passes: "
            f"`{research_cost.estimated_walk_forward_validation_passes}`"
        ),
        (
            "- Walk-forward selected train/test passes: "
            f"`{research_cost.estimated_walk_forward_selected_passes}`"
        ),
        f"- Runtime total seconds: `{runtime_seconds['total']:.2f}`",
        "",
        "## Runtime Stages",
        "",
        *[f"- {stage}: `{seconds:.2f}s`" for stage, seconds in runtime_seconds["stages"].items()],
        "",
        "## Acceptance Gate",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _acceptance_gate(candidates[0], walk_forward).items()
        ],
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: ExposureSwitchCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_forward_payload(item: ExposureSwitchWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _metric_lines(label: str, metrics: ExposureSwitchMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} buy-hold: `{metrics.buy_hold_return_pct:.2f}%`",
        f"- {label} Alpha vs buy-hold: `{metrics.alpha_vs_buy_hold_pct:.2f}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} buy-hold Sharpe: `{_fmt(metrics.buy_hold_sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} buy-hold max drawdown: `{metrics.buy_hold_max_drawdown_pct:.2f}%`",
        f"- {label} average exposure: `{metrics.average_exposure:.2f}`",
        f"- {label} max exposure: `{metrics.max_exposure:.2f}`",
        f"- {label} exposure changes: `{metrics.exposure_changes}`",
        f"- {label} financing cost: `{metrics.financing_cost_pct:.2f}%`",
    ]


def _split_index(
    frame: pd.DataFrame,
    out_of_sample_ratio: float,
    max_warmup: int,
) -> int:
    split = int(len(frame) * (1 - out_of_sample_ratio))
    split = max(split, max_warmup + 3)
    return min(split, len(frame) - 2)


def _warmup(params: ExposureSwitchParams) -> int:
    return max(
        params.slow_bars,
        params.momentum_bars,
        params.volatility_bars,
        params.drawdown_bars,
    )


def _max_warmup(params_grid: list[ExposureSwitchParams]) -> int:
    return max(_warmup(item) for item in params_grid)


def _financing_per_bar(financing_rate_pct: float, timeframe: str) -> float:
    return financing_rate_pct / 100 / _bars_per_year(timeframe)


def _bars_per_year(timeframe: str) -> float:
    mapping = {
        "5m": 252 * 78,
        "15m": 252 * 26,
        "1h": 252 * 6.5,
        "daily": 252,
        "weekly": 52,
    }
    return float(mapping.get(timeframe, 252))


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak <= 0:
            continue
        max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return max_drawdown


def _drawdown_expanded(
    strategy_drawdown_pct: float,
    buy_hold_drawdown_pct: float,
    *,
    multiple: float,
) -> bool:
    strategy_magnitude = abs(min(strategy_drawdown_pct, 0.0))
    buy_hold_magnitude = abs(min(buy_hold_drawdown_pct, 0.0))
    if buy_hold_magnitude <= 0:
        return strategy_magnitude > 0
    return strategy_magnitude > buy_hold_magnitude * multiple


def _normalize_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    return normalized.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


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
    return filtered.reset_index(drop=True)


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _empty_metrics(frame: pd.DataFrame) -> ExposureSwitchMetrics:
    return ExposureSwitchMetrics(
        bars=len(frame),
        start_timestamp=frame["timestamp"].iloc[0].isoformat() if len(frame) else None,
        end_timestamp=frame["timestamp"].iloc[-1].isoformat() if len(frame) else None,
        total_return_pct=0.0,
        buy_hold_return_pct=0.0,
        alpha_vs_buy_hold_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        buy_hold_sharpe_ratio=None,
        max_drawdown_pct=0.0,
        buy_hold_max_drawdown_pct=0.0,
        average_exposure=0.0,
        max_exposure=0.0,
        exposure_changes=0,
        financing_cost_pct=0.0,
    )


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
