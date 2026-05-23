from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Literal

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research import intraday_daily_rotation as _intraday
from open_composer.research.router_common import (
    RouterFrameDataset,
    RouterMetrics,
    TargetSnapshot,
    backtest_router_params,
    drawdown_scale,
    effective_lookback,
    load_daily_dataset,
    market_sma_scale,
    run_router_research,
    selected_by_momentum,
    volatility_scale,
)

HybridObjective = Literal["benchmark_buy_hold_alpha", "risk_adjusted_benchmark_alpha"]
HoldingMode = Literal["open_to_open", "open_to_close"]
MomentumScoreMode = Literal["raw", "risk_adjusted"]


@dataclass(frozen=True)
class HybridRouterParams:
    holding_mode: HoldingMode
    momentum_lookback_days: int
    top_n: int
    market_sma_days: int | None
    min_momentum_pct: float
    max_position_weight: float
    gross_exposure_limit: float = 1.0
    momentum_score_mode: MomentumScoreMode = "raw"
    risk_adjustment_lookback_days: int | None = None
    market_below_sma_scale: float = 0.0
    volatility_lookback_days: int | None = None
    target_volatility_annual_pct: float | None = None
    market_drawdown_lookback_days: int | None = None
    market_drawdown_brake_pct: float | None = None
    brake_exposure_scale: float = 1.0

    @property
    def label(self) -> str:
        gate = "nogate" if self.market_sma_days is None else f"qsm{self.market_sma_days}"
        label = (
            f"{self.holding_mode}:lb{self.momentum_lookback_days}_top{self.top_n}_"
            f"{gate}_min{self.min_momentum_pct:g}_w{self.max_position_weight:g}"
        )
        if self.gross_exposure_limit < 0.999999:
            label += f"_g{self.gross_exposure_limit:g}"
        if self.momentum_score_mode != "raw":
            label += "_scoreradj"
        if self.risk_adjustment_lookback_days:
            label += f"_radj{self.risk_adjustment_lookback_days}"
        if self.market_sma_days is not None and self.market_below_sma_scale > 0:
            label += f"_qoff{self.market_below_sma_scale:g}"
        if self.volatility_lookback_days and self.target_volatility_annual_pct:
            label += f"_vol{self.volatility_lookback_days}t{self.target_volatility_annual_pct:g}"
        if self.market_drawdown_lookback_days and self.market_drawdown_brake_pct:
            label += (
                f"_mdd{self.market_drawdown_lookback_days}"
                f"p{self.market_drawdown_brake_pct:g}"
                f"s{self.brake_exposure_scale:g}"
            )
        return label


HybridRouterMetrics = RouterMetrics
_DailyHybridDataset = RouterFrameDataset


def hybrid_params_from_label(label: str) -> HybridRouterParams:
    try:
        holding_mode, remainder = label.split(":", 1)
        parts = remainder.split("_")
        lookback = int(parts[0].removeprefix("lb"))
        top_n = int(parts[1].removeprefix("top"))
        gate = parts[2]
        market_sma = None if gate == "nogate" else int(gate.removeprefix("qsm"))
        min_momentum = float(parts[3].removeprefix("min"))
        weight = float(parts[4].removeprefix("w"))
        gross = 1.0
        score_mode: MomentumScoreMode = "raw"
        risk_adjustment_lookback: int | None = None
        market_below_sma_scale = 0.0
        vol_lookback: int | None = None
        target_vol: float | None = None
        drawdown_lookback: int | None = None
        drawdown_brake: float | None = None
        brake_scale = 1.0
        for token in parts[5:]:
            if token.startswith("g"):
                gross = float(token.removeprefix("g"))
            elif token.startswith("score"):
                value = token.removeprefix("score")
                score_mode = "risk_adjusted" if value == "radj" else value  # type: ignore[assignment]
            elif token.startswith("radj"):
                risk_adjustment_lookback = int(token.removeprefix("radj"))
            elif token.startswith("qoff"):
                market_below_sma_scale = float(token.removeprefix("qoff"))
            elif token.startswith("vol"):
                match = re.fullmatch(r"vol(?P<lookback>\d+)t(?P<target>[0-9.]+)", token)
                if match is None:
                    raise ValueError
                vol_lookback = int(match.group("lookback"))
                target_vol = float(match.group("target"))
            elif token.startswith("mdd"):
                match = re.fullmatch(
                    r"mdd(?P<lookback>\d+)p(?P<brake>[0-9.]+)s(?P<scale>[0-9.]+)",
                    token,
                )
                if match is None:
                    raise ValueError
                drawdown_lookback = int(match.group("lookback"))
                drawdown_brake = float(match.group("brake"))
                brake_scale = float(match.group("scale"))
            else:
                raise ValueError
    except (IndexError, ValueError) as exc:
        raise ValueError(f"unsupported hybrid route label: {label}") from exc
    if holding_mode not in {"open_to_open", "open_to_close"}:
        raise ValueError(f"unsupported hybrid holding mode in label: {label}")
    return HybridRouterParams(
        holding_mode=holding_mode,  # type: ignore[arg-type]
        momentum_lookback_days=lookback,
        top_n=top_n,
        market_sma_days=market_sma,
        min_momentum_pct=min_momentum,
        max_position_weight=weight,
        gross_exposure_limit=gross,
        momentum_score_mode=score_mode,
        risk_adjustment_lookback_days=risk_adjustment_lookback,
        market_below_sma_scale=market_below_sma_scale,
        volatility_lookback_days=vol_lookback,
        target_volatility_annual_pct=target_vol,
        market_drawdown_lookback_days=drawdown_lookback,
        market_drawdown_brake_pct=drawdown_brake,
        brake_exposure_scale=brake_scale,
    )


