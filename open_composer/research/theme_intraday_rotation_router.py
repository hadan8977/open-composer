from __future__ import annotations

import math
import re
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

BetaSymbol = Literal["QQQ", "QLD", "TQQQ"]
ScoreMode = Literal["raw", "composite", "risk_adjusted"]

BETA_SYMBOLS: tuple[str, ...] = ("QQQ", "QLD", "TQQQ")
THEME_SYMBOLS: tuple[str, ...] = ("SMH", "SOXX", "XLK", "IGV", "ARKK")
SEMICONDUCTOR_SYMBOLS: frozenset[str] = frozenset(
    {
        "NVDA",
        "AVGO",
        "AMD",
        "AMAT",
        "QCOM",
        "MU",
        "LRCX",
        "ASML",
        "KLAC",
        "MRVL",
        "INTC",
        "TXN",
        "ADI",
        "NXPI",
        "ARM",
        "MPWR",
        "CDNS",
        "SNPS",
    }
)


@dataclass(frozen=True)
class ThemeIntradayParams:
    market_sma_days: int
    market_momentum_days: int
    min_market_momentum_pct: float
    signal_momentum_days: int
    confirmation_days: int
    top_n: int
    beta_symbol: BetaSymbol
    beta_weight: float
    satellite_weight: float
    max_symbol_weight: float
    market_below_sma_scale: float
    target_market_volatility_pct: float | None
    drawdown_lookback_days: int
    max_market_drawdown_pct: float | None
    score_mode: ScoreMode
    semiconductor_gate: bool

    @property
    def label(self) -> str:
        return (
            f"theme_intraday:sma{self.market_sma_days}_"
            f"mmom{self.market_momentum_days}_minm{self.min_market_momentum_pct:g}_"
            f"lb{self.signal_momentum_days}_conf{self.confirmation_days}_top{self.top_n}_"
            f"beta{self.beta_symbol}{self.beta_weight:g}_sat{self.satellite_weight:g}_"
            f"maxw{self.max_symbol_weight:g}_off{self.market_below_sma_scale:g}_"
            f"tvol{_label_optional(self.target_market_volatility_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{_label_optional(self.max_market_drawdown_pct)}_"
            f"score{self.score_mode}_sem{int(self.semiconductor_gate)}"
        )


@dataclass(frozen=True)
class ThemeIntradayMetrics:
    days: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    annualized_volatility_pct: float | None
    max_drawdown_pct: float
    traded_days: int
    round_trips: int
    exposure_pct: float
    average_gross_exposure_pct: float
    max_gross_exposure_pct: float
    max_symbol_weight_pct: float
    win_day_pct: float
    profit_factor: float | None
    average_win_pct: float | None
    average_loss_pct: float | None
    payoff_ratio: float | None
    cost_drag_pct: float
    qqq_buy_hold_return_pct: float
    qqq_buy_hold_annualized_pct: float | None
    alpha_vs_qqq_buy_hold_annualized_pct: float | None
    tqqq_buy_hold_return_pct: float
    tqqq_buy_hold_annualized_pct: float | None
    alpha_vs_tqqq_buy_hold_annualized_pct: float | None
    qqq_intraday_annualized_pct: float | None
    alpha_vs_qqq_intraday_annualized_pct: float | None
    equal_weight_buy_hold_annualized_pct: float | None
    alpha_vs_equal_weight_buy_hold_annualized_pct: float | None
    equal_weight_intraday_annualized_pct: float | None
    alpha_vs_equal_weight_intraday_annualized_pct: float | None
    smh_buy_hold_annualized_pct: float | None
    alpha_vs_smh_buy_hold_annualized_pct: float | None
    best_symbol: str | None
    best_symbol_buy_hold_return_pct: float
    alpha_vs_best_symbol_buy_hold_pct: float
    market_scaled_days: int
    volatility_scaled_days: int
    drawdown_brake_days: int
    semiconductor_blocked_days: int


@dataclass(frozen=True)
class ThemeIntradayCandidate:
    rank: int
    params: ThemeIntradayParams
    score: float
    train: ThemeIntradayMetrics
    out_of_sample: ThemeIntradayMetrics
    full_window: ThemeIntradayMetrics
    ytd_2026: ThemeIntradayMetrics | None
    quality_flags: list[str]


@dataclass(frozen=True)
class ThemeIntradayWalkForwardSlice:
    fold: int
    params: ThemeIntradayParams
    train: ThemeIntradayMetrics
    test: ThemeIntradayMetrics


@dataclass(frozen=True)
class ThemeIntradayResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


@dataclass(frozen=True)
class ThemeIntradayDataset:
    frame: pd.DataFrame
    dates: list[str]
    symbols: list[str]
    market_symbol: str
    benchmark_symbol: str
    candidate_symbols: list[str]
    data_profile: dict[str, Any]


@dataclass(frozen=True)
class ThemeIntradaySnapshot:
    selected: list[str]
    weights: dict[str, float]
    market_scale: float
    volatility_scale: float
    drawdown_scale: float
    semiconductor_blocked_count: int


