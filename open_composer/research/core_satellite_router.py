from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

import numpy as np
import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.json_utils import json_safe_sorted_values
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.metadata import (
    combined_data_profile,
    frame_data_profile,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json

SatelliteAsset = Literal["TQQQ", "QLD"]


@dataclass(frozen=True)
class CoreSatelliteParams:
    trend_sma_days: int
    momentum_lookback_days: int
    min_momentum_pct: float
    volatility_lookback_days: int
    max_volatility_annual_pct: float | None
    drawdown_lookback_days: int
    max_drawdown_pct: float | None
    core_weight: float
    satellite_symbol: SatelliteAsset
    satellite_weight: float
    risk_off_core_scale: float
    target_satellite_volatility_pct: float | None
    rebalance_threshold_pct: float

    @property
    def label(self) -> str:
        return (
            f"core_sat:sma{self.trend_sma_days}_mom{self.momentum_lookback_days}_"
            f"min{self.min_momentum_pct:g}_vol{self.volatility_lookback_days}_"
            f"maxv{_label_optional(self.max_volatility_annual_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{_label_optional(self.max_drawdown_pct)}_"
            f"core{self.core_weight:g}_sat{self.satellite_symbol}{self.satellite_weight:g}_"
            f"off{self.risk_off_core_scale:g}_"
            f"tvol{_label_optional(self.target_satellite_volatility_pct)}_"
            f"thr{self.rebalance_threshold_pct:g}"
        )


@dataclass(frozen=True)
class CoreSatelliteMetrics:
    days: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    annualized_volatility_pct: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    max_drawdown_pct: float
    qqq_buy_hold_return_pct: float
    qqq_buy_hold_annualized_pct: float | None
    alpha_vs_qqq_buy_hold_annualized_pct: float | None
    satellite_symbol: str
    satellite_buy_hold_return_pct: float
    satellite_buy_hold_annualized_pct: float | None
    alpha_vs_satellite_buy_hold_annualized_pct: float | None
    cash_proxy_return_pct: float
    exposure_pct: float
    average_gross_exposure_pct: float
    max_gross_exposure_pct: float
    rebalance_count: int
    turnover_ratio: float
    cost_drag_pct: float
    risk_on_days: int
    core_only_days: int
    risk_off_days: int


@dataclass(frozen=True)
class CoreSatelliteCandidate:
    rank: int
    params: CoreSatelliteParams
    score: float
    train: CoreSatelliteMetrics
    out_of_sample: CoreSatelliteMetrics
    full_window: CoreSatelliteMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class CoreSatelliteWalkForwardSlice:
    fold: int
    params: CoreSatelliteParams
    train: CoreSatelliteMetrics
    test: CoreSatelliteMetrics


@dataclass(frozen=True)
class CoreSatelliteResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


@dataclass(frozen=True)
class CoreSatelliteDataset:
    frame: pd.DataFrame
    dates: list[str]
    data_profile: dict[str, Any]


@dataclass(frozen=True)
class CoreSatelliteSnapshot:
    state: str
    weights: dict[str, float]
    satellite_volatility_scale: float
    trend_ok: bool
    momentum_ok: bool
    volatility_ok: bool
    drawdown_ok: bool


def run_core_satellite_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    satellite_symbols: list[str] | None = None,
    trend_sma_days: list[int] | None = None,
    momentum_lookback_days: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    volatility_lookback_days: list[int] | None = None,
    max_volatility_annual_pct: list[float | None] | None = None,
    drawdown_lookback_days: list[int] | None = None,
    max_drawdown_pct: list[float | None] | None = None,
    core_weight: list[float] | None = None,
    satellite_weight: list[float] | None = None,
    risk_off_core_scale: list[float] | None = None,
    target_satellite_volatility_pct: list[float | None] | None = None,
    rebalance_threshold_pct: list[float] | None = None,
    out_of_sample_ratio: float = 0.35,
    walk_forward_folds: int = 5,
    walk_forward_top_k: int | None = 20,
    max_candidates: int = 900,
    refresh_data: bool = False,
) -> CoreSatelliteResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    dataset = load_core_satellite_dataset(
        root=base,
        data_source=data_source,
        feed=selected_feed,
        timeframe=spec.timeframe,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    params_grid = _build_params_grid(
        trend_sma_days or [100, 150, 200],
        momentum_lookback_days or [60, 120],
        min_momentum_pct or [0.0, 3.0],
        volatility_lookback_days or [20, 60],
        max_volatility_annual_pct or [None, 30.0, 40.0],
        drawdown_lookback_days or [60, 120],
        max_drawdown_pct or [None, 15.0, 20.0],
        core_weight or [0.5, 0.6, 0.7],
        _satellite_assets(satellite_symbols) or ["TQQQ", "QLD"],
        satellite_weight or [0.1, 0.2, 0.3],
        risk_off_core_scale or [0.0, 0.25, 0.5, 0.75],
        target_satellite_volatility_pct or [None, 35.0, 45.0],
        rebalance_threshold_pct or [0.0, 5.0],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started

    stage_started = perf_counter()
    cache = _build_indicator_cache(dataset)
    candidates = _evaluate_candidates(
        spec=spec,
        dataset=dataset,
        cache=cache,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    walk_params = _walk_forward_params(
        params_grid=params_grid,
        candidates=candidates,
        walk_forward_top_k=walk_forward_top_k,
    )
    walk_forward = _walk_forward(
        spec=spec,
        dataset=dataset,
        cache=cache,
        params_grid=walk_params,
        folds=walk_forward_folds,
    )
    pass_status = _pass_status(candidates[0], walk_forward)
    stages["research"] = perf_counter() - stage_started

    json_path = base / "reports" / "research" / f"{spec.name}-core-satellite-router.json"
    report_path = json_path.with_suffix(".md")
    payload = _payload(
        spec=spec,
        spec_path=spec_path,
        dataset=dataset,
        params_grid=params_grid,
        candidates=candidates,
        walk_forward=walk_forward,
        pass_status=pass_status,
        start=start,
        end=end,
        runtime=runtime_payload(started_at, stages),
        walk_forward_top_k=walk_forward_top_k,
    )
    write_json(json_path, payload)
    _write_report(report_path, json_path, payload)
    return CoreSatelliteResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=candidates[0].params.label,
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def load_core_satellite_dataset(
    *,
    root: Path,
    data_source: str,
    feed: str | None,
    timeframe: str,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> CoreSatelliteDataset:
    symbols = ["QQQ", "TQQQ", "QLD"]
    frames = {
        symbol: _load_symbol_frame(
            root=root,
            symbol=symbol,
            timeframe=timeframe,
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        )
        for symbol in symbols
    }
    frame = (
        frames["QQQ"][["timestamp", "open", "close"]]
        .rename(columns={"open": "QQQ_open", "close": "QQQ_close"})
        .merge(
            frames["TQQQ"][["timestamp", "open", "close"]].rename(
                columns={"open": "TQQQ_open", "close": "TQQQ_close"}
            ),
            on="timestamp",
            how="inner",
        )
        .merge(
            frames["QLD"][["timestamp", "open", "close"]].rename(
                columns={"open": "QLD_open", "close": "QLD_close"}
            ),
            on="timestamp",
            how="inner",
        )
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    if len(frame) < 260:
        raise ValueError("core satellite router requires at least 260 common daily bars")
    dates = [
        pd.Timestamp(value).tz_convert("America/New_York").date().isoformat()
        for value in frame["timestamp"]
    ]
    profiles = [
        frame_data_profile(
            frames[symbol],
            symbol=symbol,
            timeframe=timeframe,
            provider=data_source,
            feed=feed,
            source_mode=frames[symbol].attrs.get("data_source_mode"),
            path=frames[symbol].attrs.get("data_source_path"),
        )
        for symbol in symbols
    ]
    return CoreSatelliteDataset(
        frame=frame,
        dates=dates,
        data_profile=combined_data_profile(profiles),
    )


def core_satellite_params_from_label(label: str) -> CoreSatelliteParams:
    if not label.startswith("core_sat:"):
        raise ValueError(f"not a core satellite route label: {label}")
    raw: dict[str, str] = {}
    for part in label.removeprefix("core_sat:").split("_"):
        for prefix in [
            "sma",
            "mom",
            "min",
            "vol",
            "maxv",
            "dd",
            "maxdd",
            "core",
            "sat",
            "off",
            "tvol",
            "thr",
        ]:
            if part.startswith(prefix):
                raw[prefix] = part.removeprefix(prefix)
                break
    satellite_symbol, satellite_weight_value = _parse_satellite_weight(raw["sat"])
    return CoreSatelliteParams(
        trend_sma_days=int(raw["sma"]),
        momentum_lookback_days=int(raw["mom"]),
        min_momentum_pct=float(raw["min"]),
        volatility_lookback_days=int(raw["vol"]),
        max_volatility_annual_pct=_parse_optional_float(raw["maxv"]),
        drawdown_lookback_days=int(raw["dd"]),
        max_drawdown_pct=_parse_optional_float(raw["maxdd"]),
        core_weight=float(raw["core"]),
        satellite_symbol=satellite_symbol,
        satellite_weight=satellite_weight_value,
        risk_off_core_scale=float(raw["off"]),
        target_satellite_volatility_pct=_parse_optional_float(raw["tvol"]),
        rebalance_threshold_pct=float(raw["thr"]),
    )


def core_satellite_target_weight_snapshot(
    dataset: CoreSatelliteDataset,
    params: CoreSatelliteParams,
    index: int,
) -> CoreSatelliteSnapshot:
    cache = _build_indicator_cache(dataset)
    return _target_snapshot(dataset, cache, params, index)


def _load_symbol_frame(
    *,
    root: Path,
    symbol: str,
    timeframe: str,
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> pd.DataFrame:
    frame = fetch_ohlcv(
        root=root,
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=_parse_research_datetime(start),
        end=_parse_research_datetime(end),
        source=data_source,
        feed=feed,
        use_cache=not refresh_data,
        allow_fallback=False,
    )
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if start:
        frame = frame[frame["timestamp"] >= _parse_research_datetime(start)]
    if end:
        frame = frame[frame["timestamp"] <= _parse_research_datetime(end)]
    return frame.sort_values("timestamp").reset_index(drop=True)


def _build_params_grid(
    trend_values: list[int],
    momentum_values: list[int],
    min_momentum_values: list[float],
    volatility_values: list[int],
    max_volatility_values: list[float | None],
    drawdown_values: list[int],
    max_drawdown_values: list[float | None],
    core_values: list[float],
    satellite_symbols: list[SatelliteAsset],
    satellite_values: list[float],
    risk_off_values: list[float],
    target_satellite_volatility_values: list[float | None],
    rebalance_threshold_values: list[float],
    *,
    max_candidates: int,
) -> list[CoreSatelliteParams]:
    total = math.prod(
        [
            len(trend_values),
            len(momentum_values),
            len(min_momentum_values),
            len(volatility_values),
            len(max_volatility_values),
            len(drawdown_values),
            len(max_drawdown_values),
            len(core_values),
            len(satellite_symbols),
            len(satellite_values),
            len(risk_off_values),
            len(target_satellite_volatility_values),
            len(rebalance_threshold_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"core satellite router grid would create {total} candidates; raise "
            f"--max-candidates above {total} or narrow the grid"
        )
    params: list[CoreSatelliteParams] = []
    for item in product(
        trend_values,
        momentum_values,
        min_momentum_values,
        volatility_values,
        max_volatility_values,
        drawdown_values,
        max_drawdown_values,
        core_values,
        satellite_symbols,
        satellite_values,
        risk_off_values,
        target_satellite_volatility_values,
        rebalance_threshold_values,
    ):
        (
            trend,
            momentum,
            min_momentum,
            volatility,
            max_volatility,
            drawdown,
            max_drawdown,
            core,
            satellite_symbol,
            satellite,
            risk_off,
            target_volatility,
            rebalance_threshold,
        ) = item
        if min(trend, momentum, volatility, drawdown) < 1:
            continue
        if min(core, satellite, risk_off, rebalance_threshold) < 0:
            continue
        if max(core, satellite, risk_off) > 1.0:
            continue
        if core + satellite > 1.0:
            continue
        params.append(
            CoreSatelliteParams(
                trend_sma_days=trend,
                momentum_lookback_days=momentum,
                min_momentum_pct=min_momentum,
                volatility_lookback_days=volatility,
                max_volatility_annual_pct=max_volatility,
                drawdown_lookback_days=drawdown,
                max_drawdown_pct=max_drawdown,
                core_weight=core,
                satellite_symbol=satellite_symbol,
                satellite_weight=satellite,
                risk_off_core_scale=risk_off,
                target_satellite_volatility_pct=target_volatility,
                rebalance_threshold_pct=rebalance_threshold,
            )
        )
    if not params:
        raise ValueError("core satellite grid produced no valid candidates")
    return params


def _build_indicator_cache(dataset: CoreSatelliteDataset) -> dict[str, Any]:
    frame = dataset.frame
    qqq_close = frame["QQQ_close"].to_numpy(dtype=float)
    qqq_open = frame["QQQ_open"].to_numpy(dtype=float)
    tqqq_close = frame["TQQQ_close"].to_numpy(dtype=float)
    tqqq_open = frame["TQQQ_open"].to_numpy(dtype=float)
    qld_close = frame["QLD_close"].to_numpy(dtype=float)
    qld_open = frame["QLD_open"].to_numpy(dtype=float)
    return {
        "QQQ_close": qqq_close,
        "QQQ_open": qqq_open,
        "TQQQ_close": tqqq_close,
        "TQQQ_open": tqqq_open,
        "QLD_close": qld_close,
        "QLD_open": qld_open,
        "QQQ_open_return": _next_open_returns(qqq_open),
        "TQQQ_open_return": _next_open_returns(tqqq_open),
        "QLD_open_return": _next_open_returns(qld_open),
        "sma": {},
        "momentum": {},
        "qqq_volatility": {},
        "satellite_volatility": {},
        "drawdown": {},
    }


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: CoreSatelliteDataset,
    cache: dict[str, Any],
    params_grid: list[CoreSatelliteParams],
    out_of_sample_ratio: float,
) -> list[CoreSatelliteCandidate]:
    split = _split_index(len(dataset.frame), out_of_sample_ratio, params_grid)
    rows: list[CoreSatelliteCandidate] = []
    for params in params_grid:
        train = _backtest_params(spec, dataset, cache, params, start_index=0, end_index=split)
        oos = _backtest_params(
            spec,
            dataset,
            cache,
            params,
            start_index=max(0, split - _effective_lookback(params) - 1),
            end_index=len(dataset.frame) - 1,
            evaluation_start_index=split,
        )
        full = _backtest_params(
            spec,
            dataset,
            cache,
            params,
            start_index=0,
            end_index=len(dataset.frame) - 1,
        )
        rows.append(
            CoreSatelliteCandidate(
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
        CoreSatelliteCandidate(
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
    params_grid: list[CoreSatelliteParams],
    candidates: list[CoreSatelliteCandidate],
    walk_forward_top_k: int | None,
) -> list[CoreSatelliteParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: CoreSatelliteDataset,
    cache: dict[str, Any],
    params_grid: list[CoreSatelliteParams],
    folds: int,
) -> list[CoreSatelliteWalkForwardSlice]:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.frame) - max_lookback) // (max(folds, 1) + 1), 20)
    rows: list[CoreSatelliteWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.frame) - 1, test_start + fold_size)
        if test_end - test_start < 20:
            continue
        scored: list[tuple[float, CoreSatelliteParams]] = []
        for params in params_grid:
            train = _backtest_params(
                spec,
                dataset,
                cache,
                params,
                start_index=0,
                end_index=test_start,
            )
            scored.append((_score_candidate(train), params))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        rows.append(
            CoreSatelliteWalkForwardSlice(
                fold=fold,
                params=selected,
                train=_backtest_params(
                    spec,
                    dataset,
                    cache,
                    selected,
                    start_index=0,
                    end_index=test_start,
                ),
                test=_backtest_params(
                    spec,
                    dataset,
                    cache,
                    selected,
                    start_index=max(0, test_start - _effective_lookback(selected) - 1),
                    end_index=test_end,
                    evaluation_start_index=test_start,
                ),
            )
        )
    return rows


def _backtest_params(
    spec: StrategySpec,
    dataset: CoreSatelliteDataset,
    cache: dict[str, Any],
    params: CoreSatelliteParams,
    *,
    start_index: int,
    end_index: int,
    evaluation_start_index: int | None = None,
    start_equity: float = 100_000.0,
) -> CoreSatelliteMetrics:
    start_index = max(start_index, _effective_lookback(params) + 1)
    if evaluation_start_index is not None:
        start_index = max(start_index, evaluation_start_index)
    end_index = min(end_index, len(dataset.frame) - 1)
    if end_index <= start_index:
        return _empty_metrics(dataset, params.satellite_symbol, start_index, end_index)

    equity = start_equity
    curve = [equity]
    returns: list[float] = []
    gross_exposures: list[float] = []
    states: list[str] = []
    previous_weights = {"QQQ": 0.0, params.satellite_symbol: 0.0}
    rebalance_count = 0
    turnover_ratio = 0.0
    cost_drag = 0.0
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    threshold = params.rebalance_threshold_pct / 100

    for index in range(start_index, end_index):
        snapshot = _target_snapshot(dataset, cache, params, index)
        weights = {
            "QQQ": snapshot.weights.get("QQQ", 0.0),
            params.satellite_symbol: snapshot.weights.get(params.satellite_symbol, 0.0),
        }
        raw_turnover = sum(
            abs(weights[symbol] - previous_weights.get(symbol, 0.0)) for symbol in weights
        )
        if threshold > 0 and raw_turnover < threshold:
            weights = previous_weights.copy()
            turnover = 0.0
        else:
            turnover = raw_turnover
        if turnover > 1e-12:
            rebalance_count += 1
        turnover_ratio += turnover
        cost = turnover * cost_rate
        period_return = (
            weights["QQQ"] * float(cache["QQQ_open_return"][index])
            + weights[params.satellite_symbol]
            * float(cache[f"{params.satellite_symbol}_open_return"][index])
            - cost
        )
        equity *= 1 + period_return
        curve.append(equity)
        returns.append(period_return)
        gross_exposures.append(sum(abs(value) for value in weights.values()))
        states.append(snapshot.state)
        previous_weights = weights
        cost_drag += cost
        if equity <= 0:
            break

    metrics = build_performance_metrics(curve, spec.timeframe)
    days = len(returns)
    qqq_buy_hold = _buy_hold_return(dataset, "QQQ", start_index, end_index)
    satellite_buy_hold = _buy_hold_return(dataset, params.satellite_symbol, start_index, end_index)
    qqq_ann = _annualized_from_total(qqq_buy_hold, days)
    satellite_ann = _annualized_from_total(satellite_buy_hold, days)
    annualized = metrics.annualized_return_pct
    return CoreSatelliteMetrics(
        days=days,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index - 1] if end_index - 1 < len(dataset.dates) else None,
        total_return_pct=(equity / start_equity - 1) * 100,
        annualized_return_pct=annualized,
        sharpe_ratio=metrics.sharpe_ratio,
        annualized_volatility_pct=metrics.annualized_volatility_pct,
        sortino_ratio=metrics.sortino_ratio,
        calmar_ratio=metrics.calmar_ratio,
        max_drawdown_pct=metrics.max_drawdown_pct,
        qqq_buy_hold_return_pct=qqq_buy_hold,
        qqq_buy_hold_annualized_pct=qqq_ann,
        alpha_vs_qqq_buy_hold_annualized_pct=_alpha(annualized, qqq_ann),
        satellite_symbol=params.satellite_symbol,
        satellite_buy_hold_return_pct=satellite_buy_hold,
        satellite_buy_hold_annualized_pct=satellite_ann,
        alpha_vs_satellite_buy_hold_annualized_pct=_alpha(annualized, satellite_ann),
        cash_proxy_return_pct=0.0,
        exposure_pct=sum(1 for value in gross_exposures if value > 0) / days * 100 if days else 0.0,
        average_gross_exposure_pct=mean(gross_exposures) * 100 if gross_exposures else 0.0,
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        rebalance_count=rebalance_count,
        turnover_ratio=turnover_ratio,
        cost_drag_pct=cost_drag * 100,
        risk_on_days=sum(1 for item in states if item == "risk_on"),
        core_only_days=sum(1 for item in states if item == "core_only"),
        risk_off_days=sum(1 for item in states if item == "risk_off"),
    )


def _target_snapshot(
    dataset: CoreSatelliteDataset,
    cache: dict[str, Any],
    params: CoreSatelliteParams,
    index: int,
) -> CoreSatelliteSnapshot:
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    qqq_close = cache["QQQ_close"]
    trend_sma = _cached_sma(cache, params.trend_sma_days)
    momentum = _cached_momentum(cache, params.momentum_lookback_days)
    qqq_volatility = _cached_qqq_volatility(cache, params.volatility_lookback_days)
    drawdown = _cached_drawdown(cache, params.drawdown_lookback_days)
    trend_ok = bool(qqq_close[previous_index] > trend_sma[previous_index])
    momentum_value = momentum[previous_index]
    momentum_ok = bool(not np.isnan(momentum_value) and momentum_value >= params.min_momentum_pct)
    volatility_value = qqq_volatility[previous_index]
    volatility_ok = True
    if params.max_volatility_annual_pct is not None and not np.isnan(volatility_value):
        volatility_ok = bool(volatility_value <= params.max_volatility_annual_pct)
    drawdown_value = drawdown[previous_index]
    drawdown_ok = True
    if params.max_drawdown_pct is not None and not np.isnan(drawdown_value):
        drawdown_ok = bool(abs(min(float(drawdown_value), 0.0)) <= params.max_drawdown_pct)

    if trend_ok and momentum_ok and volatility_ok and drawdown_ok:
        satellite_scale = _satellite_volatility_scale(dataset, cache, params, index)
        weights = {
            "QQQ": params.core_weight,
            params.satellite_symbol: params.satellite_weight * satellite_scale,
        }
        weights = _cap_gross(weights)
        return CoreSatelliteSnapshot(
            state="risk_on",
            weights=weights,
            satellite_volatility_scale=satellite_scale,
            trend_ok=trend_ok,
            momentum_ok=momentum_ok,
            volatility_ok=volatility_ok,
            drawdown_ok=drawdown_ok,
        )
    if trend_ok and drawdown_ok:
        return CoreSatelliteSnapshot(
            state="core_only",
            weights={"QQQ": params.core_weight},
            satellite_volatility_scale=0.0,
            trend_ok=trend_ok,
            momentum_ok=momentum_ok,
            volatility_ok=volatility_ok,
            drawdown_ok=drawdown_ok,
        )
    return CoreSatelliteSnapshot(
        state="risk_off",
        weights={"QQQ": params.core_weight * params.risk_off_core_scale},
        satellite_volatility_scale=0.0,
        trend_ok=trend_ok,
        momentum_ok=momentum_ok,
        volatility_ok=volatility_ok,
        drawdown_ok=drawdown_ok,
    )


def _satellite_volatility_scale(
    dataset: CoreSatelliteDataset,
    cache: dict[str, Any],
    params: CoreSatelliteParams,
    index: int,
) -> float:
    if params.target_satellite_volatility_pct is None:
        return 1.0
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    volatility = _cached_satellite_volatility(
        cache,
        params.satellite_symbol,
        params.volatility_lookback_days,
    )
    value = volatility[previous_index]
    if np.isnan(value) or value <= 0:
        return 1.0
    return max(0.0, min(1.0, params.target_satellite_volatility_pct / float(value)))


def _score_candidate(metrics: CoreSatelliteMetrics) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    alpha = metrics.alpha_vs_qqq_buy_hold_annualized_pct or -100.0
    drawdown_penalty = abs(min(metrics.max_drawdown_pct, 0.0)) * 0.45
    turnover_penalty = max(0, metrics.rebalance_count - 80) * 0.06
    high_sharpe_penalty = max(0.0, sharpe - 2.2) * 30
    sparse_penalty = max(0.0, 35.0 - metrics.exposure_pct) * 0.35
    low_return_penalty = max(0.0, 8.0 - annualized) * 0.5
    return (
        alpha
        + annualized * 0.3
        + min(sharpe, 2.2) * 10
        - drawdown_penalty
        - turnover_penalty
        - high_sharpe_penalty
        - sparse_penalty
        - low_return_penalty
    )


def _quality_flags(
    train: CoreSatelliteMetrics,
    oos: CoreSatelliteMetrics,
    full: CoreSatelliteMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq")
    if (oos.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq")
    if (full.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        flags.append("oos_low_sharpe")
    if oos.max_drawdown_pct <= -28:
        flags.append("oos_large_drawdown")
    if full.max_drawdown_pct <= -32:
        flags.append("full_large_drawdown")
    if full.rebalance_count > max(80, full.days // 4):
        flags.append("high_turnover")
    if (train.sharpe_ratio or 0.0) > 2.2 or (oos.sharpe_ratio or 0.0) > 2.2:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if oos.exposure_pct < 35:
        flags.append("oos_too_sparse")
    return flags


def _acceptance_gate(
    candidate: CoreSatelliteCandidate,
    walk_forward: list[CoreSatelliteWalkForwardSlice],
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_qqq_buy_hold_annualized_pct for item in walk_forward]
    wf_positive = sum((value or -100.0) > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    oos_sharpe = candidate.out_of_sample.sharpe_ratio or 0.0
    full_sharpe = candidate.full_window.sharpe_ratio or 0.0
    passed = (
        (candidate.train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.annualized_return_pct or -100.0) >= 12
        and 0.7 <= oos_sharpe <= 2.2
        and full_sharpe <= 2.2
        and candidate.out_of_sample.max_drawdown_pct > -28
        and candidate.full_window.max_drawdown_pct > -32
        and candidate.full_window.max_gross_exposure_pct <= 100
        and candidate.full_window.rebalance_count <= max(80, candidate.full_window.days // 4)
        and wf_count > 0
        and wf_positive >= max(1, math.ceil(wf_count * 0.6))
        and not {"oos_too_sparse", "suspiciously_high_sharpe_review_overfit"}.intersection(
            candidate.quality_flags
        )
    )
    return {
        "passed": passed,
        "objective": "core_satellite_alpha_vs_qqq_buy_hold_after_costs",
        "train_alpha_vs_qqq_annualized_pct": (candidate.train.alpha_vs_qqq_buy_hold_annualized_pct),
        "oos_alpha_vs_qqq_annualized_pct": (
            candidate.out_of_sample.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "full_alpha_vs_qqq_annualized_pct": (
            candidate.full_window.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "oos_annualized_return_pct": candidate.out_of_sample.annualized_return_pct,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "full_sharpe_ratio": candidate.full_window.sharpe_ratio,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "full_max_drawdown_pct": candidate.full_window.max_drawdown_pct,
        "full_rebalance_count": candidate.full_window.rebalance_count,
        "full_turnover_ratio": candidate.full_window.turnover_ratio,
        "walk_forward_positive_alpha_folds": wf_positive,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _pass_status(
    candidate: CoreSatelliteCandidate,
    walk_forward: list[CoreSatelliteWalkForwardSlice],
) -> dict[str, Any]:
    gate = _acceptance_gate(candidate, walk_forward)
    blockers = [
        "draft/manual_signal strategy only",
        "Alpaca IEX/cache evidence is not consolidated live SIP evidence",
        "promotion report and strict paper readiness still required before paper_auto",
        "LLM/news is advisory only; no independent LLM Alpha is claimed",
    ]
    if not gate["passed"]:
        blockers.insert(0, "research acceptance gate failed")
    return {
        "workflow_pass": True,
        "research_pass": bool(gate["passed"]),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_ready_blockers": blockers,
    }


def _payload(
    *,
    spec: StrategySpec,
    spec_path: Path,
    dataset: CoreSatelliteDataset,
    params_grid: list[CoreSatelliteParams],
    candidates: list[CoreSatelliteCandidate],
    walk_forward: list[CoreSatelliteWalkForwardSlice],
    pass_status: dict[str, Any],
    start: str | None,
    end: str | None,
    runtime: dict[str, Any],
    walk_forward_top_k: int | None,
) -> dict[str, Any]:
    return {
        "strategy_name": spec.name,
        "mode": "core_satellite_router",
        "source_spec_path": _relpath(spec_path, spec_path.parents[2]),
        "market_symbol": "QQQ",
        "satellite_symbols": ["TQQQ", "QLD"],
        "research_window": {"start": start, "end": end},
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective="risk-managed Alpha versus QQQ buy-and-hold",
            hypothesis=(
                "A persistent QQQ core position plus bounded leveraged ETF satellite exposure "
                "can retain recent-cycle upside while reducing crash exposure versus all-in "
                "leveraged beta."
            ),
            constraints=[
                "Signals use only QQQ information visible after the previous daily close.",
                "Target weights are applied at the next regular-session open.",
                "Gross exposure is capped at 100%; no shorts or margin are used.",
                "LLM/news is review context only and not an execution factor.",
            ],
        ),
        "search_space": search_space(
            family="core_satellite_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "core_weight + satellite_weight <= 100%",
                "satellite_symbol in TQQQ or QLD",
                "train-only ranking; OOS and walk-forward are validation",
                "rebalance threshold may suppress tiny weight changes",
            ],
        ),
        "references": [
            {
                "title": "Time Series Momentum",
                "url": "https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf",
                "used_for": "trend and absolute-momentum regime framing",
            },
            {
                "title": "Momentum Has Its Moments",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "used_for": "volatility-managed momentum risk control",
            },
            {
                "title": "Absolute Momentum",
                "url": "https://ssrn.com/abstract=2244633",
                "used_for": "absolute momentum defensive switch",
            },
            {
                "title": "A Century of Evidence on Trend-Following Investing",
                "url": "https://www.aqr.com/Insights/Research/White-Papers/A-Century-of-Evidence-on-Trend-Following-Investing",
                "used_for": "trend-following robustness framing",
            },
        ],
        "anti_leakage": [
            "Each target uses index-1 QQQ close-derived indicators.",
            "Backtest return is open[index] to open[index+1], after the signal close.",
            "Walk-forward folds reselect parameters only from earlier data.",
            "OOS metrics never enter the training score.",
        ],
        "known_limits": [
            "TQQQ did not trade before 2010; current cache may start later unless refreshed.",
            "Alpaca IEX/free data is not consolidated market data.",
            "Cash proxy is modeled at 0% return.",
            "ETF distributions, taxes, and market-impact beyond linear costs are not modeled.",
        ],
        "selection_objective": (
            "Training score prioritizes annualized Alpha versus QQQ, moderate Sharpe, "
            "controlled drawdown, and bounded turnover; validation gates are separate."
        ),
        "acceptance_standard": {
            "train_oos_full_alpha_vs_qqq_annualized_pct": "> 0",
            "oos_annualized_return_pct": ">= 12",
            "oos_sharpe_ratio": "0.7 to 2.2",
            "max_drawdown_pct": "OOS > -28 and full > -32",
            "walk_forward": "at least 60% positive Alpha folds",
            "turnover": "full rebalances <= max(80, days / 4)",
            "paper_ready_pass": "always false until promotion/readiness evidence passes",
        },
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward),
        "pass_status": pass_status,
        "research_cost": {
            "candidate_count": len(params_grid),
            "walk_forward_candidate_count": len(
                _walk_forward_params(
                    params_grid=params_grid,
                    candidates=candidates,
                    walk_forward_top_k=walk_forward_top_k,
                )
            ),
            "walk_forward_top_k": walk_forward_top_k,
            "walk_forward_folds": len(walk_forward),
        },
        "runtime_seconds": runtime,
        "selected_route_label": candidates[0].params.label,
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_payload(item) for item in walk_forward],
    }


def _write_report(path: Path, json_path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    gate = payload["acceptance_gate"]
    status = payload["pass_status"]
    top = payload["candidates"][0]
    lines = [
        f"# Core Satellite Router Research: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Research window: `{payload['research_window']['start'] or 'cache start'}` -> "
        f"`{payload['research_window']['end'] or 'cache end'}`",
        f"- Selected route: `{payload['selected_route_label']}`",
        f"- Research pass: `{status['research_pass']}`",
        f"- Paper ready pass: `{status['paper_ready_pass']}`",
        "- Signal timing: previous daily close indicators; next regular-session open targets.",
        "",
        "## Acceptance Gate",
        "",
        *[f"- {key}: `{value}`" for key, value in gate.items()],
        "",
        "## Selected Candidate",
        "",
        f"- Rank: `{top['rank']}`",
        f"- Score: `{top['score']:.2f}`",
        f"- Quality flags: `{', '.join(top['quality_flags']) if top['quality_flags'] else 'none'}`",
        *_metric_lines("Train", top["train"]),
        *_metric_lines("Out of sample", top["out_of_sample"]),
        *_metric_lines("Full window", top["full_window"]),
        "",
        "## Walk Forward",
        "",
    ]
    for item in payload["walk_forward"]:
        lines.extend(
            [
                f"### Fold {item['fold']}: {item['params']['label']}",
                "",
                *_metric_lines("Test", item["test"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Notes",
            "",
            "- This is research evidence only; it does not activate paper_auto.",
            "- LLM/news remains advisory and is not claimed as independent Alpha.",
            "- Very high Sharpe is treated as an overfit warning, not as proof of quality.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: CoreSatelliteCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__ | {"label": candidate.params.label},
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: CoreSatelliteWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__ | {"label": item.params.label},
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _metric_lines(label: str, metrics: dict[str, Any]) -> list[str]:
    return [
        f"- {label} annualized: `{_fmt(metrics.get('annualized_return_pct'))}%`",
        f"- {label} Sharpe: `{_fmt(metrics.get('sharpe_ratio'))}`",
        f"- {label} max drawdown: `{_fmt(metrics.get('max_drawdown_pct'))}%`",
        f"- {label} Alpha vs QQQ annualized: "
        f"`{_fmt(metrics.get('alpha_vs_qqq_buy_hold_annualized_pct'))}%`",
        f"- {label} Alpha vs satellite annualized: "
        f"`{_fmt(metrics.get('alpha_vs_satellite_buy_hold_annualized_pct'))}%`",
        f"- {label} exposure/rebalances: "
        f"`{_fmt(metrics.get('exposure_pct'))}% / {metrics.get('rebalance_count')}`",
    ]


def _params_grid_ranges(params_grid: list[CoreSatelliteParams]) -> dict[str, list[Any]]:
    keys = [
        "trend_sma_days",
        "momentum_lookback_days",
        "min_momentum_pct",
        "volatility_lookback_days",
        "max_volatility_annual_pct",
        "drawdown_lookback_days",
        "max_drawdown_pct",
        "core_weight",
        "satellite_symbol",
        "satellite_weight",
        "risk_off_core_scale",
        "target_satellite_volatility_pct",
        "rebalance_threshold_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _cached_sma(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["sma"]
    if lookback not in values:
        values[lookback] = (
            pd.Series(cache["QQQ_close"]).rolling(lookback).mean().to_numpy(dtype=float)
        )
    return values[lookback]


def _cached_momentum(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["momentum"]
    if lookback not in values:
        close = cache["QQQ_close"]
        output = np.full(len(close), np.nan)
        output[lookback:] = (close[lookback:] / close[:-lookback] - 1) * 100
        values[lookback] = output
    return values[lookback]


def _cached_qqq_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["qqq_volatility"]
    if lookback not in values:
        values[lookback] = _realized_volatility(pd.Series(cache["QQQ_close"]), lookback)
    return values[lookback]


def _cached_satellite_volatility(
    cache: dict[str, Any],
    symbol: SatelliteAsset,
    lookback: int,
) -> np.ndarray:
    values = cache["satellite_volatility"]
    key = (symbol, lookback)
    if key not in values:
        values[key] = _realized_volatility(pd.Series(cache[f"{symbol}_close"]), lookback)
    return values[key]


def _cached_drawdown(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["drawdown"]
    if lookback not in values:
        close = pd.Series(cache["QQQ_close"])
        peak = close.rolling(lookback).max()
        values[lookback] = (close / peak - 1).to_numpy(dtype=float) * 100
    return values[lookback]


def _realized_volatility(close: pd.Series, lookback: int) -> np.ndarray:
    return close.pct_change().rolling(lookback).std().to_numpy(dtype=float) * math.sqrt(252) * 100


def _next_open_returns(open_values: np.ndarray) -> np.ndarray:
    output = np.zeros(len(open_values))
    if len(open_values) > 1:
        output[:-1] = open_values[1:] / open_values[:-1] - 1
    return output


def _split_index(
    frame_len: int,
    out_of_sample_ratio: float,
    params_grid: list[CoreSatelliteParams],
) -> int:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - out_of_sample_ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _effective_lookback(params: CoreSatelliteParams) -> int:
    return max(
        params.trend_sma_days,
        params.momentum_lookback_days,
        params.volatility_lookback_days,
        params.drawdown_lookback_days,
    )


def _buy_hold_return(
    dataset: CoreSatelliteDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if end_index <= start_index:
        return 0.0
    frame = dataset.frame
    start = float(frame[f"{symbol}_open"].iloc[start_index])
    end = float(frame[f"{symbol}_close"].iloc[end_index - 1])
    return (end / start - 1) * 100 if start > 0 else 0.0


def _annualized_from_total(total_return_pct: float, days: int) -> float | None:
    if days <= 0 or total_return_pct <= -100:
        return None
    return ((1 + total_return_pct / 100) ** (252 / days) - 1) * 100


def _alpha(value: float | None, benchmark: float | None) -> float | None:
    if value is None or benchmark is None:
        return None
    return value - benchmark


def _empty_metrics(
    dataset: CoreSatelliteDataset,
    satellite_symbol: str,
    start_index: int,
    end_index: int,
) -> CoreSatelliteMetrics:
    return CoreSatelliteMetrics(
        days=0,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index] if end_index < len(dataset.dates) else None,
        total_return_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        annualized_volatility_pct=None,
        sortino_ratio=None,
        calmar_ratio=None,
        max_drawdown_pct=0.0,
        qqq_buy_hold_return_pct=0.0,
        qqq_buy_hold_annualized_pct=None,
        alpha_vs_qqq_buy_hold_annualized_pct=None,
        satellite_symbol=satellite_symbol,
        satellite_buy_hold_return_pct=0.0,
        satellite_buy_hold_annualized_pct=None,
        alpha_vs_satellite_buy_hold_annualized_pct=None,
        cash_proxy_return_pct=0.0,
        exposure_pct=0.0,
        average_gross_exposure_pct=0.0,
        max_gross_exposure_pct=0.0,
        rebalance_count=0,
        turnover_ratio=0.0,
        cost_drag_pct=0.0,
        risk_on_days=0,
        core_only_days=0,
        risk_off_days=0,
    )


def _cap_gross(weights: dict[str, float]) -> dict[str, float]:
    gross = sum(abs(value) for value in weights.values())
    if gross <= 1.0:
        return {key: value for key, value in weights.items() if value > 0}
    return {key: value / gross for key, value in weights.items() if value > 0}


def _parse_research_datetime(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _label_optional(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)


def _parse_satellite_weight(value: str) -> tuple[SatelliteAsset, float]:
    for asset in ["TQQQ", "QLD"]:
        if value.startswith(asset):
            return asset, float(value.removeprefix(asset) or 0.0)  # type: ignore[return-value]
    raise ValueError(f"invalid satellite asset weight: {value}")


def _satellite_assets(values: list[str] | None) -> list[SatelliteAsset] | None:
    if values is None:
        return None
    allowed = {"TQQQ", "QLD"}
    assets = [item.strip().upper() for item in values if item.strip()]
    unknown = sorted(set(assets) - allowed)
    if unknown:
        raise ValueError(f"unsupported satellite asset(s): {', '.join(unknown)}")
    return assets  # type: ignore[return-value]


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