def run_hybrid_adaptive_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    holding_modes: list[HoldingMode] | None = None,
    momentum_lookback_days: list[int] | None = None,
    top_n_values: list[int] | None = None,
    market_sma_days: list[int | None] | None = None,
    min_momentum_pct: list[float] | None = None,
    max_position_weight: list[float] | None = None,
    gross_exposure_limit: list[float] | None = None,
    momentum_score_mode: list[MomentumScoreMode] | None = None,
    risk_adjustment_lookback_days: list[int | None] | None = None,
    market_below_sma_scale: list[float] | None = None,
    volatility_lookback_days: list[int | None] | None = None,
    target_volatility_annual_pct: list[float | None] | None = None,
    market_drawdown_lookback_days: list[int | None] | None = None,
    market_drawdown_brake_pct: list[float | None] | None = None,
    brake_exposure_scale: list[float] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    walk_forward_top_k: int | None = 20,
    max_candidates: int = 240,
    refresh_data: bool = False,
    objective: HybridObjective = "benchmark_buy_hold_alpha",
):
    from open_composer.models.strategy_spec import load_strategy_spec

    preview_spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or preview_spec.universe)]
    params_grid = _build_hybrid_params_grid(
        holding_modes=holding_modes or ["open_to_open", "open_to_close"],
        momentum_lookback_days=momentum_lookback_days or [10, 20, 40],
        top_n_values=top_n_values or [1, 2],
        market_sma_days=market_sma_days or [None, 20, 50],
        min_momentum_pct=min_momentum_pct or [0.0],
        max_position_weight=max_position_weight or [preview_spec.risk.max_position_weight],
        gross_exposure_limit=gross_exposure_limit
        or [preview_spec.portfolio.gross_exposure_limit or 1.0],
        momentum_score_mode=momentum_score_mode or ["raw"],
        risk_adjustment_lookback_days=risk_adjustment_lookback_days or [None],
        market_below_sma_scale=market_below_sma_scale or [0.0],
        volatility_lookback_days=volatility_lookback_days or [None],
        target_volatility_annual_pct=target_volatility_annual_pct or [None],
        market_drawdown_lookback_days=market_drawdown_lookback_days or [None],
        market_drawdown_brake_pct=market_drawdown_brake_pct or [None],
        brake_exposure_scale=brake_exposure_scale or [1.0],
        max_candidates=max_candidates,
    )
    return run_router_research(
        spec_path=spec_path,
        root=root,
        mode="hybrid_adaptive_router",
        report_suffix="hybrid-adaptive-router",
        params_grid=params_grid,
        load_dataset=lambda spec, base: _load_daily_hybrid_dataset(
            spec=spec,
            root=base,
            symbols=universe,
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol,
            market_symbol=market_symbol,
            refresh_data=refresh_data,
        ),
        snapshot=hybrid_target_weight_snapshot,
        objective=objective,
        filters=[
            "signal uses previous confirmed close",
            "fill uses next regular-session open",
            "commission and slippage applied on each entry and exit",
        ],
        out_of_sample_ratio=out_of_sample_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
    )