def run_theme_intraday_rotation_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    market_symbol: str = "QQQ",
    benchmark_symbol: str = "TQQQ",
    market_sma_days: list[int] | None = None,
    market_momentum_days: list[int] | None = None,
    min_market_momentum_pct: list[float] | None = None,
    signal_momentum_days: list[int] | None = None,
    confirmation_days: list[int] | None = None,
    top_n: list[int] | None = None,
    beta_symbol: list[str] | None = None,
    beta_weight: list[float] | None = None,
    satellite_weight: list[float] | None = None,
    max_symbol_weight: list[float] | None = None,
    market_below_sma_scale: list[float] | None = None,
    target_market_volatility_pct: list[float | None] | None = None,
    drawdown_lookback_days: list[int] | None = None,
    max_market_drawdown_pct: list[float | None] | None = None,
    score_mode: list[str] | None = None,
    semiconductor_gate: list[bool] | None = None,
    out_of_sample_ratio: float = 0.30,
    walk_forward_folds: int = 5,
    walk_forward_top_k: int | None = 30,
    max_candidates: int = 900,
    refresh_data: bool = False,
) -> ThemeIntradayResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()
    universe = [item.upper() for item in (symbols or spec.universe)]

    stage_started = perf_counter()
    dataset = load_theme_intraday_dataset(
        root=base,
        spec=spec,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        market_symbol=market_symbol,
        benchmark_symbol=benchmark_symbol,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    params_grid = _build_params_grid(
        market_sma_days or [50, 100, 150],
        market_momentum_days or [20, 60],
        min_market_momentum_pct or [0.0],
        signal_momentum_days or [20, 40, 60],
        confirmation_days or [5, 20],
        top_n or [2, 3, 5],
        _beta_symbols(beta_symbol) or ["QQQ", "QLD", "TQQQ"],
        beta_weight or [0.0, 0.25, 0.4],
        satellite_weight or [0.4, 0.6, 0.75],
        max_symbol_weight or [0.1, 0.15, 0.2],
        market_below_sma_scale or [0.0, 0.25, 0.5],
        target_market_volatility_pct or [None, 30.0, 40.0],
        drawdown_lookback_days or [60, 120],
        max_market_drawdown_pct or [None, 12.0, 20.0],
        _score_modes(score_mode) or ["raw", "composite", "risk_adjusted"],
        semiconductor_gate if semiconductor_gate is not None else [True],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started

    stage_started = perf_counter()
    cache = _build_cache(dataset)
    candidates = _evaluate_candidates(
        spec=spec,
        dataset=dataset,
        cache=cache,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    walk_params = _walk_forward_params(
        candidates=candidates,
        params_grid=params_grid,
        walk_forward_top_k=walk_forward_top_k,
    )
    walk_forward = _walk_forward(
        spec=spec,
        dataset=dataset,
        cache=cache,
        params_grid=walk_params,
        folds=walk_forward_folds,
    )
    validation_windows = _validation_windows(spec, dataset, cache, candidates[0].params)
    pass_status = _pass_status(candidates[0], walk_forward)
    stages["research"] = perf_counter() - stage_started

    json_path = base / "reports" / "research" / f"{spec.name}-theme-intraday-router.json"
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
    return ThemeIntradayResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=candidates[0].params.label,
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def load_theme_intraday_dataset(
    *,
    root: Path,
    spec: StrategySpec,
    symbols: list[str],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    market_symbol: str,
    benchmark_symbol: str,
    refresh_data: bool,
) -> ThemeIntradayDataset:
    market = market_symbol.upper()
    benchmark = benchmark_symbol.upper()
    required = list(dict.fromkeys([*symbols, market, benchmark, *BETA_SYMBOLS, "SMH", "SOXX"]))
    frames = {
        symbol: _load_symbol_frame(
            root=root,
            symbol=symbol,
            timeframe=spec.timeframe,
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        )
        for symbol in required
    }
    frame: pd.DataFrame | None = None
    for symbol, symbol_frame in frames.items():
        renamed = symbol_frame[["timestamp", "open", "close"]].rename(
            columns={"open": f"{symbol}_open", "close": f"{symbol}_close"}
        )
        frame = renamed if frame is None else frame.merge(renamed, on="timestamp", how="inner")
    if frame is None:
        raise ValueError("theme intraday router produced no data frame")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if len(frame) < 260:
        raise ValueError("theme intraday router requires at least 260 common daily bars")
    dates = [
        pd.Timestamp(value).tz_convert("America/New_York").date().isoformat()
        for value in frame["timestamp"]
    ]
    candidates = [
        symbol
        for symbol in symbols
        if symbol not in {market, benchmark, *BETA_SYMBOLS, "SPY", "SQQQ", "PSQ", "QID"}
        and f"{symbol}_close" in frame
    ]
    if len(candidates) < 3:
        raise ValueError("theme intraday router requires at least three candidate symbols")
    profiles = [
        frame_data_profile(
            frames[symbol],
            symbol=symbol,
            timeframe=spec.timeframe,
            provider=data_source,
            feed=feed,
            source_mode=frames[symbol].attrs.get("data_source_mode"),
            path=frames[symbol].attrs.get("data_source_path"),
        )
        for symbol in required
    ]
    return ThemeIntradayDataset(
        frame=frame,
        dates=dates,
        symbols=required,
        market_symbol=market,
        benchmark_symbol=benchmark,
        candidate_symbols=candidates,
        data_profile=combined_data_profile(profiles),
    )


def theme_intraday_params_from_label(label: str) -> ThemeIntradayParams:
    if not label.startswith("theme_intraday:"):
        raise ValueError(f"not a theme intraday route label: {label}")
    pattern = re.compile(
        r"^theme_intraday:sma(?P<sma>\d+)_mmom(?P<mmom>\d+)_minm(?P<minm>[0-9.-]+)_"
        r"lb(?P<lb>\d+)_conf(?P<conf>\d+)_top(?P<top>\d+)_"
        r"beta(?P<beta>QQQ|QLD|TQQQ)(?P<betaw>[0-9.]+)_sat(?P<satw>[0-9.]+)_"
        r"maxw(?P<maxw>[0-9.]+)_off(?P<off>[0-9.]+)_tvol(?P<tvol>none|[0-9.]+)_"
        r"dd(?P<dd>\d+)_maxdd(?P<maxdd>none|[0-9.]+)_"
        r"score(?P<score>raw|composite|risk_adjusted)_sem(?P<sem>[01])$"
    )
    match = pattern.fullmatch(label)
    if match is None:
        raise ValueError(f"unsupported theme intraday route label: {label}")
    groups = match.groupdict()
    return ThemeIntradayParams(
        market_sma_days=int(groups["sma"]),
        market_momentum_days=int(groups["mmom"]),
        min_market_momentum_pct=float(groups["minm"]),
        signal_momentum_days=int(groups["lb"]),
        confirmation_days=int(groups["conf"]),
        top_n=int(groups["top"]),
        beta_symbol=groups["beta"],  # type: ignore[arg-type]
        beta_weight=float(groups["betaw"]),
        satellite_weight=float(groups["satw"]),
        max_symbol_weight=float(groups["maxw"]),
        market_below_sma_scale=float(groups["off"]),
        target_market_volatility_pct=_parse_optional_float(groups["tvol"]),
        drawdown_lookback_days=int(groups["dd"]),
        max_market_drawdown_pct=_parse_optional_float(groups["maxdd"]),
        score_mode=groups["score"],  # type: ignore[arg-type]
        semiconductor_gate=groups["sem"] == "1",
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
    selected_feed = feed or "iex"
    cache_path = root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{selected_feed}.csv"
    if not refresh_data and cache_path.exists():
        frame = pd.read_csv(cache_path)
        frame.attrs["data_source_mode"] = "cache"
        frame.attrs["data_source_path"] = str(cache_path)
    else:
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
    if frame.empty:
        raise ValueError(f"no daily bars available for {symbol}")
    return frame.sort_values("timestamp").reset_index(drop=True)


def _build_params_grid(
    market_sma_values: list[int],
    market_momentum_values: list[int],
    min_market_momentum_values: list[float],
    signal_momentum_values: list[int],
    confirmation_values: list[int],
    top_n_values: list[int],
    beta_symbols: list[BetaSymbol],
    beta_values: list[float],
    satellite_values: list[float],
    max_symbol_values: list[float],
    market_below_values: list[float],
    target_volatility_values: list[float | None],
    drawdown_values: list[int],
    max_drawdown_values: list[float | None],
    score_modes: list[ScoreMode],
    semiconductor_values: list[bool],
    *,
    max_candidates: int,
) -> list[ThemeIntradayParams]:
    total = math.prod(
        [
            len(market_sma_values),
            len(market_momentum_values),
            len(min_market_momentum_values),
            len(signal_momentum_values),
            len(confirmation_values),
            len(top_n_values),
            len(beta_symbols),
            len(beta_values),
            len(satellite_values),
            len(max_symbol_values),
            len(market_below_values),
            len(target_volatility_values),
            len(drawdown_values),
            len(max_drawdown_values),
            len(score_modes),
            len(semiconductor_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"theme intraday router grid would create {total} candidates; raise "
            f"--max-candidates above {total} or narrow the grid"
        )
    params: list[ThemeIntradayParams] = []
    for item in product(
        market_sma_values,
        market_momentum_values,
        min_market_momentum_values,
        signal_momentum_values,
        confirmation_values,
        top_n_values,
        beta_symbols,
        beta_values,
        satellite_values,
        max_symbol_values,
        market_below_values,
        target_volatility_values,
        drawdown_values,
        max_drawdown_values,
        score_modes,
        semiconductor_values,
    ):
        (
            market_sma,
            market_momentum,
            min_market_momentum,
            signal_momentum,
            confirmation,
            top_n,
            beta_symbol,
            beta_weight,
            satellite_weight,
            max_symbol_weight,
            market_below,
            target_volatility,
            drawdown,
            max_drawdown,
            score_mode,
            semiconductor_gate,
        ) = item
        if min(market_sma, market_momentum, signal_momentum, confirmation, top_n, drawdown) < 1:
            continue
        if min(beta_weight, satellite_weight, max_symbol_weight, market_below) < 0:
            continue
        if max(beta_weight, satellite_weight, max_symbol_weight, market_below) > 1:
            continue
        if beta_weight + satellite_weight > 1:
            continue
        if beta_weight == 0 and beta_symbol != "QQQ":
            continue
        params.append(
            ThemeIntradayParams(
                market_sma_days=market_sma,
                market_momentum_days=market_momentum,
                min_market_momentum_pct=min_market_momentum,
                signal_momentum_days=signal_momentum,
                confirmation_days=confirmation,
                top_n=top_n,
                beta_symbol=beta_symbol,
                beta_weight=beta_weight,
                satellite_weight=satellite_weight,
                max_symbol_weight=max_symbol_weight,
                market_below_sma_scale=market_below,
                target_market_volatility_pct=target_volatility,
                drawdown_lookback_days=drawdown,
                max_market_drawdown_pct=max_drawdown,
                score_mode=score_mode,
                semiconductor_gate=semiconductor_gate,
            )
        )
    if not params:
        raise ValueError("theme intraday router grid produced no valid candidates")
    return params


def _build_cache(dataset: ThemeIntradayDataset) -> dict[str, Any]:
    frame = dataset.frame
    close = pd.DataFrame(
        {symbol: frame[f"{symbol}_close"].astype(float) for symbol in dataset.symbols}
    )
    open_ = pd.DataFrame(
        {symbol: frame[f"{symbol}_open"].astype(float) for symbol in dataset.symbols}
    )
    return {
        "close": close,
        "open": open_,
        "open_to_close_return": ((close / open_) - 1.0).to_numpy(dtype=float),
        "close_np": close.to_numpy(dtype=float),
        "symbol_index": {symbol: index for index, symbol in enumerate(dataset.symbols)},
        "market_close": close[dataset.market_symbol].to_numpy(dtype=float),
        "sma": {},
        "momentum": {},
        "confirmation": {},
        "volatility": {},
        "drawdown": {},
    }


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params_grid: list[ThemeIntradayParams],
    out_of_sample_ratio: float,
) -> list[ThemeIntradayCandidate]:
    split = _split_index(len(dataset.frame), out_of_sample_ratio, params_grid)
    ytd_start = _index_for_date(dataset, "2026-01-01")
    rows: list[ThemeIntradayCandidate] = []
    for params in params_grid:
        train = _backtest_params(spec, dataset, cache, params, start_index=0, end_index=split)
        oos = _backtest_params(
            spec,
            dataset,
            cache,
            params,
            start_index=max(0, split - _effective_lookback(params) - 1),
            end_index=len(dataset.frame),
            evaluation_start_index=split,
        )
        full = _backtest_params(
            spec, dataset, cache, params, start_index=0, end_index=len(dataset.frame)
        )
        ytd = None
        if 0 <= ytd_start < len(dataset.frame) - 20:
            ytd = _backtest_params(
                spec,
                dataset,
                cache,
                params,
                start_index=max(0, ytd_start - _effective_lookback(params) - 1),
                end_index=len(dataset.frame),
                evaluation_start_index=ytd_start,
            )
        rows.append(
            ThemeIntradayCandidate(
                rank=0,
                params=params,
                score=_score_candidate(train),
                train=train,
                out_of_sample=oos,
                full_window=full,
                ytd_2026=ytd,
                quality_flags=_quality_flags(train, oos, full, ytd),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        ThemeIntradayCandidate(
            rank=index,
            params=item.params,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            ytd_2026=item.ytd_2026,
            quality_flags=item.quality_flags,
        )
        for index, item in enumerate(rows, start=1)
    ]


def _walk_forward_params(
    *,
    candidates: list[ThemeIntradayCandidate],
    params_grid: list[ThemeIntradayParams],
    walk_forward_top_k: int | None,
) -> list[ThemeIntradayParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params_grid: list[ThemeIntradayParams],
    folds: int,
) -> list[ThemeIntradayWalkForwardSlice]:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.frame) - max_lookback) // (max(folds, 1) + 1), 20)
    rows: list[ThemeIntradayWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.frame), test_start + fold_size)
        if test_end - test_start < 20:
            continue
        scored: list[tuple[float, ThemeIntradayParams]] = []
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
            ThemeIntradayWalkForwardSlice(
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
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params: ThemeIntradayParams,
    *,
    start_index: int,
    end_index: int,
    evaluation_start_index: int | None = None,
    start_equity: float = 100_000.0,
) -> ThemeIntradayMetrics:
    start_index = max(start_index, _effective_lookback(params) + 1)
    if evaluation_start_index is not None:
        start_index = max(start_index, evaluation_start_index)
    end_index = min(end_index, len(dataset.frame))
    if end_index <= start_index:
        return _empty_metrics(dataset, start_index, end_index)

    equity = start_equity
    curve = [equity]
    returns: list[float] = []
    gross_exposures: list[float] = []
    max_symbol_weights: list[float] = []
    traded_days = 0
    round_trips = 0
    cost_drag = 0.0
    market_scaled_days = 0
    volatility_scaled_days = 0
    drawdown_brake_days = 0
    semiconductor_blocked_days = 0
    positive_returns: list[float] = []
    negative_returns: list[float] = []
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000

    for index in range(start_index, end_index):
        snapshot = _target_snapshot(dataset, cache, params, index)
        weights = snapshot.weights
        if snapshot.market_scale < 0.999999:
            market_scaled_days += 1
        if snapshot.volatility_scale < 0.999999:
            volatility_scaled_days += 1
        if snapshot.drawdown_scale < 0.999999:
            drawdown_brake_days += 1
        semiconductor_blocked_days += snapshot.semiconductor_blocked_count
        gross = sum(abs(value) for value in weights.values())
        max_weight = max((abs(value) for value in weights.values()), default=0.0)
        if gross <= 0:
            period_return = 0.0
        else:
            day_returns = cache["open_to_close_return"]
            period_return = sum(
                weight * float(day_returns[index, cache["symbol_index"][symbol]])
                for symbol, weight in weights.items()
            )
            cost = gross * cost_rate * 2
            period_return -= cost
            cost_drag += cost
            traded_days += 1
            round_trips += len(weights)
        if period_return > 0:
            positive_returns.append(period_return)
        elif period_return < 0:
            negative_returns.append(period_return)
        equity *= 1 + period_return
        curve.append(equity)
        returns.append(period_return)
        gross_exposures.append(gross)
        max_symbol_weights.append(max_weight)
        if equity <= 0:
            break

    metrics = build_performance_metrics(curve, spec.timeframe)
    days = len(returns)
    qqq_buy_hold = _buy_hold_return(dataset, dataset.market_symbol, start_index, end_index)
    tqqq_buy_hold = _buy_hold_return(dataset, dataset.benchmark_symbol, start_index, end_index)
    qqq_intraday = _intraday_compounded_return(
        dataset, dataset.market_symbol, start_index, end_index
    )
    equal_weight_bh = _equal_weight_buy_hold(
        dataset, dataset.candidate_symbols, start_index, end_index
    )
    equal_weight_intraday = _equal_weight_intraday(
        dataset, cache, dataset.candidate_symbols, start_index, end_index
    )
    smh_bh = (
        _buy_hold_return(dataset, "SMH", start_index, end_index)
        if "SMH" in dataset.symbols
        else 0.0
    )
    universe_returns = {
        symbol: _buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.candidate_symbols
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = metrics.annualized_return_pct
    qqq_ann = _annualized_from_total(qqq_buy_hold, days)
    tqqq_ann = _annualized_from_total(tqqq_buy_hold, days)
    qqq_intraday_ann = _annualized_from_total(qqq_intraday, days)
    equal_weight_ann = _annualized_from_total(equal_weight_bh, days)
    equal_weight_intraday_ann = _annualized_from_total(equal_weight_intraday, days)
    smh_ann = _annualized_from_total(smh_bh, days)
    wins = [value * 100 for value in positive_returns]
    losses = [abs(value) * 100 for value in negative_returns]
    average_win = mean(wins) if wins else None
    average_loss = mean(losses) if losses else None
    profit_factor = (
        sum(positive_returns) / abs(sum(negative_returns)) if sum(negative_returns) < 0 else None
    )
    return ThemeIntradayMetrics(
        days=days,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index - 1] if end_index - 1 < len(dataset.dates) else None,
        total_return_pct=(equity / start_equity - 1) * 100,
        annualized_return_pct=annualized,
        sharpe_ratio=metrics.sharpe_ratio,
        sortino_ratio=metrics.sortino_ratio,
        calmar_ratio=metrics.calmar_ratio,
        annualized_volatility_pct=metrics.annualized_volatility_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        traded_days=traded_days,
        round_trips=round_trips,
        exposure_pct=(traded_days / days * 100) if days else 0.0,
        average_gross_exposure_pct=mean(gross_exposures) * 100 if gross_exposures else 0.0,
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        max_symbol_weight_pct=max(max_symbol_weights) * 100 if max_symbol_weights else 0.0,
        win_day_pct=(len(positive_returns) / days * 100) if days else 0.0,
        profit_factor=profit_factor,
        average_win_pct=average_win,
        average_loss_pct=average_loss,
        payoff_ratio=(average_win / average_loss) if average_win and average_loss else None,
        cost_drag_pct=cost_drag * 100,
        qqq_buy_hold_return_pct=qqq_buy_hold,
        qqq_buy_hold_annualized_pct=qqq_ann,
        alpha_vs_qqq_buy_hold_annualized_pct=_alpha(annualized, qqq_ann),
        tqqq_buy_hold_return_pct=tqqq_buy_hold,
        tqqq_buy_hold_annualized_pct=tqqq_ann,
        alpha_vs_tqqq_buy_hold_annualized_pct=_alpha(annualized, tqqq_ann),
        qqq_intraday_annualized_pct=qqq_intraday_ann,
        alpha_vs_qqq_intraday_annualized_pct=_alpha(annualized, qqq_intraday_ann),
        equal_weight_buy_hold_annualized_pct=equal_weight_ann,
        alpha_vs_equal_weight_buy_hold_annualized_pct=_alpha(annualized, equal_weight_ann),
        equal_weight_intraday_annualized_pct=equal_weight_intraday_ann,
        alpha_vs_equal_weight_intraday_annualized_pct=_alpha(
            annualized,
            equal_weight_intraday_ann,
        ),
        smh_buy_hold_annualized_pct=smh_ann,
        alpha_vs_smh_buy_hold_annualized_pct=_alpha(annualized, smh_ann),
        best_symbol=best_symbol,
        best_symbol_buy_hold_return_pct=best_return,
        alpha_vs_best_symbol_buy_hold_pct=((equity / start_equity - 1) * 100) - best_return,
        market_scaled_days=market_scaled_days,
        volatility_scaled_days=volatility_scaled_days,
        drawdown_brake_days=drawdown_brake_days,
        semiconductor_blocked_days=semiconductor_blocked_days,
    )


def _target_snapshot(
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params: ThemeIntradayParams,
    index: int,
) -> ThemeIntradaySnapshot:
    previous_index = max(0, index - 1)
    market_scale = _market_scale(cache, params, previous_index)
    volatility_scale = _volatility_scale(cache, params, previous_index)
    drawdown_scale = _drawdown_scale(cache, params, previous_index)
    effective_scale = market_scale * volatility_scale * drawdown_scale
    if effective_scale <= 0:
        return ThemeIntradaySnapshot([], {}, market_scale, volatility_scale, drawdown_scale, 0)

    weights: dict[str, float] = {}
    if params.beta_weight > 0:
        weights[params.beta_symbol] = params.beta_weight * effective_scale
    selected, blocked = _selected_satellites(dataset, cache, params, previous_index)
    if selected and params.satellite_weight > 0:
        per_symbol = min(
            params.max_symbol_weight, (params.satellite_weight * effective_scale) / len(selected)
        )
        for symbol in selected:
            weights[symbol] = weights.get(symbol, 0.0) + per_symbol
    weights = _cap_gross(weights)
    return ThemeIntradaySnapshot(
        selected=selected,
        weights=weights,
        market_scale=market_scale,
        volatility_scale=volatility_scale,
        drawdown_scale=drawdown_scale,
        semiconductor_blocked_count=blocked,
    )


def _selected_satellites(
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params: ThemeIntradayParams,
    previous_index: int,
) -> tuple[list[str], int]:
    momentum = _momentum_frame(cache, params.signal_momentum_days)
    confirmation = _confirmation_frame(cache, params.confirmation_days)
    if previous_index < 0 or previous_index >= len(momentum):
        return [], 0
    scores: list[tuple[float, str]] = []
    blocked = 0
    smh_momentum = _symbol_value(momentum, "SMH", previous_index)
    smh_confirmation = _symbol_value(confirmation, "SMH", previous_index)
    volatility = _symbol_volatility_frame(cache, 20)
    for symbol in dataset.candidate_symbols:
        value = _symbol_value(momentum, symbol, previous_index)
        confirm = _symbol_value(confirmation, symbol, previous_index)
        if not np.isfinite(value) or not np.isfinite(confirm):
            continue
        if value <= 0 or confirm <= 0:
            continue
        if params.semiconductor_gate and symbol in SEMICONDUCTOR_SYMBOLS:
            if smh_momentum <= 0 or smh_confirmation <= 0:
                blocked += 1
                continue
        score = value
        if params.score_mode == "composite":
            score = value + 0.5 * confirm
        elif params.score_mode == "risk_adjusted":
            vol = _symbol_value(volatility, symbol, previous_index)
            if not np.isfinite(vol) or vol <= 0:
                continue
            score = value / vol
        scores.append((score, symbol))
    scores.sort(reverse=True)
    return [symbol for _, symbol in scores[: params.top_n]], blocked


def _market_scale(cache: dict[str, Any], params: ThemeIntradayParams, index: int) -> float:
    market = cache["market_close"]
    if index < params.market_sma_days:
        return 0.0
    sma = _sma(cache, params.market_sma_days)
    momentum = _market_momentum(cache, params.market_momentum_days)
    if not np.isfinite(sma[index]) or not np.isfinite(momentum[index]):
        return 0.0
    trend_ok = market[index] > sma[index]
    momentum_ok = momentum[index] >= params.min_market_momentum_pct
    if trend_ok and momentum_ok:
        return 1.0
    if trend_ok:
        return params.market_below_sma_scale
    return 0.0


def _volatility_scale(cache: dict[str, Any], params: ThemeIntradayParams, index: int) -> float:
    if params.target_market_volatility_pct is None:
        return 1.0
    volatility = _market_volatility(cache, 20)
    value = volatility[index] if 0 <= index < len(volatility) else np.nan
    if not np.isfinite(value) or value <= 0:
        return 1.0
    return max(0.0, min(1.0, params.target_market_volatility_pct / float(value)))


def _drawdown_scale(cache: dict[str, Any], params: ThemeIntradayParams, index: int) -> float:
    if params.max_market_drawdown_pct is None:
        return 1.0
    drawdown = _market_drawdown(cache, params.drawdown_lookback_days)
    value = drawdown[index] if 0 <= index < len(drawdown) else np.nan
    if not np.isfinite(value):
        return 1.0
    return 0.5 if value <= -params.max_market_drawdown_pct else 1.0


def _score_candidate(metrics: ThemeIntradayMetrics) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    qqq_alpha = metrics.alpha_vs_qqq_buy_hold_annualized_pct or -100.0
    intraday_alpha = metrics.alpha_vs_equal_weight_intraday_annualized_pct or -100.0
    drawdown_penalty = abs(min(metrics.max_drawdown_pct, 0.0)) * 0.75
    high_sharpe_penalty = max(0.0, sharpe - 2.4) * 40
    sparse_penalty = max(0.0, 35.0 - metrics.exposure_pct) * 0.4
    profit_factor_bonus = min(metrics.profit_factor or 0.0, 2.5) * 5
    return (
        qqq_alpha
        + 0.5 * intraday_alpha
        + 0.25 * annualized
        + min(sharpe, 2.4) * 10
        + profit_factor_bonus
        - drawdown_penalty
        - high_sharpe_penalty
        - sparse_penalty
    )


def _quality_flags(
    train: ThemeIntradayMetrics,
    oos: ThemeIntradayMetrics,
    full: ThemeIntradayMetrics,
    ytd: ThemeIntradayMetrics | None,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq_buy_hold")
    if (oos.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq_buy_hold")
    if (full.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq_buy_hold")
    if (oos.alpha_vs_equal_weight_intraday_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_equal_weight_intraday")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.8:
        flags.append("oos_low_sharpe")
    if full.sharpe_ratio is not None and full.sharpe_ratio > 2.4:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if oos.max_drawdown_pct <= -25:
        flags.append("oos_large_drawdown")
    if full.max_drawdown_pct <= -28:
        flags.append("full_large_drawdown")
    if (full.profit_factor or 0.0) < 1.15:
        flags.append("low_profit_factor")
    if full.exposure_pct < 35:
        flags.append("too_sparse")
    if ytd and (ytd.annualized_return_pct or -100.0) <= 0:
        flags.append("ytd_2026_negative")
    return flags


def _acceptance_gate(
    candidate: ThemeIntradayCandidate,
    walk_forward: list[ThemeIntradayWalkForwardSlice],
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_qqq_buy_hold_annualized_pct for item in walk_forward]
    wf_positive = sum((value or -100.0) > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    oos_sharpe = candidate.out_of_sample.sharpe_ratio or 0.0
    full_sharpe = candidate.full_window.sharpe_ratio or 0.0
    active_beta_ann = _active_beta_full_annualized_pct()
    passed = (
        (candidate.train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.annualized_return_pct or -100.0) > active_beta_ann
        and 0.8 <= oos_sharpe <= 2.4
        and full_sharpe <= 2.4
        and candidate.out_of_sample.max_drawdown_pct > -25
        and candidate.full_window.max_drawdown_pct > -28
        and (candidate.full_window.profit_factor or 0.0) >= 1.2
        and wf_count > 0
        and wf_positive >= max(1, math.ceil(wf_count * 0.8))
        and not {"suspiciously_high_sharpe_review_overfit", "too_sparse"}.intersection(
            candidate.quality_flags
        )
    )
    return {
        "passed": passed,
        "objective": "theme_intraday_rotation_alpha_vs_qqq_and_active_beta_after_costs",
        "active_beta_full_annualized_pct": active_beta_ann,
        "train_alpha_vs_qqq_annualized_pct": candidate.train.alpha_vs_qqq_buy_hold_annualized_pct,
        "oos_alpha_vs_qqq_annualized_pct": (
            candidate.out_of_sample.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "full_alpha_vs_qqq_annualized_pct": (
            candidate.full_window.alpha_vs_qqq_buy_hold_annualized_pct
        ),
        "full_annualized_return_pct": candidate.full_window.annualized_return_pct,
        "oos_annualized_return_pct": candidate.out_of_sample.annualized_return_pct,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "full_sharpe_ratio": candidate.full_window.sharpe_ratio,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "full_max_drawdown_pct": candidate.full_window.max_drawdown_pct,
        "full_profit_factor": candidate.full_window.profit_factor,
        "full_round_trips": candidate.full_window.round_trips,
        "walk_forward_positive_alpha_folds": wf_positive,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _pass_status(
    candidate: ThemeIntradayCandidate,
    walk_forward: list[ThemeIntradayWalkForwardSlice],
) -> dict[str, Any]:
    gate = _acceptance_gate(candidate, walk_forward)
    blockers = [
        "draft/manual_signal strategy only",
        "Alpaca IEX/cache evidence is not consolidated live SIP evidence",
        "theme intraday router has no paper_auto runtime mapping yet",
        "LLM/news remains advisory; no PIT marginal-lift pass is claimed",
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


def _validation_windows(
    spec: StrategySpec,
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    params: ThemeIntradayParams,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, start, end in [
        ("calendar_2022", "2022-01-03", "2022-12-30"),
        ("calendar_2023", "2023-01-03", "2023-12-29"),
        ("calendar_2024", "2024-01-02", "2024-12-31"),
        ("calendar_2025", "2025-01-02", "2025-12-31"),
        ("ytd_2026", "2026-01-02", dataset.dates[-1]),
        ("last_24m", "2024-05-20", dataset.dates[-1]),
    ]:
        start_index = _index_for_date(dataset, start)
        end_index = _index_for_date(dataset, end, side="right")
        if end_index - start_index < 20:
            continue
        metrics = _backtest_params(
            spec,
            dataset,
            cache,
            params,
            start_index=max(0, start_index - _effective_lookback(params) - 1),
            end_index=end_index,
            evaluation_start_index=start_index,
        )
        rows.append(
            {
                "name": name,
                "requested_start": start,
                "requested_end": end,
                **metrics.__dict__,
            }
        )
    return rows


def _payload(
    *,
    spec: StrategySpec,
    spec_path: Path,
    dataset: ThemeIntradayDataset,
    params_grid: list[ThemeIntradayParams],
    candidates: list[ThemeIntradayCandidate],
    walk_forward: list[ThemeIntradayWalkForwardSlice],
    validation_windows: list[dict[str, Any]],
    pass_status: dict[str, Any],
    start: str | None,
    end: str | None,
    runtime: dict[str, Any],
    walk_forward_top_k: int | None,
) -> dict[str, Any]:
    return {
        "strategy_name": spec.name,
        "mode": "theme_intraday_rotation_router",
        "source_spec_path": _relpath(spec_path, spec_path.parents[2]),
        "symbols": dataset.symbols,
        "candidate_symbols": dataset.candidate_symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective=(
                "Daily market scan with same-session open-to-close NASDAQ theme and stock "
                "momentum rotation, benchmarked against QQQ buy-and-hold and the "
                "active beta router."
            ),
            hypothesis=(
                "When QQQ trend and momentum are supportive, concentrated but capped theme and "
                "large-cap NASDAQ momentum exposure can improve recent-cycle participation while "
                "daily flattening and volatility/drawdown brakes reduce overnight event risk."
            ),
            constraints=[
                "Signals use only previous daily close data.",
                "Entries are modeled at the next regular-session open and exited the same close.",
                "No shorts, margin, or real broker writes are used.",
                "LLM/news is advisory until PIT packet and marginal-lift evidence exists.",
            ],
        ),
        "search_space": search_space(
            family="theme_intraday_rotation_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "beta_weight + satellite_weight <= 100%",
                "single-name max weight is capped",
                "semiconductor stock route can require SMH confirmation",
                "OOS and validation windows are not used in train score",
            ],
        ),
        "references": [
            {
                "title": "Market Intraday Momentum",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752",
                "used_for": "open-to-close intraday momentum and market-state framing",
            },
            {
                "title": "Do Industries Explain Momentum?",
                "url": "https://doi.org/10.1111/0022-1082.00146",
                "used_for": "industry/theme momentum and semiconductor confirmation",
            },
            {
                "title": "Momentum Crashes",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2371227",
                "used_for": "drawdown and volatility brakes for momentum exposure",
            },
            {
                "title": "SEC EDGAR APIs",
                "url": "https://www.sec.gov/edgar/sec-api-documentation",
                "used_for": "future PIT event and filing risk filters",
            },
        ],
        "anti_leakage": [
            "Route selection uses index-1 close-derived indicators only.",
            "Backtest return is same-day open[index] to close[index] after the prior close signal.",
            "Walk-forward folds reselect parameters only from earlier data.",
            "LLM/news does not alter signals in this research pass.",
        ],
        "known_limits": [
            "Current universe is a research universe, not PIT Nasdaq-100 membership.",
            "Alpaca IEX/free cache is not consolidated SIP evidence.",
            "Daily bars cannot model sub-day stops, auction liquidity, or open gaps perfectly.",
            "Earnings/news filters are documented but not active until PIT packets exist.",
        ],
        "acceptance_standard": {
            "train_oos_full_alpha_vs_qqq_buy_hold": "> 0",
            "full_annualized_return_pct": "> current active beta router full annualized",
            "oos_sharpe_ratio": "0.8 to 2.4",
            "max_drawdown_pct": "OOS > -25 and full > -28",
            "profit_factor": ">= 1.2",
            "walk_forward": "at least 80% positive QQQ-alpha folds",
            "paper_ready_pass": "always false until runtime mapping/readiness evidence passes",
        },
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward),
        "pass_status": pass_status,
        "research_cost": {
            "candidate_count": len(params_grid),
            "walk_forward_candidate_count": len(
                _walk_forward_params(
                    candidates=candidates,
                    params_grid=params_grid,
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
        "validation_windows": validation_windows,
    }


def _write_report(path: Path, json_path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    gate = payload["acceptance_gate"]
    status = payload["pass_status"]
    top = payload["candidates"][0]
    lines = [
        f"# Theme Intraday Rotation Router Research: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Selected route: `{payload['selected_route_label']}`",
        f"- Research pass: `{status['research_pass']}`",
        f"- Paper ready pass: `{status['paper_ready_pass']}`",
        "- Signal timing: previous daily close scan; next regular-session open entry; "
        "same close exit.",
        f"- Candidate symbols: `{', '.join(payload['candidate_symbols'])}`",
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
        "## Validation Windows",
        "",
        "| Window | Dates | Ann. | Sharpe | Max DD | Alpha vs QQQ | PF | Round Trips |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in payload["validation_windows"]:
        lines.append(
            f"| `{item['name']}` | {item['start_date']} -> {item['end_date']} | "
            f"{_fmt(item.get('annualized_return_pct'))}% | "
            f"{_fmt(item.get('sharpe_ratio'))} | "
            f"{_fmt(item.get('max_drawdown_pct'))}% | "
            f"{_fmt(item.get('alpha_vs_qqq_buy_hold_annualized_pct'))}% | "
            f"{_fmt(item.get('profit_factor'))} | {item.get('round_trips')} |"
        )
    lines.extend(["", "## Walk Forward", ""])
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


def _candidate_payload(candidate: ThemeIntradayCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__ | {"label": candidate.params.label},
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
        "ytd_2026": candidate.ytd_2026.__dict__ if candidate.ytd_2026 else None,
    }


def _walk_payload(item: ThemeIntradayWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__ | {"label": item.params.label},
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _metric_lines(label: str, metrics: dict[str, Any]) -> list[str]:
    return [
        f"- {label} annualized: `{_fmt(metrics.get('annualized_return_pct'))}%`",
        f"- {label} Sharpe / Sortino: "
        f"`{_fmt(metrics.get('sharpe_ratio'))}` / `{_fmt(metrics.get('sortino_ratio'))}`",
        f"- {label} max drawdown: `{_fmt(metrics.get('max_drawdown_pct'))}%`",
        f"- {label} Alpha vs QQQ buy-hold annualized: "
        f"`{_fmt(metrics.get('alpha_vs_qqq_buy_hold_annualized_pct'))}%`",
        f"- {label} Alpha vs equal-weight intraday annualized: "
        f"`{_fmt(metrics.get('alpha_vs_equal_weight_intraday_annualized_pct'))}%`",
        f"- {label} win/PF/payoff: "
        f"`{_fmt(metrics.get('win_day_pct'))}%` / `{_fmt(metrics.get('profit_factor'))}` / "
        f"`{_fmt(metrics.get('payoff_ratio'))}`",
        f"- {label} avg win/loss: "
        f"`{_fmt(metrics.get('average_win_pct'))}%` / `{_fmt(metrics.get('average_loss_pct'))}%`",
        f"- {label} exposure/gross/round trips: "
        f"`{_fmt(metrics.get('exposure_pct'))}%` / "
        f"`{_fmt(metrics.get('average_gross_exposure_pct'))}%` / "
        f"`{metrics.get('round_trips')}`",
    ]


def _params_grid_ranges(params_grid: list[ThemeIntradayParams]) -> dict[str, list[Any]]:
    keys = [
        "market_sma_days",
        "market_momentum_days",
        "min_market_momentum_pct",
        "signal_momentum_days",
        "confirmation_days",
        "top_n",
        "beta_symbol",
        "beta_weight",
        "satellite_weight",
        "max_symbol_weight",
        "market_below_sma_scale",
        "target_market_volatility_pct",
        "drawdown_lookback_days",
        "max_market_drawdown_pct",
        "score_mode",
        "semiconductor_gate",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _sma(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["sma"]
    if lookback not in values:
        values[lookback] = (
            pd.Series(cache["market_close"]).rolling(lookback).mean().to_numpy(dtype=float)
        )
    return values[lookback]


def _market_momentum(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["momentum"]
    key = ("market", lookback)
    if key not in values:
        close = cache["market_close"]
        output = np.full(len(close), np.nan)
        output[lookback:] = (close[lookback:] / close[:-lookback] - 1) * 100
        values[key] = output
    return values[key]


def _momentum_frame(cache: dict[str, Any], lookback: int) -> pd.DataFrame:
    values = cache["momentum"]
    key = ("symbols", lookback)
    if key not in values:
        values[key] = (cache["close"] / cache["close"].shift(lookback) - 1.0) * 100
    return values[key]


def _confirmation_frame(cache: dict[str, Any], lookback: int) -> pd.DataFrame:
    values = cache["confirmation"]
    if lookback not in values:
        values[lookback] = (cache["close"] / cache["close"].shift(lookback) - 1.0) * 100
    return values[lookback]


def _market_volatility(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["volatility"]
    key = ("market", lookback)
    if key not in values:
        values[key] = (
            pd.Series(cache["market_close"])
            .pct_change()
            .rolling(lookback)
            .std()
            .to_numpy(dtype=float)
            * math.sqrt(252)
            * 100
        )
    return values[key]


def _symbol_volatility_frame(cache: dict[str, Any], lookback: int) -> pd.DataFrame:
    values = cache["volatility"]
    key = ("symbols", lookback)
    if key not in values:
        values[key] = cache["close"].pct_change().rolling(lookback).std() * math.sqrt(252) * 100
    return values[key]


def _market_drawdown(cache: dict[str, Any], lookback: int) -> np.ndarray:
    values = cache["drawdown"]
    if lookback not in values:
        close = pd.Series(cache["market_close"])
        peak = close.rolling(lookback).max()
        values[lookback] = (close / peak - 1.0).to_numpy(dtype=float) * 100
    return values[lookback]


def _symbol_value(frame: pd.DataFrame, symbol: str, index: int) -> float:
    if symbol not in frame:
        return float("nan")
    return float(frame[symbol].iloc[index])


def _cap_gross(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: value for key, value in weights.items() if value > 0}
    gross = sum(abs(value) for value in cleaned.values())
    if gross <= 1.0:
        return cleaned
    return {key: value / gross for key, value in cleaned.items()}


def _split_index(
    frame_len: int,
    out_of_sample_ratio: float,
    params_grid: list[ThemeIntradayParams],
) -> int:
    max_lookback = max(_effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - out_of_sample_ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _effective_lookback(params: ThemeIntradayParams) -> int:
    return max(
        params.market_sma_days,
        params.market_momentum_days,
        params.signal_momentum_days,
        params.confirmation_days,
        params.drawdown_lookback_days,
        20,
    )


def _buy_hold_return(
    dataset: ThemeIntradayDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if symbol not in dataset.symbols or end_index <= start_index:
        return 0.0
    frame = dataset.frame
    start = float(frame[f"{symbol}_open"].iloc[start_index])
    end = float(frame[f"{symbol}_close"].iloc[end_index - 1])
    return (end / start - 1) * 100 if start > 0 else 0.0


def _intraday_compounded_return(
    dataset: ThemeIntradayDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if symbol not in dataset.symbols or end_index <= start_index:
        return 0.0
    frame = dataset.frame
    returns = (
        frame[f"{symbol}_close"].iloc[start_index:end_index].to_numpy(dtype=float)
        / frame[f"{symbol}_open"].iloc[start_index:end_index].to_numpy(dtype=float)
        - 1
    )
    return (float(np.prod(1 + returns)) - 1) * 100


def _equal_weight_buy_hold(
    dataset: ThemeIntradayDataset,
    symbols: list[str],
    start_index: int,
    end_index: int,
) -> float:
    returns = [
        _buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in symbols
        if symbol in dataset.symbols
    ]
    return mean(returns) if returns else 0.0


def _equal_weight_intraday(
    dataset: ThemeIntradayDataset,
    cache: dict[str, Any],
    symbols: list[str],
    start_index: int,
    end_index: int,
) -> float:
    selected = [symbol for symbol in symbols if symbol in dataset.symbols]
    if not selected or end_index <= start_index:
        return 0.0
    returns = []
    for index in range(start_index, end_index):
        returns.append(
            mean(
                float(cache["open_to_close_return"][index, cache["symbol_index"][symbol]])
                for symbol in selected
            )
        )
    return (float(np.prod(1 + np.array(returns))) - 1) * 100


def _annualized_from_total(total_return_pct: float, days: int) -> float | None:
    if days <= 0 or total_return_pct <= -100:
        return None
    return ((1 + total_return_pct / 100) ** (252 / days) - 1) * 100


def _alpha(value: float | None, benchmark: float | None) -> float | None:
    if value is None or benchmark is None:
        return None
    return value - benchmark


def _empty_metrics(
    dataset: ThemeIntradayDataset,
    start_index: int,
    end_index: int,
) -> ThemeIntradayMetrics:
    return ThemeIntradayMetrics(
        days=0,
        start_date=dataset.dates[start_index] if start_index < len(dataset.dates) else None,
        end_date=dataset.dates[end_index] if end_index < len(dataset.dates) else None,
        total_return_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        sortino_ratio=None,
        calmar_ratio=None,
        annualized_volatility_pct=None,
        max_drawdown_pct=0.0,
        traded_days=0,
        round_trips=0,
        exposure_pct=0.0,
        average_gross_exposure_pct=0.0,
        max_gross_exposure_pct=0.0,
        max_symbol_weight_pct=0.0,
        win_day_pct=0.0,
        profit_factor=None,
        average_win_pct=None,
        average_loss_pct=None,
        payoff_ratio=None,
        cost_drag_pct=0.0,
        qqq_buy_hold_return_pct=0.0,
        qqq_buy_hold_annualized_pct=None,
        alpha_vs_qqq_buy_hold_annualized_pct=None,
        tqqq_buy_hold_return_pct=0.0,
        tqqq_buy_hold_annualized_pct=None,
        alpha_vs_tqqq_buy_hold_annualized_pct=None,
        qqq_intraday_annualized_pct=None,
        alpha_vs_qqq_intraday_annualized_pct=None,
        equal_weight_buy_hold_annualized_pct=None,
        alpha_vs_equal_weight_buy_hold_annualized_pct=None,
        equal_weight_intraday_annualized_pct=None,
        alpha_vs_equal_weight_intraday_annualized_pct=None,
        smh_buy_hold_annualized_pct=None,
        alpha_vs_smh_buy_hold_annualized_pct=None,
        best_symbol=None,
        best_symbol_buy_hold_return_pct=0.0,
        alpha_vs_best_symbol_buy_hold_pct=0.0,
        market_scaled_days=0,
        volatility_scaled_days=0,
        drawdown_brake_days=0,
        semiconductor_blocked_days=0,
    )


def _active_beta_full_annualized_pct() -> float:
    path = (
        project_root()
        / "reports"
        / "research"
        / "nasdaq_beta_exposure_router_daily-beta-exposure-router.json"
    )
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        return float(payload.get("acceptance_gate", {}).get("full_annualized_return_pct", 42.64))
    except (OSError, ValueError, TypeError):
        return 42.64


def _index_for_date(dataset: ThemeIntradayDataset, date: str, *, side: str = "left") -> int:
    if side == "right":
        output = 0
        for index, value in enumerate(dataset.dates):
            if value <= date:
                output = index + 1
        return min(output, len(dataset.dates))
    for index, value in enumerate(dataset.dates):
        if value >= date:
            return index
    return len(dataset.dates) - 1


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


def _beta_symbols(values: list[str] | None) -> list[BetaSymbol] | None:
    if values is None:
        return None
    allowed = set(BETA_SYMBOLS)
    symbols = [item.strip().upper() for item in values if item.strip()]
    unknown = sorted(set(symbols) - allowed)
    if unknown:
        raise ValueError(f"unsupported beta symbol(s): {', '.join(unknown)}")
    return symbols  # type: ignore[return-value]


def _score_modes(values: list[str] | None) -> list[ScoreMode] | None:
    if values is None:
        return None
    allowed = {"raw", "composite", "risk_adjusted"}
    modes = [item.strip() for item in values if item.strip()]
    unknown = sorted(set(modes) - allowed)
    if unknown:
        raise ValueError(f"unsupported score mode(s): {', '.join(unknown)}")
    return modes  # type: ignore[return-value]


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
