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
    market_sma_scale,
    run_router_research,
    selected_by_momentum,
    volatility_scale,
)


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
    satellite_symbol: str
    satellite_weight: float
    risk_off_core_scale: float
    target_satellite_volatility_pct: float | None
    rebalance_threshold_pct: float

    @property
    def label(self) -> str:
        return (
            f"core_sat:sma{self.trend_sma_days}_mom{self.momentum_lookback_days}_"
            f"min{self.min_momentum_pct:g}_vol{self.volatility_lookback_days}_"
            f"maxv{_opt(self.max_volatility_annual_pct)}_dd{self.drawdown_lookback_days}_"
            f"maxdd{_opt(self.max_drawdown_pct)}_core{self.core_weight:g}_"
            f"sat{self.satellite_symbol}{self.satellite_weight:g}_"
            f"off{self.risk_off_core_scale:g}_tvol{_opt(self.target_satellite_volatility_pct)}_"
            f"thr{self.rebalance_threshold_pct:g}"
        )


def core_satellite_params_from_label(label: str) -> CoreSatelliteParams:
    match = re.match(
        r"^core_sat:sma(?P<sma>\d+)_mom(?P<mom>\d+)_min(?P<min>[-0-9.]+)_"
        r"vol(?P<vol>\d+)_maxv(?P<maxv>none|[-0-9.]+)_dd(?P<dd>\d+)_"
        r"maxdd(?P<maxdd>none|[-0-9.]+)_core(?P<core>[-0-9.]+)_"
        r"sat(?P<sat>[A-Z]+)(?P<satw>[-0-9.]+)_off(?P<off>[-0-9.]+)_"
        r"tvol(?P<tvol>none|[-0-9.]+)_thr(?P<thr>[-0-9.]+)$",
        label,
    )
    if match is None:
        raise ValueError(f"unsupported core satellite route label: {label}")
    return CoreSatelliteParams(
        trend_sma_days=int(match.group("sma")),
        momentum_lookback_days=int(match.group("mom")),
        min_momentum_pct=float(match.group("min")),
        volatility_lookback_days=int(match.group("vol")),
        max_volatility_annual_pct=_parse_optional_float(match.group("maxv")),
        drawdown_lookback_days=int(match.group("dd")),
        max_drawdown_pct=_parse_optional_float(match.group("maxdd")),
        core_weight=float(match.group("core")),
        satellite_symbol=match.group("sat"),
        satellite_weight=float(match.group("satw")),
        risk_off_core_scale=float(match.group("off")),
        target_satellite_volatility_pct=_parse_optional_float(match.group("tvol")),
        rebalance_threshold_pct=float(match.group("thr")),
    )


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
):
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(spec_path)
    satellites = [
        item.upper()
        for item in (
            satellite_symbols
            or [item for item in spec.universe if item.upper() != "QQQ"]
            or ["TQQQ"]
        )
    ]
    params_grid = [
        CoreSatelliteParams(*values)
        for values in product(
            trend_sma_days or [20, 50],
            momentum_lookback_days or [10, 20],
            min_momentum_pct or [0.0],
            volatility_lookback_days or [20],
            max_volatility_annual_pct or [None],
            drawdown_lookback_days or [60],
            max_drawdown_pct or [None],
            core_weight or [0.6],
            satellites,
            satellite_weight or [0.2],
            risk_off_core_scale or [0.5],
            target_satellite_volatility_pct or [None],
            rebalance_threshold_pct or [0.0],
        )
    ]
    if len(params_grid) > max_candidates:
        raise ValueError(f"core satellite grid would create {len(params_grid)} candidates")
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="core_satellite_router",
        report_suffix="core-satellite-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: load_core_satellite_dataset(
            root=base,
            spec=spec,
            symbols=["QQQ", *satellites],
            data_source=data_source,
            feed=feed or spec.data.feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        ),
        snapshot=core_satellite_target_weight_snapshot,
        objective="core_satellite_alpha_vs_qqq_buy_hold_after_costs",
        filters=["index-1 QQQ trend gate", "satellite exposure is bounded"],
        out_of_sample_ratio=out_of_sample_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
    )


def load_core_satellite_dataset(
    *,
    root: Path,
    spec: StrategySpec,
    symbols: list[str],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> RouterFrameDataset:
    return load_daily_dataset(
        spec=spec,
        root=root,
        symbols=list(dict.fromkeys([symbol.upper() for symbol in symbols])),
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="QQQ",
        refresh_data=refresh_data,
        fetcher=fetch_ohlcv,
    )


def core_satellite_target_weight_snapshot(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: CoreSatelliteParams,
    index: int,
) -> TargetSnapshot:
    trend_scale = market_sma_scale(
        dataset, params, index, field="trend_sma_days", scale_field="risk_off_core_scale"
    )
    core = (
        params.core_weight if trend_scale >= 1 else params.core_weight * params.risk_off_core_scale
    )
    selected = selected_by_momentum(
        dataset,
        index,
        lookback=params.momentum_lookback_days,
        top_n=1,
        min_momentum_pct=params.min_momentum_pct,
        symbols=[params.satellite_symbol],
    )
    sat_scale = volatility_scale(
        dataset,
        params.satellite_symbol,
        index,
        lookback=params.volatility_lookback_days,
        target_pct=params.target_satellite_volatility_pct,
    )
    weights = {"QQQ": max(0.0, core)}
    if selected and trend_scale > 0:
        weights[params.satellite_symbol] = params.satellite_weight * sat_scale
    max_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    weights = {symbol: min(weight, max_weight) for symbol, weight in weights.items() if weight > 0}
    return TargetSnapshot(list(weights), weights, sat_scale, trend_scale, 1.0)


def _opt(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)
