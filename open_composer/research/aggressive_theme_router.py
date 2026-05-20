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

ThemeSymbol = Literal["SMH", "SOXX", "XLK", "IGV", "ARKK", "IWM", "DIA"]
LeveredSymbol = Literal["TQQQ", "QLD", "SOXL"]
DefensiveSymbol = Literal["QQQ", "SPY", "CASH"]

THEME_SYMBOLS: tuple[ThemeSymbol, ...] = ("SMH", "SOXX", "XLK", "IGV", "ARKK", "IWM", "DIA")
LEVERED_SYMBOLS: tuple[LeveredSymbol, ...] = ("TQQQ", "QLD", "SOXL")
DEFENSIVE_SYMBOLS: tuple[DefensiveSymbol, ...] = ("QQQ", "SPY", "CASH")
REQUIRED_SYMBOLS: tuple[str, ...] = (
    "QQQ",
    "SPY",
    *THEME_SYMBOLS,
    *LEVERED_SYMBOLS,
)


@dataclass(frozen=True)
class AggressiveThemeParams:
    trend_sma_days: int
    momentum_lookback_days: int
    top_n: int
    min_theme_momentum_pct: float
    core_weight: float
    theme_gross_weight: float
    levered_symbol: LeveredSymbol
    levered_weight: float
    defensive_symbol: DefensiveSymbol
    defensive_weight: float
    volatility_lookback_days: int
    target_portfolio_volatility_pct: float | None
    max_market_volatility_pct: float | None
    drawdown_lookback_days: int
    max_market_drawdown_pct: float | None
    rebalance_threshold_pct: float

    @property
    def label(self) -> str:
        return (
            f"aggr_theme:sma{self.trend_sma_days}_mom{self.momentum_lookback_days}_"
            f"top{self.top_n}_min{self.min_theme_momentum_pct:g}_core{self.core_weight:g}_"
            f"theme{self.theme_gross_weight:g}_lev{self.levered_symbol}{self.levered_weight:g}_"
            f"def{self.defensive_symbol}{self.defensive_weight:g}_vol{self.volatility_lookback_days}_"
            f"tvol{_label_optional(self.target_portfolio_volatility_pct)}_"
            f"maxv{_label_optional(self.max_market_volatility_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{_label_optional(self.max_market_drawdown_pct)}_"
            f"thr{self.rebalance_threshold_pct:g}"
        )


@dataclass(frozen=True)
class AggressiveThemeMetrics:
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
    spy_buy_hold_return_pct: float
    spy_buy_hold_annualized_pct: float | None
    alpha_vs_spy_buy_hold_annualized_pct: float | None
    equal_weight_return_pct: float
    equal_weight_annualized_pct: float | None
    alpha_vs_equal_weight_annualized_pct: float | None
    best_symbol: str | None
    best_symbol_buy_hold_return_pct: float
    alpha_vs_best_symbol_buy_hold_pct: float
    exposure_pct: float
    average_gross_exposure_pct: float
    max_gross_exposure_pct: float
    rebalance_count: int
    turnover_ratio: float
    cost_drag_pct: float
    risk_on_days: int
    defensive_days: int


@dataclass(frozen=True)
class AggressiveThemeCandidate:
    rank: int
    params: AggressiveThemeParams
    score: float
    train: AggressiveThemeMetrics
    out_of_sample: AggressiveThemeMetrics
    full_window: AggressiveThemeMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class AggressiveThemeWalkForwardSlice:
    fold: int
    params: AggressiveThemeParams
    train: AggressiveThemeMetrics
    test: AggressiveThemeMetrics


@dataclass(frozen=True)
class AggressiveThemeResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


@dataclass(frozen=True)
class AggressiveThemeDataset:
    frame: pd.DataFrame
    dates: list[str]
    data_profile: dict[str, Any]


@dataclass(frozen=True)
class AggressiveThemeSnapshot:
    state: str
    weights: dict[str, float]
    selected_themes: list[str]
    portfolio_volatility_scale: float
    trend_ok: bool
    market_volatility_ok: bool
    market_drawdown_ok: bool


