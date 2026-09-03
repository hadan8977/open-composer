from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Literal

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research import intraday_daily_rotation as _intraday
from open_composer.research.defensive_transition_overlay import (
    DefensiveTransitionOverlay,
    defensive_transition_overlay_effective_lookback,
    defensive_transition_overlay_from_label,
    defensive_transition_overlay_target_weight_snapshot,
    is_defensive_transition_overlay_label,
)
from open_composer.research.delayed_entry_overlay import (
    DelayedEntryOverlay,
    delayed_entry_overlay_from_label,
    is_delayed_entry_label,
)
from open_composer.research.post_drawdown_reentry_router import (
    PostDrawdownReentryParams,
    is_post_drawdown_reentry_label,
    post_drawdown_reentry_effective_lookback,
    post_drawdown_reentry_params_from_label,
    post_drawdown_reentry_target_weight_snapshot,
)
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

HybridObjective = Literal[
    "benchmark_buy_hold_alpha",
    "risk_adjusted_benchmark_alpha",
    "absolute_return_risk",
]
HoldingMode = Literal["open_to_open", "open_to_close"]
MomentumScoreMode = Literal["raw", "risk_adjusted"]

LEADERSHIP_BREADTH_SYMBOLS = ("QQQ", "SMH", "SOXX", "XLK", "IGV", "USD")


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
    override_weight_scale: float = 1.0
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
    override_short_momentum_lookback_days: int | None = None
    min_override_short_momentum_pct: float | None = None
    market_drawdown_lookback_days: int | None = None
    max_market_drawdown_pct: float | None = None
    market_drawdown_brake_scale: float = 0.0
    market_reentry_momentum_lookback_days: int | None = None
    min_market_reentry_momentum_pct: float | None = None
    volatility_lookback_days: int | None = None
    target_volatility_annual_pct: float | None = None
    override_target_volatility_annual_pct: float | None = None
    gross_exposure_scale: float = 1.0
    base_mode: Literal["iter2", "tqqq_cycle", "tqqq_always"] = "iter2"
    bear_inverse_symbol: str | None = None
    bear_inverse_lookback_days: int = 60
    bear_inverse_min_momentum_pct: float = 0.0
    bear_inverse_confirmation_sma_days: int | None = 50
    bear_inverse_weight: float = 0.0
    leadership_breadth_lookback_days: int | None = None
    min_leadership_breadth_count: int | None = None
    min_leadership_breadth_momentum_pct: float = 0.0
    leadership_breadth_scale: float = 1.0
    leadership_breadth_symbols: tuple[str, ...] = LEADERSHIP_BREADTH_SYMBOLS

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
        if (
            self.override_short_momentum_lookback_days
            and self.min_override_short_momentum_pct is not None
        ):
            label += (
                f"_osm{self.override_short_momentum_lookback_days}"
                f"p{self.min_override_short_momentum_pct:g}"
            )
        if self.market_drawdown_lookback_days and self.max_market_drawdown_pct is not None:
            label += f"_mdd{self.market_drawdown_lookback_days}p{self.max_market_drawdown_pct:g}"
            if self.market_drawdown_brake_scale > 0:
                label += f"s{self.market_drawdown_brake_scale:g}"
            if (
                self.market_reentry_momentum_lookback_days
                and self.min_market_reentry_momentum_pct is not None
            ):
                label += (
                    f"_mre{self.market_reentry_momentum_lookback_days}"
                    f"p{self.min_market_reentry_momentum_pct:g}"
                )
        if self.volatility_lookback_days and self.target_volatility_annual_pct is not None:
            label += f"_vol{self.volatility_lookback_days}t{self.target_volatility_annual_pct:g}"
        if self.override_target_volatility_annual_pct is not None:
            if self.volatility_lookback_days and self.target_volatility_annual_pct is None:
                label += (
                    f"_ov{self.volatility_lookback_days}"
                    f"t{self.override_target_volatility_annual_pct:g}"
                )
            else:
                label += f"_ovt{self.override_target_volatility_annual_pct:g}"
        if self.gross_exposure_scale < 0.999999:
            label += f"_g{self.gross_exposure_scale:g}"
        if self.override_weight_scale < 0.999999:
            label += f"_ows{self.override_weight_scale:g}"
        if self.bear_inverse_symbol and self.bear_inverse_weight > 0:
            bear_sma = (
                "none"
                if self.bear_inverse_confirmation_sma_days is None
                else str(self.bear_inverse_confirmation_sma_days)
            )
            label += (
                f"_bear{self.bear_inverse_symbol.upper()}"
                f"lb{self.bear_inverse_lookback_days}"
                f"min{self.bear_inverse_min_momentum_pct:g}"
                f"sma{bear_sma}"
                f"w{self.bear_inverse_weight:g}"
            )
        if self.leadership_breadth_lookback_days and self.min_leadership_breadth_count:
            label += (
                f"_br{self.leadership_breadth_lookback_days}"
                f"n{self.min_leadership_breadth_count}"
                f"m{self.min_leadership_breadth_momentum_pct:g}"
                f"s{self.leadership_breadth_scale:g}"
            )
        if self.base_mode != "iter2":
            label += f"_{self.base_mode}"
        return label


