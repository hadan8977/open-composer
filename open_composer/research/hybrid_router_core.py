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
    active_membership_symbols,
    backtest_router_params,
    close_series,
    close_value,
    drawdown_scale,
    effective_lookback,
    load_daily_dataset,
    market_sma_scale,
    rolling_close_max,
    rolling_close_mean,
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


@dataclass(frozen=True)
class BetaOverrideHybridParams:
    holding_mode: HoldingMode
    momentum_lookback_days: int
    min_momentum_pct: float
    override_advantage_pct: float
    confirmation_sma_days: int | None
    exclude_tqqq: bool
    trend_sma_days: int = 250
    beta_momentum_lookback_days: int = 120
    leverage_trend_sma_days: int = 50
    leverage_drawdown_lookback_days: int = 60
    max_leverage_drawdown_pct: float = 20.0
    risk_on_weight: float = 1.0
    neutral_weight: float = 0.75
    cycle_gate: str = "none"
    symbol_drawdown_lookback_days: int | None = None
    max_symbol_drawdown_pct: float | None = None
    market_drawdown_lookback_days: int | None = None
    max_market_drawdown_pct: float | None = None
    volatility_lookback_days: int | None = None
    target_volatility_annual_pct: float | None = None
    gross_exposure_scale: float = 1.0
    base_mode: Literal["iter2", "tqqq_cycle", "tqqq_always"] = "iter2"

    @property
    def label(self) -> str:
        sma = "none" if self.confirmation_sma_days is None else str(self.confirmation_sma_days)
        suffix = "_exTQQQ" if self.exclude_tqqq else ""
        gate = "" if self.cycle_gate == "none" else f"_gate{self.cycle_gate}"
        label = (
            "beta_override:"
            f"baseiter2_lb{self.momentum_lookback_days}_min{self.min_momentum_pct:g}_"
            f"adv{self.override_advantage_pct:g}_sma{sma}{suffix}{gate}"
        )
        if self.symbol_drawdown_lookback_days and self.max_symbol_drawdown_pct is not None:
            label += f"_sdd{self.symbol_drawdown_lookback_days}p{self.max_symbol_drawdown_pct:g}"
        if self.market_drawdown_lookback_days and self.max_market_drawdown_pct is not None:
            label += f"_mdd{self.market_drawdown_lookback_days}p{self.max_market_drawdown_pct:g}"
        if self.volatility_lookback_days and self.target_volatility_annual_pct is not None:
            label += f"_vol{self.volatility_lookback_days}t{self.target_volatility_annual_pct:g}"
        if self.gross_exposure_scale < 0.999999:
            label += f"_g{self.gross_exposure_scale:g}"
        if self.base_mode != "iter2":
            label += f"_{self.base_mode}"
        return label


HybridRouterMetrics = RouterMetrics
_DailyHybridDataset = RouterFrameDataset


