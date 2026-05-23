from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from open_composer.adapters.data import fetch_ohlcv
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research import beta_router_core as _beta
from open_composer.research.beta_router_core import (
    beta_params_from_label,
    beta_target_weight_snapshot,
    load_beta_router_dataset,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    TargetSnapshot,
    effective_lookback,
    load_daily_dataset,
    run_router_research,
    selected_by_momentum,
    volatility_scale,
)

ACTIVE_BETA_ROUTE_LABEL = (
    "beta:sma20_mom20_min0_vol20_maxvnone_dd60_maxddnone_"
    "levsmanone_levmaxvnone_levdd60_levmaxddnone_"
    "onTQQQ0.5_neuQQQ0.5_offCASH0_vtnone"
)


@dataclass(frozen=True)
class CoreBetaSatelliteParams:
    core_variant: str
    universe_mode: str
    satellite_budget: float
    satellite_momentum_days: int
    confirmation_days: int
    top_n: int
    max_symbol_weight: float
    score_mode: str
    theme_gate_symbol: str
    theme_sma_days: int
    theme_momentum_days: int
    min_theme_momentum_pct: float
    satellite_volatility_lookback_days: int
    target_satellite_volatility_pct: float | None

    @property
    def label(self) -> str:
        return (
            f"core_beta_sat:core{self.core_variant}_u{self.universe_mode}_"
            f"sat{self.satellite_budget:g}_mom{self.satellite_momentum_days}_"
            f"conf{self.confirmation_days}_top{self.top_n}_maxw{self.max_symbol_weight:g}_"
            f"score{self.score_mode}_gate{self.theme_gate_symbol}_gsma{self.theme_sma_days}_"
            f"gmom{self.theme_momentum_days}_gmin{self.min_theme_momentum_pct:g}_"
            f"vol{self.satellite_volatility_lookback_days}_"
            f"tvol{_opt(self.target_satellite_volatility_pct)}"
        )

    @property
    def core_route_label(self) -> str:
        return ACTIVE_BETA_ROUTE_LABEL


@dataclass(frozen=True)
class CoreBetaSatelliteDataset(RouterFrameDataset):
    beta_dataset: object | None = None


def core_beta_satellite_params_from_label(label: str) -> CoreBetaSatelliteParams:
    match = re.match(
        r"^core_beta_sat:core(?P<core>[a-zA-Z0-9]+)_u(?P<universe>[a-zA-Z0-9_]+)_"
        r"sat(?P<sat>[-0-9.]+)_mom(?P<mom>\d+)_conf(?P<conf>\d+)_top(?P<top>\d+)_"
        r"maxw(?P<maxw>[-0-9.]+)_score(?P<score>[a-zA-Z0-9_]+)_gate(?P<gate>[A-Z]+)_"
        r"gsma(?P<gsma>\d+)_gmom(?P<gmom>\d+)_gmin(?P<gmin>[-0-9.]+)_"
        r"vol(?P<vol>\d+)_tvol(?P<tvol>none|[-0-9.]+)$",
        label,
    )
    if match is None:
        raise ValueError(f"unsupported core beta satellite route label: {label}")
    return CoreBetaSatelliteParams(
        core_variant=match.group("core"),
        universe_mode=match.group("universe"),
        satellite_budget=float(match.group("sat")),
        satellite_momentum_days=int(match.group("mom")),
        confirmation_days=int(match.group("conf")),
        top_n=int(match.group("top")),
        max_symbol_weight=float(match.group("maxw")),
        score_mode=match.group("score"),
        theme_gate_symbol=match.group("gate"),
        theme_sma_days=int(match.group("gsma")),
        theme_momentum_days=int(match.group("gmom")),
        min_theme_momentum_pct=float(match.group("gmin")),
        satellite_volatility_lookback_days=int(match.group("vol")),
        target_satellite_volatility_pct=_parse_optional_float(match.group("tvol")),
    )


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
):
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(spec_path)
    universe = symbols or spec.universe
    params_grid = [
        CoreBetaSatelliteParams(*values)
        for values in product(
            core_variant or ["active75"],
            universe_mode or ["semiconductor"],
            satellite_budget or [0.1],
            satellite_momentum_days or [20],
            confirmation_days or [5],
            top_n or [2],
            max_symbol_weight or [0.1],
            score_mode or ["raw"],
            theme_gate_symbol or ["SMH"],
            theme_sma_days or [30],
            theme_momentum_days or [10],
            min_theme_momentum_pct or [0.0],
            satellite_volatility_lookback_days or [20],
            target_satellite_volatility_pct or [None],
        )
    ]
    if len(params_grid) > max_candidates:
        raise ValueError(f"core beta satellite grid would create {len(params_grid)} candidates")
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="core_beta_satellite_router",
        report_suffix="core-beta-satellite-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: load_core_beta_satellite_dataset(
            root=base,
            spec=spec,
            symbols=universe,
            data_source=data_source,
            feed=feed or spec.data.feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        ),
        snapshot=lambda spec, dataset, params, index: _target_snapshot(
            dataset,
            beta_params_from_label(params.core_route_label),
            params,
            index,
        ),
        objective="core_beta_satellite_alpha_vs_active_beta_after_costs",
        filters=["core-only ablation is required", "satellite sleeve is bounded"],
        out_of_sample_ratio=0.35,
        walk_forward_folds=3,
        walk_forward_top_k=walk_forward_top_k,
    )


