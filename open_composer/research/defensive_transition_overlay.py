from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.delayed_entry_overlay import DelayedEntryOverlay
from open_composer.research.pdr_ml_gate import (
    PDRMLGateConfig,
    pdr_ml_gate_from_token,
    pdr_ml_gate_should_release,
)
from open_composer.research.post_drawdown_reentry_router import (
    post_drawdown_reentry_effective_lookback,
    post_drawdown_reentry_ml_release_snapshot,
    post_drawdown_reentry_params_from_label,
    post_drawdown_reentry_target_weight_snapshot,
)
from open_composer.research.router_common import RouterFrameDataset, TargetSnapshot

HARD_STRESS_STATES = {"hard_stress_defensive"}
TRANSITION_STATES = {"confirmation_transition", "cooldown_transition"}

_LABEL_RE = re.compile(
    r"^defensive_overlay:"
    r"(?P<scope>hard_stress|transition|hard_and_transition)_"
    r"(?P<replacement>[A-Za-z0-9]+)_"
    r"(?P<condition>always|replacement_mom_positive|qqq_below_sma200)_"
    r"lb(?P<lookback>\d+)_"
    r"min(?P<minimum>[-0-9.]+)_"
    r"delay(?P<delay>\d+)_"
    r"(?:(?P<mlgate>mlgate_h\d+_tm?\d+(?:p\d+)?_p\d+)_)?"
    r"base\[(?P<base>.+)\]$"
)


@dataclass(frozen=True)
class DefensiveTransitionOverlay:
    scope: str
    replacement_symbol: str
    condition: str
    lookback_days: int
    min_momentum_pct: float
    delay_minutes: int
    base_route_label: str
    covered_symbols: tuple[str, ...] = ("TQQQ", "QLD", "SOXL", "USD")
    ml_gate: PDRMLGateConfig | None = None

    @property
    def label(self) -> str:
        base = self.base_route_label.replace("post_drawdown_reentry:", "pdr:")
        gate = f"_{self.ml_gate.token}" if self.ml_gate is not None else ""
        return (
            f"defensive_overlay:{self.scope}_{self.replacement_symbol}_{self.condition}"
            f"_lb{self.lookback_days}_min{self.min_momentum_pct:g}"
            f"_delay{self.delay_minutes}{gate}_base[{base}]"
        )

    @property
    def holding_mode(self) -> str:
        return post_drawdown_reentry_params_from_label(self.base_route_label).holding_mode

    @property
    def delayed_entry_overlay(self) -> DelayedEntryOverlay:
        return DelayedEntryOverlay(
            delay_minutes=self.delay_minutes,
            base_route_label=self.base_route_label,
            covered_symbols=self.covered_symbols,
        )


def defensive_transition_overlay_from_label(label: str) -> DefensiveTransitionOverlay:
    match = _LABEL_RE.fullmatch(label)
    if match is None:
        raise ValueError(f"unsupported defensive-transition overlay label: {label}")
    delay_minutes = int(match.group("delay"))
    if delay_minutes < 0:
        raise ValueError(f"unsupported defensive-transition delay_minutes={delay_minutes}")
    return DefensiveTransitionOverlay(
        scope=match.group("scope"),
        replacement_symbol=match.group("replacement").upper(),
        condition=match.group("condition"),
        lookback_days=int(match.group("lookback")),
        min_momentum_pct=float(match.group("minimum")),
        delay_minutes=delay_minutes,
        base_route_label=_expand_base_label(match.group("base")),
        ml_gate=(
            pdr_ml_gate_from_token(match.group("mlgate"))
            if match.group("mlgate") is not None
            else None
        ),
    )


def is_defensive_transition_overlay_label(label: str | None) -> bool:
    return bool(label and label.startswith("defensive_overlay:"))


def defensive_transition_overlay_effective_lookback(
    overlay: DefensiveTransitionOverlay,
) -> int:
    base = post_drawdown_reentry_params_from_label(overlay.base_route_label)
    return max(post_drawdown_reentry_effective_lookback(base), overlay.lookback_days + 1, 201)


