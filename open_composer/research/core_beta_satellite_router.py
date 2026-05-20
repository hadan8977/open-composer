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
from open_composer.research.beta_exposure_router import (
    BetaRouterDataset,
    BetaRouterParams,
    beta_params_from_label,
)
from open_composer.research.beta_exposure_router import (
    _build_indicator_cache as _build_beta_indicator_cache,
)
from open_composer.research.beta_exposure_router import (
    _effective_lookback as _beta_effective_lookback,
)
from open_composer.research.beta_exposure_router import (
    _target_snapshot as _beta_target_snapshot,
)
from open_composer.research.metadata import (
    combined_data_profile,
    frame_data_profile,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json

CoreVariant = Literal["active75", "aggressive100"]
UniverseMode = Literal["semiconductor", "wide_mega", "theme_etf"]
ScoreMode = Literal["raw", "risk_adjusted", "composite"]
ThemeGate = Literal["QQQ", "SMH", "SOXX", "XLK"]

ACTIVE_BETA_ROUTE_LABEL = (
    "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
    "levsma50_levmaxvnone_levdd60_levmaxdd20_"
    "onTQQQ0.75_neuQQQ0.75_offCASH0_vtnone"
)
AGGRESSIVE_BETA_ROUTE_LABEL = (
    "beta:sma250_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
    "levsma50_levmaxvnone_levdd60_levmaxdd20_"
    "onTQQQ1_neuQQQ0.75_offCASH0_vtnone"
)

CORE_ROUTE_LABELS: dict[str, str] = {
    "active75": ACTIVE_BETA_ROUTE_LABEL,
    "aggressive100": AGGRESSIVE_BETA_ROUTE_LABEL,
}

SEMICONDUCTOR_SYMBOLS: tuple[str, ...] = (
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
    "MPWR",
)
WIDE_MEGA_SYMBOLS: tuple[str, ...] = (
    "NVDA",
    "AVGO",
    "AMD",
    "AMAT",
    "QCOM",
    "MSFT",
    "AAPL",
    "META",
    "AMZN",
    "GOOGL",
    "GOOG",
    "TSLA",
    "NFLX",
    "COST",
    "CSCO",
    "PLTR",
    "PANW",
    "CRWD",
    "APP",
)
THEME_ETF_SYMBOLS: tuple[str, ...] = ("SMH", "SOXX", "XLK", "IGV", "ARKK")


@dataclass(frozen=True)
class CoreBetaSatelliteParams:
    core_variant: CoreVariant
    universe_mode: UniverseMode
    satellite_budget: float
    satellite_momentum_days: int
    confirmation_days: int
    top_n: int
    max_symbol_weight: float
    score_mode: ScoreMode
    theme_gate_symbol: ThemeGate
    theme_sma_days: int
    theme_momentum_days: int
    min_theme_momentum_pct: float
    satellite_volatility_lookback_days: int
    target_satellite_volatility_pct: float | None

    @property
    def core_route_label(self) -> str:
        return CORE_ROUTE_LABELS[self.core_variant]

    @property
    def label(self) -> str:
        return (
            f"core_beta_sat:core{self.core_variant}_u{self.universe_mode}_"
            f"sat{self.satellite_budget:g}_mom{self.satellite_momentum_days}_"
            f"conf{self.confirmation_days}_top{self.top_n}_maxw{self.max_symbol_weight:g}_"
            f"score{self.score_mode}_gate{self.theme_gate_symbol}_"
            f"gsma{self.theme_sma_days}_gmom{self.theme_momentum_days}_"
            f"gmin{self.min_theme_momentum_pct:g}_"
            f"vol{self.satellite_volatility_lookback_days}_"
            f"tvol{_label_optional(self.target_satellite_volatility_pct)}"
        )


@dataclass(frozen=True)
class CoreBetaSatelliteMetrics:
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
    win_day_pct: float
    profit_factor: float | None
    average_win_pct: float | None
    average_loss_pct: float | None
    payoff_ratio: float | None
    qqq_buy_hold_return_pct: float
    qqq_buy_hold_annualized_pct: float | None
    alpha_vs_qqq_buy_hold_annualized_pct: float | None
    tqqq_buy_hold_return_pct: float
    tqqq_buy_hold_annualized_pct: float | None
    alpha_vs_tqqq_buy_hold_annualized_pct: float | None
    equal_weight_buy_hold_annualized_pct: float | None
    alpha_vs_equal_weight_buy_hold_annualized_pct: float | None
    active_beta_annualized_pct: float | None
    alpha_vs_active_beta_annualized_pct: float | None
    core_only_annualized_pct: float | None
    satellite_marginal_annualized_pct: float | None
    exposure_pct: float
    average_gross_exposure_pct: float
    max_gross_exposure_pct: float
    average_core_gross_pct: float
    average_satellite_gross_pct: float
    satellite_days: int
    average_selected_count: float
    rebalance_count: int
    turnover_ratio: float
    cost_drag_pct: float


@dataclass(frozen=True)
class CoreBetaSatelliteCandidate:
    rank: int
    params: CoreBetaSatelliteParams
    score: float
    train: CoreBetaSatelliteMetrics
    out_of_sample: CoreBetaSatelliteMetrics
    full_window: CoreBetaSatelliteMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class CoreBetaSatelliteWalkForwardSlice:
    fold: int
    params: CoreBetaSatelliteParams
    train: CoreBetaSatelliteMetrics
    test: CoreBetaSatelliteMetrics


@dataclass(frozen=True)
class CoreBetaSatelliteResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


@dataclass(frozen=True)
class CoreBetaSatelliteDataset:
    frame: pd.DataFrame
    dates: list[str]
    symbols: list[str]
    market_symbol: str
    leverage_symbol: str
    hedge_symbol: str
    theme_symbols: list[str]
    data_profile: dict[str, Any]
    beta_dataset: BetaRouterDataset


@dataclass(frozen=True)
class CoreBetaSatelliteSnapshot:
    state: str
    selected: list[str]
    weights: dict[str, float]
    core_gross: float
    satellite_gross: float
    satellite_scale: float
    theme_gate_ok: bool


def run_core_beta_satellite_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    core_variant: list[str] | None = None,
    universe_mode: list[str] | None = None,
    satellite_budget: list[float] | None = None,
    satellite_momentum_days: list[int] | None = None,
    confirmation_days: list[int] | None = None,
    top_n: list[int] | None = None,
    max_symbol_weight: list[float] | None = None,
    score_mode: list[str] | None = None,
    theme_gate_symbol: list[str] | None = None,
    theme_sma_days: list[int] | None = None,
    theme_momentum_days: list[int] | None = None,
    min_theme_momentum_pct: list[float] | None = None,
    satellite_volatility_lookback_days: list[int] | None = None,
    target_satellite_volatility_pct: list[float | None] | None = None,
    walk_forward_top_k: int | None = 30,
    max_candidates: int = 700,
    refresh_data: bool = False,
) -> CoreBetaSatelliteResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    params_grid = _build_params_grid(
        _core_variants(core_variant) or ["active75", "aggressive100"],
        _universe_modes(universe_mode) or ["semiconductor", "wide_mega"],
        satellite_budget or [0.0, 0.10, 0.20],
        satellite_momentum_days or [20, 60],
        confirmation_days or [5],
        top_n or [2, 3],
        max_symbol_weight or [0.10],
        _score_modes(score_mode) or ["raw", "risk_adjusted"],
        _theme_gates(theme_gate_symbol) or ["QQQ", "SMH"],
        theme_sma_days or [50],
        theme_momentum_days or [20],
        min_theme_momentum_pct or [0.0],
        satellite_volatility_lookback_days or [20],
        target_satellite_volatility_pct or [None, 60.0],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started

    stage_started = perf_counter()
    dataset = load_core_beta_satellite_dataset(
        root=base,
        spec=spec,
        symbols=symbols,
        params_grid=params_grid,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    cache = _build_cache(dataset)
    beta_cache = _build_beta_indicator_cache(dataset.beta_dataset)
    active_params = beta_params_from_label(ACTIVE_BETA_ROUTE_LABEL)
    candidates = _evaluate_candidates(
        spec=spec,
        dataset=dataset,
        cache=cache,
        beta_cache=beta_cache,
        active_params=active_params,
        params_grid=params_grid,
    )
    selected = _select_satellite_candidate(candidates)
    walk_params = _walk_forward_params(candidates, walk_forward_top_k)
    walk_forward = _walk_forward(
        spec=spec,
        dataset=dataset,
        cache=cache,
        beta_cache=beta_cache,
        active_params=active_params,
        params_grid=walk_params,
    )
    validation = _validation_windows(
        spec=spec,
        dataset=dataset,
        cache=cache,
        beta_cache=beta_cache,
        active_params=active_params,
        params=selected.params,
    )
    pass_status = _pass_status(selected, walk_forward, validation)
    stages["research"] = perf_counter() - stage_started

    json_path = base / "reports" / "research" / f"{spec.name}-core-beta-satellite-router.json"
    report_path = json_path.with_suffix(".md")
    payload = _payload(
        spec=spec,
        spec_path=spec_path,
        dataset=dataset,
        params_grid=params_grid,
        candidates=candidates,
        selected=selected,
        walk_forward=walk_forward,
        validation=validation,
        pass_status=pass_status,
        start=start,
        end=end,
        runtime=runtime_payload(started_at, stages),
        walk_forward_top_k=walk_forward_top_k,
    )
    write_json(json_path, payload)
    _write_report(report_path, json_path, payload)
    return CoreBetaSatelliteResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=selected.params.label,
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def load_core_beta_satellite_dataset(
    *,
    root: Path,
    spec: StrategySpec,
    symbols: list[str] | None,
    params_grid: list[CoreBetaSatelliteParams],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> CoreBetaSatelliteDataset:
    if symbols:
        candidate_symbols = [item.upper() for item in symbols]
    else:
        candidate_symbols = _candidate_symbols_for_modes(
            sorted({params.universe_mode for params in params_grid})
        )
    theme_symbols = sorted(
        {params.theme_gate_symbol for params in params_grid if params.theme_gate_symbol != "QQQ"}
    )
    required = list(
        dict.fromkeys(
            [
                "QQQ",
                "TQQQ",
                "SQQQ",
                *theme_symbols,
                *candidate_symbols,
            ]
        )
    )
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
    for symbol in required:
        piece = frames[symbol][["timestamp", "open", "close"]].rename(
            columns={"open": f"{symbol}_open", "close": f"{symbol}_close"}
        )
        frame = piece if frame is None else frame.merge(piece, on="timestamp", how="inner")
    if frame is None:
        raise ValueError("core beta satellite dataset has no symbols")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if len(frame) < 520:
        raise ValueError("core beta satellite router requires at least 520 common daily bars")
    dates = [
        pd.Timestamp(value).tz_convert("America/New_York").date().isoformat()
        for value in frame["timestamp"]
    ]
    profiles = [
        frame_data_profile(
            frames[symbol],
            symbol=symbol,
            timeframe=spec.timeframe,
            provider=data_source,
            feed=feed,
            source_mode=frames[symbol].attrs.get("data_source_mode")
            or ("live_fetch" if refresh_data else "cache"),
            path=frames[symbol].attrs.get("data_source_path"),
        )
        for symbol in required
    ]
    beta_frame = frame[
        [
            "timestamp",
            "QQQ_open",
            "QQQ_close",
            "TQQQ_open",
            "TQQQ_close",
            "SQQQ_open",
            "SQQQ_close",
        ]
    ].copy()
    beta_dataset = BetaRouterDataset(
        frame=beta_frame,
        dates=dates,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
        data_profile=combined_data_profile(profiles[:3]),
    )
    return CoreBetaSatelliteDataset(
        frame=frame,
        dates=dates,
        symbols=candidate_symbols,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
        theme_symbols=theme_symbols,
        data_profile=combined_data_profile(profiles),
        beta_dataset=beta_dataset,
    )


def core_beta_satellite_params_from_label(label: str) -> CoreBetaSatelliteParams:
    if not label.startswith("core_beta_sat:"):
        raise ValueError(f"not a core beta satellite route label: {label}")
    raw: dict[str, str] = {}
    for part in label.removeprefix("core_beta_sat:").split("_"):
        for prefix in [
            "core",
            "u",
            "sat",
            "mom",
            "conf",
            "top",
            "maxw",
            "score",
            "gate",
            "gsma",
            "gmom",
            "gmin",
            "vol",
            "tvol",
        ]:
            if part.startswith(prefix):
                raw[prefix] = part.removeprefix(prefix)
                break
    return CoreBetaSatelliteParams(
        core_variant=_core_variant(raw["core"]),
        universe_mode=_universe_mode(raw["u"]),
        satellite_budget=float(raw["sat"]),
        satellite_momentum_days=int(raw["mom"]),
        confirmation_days=int(raw["conf"]),
        top_n=int(raw["top"]),
        max_symbol_weight=float(raw["maxw"]),
        score_mode=_score_mode(raw["score"]),
        theme_gate_symbol=_theme_gate(raw["gate"]),
        theme_sma_days=int(raw["gsma"]),
        theme_momentum_days=int(raw["gmom"]),
        min_theme_momentum_pct=float(raw["gmin"]),
        satellite_volatility_lookback_days=int(raw["vol"]),
        target_satellite_volatility_pct=_parse_optional_float(raw["tvol"]),
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
        start=_utc_timestamp(start) if start else None,
        end=_utc_timestamp(end) if end else None,
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


def _build_params_grid(
    core_variants: list[CoreVariant],
    universe_modes: list[UniverseMode],
    satellite_budgets: list[float],
    momentum_values: list[int],
    confirmation_values: list[int],
    top_n_values: list[int],
    max_symbol_weight_values: list[float],
    score_modes: list[ScoreMode],
    theme_gates: list[ThemeGate],
    theme_sma_values: list[int],
    theme_momentum_values: list[int],
    min_theme_momentum_values: list[float],
    volatility_lookback_values: list[int],
    target_volatility_values: list[float | None],
    *,
    max_candidates: int,
) -> list[CoreBetaSatelliteParams]:
    total = math.prod(
        [
            len(core_variants),
            len(universe_modes),
            len(satellite_budgets),
            len(momentum_values),
            len(confirmation_values),
            len(top_n_values),
            len(max_symbol_weight_values),
            len(score_modes),
            len(theme_gates),
            len(theme_sma_values),
            len(theme_momentum_values),
            len(min_theme_momentum_values),
            len(volatility_lookback_values),
            len(target_volatility_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"core beta satellite grid would create {total} candidates; raise "
            f"--max-candidates above {total} or narrow the grid"
        )
    params: list[CoreBetaSatelliteParams] = []
    seen: set[tuple[Any, ...]] = set()
    for item in product(
        core_variants,
        universe_modes,
        satellite_budgets,
        momentum_values,
        confirmation_values,
        top_n_values,
        max_symbol_weight_values,
        score_modes,
        theme_gates,
        theme_sma_values,
        theme_momentum_values,
        min_theme_momentum_values,
        volatility_lookback_values,
        target_volatility_values,
    ):
        (
            core,
            universe,
            satellite_budget,
            momentum,
            confirmation,
            top_n,
            max_weight,
            score,
            gate,
            gate_sma,
            gate_momentum,
            gate_min_momentum,
            volatility,
            target_volatility,
        ) = item
        if min(momentum, confirmation, top_n, gate_sma, gate_momentum, volatility) < 1:
            continue
        if satellite_budget < 0 or satellite_budget > 0.5:
            continue
        if max_weight <= 0 or max_weight > 0.25:
            continue
        if satellite_budget == 0:
            key = (core, universe, 0.0)
        else:
            key = item
        if key in seen:
            continue
        seen.add(key)
        params.append(
            CoreBetaSatelliteParams(
                core_variant=core,
                universe_mode=universe,
                satellite_budget=satellite_budget,
                satellite_momentum_days=momentum,
                confirmation_days=confirmation,
                top_n=top_n,
                max_symbol_weight=max_weight,
                score_mode=score,
                theme_gate_symbol=gate,
                theme_sma_days=gate_sma,
                theme_momentum_days=gate_momentum,
                min_theme_momentum_pct=gate_min_momentum,
                satellite_volatility_lookback_days=volatility,
                target_satellite_volatility_pct=target_volatility,
            )
        )
    if not params:
        raise ValueError("core beta satellite grid produced no valid candidates")
    return params


def _build_cache(dataset: CoreBetaSatelliteDataset) -> dict[str, Any]:
    frame = dataset.frame
    symbols = dataset.symbols
    close = pd.DataFrame({symbol: frame[f"{symbol}_close"].astype(float) for symbol in symbols})
    open_ = pd.DataFrame({symbol: frame[f"{symbol}_open"].astype(float) for symbol in symbols})
    all_symbols = list(
        dict.fromkeys(["QQQ", "TQQQ", "SQQQ", *dataset.theme_symbols, *dataset.symbols])
    )
    open_returns = {
        symbol: _next_open_returns(frame[f"{symbol}_open"].to_numpy(dtype=float))
        for symbol in all_symbols
    }
    return {
        "close": close,
        "close_np": close.to_numpy(dtype=float),
        "open": open_,
        "open_return": open_returns,
        "symbol_index": {symbol: index for index, symbol in enumerate(symbols)},
        "momentum": {},
        "confirmation": {},
        "symbol_volatility": {},
        "theme_sma": {},
        "theme_momentum": {},
    }


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    active_params: BetaRouterParams,
    params_grid: list[CoreBetaSatelliteParams],
) -> list[CoreBetaSatelliteCandidate]:
    train_start = _index_for_date(dataset, "2022-01-03")
    train_end = _index_for_date(dataset, "2024-12-31", side="right")
    oos_start = _index_for_date(dataset, "2025-01-01")
    oos_end = _index_for_date(dataset, "2025-12-31", side="right")
    full_start = train_start
    full_end = _index_for_date(dataset, "2026-05-18", side="right")
    rows: list[CoreBetaSatelliteCandidate] = []
    for params in params_grid:
        lookback = _effective_lookback(params)
        train = _backtest_params(
            spec,
            dataset,
            cache,
            beta_cache,
            active_params,
            params,
            start_index=max(train_start, lookback),
            end_index=train_end,
        )
        train_windows = [
            _backtest_params(
                spec,
                dataset,
                cache,
                beta_cache,
                active_params,
                params,
                start_index=max(_index_for_date(dataset, start), lookback),
                end_index=_index_for_date(dataset, end, side="right"),
            )
            for start, end in [
                ("2022-01-03", "2022-12-30"),
                ("2023-01-03", "2023-12-29"),
                ("2024-01-02", "2024-12-31"),
            ]
        ]
        oos = _backtest_params(
            spec,
            dataset,
            cache,
            beta_cache,
            active_params,
            params,
            start_index=max(oos_start, lookback),
            end_index=oos_end,
        )
        full = _backtest_params(
            spec,
            dataset,
            cache,
            beta_cache,
            active_params,
            params,
            start_index=max(full_start, lookback),
            end_index=full_end,
        )
        rows.append(
            CoreBetaSatelliteCandidate(
                rank=0,
                params=params,
                score=_score_candidate(train, train_windows),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=_quality_flags(train, oos, full),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        CoreBetaSatelliteCandidate(
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


def _select_satellite_candidate(
    candidates: list[CoreBetaSatelliteCandidate],
) -> CoreBetaSatelliteCandidate:
    satellite_candidates = [
        item
        for item in candidates
        if item.params.satellite_budget > 0
        and (item.full_window.satellite_marginal_annualized_pct or -100.0) > 0
        and (item.out_of_sample.satellite_marginal_annualized_pct or -100.0) > -3
        and "satellite_no_full_marginal_lift" not in item.quality_flags
    ]
    return satellite_candidates[0] if satellite_candidates else candidates[0]


def _walk_forward_params(
    candidates: list[CoreBetaSatelliteCandidate],
    top_k: int | None,
) -> list[CoreBetaSatelliteParams]:
    if top_k is None:
        return [item.params for item in candidates]
    if top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(top_k, len(candidates))]]


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    active_params: BetaRouterParams,
    params_grid: list[CoreBetaSatelliteParams],
) -> list[CoreBetaSatelliteWalkForwardSlice]:
    rows: list[CoreBetaSatelliteWalkForwardSlice] = []
    for fold, train_start, train_end, test_start, test_end in _walk_forward_boundaries():
        scored: list[tuple[float, CoreBetaSatelliteParams, CoreBetaSatelliteMetrics]] = []
        for params in params_grid:
            lookback = _effective_lookback(params)
            train = _backtest_params(
                spec,
                dataset,
                cache,
                beta_cache,
                active_params,
                params,
                start_index=max(_index_for_date(dataset, train_start), lookback),
                end_index=_index_for_date(dataset, train_end, side="right"),
            )
            scored.append((_score_candidate(train, [train]), params, train))
        scored.sort(key=lambda item: item[0], reverse=True)
        _, selected, train = scored[0]
        test = _backtest_params(
            spec,
            dataset,
            cache,
            beta_cache,
            active_params,
            selected,
            start_index=max(_index_for_date(dataset, test_start), _effective_lookback(selected)),
            end_index=_index_for_date(dataset, test_end, side="right"),
        )
        rows.append(
            CoreBetaSatelliteWalkForwardSlice(
                fold=fold,
                params=selected,
                train=train,
                test=test,
            )
        )
    return rows


def _validation_windows(
    *,
    spec: StrategySpec,
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    active_params: BetaRouterParams,
    params: CoreBetaSatelliteParams,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, start, end in _validation_boundaries(dataset):
        metrics = _backtest_params(
            spec,
            dataset,
            cache,
            beta_cache,
            active_params,
            params,
            start_index=max(_index_for_date(dataset, start), _effective_lookback(params)),
            end_index=_index_for_date(dataset, end, side="right"),
        )
        rows.append(
            {"name": name, "requested_start": start, "requested_end": end} | metrics.__dict__
        )
    return rows


def _backtest_params(
    spec: StrategySpec,
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    active_params: BetaRouterParams,
    params: CoreBetaSatelliteParams,
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> CoreBetaSatelliteMetrics:
    start_index = max(start_index, _effective_lookback(params))
    end_index = min(end_index, len(dataset.frame) - 1)
    if end_index <= start_index:
        return _empty_metrics(dataset, start_index, end_index)
    core_params = beta_params_from_label(params.core_route_label)
    equity = start_equity
    core_equity = start_equity
    curve = [equity]
    core_curve = [core_equity]
    returns: list[float] = []
    selected_counts: list[int] = []
    gross_exposures: list[float] = []
    core_gross_values: list[float] = []
    satellite_gross_values: list[float] = []
    previous_weights = {symbol: 0.0 for symbol in _all_trade_symbols(dataset)}
    rebalance_count = 0
    turnover_ratio = 0.0
    cost_drag = 0.0
    satellite_days = 0
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    for index in range(start_index, end_index):
        snapshot = _target_snapshot(dataset, cache, beta_cache, core_params, params, index)
        weights = {symbol: snapshot.weights.get(symbol, 0.0) for symbol in previous_weights}
        turnover = sum(
            abs(weights[symbol] - previous_weights.get(symbol, 0.0)) for symbol in weights
        )
        if turnover > 1e-12:
            rebalance_count += 1
        turnover_ratio += turnover
        cost = turnover * cost_rate
        period_return = (
            sum(weights[symbol] * float(cache["open_return"][symbol][index]) for symbol in weights)
            - cost
        )
        core_weights = _core_weights(dataset, beta_cache, core_params, index)
        core_return = sum(
            core_weights[symbol] * float(cache["open_return"][symbol][index])
            for symbol in core_weights
        )
        equity *= 1 + period_return
        core_equity *= 1 + core_return
        curve.append(equity)
        core_curve.append(core_equity)
        returns.append(period_return)
        gross = sum(abs(value) for value in weights.values())
        gross_exposures.append(gross)
        core_gross_values.append(snapshot.core_gross)
        satellite_gross_values.append(snapshot.satellite_gross)
        selected_counts.append(len(snapshot.selected))
        if snapshot.satellite_gross > 1e-12:
            satellite_days += 1
        previous_weights = weights
        cost_drag += cost
        if equity <= 0:
            break
    metrics = build_performance_metrics(curve, spec.timeframe)
    core_metrics = build_performance_metrics(core_curve, spec.timeframe)
    days = len(returns)
    qqq_buy_hold = _buy_hold_return(dataset, "QQQ", start_index, end_index)
    tqqq_buy_hold = _buy_hold_return(dataset, "TQQQ", start_index, end_index)
    equal_weight_buy_hold = _equal_weight_buy_hold(dataset, params, start_index, end_index)
    active_beta_ann = _active_beta_annualized(
        spec,
        dataset,
        cache,
        beta_cache,
        active_params,
        start_index,
        end_index,
    )
    annualized = metrics.annualized_return_pct
    core_annualized = core_metrics.annualized_return_pct
    return CoreBetaSatelliteMetrics(
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
        win_day_pct=_win_pct(returns),
        profit_factor=_profit_factor(returns),
        average_win_pct=_average_win_pct(returns),
        average_loss_pct=_average_loss_pct(returns),
        payoff_ratio=_payoff_ratio(returns),
        qqq_buy_hold_return_pct=qqq_buy_hold,
        qqq_buy_hold_annualized_pct=_annualized_from_total(qqq_buy_hold, days),
        alpha_vs_qqq_buy_hold_annualized_pct=_alpha(
            annualized,
            _annualized_from_total(qqq_buy_hold, days),
        ),
        tqqq_buy_hold_return_pct=tqqq_buy_hold,
        tqqq_buy_hold_annualized_pct=_annualized_from_total(tqqq_buy_hold, days),
        alpha_vs_tqqq_buy_hold_annualized_pct=_alpha(
            annualized,
            _annualized_from_total(tqqq_buy_hold, days),
        ),
        equal_weight_buy_hold_annualized_pct=_annualized_from_total(equal_weight_buy_hold, days),
        alpha_vs_equal_weight_buy_hold_annualized_pct=_alpha(
            annualized,
            _annualized_from_total(equal_weight_buy_hold, days),
        ),
        active_beta_annualized_pct=active_beta_ann,
        alpha_vs_active_beta_annualized_pct=_alpha(annualized, active_beta_ann),
        core_only_annualized_pct=core_annualized,
        satellite_marginal_annualized_pct=_alpha(annualized, core_annualized),
        exposure_pct=sum(1 for value in gross_exposures if value > 0) / days * 100 if days else 0.0,
        average_gross_exposure_pct=mean(gross_exposures) * 100 if gross_exposures else 0.0,
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        average_core_gross_pct=mean(core_gross_values) * 100 if core_gross_values else 0.0,
        average_satellite_gross_pct=mean(satellite_gross_values) * 100
        if satellite_gross_values
        else 0.0,
        satellite_days=satellite_days,
        average_selected_count=mean(selected_counts) if selected_counts else 0.0,
        rebalance_count=rebalance_count,
        turnover_ratio=turnover_ratio,
        cost_drag_pct=cost_drag * 100,
    )


def core_beta_satellite_target_weight_snapshot(
    dataset: CoreBetaSatelliteDataset,
    params: CoreBetaSatelliteParams,
    index: int,
) -> CoreBetaSatelliteSnapshot:
    cache = _build_cache(dataset)
    beta_cache = _build_beta_indicator_cache(dataset.beta_dataset)
    core_params = beta_params_from_label(params.core_route_label)
    return _target_snapshot(dataset, cache, beta_cache, core_params, params, index)


def _target_snapshot(
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    core_params: BetaRouterParams,
    params: CoreBetaSatelliteParams,
    index: int,
) -> CoreBetaSatelliteSnapshot:
    core_snapshot = _beta_target_snapshot(dataset.beta_dataset, beta_cache, core_params, index)
    weights = dict(core_snapshot.weights)
    core_gross = sum(abs(value) for value in weights.values())
    if params.satellite_budget <= 0 or core_snapshot.state != "risk_on":
        return CoreBetaSatelliteSnapshot(
            state=f"{core_snapshot.state}_core_only",
            selected=[],
            weights=weights,
            core_gross=core_gross,
            satellite_gross=0.0,
            satellite_scale=0.0,
            theme_gate_ok=False,
        )
    gate_ok = _theme_gate_ok(dataset, cache, params, index)
    selected = _selected_symbols(dataset, cache, params, index) if gate_ok else []
    if not selected:
        return CoreBetaSatelliteSnapshot(
            state=f"{core_snapshot.state}_no_satellite",
            selected=[],
            weights=weights,
            core_gross=core_gross,
            satellite_gross=0.0,
            satellite_scale=0.0,
            theme_gate_ok=gate_ok,
        )
    satellite_scale = _satellite_volatility_scale(dataset, cache, params, selected, index)
    satellite_budget = min(params.satellite_budget * satellite_scale, max(0.0, 1.0 - core_gross))
    if satellite_budget <= 0:
        return CoreBetaSatelliteSnapshot(
            state=f"{core_snapshot.state}_satellite_blocked",
            selected=[],
            weights=weights,
            core_gross=core_gross,
            satellite_gross=0.0,
            satellite_scale=satellite_scale,
            theme_gate_ok=gate_ok,
        )
    per_symbol = min(params.max_symbol_weight, satellite_budget / len(selected))
    satellite_gross = per_symbol * len(selected)
    for symbol in selected:
        weights[symbol] = weights.get(symbol, 0.0) + per_symbol
    weights = _cap_gross(weights)
    satellite_gross = sum(weights.get(symbol, 0.0) for symbol in selected)
    return CoreBetaSatelliteSnapshot(
        state=f"{core_snapshot.state}_with_satellite",
        selected=selected,
        weights=weights,
        core_gross=core_gross,
        satellite_gross=satellite_gross,
        satellite_scale=satellite_scale,
        theme_gate_ok=gate_ok,
    )


def _core_weights(
    dataset: CoreBetaSatelliteDataset,
    beta_cache: dict[str, Any],
    core_params: BetaRouterParams,
    index: int,
) -> dict[str, float]:
    snapshot = _beta_target_snapshot(dataset.beta_dataset, beta_cache, core_params, index)
    return {symbol: value for symbol, value in snapshot.weights.items() if value > 0}


def _selected_symbols(
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    params: CoreBetaSatelliteParams,
    index: int,
) -> list[str]:
    universe = _symbols_for_mode(dataset, params.universe_mode)
    if not universe:
        return []
    indices = [
        cache["symbol_index"][symbol] for symbol in universe if symbol in cache["symbol_index"]
    ]
    if not indices:
        return []
    momentum = _momentum_array(cache, params.satellite_momentum_days)
    confirmation = _momentum_array(cache, params.confirmation_days)
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    scores = momentum[previous_index, indices].astype(float).copy()
    confirm = confirmation[previous_index, indices].astype(float)
    scores[~np.isfinite(scores)] = -np.inf
    scores[~np.isfinite(confirm)] = -np.inf
    scores[confirm <= 0] = -np.inf
    if params.score_mode in {"risk_adjusted", "composite"}:
        vol = _symbol_volatility_array(cache, params.satellite_volatility_lookback_days)
        denom = vol[previous_index, indices]
        with np.errstate(divide="ignore", invalid="ignore"):
            risk_adjusted = scores / denom
        risk_adjusted[~np.isfinite(risk_adjusted)] = -np.inf
        if params.score_mode == "risk_adjusted":
            scores = risk_adjusted
        else:
            scores = scores + risk_adjusted * 10
    finite = np.isfinite(scores)
    if not finite.any():
        return []
    count = min(params.top_n, int(finite.sum()))
    selected_local = np.argpartition(scores, -count)[-count:]
    selected_local = selected_local[np.argsort(scores[selected_local])[::-1]]
    return [universe[int(item)] for item in selected_local if np.isfinite(scores[int(item)])]


def _theme_gate_ok(
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    params: CoreBetaSatelliteParams,
    index: int,
) -> bool:
    symbol = params.theme_gate_symbol
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    close = dataset.frame[f"{symbol}_close"].to_numpy(dtype=float)
    sma_key = (symbol, params.theme_sma_days)
    if sma_key not in cache["theme_sma"]:
        cache["theme_sma"][sma_key] = (
            pd.Series(close).rolling(params.theme_sma_days).mean().to_numpy(dtype=float)
        )
    momentum_key = (symbol, params.theme_momentum_days)
    if momentum_key not in cache["theme_momentum"]:
        values = np.full(len(close), np.nan)
        lookback = params.theme_momentum_days
        values[lookback:] = (close[lookback:] / close[:-lookback] - 1) * 100
        cache["theme_momentum"][momentum_key] = values
    sma = cache["theme_sma"][sma_key][previous_index]
    momentum = cache["theme_momentum"][momentum_key][previous_index]
    latest = close[previous_index]
    return bool(
        np.isfinite(sma)
        and np.isfinite(momentum)
        and latest > float(sma)
        and float(momentum) >= params.min_theme_momentum_pct
    )


def _satellite_volatility_scale(
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    params: CoreBetaSatelliteParams,
    selected: list[str],
    index: int,
) -> float:
    if params.target_satellite_volatility_pct is None or not selected:
        return 1.0
    vol = _symbol_volatility_array(cache, params.satellite_volatility_lookback_days)
    previous_index = max(0, min(index - 1, len(dataset.frame) - 1))
    indices = [cache["symbol_index"][symbol] for symbol in selected]
    values = [
        float(vol[previous_index, idx]) for idx in indices if np.isfinite(vol[previous_index, idx])
    ]
    if not values:
        return 1.0
    current = mean(values)
    if current <= 0:
        return 1.0
    return max(0.0, min(1.0, params.target_satellite_volatility_pct / current))


def _active_beta_annualized(
    spec: StrategySpec,
    dataset: CoreBetaSatelliteDataset,
    cache: dict[str, Any],
    beta_cache: dict[str, Any],
    active_params: BetaRouterParams,
    start_index: int,
    end_index: int,
) -> float | None:
    equity = 100_000.0
    curve = [equity]
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    previous_weights = {"QQQ": 0.0, "TQQQ": 0.0, "SQQQ": 0.0}
    for index in range(start_index, end_index):
        weights = _core_weights(dataset, beta_cache, active_params, index)
        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in previous_weights
        )
        period_return = (
            sum(
                weights.get(symbol, 0.0) * float(cache["open_return"][symbol][index])
                for symbol in previous_weights
            )
            - turnover * cost_rate
        )
        equity *= 1 + period_return
        curve.append(equity)
        previous_weights = {symbol: weights.get(symbol, 0.0) for symbol in previous_weights}
        if equity <= 0:
            break
    return build_performance_metrics(curve, spec.timeframe).annualized_return_pct


def _score_candidate(
    metrics: CoreBetaSatelliteMetrics,
    train_windows: list[CoreBetaSatelliteMetrics] | None = None,
) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    qqq_alpha = metrics.alpha_vs_qqq_buy_hold_annualized_pct or -100.0
    active_alpha = metrics.alpha_vs_active_beta_annualized_pct or -100.0
    satellite_lift = metrics.satellite_marginal_annualized_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    drawdown = abs(min(metrics.max_drawdown_pct, 0.0))
    score = (
        annualized * 0.25
        + qqq_alpha * 0.7
        + active_alpha * 0.8
        + satellite_lift * 0.6
        + min(sharpe, 2.4) * 8
        - drawdown * 0.55
        - max(0, metrics.rebalance_count - 90) * 0.08
        - max(0.0, sharpe - 2.4) * 35
    )
    if metrics.satellite_days == 0:
        score -= 25
    if train_windows:
        negative_windows = sum(
            (item.annualized_return_pct or -100.0) <= 0 for item in train_windows
        )
        active_miss = sum(
            (item.alpha_vs_active_beta_annualized_pct or -100.0) <= -5 for item in train_windows
        )
        poor_lift = sum(
            (item.satellite_marginal_annualized_pct or -100.0) <= -5 for item in train_windows
        )
        score -= negative_windows * 45
        score -= active_miss * 18
        score -= poor_lift * 12
    return score


def _quality_flags(
    train: CoreBetaSatelliteMetrics,
    oos: CoreBetaSatelliteMetrics,
    full: CoreBetaSatelliteMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq")
    if (oos.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq")
    if (full.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq")
    if (train.alpha_vs_active_beta_annualized_pct or -100.0) <= -5:
        flags.append("train_lags_active_beta")
    if (oos.alpha_vs_active_beta_annualized_pct or -100.0) <= -5:
        flags.append("oos_lags_active_beta")
    if (full.alpha_vs_active_beta_annualized_pct or -100.0) <= -3:
        flags.append("full_lags_active_beta")
    if (full.satellite_marginal_annualized_pct or -100.0) <= 0:
        flags.append("satellite_no_full_marginal_lift")
    if (oos.satellite_marginal_annualized_pct or -100.0) <= -5:
        flags.append("satellite_hurts_oos")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        flags.append("oos_low_sharpe")
    if (train.sharpe_ratio or 0.0) > 2.5 or (oos.sharpe_ratio or 0.0) > 2.5:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if full.max_drawdown_pct <= -32:
        flags.append("full_large_drawdown")
    if full.max_gross_exposure_pct > 100:
        flags.append("gross_exposure_above_100")
    if full.satellite_days < 20 and full.days >= 250:
        flags.append("satellite_too_sparse")
    return flags


def _acceptance_gate(
    selected: CoreBetaSatelliteCandidate,
    walk_forward: list[CoreBetaSatelliteWalkForwardSlice],
    validation: list[dict[str, Any]],
) -> dict[str, Any]:
    train = selected.train
    oos = selected.out_of_sample
    full = selected.full_window
    wf_positive_active = sum(
        (item.test.alpha_vs_active_beta_annualized_pct or -100.0) > -3 for item in walk_forward
    )
    wf_positive_lift = sum(
        (item.test.satellite_marginal_annualized_pct or -100.0) > -3 for item in walk_forward
    )
    by_name = {row["name"]: row for row in validation}
    ytd = by_name.get("ytd_2026", {})
    last_24m = by_name.get("last_24m", {})
    conditions = {
        "train_alpha_vs_qqq_positive": (train.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0,
        "oos_alpha_vs_qqq_positive": (oos.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0,
        "full_alpha_vs_qqq_positive": (full.alpha_vs_qqq_buy_hold_annualized_pct or -100.0) > 0,
        "full_annualized_at_least_active_beta_minus_3": (
            full.alpha_vs_active_beta_annualized_pct or -100.0
        )
        >= -3.0,
        "full_satellite_marginal_lift_positive": (full.satellite_marginal_annualized_pct or -100.0)
        > 0,
        "oos_satellite_not_harmful": (oos.satellite_marginal_annualized_pct or -100.0) >= -3,
        "oos_sharpe_band": 0.7 <= (oos.sharpe_ratio or -100.0) <= 2.5,
        "full_drawdown_controlled": full.max_drawdown_pct > -32,
        "max_gross_ok": full.max_gross_exposure_pct <= 100,
        "satellite_used": full.satellite_days >= 20,
        "walk_forward_mostly_not_worse_than_active": wf_positive_active
        >= max(1, math.ceil(len(walk_forward) * 0.6)),
        "walk_forward_mostly_nonharmful_lift": wf_positive_lift
        >= max(1, math.ceil(len(walk_forward) * 0.6)),
        "last_24m_not_worse_than_active_by_5": (
            last_24m.get("alpha_vs_active_beta_annualized_pct") or -100.0
        )
        >= -5,
        "ytd_2026_not_sole_driver": (ytd.get("satellite_marginal_annualized_pct") or 0.0) < 150,
    }
    return {
        "passed": all(conditions.values())
        and not {
            "suspiciously_high_sharpe_review_overfit",
            "gross_exposure_above_100",
        }.intersection(selected.quality_flags),
        "objective": "core_beta_plus_bounded_satellite_marginal_lift",
        "conditions": conditions,
        "selected_route": selected.params.label,
        "walk_forward_active_nonharmful_folds": wf_positive_active,
        "walk_forward_lift_nonharmful_folds": wf_positive_lift,
        "walk_forward_fold_count": len(walk_forward),
        "quality_flags": selected.quality_flags,
    }


def _pass_status(
    selected: CoreBetaSatelliteCandidate,
    walk_forward: list[CoreBetaSatelliteWalkForwardSlice],
    validation: list[dict[str, Any]],
) -> dict[str, Any]:
    gate = _acceptance_gate(selected, walk_forward, validation)
    blockers = [
        "draft/manual_signal strategy only",
        "current-constituent candidate universe is not point-in-time membership",
        "Alpaca IEX/cache evidence is not consolidated live SIP evidence",
        "target-weight paper runtime mapping not implemented for core beta satellite router",
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
    dataset: CoreBetaSatelliteDataset,
    params_grid: list[CoreBetaSatelliteParams],
    candidates: list[CoreBetaSatelliteCandidate],
    selected: CoreBetaSatelliteCandidate,
    walk_forward: list[CoreBetaSatelliteWalkForwardSlice],
    validation: list[dict[str, Any]],
    pass_status: dict[str, Any],
    start: str | None,
    end: str | None,
    runtime: dict[str, Any],
    walk_forward_top_k: int | None,
) -> dict[str, Any]:
    return {
        "strategy_name": spec.name,
        "mode": "core_beta_satellite_router",
        "source_spec_path": _relpath(spec_path, spec_path.parents[2]),
        "market_symbol": dataset.market_symbol,
        "leverage_symbol": dataset.leverage_symbol,
        "hedge_symbol": dataset.hedge_symbol,
        "candidate_symbols": dataset.symbols,
        "theme_symbols": dataset.theme_symbols,
        "research_window": {"start": start, "end": end},
        "selection_policy": "train_2022_2024_only; 2025, 2026, and rolling windows are validation",
        "data_profile": dataset.data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective=(
                "Keep the validated QQQ/TQQQ beta route as core while testing whether a "
                "bounded NASDAQ/semiconductor satellite adds PIT-compatible marginal lift."
            ),
            hypothesis=(
                "Time-series momentum selects the core beta regime; industry/stock momentum "
                "can add a small satellite only when it is confirmed by QQQ or theme trend and "
                "does not degrade the core route materially."
            ),
            constraints=[
                "All satellite signals use prior confirmed daily closes.",
                "Targets are applied at the next regular-session open.",
                "Gross exposure is capped at 100%; satellite budget comes after core weights.",
                "LLM/news remains advisory until PIT marginal-lift evidence exists.",
            ],
        ),
        "search_space": search_space(
            family="core_beta_satellite_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "core beta route is active75 or aggressive100",
                "satellite budget <= 20% in default research",
                "satellite only active when core state is risk_on",
                "theme gate must pass before stock/theme selection",
                "train-only ranking; validation is separate",
            ],
        ),
        "references": [
            {
                "title": "Time Series Momentum",
                "authors": "Moskowitz, Ooi, Pedersen",
                "url": "https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf",
                "used_for": "core trend and absolute momentum route hypothesis",
            },
            {
                "title": "Do Industries Explain Momentum?",
                "authors": "Moskowitz, Grinblatt",
                "url": "https://doi.org/10.1111/0022-1082.00146",
                "used_for": "industry/theme confirmation for stock momentum satellite",
            },
            {
                "title": "Momentum Has Its Moments",
                "authors": "Barroso, Santa-Clara",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "used_for": "volatility-managed momentum risk control",
            },
            {
                "title": "SEC Leveraged and Inverse ETFs Investor Bulletin",
                "url": "https://www.sec.gov/investor/pubs/leveragedetfs-alert.htm",
                "used_for": "leveraged ETF daily reset and compounding risk review",
            },
        ],
        "anti_leakage": [
            "Core and satellite target weights use index-1 daily closes.",
            "Backtest return is open[index] to open[index+1], after the signal close.",
            "Candidate ranking uses 2022-2024 train metrics only.",
            "2025, 2026, last_12m, and last_24m windows do not select the route.",
            "The satellite is evaluated against a core-only ablation to prevent false attribution.",
        ],
        "known_limits": [
            "Current-constituent NASDAQ representative universe is not PIT membership.",
            "Alpaca IEX/cache is not consolidated SIP evidence.",
            (
                "Corporate actions are assumed adjusted by data provider; "
                "distributions/taxes are not modeled."
            ),
            "LLM/news does not influence target weights in this pass.",
        ],
        "acceptance_standard": {
            "alpha_vs_qqq": "train/OOS/full > 0",
            "active_beta_comparison": "full annualized no worse than active beta by 3 points",
            "satellite_marginal_lift": "full > 0 and OOS not worse than -3 annualized points",
            "oos_sharpe_ratio": "0.7 to 2.5",
            "max_drawdown_pct": "> -32",
            "gross_exposure": "<= 100%",
            "walk_forward": ">=60% folds non-harmful versus active beta and core-only ablation",
            "paper_ready_pass": False,
        },
        "acceptance_gate": _acceptance_gate(selected, walk_forward, validation),
        "pass_status": pass_status,
        "research_cost": {
            "candidate_count": len(params_grid),
            "walk_forward_candidate_count": len(
                _walk_forward_params(candidates, walk_forward_top_k)
            ),
            "walk_forward_top_k": walk_forward_top_k,
            "walk_forward_folds": len(walk_forward),
        },
        "runtime_seconds": runtime,
        "selected_route_label": selected.params.label,
        "selected_candidate": _candidate_payload(selected),
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_payload(item) for item in walk_forward],
        "validation_windows": validation,
    }


def _write_report(path: Path, json_path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    selected = payload["selected_candidate"]
    gate = payload["acceptance_gate"]
    status = payload["pass_status"]
    lines = [
        f"# Core Beta Satellite Router Research: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Selected route: `{payload['selected_route_label']}`",
        f"- Research pass: `{status['research_pass']}`",
        f"- Paper ready pass: `{status['paper_ready_pass']}`",
        f"- Selection policy: `{payload['selection_policy']}`",
        f"- Candidate universe size: `{len(payload['candidate_symbols'])}`",
        "",
        "## Acceptance",
        "",
        f"- passed: `{gate['passed']}`",
        f"- objective: `{gate['objective']}`",
        f"- walk-forward non-harmful vs active beta: "
        f"`{gate['walk_forward_active_nonharmful_folds']}/{gate['walk_forward_fold_count']}`",
        f"- walk-forward non-harmful satellite lift: "
        f"`{gate['walk_forward_lift_nonharmful_folds']}/{gate['walk_forward_fold_count']}`",
    ]
    for key, value in gate["conditions"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Selected Metrics",
            "",
            f"- Rank / score: `{selected['rank']}` / `{selected['score']:.2f}`",
            (
                f"- Quality flags: "
                f"`{', '.join(selected['quality_flags']) if selected['quality_flags'] else 'none'}`"
            ),
            *_metric_lines("Train", selected["train"]),
            *_metric_lines("2025 OOS", selected["out_of_sample"]),
            *_metric_lines("Full", selected["full_window"]),
            "",
            "## Validation Windows",
            "",
            (
                "| Window | Dates | Ann. | Sharpe | Max DD | Alpha vs QQQ | "
                "Alpha vs Active | Satellite Lift | Sat Days |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["validation_windows"]:
        lines.append(
            f"| {row['name']} | {row.get('start_date')} -> {row.get('end_date')} | "
            f"{_fmt(row.get('annualized_return_pct'))}% | {_fmt(row.get('sharpe_ratio'))} | "
            f"{_fmt(row.get('max_drawdown_pct'))}% | "
            f"{_fmt(row.get('alpha_vs_qqq_buy_hold_annualized_pct'))}% | "
            f"{_fmt(row.get('alpha_vs_active_beta_annualized_pct'))}% | "
            f"{_fmt(row.get('satellite_marginal_annualized_pct'))}% | "
            f"{row.get('satellite_days')} |"
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
            "## Risk Review",
            "",
            "- This research does not touch the active paper strategy.",
            "- The satellite is only useful if marginal lift survives OOS and walk-forward checks.",
            "- LLM/news remains advisory; no LLM alpha is claimed here.",
            (
                "- Paper automation is blocked until execution mapping, promotion, "
                "readiness, and user confirmation exist."
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: CoreBetaSatelliteCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__
        | {"label": candidate.params.label, "core_route_label": candidate.params.core_route_label},
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: CoreBetaSatelliteWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__
        | {"label": item.params.label, "core_route_label": item.params.core_route_label},
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _metric_lines(label: str, metrics: dict[str, Any]) -> list[str]:
    return [
        f"- {label} annualized / Sharpe / max DD: "
        f"`{_fmt(metrics.get('annualized_return_pct'))}%` / "
        f"`{_fmt(metrics.get('sharpe_ratio'))}` / "
        f"`{_fmt(metrics.get('max_drawdown_pct'))}%`",
        f"- {label} Alpha vs QQQ / Active beta / Core-only annualized: "
        f"`{_fmt(metrics.get('alpha_vs_qqq_buy_hold_annualized_pct'))}%` / "
        f"`{_fmt(metrics.get('alpha_vs_active_beta_annualized_pct'))}%` / "
        f"`{_fmt(metrics.get('satellite_marginal_annualized_pct'))}%`",
        f"- {label} win/PF/payoff: "
        f"`{_fmt(metrics.get('win_day_pct'))}%` / "
        f"`{_fmt(metrics.get('profit_factor'))}` / "
        f"`{_fmt(metrics.get('payoff_ratio'))}`",
        f"- {label} gross/core/satellite avg: "
        f"`{_fmt(metrics.get('average_gross_exposure_pct'))}%` / "
        f"`{_fmt(metrics.get('average_core_gross_pct'))}%` / "
        f"`{_fmt(metrics.get('average_satellite_gross_pct'))}%`",
        f"- {label} satellite days / rebalances / turnover: "
        f"`{metrics.get('satellite_days')}` / `{metrics.get('rebalance_count')}` / "
        f"`{_fmt(metrics.get('turnover_ratio'))}`",
    ]


def _params_grid_ranges(params_grid: list[CoreBetaSatelliteParams]) -> dict[str, list[Any]]:
    keys = [
        "core_variant",
        "universe_mode",
        "satellite_budget",
        "satellite_momentum_days",
        "confirmation_days",
        "top_n",
        "max_symbol_weight",
        "score_mode",
        "theme_gate_symbol",
        "theme_sma_days",
        "theme_momentum_days",
        "min_theme_momentum_pct",
        "satellite_volatility_lookback_days",
        "target_satellite_volatility_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _momentum_array(cache: dict[str, Any], lookback: int) -> np.ndarray:
    if lookback not in cache["momentum"]:
        close = cache["close_np"]
        values = np.full_like(close, np.nan, dtype=float)
        values[lookback:, :] = (close[lookback:, :] / close[:-lookback, :] - 1) * 100
        cache["momentum"][lookback] = values
    return cache["momentum"][lookback]


def _symbol_volatility_array(cache: dict[str, Any], lookback: int) -> np.ndarray:
    if lookback not in cache["symbol_volatility"]:
        values = (
            pd.DataFrame(cache["close_np"])
            .pct_change()
            .rolling(lookback, min_periods=2)
            .std()
            .to_numpy(dtype=float)
            * math.sqrt(252)
            * 100
        )
        cache["symbol_volatility"][lookback] = values
    return cache["symbol_volatility"][lookback]


def _symbols_for_mode(
    dataset: CoreBetaSatelliteDataset,
    mode: UniverseMode,
) -> list[str]:
    allowed = {
        "semiconductor": SEMICONDUCTOR_SYMBOLS,
        "wide_mega": WIDE_MEGA_SYMBOLS,
        "theme_etf": THEME_ETF_SYMBOLS,
    }[mode]
    return [symbol for symbol in allowed if symbol in dataset.symbols]


def _candidate_symbols_for_modes(modes: list[UniverseMode]) -> list[str]:
    symbols: list[str] = []
    for mode in modes:
        symbols.extend(
            {
                "semiconductor": SEMICONDUCTOR_SYMBOLS,
                "wide_mega": WIDE_MEGA_SYMBOLS,
                "theme_etf": THEME_ETF_SYMBOLS,
            }[mode]
        )
    return list(dict.fromkeys(symbols))


def _all_trade_symbols(dataset: CoreBetaSatelliteDataset) -> list[str]:
    return list(dict.fromkeys(["QQQ", "TQQQ", "SQQQ", *dataset.symbols]))


def _cap_gross(weights: dict[str, float]) -> dict[str, float]:
    gross = sum(abs(value) for value in weights.values())
    if gross <= 1.0 or gross <= 0:
        return weights
    scale = 1.0 / gross
    return {symbol: value * scale for symbol, value in weights.items()}


def _buy_hold_return(
    dataset: CoreBetaSatelliteDataset,
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


def _equal_weight_buy_hold(
    dataset: CoreBetaSatelliteDataset,
    params: CoreBetaSatelliteParams,
    start_index: int,
    end_index: int,
) -> float:
    symbols = _symbols_for_mode(dataset, params.universe_mode)
    if not symbols:
        return 0.0
    return sum(
        _buy_hold_return(dataset, symbol, start_index, end_index) for symbol in symbols
    ) / len(symbols)


def _effective_lookback(params: CoreBetaSatelliteParams) -> int:
    core = beta_params_from_label(params.core_route_label)
    return max(
        _beta_effective_lookback(core) + 1,
        params.satellite_momentum_days,
        params.confirmation_days,
        params.theme_sma_days,
        params.theme_momentum_days,
        params.satellite_volatility_lookback_days,
    )


def _next_open_returns(open_values: np.ndarray) -> np.ndarray:
    output = np.zeros(len(open_values))
    if len(open_values) > 1:
        output[:-1] = open_values[1:] / open_values[:-1] - 1
    return output


def _annualized_from_total(total_return_pct: float, days: int) -> float | None:
    if days <= 0 or total_return_pct <= -100:
        return None
    return ((1 + total_return_pct / 100) ** (252 / days) - 1) * 100


def _alpha(value: float | None, benchmark: float | None) -> float | None:
    if value is None or benchmark is None:
        return None
    return value - benchmark


def _win_pct(returns: list[float]) -> float:
    return sum(1 for value in returns if value > 0) / len(returns) * 100 if returns else 0.0


def _profit_factor(returns: list[float]) -> float | None:
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    if losses <= 0:
        return None if gains <= 0 else math.inf
    return gains / losses


def _average_win_pct(returns: list[float]) -> float | None:
    wins = [value for value in returns if value > 0]
    return mean(wins) * 100 if wins else None


def _average_loss_pct(returns: list[float]) -> float | None:
    losses = [value for value in returns if value < 0]
    return mean(losses) * 100 if losses else None


def _payoff_ratio(returns: list[float]) -> float | None:
    win = _average_win_pct(returns)
    loss = _average_loss_pct(returns)
    if win is None or loss is None or loss == 0:
        return None
    return abs(win / loss)


def _index_for_date(
    dataset: CoreBetaSatelliteDataset,
    date: str,
    *,
    side: str = "left",
) -> int:
    dates = list(dataset.dates)
    if side == "right":
        return next((index for index, value in enumerate(dates) if value > date), len(dates))
    return next((index for index, value in enumerate(dates) if value >= date), len(dates))


def _validation_boundaries(dataset: CoreBetaSatelliteDataset) -> list[tuple[str, str, str]]:
    last = dataset.dates[-1]
    return [
        ("calendar_2022", "2022-01-03", "2022-12-30"),
        ("calendar_2023", "2023-01-03", "2023-12-29"),
        ("calendar_2024", "2024-01-02", "2024-12-31"),
        ("calendar_2025", "2025-01-02", "2025-12-31"),
        ("ytd_2026", "2026-01-02", last),
        ("last_12m", _date_offset(last, months=12), last),
        ("last_24m", _date_offset(last, months=24), last),
    ]


def _walk_forward_boundaries() -> list[tuple[int, str, str, str, str]]:
    return [
        (1, "2022-01-03", "2022-12-30", "2023-01-03", "2023-12-29"),
        (2, "2022-01-03", "2023-12-29", "2024-01-02", "2024-12-31"),
        (3, "2022-01-03", "2024-12-31", "2025-01-02", "2025-12-31"),
        (4, "2022-01-03", "2025-12-31", "2026-01-02", "2026-05-18"),
    ]


def _date_offset(date: str, *, months: int) -> str:
    timestamp = pd.Timestamp(date)
    return (timestamp - pd.DateOffset(months=months)).date().isoformat()


def _empty_metrics(
    dataset: CoreBetaSatelliteDataset,
    start_index: int,
    end_index: int,
) -> CoreBetaSatelliteMetrics:
    return CoreBetaSatelliteMetrics(
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
        win_day_pct=0.0,
        profit_factor=None,
        average_win_pct=None,
        average_loss_pct=None,
        payoff_ratio=None,
        qqq_buy_hold_return_pct=0.0,
        qqq_buy_hold_annualized_pct=None,
        alpha_vs_qqq_buy_hold_annualized_pct=None,
        tqqq_buy_hold_return_pct=0.0,
        tqqq_buy_hold_annualized_pct=None,
        alpha_vs_tqqq_buy_hold_annualized_pct=None,
        equal_weight_buy_hold_annualized_pct=None,
        alpha_vs_equal_weight_buy_hold_annualized_pct=None,
        active_beta_annualized_pct=None,
        alpha_vs_active_beta_annualized_pct=None,
        core_only_annualized_pct=None,
        satellite_marginal_annualized_pct=None,
        exposure_pct=0.0,
        average_gross_exposure_pct=0.0,
        max_gross_exposure_pct=0.0,
        average_core_gross_pct=0.0,
        average_satellite_gross_pct=0.0,
        satellite_days=0,
        average_selected_count=0.0,
        rebalance_count=0,
        turnover_ratio=0.0,
        cost_drag_pct=0.0,
    )


def _core_variants(values: list[str] | None) -> list[CoreVariant] | None:
    return [_core_variant(value) for value in values] if values else None


def _core_variant(value: str) -> CoreVariant:
    normalized = value.strip()
    if normalized not in {"active75", "aggressive100"}:
        raise ValueError(f"unsupported core variant: {value}")
    return normalized  # type: ignore[return-value]


def _universe_modes(values: list[str] | None) -> list[UniverseMode] | None:
    return [_universe_mode(value) for value in values] if values else None


def _universe_mode(value: str) -> UniverseMode:
    normalized = value.strip()
    if normalized not in {"semiconductor", "wide_mega", "theme_etf"}:
        raise ValueError(f"unsupported universe mode: {value}")
    return normalized  # type: ignore[return-value]


def _score_modes(values: list[str] | None) -> list[ScoreMode] | None:
    return [_score_mode(value) for value in values] if values else None


def _score_mode(value: str) -> ScoreMode:
    normalized = value.strip()
    if normalized not in {"raw", "risk_adjusted", "composite"}:
        raise ValueError(f"unsupported score mode: {value}")
    return normalized  # type: ignore[return-value]


def _theme_gates(values: list[str] | None) -> list[ThemeGate] | None:
    return [_theme_gate(value) for value in values] if values else None


def _theme_gate(value: str) -> ThemeGate:
    normalized = value.strip().upper()
    if normalized not in {"QQQ", "SMH", "SOXX", "XLK"}:
        raise ValueError(f"unsupported theme gate: {value}")
    return normalized  # type: ignore[return-value]


def _label_optional(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return f"{float(value):.2f}"


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