@dataclass(frozen=True)
class EquityRiskManagedHybridParams:
    base_label: str
    base_params: HybridRouterParams | BetaOverrideHybridParams
    trigger_drawdown_pct: float
    recovery_drawdown_pct: float
    risk_scale: float
    defensive_symbol: str
    defensive_redeploy: float
    min_throttle_days: int

    @property
    def holding_mode(self) -> HoldingMode:
        return self.base_params.holding_mode

    @property
    def label(self) -> str:
        return (
            "equity_risk_manager:"
            f"trig{self.trigger_drawdown_pct:g}_"
            f"recover{self.recovery_drawdown_pct:g}_"
            f"scale{self.risk_scale:g}_"
            f"def{self.defensive_symbol.upper()}w{self.defensive_redeploy:g}_"
            f"mindays{self.min_throttle_days}"
            f"__base__{self.base_label}"
        )


HybridRouterMetrics = RouterMetrics
_DailyHybridDataset = RouterFrameDataset


def hybrid_params_from_label(
    label: str,
) -> (
    HybridRouterParams
    | BetaOverrideHybridParams
    | EquityRiskManagedHybridParams
    | PostDrawdownReentryParams
    | DefensiveTransitionOverlay
    | DelayedEntryOverlay
):
    if is_defensive_transition_overlay_label(label):
        return defensive_transition_overlay_from_label(label)
    if is_post_drawdown_reentry_label(label):
        return post_drawdown_reentry_params_from_label(label)
    if is_delayed_entry_label(label):
        return delayed_entry_overlay_from_label(label)
    if label.startswith("equity_risk_manager:"):
        try:
            manager_label, base_label = label.split("__base__", 1)
        except ValueError as exc:
            raise ValueError(f"unsupported equity risk manager route label: {label}") from exc
        match = re.fullmatch(
            r"equity_risk_manager:trig(?P<trigger>[-0-9.]+)_"
            r"recover(?P<recover>[-0-9.]+)_"
            r"scale(?P<scale>[-0-9.]+)_"
            r"def(?P<defensive>[A-Z0-9]+)w(?P<redeploy>[-0-9.]+)_"
            r"mindays(?P<mindays>\d+)",
            manager_label,
        )
        if match is None or base_label.startswith("equity_risk_manager:"):
            raise ValueError(f"unsupported equity risk manager route label: {label}")
        base_params = hybrid_params_from_label(base_label)
        if not isinstance(base_params, (HybridRouterParams, BetaOverrideHybridParams)):
            raise ValueError("equity risk manager requires a direct hybrid base route")
        trigger = float(match.group("trigger"))
        recovery = float(match.group("recover"))
        risk_scale = float(match.group("scale"))
        redeploy = float(match.group("redeploy"))
        min_days = int(match.group("mindays"))
        if trigger <= 0 or recovery < 0 or recovery >= trigger:
            raise ValueError("equity risk manager requires 0 <= recovery < trigger")
        if not 0 <= risk_scale <= 1:
            raise ValueError("equity risk manager risk scale must be between 0 and 1")
        if not 0 <= redeploy <= 1:
            raise ValueError("equity risk manager defensive redeploy must be between 0 and 1")
        if min_days < 1:
            raise ValueError("equity risk manager minimum throttle days must be positive")
        return EquityRiskManagedHybridParams(
            base_label=base_label,
            base_params=base_params,
            trigger_drawdown_pct=trigger,
            recovery_drawdown_pct=recovery,
            risk_scale=risk_scale,
            defensive_symbol=match.group("defensive").upper(),
            defensive_redeploy=redeploy,
            min_throttle_days=min_days,
        )
    if label.startswith("beta_override:"):
        match = re.fullmatch(
            r"beta_override:baseiter2_lb(?P<lb>\d+)_min(?P<min>[-0-9.]+)_"
            r"adv(?P<adv>[-0-9.]+)_sma(?P<sma>none|\d+)(?P<ex>_exTQQQ)?"
            r"(?:_gate(?P<gate>[A-Za-z0-9]+))?"
            r"(?:_sdd(?P<sdd_lb>\d+)p(?P<sdd>[-0-9.]+))?"
            r"(?:_osm(?P<osm_lb>\d+)p(?P<osm>[-0-9.]+))?"
            r"(?:_mdd(?P<mdd_lb>\d+)p(?P<mdd>[-0-9.]+)"
            r"(?:s(?P<mdd_scale>[-0-9.]+))?)?"
            r"(?:_mre(?P<mre_lb>\d+)p(?P<mre>[-0-9.]+))?"
            r"(?:_vol(?P<vol_lb>\d+)t(?P<vol>[-0-9.]+))?"
            r"(?:(?:_ov(?P<ov_lb>\d+)t(?P<ovt>[-0-9.]+))|(?:_ovt(?P<legacy_ovt>[-0-9.]+)))?"
            r"(?:_g(?P<gross>[-0-9.]+))?"
            r"(?:_ows(?P<ows>[-0-9.]+))?"
            r"(?P<bear>_bear(?P<bear_symbol>[A-Z0-9]+)lb(?P<bear_lb>\d+)"
            r"min(?P<bear_min>[-0-9.]+)sma(?P<bear_sma>none|\d+)"
            r"w(?P<bear_w>[-0-9.]+))?"
            r"(?:_br(?P<br_lb>\d+)n(?P<br_count>\d+)"
            r"m(?P<br_min>[-0-9.]+)s(?P<br_scale>[-0-9.]+))?"
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
            override_weight_scale=float(match.group("ows") or 1.0),
            cycle_gate=match.group("gate") or "none",
            symbol_drawdown_lookback_days=(
                int(match.group("sdd_lb")) if match.group("sdd_lb") else None
            ),
            max_symbol_drawdown_pct=float(match.group("sdd")) if match.group("sdd") else None,
            override_short_momentum_lookback_days=(
                int(match.group("osm_lb")) if match.group("osm_lb") else None
            ),
            min_override_short_momentum_pct=(
                float(match.group("osm")) if match.group("osm") else None
            ),
            market_drawdown_lookback_days=(
                int(match.group("mdd_lb")) if match.group("mdd_lb") else None
            ),
            max_market_drawdown_pct=float(match.group("mdd")) if match.group("mdd") else None,
            market_drawdown_brake_scale=float(match.group("mdd_scale") or 0.0),
            market_reentry_momentum_lookback_days=(
                int(match.group("mre_lb")) if match.group("mre_lb") else None
            ),
            min_market_reentry_momentum_pct=(
                float(match.group("mre")) if match.group("mre") else None
            ),
            volatility_lookback_days=(
                int(match.group("vol_lb") or match.group("ov_lb"))
                if match.group("vol_lb") or match.group("ov_lb")
                else None
            ),
            target_volatility_annual_pct=(
                float(match.group("vol")) if match.group("vol") else None
            ),
            override_target_volatility_annual_pct=(
                float(match.group("ovt") or match.group("legacy_ovt"))
                if match.group("ovt") or match.group("legacy_ovt")
                else None
            ),
            gross_exposure_scale=float(match.group("gross") or 1.0),
            base_mode=match.group("base") or "iter2",  # type: ignore[arg-type]
            bear_inverse_symbol=match.group("bear_symbol"),
            bear_inverse_lookback_days=(
                int(match.group("bear_lb")) if match.group("bear_lb") else 60
            ),
            bear_inverse_min_momentum_pct=(
                float(match.group("bear_min")) if match.group("bear_min") else 0.0
            ),
            bear_inverse_confirmation_sma_days=(
                None
                if match.group("bear_sma") == "none"
                else int(match.group("bear_sma"))
                if match.group("bear_sma")
                else 50
            ),
            bear_inverse_weight=float(match.group("bear_w") or 0.0),
            leadership_breadth_lookback_days=(
                int(match.group("br_lb")) if match.group("br_lb") else None
            ),
            min_leadership_breadth_count=(
                int(match.group("br_count")) if match.group("br_count") else None
            ),
            min_leadership_breadth_momentum_pct=(
                float(match.group("br_min")) if match.group("br_min") else 0.0
            ),
            leadership_breadth_scale=(
                float(match.group("br_scale")) if match.group("br_scale") else 1.0
            ),
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
    beta_override_weight_scale: list[float] | None = None,
    beta_override_cycle_gates: list[str] | None = None,
    beta_override_symbol_drawdown_lookback_days: list[int | None] | None = None,
    beta_override_max_symbol_drawdown_pct: list[float | None] | None = None,
    beta_override_short_momentum_lookback_days: list[int | None] | None = None,
    beta_override_min_short_momentum_pct: list[float | None] | None = None,
    beta_override_target_volatility_annual_pct: list[float | None] | None = None,
    beta_override_bear_inverse_symbols: list[str | None] | None = None,
    beta_override_bear_inverse_lookback_days: list[int] | None = None,
    beta_override_bear_inverse_min_momentum_pct: list[float] | None = None,
    beta_override_bear_inverse_confirmation_sma_days: list[int | None] | None = None,
    beta_override_bear_inverse_weight: list[float] | None = None,
    beta_override_leadership_breadth_lookback_days: list[int | None] | None = None,
    beta_override_min_leadership_breadth_count: list[int | None] | None = None,
    beta_override_min_leadership_breadth_momentum_pct: list[float] | None = None,
    beta_override_leadership_breadth_scale: list[float] | None = None,
    beta_override_market_reentry_momentum_lookback_days: list[int | None] | None = None,
    beta_override_min_market_reentry_momentum_pct: list[float | None] | None = None,
    beta_override_market_drawdown_brake_scale: list[float] | None = None,
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
            override_weight_scale=beta_override_weight_scale or [1.0],
            cycle_gates=beta_override_cycle_gates or ["none"],
            symbol_drawdown_lookback_days=(beta_override_symbol_drawdown_lookback_days or [None]),
            max_symbol_drawdown_pct=beta_override_max_symbol_drawdown_pct or [None],
            short_momentum_lookback_days=beta_override_short_momentum_lookback_days or [None],
            min_short_momentum_pct=beta_override_min_short_momentum_pct or [None],
            bear_inverse_symbols=beta_override_bear_inverse_symbols or [None],
            bear_inverse_lookback_days=beta_override_bear_inverse_lookback_days or [60],
            bear_inverse_min_momentum_pct=(beta_override_bear_inverse_min_momentum_pct or [0.0]),
            bear_inverse_confirmation_sma_days=(
                beta_override_bear_inverse_confirmation_sma_days or [50]
            ),
            bear_inverse_weight=beta_override_bear_inverse_weight or [0.0],
            leadership_breadth_lookback_days=(
                beta_override_leadership_breadth_lookback_days or [None]
            ),
            min_leadership_breadth_count=(beta_override_min_leadership_breadth_count or [None]),
            min_leadership_breadth_momentum_pct=(
                beta_override_min_leadership_breadth_momentum_pct or [0.0]
            ),
            leadership_breadth_scale=beta_override_leadership_breadth_scale or [1.0],
            market_drawdown_lookback_days=market_drawdown_lookback_days or [None],
            max_market_drawdown_pct=market_drawdown_brake_pct or [None],
            market_drawdown_brake_scale=beta_override_market_drawdown_brake_scale or [0.0],
            market_reentry_momentum_lookback_days=(
                beta_override_market_reentry_momentum_lookback_days or [None]
            ),
            min_market_reentry_momentum_pct=(
                beta_override_min_market_reentry_momentum_pct or [None]
            ),
            volatility_lookback_days=volatility_lookback_days or [None],
            target_volatility_annual_pct=target_volatility_annual_pct or [None],
            override_target_volatility_annual_pct=(
                beta_override_target_volatility_annual_pct or [None]
            ),
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
    override_weight_scale: list[float] | None = None,
    symbol_drawdown_lookback_days: list[int | None] | None = None,
    max_symbol_drawdown_pct: list[float | None] | None = None,
    short_momentum_lookback_days: list[int | None] | None = None,
    min_short_momentum_pct: list[float | None] | None = None,
    bear_inverse_symbols: list[str | None] | None = None,
    bear_inverse_lookback_days: list[int] | None = None,
    bear_inverse_min_momentum_pct: list[float] | None = None,
    bear_inverse_confirmation_sma_days: list[int | None] | None = None,
    bear_inverse_weight: list[float] | None = None,
    leadership_breadth_lookback_days: list[int | None] | None = None,
    min_leadership_breadth_count: list[int | None] | None = None,
    min_leadership_breadth_momentum_pct: list[float] | None = None,
    leadership_breadth_scale: list[float] | None = None,
    market_drawdown_brake_scale: list[float] | None = None,
    market_drawdown_lookback_days: list[int | None] | None = None,
    max_market_drawdown_pct: list[float | None] | None = None,
    market_reentry_momentum_lookback_days: list[int | None] | None = None,
    min_market_reentry_momentum_pct: list[float | None] | None = None,
    volatility_lookback_days: list[int | None] | None = None,
    target_volatility_annual_pct: list[float | None] | None = None,
    override_target_volatility_annual_pct: list[float | None] | None = None,
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
            override_weight_scale=override_scale,
            cycle_gate=cycle_gate,
            symbol_drawdown_lookback_days=symbol_drawdown_lookback,
            max_symbol_drawdown_pct=symbol_drawdown_pct,
            override_short_momentum_lookback_days=short_momentum_lookback,
            min_override_short_momentum_pct=short_momentum_pct,
            bear_inverse_symbol=bear_symbol.upper() if bear_symbol else None,
            bear_inverse_lookback_days=bear_lookback,
            bear_inverse_min_momentum_pct=bear_min_momentum,
            bear_inverse_confirmation_sma_days=bear_sma,
            bear_inverse_weight=bear_weight,
            leadership_breadth_lookback_days=leadership_lookback,
            min_leadership_breadth_count=leadership_count,
            min_leadership_breadth_momentum_pct=leadership_momentum,
            leadership_breadth_scale=leadership_scale,
            market_drawdown_brake_scale=drawdown_scale_value,
            market_drawdown_lookback_days=drawdown_lookback,
            max_market_drawdown_pct=drawdown_pct,
            market_reentry_momentum_lookback_days=reentry_lookback,
            min_market_reentry_momentum_pct=reentry_momentum,
            volatility_lookback_days=vol_lookback,
            target_volatility_annual_pct=target_vol,
            override_target_volatility_annual_pct=override_target_vol,
            gross_exposure_scale=gross,
            base_mode=base_mode,
        )
        for (
            lookback,
            min_momentum,
            advantage,
            sma,
            override_scale,
            cycle_gate,
            symbol_drawdown_lookback,
            symbol_drawdown_pct,
            short_momentum_lookback,
            short_momentum_pct,
            bear_symbol,
            bear_lookback,
            bear_min_momentum,
            bear_sma,
            bear_weight,
            leadership_lookback,
            leadership_count,
            leadership_momentum,
            leadership_scale,
            drawdown_scale_value,
            drawdown_lookback,
            drawdown_pct,
            reentry_lookback,
            reentry_momentum,
            vol_lookback,
            target_vol,
            override_target_vol,
            gross,
            base_mode,
        ) in product(
            momentum_lookback_days,
            min_momentum_pct,
            override_advantage_pct,
            confirmation_sma_days,
            override_weight_scale or [1.0],
            cycle_gates,
            symbol_drawdown_lookback_days or [None],
            max_symbol_drawdown_pct or [None],
            short_momentum_lookback_days or [None],
            min_short_momentum_pct or [None],
            bear_inverse_symbols or [None],
            bear_inverse_lookback_days or [60],
            bear_inverse_min_momentum_pct or [0.0],
            bear_inverse_confirmation_sma_days or [50],
            bear_inverse_weight or [0.0],
            leadership_breadth_lookback_days or [None],
            min_leadership_breadth_count or [None],
            min_leadership_breadth_momentum_pct or [0.0],
            leadership_breadth_scale or [1.0],
            market_drawdown_brake_scale or [0.0],
            market_drawdown_lookback_days or [None],
            max_market_drawdown_pct or [None],
            market_reentry_momentum_lookback_days or [None],
            min_market_reentry_momentum_pct or [None],
            volatility_lookback_days or [None],
            target_volatility_annual_pct or [None],
            override_target_volatility_annual_pct or [None],
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
    params: (
        HybridRouterParams
        | BetaOverrideHybridParams
        | EquityRiskManagedHybridParams
        | PostDrawdownReentryParams
        | DefensiveTransitionOverlay
        | DelayedEntryOverlay
    ),
    index: int,
) -> TargetSnapshot:
    if isinstance(params, DefensiveTransitionOverlay):
        return defensive_transition_overlay_target_weight_snapshot(spec, dataset, params, index)
    if isinstance(params, PostDrawdownReentryParams):
        return post_drawdown_reentry_target_weight_snapshot(spec, dataset, params, index)
    if isinstance(params, DelayedEntryOverlay):
        base_params = hybrid_params_from_label(params.base_route_label)
        return hybrid_target_weight_snapshot(spec, dataset, base_params, index)
    if isinstance(params, EquityRiskManagedHybridParams):
        return _equity_risk_managed_target_weight_snapshot(spec, dataset, params, index)
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