def load_core_beta_satellite_dataset(
    *,
    root: Path,
    spec: StrategySpec,
    symbols: list[str] | None,
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    refresh_data: bool,
) -> CoreBetaSatelliteDataset:
    universe = list(dict.fromkeys([item.upper() for item in (symbols or spec.universe)]))
    required = list(dict.fromkeys(["QQQ", "TQQQ", "SQQQ", "SMH", *universe]))
    base = load_daily_dataset(
        spec=spec,
        root=root,
        symbols=required,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        refresh_data=refresh_data,
        fetcher=fetch_ohlcv,
    )
    _beta.fetch_ohlcv = fetch_ohlcv
    beta_dataset = load_beta_router_dataset(
        root=root,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
        timeframe=spec.timeframe,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
        fetcher=fetch_ohlcv,
    )
    return CoreBetaSatelliteDataset(
        symbols=universe,
        market_symbol=base.market_symbol,
        benchmark_symbol=base.benchmark_symbol,
        dates=base.dates,
        frame=base.frame,
        data_profile=base.data_profile,
        beta_dataset=beta_dataset,
    )


def core_beta_satellite_target_weight_snapshot(
    dataset: CoreBetaSatelliteDataset,
    params: CoreBetaSatelliteParams,
    index: int,
) -> TargetSnapshot:
    return _target_snapshot(
        dataset,
        beta_params_from_label(params.core_route_label),
        params,
        index,
    )


def _target_snapshot(
    dataset: CoreBetaSatelliteDataset,
    core_params,
    params: CoreBetaSatelliteParams,
    index: int,
) -> TargetSnapshot:
    core = beta_target_weight_snapshot(dataset.beta_dataset, core_params, index)
    weights = dict(core.weights)
    theme_ok = _theme_gate_ok(dataset, params, index)
    selected = []
    if theme_ok and params.satellite_budget > 0:
        selected = selected_by_momentum(
            dataset,
            index,
            lookback=params.satellite_momentum_days,
            top_n=params.top_n,
            min_momentum_pct=0.0,
            symbols=[symbol for symbol in dataset.symbols if symbol not in {"QQQ", "TQQQ", "SQQQ"}],
        )
        scale = volatility_scale(
            dataset,
            dataset.market_symbol,
            index,
            lookback=params.satellite_volatility_lookback_days,
            target_pct=params.target_satellite_volatility_pct,
        )
        if selected:
            per_symbol = min(
                params.max_symbol_weight, params.satellite_budget * scale / len(selected)
            )
            for symbol in selected:
                weights[symbol] = per_symbol
    else:
        scale = 0.0
    return TargetSnapshot(
        selected=list(weights),
        weights={symbol: weight for symbol, weight in weights.items() if weight > 0},
        state=core.state,
        core_gross=sum(abs(value) for value in core.weights.values()),
        satellite_gross=sum(weights.get(symbol, 0.0) for symbol in selected),
        satellite_scale=scale,
        theme_gate_ok=theme_ok,
    )


def _theme_gate_ok(
    dataset: CoreBetaSatelliteDataset, params: CoreBetaSatelliteParams, index: int
) -> bool:
    if index < max(params.theme_sma_days, params.theme_momentum_days) + 1:
        return False
    symbol = params.theme_gate_symbol
    close = dataset.frame[f"{symbol}_close"].astype(float)
    sma = float(close.iloc[index - params.theme_sma_days : index].mean())
    prior = float(close.iloc[index - 1])
    earlier = float(close.iloc[index - params.theme_momentum_days - 1])
    momentum = (prior / earlier - 1) * 100 if earlier > 0 else -100.0
    return prior > sma and momentum >= params.min_theme_momentum_pct


def _effective_lookback(params: CoreBetaSatelliteParams) -> int:
    return effective_lookback(params)


def _all_trade_symbols(dataset: CoreBetaSatelliteDataset) -> list[str]:
    return list(dict.fromkeys(["QQQ", "TQQQ", "SQQQ", *dataset.symbols]))


def _opt(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)
