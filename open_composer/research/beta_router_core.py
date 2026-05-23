from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from open_composer.adapters.data import fetch_ohlcv
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.router_common import (
    RouterFrameDataset,
    RouterMetrics,
    TargetSnapshot,
    backtest_router_params,
    drawdown_scale,
    effective_lookback,
    label_optional,
    label_optional_int,
    load_daily_dataset,
    max_volatility_ok,
    momentum_ok,
    parse_optional_float,
    parse_optional_int,
    run_router_research,
    trend_ok,
    volatility_scale,
)


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
    risk_on_symbol: str
    risk_on_weight: float
    neutral_symbol: str
    neutral_weight: float
    risk_off_symbol: str
    risk_off_weight: float
    target_volatility_annual_pct: float | None

    @property
    def label(self) -> str:
        return (
            f"beta:sma{self.trend_sma_days}_mom{self.momentum_lookback_days}_"
            f"min{self.min_momentum_pct:g}_vol{self.volatility_lookback_days}_"
            f"maxv{label_optional(self.max_volatility_annual_pct)}_"
            f"dd{self.drawdown_lookback_days}_maxdd{label_optional(self.max_drawdown_pct)}_"
            f"levsma{label_optional_int(self.leverage_trend_sma_days)}_"
            f"levmaxv{label_optional(self.max_leverage_volatility_annual_pct)}_"
            f"levdd{self.leverage_drawdown_lookback_days}_"
            f"levmaxdd{label_optional(self.max_leverage_drawdown_pct)}_"
            f"on{self.risk_on_symbol}{self.risk_on_weight:g}_"
            f"neu{self.neutral_symbol}{self.neutral_weight:g}_"
            f"off{self.risk_off_symbol}{self.risk_off_weight:g}_"
            f"vt{label_optional(self.target_volatility_annual_pct)}"
        )


@dataclass(frozen=True)
class BetaRouterDataset(RouterFrameDataset):
    leverage_symbol: str = "TQQQ"
    hedge_symbol: str | None = "SQQQ"


BetaRouterMetrics = RouterMetrics