def run_aggressive_theme_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    trend_sma_days: list[int] | None = None,
    momentum_lookback_days: list[int] | None = None,
    top_n_values: list[int] | None = None,
    min_theme_momentum_pct: list[float] | None = None,
    core_weight: list[float] | None = None,
    theme_gross_weight: list[float] | None = None,
    levered_symbol: list[str] | None = None,
    levered_weight: list[float] | None = None,
    defensive_symbol: list[str] | None = None,
    defensive_weight: list[float] | None = None,
    volatility_lookback_days: list[int] | None = None,
    target_portfolio_volatility_pct: list[float | None] | None = None,
    max_market_volatility_pct: list[float | None] | None = None,
    drawdown_lookback_days: list[int] | None = None,
    max_market_drawdown_pct: list[float | None] | None = None,
    rebalance_threshold_pct: list[float] | None = None,
    out_of_sample_ratio: float = 0.35,
    walk_forward_folds: int = 5,
    walk_forward_top_k: int | None = 30,
    max_candidates: int = 1600,
    refresh_data: bool = False,
) -> AggressiveThemeResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    dataset = load_aggressive_theme_dataset(
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
        momentum_lookback_days or [42, 63, 126],
        top_n_values or [1, 2],
        min_theme_momentum_pct or [0.0, 5.0],
        core_weight or [0.0, 0.25],
        theme_gross_weight or [0.65, 0.8],
        _levered_symbols(levered_symbol) or ["TQQQ", "QLD", "SOXL"],
        levered_weight or [0.0, 0.2, 0.35],
        _defensive_symbols(defensive_symbol) or ["QQQ", "SPY", "CASH"],
        defensive_weight or [0.0, 0.5, 0.75],
        volatility_lookback_days or [20],
        target_portfolio_volatility_pct or [None, 35.0, 45.0],
        max_market_volatility_pct or [None, 35.0],
        drawdown_lookback_days or [60, 120],
        max_market_drawdown_pct or [None, 15.0, 20.0],
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

    json_path = base / "reports" / "research" / f"{spec.name}-aggressive-theme-router.json"
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
    return AggressiveThemeResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=candidates[0].params.label,
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def load_aggressive_theme_dataset(
    *,
    root: Path,
    data_source: str,
    feed: str | None,
    timeframe: str,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> AggressiveThemeDataset:
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
        for symbol in REQUIRED_SYMBOLS
    }
    frame: pd.DataFrame | None = None
    for symbol, symbol_frame in frames.items():
        renamed = symbol_frame[["timestamp", "open", "close"]].rename(
            columns={"open": f"{symbol}_open", "close": f"{symbol}_close"}
        )
        frame = renamed if frame is None else frame.merge(renamed, on="timestamp", how="inner")
    if frame is None:
        raise ValueError("aggressive theme router produced no data frame")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if len(frame) < 260:
        raise ValueError("aggressive theme router requires at least 260 common daily bars")
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
        for symbol in REQUIRED_SYMBOLS
    ]
    return AggressiveThemeDataset(
        frame=frame,
        dates=dates,
        data_profile=combined_data_profile(profiles),
    )


