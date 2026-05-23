from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from open_composer.adapters.data import fetch_ohlcv
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.router_common import (
    RouterFrameDataset,
    TargetSnapshot,
    load_daily_dataset,
    run_router_research,
    selected_by_momentum,
    volatility_scale,
)


@dataclass(frozen=True)
class AggressiveThemeParams:
    trend_sma_days: int
    momentum_lookback_days: int
    top_n: int
    min_theme_momentum_pct: float
    core_weight: float
    theme_gross_weight: float
    levered_symbol: str
    levered_weight: float
    defensive_symbol: str
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
            f"tvol{_opt(self.target_portfolio_volatility_pct)}_"
            f"maxv{_opt(self.max_market_volatility_pct)}_dd{self.drawdown_lookback_days}_"
            f"maxdd{_opt(self.max_market_drawdown_pct)}_thr{self.rebalance_threshold_pct:g}"
        )


def aggressive_theme_params_from_label(label: str) -> AggressiveThemeParams:
    match = re.match(
        r"^aggr_theme:sma(?P<sma>\d+)_mom(?P<mom>\d+)_top(?P<top>\d+)_min(?P<min>[-0-9.]+)_"
        r"core(?P<core>[-0-9.]+)_theme(?P<theme>[-0-9.]+)_lev(?P<lev>[A-Z]+)(?P<levw>[-0-9.]+)_"
        r"def(?P<def>[A-Z]+)(?P<defw>[-0-9.]+)_vol(?P<vol>\d+)_tvol(?P<tvol>none|[-0-9.]+)_"
        r"maxv(?P<maxv>none|[-0-9.]+)_dd(?P<dd>\d+)_maxdd(?P<maxdd>none|[-0-9.]+)_thr(?P<thr>[-0-9.]+)$",
        label,
    )
    if match is None:
        raise ValueError(f"unsupported aggressive theme route label: {label}")
    return AggressiveThemeParams(
        trend_sma_days=int(match.group("sma")),
        momentum_lookback_days=int(match.group("mom")),
        top_n=int(match.group("top")),
        min_theme_momentum_pct=float(match.group("min")),
        core_weight=float(match.group("core")),
        theme_gross_weight=float(match.group("theme")),
        levered_symbol=match.group("lev"),
        levered_weight=float(match.group("levw")),
        defensive_symbol=match.group("def"),
        defensive_weight=float(match.group("defw")),
        volatility_lookback_days=int(match.group("vol")),
        target_portfolio_volatility_pct=_parse_optional_float(match.group("tvol")),
        max_market_volatility_pct=_parse_optional_float(match.group("maxv")),
        drawdown_lookback_days=int(match.group("dd")),
        max_market_drawdown_pct=_parse_optional_float(match.group("maxdd")),
        rebalance_threshold_pct=float(match.group("thr")),
    )


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
):
    params_grid = [
        AggressiveThemeParams(*values)
        for values in product(
            trend_sma_days or [20],
            momentum_lookback_days or [10, 20],
            top_n_values or [1, 2],
            min_theme_momentum_pct or [0.0],
            core_weight or [0.2],
            theme_gross_weight or [0.6],
            [item.upper() for item in (levered_symbol or ["TQQQ"])],
            levered_weight or [0.1],
            [item.upper() for item in (defensive_symbol or ["CASH"])],
            defensive_weight or [0.0],
            volatility_lookback_days or [20],
            target_portfolio_volatility_pct or [None],
            max_market_volatility_pct or [None],
            drawdown_lookback_days or [60],
            max_market_drawdown_pct or [None],
            rebalance_threshold_pct or [0.0],
        )
    ]
    if len(params_grid) > max_candidates:
        raise ValueError(f"aggressive theme grid would create {len(params_grid)} candidates")
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="aggressive_theme_router",
        report_suffix="aggressive-theme-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: load_aggressive_theme_dataset(
            root=base,
            spec=spec,
            data_source=data_source,
            feed=feed or spec.data.feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        ),
        snapshot=_target_snapshot,
        objective="aggressive_theme_alpha_vs_qqq_after_costs",
        filters=["index-1 close theme ranking", "levered sleeve is bounded"],
        out_of_sample_ratio=out_of_sample_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
    )


def load_aggressive_theme_dataset(
    *,
    root: Path,
    spec: StrategySpec,
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> RouterFrameDataset:
    symbols = list(dict.fromkeys([*spec.universe, "QQQ", "TQQQ", "QLD", "SOXL"]))
    return load_daily_dataset(
        spec=spec,
        root=root,
        symbols=symbols,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="QQQ",
        refresh_data=refresh_data,
        fetcher=fetch_ohlcv,
    )


def _target_snapshot(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: AggressiveThemeParams,
    index: int,
) -> TargetSnapshot:
    selected = selected_by_momentum(
        dataset,
        index,
        lookback=params.momentum_lookback_days,
        top_n=params.top_n,
        min_momentum_pct=params.min_theme_momentum_pct,
        symbols=[
            symbol for symbol in dataset.symbols if symbol not in {"QQQ", params.levered_symbol}
        ],
    )
    scale = volatility_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.volatility_lookback_days,
        target_pct=params.target_portfolio_volatility_pct,
    )
    weights = {"QQQ": params.core_weight * scale}
    if selected:
        per_theme = params.theme_gross_weight * scale / len(selected)
        weights.update({symbol: per_theme for symbol in selected})
    if params.levered_symbol != "CASH":
        weights[params.levered_symbol] = params.levered_weight * scale
    if not selected and params.defensive_symbol != "CASH":
        weights[params.defensive_symbol] = params.defensive_weight
    max_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    weights = {symbol: min(weight, max_weight) for symbol, weight in weights.items() if weight > 0}
    return TargetSnapshot(list(weights), weights, scale, 1.0, 1.0)


def _opt(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)