def beta_params_from_label(label: str) -> BetaRouterParams:
    pattern = re.compile(
        r"^beta:sma(?P<sma>\d+)_mom(?P<mom>\d+)_min(?P<min>[-0-9.]+)_"
        r"vol(?P<vol>\d+)_maxv(?P<maxv>none|[-0-9.]+)_"
        r"dd(?P<dd>\d+)_maxdd(?P<maxdd>none|[-0-9.]+)_"
        r"levsma(?P<levsma>none|\d+)_levmaxv(?P<levmaxv>none|[-0-9.]+)_"
        r"levdd(?P<levdd>\d+)_levmaxdd(?P<levmaxdd>none|[-0-9.]+)_"
        r"on(?P<on>[A-Z]+)(?P<onw>[-0-9.]+)_"
        r"neu(?P<neu>[A-Z]+)(?P<neuw>[-0-9.]+)_"
        r"off(?P<off>[A-Z]+)(?P<offw>[-0-9.]+)_"
        r"vt(?P<vt>none|[-0-9.]+)$"
    )
    match = pattern.match(label)
    if match is None:
        raise ValueError(f"unsupported beta route label: {label}")
    return BetaRouterParams(
        trend_sma_days=int(match.group("sma")),
        momentum_lookback_days=int(match.group("mom")),
        min_momentum_pct=float(match.group("min")),
        volatility_lookback_days=int(match.group("vol")),
        max_volatility_annual_pct=parse_optional_float(match.group("maxv")),
        drawdown_lookback_days=int(match.group("dd")),
        max_drawdown_pct=parse_optional_float(match.group("maxdd")),
        leverage_trend_sma_days=parse_optional_int(match.group("levsma")),
        max_leverage_volatility_annual_pct=parse_optional_float(match.group("levmaxv")),
        leverage_drawdown_lookback_days=int(match.group("levdd")),
        max_leverage_drawdown_pct=parse_optional_float(match.group("levmaxdd")),
        risk_on_symbol=match.group("on"),
        risk_on_weight=float(match.group("onw")),
        neutral_symbol=match.group("neu"),
        neutral_weight=float(match.group("neuw")),
        risk_off_symbol=match.group("off"),
        risk_off_weight=float(match.group("offw")),
        target_volatility_annual_pct=parse_optional_float(match.group("vt")),
    )


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
):
    params_grid = _build_params_grid(
        market_symbol=market_symbol.upper(),
        leverage_symbol=leverage_symbol.upper(),
        trend_sma_days=trend_sma_days or [20, 50, 100],
        momentum_lookback_days=momentum_lookback_days or [20, 60],
        min_momentum_pct=min_momentum_pct or [0.0],
        volatility_lookback_days=volatility_lookback_days or [20],
        max_volatility_annual_pct=max_volatility_annual_pct or [None],
        drawdown_lookback_days=drawdown_lookback_days or [60],
        max_drawdown_pct=max_drawdown_pct or [None],
        leverage_trend_sma_days=leverage_trend_sma_days or [None],
        max_leverage_volatility_annual_pct=max_leverage_volatility_annual_pct or [None],
        leverage_drawdown_lookback_days=leverage_drawdown_lookback_days or [60],
        max_leverage_drawdown_pct=max_leverage_drawdown_pct or [None],
        risk_on_symbol=[item.upper() for item in (risk_on_symbol or [leverage_symbol])],
        risk_on_weight=risk_on_weight or [0.5],
        neutral_weight=neutral_weight or [0.5],
        risk_off_symbol=[item.upper() for item in (risk_off_symbol or ["CASH"])],
        risk_off_weight=risk_off_weight or [0.0],
        target_volatility_annual_pct=target_volatility_annual_pct or [None],
        max_candidates=max_candidates,
    )
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="beta_exposure_router",
        report_suffix="beta-exposure-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: load_beta_router_dataset(
            root=base,
            market_symbol=market_symbol,
            leverage_symbol=leverage_symbol,
            hedge_symbol=hedge_symbol,
            timeframe=spec.timeframe,
            data_source=data_source,
            feed=feed or spec.data.feed,
            start=start,
            end=end,
            refresh_data=refresh_data,
        ),
        snapshot=lambda _spec, dataset, params, index: beta_target_weight_snapshot(
            dataset, params, index
        ),
        objective="risk_managed_beta_alpha_vs_qqq_buy_hold",
        filters=["index-1 QQQ trend and momentum", "cash modeled at 0% return"],
        out_of_sample_ratio=out_of_sample_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
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
    fetcher=None,
) -> BetaRouterDataset:
    symbols = [market_symbol.upper(), leverage_symbol.upper()]
    if hedge_symbol:
        symbols.append(hedge_symbol.upper())
    base = load_daily_dataset(
        spec=_synthetic_spec(timeframe=timeframe, data_source=data_source, feed=feed),
        root=root,
        symbols=symbols,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol=market_symbol,
        benchmark_symbol=leverage_symbol,
        refresh_data=refresh_data,
        min_sessions=30,
        fetcher=fetcher or fetch_ohlcv,
    )
    return BetaRouterDataset(
        symbols=base.symbols,
        market_symbol=base.market_symbol,
        benchmark_symbol=base.benchmark_symbol,
        dates=base.dates,
        frame=base.frame,
        data_profile=base.data_profile,
        leverage_symbol=leverage_symbol.upper(),
        hedge_symbol=hedge_symbol.upper() if hedge_symbol else None,
    )


def beta_target_weight_snapshot(
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    index: int,
) -> TargetSnapshot:
    market_trend_ok = trend_ok(dataset, dataset.market_symbol, index, params.trend_sma_days)
    market_momentum_ok = momentum_ok(
        dataset,
        dataset.market_symbol,
        index,
        params.momentum_lookback_days,
        params.min_momentum_pct,
    )
    market_vol_ok = max_volatility_ok(
        dataset,
        dataset.market_symbol,
        index,
        params.volatility_lookback_days,
        params.max_volatility_annual_pct,
    )
    market_dd_scale = drawdown_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.drawdown_lookback_days,
        max_drawdown=params.max_drawdown_pct,
        brake_scale=0.0,
    )
    leverage_trend_ok = (
        True
        if params.leverage_trend_sma_days is None
        else trend_ok(dataset, params.risk_on_symbol, index, params.leverage_trend_sma_days)
    )
    leverage_vol_ok = max_volatility_ok(
        dataset,
        params.risk_on_symbol,
        index,
        params.volatility_lookback_days,
        params.max_leverage_volatility_annual_pct,
    )
    leverage_dd_ok = (
        drawdown_scale(
            dataset,
            params.risk_on_symbol,
            index,
            lookback=params.leverage_drawdown_lookback_days,
            max_drawdown=params.max_leverage_drawdown_pct,
            brake_scale=0.0,
        )
        > 0
    )
    risk_on = (
        market_trend_ok
        and market_momentum_ok
        and market_vol_ok
        and market_dd_scale > 0
        and leverage_trend_ok
        and leverage_vol_ok
        and leverage_dd_ok
    )
    if risk_on:
        state = "risk_on"
        weights = {params.risk_on_symbol: params.risk_on_weight}
    elif market_trend_ok and market_dd_scale > 0:
        state = "neutral"
        weights = {params.neutral_symbol: params.neutral_weight}
    else:
        state = "risk_off"
        weights = (
            {}
            if params.risk_off_symbol == "CASH" or params.risk_off_weight <= 0
            else {params.risk_off_symbol: params.risk_off_weight}
        )
    scale = volatility_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.volatility_lookback_days,
        target_pct=params.target_volatility_annual_pct,
    )
    weights = {symbol: weight * scale for symbol, weight in weights.items() if weight * scale > 0}
    return TargetSnapshot(
        selected=list(weights),
        weights=weights,
        volatility_scale=scale,
        market_regime_scale=1.0 if market_trend_ok and market_momentum_ok else 0.0,
        market_drawdown_scale=market_dd_scale,
        state=state,
        qqq_trend_ok=market_trend_ok,
        qqq_momentum_ok=market_momentum_ok,
        qqq_drawdown_ok=market_dd_scale > 0,
        leverage_trend_ok=leverage_trend_ok,
        leverage_volatility_ok=leverage_vol_ok,
        leverage_drawdown_ok=leverage_dd_ok,
    )