_EQUITY_RISK_ASSETS = {"TQQQ", "QLD", "SOXL", "TECL", "USD", "ROM"}


def _equity_risk_managed_target_weight_snapshot(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: EquityRiskManagedHybridParams,
    index: int,
) -> TargetSnapshot:
    base = hybrid_target_weight_snapshot(spec, dataset, params.base_params, index)
    throttled, _, _ = _equity_risk_manager_state(spec, dataset, params, index)
    weights = dict(base.weights)
    if throttled:
        if params.defensive_symbol not in dataset.symbols:
            raise ValueError(
                "equity risk manager defensive symbol is absent from the dataset: "
                f"{params.defensive_symbol}"
            )
        weights = _apply_equity_risk_manager_weights(weights, params)
    weights = {symbol: weight for symbol, weight in weights.items() if weight > 1e-12}
    gross = sum(abs(weight) for weight in weights.values())
    gross_limit = max(spec.portfolio.gross_exposure_limit or 1.0, 0.0)
    if gross_limit and gross > gross_limit:
        weights = {symbol: weight * gross_limit / gross for symbol, weight in weights.items()}
    return TargetSnapshot(
        selected=list(weights),
        weights=weights,
        volatility_scale=base.volatility_scale,
        market_regime_scale=base.market_regime_scale,
        market_drawdown_scale=base.market_drawdown_scale,
        state="equity_throttle" if throttled else f"equity_pass:{base.state}",
        qqq_trend_ok=base.qqq_trend_ok,
        qqq_momentum_ok=base.qqq_momentum_ok,
        qqq_drawdown_ok=base.qqq_drawdown_ok,
        leverage_trend_ok=base.leverage_trend_ok,
        leverage_volatility_ok=base.leverage_volatility_ok,
        leverage_drawdown_ok=base.leverage_drawdown_ok,
        core_gross=base.core_gross,
        satellite_gross=base.satellite_gross,
        satellite_scale=base.satellite_scale,
        theme_gate_ok=base.theme_gate_ok,
    )


