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

BetaAsset = Literal["QQQ", "TQQQ", "SQQQ", "PSQ", "QID", "QLD", "SMH", "SOXL", "CASH"]


@dataclass(frozen=True)
class BetaRouterParams:
    trend_sma_days: int
    momentum_lookback_days: int
    min_momentum_pct: float
    volatility_lookback_days: int
    max_volatility_annual_pct: float | None
    drawdown_lookback_days: int
    max_drawdown_pct: float | None
    leverage_trend_sma_days: int | None
    max_leverage_volatility_annual_pct: float | None
    leverage_drawdown_lookback_days: int
    max_leverage_drawdown_pct: float | None
    risk_on_symbol: BetaAsset
    risk_on_weight: float
    neutral_symbol: BetaAsset
    neutral_weight: float
    risk_off_symbol: BetaAsset
    risk_off_weight: float
    target_volatility_annual_pct: float | None

    @property
    def label(self) -> str:
        return (
            f"beta:sma{self.trend_sma_days}_mom{self.momentum_lookback_days}_"
            f"min{self.min_momentum_pct:g}_vol{self.volatility_lookback_days}_"
            f"maxv{_label_optional(self.max_volatility_annual_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{_label_optional(self.max_drawdown_pct)}_"
            f"levsma{_label_optional_int(self.leverage_trend_sma_days)}_"
            f"levmaxv{_label_optional(self.max_leverage_volatility_annual_pct)}_"
            f"levdd{self.leverage_drawdown_lookback_days}_"
            f"levmaxdd{_label_optional(self.max_leverage_drawdown_pct)}_"
            f"on{self.risk_on_symbol}{self.risk_on_weight:g}_"
            f"neu{self.neutral_symbol}{self.neutral_weight:g}_"
            f"off{self.risk_off_symbol}{self.risk_off_weight:g}_"
            f"vt{_label_optional(self.target_volatility_annual_pct)}"
        )


@dataclass(frozen=True)
class BetaRouterMetrics:
    days: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    annualized_volatility_pct: float | None
    max_drawdown_pct: float
    market_symbol: str
    market_buy_hold_return_pct: float
    market_buy_hold_annualized_pct: float | None
    alpha_vs_market_buy_hold_annualized_pct: float | None
    leverage_symbol: str
    leverage_buy_hold_return_pct: float
    leverage_buy_hold_annualized_pct: float | None
    alpha_vs_leverage_buy_hold_annualized_pct: float | None
    cash_proxy_return_pct: float
    exposure_pct: float
    average_gross_exposure_pct: float
    max_gross_exposure_pct: float
    rebalance_count: int
    turnover_ratio: float
    cost_drag_pct: float
    risk_on_days: int
    neutral_days: int
    risk_off_days: int


@dataclass(frozen=True)
class BetaRouterValidationWindow:
    name: str
    start_date: str
    end_date: str
    metrics: BetaRouterMetrics


@dataclass(frozen=True)
class BetaRouterCandidate:
    rank: int
    params: BetaRouterParams
    score: float
    train: BetaRouterMetrics
    out_of_sample: BetaRouterMetrics
    full_window: BetaRouterMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class BetaRouterWalkForwardSlice:
    fold: int
    params: BetaRouterParams
    train: BetaRouterMetrics
    test: BetaRouterMetrics


@dataclass(frozen=True)
class BetaRouterResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


@dataclass(frozen=True)
class BetaTargetWeightSnapshot:
    state: str
    weights: dict[str, float]
    volatility_scale: float
    qqq_trend_ok: bool
    qqq_momentum_ok: bool
    qqq_volatility_ok: bool
    qqq_drawdown_ok: bool
    leverage_trend_ok: bool
    leverage_volatility_ok: bool
    leverage_drawdown_ok: bool


@dataclass(frozen=True)
class BetaRouterDataset:
    frame: pd.DataFrame
    dates: list[str]
    market_symbol: str
    leverage_symbol: str
    hedge_symbol: str | None
    data_profile: dict[str, Any]