def hybrid_params_from_label(label: str) -> HybridRouterParams | BetaOverrideHybridParams:
    if label.startswith("beta_override:"):
        match = re.fullmatch(
            r"beta_override:baseiter2_lb(?P<lb>\d+)_min(?P<min>[-0-9.]+)_"
            r"adv(?P<adv>[-0-9.]+)_sma(?P<sma>none|\d+)(?P<ex>_exTQQQ)?"
            r"(?:_gate(?P<gate>[A-Za-z0-9]+))?"
            r"(?:_sdd(?P<sdd_lb>\d+)p(?P<sdd>[-0-9.]+))?"
            r"(?:_mdd(?P<mdd_lb>\d+)p(?P<mdd>[-0-9.]+))?"
            r"(?:_vol(?P<vol_lb>\d+)t(?P<vol>[-0-9.]+))?"
            r"(?:_g(?P<gross>[-0-9.]+))?"
            r"(?:_(?P<base>tqqq_cycle|tqqq_always|iter2))?",
            label,
        )
        if match is None:
            raise ValueError(f"unsupported beta override hybrid route label: {label}")
        sma_raw = match.group("sma")
        return BetaOverrideHybridParams(
            holding_mode="open_to_open",
            momentum_lookback_days=int(match.group("lb")),
            min_momentum_pct=float(match.group("min")),
            override_advantage_pct=float(match.group("adv")),
            confirmation_sma_days=None if sma_raw == "none" else int(sma_raw),
            exclude_tqqq=bool(match.group("ex")),
            cycle_gate=match.group("gate") or "none",
            symbol_drawdown_lookback_days=(
                int(match.group("sdd_lb")) if match.group("sdd_lb") else None
            ),
            max_symbol_drawdown_pct=float(match.group("sdd")) if match.group("sdd") else None,
            market_drawdown_lookback_days=(
                int(match.group("mdd_lb")) if match.group("mdd_lb") else None
            ),
            max_market_drawdown_pct=float(match.group("mdd")) if match.group("mdd") else None,
            volatility_lookback_days=(
                int(match.group("vol_lb")) if match.group("vol_lb") else None
            ),
            target_volatility_annual_pct=(
                float(match.group("vol")) if match.group("vol") else None
            ),
            gross_exposure_scale=float(match.group("gross") or 1.0),
            base_mode=match.group("base") or "iter2",  # type: ignore[arg-type]
        )
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
    beta_override_base_modes: list[Literal["iter2", "tqqq_cycle", "tqqq_always"]] | None = None,
    beta_override_advantage_pct: list[float] | None = None,
    beta_override_confirmation_sma_days: list[int | None] | None = None,
    beta_override_exclude_tqqq: bool = True,
    beta_override_cycle_gates: list[str] | None = None,
    beta_override_symbol_drawdown_lookback_days: list[int | None] | None = None,
    beta_override_max_symbol_drawdown_pct: list[float | None] | None = None,
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
    if beta_override_base_modes:
        params_grid = _build_beta_override_params_grid(
            momentum_lookback_days=momentum_lookback_days or [20],
            min_momentum_pct=min_momentum_pct or [0.0],
            override_advantage_pct=beta_override_advantage_pct or [0.0],
            confirmation_sma_days=beta_override_confirmation_sma_days or [None],
            exclude_tqqq=beta_override_exclude_tqqq,
            cycle_gates=beta_override_cycle_gates or ["none"],
            symbol_drawdown_lookback_days=(beta_override_symbol_drawdown_lookback_days or [None]),
            max_symbol_drawdown_pct=beta_override_max_symbol_drawdown_pct or [None],
            market_drawdown_lookback_days=market_drawdown_lookback_days or [None],
            max_market_drawdown_pct=market_drawdown_brake_pct or [None],
            volatility_lookback_days=volatility_lookback_days or [None],
            target_volatility_annual_pct=target_volatility_annual_pct or [None],
            gross_exposure_scale=gross_exposure_limit
            or [preview_spec.portfolio.gross_exposure_limit or 1.0],
            base_modes=beta_override_base_modes,
            max_candidates=max_candidates,
        )
    else:
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


def _build_beta_override_params_grid(
    *,
    momentum_lookback_days: list[int],
    min_momentum_pct: list[float],
    override_advantage_pct: list[float],
    confirmation_sma_days: list[int | None],
    exclude_tqqq: bool,
    cycle_gates: list[str],
    symbol_drawdown_lookback_days: list[int | None] | None = None,
    max_symbol_drawdown_pct: list[float | None] | None = None,
    market_drawdown_lookback_days: list[int | None] | None = None,
    max_market_drawdown_pct: list[float | None] | None = None,
    volatility_lookback_days: list[int | None] | None = None,
    target_volatility_annual_pct: list[float | None] | None = None,
    gross_exposure_scale: list[float] | None = None,
    base_modes: list[Literal["iter2", "tqqq_cycle", "tqqq_always"]] | None = None,
    max_candidates: int = 240,
) -> list[BetaOverrideHybridParams]:
    rows = [
        BetaOverrideHybridParams(
            holding_mode="open_to_open",
            momentum_lookback_days=lookback,
            min_momentum_pct=min_momentum,
            override_advantage_pct=advantage,
            confirmation_sma_days=sma,
            exclude_tqqq=exclude_tqqq,
            cycle_gate=cycle_gate,
            symbol_drawdown_lookback_days=symbol_drawdown_lookback,
            max_symbol_drawdown_pct=symbol_drawdown_pct,
            market_drawdown_lookback_days=drawdown_lookback,
            max_market_drawdown_pct=drawdown_pct,
            volatility_lookback_days=vol_lookback,
            target_volatility_annual_pct=target_vol,
            gross_exposure_scale=gross,
            base_mode=base_mode,
        )
        for (
            lookback,
            min_momentum,
            advantage,
            sma,
            cycle_gate,
            symbol_drawdown_lookback,
            symbol_drawdown_pct,
            drawdown_lookback,
            drawdown_pct,
            vol_lookback,
            target_vol,
            gross,
            base_mode,
        ) in product(
            momentum_lookback_days,
            min_momentum_pct,
            override_advantage_pct,
            confirmation_sma_days,
            cycle_gates,
            symbol_drawdown_lookback_days or [None],
            max_symbol_drawdown_pct or [None],
            market_drawdown_lookback_days or [None],
            max_market_drawdown_pct or [None],
            volatility_lookback_days or [None],
            target_volatility_annual_pct or [None],
            gross_exposure_scale or [1.0],
            base_modes or ["iter2"],
        )
    ]
    deduped = list({row.label: row for row in rows}.values())
    if len(deduped) > max_candidates:
        raise ValueError(f"hybrid beta-override grid would create {len(deduped)} candidates")
    return deduped


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
    params: HybridRouterParams | BetaOverrideHybridParams,
    index: int,
) -> TargetSnapshot:
    if isinstance(params, BetaOverrideHybridParams):
        return _beta_override_target_weight_snapshot(dataset, params, index)
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
        dataset.benchmark_symbol,
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