def _build_hybrid_params_grid(
    *,
    holding_modes: list[HoldingMode],
    momentum_lookback_days: list[int],
    top_n_values: list[int],
    market_sma_days: list[int | None],
    min_momentum_pct: list[float],
    max_position_weight: list[float],
    gross_exposure_limit: list[float],
    momentum_score_mode: list[MomentumScoreMode],
    risk_adjustment_lookback_days: list[int | None],
    market_below_sma_scale: list[float],
    volatility_lookback_days: list[int | None],
    target_volatility_annual_pct: list[float | None],
    market_drawdown_lookback_days: list[int | None],
    market_drawdown_brake_pct: list[float | None],
    brake_exposure_scale: list[float],
    max_candidates: int,
) -> list[HybridRouterParams]:
    rows = [
        HybridRouterParams(*values)
        for values in product(
            holding_modes,
            momentum_lookback_days,
            top_n_values,
            market_sma_days,
            min_momentum_pct,
            max_position_weight,
            gross_exposure_limit,
            momentum_score_mode,
            risk_adjustment_lookback_days,
            market_below_sma_scale,
            volatility_lookback_days,
            target_volatility_annual_pct,
            market_drawdown_lookback_days,
            market_drawdown_brake_pct,
            brake_exposure_scale,
        )
    ]
    if len(rows) > max_candidates:
        raise ValueError(f"hybrid grid would create {len(rows)} candidates")
    return rows


def _load_daily_hybrid_dataset(
    *,
    spec: StrategySpec,
    root: Path,
    symbols: list[str],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    benchmark_symbol: str,
    market_symbol: str,
    refresh_data: bool,
) -> _DailyHybridDataset:
    return load_daily_dataset(
        spec=spec,
        root=root,
        symbols=[item.upper() for item in symbols],
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol=market_symbol,
        benchmark_symbol=benchmark_symbol,
        refresh_data=refresh_data,
        min_sessions=30,
        fetcher=_intraday.fetch_ohlcv,
    )


def hybrid_target_weight_snapshot(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    index: int,
) -> TargetSnapshot:
    max_symbol_weight = min(
        params.max_position_weight,
        spec.portfolio.max_symbol_weight or spec.risk.max_position_weight,
        spec.risk.max_position_weight,
    )
    gross_limit = min(params.gross_exposure_limit, spec.portfolio.gross_exposure_limit or 1.0)
    if max_symbol_weight <= 0 or gross_limit <= 0:
        return TargetSnapshot([], {}, 0.0, 0.0, 0.0)
    effective_top_n = min(params.top_n, spec.portfolio.max_symbols_per_day or params.top_n)
    selected = _hybrid_selected_symbols(dataset, index, params, effective_top_n)
    regime_scale = _market_regime_exposure_scale(dataset, params, index)
    vol_scale = volatility_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.volatility_lookback_days,
        target_pct=params.target_volatility_annual_pct,
    )
    mdd_scale = drawdown_scale(
        dataset,
        dataset.market_symbol,
        index,
        lookback=params.market_drawdown_lookback_days,
        max_drawdown=params.market_drawdown_brake_pct,
        brake_scale=params.brake_exposure_scale,
    )
    effective_gross = gross_limit * regime_scale * vol_scale * mdd_scale
    if not selected or effective_gross <= 0:
        return TargetSnapshot([], {}, vol_scale, regime_scale, mdd_scale)
    per_symbol = min(max_symbol_weight, effective_gross / len(selected))
    weights = {symbol: per_symbol for symbol in selected if per_symbol > 0}
    return TargetSnapshot(list(weights), weights, vol_scale, regime_scale, mdd_scale)


def _hybrid_selected_symbols(
    dataset: _DailyHybridDataset,
    index: int,
    params: HybridRouterParams,
    top_n: int,
) -> list[str]:
    if params.market_sma_days is not None and params.market_below_sma_scale <= 0:
        if _market_regime_exposure_scale(dataset, params, index) <= 0:
            return []
    return selected_by_momentum(
        dataset,
        index,
        lookback=params.momentum_lookback_days,
        top_n=top_n,
        min_momentum_pct=params.min_momentum_pct,
        score_mode=params.momentum_score_mode,
        risk_adjustment_lookback=params.risk_adjustment_lookback_days,
    )


def _market_regime_exposure_scale(
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    index: int,
) -> float:
    return market_sma_scale(dataset, params, index)


def _backtest_hybrid_params(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> HybridRouterMetrics:
    return backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
        start_equity=start_equity,
    )


def _effective_lookback(params: HybridRouterParams) -> int:
    return effective_lookback(params)