def backtest_beta_router_params(
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    *,
    start_index: int,
    end_index: int,
) -> BetaRouterMetrics:
    metrics = backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=lambda _spec, data, route, index: beta_target_weight_snapshot(data, route, index),
        start_index=start_index,
        end_index=end_index,
    )
    exposed_days = metrics.traded_days
    object.__setattr__(metrics, "risk_on_days", exposed_days)  # type: ignore[attr-defined]
    object.__setattr__(metrics, "neutral_days", 0)  # type: ignore[attr-defined]
    object.__setattr__(metrics, "risk_off_days", max(0, metrics.days - exposed_days))  # type: ignore[attr-defined]
    return metrics


def _effective_lookback(params: BetaRouterParams) -> int:
    return effective_lookback(params)


def _build_params_grid(
    *,
    market_symbol: str,
    leverage_symbol: str,
    trend_sma_days: list[int],
    momentum_lookback_days: list[int],
    min_momentum_pct: list[float],
    volatility_lookback_days: list[int],
    max_volatility_annual_pct: list[float | None],
    drawdown_lookback_days: list[int],
    max_drawdown_pct: list[float | None],
    leverage_trend_sma_days: list[int | None],
    max_leverage_volatility_annual_pct: list[float | None],
    leverage_drawdown_lookback_days: list[int],
    max_leverage_drawdown_pct: list[float | None],
    risk_on_symbol: list[str],
    risk_on_weight: list[float],
    neutral_weight: list[float],
    risk_off_symbol: list[str],
    risk_off_weight: list[float],
    target_volatility_annual_pct: list[float | None],
    max_candidates: int,
) -> list[BetaRouterParams]:
    rows: list[BetaRouterParams] = []
    for (
        trend,
        momentum,
        min_mom,
        vol,
        max_vol,
        dd,
        max_dd,
        lev_sma,
        lev_max_vol,
        lev_dd,
        lev_max_dd,
        on_symbol,
        on_weight,
        neutral,
        off_symbol,
        off_weight,
        target_vol,
    ) in product(
        trend_sma_days,
        momentum_lookback_days,
        min_momentum_pct,
        volatility_lookback_days,
        max_volatility_annual_pct,
        drawdown_lookback_days,
        max_drawdown_pct,
        leverage_trend_sma_days,
        max_leverage_volatility_annual_pct,
        leverage_drawdown_lookback_days,
        max_leverage_drawdown_pct,
        risk_on_symbol,
        risk_on_weight,
        neutral_weight,
        risk_off_symbol,
        risk_off_weight,
        target_volatility_annual_pct,
    ):
        if off_symbol != "CASH" and off_weight <= 0:
            continue
        rows.append(
            BetaRouterParams(
                trend,
                momentum,
                min_mom,
                vol,
                max_vol,
                dd,
                max_dd,
                lev_sma,
                lev_max_vol,
                lev_dd,
                lev_max_dd,
                on_symbol,
                on_weight,
                market_symbol,
                neutral,
                off_symbol,
                off_weight,
                target_vol,
            )
        )
    if len(rows) > max_candidates:
        raise ValueError(f"beta router grid would create {len(rows)} candidates")
    return rows


def _synthetic_spec(*, timeframe: str, data_source: str, feed: str | None) -> StrategySpec:
    return SimpleNamespace(timeframe=timeframe, data=SimpleNamespace(source=data_source, feed=feed))  # type: ignore[return-value]