def defensive_transition_overlay_target_weight_snapshot(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    overlay: DefensiveTransitionOverlay,
    index: int,
) -> TargetSnapshot:
    base_params = post_drawdown_reentry_params_from_label(overlay.base_route_label)
    base = post_drawdown_reentry_target_weight_snapshot(spec, dataset, base_params, index)
    if (
        overlay.ml_gate is not None
        and base.state == "hard_stress_defensive"
        and pdr_ml_gate_should_release(spec, dataset, overlay.ml_gate, index)
    ):
        released = post_drawdown_reentry_ml_release_snapshot(spec, dataset, base_params, index)
        if not released.weights:
            return base
        if _condition_matches(dataset, overlay, index):
            return _replace_snapshot_symbol(released, overlay.replacement_symbol, dataset)
        return released
    if not base.weights or not _scope_matches(base.state, overlay.scope):
        return base
    if not _condition_matches(dataset, overlay, index):
        return base
    return _replace_snapshot_symbol(base, overlay.replacement_symbol, dataset)


def defensive_transition_overlay_summary(
    overlay: DefensiveTransitionOverlay | None,
) -> dict[str, object] | None:
    if overlay is None:
        return None
    return {
        "type": "defensive_transition_overlay",
        "scope": overlay.scope,
        "replacement_symbol": overlay.replacement_symbol,
        "condition": overlay.condition,
        "lookback_days": overlay.lookback_days,
        "min_momentum_pct": overlay.min_momentum_pct,
        "delay_minutes": overlay.delay_minutes,
        "covered_symbols": list(overlay.covered_symbols),
        "base_route_label": overlay.base_route_label,
        "ml_gate": overlay.ml_gate.to_payload() if overlay.ml_gate is not None else None,
        "status": "research_observation",
        "limits": [
            "changes target asset only in configured defensive or transition states",
            "requires full artifact, forensics, and paper-readiness checks before paper_auto",
        ],
    }


def _condition_matches(
    dataset: RouterFrameDataset,
    overlay: DefensiveTransitionOverlay,
    index: int,
) -> bool:
    features = _features(dataset, overlay.replacement_symbol, overlay.lookback_days)
    if overlay.condition == "always":
        return True
    if overlay.condition == "qqq_below_sma200":
        return bool(features["qqq_below_sma200"].iloc[index])
    if overlay.condition == "replacement_mom_positive":
        momentum = _safe(features["replacement_momentum"].iloc[index])
        return math.isfinite(momentum) and momentum >= overlay.min_momentum_pct
    raise ValueError(f"unsupported defensive-transition condition: {overlay.condition}")


def _scope_matches(state: str, scope: str) -> bool:
    if scope == "hard_stress":
        return state in HARD_STRESS_STATES
    if scope == "transition":
        return state in TRANSITION_STATES
    if scope == "hard_and_transition":
        return state in HARD_STRESS_STATES or state in TRANSITION_STATES
    raise ValueError(f"unsupported defensive-transition scope: {scope}")


def _replace_snapshot_symbol(
    base: TargetSnapshot,
    replacement_symbol: str,
    dataset: RouterFrameDataset,
) -> TargetSnapshot:
    replacement = replacement_symbol.upper()
    if replacement not in dataset.symbols:
        return base
    weight = sum(float(value) for value in base.weights.values())
    if weight <= 0:
        return base
    return replace(
        base,
        selected=[replacement],
        weights={replacement: weight},
        state=f"{base.state}_overlay_{replacement}",
    )


def _features(
    dataset: RouterFrameDataset,
    replacement_symbol: str,
    lookback_days: int,
) -> dict[str, pd.Series]:
    key = f"defensive_transition_overlay:{replacement_symbol}:{lookback_days}"
    cached = dataset.runtime_cache.get(key)
    if cached is not None:
        return cached
    qqq_close = dataset.frame["QQQ_close"].astype(float)
    replacement_close = dataset.frame[f"{replacement_symbol.upper()}_close"].astype(float)
    features = {
        "qqq_below_sma200": qqq_close.shift(1)
        < qqq_close.rolling(200, min_periods=100).mean().shift(1),
        "replacement_momentum": (
            replacement_close.shift(1) / replacement_close.shift(lookback_days + 1) - 1
        )
        * 100,
    }
    dataset.runtime_cache[key] = features
    return features


def _expand_base_label(label: str) -> str:
    if label.startswith("pdr:"):
        return "post_drawdown_reentry:" + label.removeprefix("pdr:")
    return label


def _safe(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")