def _apply_equity_risk_manager_weights(
    weights: dict[str, float],
    params: EquityRiskManagedHybridParams,
) -> dict[str, float]:
    managed = dict(weights)
    freed = 0.0
    for symbol, weight in list(managed.items()):
        if symbol.upper() not in _EQUITY_RISK_ASSETS:
            continue
        scaled = weight * params.risk_scale
        freed += abs(weight - scaled)
        managed[symbol] = scaled
    if params.defensive_redeploy > 0 and freed > 0:
        defensive = params.defensive_symbol.upper()
        managed[defensive] = managed.get(defensive, 0.0) + freed * params.defensive_redeploy
    return managed


def _equity_risk_manager_state(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: EquityRiskManagedHybridParams,
    index: int,
) -> tuple[bool, float, int]:
    cache_key = (
        "equity_risk_manager_state",
        params.label,
        spec.costs.commission_pct,
        spec.costs.slippage_bps,
        spec.portfolio.gross_exposure_limit,
    )
    cached = dataset.runtime_cache.get(cache_key)
    if cached is None:
        cached = _build_equity_risk_manager_state_cache(spec, dataset, params)
        dataset.runtime_cache[cache_key] = cached
    if index in cached:
        return cached[index]
    available = [key for key in cached if key <= index]
    if not available:
        return False, 0.0, 0
    return cached[max(available)]