def run_beta_exposure_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    market_symbol: str = "QQQ",
    leverage_symbol: str = "TQQQ",
    hedge_symbol: str | None = "SQQQ",
    trend_sma_days: list[int] | None = None,
    momentum_lookback_days: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    volatility_lookback_days: list[int] | None = None,
    max_volatility_annual_pct: list[float | None] | None = None,
    drawdown_lookback_days: list[int] | None = None,
    max_drawdown_pct: list[float | None] | None = None,
    leverage_trend_sma_days: list[int | None] | None = None,
    max_leverage_volatility_annual_pct: list[float | None] | None = None,
    leverage_drawdown_lookback_days: list[int] | None = None,
    max_leverage_drawdown_pct: list[float | None] | None = None,
    risk_on_symbol: list[str] | None = None,
    risk_on_weight: list[float] | None = None,
    neutral_weight: list[float] | None = None,
    risk_off_symbol: list[str] | None = None,
    risk_off_weight: list[float] | None = None,
    target_volatility_annual_pct: list[float | None] | None = None,
    out_of_sample_ratio: float = 0.35,
    walk_forward_folds: int = 5,
    walk_forward_top_k: int | None = 20,
    max_candidates: int = 600,
    refresh_data: bool = False,
) -> BetaRouterResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    dataset = load_beta_router_dataset(
        root=base,
        market_symbol=market_symbol,
        leverage_symbol=leverage_symbol,
        hedge_symbol=hedge_symbol,
        timeframe=spec.timeframe,
        data_source=data_source,
        feed=selected_feed,
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
        max_volatility_annual_pct or [None, 30.0],
        drawdown_lookback_days or [60, 120],
        max_drawdown_pct or [None, 20.0],
        leverage_trend_sma_days or [None],
        max_leverage_volatility_annual_pct or [None],
        leverage_drawdown_lookback_days or [60, 120],
        max_leverage_drawdown_pct or [None],
        _beta_assets(risk_on_symbol) or [leverage_symbol.upper()],
        risk_on_weight or [0.5, 0.75, 1.0],
        (_beta_assets([market_symbol]) or ["QQQ"])[0],
        neutral_weight or [0.5, 0.75, 1.0],
        _beta_assets(risk_off_symbol) or ["CASH", "SQQQ"],
        risk_off_weight or [0.0, 0.25, 0.5],
        target_volatility_annual_pct or [None, 30.0],
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
    validation_windows = _validation_windows(
        spec=spec,
        dataset=dataset,
        cache=cache,
        params=candidates[0].params,
    )
    pass_status = _pass_status(candidates[0], walk_forward, validation_windows)
    stages["research"] = perf_counter() - stage_started

    json_path = base / "reports" / "research" / f"{spec.name}-beta-exposure-router.json"
    report_path = json_path.with_suffix(".md")
    payload = _payload(
        spec=spec,
        spec_path=spec_path,
        dataset=dataset,
        params_grid=params_grid,
        candidates=candidates,
        walk_forward=walk_forward,
        validation_windows=validation_windows,
        pass_status=pass_status,
        start=start,
        end=end,
        runtime=runtime_payload(started_at, stages),
        walk_forward_top_k=walk_forward_top_k,
    )
    write_json(json_path, payload)
    _write_report(report_path, json_path, payload)
    return BetaRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=candidates[0].params.label,
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def load_beta_router_dataset(
    *,
    root: Path,
    market_symbol: str,
    leverage_symbol: str,
    hedge_symbol: str | None,
    timeframe: str,
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> BetaRouterDataset:
    market = _load_symbol_frame(
        root=root,
        symbol=market_symbol,
        timeframe=timeframe,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    leverage = _load_symbol_frame(
        root=root,
        symbol=leverage_symbol,
        timeframe=timeframe,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    hedge = (
        _load_symbol_frame(
            root=root,
            symbol=hedge_symbol,
            timeframe=timeframe,
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        )
        if hedge_symbol
        else None
    )
    market_symbol = market_symbol.upper()
    leverage_symbol = leverage_symbol.upper()
    hedge_symbol = hedge_symbol.upper() if hedge_symbol else None
    frame = (
        market[["timestamp", "open", "close"]]
        .rename(
            columns={
                "open": f"{market_symbol}_open",
                "close": f"{market_symbol}_close",
            }
        )
        .merge(
            leverage[["timestamp", "open", "close"]].rename(
                columns={
                    "open": f"{leverage_symbol}_open",
                    "close": f"{leverage_symbol}_close",
                }
            ),
            on="timestamp",
            how="inner",
        )
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    if hedge is not None and hedge_symbol:
        frame = (
            frame.merge(
                hedge[["timestamp", "open", "close"]].rename(
                    columns={
                        "open": f"{hedge_symbol}_open",
                        "close": f"{hedge_symbol}_close",
                    }
                ),
                on="timestamp",
                how="inner",
            )
            .sort_values("timestamp")
            .drop_duplicates("timestamp")
            .reset_index(drop=True)
        )
    if len(frame) < 260:
        raise ValueError("beta exposure router requires at least 260 common daily bars")
    dates = [
        pd.Timestamp(value).tz_convert("America/New_York").date().isoformat()
        for value in frame["timestamp"]
    ]
    profiles = [
        frame_data_profile(
            market,
            symbol=market_symbol,
            timeframe=timeframe,
            provider=data_source,
            feed=feed,
            source_mode="cache" if not refresh_data else "live_fetch",
        ),
        frame_data_profile(
            leverage,
            symbol=leverage_symbol,
            timeframe=timeframe,
            provider=data_source,
            feed=feed,
            source_mode="cache" if not refresh_data else "live_fetch",
        ),
    ]
    if hedge is not None and hedge_symbol:
        profiles.append(
            frame_data_profile(
                hedge,
                symbol=hedge_symbol,
                timeframe=timeframe,
                provider=data_source,
                feed=feed,
                source_mode="cache" if not refresh_data else "live_fetch",
            )
        )
    return BetaRouterDataset(
        frame=frame,
        dates=dates,
        market_symbol=market_symbol,
        leverage_symbol=leverage_symbol,
        hedge_symbol=hedge_symbol,
        data_profile=combined_data_profile(profiles),
    )


def beta_params_from_label(label: str) -> BetaRouterParams:
    if not label.startswith("beta:"):
        raise ValueError(f"not a beta router label: {label}")
    raw: dict[str, str] = {}
    for part in label.removeprefix("beta:").split("_"):
        for prefix in [
            "levmaxdd",
            "levmaxv",
            "levsma",
            "levdd",
            "maxdd",
            "maxv",
            "sma",
            "mom",
            "min",
            "vol",
            "dd",
            "on",
            "neu",
            "off",
            "vt",
        ]:
            if part.startswith(prefix):
                raw[prefix] = part.removeprefix(prefix)
                break
    on_symbol, on_weight = _parse_asset_weight(raw["on"])
    neutral_symbol, neutral_weight = _parse_asset_weight(raw["neu"])
    off_symbol, off_weight = _parse_asset_weight(raw["off"])
    return BetaRouterParams(
        trend_sma_days=int(raw["sma"]),
        momentum_lookback_days=int(raw["mom"]),
        min_momentum_pct=float(raw["min"]),
        volatility_lookback_days=int(raw["vol"]),
        max_volatility_annual_pct=_parse_optional_float(raw["maxv"]),
        drawdown_lookback_days=int(raw["dd"]),
        max_drawdown_pct=_parse_optional_float(raw["maxdd"]),
        leverage_trend_sma_days=_parse_optional_int(raw.get("levsma", "none")),
        max_leverage_volatility_annual_pct=_parse_optional_float(raw.get("levmaxv", "none")),
        leverage_drawdown_lookback_days=int(raw.get("levdd", raw["dd"])),
        max_leverage_drawdown_pct=_parse_optional_float(raw.get("levmaxdd", "none")),
        risk_on_symbol=on_symbol,
        risk_on_weight=on_weight,
        neutral_symbol=neutral_symbol,
        neutral_weight=neutral_weight,
        risk_off_symbol=off_symbol,
        risk_off_weight=off_weight,
        target_volatility_annual_pct=_parse_optional_float(raw["vt"]),
    )


def beta_target_weight_snapshot(
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    index: int,
) -> BetaTargetWeightSnapshot:
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
        frame = frame[frame["timestamp"] >= _utc_timestamp(start)]
    if end:
        frame = frame[frame["timestamp"] <= _utc_timestamp(end)]
    return frame.sort_values("timestamp").reset_index(drop=True)


def _parse_research_datetime(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _build_params_grid(
    trend_values: list[int],
    momentum_values: list[int],
    min_momentum_values: list[float],
    volatility_values: list[int],
    max_volatility_values: list[float | None],
    drawdown_values: list[int],
    max_drawdown_values: list[float | None],
    leverage_trend_values: list[int | None],
    max_leverage_volatility_values: list[float | None],
    leverage_drawdown_values: list[int],
    max_leverage_drawdown_values: list[float | None],
    risk_on_symbols: list[BetaAsset],
    risk_on_values: list[float],
    neutral_symbol: BetaAsset,
    neutral_values: list[float],
    risk_off_symbols: list[BetaAsset],
    risk_off_values: list[float],
    target_volatility_values: list[float | None],
    *,
    max_candidates: int,
) -> list[BetaRouterParams]:
    total = math.prod(
        [
            len(trend_values),
            len(momentum_values),
            len(min_momentum_values),
            len(volatility_values),
            len(max_volatility_values),
            len(drawdown_values),
            len(max_drawdown_values),
            len(leverage_trend_values),
            len(max_leverage_volatility_values),
            len(leverage_drawdown_values),
            len(max_leverage_drawdown_values),
            len(risk_on_symbols),
            len(risk_on_values),
            len(neutral_values),
            len(risk_off_symbols),
            len(risk_off_values),
            len(target_volatility_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"beta router grid would create {total} candidates; raise --max-candidates "
            f"above {total} or narrow the grid"
        )
    params: list[BetaRouterParams] = []
    for item in product(
        trend_values,
        momentum_values,
        min_momentum_values,
        volatility_values,
        max_volatility_values,
        drawdown_values,
        max_drawdown_values,
        leverage_trend_values,
        max_leverage_volatility_values,
        leverage_drawdown_values,
        max_leverage_drawdown_values,
        risk_on_symbols,
        risk_on_values,
        neutral_values,
        risk_off_symbols,
        risk_off_values,
        target_volatility_values,
    ):
        (
            trend,
            momentum,
            min_momentum,
            volatility,
            max_volatility,
            drawdown,
            max_drawdown,
            leverage_trend,
            max_leverage_volatility,
            leverage_drawdown,
            max_leverage_drawdown,
            risk_on_asset,
            risk_on,
            neutral,
            risk_off_asset,
            risk_off,
            target_volatility,
        ) = item
        if min(trend, momentum, volatility, drawdown) < 1:
            continue
        if leverage_trend is not None and leverage_trend < 1:
            continue
        if leverage_drawdown < 1:
            continue
        if min(risk_on, neutral, risk_off) < 0 or max(risk_on, neutral, risk_off) > 1.0:
            continue
        if risk_off_asset == "CASH" and risk_off != 0:
            continue
        params.append(
            BetaRouterParams(
                trend_sma_days=trend,
                momentum_lookback_days=momentum,
                min_momentum_pct=min_momentum,
                volatility_lookback_days=volatility,
                max_volatility_annual_pct=max_volatility,
                drawdown_lookback_days=drawdown,
                max_drawdown_pct=max_drawdown,
                leverage_trend_sma_days=leverage_trend,
                max_leverage_volatility_annual_pct=max_leverage_volatility,
                leverage_drawdown_lookback_days=leverage_drawdown,
                max_leverage_drawdown_pct=max_leverage_drawdown,
                risk_on_symbol=risk_on_asset,
                risk_on_weight=risk_on,
                neutral_symbol=neutral_symbol,
                neutral_weight=neutral,
                risk_off_symbol=risk_off_asset,
                risk_off_weight=risk_off,
                target_volatility_annual_pct=target_volatility,
            )
        )
    if not params:
        raise ValueError("beta router grid produced no valid candidates")
    return params


def _build_indicator_cache(dataset: BetaRouterDataset) -> dict[str, Any]:
    frame = dataset.frame
    market_close = frame[f"{dataset.market_symbol}_close"].to_numpy(dtype=float)
    market_open = frame[f"{dataset.market_symbol}_open"].to_numpy(dtype=float)
    leverage_close = frame[f"{dataset.leverage_symbol}_close"].to_numpy(dtype=float)
    leverage_open = frame[f"{dataset.leverage_symbol}_open"].to_numpy(dtype=float)
    hedge_close = (
        frame[f"{dataset.hedge_symbol}_close"].to_numpy(dtype=float)
        if dataset.hedge_symbol
        else np.zeros(len(frame))
    )
    hedge_open = (
        frame[f"{dataset.hedge_symbol}_open"].to_numpy(dtype=float)
        if dataset.hedge_symbol
        else np.zeros(len(frame))
    )
    return {
        "market_close": market_close,
        "market_open": market_open,
        "leverage_close": leverage_close,
        "leverage_open": leverage_open,
        "hedge_close": hedge_close,
        "hedge_open": hedge_open,
        "market_open_return": _next_open_returns(market_open),
        "leverage_open_return": _next_open_returns(leverage_open),
        "hedge_open_return": _next_open_returns(hedge_open)
        if dataset.hedge_symbol
        else np.zeros(len(frame)),
        "sma": {},
        "momentum": {},
        "market_volatility": {},
        "leverage_volatility": {},
        "hedge_volatility": {},
        "drawdown": {},
        "leverage_sma": {},
        "leverage_drawdown": {},
    }


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params_grid: list[BetaRouterParams],
    out_of_sample_ratio: float,
) -> list[BetaRouterCandidate]:
    split = _split_index(len(dataset.frame), out_of_sample_ratio, params_grid)
    rows: list[BetaRouterCandidate] = []
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
            BetaRouterCandidate(
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
        BetaRouterCandidate(
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
    params_grid: list[BetaRouterParams],
    candidates: list[BetaRouterCandidate],
    walk_forward_top_k: int | None,
) -> list[BetaRouterParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params_grid: list[BetaRouterParams],
    folds: int,
) -> list[BetaRouterWalkForwardSlice]:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.frame) - max_lookback) // (max(folds, 1) + 1), 20)
    rows: list[BetaRouterWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.frame) - 1, test_start + fold_size)
        if test_end - test_start < 20:
            continue
        scored: list[tuple[float, BetaRouterParams]] = []
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
            BetaRouterWalkForwardSlice(
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
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params: BetaRouterParams,
    *,
    start_index: int,
    end_index: int,
    evaluation_start_index: int | None = None,
    start_equity: float = 100_000.0,
) -> BetaRouterMetrics:
    start_index = max(start_index, _effective_lookback(params) + 1)
    if evaluation_start_index is not None:
        start_index = max(start_index, evaluation_start_index)
    end_index = min(end_index, len(dataset.frame) - 1)
    if end_index <= start_index:
        return _empty_metrics(dataset, start_index, end_index)

    equity = start_equity
    curve = [equity]
    returns: list[float] = []
    gross_exposures: list[float] = []
    states: list[str] = []
    symbols = [dataset.market_symbol, dataset.leverage_symbol]
    if dataset.hedge_symbol:
        symbols.append(dataset.hedge_symbol)
    previous_weights = {symbol: 0.0 for symbol in symbols}
    rebalance_count = 0
    turnover_ratio = 0.0
    cost_drag = 0.0
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000

    for index in range(start_index, end_index):
        snapshot = _target_snapshot(dataset, cache, params, index)
        weights = {symbol: snapshot.weights.get(symbol, 0.0) for symbol in symbols}
        turnover = sum(
            abs(weights[symbol] - previous_weights.get(symbol, 0.0)) for symbol in weights
        )
        if turnover > 1e-12:
            rebalance_count += 1
        turnover_ratio += turnover
        cost = turnover * cost_rate
        period_return = (
            weights[dataset.market_symbol] * float(cache["market_open_return"][index])
            + weights[dataset.leverage_symbol] * float(cache["leverage_open_return"][index])
            + (
                weights.get(dataset.hedge_symbol, 0.0) * float(cache["hedge_open_return"][index])
                if dataset.hedge_symbol
                else 0.0
            )
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
    market_buy_hold = _buy_hold_return(dataset, dataset.market_symbol, start_index, end_index)
    leverage_buy_hold = _buy_hold_return(dataset, dataset.leverage_symbol, start_index, end_index)
    market_ann = _annualized_from_total(market_buy_hold, days)
    leverage_ann = _annualized_from_total(leverage_buy_hold, days)
    annualized = metrics.annualized_return_pct
    return BetaRouterMetrics(
        days=days,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index - 1] if end_index - 1 < len(dataset.dates) else None,
        total_return_pct=(equity / start_equity - 1) * 100,
        annualized_return_pct=annualized,
        sharpe_ratio=metrics.sharpe_ratio,
        annualized_volatility_pct=metrics.annualized_volatility_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=market_buy_hold,
        market_buy_hold_annualized_pct=market_ann,
        alpha_vs_market_buy_hold_annualized_pct=_alpha(annualized, market_ann),
        leverage_symbol=dataset.leverage_symbol,
        leverage_buy_hold_return_pct=leverage_buy_hold,
        leverage_buy_hold_annualized_pct=leverage_ann,
        alpha_vs_leverage_buy_hold_annualized_pct=_alpha(annualized, leverage_ann),
        cash_proxy_return_pct=0.0,
        exposure_pct=sum(1 for value in gross_exposures if value > 0) / days * 100 if days else 0.0,
        average_gross_exposure_pct=mean(gross_exposures) * 100 if gross_exposures else 0.0,
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        rebalance_count=rebalance_count,
        turnover_ratio=turnover_ratio,
        cost_drag_pct=cost_drag * 100,
        risk_on_days=sum(1 for item in states if item == "risk_on"),
        neutral_days=sum(1 for item in states if item == "neutral"),
        risk_off_days=sum(1 for item in states if item == "risk_off"),
    )


def backtest_beta_router_params(
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    *,
    start_index: int,
    end_index: int,
) -> BetaRouterMetrics:
    cache = _build_indicator_cache(dataset)
    return _backtest_params(
        spec,
        dataset,
        cache,
        params,
        start_index=start_index,
        end_index=end_index,
    )


def _target_snapshot(
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params: BetaRouterParams,
    index: int,
) -> BetaTargetWeightSnapshot:
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    market_close = cache["market_close"]
    trend_sma = _cached_sma(cache, params.trend_sma_days)
    momentum = _cached_momentum(cache, params.momentum_lookback_days)
    market_volatility = _cached_market_volatility(cache, params.volatility_lookback_days)
    drawdown = _cached_drawdown(cache, params.drawdown_lookback_days)
    trend_ok = bool(market_close[previous_index] > trend_sma[previous_index])
    momentum_value = momentum[previous_index]
    momentum_ok = bool(not np.isnan(momentum_value) and momentum_value >= params.min_momentum_pct)
    volatility_value = market_volatility[previous_index]
    volatility_ok = True
    if params.max_volatility_annual_pct is not None and not np.isnan(volatility_value):
        volatility_ok = bool(volatility_value <= params.max_volatility_annual_pct)
    drawdown_value = drawdown[previous_index]
    drawdown_ok = True
    if params.max_drawdown_pct is not None and not np.isnan(drawdown_value):
        drawdown_ok = bool(abs(min(float(drawdown_value), 0.0)) <= params.max_drawdown_pct)
    leverage_trend_ok = True
    if params.leverage_trend_sma_days is not None:
        leverage_sma = _cached_leverage_sma(cache, params.leverage_trend_sma_days)
        leverage_trend_ok = bool(
            cache["leverage_close"][previous_index] > leverage_sma[previous_index]
        )
    leverage_volatility_ok = True
    if params.max_leverage_volatility_annual_pct is not None:
        leverage_volatility = _cached_leverage_volatility(cache, params.volatility_lookback_days)
        leverage_volatility_value = leverage_volatility[previous_index]
        if not np.isnan(leverage_volatility_value):
            leverage_volatility_ok = bool(
                leverage_volatility_value <= params.max_leverage_volatility_annual_pct
            )
    leverage_drawdown = _cached_leverage_drawdown(cache, params.leverage_drawdown_lookback_days)
    leverage_drawdown_value = leverage_drawdown[previous_index]
    leverage_drawdown_ok = True
    if params.max_leverage_drawdown_pct is not None and not np.isnan(leverage_drawdown_value):
        leverage_drawdown_ok = bool(
            abs(min(float(leverage_drawdown_value), 0.0)) <= params.max_leverage_drawdown_pct
        )

    if (
        trend_ok
        and momentum_ok
        and volatility_ok
        and drawdown_ok
        and leverage_trend_ok
        and leverage_volatility_ok
        and leverage_drawdown_ok
    ):
        vol_scale = _asset_volatility_scale(dataset, cache, params, params.risk_on_symbol, index)
        return _snapshot_for_asset(
            dataset,
            state="risk_on",
            asset=params.risk_on_symbol,
            weight=params.risk_on_weight * vol_scale,
            volatility_scale=vol_scale,
            trend_ok=trend_ok,
            momentum_ok=momentum_ok,
            volatility_ok=volatility_ok,
            drawdown_ok=drawdown_ok,
            leverage_trend_ok=leverage_trend_ok,
            leverage_volatility_ok=leverage_volatility_ok,
            leverage_drawdown_ok=leverage_drawdown_ok,
        )
    if trend_ok and drawdown_ok:
        vol_scale = _asset_volatility_scale(dataset, cache, params, params.neutral_symbol, index)
        return _snapshot_for_asset(
            dataset,
            state="neutral",
            asset=params.neutral_symbol,
            weight=params.neutral_weight * vol_scale,
            volatility_scale=vol_scale,
            trend_ok=trend_ok,
            momentum_ok=momentum_ok,
            volatility_ok=volatility_ok,
            drawdown_ok=drawdown_ok,
            leverage_trend_ok=leverage_trend_ok,
            leverage_volatility_ok=leverage_volatility_ok,
            leverage_drawdown_ok=leverage_drawdown_ok,
        )
    vol_scale = _asset_volatility_scale(dataset, cache, params, params.risk_off_symbol, index)
    return _snapshot_for_asset(
        dataset,
        state="risk_off",
        asset=params.risk_off_symbol,
        weight=params.risk_off_weight,
        volatility_scale=vol_scale,
        trend_ok=trend_ok,
        momentum_ok=momentum_ok,
        volatility_ok=volatility_ok,
        drawdown_ok=drawdown_ok,
        leverage_trend_ok=leverage_trend_ok,
        leverage_volatility_ok=leverage_volatility_ok,
        leverage_drawdown_ok=leverage_drawdown_ok,
    )


def _asset_volatility_scale(
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params: BetaRouterParams,
    asset: BetaAsset,
    index: int,
) -> float:
    if params.target_volatility_annual_pct is None or asset == "CASH":
        return 1.0
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    if asset == dataset.leverage_symbol:
        volatility = _cached_leverage_volatility(cache, params.volatility_lookback_days)
    elif dataset.hedge_symbol and asset == dataset.hedge_symbol:
        volatility = _cached_hedge_volatility(cache, params.volatility_lookback_days)
    else:
        volatility = _cached_market_volatility(cache, params.volatility_lookback_days)
    value = volatility[previous_index]
    if np.isnan(value) or value <= 0:
        return 1.0
    return max(0.0, min(1.0, params.target_volatility_annual_pct / float(value)))


def _snapshot_for_asset(
    dataset: BetaRouterDataset,
    *,
    state: str,
    asset: BetaAsset,
    weight: float,
    volatility_scale: float,
    trend_ok: bool,
    momentum_ok: bool,
    volatility_ok: bool,
    drawdown_ok: bool,
    leverage_trend_ok: bool,
    leverage_volatility_ok: bool,
    leverage_drawdown_ok: bool,
) -> BetaTargetWeightSnapshot:
    weights: dict[str, float] = {}
    if asset == dataset.market_symbol and weight > 0:
        weights[dataset.market_symbol] = min(weight, 1.0)
    elif asset == dataset.leverage_symbol and weight > 0:
        weights[dataset.leverage_symbol] = min(weight, 1.0)
    elif dataset.hedge_symbol and asset == dataset.hedge_symbol and weight > 0:
        weights[dataset.hedge_symbol] = min(weight, 1.0)
    return BetaTargetWeightSnapshot(
        state=state,
        weights=weights,
        volatility_scale=volatility_scale,
        qqq_trend_ok=trend_ok,
        qqq_momentum_ok=momentum_ok,
        qqq_volatility_ok=volatility_ok,
        qqq_drawdown_ok=drawdown_ok,
        leverage_trend_ok=leverage_trend_ok,
        leverage_volatility_ok=leverage_volatility_ok,
        leverage_drawdown_ok=leverage_drawdown_ok,
    )


def _score_candidate(metrics: BetaRouterMetrics) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    market_alpha = metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0
    drawdown_penalty = abs(min(metrics.max_drawdown_pct, 0.0)) * 0.35
    leverage_drawdown_bonus = max(0.0, 40.0 - abs(min(metrics.max_drawdown_pct, 0.0))) * 0.05
    turnover_penalty = max(0, metrics.rebalance_count - 80) * 0.08
    high_sharpe_penalty = max(0.0, sharpe - 2.5) * 30
    sparse_penalty = max(0.0, 20.0 - metrics.exposure_pct) * 0.5
    return (
        market_alpha
        + annualized * 0.25
        + min(sharpe, 2.5) * 10
        + leverage_drawdown_bonus
        - drawdown_penalty
        - turnover_penalty
        - high_sharpe_penalty
        - sparse_penalty
    )


def _quality_flags(
    train: BetaRouterMetrics,
    oos: BetaRouterMetrics,
    full: BetaRouterMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq")
    if (oos.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq")
    if (full.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        flags.append("oos_low_sharpe")
    if oos.max_drawdown_pct <= -35:
        flags.append("oos_large_drawdown")
    if full.max_drawdown_pct <= -40:
        flags.append("full_large_drawdown")
    if full.rebalance_count > max(40, full.days // 5):
        flags.append("high_turnover")
    if (train.sharpe_ratio or 0.0) > 2.5 or (oos.sharpe_ratio or 0.0) > 2.5:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if oos.exposure_pct < 20:
        flags.append("oos_too_sparse")
    return flags


def _validation_windows(
    *,
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    cache: dict[str, Any],
    params: BetaRouterParams,
) -> list[BetaRouterValidationWindow]:
    first = dataset.dates[0]
    last = dataset.dates[-1]
    windows = [
        ("2023", "2023-01-01", "2023-12-31"),
        ("2024", "2024-01-01", "2024-12-31"),
        ("2025", "2025-01-01", "2025-12-31"),
        ("2026_ytd", "2026-01-01", last),
        ("last_12m", _date_offset(last, months=12), last),
        ("last_24m", _date_offset(last, months=24), last),
    ]
    rows: list[BetaRouterValidationWindow] = []
    lookback = _effective_lookback(params) + 1
    for name, start, end in windows:
        start_index = _first_date_index(dataset, max(start, first))
        end_index = _last_date_index(dataset, min(end, last))
        if start_index is None or end_index is None:
            continue
        metrics = _backtest_params(
            spec,
            dataset,
            cache,
            params,
            start_index=max(0, start_index - lookback),
            end_index=end_index,
            evaluation_start_index=start_index,
        )
        if metrics.days < 40:
            continue
        rows.append(
            BetaRouterValidationWindow(
                name=name,
                start_date=metrics.start_date or dataset.dates[start_index],
                end_date=metrics.end_date or dataset.dates[end_index - 1],
                metrics=metrics,
            )
        )
    return rows


def _validation_gate(windows: list[BetaRouterValidationWindow]) -> dict[str, Any]:
    required_names = {"2024", "2025", "last_12m", "last_24m"}
    blockers: list[str] = []
    by_name = {item.name: item for item in windows}
    missing = sorted(required_names - set(by_name))
    if missing:
        blockers.append("missing_validation_windows:" + ",".join(missing))
    evaluated = [item for item in windows if item.name in required_names]
    positive = sum(
        (item.metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0) > 0 for item in evaluated
    )
    weak_windows = [
        item.name
        for item in evaluated
        if (item.metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0
        or (item.metrics.sharpe_ratio or -100.0) < 0.5
    ]
    worst_drawdown = min(
        (item.metrics.max_drawdown_pct for item in evaluated),
        default=None,
    )
    if positive < max(1, math.ceil(len(evaluated) * 0.75)):
        blockers.append("fewer_than_75pct_validation_windows_have_positive_alpha")
    if worst_drawdown is not None and worst_drawdown <= -30:
        blockers.append("validation_drawdown_worse_than_30pct")
    if "2025" in by_name:
        window_2025 = by_name["2025"].metrics
        if (window_2025.annualized_return_pct or -100.0) <= 0:
            blockers.append("2025_annualized_return_not_positive")
        if (window_2025.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= -5:
            blockers.append("2025_alpha_worse_than_minus_5pct")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "positive_alpha_windows": positive,
        "window_count": len(evaluated),
        "worst_drawdown_pct": worst_drawdown,
        "weak_windows": weak_windows,
    }


def _acceptance_gate(
    candidate: BetaRouterCandidate,
    walk_forward: list[BetaRouterWalkForwardSlice],
    validation_windows: list[BetaRouterValidationWindow] | None = None,
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_market_buy_hold_annualized_pct for item in walk_forward]
    wf_positive = sum((value or -100.0) > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    validation = _validation_gate(validation_windows or [])
    oos_sharpe = candidate.out_of_sample.sharpe_ratio or 0.0
    full_sharpe = candidate.full_window.sharpe_ratio or 0.0
    passed = (
        (candidate.train.alpha_vs_market_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.alpha_vs_market_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.alpha_vs_market_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.annualized_return_pct or -100.0) >= 12
        and 0.7 <= oos_sharpe <= 2.5
        and full_sharpe <= 2.5
        and candidate.out_of_sample.max_drawdown_pct > -35
        and candidate.full_window.max_drawdown_pct > -40
        and candidate.full_window.max_gross_exposure_pct <= 100
        and candidate.full_window.rebalance_count <= max(40, candidate.full_window.days // 5)
        and wf_count > 0
        and wf_positive >= max(1, math.ceil(wf_count * 0.6))
        and validation["passed"]
        and not {"oos_too_sparse", "suspiciously_high_sharpe_review_overfit"}.intersection(
            candidate.quality_flags
        )
    )
    return {
        "passed": passed,
        "objective": "risk_managed_beta_alpha_vs_qqq_buy_hold",
        "train_alpha_vs_qqq_annualized_pct": (
            candidate.train.alpha_vs_market_buy_hold_annualized_pct
        ),
        "oos_alpha_vs_qqq_annualized_pct": (
            candidate.out_of_sample.alpha_vs_market_buy_hold_annualized_pct
        ),
        "full_alpha_vs_qqq_annualized_pct": (
            candidate.full_window.alpha_vs_market_buy_hold_annualized_pct
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
        "validation_window_passed": validation["passed"],
        "validation_window_blockers": validation["blockers"],
        "validation_positive_alpha_windows": validation["positive_alpha_windows"],
        "validation_window_count": validation["window_count"],
        "worst_validation_drawdown_pct": validation["worst_drawdown_pct"],
        "weak_validation_windows": validation["weak_windows"],
        "quality_flags": candidate.quality_flags,
    }


def _pass_status(
    candidate: BetaRouterCandidate,
    walk_forward: list[BetaRouterWalkForwardSlice],
    validation_windows: list[BetaRouterValidationWindow] | None = None,
) -> dict[str, Any]:
    gate = _acceptance_gate(candidate, walk_forward, validation_windows)
    blockers = [
        "draft/manual_signal strategy only",
        "Alpaca IEX/cache evidence is not consolidated live SIP evidence",
        "promotion report and strict paper readiness still required before paper_auto",
        "LLM/news is advisory only; no independent LLM Alpha is claimed",
    ]
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
    dataset: BetaRouterDataset,
    params_grid: list[BetaRouterParams],
    candidates: list[BetaRouterCandidate],
    walk_forward: list[BetaRouterWalkForwardSlice],
    validation_windows: list[BetaRouterValidationWindow],
    pass_status: dict[str, Any],
    start: str | None,
    end: str | None,
    runtime: dict[str, Any],
    walk_forward_top_k: int | None,
) -> dict[str, Any]:
    return {
        "strategy_name": spec.name,
        "mode": "beta_exposure_router",
        "source_spec_path": _relpath(spec_path, spec_path.parents[2]),
        "market_symbol": dataset.market_symbol,
        "leverage_symbol": dataset.leverage_symbol,
        "hedge_symbol": dataset.hedge_symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective="risk-managed beta Alpha versus QQQ buy-and-hold",
            hypothesis=(
                "Absolute momentum, trend state, volatility targeting, and drawdown brakes "
                "can route capital among QQQ, TQQQ, hedge ETF, and cash with better recent-cycle "
                "risk-adjusted performance than static QQQ exposure."
            ),
            constraints=[
                "Signals use only QQQ information visible after the previous daily close.",
                "Target weights are applied at the next regular-session open.",
                "The strategy is long-only and never uses margin above 100% gross exposure.",
                "LLM/news review is not an execution factor in this research pass.",
            ],
        ),
        "search_space": search_space(
            family="beta_exposure_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "risk_on_symbol=TQQQ",
                "neutral_symbol=QQQ",
                "risk_off_symbol in CASH or hedge ETF",
                "optional leveraged ETF self-trend/volatility/drawdown filters",
                "gross exposure <= 100%",
                "train-only selection; OOS and walk-forward are validation",
            ],
        ),
        "references": [
            {
                "title": "Absolute Momentum",
                "url": "https://ssrn.com/abstract=2244633",
                "used_for": "absolute/time-series momentum risk switch",
            },
            {
                "title": "Time Series Momentum",
                "url": "https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf",
                "used_for": "trend persistence evidence across assets",
            },
            {
                "title": "Momentum Has Its Moments",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "used_for": "volatility-managed momentum risk control",
            },
            {
                "title": "A Century of Evidence on Trend-Following Investing",
                "url": "https://www.aqr.com/insights/trend-following",
                "used_for": "trend-following robustness framing",
            },
        ],
        "anti_leakage": [
            "Every target uses index-1 QQQ close-derived indicators.",
            "Optional leveraged ETF self-risk filters also use index-1 close-derived indicators.",
            "Backtest return is open[index] to open[index+1], after the signal close.",
            "Walk-forward folds reselect parameters only from trailing data.",
            "The selected route is not paper-ready unless OOS and walk-forward gates pass.",
        ],
        "known_limits": [
            "TQQQ did not trade before 2010, but current cache starts in 2022.",
            "Alpaca IEX cache is not consolidated market data.",
            "Cash proxy is modeled at 0% return in this research pass.",
            "ETF distributions, taxes, and borrow/margin effects are not modeled.",
            "Inverse ETF exposure is bounded and treated as higher-risk paper research evidence.",
        ],
        "selection_objective": (
            "Training score prioritizes annualized Alpha versus QQQ, controlled drawdown, "
            "moderate Sharpe, and bounded turnover; validation gates are separate."
        ),
        "acceptance_standard": {
            "train_oos_full_alpha_vs_qqq_annualized_pct": "> 0",
            "oos_annualized_return_pct": ">= 12",
            "oos_sharpe_ratio": "0.7 to 2.5",
            "max_drawdown_pct": "OOS > -35 and full > -40",
            "leveraged_self_filter": "optional TQQQ/QLD trend, volatility, and drawdown gates",
            "walk_forward": "at least 60% positive Alpha folds",
            "validation_windows": (
                "2024, 2025, last_12m, and last_24m must have mostly positive QQQ Alpha, "
                "validation drawdown better than -30%, and 2025 must stay positive"
            ),
            "turnover": "full rebalances <= max(40, days / 5)",
            "paper_ready_pass": "always false until promotion/readiness evidence passes",
        },
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward, validation_windows),
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
        "validation_windows": [_validation_window_payload(item) for item in validation_windows],
    }


def _write_report(path: Path, json_path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    gate = payload["acceptance_gate"]
    status = payload["pass_status"]
    top = payload["candidates"][0]
    lines = [
        f"# Beta Exposure Router Research: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Market/leverage: `{payload['market_symbol']}` / `{payload['leverage_symbol']}`",
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
        "## Fixed Validation Windows",
        "",
    ]
    for item in payload["validation_windows"]:
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- Window: `{item['start_date']}` -> `{item['end_date']}` days `{item['days']}`",
                *_metric_lines("Validation", item),
                "",
            ]
        )
    lines.extend(
        [
            "## Walk Forward",
            "",
        ]
    )
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
            "- LLM/news is intentionally advisory until PIT marginal-lift evidence exists.",
            "- Very high Sharpe is treated as an overfit warning, not as proof of quality.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: BetaRouterCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__ | {"label": candidate.params.label},
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: BetaRouterWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__ | {"label": item.params.label},
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _validation_window_payload(item: BetaRouterValidationWindow) -> dict[str, Any]:
    return {
        "name": item.name,
        "start_date": item.start_date,
        "end_date": item.end_date,
        **item.metrics.__dict__,
    }


def _metric_lines(label: str, metrics: dict[str, Any]) -> list[str]:
    return [
        f"- {label} annualized: `{_fmt(metrics.get('annualized_return_pct'))}%`",
        f"- {label} Sharpe: `{_fmt(metrics.get('sharpe_ratio'))}`",
        f"- {label} max drawdown: `{_fmt(metrics.get('max_drawdown_pct'))}%`",
        f"- {label} Alpha vs QQQ annualized: "
        f"`{_fmt(metrics.get('alpha_vs_market_buy_hold_annualized_pct'))}%`",
        f"- {label} Alpha vs TQQQ annualized: "
        f"`{_fmt(metrics.get('alpha_vs_leverage_buy_hold_annualized_pct'))}%`",
        f"- {label} exposure/rebalances: "
        f"`{_fmt(metrics.get('exposure_pct'))}% / {metrics.get('rebalance_count')}`",
    ]


def _params_grid_ranges(params_grid: list[BetaRouterParams]) -> dict[str, list[Any]]:
    keys = [
        "trend_sma_days",
        "momentum_lookback_days",
        "min_momentum_pct",
        "volatility_lookback_days",
        "max_volatility_annual_pct",
        "drawdown_lookback_days",
        "max_drawdown_pct",
        "leverage_trend_sma_days",
        "max_leverage_volatility_annual_pct",
        "leverage_drawdown_lookback_days",
        "max_leverage_drawdown_pct",
        "risk_on_weight",
        "neutral_weight",
        "risk_off_symbol",
        "risk_off_weight",
        "target_volatility_annual_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _cached_sma(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["sma"]
    if lookback not in values:
        values[lookback] = (
            pd.Series(cache["market_close"]).rolling(lookback).mean().to_numpy(dtype=float)
        )
    return values[lookback]


def _cached_momentum(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["momentum"]
    if lookback not in values:
        close = cache["market_close"]
        out = np.full(len(close), np.nan)
        out[lookback:] = (close[lookback:] / close[:-lookback] - 1) * 100
        values[lookback] = out
    return values[lookback]


def _cached_market_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["market_volatility"]
    if lookback not in values:
        close = pd.Series(cache["market_close"])
        values[lookback] = _realized_volatility(close, lookback)
    return values[lookback]


def _cached_leverage_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["leverage_volatility"]
    if lookback not in values:
        close = pd.Series(cache["leverage_close"])
        values[lookback] = _realized_volatility(close, lookback)
    return values[lookback]


def _cached_hedge_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["hedge_volatility"]
    if lookback not in values:
        close = pd.Series(cache["hedge_close"])
        values[lookback] = _realized_volatility(close, lookback)
    return values[lookback]


def _realized_volatility(close: pd.Series, lookback: int) -> np.ndarray:
    return close.pct_change().rolling(lookback).std().to_numpy(dtype=float) * math.sqrt(252) * 100


def _cached_drawdown(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["drawdown"]
    if lookback not in values:
        close = pd.Series(cache["market_close"])
        peak = close.rolling(lookback).max()
        values[lookback] = (close / peak - 1).to_numpy(dtype=float) * 100
    return values[lookback]


def _cached_leverage_sma(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache.setdefault("leverage_sma", {})
    if lookback not in values:
        values[lookback] = (
            pd.Series(cache["leverage_close"]).rolling(lookback).mean().to_numpy(dtype=float)
        )
    return values[lookback]


def _cached_leverage_drawdown(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache.setdefault("leverage_drawdown", {})
    if lookback not in values:
        close = pd.Series(cache["leverage_close"])
        peak = close.rolling(lookback).max()
        values[lookback] = (close / peak - 1).to_numpy(dtype=float) * 100
    return values[lookback]


def _next_open_returns(open_values: np.ndarray) -> np.ndarray:
    output = np.zeros(len(open_values))
    if len(open_values) > 1:
        output[:-1] = open_values[1:] / open_values[:-1] - 1
    return output


def _split_index(
    frame_len: int,
    out_of_sample_ratio: float,
    params_grid: list[BetaRouterParams],
) -> int:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - out_of_sample_ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _effective_lookback(params: BetaRouterParams) -> int:
    return max(
        params.trend_sma_days,
        params.momentum_lookback_days,
        params.volatility_lookback_days,
        params.drawdown_lookback_days,
    )


def _buy_hold_return(
    dataset: BetaRouterDataset,
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
    dataset: BetaRouterDataset,
    start_index: int,
    end_index: int,
) -> BetaRouterMetrics:
    return BetaRouterMetrics(
        days=0,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index] if end_index < len(dataset.dates) else None,
        total_return_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        annualized_volatility_pct=None,
        max_drawdown_pct=0.0,
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=0.0,
        market_buy_hold_annualized_pct=None,
        alpha_vs_market_buy_hold_annualized_pct=None,
        leverage_symbol=dataset.leverage_symbol,
        leverage_buy_hold_return_pct=0.0,
        leverage_buy_hold_annualized_pct=None,
        alpha_vs_leverage_buy_hold_annualized_pct=None,
        cash_proxy_return_pct=0.0,
        exposure_pct=0.0,
        average_gross_exposure_pct=0.0,
        max_gross_exposure_pct=0.0,
        rebalance_count=0,
        turnover_ratio=0.0,
        cost_drag_pct=0.0,
        risk_on_days=0,
        neutral_days=0,
        risk_off_days=0,
    )


def _label_optional(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)


def _parse_optional_int(value: str) -> int | None:
    return None if value == "none" else int(value)


def _label_optional_int(value: int | None) -> str:
    return "none" if value is None else str(value)


def _parse_asset_weight(value: str) -> tuple[BetaAsset, float]:
    for asset in _allowed_beta_assets():
        if value.startswith(asset):
            return asset, float(value.removeprefix(asset) or 0.0)  # type: ignore[return-value]
    raise ValueError(f"invalid beta asset weight: {value}")


def _beta_assets(values: list[str] | None) -> list[BetaAsset] | None:
    if values is None:
        return None
    allowed = set(_allowed_beta_assets())
    assets = [item.strip().upper() for item in values if item.strip()]
    unknown = sorted(set(assets) - allowed)
    if unknown:
        raise ValueError(f"unsupported beta asset(s): {', '.join(unknown)}")
    return assets  # type: ignore[return-value]


def _allowed_beta_assets() -> tuple[BetaAsset, ...]:
    return ("TQQQ", "SOXL", "QQQ", "SMH", "SQQQ", "PSQ", "QID", "QLD", "CASH")


def _first_date_index(dataset: BetaRouterDataset, date: str) -> int | None:
    for index, value in enumerate(dataset.dates):
        if value >= date:
            return index
    return None


def _last_date_index(dataset: BetaRouterDataset, date: str) -> int | None:
    for index in range(len(dataset.dates) - 1, -1, -1):
        if dataset.dates[index] <= date:
            return min(index + 1, len(dataset.dates) - 1)
    return None


def _date_offset(date: str, *, months: int) -> str:
    return (pd.Timestamp(date) - pd.DateOffset(months=months)).date().isoformat()


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


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