def aggressive_theme_params_from_label(label: str) -> AggressiveThemeParams:
    if not label.startswith("aggr_theme:"):
        raise ValueError(f"not an aggressive theme route label: {label}")
    raw: dict[str, str] = {}
    for part in label.removeprefix("aggr_theme:").split("_"):
        for prefix in [
            "sma",
            "mom",
            "top",
            "min",
            "core",
            "theme",
            "lev",
            "def",
            "vol",
            "tvol",
            "maxv",
            "dd",
            "maxdd",
            "thr",
        ]:
            if part.startswith(prefix):
                raw[prefix] = part.removeprefix(prefix)
                break
    levered, levered_weight = _parse_levered_weight(raw["lev"])
    defensive, defensive_weight = _parse_defensive_weight(raw["def"])
    return AggressiveThemeParams(
        trend_sma_days=int(raw["sma"]),
        momentum_lookback_days=int(raw["mom"]),
        top_n=int(raw["top"]),
        min_theme_momentum_pct=float(raw["min"]),
        core_weight=float(raw["core"]),
        theme_gross_weight=float(raw["theme"]),
        levered_symbol=levered,
        levered_weight=levered_weight,
        defensive_symbol=defensive,
        defensive_weight=defensive_weight,
        volatility_lookback_days=int(raw["vol"]),
        target_portfolio_volatility_pct=_parse_optional_float(raw["tvol"]),
        max_market_volatility_pct=_parse_optional_float(raw["maxv"]),
        drawdown_lookback_days=int(raw["dd"]),
        max_market_drawdown_pct=_parse_optional_float(raw["maxdd"]),
        rebalance_threshold_pct=float(raw["thr"]),
    )


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
    top_n_values: list[int],
    min_momentum_values: list[float],
    core_values: list[float],
    theme_values: list[float],
    levered_symbols: list[LeveredSymbol],
    levered_values: list[float],
    defensive_symbols: list[DefensiveSymbol],
    defensive_values: list[float],
    volatility_values: list[int],
    target_volatility_values: list[float | None],
    max_volatility_values: list[float | None],
    drawdown_values: list[int],
    max_drawdown_values: list[float | None],
    rebalance_threshold_values: list[float],
    *,
    max_candidates: int,
) -> list[AggressiveThemeParams]:
    total = math.prod(
        [
            len(trend_values),
            len(momentum_values),
            len(top_n_values),
            len(min_momentum_values),
            len(core_values),
            len(theme_values),
            len(levered_symbols),
            len(levered_values),
            len(defensive_symbols),
            len(defensive_values),
            len(volatility_values),
            len(target_volatility_values),
            len(max_volatility_values),
            len(drawdown_values),
            len(max_drawdown_values),
            len(rebalance_threshold_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"aggressive theme router grid would create {total} candidates; raise "
            f"--max-candidates above {total} or narrow the grid"
        )
    params: list[AggressiveThemeParams] = []
    for item in product(
        trend_values,
        momentum_values,
        top_n_values,
        min_momentum_values,
        core_values,
        theme_values,
        levered_symbols,
        levered_values,
        defensive_symbols,
        defensive_values,
        volatility_values,
        target_volatility_values,
        max_volatility_values,
        drawdown_values,
        max_drawdown_values,
        rebalance_threshold_values,
    ):
        (
            trend,
            momentum,
            top_n,
            min_momentum,
            core,
            theme,
            levered_symbol,
            levered,
            defensive_symbol,
            defensive,
            volatility,
            target_volatility,
            max_volatility,
            drawdown,
            max_drawdown,
            threshold,
        ) = item
        if min(trend, momentum, top_n, volatility, drawdown) < 1:
            continue
        if min(core, theme, levered, defensive, threshold) < 0:
            continue
        if max(core, theme, levered, defensive) > 1.0:
            continue
        if defensive_symbol == "CASH" and defensive != 0:
            continue
        if core + theme + levered > 1.0:
            continue
        params.append(
            AggressiveThemeParams(
                trend_sma_days=trend,
                momentum_lookback_days=momentum,
                top_n=top_n,
                min_theme_momentum_pct=min_momentum,
                core_weight=core,
                theme_gross_weight=theme,
                levered_symbol=levered_symbol,
                levered_weight=levered,
                defensive_symbol=defensive_symbol,
                defensive_weight=defensive,
                volatility_lookback_days=volatility,
                target_portfolio_volatility_pct=target_volatility,
                max_market_volatility_pct=max_volatility,
                drawdown_lookback_days=drawdown,
                max_market_drawdown_pct=max_drawdown,
                rebalance_threshold_pct=threshold,
            )
        )
    if not params:
        raise ValueError("aggressive theme router grid produced no valid candidates")
    return params


def _build_indicator_cache(dataset: AggressiveThemeDataset) -> dict[str, Any]:
    frame = dataset.frame
    close = pd.DataFrame(
        {symbol: frame[f"{symbol}_close"].astype(float) for symbol in REQUIRED_SYMBOLS}
    )
    open_ = pd.DataFrame(
        {symbol: frame[f"{symbol}_open"].astype(float) for symbol in REQUIRED_SYMBOLS}
    )
    return {
        "close": close,
        "open": open_,
        "close_np": close.to_numpy(dtype=float),
        "open_np": open_.to_numpy(dtype=float),
        "open_return": ((open_.shift(-1) / open_) - 1.0).to_numpy(dtype=float),
        "symbol_index": {symbol: index for index, symbol in enumerate(REQUIRED_SYMBOLS)},
        "theme_indices": np.array([REQUIRED_SYMBOLS.index(symbol) for symbol in THEME_SYMBOLS]),
        "sma": {},
        "momentum": {},
        "market_volatility": {},
        "portfolio_volatility": {},
        "drawdown": {},
    }


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: AggressiveThemeDataset,
    cache: dict[str, Any],
    params_grid: list[AggressiveThemeParams],
    out_of_sample_ratio: float,
) -> list[AggressiveThemeCandidate]:
    split = _split_index(len(dataset.frame), out_of_sample_ratio, params_grid)
    rows: list[AggressiveThemeCandidate] = []
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
            AggressiveThemeCandidate(
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
        AggressiveThemeCandidate(
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
    params_grid: list[AggressiveThemeParams],
    candidates: list[AggressiveThemeCandidate],
    walk_forward_top_k: int | None,
) -> list[AggressiveThemeParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: AggressiveThemeDataset,
    cache: dict[str, Any],
    params_grid: list[AggressiveThemeParams],
    folds: int,
) -> list[AggressiveThemeWalkForwardSlice]:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.frame) - max_lookback) // (max(folds, 1) + 1), 20)
    rows: list[AggressiveThemeWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.frame) - 1, test_start + fold_size)
        if test_end - test_start < 20:
            continue
        scored: list[tuple[float, AggressiveThemeParams]] = []
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
            AggressiveThemeWalkForwardSlice(
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
    dataset: AggressiveThemeDataset,
    cache: dict[str, Any],
    params: AggressiveThemeParams,
    *,
    start_index: int,
    end_index: int,
    evaluation_start_index: int | None = None,
    start_equity: float = 100_000.0,
) -> AggressiveThemeMetrics:
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
    previous_weights = {symbol: 0.0 for symbol in REQUIRED_SYMBOLS}
    rebalance_count = 0
    turnover_ratio = 0.0
    cost_drag = 0.0
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    threshold = params.rebalance_threshold_pct / 100

    for index in range(start_index, end_index):
        snapshot = _target_snapshot(dataset, cache, params, index)
        weights = {symbol: snapshot.weights.get(symbol, 0.0) for symbol in REQUIRED_SYMBOLS}
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
        period_return = 0.0
        for symbol, weight in weights.items():
            symbol_index = cache["symbol_index"][symbol]
            period_return += weight * float(cache["open_return"][index, symbol_index])
        period_return -= cost
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
    spy_buy_hold = _buy_hold_return(dataset, "SPY", start_index, end_index)
    equal_weight = mean(
        _buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in [*THEME_SYMBOLS, "QQQ", "SPY"]
    )
    universe_returns = {
        symbol: _buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in REQUIRED_SYMBOLS
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = metrics.annualized_return_pct
    qqq_ann = _annualized_from_total(qqq_buy_hold, days)
    spy_ann = _annualized_from_total(spy_buy_hold, days)
    equal_ann = _annualized_from_total(equal_weight, days)
    return AggressiveThemeMetrics(
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
        spy_buy_hold_return_pct=spy_buy_hold,
        spy_buy_hold_annualized_pct=spy_ann,
        alpha_vs_spy_buy_hold_annualized_pct=_alpha(annualized, spy_ann),
        equal_weight_return_pct=equal_weight,
        equal_weight_annualized_pct=equal_ann,
        alpha_vs_equal_weight_annualized_pct=_alpha(annualized, equal_ann),
        best_symbol=best_symbol,
        best_symbol_buy_hold_return_pct=best_return,
        alpha_vs_best_symbol_buy_hold_pct=(equity / start_equity - 1) * 100 - best_return,
        exposure_pct=sum(1 for value in gross_exposures if value > 0) / days * 100 if days else 0.0,
        average_gross_exposure_pct=mean(gross_exposures) * 100 if gross_exposures else 0.0,
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        rebalance_count=rebalance_count,
        turnover_ratio=turnover_ratio,
        cost_drag_pct=cost_drag * 100,
        risk_on_days=sum(1 for item in states if item == "risk_on"),
        defensive_days=sum(1 for item in states if item == "defensive"),
    )


def _target_snapshot(
    dataset: AggressiveThemeDataset,
    cache: dict[str, Any],
    params: AggressiveThemeParams,
    index: int,
) -> AggressiveThemeSnapshot:
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    qqq_idx = cache["symbol_index"]["QQQ"]
    qqq_close = cache["close_np"][:, qqq_idx]
    trend_sma = _cached_sma(cache, params.trend_sma_days)
    market_volatility = _cached_market_volatility(cache, params.volatility_lookback_days)
    drawdown = _cached_drawdown(cache, params.drawdown_lookback_days)
    trend_ok = bool(qqq_close[previous_index] > trend_sma[previous_index])
    volatility_value = market_volatility[previous_index]
    volatility_ok = True
    if params.max_market_volatility_pct is not None and not np.isnan(volatility_value):
        volatility_ok = bool(volatility_value <= params.max_market_volatility_pct)
    drawdown_value = drawdown[previous_index]
    drawdown_ok = True
    if params.max_market_drawdown_pct is not None and not np.isnan(drawdown_value):
        drawdown_ok = bool(abs(min(float(drawdown_value), 0.0)) <= params.max_market_drawdown_pct)

    if not (trend_ok and volatility_ok and drawdown_ok):
        weights: dict[str, float] = {}
        if params.defensive_symbol != "CASH" and params.defensive_weight > 0:
            weights[params.defensive_symbol] = params.defensive_weight
        return AggressiveThemeSnapshot(
            state="defensive",
            weights=weights,
            selected_themes=[],
            portfolio_volatility_scale=1.0,
            trend_ok=trend_ok,
            market_volatility_ok=volatility_ok,
            market_drawdown_ok=drawdown_ok,
        )

    selected = _selected_themes(cache, params, previous_index)
    weights = {}
    if params.core_weight > 0:
        weights["QQQ"] = params.core_weight
    if selected:
        per_theme = params.theme_gross_weight / len(selected)
        for symbol in selected:
            weights[symbol] = weights.get(symbol, 0.0) + per_theme
    if params.levered_weight > 0:
        weights[params.levered_symbol] = (
            weights.get(params.levered_symbol, 0.0) + params.levered_weight
        )
    weights = _cap_gross(weights)
    vol_scale = _portfolio_volatility_scale(cache, params, weights, previous_index)
    weights = {symbol: weight * vol_scale for symbol, weight in weights.items() if weight > 0}
    return AggressiveThemeSnapshot(
        state="risk_on",
        weights=weights,
        selected_themes=selected,
        portfolio_volatility_scale=vol_scale,
        trend_ok=trend_ok,
        market_volatility_ok=volatility_ok,
        market_drawdown_ok=drawdown_ok,
    )


def _selected_themes(
    cache: dict[str, Any],
    params: AggressiveThemeParams,
    previous_index: int,
) -> list[str]:
    momentum = _cached_momentum(cache, params.momentum_lookback_days)
    theme_indices = cache["theme_indices"]
    scores = momentum[previous_index, theme_indices].copy()
    scores[~np.isfinite(scores)] = -np.inf
    scores[scores < params.min_theme_momentum_pct] = -np.inf
    finite = np.isfinite(scores)
    if not finite.any():
        return []
    count = min(params.top_n, int(finite.sum()))
    selected_positions = np.argpartition(scores, -count)[-count:]
    selected_positions = selected_positions[np.argsort(scores[selected_positions])[::-1]]
    return [THEME_SYMBOLS[int(position)] for position in selected_positions]


def _portfolio_volatility_scale(
    cache: dict[str, Any],
    params: AggressiveThemeParams,
    weights: dict[str, float],
    previous_index: int,
) -> float:
    if params.target_portfolio_volatility_pct is None or not weights:
        return 1.0
    vol = _cached_portfolio_volatility(cache, params, weights)
    value = vol[previous_index]
    if np.isnan(value) or value <= 0:
        return 1.0
    return max(0.0, min(1.0, params.target_portfolio_volatility_pct / float(value)))


def _score_candidate(metrics: AggressiveThemeMetrics) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    alpha = metrics.alpha_vs_qqq_buy_hold_annualized_pct or -100.0
    ew_alpha = metrics.alpha_vs_equal_weight_annualized_pct or -100.0
    drawdown_penalty = abs(min(metrics.max_drawdown_pct, 0.0)) * 0.45
    turnover_penalty = max(0, metrics.rebalance_count - 100) * 0.08
    high_sharpe_penalty = max(0.0, sharpe - 2.5) * 35
    sparse_penalty = max(0.0, 35.0 - metrics.exposure_pct) * 0.35
    return (
        alpha
        + annualized * 0.35
        + ew_alpha * 0.25
        + min(sharpe, 2.5) * 10
        - drawdown_penalty
        - turnover_penalty
        - high_sharpe_penalty
        - sparse_penalty
    )


def _quality_flags(
    train: AggressiveThemeMetrics,
    oos: AggressiveThemeMetrics,
    full: AggressiveThemeMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq")
    if (oos.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq")
    if (full.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq")
    if (full.alpha_vs_equal_weight_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_equal_weight")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.8:
        flags.append("oos_low_sharpe")
    if oos.max_drawdown_pct <= -35:
        flags.append("oos_large_drawdown")
    if full.max_drawdown_pct <= -38:
        flags.append("full_large_drawdown")
    if full.rebalance_count > max(100, full.days // 3):
        flags.append("high_turnover")
    if (train.sharpe_ratio or 0.0) > 2.5 or (oos.sharpe_ratio or 0.0) > 2.5:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if oos.exposure_pct < 35:
        flags.append("oos_too_sparse")
    return flags


def _acceptance_gate(
    candidate: AggressiveThemeCandidate,
    walk_forward: list[AggressiveThemeWalkForwardSlice],
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
        and (candidate.full_window.alpha_vs_equal_weight_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.annualized_return_pct or -100.0) >= 15
        and 0.8 <= oos_sharpe <= 2.5
        and full_sharpe <= 2.5
        and candidate.out_of_sample.max_drawdown_pct > -35
        and candidate.full_window.max_drawdown_pct > -38
        and candidate.full_window.max_gross_exposure_pct <= 100
        and candidate.full_window.rebalance_count <= max(100, candidate.full_window.days // 3)
        and wf_count > 0
        and wf_positive >= max(1, math.ceil(wf_count * 0.6))
        and not {"oos_too_sparse", "suspiciously_high_sharpe_review_overfit"}.intersection(
            candidate.quality_flags
        )
    )
    return {
        "passed": passed,
        "objective": "aggressive_theme_alpha_vs_qqq_after_costs",
        "train_alpha_vs_qqq_annualized_pct": candidate.train.alpha_vs_qqq_buy_hold_annualized_pct,
        "oos_alpha_vs_qqq_annualized_pct": (
            candidate.out_of_sample.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "full_alpha_vs_qqq_annualized_pct": (
            candidate.full_window.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "full_alpha_vs_equal_weight_annualized_pct": (
            candidate.full_window.alpha_vs_equal_weight_annualized_pct
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
    candidate: AggressiveThemeCandidate,
    walk_forward: list[AggressiveThemeWalkForwardSlice],
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
    dataset: AggressiveThemeDataset,
    params_grid: list[AggressiveThemeParams],
    candidates: list[AggressiveThemeCandidate],
    walk_forward: list[AggressiveThemeWalkForwardSlice],
    pass_status: dict[str, Any],
    start: str | None,
    end: str | None,
    runtime: dict[str, Any],
    walk_forward_top_k: int | None,
) -> dict[str, Any]:
    return {
        "strategy_name": spec.name,
        "mode": "aggressive_theme_router",
        "source_spec_path": _relpath(spec_path, spec_path.parents[2]),
        "research_window": {"start": start, "end": end},
        "symbols": list(REQUIRED_SYMBOLS),
        "theme_symbols": list(THEME_SYMBOLS),
        "levered_symbols": list(LEVERED_SYMBOLS),
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective="aggressive but risk-managed Alpha versus QQQ buy-and-hold",
            hypothesis=(
                "Theme momentum plus bounded leveraged satellite exposure can outperform QQQ "
                "during persistent technology/semiconductor cycles while QQQ/SPY/cash defensive "
                "routing limits drawdowns."
            ),
            constraints=[
                "Signals use only information visible after the previous daily close.",
                "Target weights are applied at the next regular-session open.",
                "Gross exposure is capped at 100%; no shorts or margin are modeled.",
                "LLM/news is advisory context only and not an execution factor.",
            ],
        ),
        "search_space": search_space(
            family="aggressive_theme_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "core + theme + levered weight <= 100%",
                "risk-off routes to QQQ, SPY, or cash",
                "train-only ranking; OOS and walk-forward are validation",
                "rebalance threshold may suppress small weight changes",
            ],
        ),
        "references": [
            {
                "title": "Time Series Momentum",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463",
                "used_for": "trend-following and absolute momentum framing",
            },
            {
                "title": "Momentum Has Its Moments",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "used_for": "volatility-managed momentum risk control",
            },
            {
                "title": "Absolute Momentum",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2244633",
                "used_for": "defensive switching after weak absolute momentum",
            },
            {
                "title": "A Century of Evidence on Trend-Following Investing",
                "url": "https://www.aqr.com/Insights/Research/White-Papers/A-Century-of-Evidence-on-Trend-Following-Investing",
                "used_for": "trend-following robustness framing",
            },
        ],
        "anti_leakage": [
            "Each target uses index-1 close-derived indicators.",
            "Backtest return is open[index] to open[index+1], after signal close.",
            "Walk-forward folds reselect parameters only from earlier data.",
            "OOS metrics never enter the training score.",
        ],
        "acceptance_standard": {
            "train_oos_full_alpha_vs_qqq_annualized_pct": "> 0",
            "full_alpha_vs_equal_weight_annualized_pct": "> 0",
            "oos_annualized_return_pct": ">= 15",
            "oos_sharpe_ratio": "0.8 to 2.5",
            "max_drawdown_pct": "OOS > -35 and full > -38",
            "walk_forward": "at least 60% positive Alpha folds",
            "turnover": "full rebalances <= max(100, days / 3)",
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
        f"# Aggressive Theme Router Research: {payload['strategy_name']}",
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
            "- High Sharpe or cycle-concentrated results are treated as overfit warnings.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: AggressiveThemeCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__ | {"label": candidate.params.label},
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: AggressiveThemeWalkForwardSlice) -> dict[str, Any]:
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
        f"- {label} Alpha vs equal-weight annualized: "
        f"`{_fmt(metrics.get('alpha_vs_equal_weight_annualized_pct'))}%`",
        f"- {label} exposure/rebalances: "
        f"`{_fmt(metrics.get('exposure_pct'))}% / {metrics.get('rebalance_count')}`",
    ]


def _params_grid_ranges(params_grid: list[AggressiveThemeParams]) -> dict[str, list[Any]]:
    keys = [
        "trend_sma_days",
        "momentum_lookback_days",
        "top_n",
        "min_theme_momentum_pct",
        "core_weight",
        "theme_gross_weight",
        "levered_symbol",
        "levered_weight",
        "defensive_symbol",
        "defensive_weight",
        "volatility_lookback_days",
        "target_portfolio_volatility_pct",
        "max_market_volatility_pct",
        "drawdown_lookback_days",
        "max_market_drawdown_pct",
        "rebalance_threshold_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _cached_sma(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["sma"]
    if lookback not in values:
        qqq_idx = cache["symbol_index"]["QQQ"]
        values[lookback] = (
            pd.Series(cache["close_np"][:, qqq_idx]).rolling(lookback).mean().to_numpy(dtype=float)
        )
    return values[lookback]


def _cached_momentum(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["momentum"]
    if lookback not in values:
        close = cache["close_np"]
        output = np.full(close.shape, np.nan)
        output[lookback:, :] = (close[lookback:, :] / close[:-lookback, :] - 1.0) * 100
        values[lookback] = output
    return values[lookback]


def _cached_market_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["market_volatility"]
    if lookback not in values:
        qqq_idx = cache["symbol_index"]["QQQ"]
        values[lookback] = _realized_volatility(cache["close_np"][:, qqq_idx], lookback)
    return values[lookback]


def _cached_portfolio_volatility(
    cache: dict[str, Any],
    params: AggressiveThemeParams,
    weights: dict[str, float],
) -> np.ndarray:
    values = cache["portfolio_volatility"]
    key = (
        params.volatility_lookback_days,
        tuple(sorted((symbol, round(weight, 6)) for symbol, weight in weights.items())),
    )
    if key not in values:
        returns = np.zeros(len(cache["close_np"]))
        for symbol, weight in weights.items():
            symbol_index = cache["symbol_index"][symbol]
            close = cache["close_np"][:, symbol_index]
            symbol_returns = np.zeros(len(close))
            symbol_returns[1:] = close[1:] / close[:-1] - 1.0
            returns += weight * symbol_returns
        values[key] = (
            pd.Series(returns).rolling(params.volatility_lookback_days).std().to_numpy(dtype=float)
            * math.sqrt(252)
            * 100
        )
    return values[key]


def _cached_drawdown(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["drawdown"]
    if lookback not in values:
        qqq_idx = cache["symbol_index"]["QQQ"]
        close = pd.Series(cache["close_np"][:, qqq_idx])
        peak = close.rolling(lookback).max()
        values[lookback] = (close / peak - 1).to_numpy(dtype=float) * 100
    return values[lookback]


def _realized_volatility(close: np.ndarray, lookback: int) -> np.ndarray:
    returns = pd.Series(close).pct_change()
    return returns.rolling(lookback).std().to_numpy(dtype=float) * math.sqrt(252) * 100


def _split_index(
    frame_len: int,
    out_of_sample_ratio: float,
    params_grid: list[AggressiveThemeParams],
) -> int:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - out_of_sample_ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _effective_lookback(params: AggressiveThemeParams) -> int:
    return max(
        params.trend_sma_days,
        params.momentum_lookback_days,
        params.volatility_lookback_days,
        params.drawdown_lookback_days,
    )


def _buy_hold_return(
    dataset: AggressiveThemeDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if symbol == "CASH" or end_index <= start_index:
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
    dataset: AggressiveThemeDataset,
    start_index: int,
    end_index: int,
) -> AggressiveThemeMetrics:
    return AggressiveThemeMetrics(
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
        spy_buy_hold_return_pct=0.0,
        spy_buy_hold_annualized_pct=None,
        alpha_vs_spy_buy_hold_annualized_pct=None,
        equal_weight_return_pct=0.0,
        equal_weight_annualized_pct=None,
        alpha_vs_equal_weight_annualized_pct=None,
        best_symbol=None,
        best_symbol_buy_hold_return_pct=0.0,
        alpha_vs_best_symbol_buy_hold_pct=0.0,
        exposure_pct=0.0,
        average_gross_exposure_pct=0.0,
        max_gross_exposure_pct=0.0,
        rebalance_count=0,
        turnover_ratio=0.0,
        cost_drag_pct=0.0,
        risk_on_days=0,
        defensive_days=0,
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


def _parse_levered_weight(value: str) -> tuple[LeveredSymbol, float]:
    for asset in LEVERED_SYMBOLS:
        if value.startswith(asset):
            return asset, float(value.removeprefix(asset) or 0.0)
    raise ValueError(f"invalid levered asset weight: {value}")


def _parse_defensive_weight(value: str) -> tuple[DefensiveSymbol, float]:
    for asset in DEFENSIVE_SYMBOLS:
        if value.startswith(asset):
            return asset, float(value.removeprefix(asset) or 0.0)
    raise ValueError(f"invalid defensive asset weight: {value}")


def _levered_symbols(values: list[str] | None) -> list[LeveredSymbol] | None:
    if values is None:
        return None
    assets = [item.strip().upper() for item in values if item.strip()]
    unknown = sorted(set(assets) - set(LEVERED_SYMBOLS))
    if unknown:
        raise ValueError(f"unsupported levered asset(s): {', '.join(unknown)}")
    return assets  # type: ignore[return-value]


def _defensive_symbols(values: list[str] | None) -> list[DefensiveSymbol] | None:
    if values is None:
        return None
    assets = [item.strip().upper() for item in values if item.strip()]
    unknown = sorted(set(assets) - set(DEFENSIVE_SYMBOLS))
    if unknown:
        raise ValueError(f"unsupported defensive asset(s): {', '.join(unknown)}")
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