def _build_equity_risk_manager_state_cache(
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: EquityRiskManagedHybridParams,
) -> dict[int, tuple[bool, float, int]]:
    start_index = _effective_lookback(params.base_params) + 1
    end_index = len(dataset.dates) - 1
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    equity = 1.0
    peak = 1.0
    throttled = False
    throttle_days = 0
    previous_weights: dict[str, float] = {}
    states: dict[int, tuple[bool, float, int]] = {}
    for route_index in range(start_index, end_index):
        drawdown_pct = (equity / peak - 1) * 100 if peak > 0 else 0.0
        throttled, throttle_days = _next_equity_throttle_state(
            throttled,
            throttle_days,
            drawdown_pct,
            params,
        )
        states[route_index] = (throttled, drawdown_pct, throttle_days)
        base = hybrid_target_weight_snapshot(spec, dataset, params.base_params, route_index)
        weights = dict(base.weights)
        if throttled:
            if params.defensive_symbol not in dataset.symbols:
                raise ValueError(
                    "equity risk manager defensive symbol is absent from the dataset: "
                    f"{params.defensive_symbol}"
                )
            weights = _apply_equity_risk_manager_weights(weights, params)
            throttle_days += 1
        gross = sum(abs(weight) for weight in weights.values())
        gross_limit = max(spec.portfolio.gross_exposure_limit or 1.0, 0.0)
        if gross_limit and gross > gross_limit:
            weights = {symbol: weight * gross_limit / gross for symbol, weight in weights.items()}
        daily_return = _equity_managed_daily_return(dataset, route_index, weights)
        daily_return -= _weight_turnover(weights, previous_weights) * cost_rate
        equity *= 1 + daily_return
        peak = max(peak, equity)
        previous_weights = weights
    drawdown_pct = (equity / peak - 1) * 100 if peak > 0 else 0.0
    throttled, throttle_days = _next_equity_throttle_state(
        throttled,
        throttle_days,
        drawdown_pct,
        params,
    )
    states[len(dataset.dates)] = (throttled, drawdown_pct, throttle_days)
    return states