def _beta_override_target_weight_snapshot(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> TargetSnapshot:
    vol_scale = volatility_scale(
        dataset,
        dataset.benchmark_symbol,
        index,
        lookback=params.volatility_lookback_days,
        target_pct=params.target_volatility_annual_pct,
    )
    if not _beta_override_market_drawdown_ok(dataset, params, index):
        return TargetSnapshot(
            selected=[],
            weights={},
            volatility_scale=vol_scale,
            market_drawdown_scale=0.0,
            state="risk_off",
            qqq_drawdown_ok=False,
        )
    base_weights, state = _beta_override_base_weights(dataset, params, index)
    override = _beta_override_symbol(dataset, params, index)
    if override is not None:
        weight = params.risk_on_weight * params.gross_exposure_scale * vol_scale
        return TargetSnapshot(
            selected=[override] if weight > 0 else [],
            weights={override: weight} if weight > 0 else {},
            volatility_scale=vol_scale,
            state="override",
            qqq_trend_ok=True,
            qqq_momentum_ok=True,
            leverage_trend_ok=True,
            leverage_drawdown_ok=True,
        )
    scaled_base = {
        symbol: weight * vol_scale
        for symbol, weight in base_weights.items()
        if weight * vol_scale > 0
    }
    return TargetSnapshot(
        selected=list(scaled_base),
        weights=scaled_base,
        volatility_scale=vol_scale,
        state=state,
        qqq_trend_ok=state in {"risk_on", "neutral"},
        qqq_momentum_ok=state == "risk_on",
        leverage_trend_ok=state == "risk_on",
        leverage_drawdown_ok=state == "risk_on",
    )


def _beta_override_base_weights(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> tuple[dict[str, float], str]:
    if params.base_mode == "iter2":
        weights, state = _iter2_beta_base_weights(dataset, params, index)
        return {
            symbol: weight * params.gross_exposure_scale for symbol, weight in weights.items()
        }, state
    if params.base_mode == "tqqq_always":
        if index < 1:
            return {}, "risk_off"
        return {dataset.benchmark_symbol: params.risk_on_weight * params.gross_exposure_scale}, (
            "risk_on"
        )
    if params.base_mode == "tqqq_cycle":
        if _beta_override_cycle_gate(dataset, "q200ormom120", index):
            return {
                dataset.benchmark_symbol: params.risk_on_weight * params.gross_exposure_scale
            }, ("risk_on")
        return {}, "risk_off"
    raise ValueError(f"unsupported beta override base mode: {params.base_mode}")


def _iter2_beta_base_weights(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> tuple[dict[str, float], str]:
    qqq = dataset.market_symbol
    tqqq = dataset.benchmark_symbol
    if index < max(
        params.trend_sma_days,
        params.beta_momentum_lookback_days + 1,
        params.leverage_trend_sma_days,
        params.leverage_drawdown_lookback_days,
    ):
        return {}, "risk_off"
    tqqq_close = close_series(dataset, tqqq)
    qqq_trend = close_value(dataset, qqq, index - 1) > float(
        rolling_close_mean(dataset, qqq, params.trend_sma_days).iloc[index - 1]
    )
    qqq_prior = close_value(dataset, qqq, index - params.beta_momentum_lookback_days - 1)
    qqq_momentum = (
        qqq_prior > 0 and (close_value(dataset, qqq, index - 1) / qqq_prior - 1) * 100 >= 0
    )
    tqqq_trend = close_value(dataset, tqqq, index - 1) > float(
        rolling_close_mean(dataset, tqqq, params.leverage_trend_sma_days).iloc[index - 1]
    )
    tqqq_peak = float(
        rolling_close_max(dataset, tqqq, params.leverage_drawdown_lookback_days).iloc[index - 1]
    )
    tqqq_current = float(tqqq_close.iloc[index - 1])
    tqqq_drawdown = (tqqq_current / tqqq_peak - 1) * 100
    if (
        qqq_trend
        and qqq_momentum
        and tqqq_trend
        and tqqq_drawdown > -params.max_leverage_drawdown_pct
    ):
        return {tqqq: params.risk_on_weight}, "risk_on"
    if qqq_trend:
        return {qqq: params.neutral_weight}, "neutral"
    return {}, "risk_off"


def _beta_override_symbol(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> str | None:
    if index < params.momentum_lookback_days + 1:
        return None
    if not _beta_override_cycle_gate_passes(dataset, params, index):
        return None
    if not _beta_override_market_drawdown_ok(dataset, params, index):
        return None
    symbols = active_membership_symbols(dataset, index, dataset.symbols)
    scores: list[tuple[float, str]] = []
    for symbol in symbols:
        if params.exclude_tqqq and symbol == dataset.benchmark_symbol:
            continue
        previous = close_value(dataset, symbol, index - params.momentum_lookback_days - 1)
        current = close_value(dataset, symbol, index - 1)
        if previous <= 0:
            continue
        momentum = (current / previous - 1) * 100
        if momentum < params.min_momentum_pct:
            continue
        if params.confirmation_sma_days is not None:
            if index < params.confirmation_sma_days:
                continue
            sma = float(
                rolling_close_mean(dataset, symbol, params.confirmation_sma_days).iloc[index - 1]
            )
            if current <= sma:
                continue
        if not _beta_override_symbol_drawdown_ok(dataset, symbol, params, index):
            continue
        scores.append((momentum, symbol))
    if not scores:
        return None
    scores.sort(reverse=True)
    top_momentum, top_symbol = scores[0]
    tqqq_prior = close_value(
        dataset, dataset.benchmark_symbol, index - params.momentum_lookback_days - 1
    )
    tqqq_current = close_value(dataset, dataset.benchmark_symbol, index - 1)
    tqqq_momentum = (tqqq_current / tqqq_prior - 1) * 100 if tqqq_prior > 0 else -100.0
    if top_momentum < tqqq_momentum + params.override_advantage_pct:
        return None
    return top_symbol


def _beta_override_cycle_gate_passes(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> bool:
    return _beta_override_cycle_gate(dataset, params.cycle_gate, index)


def _beta_override_cycle_gate(
    dataset: _DailyHybridDataset,
    gate: str,
    index: int,
) -> bool:
    if gate == "none":
        return True
    if gate not in {"q200", "mom120", "q200ormom120", "q200andmom120"}:
        raise ValueError(f"unsupported beta override cycle gate: {gate}")
    qqq = dataset.market_symbol
    if index < max(200, 121):
        return False
    current = close_value(dataset, qqq, index - 1)
    sma200 = float(rolling_close_mean(dataset, qqq, 200).iloc[index - 1])
    prior = close_value(dataset, qqq, index - 121)
    momentum120 = current / prior - 1 if prior > 0 else -1.0
    q200 = current > sma200
    mom120 = momentum120 > 0
    if gate == "q200":
        return q200
    if gate == "mom120":
        return mom120
    if gate == "q200ormom120":
        return q200 or mom120
    return q200 and mom120


def _beta_override_market_drawdown_ok(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> bool:
    if not params.market_drawdown_lookback_days or params.max_market_drawdown_pct is None:
        return True
    return _rolling_drawdown_ok(
        dataset,
        dataset.market_symbol,
        index,
        params.market_drawdown_lookback_days,
        params.max_market_drawdown_pct,
    )


def _beta_override_symbol_drawdown_ok(
    dataset: _DailyHybridDataset,
    symbol: str,
    params: BetaOverrideHybridParams,
    index: int,
) -> bool:
    if not params.symbol_drawdown_lookback_days or params.max_symbol_drawdown_pct is None:
        return True
    return _rolling_drawdown_ok(
        dataset,
        symbol,
        index,
        params.symbol_drawdown_lookback_days,
        params.max_symbol_drawdown_pct,
    )


def _rolling_drawdown_ok(
    dataset: _DailyHybridDataset,
    symbol: str,
    index: int,
    lookback: int,
    max_drawdown_pct: float,
) -> bool:
    if index - lookback < 0:
        return False
    peak = float(rolling_close_max(dataset, symbol, lookback).iloc[index - 1])
    current = close_value(dataset, symbol, index - 1)
    if peak <= 0 or current <= 0:
        return False
    drawdown = (current / peak - 1) * 100
    return drawdown > -abs(max_drawdown_pct)


def _backtest_hybrid_params(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams | BetaOverrideHybridParams,
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
