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
class ThemeIntradayParams:
    market_sma_days: int
    market_momentum_days: int
    min_market_momentum_pct: float
    signal_momentum_days: int
    confirmation_days: int
    top_n: int
    beta_symbol: str
    beta_weight: float
    satellite_weight: float
    max_symbol_weight: float
    market_below_sma_scale: float
    target_market_volatility_pct: float | None
    drawdown_lookback_days: int
    max_market_drawdown_pct: float | None
    score_mode: str
    semiconductor_gate: bool

    @property
    def label(self) -> str:
        return (
            f"theme_intraday:sma{self.market_sma_days}_mmom{self.market_momentum_days}_"
            f"minm{self.min_market_momentum_pct:g}_lb{self.signal_momentum_days}_"
            f"conf{self.confirmation_days}_top{self.top_n}_beta{self.beta_symbol}{self.beta_weight:g}_"
            f"sat{self.satellite_weight:g}_maxw{self.max_symbol_weight:g}_"
            f"off{self.market_below_sma_scale:g}_tvol{_opt(self.target_market_volatility_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{_opt(self.max_market_drawdown_pct)}_"
            f"score{self.score_mode}_sem{1 if self.semiconductor_gate else 0}"
        )


def theme_intraday_params_from_label(label: str) -> ThemeIntradayParams:
    match = re.match(
        r"^theme_intraday:sma(?P<sma>\d+)_mmom(?P<mmom>\d+)_minm(?P<minm>[-0-9.]+)_"
        r"lb(?P<lb>\d+)_conf(?P<conf>\d+)_top(?P<top>\d+)_"
        r"beta(?P<beta>[A-Z]+)(?P<betaw>[-0-9.]+)_sat(?P<sat>[-0-9.]+)_"
        r"maxw(?P<maxw>[-0-9.]+)_off(?P<off>[-0-9.]+)_tvol(?P<tvol>none|[-0-9.]+)_"
        r"dd(?P<dd>\d+)_maxdd(?P<maxdd>none|[-0-9.]+)_score(?P<score>[a-zA-Z0-9_]+)_sem(?P<sem>[01])$",
        label,
    )
    if match is None:
        raise ValueError(f"unsupported theme intraday route label: {label}")
    return ThemeIntradayParams(
        market_sma_days=int(match.group("sma")),
        market_momentum_days=int(match.group("mmom")),
        min_market_momentum_pct=float(match.group("minm")),
        signal_momentum_days=int(match.group("lb")),
        confirmation_days=int(match.group("conf")),
        top_n=int(match.group("top")),
        beta_symbol=match.group("beta"),
        beta_weight=float(match.group("betaw")),
        satellite_weight=float(match.group("sat")),
        max_symbol_weight=float(match.group("maxw")),
        market_below_sma_scale=float(match.group("off")),
        target_market_volatility_pct=_parse_optional_float(match.group("tvol")),
        drawdown_lookback_days=int(match.group("dd")),
        max_market_drawdown_pct=_parse_optional_float(match.group("maxdd")),
        score_mode=match.group("score"),
        semiconductor_gate=match.group("sem") == "1",
    )


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
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 5,
    walk_forward_top_k: int | None = 30,
    max_candidates: int = 900,
    refresh_data: bool = False,
):
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(spec_path)
    universe = symbols or spec.universe
    params_grid = [
        ThemeIntradayParams(*values)
        for values in product(
            market_sma_days or [20],
            market_momentum_days or [10],
            min_market_momentum_pct or [0.0],
            signal_momentum_days or [10],
            confirmation_days or [5],
            top_n or [2],
            [item.upper() for item in (beta_symbol or ["QQQ"])],
            beta_weight or [0.25],
            satellite_weight or [0.5],
            max_symbol_weight or [0.25],
            market_below_sma_scale or [0.0],
            target_market_volatility_pct or [None],
            drawdown_lookback_days or [20],
            max_market_drawdown_pct or [None],
            score_mode or ["raw"],
            semiconductor_gate or [False],
        )
    ]
    if len(params_grid) > max_candidates:
        raise ValueError(f"theme intraday grid would create {len(params_grid)} candidates")
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="theme_intraday_rotation_router",
        report_suffix="theme-intraday-rotation-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: load_theme_intraday_dataset(
            root=base,
            spec=spec,
            symbols=universe,
            data_source=data_source,
            feed=feed or spec.data.feed,
            start=start,
            end=end,
            market_symbol=market_symbol,
            benchmark_symbol=benchmark_symbol,
            refresh_data=refresh_data,
        ),
        snapshot=_target_snapshot,
        objective="theme_intraday_rotation_alpha_vs_qqq_and_active_beta_after_costs",
        filters=[
            "Route selection uses index-1 close",
            "same-session execution remains research-only",
        ],
        out_of_sample_ratio=out_of_sample_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
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
) -> RouterFrameDataset:
    return load_daily_dataset(
        spec=spec,
        root=root,
        symbols=list(dict.fromkeys([*symbols, market_symbol, benchmark_symbol, "SMH"])),
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol=market_symbol,
        benchmark_symbol=benchmark_symbol,
        refresh_data=refresh_data,
        fetcher=fetch_ohlcv,
    )


def _target_snapshot(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: ThemeIntradayParams,
    index: int,
) -> TargetSnapshot:
    regime = market_sma_scale(dataset, params, index)
    selected = selected_by_momentum(
        dataset,
        index,
        lookback=params.signal_momentum_days,
        top_n=params.top_n,
        symbols=[
            symbol
            for symbol in dataset.symbols
            if symbol not in {params.beta_symbol, "QQQ", "TQQQ"}
        ],
    )
    scale = volatility_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.drawdown_lookback_days,
        target_pct=params.target_market_volatility_pct,
    )
    weights = {params.beta_symbol: params.beta_weight * regime * scale}
    if selected and regime > 0:
        per_symbol = min(params.max_symbol_weight, params.satellite_weight * scale / len(selected))
        weights.update({symbol: per_symbol for symbol in selected})
    weights = {symbol: weight for symbol, weight in weights.items() if weight > 0}
    return TargetSnapshot(list(weights), weights, scale, regime, 1.0)


def _opt(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)