def _next_equity_throttle_state(
    throttled: bool,
    throttle_days: int,
    drawdown_pct: float,
    params: EquityRiskManagedHybridParams,
) -> tuple[bool, int]:
    if not throttled and drawdown_pct <= -abs(params.trigger_drawdown_pct):
        return True, 0
    if (
        throttled
        and throttle_days >= params.min_throttle_days
        and drawdown_pct >= -abs(params.recovery_drawdown_pct)
    ):
        return False, throttle_days
    return throttled, throttle_days


def _equity_managed_daily_return(
    dataset: _DailyHybridDataset,
    index: int,
    weights: dict[str, float],
) -> float:
    if index + 1 >= len(dataset.frame):
        return 0.0
    total = 0.0
    for symbol, weight in weights.items():
        open_now = float(dataset.frame[f"{symbol}_open"].iloc[index])
        open_next = float(dataset.frame[f"{symbol}_open"].iloc[index + 1])
        if open_now > 0 and open_next > 0:
            total += weight * (open_next / open_now - 1)
    return total


def _weight_turnover(current: dict[str, float], previous: dict[str, float]) -> float:
    symbols = set(current) | set(previous)
    return sum(abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in symbols)


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
    market_drawdown_scale = _beta_override_market_drawdown_scale(dataset, params, index)
    if market_drawdown_scale <= 0:
        bear_weights = _beta_override_bear_inverse_weights(dataset, params, index)
        if bear_weights:
            scaled_bear = {
                symbol: weight * vol_scale
                for symbol, weight in bear_weights.items()
                if weight * vol_scale > 0
            }
            return TargetSnapshot(
                selected=list(scaled_bear),
                weights=scaled_bear,
                volatility_scale=vol_scale,
                market_drawdown_scale=0.0,
                state="bear_inverse",
                qqq_drawdown_ok=False,
            )
        return TargetSnapshot(
            selected=[],
            weights={},
            volatility_scale=vol_scale,
            market_drawdown_scale=0.0,
            state="risk_off",
            qqq_drawdown_ok=False,
        )
    leadership_scale = _beta_override_leadership_breadth_scale(dataset, params, index)
    if leadership_scale <= 0:
        return TargetSnapshot(
            selected=[],
            weights={},
            volatility_scale=vol_scale,
            market_regime_scale=0.0,
            state="breadth_off",
            theme_gate_ok=False,
        )
    base_weights, state = _beta_override_base_weights(dataset, params, index)
    override = _beta_override_symbol(dataset, params, index)
    if override is not None:
        override_vol_scale = (
            volatility_scale(
                dataset,
                override,
                index,
                lookback=params.volatility_lookback_days,
                target_pct=params.override_target_volatility_annual_pct,
            )
            if params.override_target_volatility_annual_pct is not None
            else vol_scale
        )
        weight = (
            params.risk_on_weight
            * params.gross_exposure_scale
            * params.override_weight_scale
            * leadership_scale
            * market_drawdown_scale
            * override_vol_scale
        )
        return TargetSnapshot(
            selected=[override] if weight > 0 else [],
            weights={override: weight} if weight > 0 else {},
            volatility_scale=override_vol_scale,
            market_regime_scale=leadership_scale,
            market_drawdown_scale=market_drawdown_scale,
            state="override",
            qqq_trend_ok=True,
            qqq_momentum_ok=True,
            qqq_drawdown_ok=market_drawdown_scale >= 1,
            leverage_trend_ok=True,
            leverage_drawdown_ok=True,
        )
    scaled_base = {
        symbol: weight * vol_scale * leadership_scale * market_drawdown_scale
        for symbol, weight in base_weights.items()
        if weight * vol_scale * leadership_scale * market_drawdown_scale > 0
    }
    return TargetSnapshot(
        selected=list(scaled_base),
        weights=scaled_base,
        volatility_scale=vol_scale,
        market_regime_scale=leadership_scale,
        market_drawdown_scale=market_drawdown_scale,
        state=state,
        qqq_trend_ok=state in {"risk_on", "neutral"},
        qqq_momentum_ok=state == "risk_on",
        qqq_drawdown_ok=market_drawdown_scale >= 1,
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
        base_gate = params.cycle_gate if params.cycle_gate != "none" else "q200ormom120"
        if _beta_override_cycle_gate(dataset, base_gate, index):
            return {
                dataset.benchmark_symbol: params.risk_on_weight * params.gross_exposure_scale
            }, ("risk_on")
        bear_weights = _beta_override_bear_inverse_weights(dataset, params, index)
        if bear_weights:
            return bear_weights, "bear_inverse"
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
        if not _beta_override_short_momentum_ok(dataset, symbol, params, index):
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


def _beta_override_bear_inverse_weights(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> dict[str, float]:
    symbol = (params.bear_inverse_symbol or "").upper()
    if not symbol or params.bear_inverse_weight <= 0:
        return {}
    if f"{symbol}_close" not in dataset.frame.columns:
        return {}
    if symbol not in active_membership_symbols(dataset, index, [symbol]):
        return {}
    if index < params.bear_inverse_lookback_days + 1:
        return {}
    previous = close_value(dataset, symbol, index - params.bear_inverse_lookback_days - 1)
    current = close_value(dataset, symbol, index - 1)
    if previous <= 0 or current <= 0:
        return {}
    momentum = (current / previous - 1) * 100
    if momentum < params.bear_inverse_min_momentum_pct:
        return {}
    sma_days = params.bear_inverse_confirmation_sma_days
    if sma_days is not None:
        if index < sma_days:
            return {}
        sma = float(rolling_close_mean(dataset, symbol, sma_days).iloc[index - 1])
        if current <= sma:
            return {}
    weight = params.bear_inverse_weight * params.gross_exposure_scale
    return {symbol: weight} if weight > 0 else {}


def _beta_override_leadership_breadth_scale(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> float:
    lookback = params.leadership_breadth_lookback_days
    min_count = params.min_leadership_breadth_count
    if not lookback or not min_count:
        return 1.0
    if index - lookback - 1 < 0:
        return 0.0
    positive = 0
    valid = 0
    for symbol in params.leadership_breadth_symbols:
        symbol = symbol.upper()
        if f"{symbol}_close" not in dataset.frame.columns:
            continue
        if symbol not in active_membership_symbols(dataset, index, [symbol]):
            continue
        previous = close_value(dataset, symbol, index - lookback - 1)
        current = close_value(dataset, symbol, index - 1)
        if previous <= 0 or current <= 0:
            continue
        valid += 1
        momentum = (current / previous - 1) * 100
        if momentum >= params.min_leadership_breadth_momentum_pct:
            positive += 1
    if valid < min_count:
        return max(0.0, min(1.0, params.leadership_breadth_scale))
    return 1.0 if positive >= min_count else max(0.0, min(1.0, params.leadership_breadth_scale))


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
    if _rolling_drawdown_ok(
        dataset,
        dataset.market_symbol,
        index,
        params.market_drawdown_lookback_days,
        params.max_market_drawdown_pct,
    ):
        return True
    return _beta_override_market_reentry_ok(dataset, params, index)


def _beta_override_market_reentry_ok(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> bool:
    lookback = params.market_reentry_momentum_lookback_days
    min_momentum = params.min_market_reentry_momentum_pct
    if not lookback or min_momentum is None or index - lookback - 1 < 0:
        return False
    previous = close_value(dataset, dataset.market_symbol, index - lookback - 1)
    current = close_value(dataset, dataset.market_symbol, index - 1)
    if previous <= 0 or current <= 0:
        return False
    momentum = (current / previous - 1) * 100
    return momentum >= min_momentum


def _beta_override_market_drawdown_scale(
    dataset: _DailyHybridDataset,
    params: BetaOverrideHybridParams,
    index: int,
) -> float:
    if _beta_override_market_drawdown_ok(dataset, params, index):
        return 1.0
    return max(0.0, min(1.0, params.market_drawdown_brake_scale))


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


def _beta_override_short_momentum_ok(
    dataset: _DailyHybridDataset,
    symbol: str,
    params: BetaOverrideHybridParams,
    index: int,
) -> bool:
    lookback = params.override_short_momentum_lookback_days
    min_momentum = params.min_override_short_momentum_pct
    if not lookback or min_momentum is None:
        return True
    if index - lookback - 1 < 0:
        return False
    previous = close_value(dataset, symbol, index - lookback - 1)
    current = close_value(dataset, symbol, index - 1)
    if previous <= 0 or current <= 0:
        return False
    momentum = (current / previous - 1) * 100
    return momentum >= min_momentum


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
    params: (
        HybridRouterParams
        | BetaOverrideHybridParams
        | EquityRiskManagedHybridParams
        | PostDrawdownReentryParams
        | DefensiveTransitionOverlay
        | DelayedEntryOverlay
    ),
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
    capture_returns: bool = False,
) -> HybridRouterMetrics:
    return backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
        start_equity=start_equity,
        capture_returns=capture_returns,
    )


def _effective_lookback(
    params: (
        HybridRouterParams
        | BetaOverrideHybridParams
        | EquityRiskManagedHybridParams
        | PostDrawdownReentryParams
        | DefensiveTransitionOverlay
        | DelayedEntryOverlay
    ),
) -> int:
    if isinstance(params, DefensiveTransitionOverlay):
        return defensive_transition_overlay_effective_lookback(params)
    if isinstance(params, PostDrawdownReentryParams):
        return post_drawdown_reentry_effective_lookback(params)
    if isinstance(params, DelayedEntryOverlay):
        return _effective_lookback(hybrid_params_from_label(params.base_route_label))
    if isinstance(params, EquityRiskManagedHybridParams):
        return _effective_lookback(params.base_params)
    return effective_lookback(params)
