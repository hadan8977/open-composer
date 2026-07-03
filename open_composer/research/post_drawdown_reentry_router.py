from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.router_common import RouterFrameDataset, TargetSnapshot, close_series

HoldingMode = Literal["open_to_open"]

CANARY_SYMBOLS = ("QQQ", "XLK", "IGV", "SOXX", "SMH")
RISK_SYMBOLS = {"QQQ", "TQQQ", "QLD", "SOXL", "USD", "SMH", "SOXX", "XLK", "IGV", "TECL", "ROM"}

_LABEL_RE = re.compile(
    r"^post_drawdown_reentry:"
    r"(?P<risk_universe>[a-z0-9_]+)"
    r"_harddd(?P<harddd>[-0-9.]+)"
    r"_v(?P<vol>[-0-9.]+)"
    r"_breadth(?P<breadth>\d+)"
    r"_soft(?P<soft>[A-Za-z0-9]+)"
    r"_def(?P<defensive>[A-Za-z0-9]+)"
    r"_rec10(?P<recovery>[-0-9.]+)"
    r"_mom60max(?P<momcap>[-0-9.]+)"
    r"_ext(?P<extension>[-0-9.]+)"
    r"_cool(?P<cooldays>\d+)(?P<coolasset>[A-Za-z0-9]+)"
    r"_confirm(?P<confirm>\d+)"
    r"_melt60(?P<meltmom>[-0-9.]+)x(?P<meltext>[-0-9.]+)"
    r"_detdd(?P<detdd>[-0-9.]+)m(?P<detmom>[-0-9.]+)$"
)


@dataclass(frozen=True)
class PostDrawdownReentryParams:
    risk_universe: str
    hard_drawdown_pct: float
    vol_rank_high: float
    canary_breadth_min: int
    soft_stress_asset: str
    defensive_mode: str
    reentry_recovery10_min_pct: float
    reentry_momentum60_max_pct: float
    extension_guard_pct: float
    cooldown_days: int
    cooldown_asset: str
    confirmation_days: int
    meltup_momentum60_min_pct: float
    meltup_extension_pct: float
    deterioration_tqqq_dd20_pct: float
    deterioration_momentum60_max_pct: float

    @property
    def holding_mode(self) -> HoldingMode:
        return "open_to_open"

    @property
    def label(self) -> str:
        return "".join(
            [
                "post_drawdown_reentry:",
                f"{self.risk_universe}_harddd{self.hard_drawdown_pct:g}",
                f"_v{self.vol_rank_high:g}_breadth{self.canary_breadth_min}",
                f"_soft{self.soft_stress_asset}_def{self.defensive_mode}",
                f"_rec10{self.reentry_recovery10_min_pct:g}",
                f"_mom60max{self.reentry_momentum60_max_pct:g}",
                f"_ext{self.extension_guard_pct:g}",
                f"_cool{self.cooldown_days}{self.cooldown_asset}",
                f"_confirm{self.confirmation_days}",
                f"_melt60{self.meltup_momentum60_min_pct:g}x{self.meltup_extension_pct:g}",
                f"_detdd{self.deterioration_tqqq_dd20_pct:g}",
                f"m{self.deterioration_momentum60_max_pct:g}",
            ]
        )


def post_drawdown_reentry_params_from_label(label: str) -> PostDrawdownReentryParams:
    match = _LABEL_RE.fullmatch(label)
    if match is None:
        raise ValueError(f"unsupported post-drawdown re-entry route label: {label}")
    cooldown_asset = match.group("coolasset")
    cooldown_asset = "adaptive" if cooldown_asset.lower() == "adaptive" else cooldown_asset.upper()
    return PostDrawdownReentryParams(
        risk_universe=match.group("risk_universe"),
        hard_drawdown_pct=float(match.group("harddd")),
        vol_rank_high=float(match.group("vol")),
        canary_breadth_min=int(match.group("breadth")),
        soft_stress_asset=match.group("soft").upper(),
        defensive_mode=match.group("defensive"),
        reentry_recovery10_min_pct=float(match.group("recovery")),
        reentry_momentum60_max_pct=float(match.group("momcap")),
        extension_guard_pct=float(match.group("extension")),
        cooldown_days=int(match.group("cooldays")),
        cooldown_asset=cooldown_asset,
        confirmation_days=int(match.group("confirm")),
        meltup_momentum60_min_pct=float(match.group("meltmom")),
        meltup_extension_pct=float(match.group("meltext")),
        deterioration_tqqq_dd20_pct=float(match.group("detdd")),
        deterioration_momentum60_max_pct=float(match.group("detmom")),
    )


def is_post_drawdown_reentry_label(label: str | None) -> bool:
    return bool(label and label.startswith("post_drawdown_reentry:"))


def post_drawdown_reentry_effective_lookback(params: PostDrawdownReentryParams) -> int:
    return max(252, params.confirmation_days + 121)


def post_drawdown_reentry_target_weight_snapshot(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: PostDrawdownReentryParams,
    index: int,
) -> TargetSnapshot:
    decisions = _route_decisions(dataset, params)
    if index < 0 or index >= len(decisions):
        return TargetSnapshot([], {}, 1.0, 1.0, 1.0)
    asset, state = decisions[index]
    if not asset:
        return TargetSnapshot([], {}, 1.0, 1.0, 1.0, state="insufficient_history")
    max_symbol_weight = min(
        spec.portfolio.max_symbol_weight or spec.risk.max_position_weight,
        spec.risk.max_position_weight,
    )
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    target_weight = max(0.0, min(1.0, max_symbol_weight, gross_limit))
    weights = {asset: target_weight} if target_weight > 0 else {}
    features = _features(dataset)
    return TargetSnapshot(
        selected=list(weights),
        weights=weights,
        state=state,
        qqq_trend_ok=_trend_ok(features, index),
        qqq_momentum_ok=_safe(features["qqq_mom120"].iloc[index], default=-100.0) > 0,
        qqq_drawdown_ok=(
            _safe(features["qqq_dd20"].iloc[index], default=-100.0) > -params.hard_drawdown_pct
        ),
        leverage_drawdown_ok=not _early_deterioration_guard(params, features, index),
    )


def _route_decisions(
    dataset: RouterFrameDataset,
    params: PostDrawdownReentryParams,
) -> list[tuple[str | None, str]]:
    key = f"post_drawdown_reentry_decisions:{params.label}"
    cached = dataset.runtime_cache.get(key)
    if cached is not None:
        return cached
    features = _features(dataset)
    start = post_drawdown_reentry_effective_lookback(params)
    decisions: list[tuple[str | None, str]] = [(None, "insufficient_history")] * len(dataset.dates)
    cooldown_remaining = 0
    for index in range(start, len(dataset.dates)):
        trend_ok = _trend_ok(features, index)
        qqq_dd20 = _safe(features["qqq_dd20"].iloc[index], default=-100.0)
        qqq_dd60 = _safe(features["qqq_dd60"].iloc[index], default=-100.0)
        tqqq_dd20 = _safe(features["dd20"]["TQQQ"].iloc[index], default=-100.0)
        tqqq_dd60 = _safe(features["dd60"]["TQQQ"].iloc[index], default=-100.0)
        vol_rank = _safe(features["vol_rank"].iloc[index], default=1.0)
        canary_breadth = int(_safe(features["canary_breadth"].iloc[index], default=0.0))

        hard_stress = (
            qqq_dd20 <= -params.hard_drawdown_pct
            or qqq_dd60 <= -params.hard_drawdown_pct * 1.6
            or tqqq_dd20 <= -12.0
            or tqqq_dd60 <= -25.0
        )
        soft_stress = vol_rank >= params.vol_rank_high or (
            canary_breadth < params.canary_breadth_min
        )
        if not trend_ok or hard_stress:
            cooldown_remaining = params.cooldown_days
            asset = _defensive_asset(params, features, index)
            state = "hard_stress_defensive"
        elif cooldown_remaining > 0:
            asset = _transition_asset(params, features, index)
            cooldown_remaining -= 1
            state = "cooldown_transition"
        elif not _post_stress_confirmed(params, features, index):
            asset = _transition_asset(params, features, index)
            state = "confirmation_transition"
        elif _reentry_ok(params, features, index):
            asset = "TQQQ"
            state = "post_drawdown_reentry"
        elif soft_stress:
            asset = params.soft_stress_asset
            state = "soft_stress"
        else:
            asset = _select_asset(params, features, index)
            if _selected_asset_blocked(params, features, asset, index):
                asset = "QLD"
                state = "selected_asset_blocked"
            else:
                state = "risk_on_ranked"

        if asset in frozenset({"TQQQ", "QLD", "SOXL", "USD"}) and _early_deterioration_guard(
            params, features, index
        ):
            asset = "QQQ"
            state = "early_deterioration_downshift"
        if asset == "TQQQ" and _meltup_guard(params, features, index):
            asset = "QLD"
            state = "melt_up_peak_guard"
        decisions[index] = (asset if asset in dataset.symbols else None, state)
    dataset.runtime_cache[key] = decisions
    return decisions


def _features(dataset: RouterFrameDataset) -> dict[str, Any]:
    cached = dataset.runtime_cache.get("post_drawdown_reentry_features")
    if cached is not None:
        return cached
    close = pd.DataFrame(
        {symbol: close_series(dataset, symbol).to_numpy() for symbol in dataset.symbols},
        index=pd.Index(dataset.dates, name="date"),
    )
    market = dataset.market_symbol
    benchmark = dataset.benchmark_symbol
    returns = close.pct_change(fill_method=None)
    vol20 = returns[market].rolling(20, min_periods=20).std(ddof=0) * math.sqrt(252)
    sma50 = close.rolling(50, min_periods=50).mean().shift(1)
    sma100 = close[market].rolling(100, min_periods=100).mean()
    sma200 = close.rolling(200, min_periods=200).mean().shift(1)
    mom120 = (close.shift(1) / close.shift(121) - 1) * 100
    canaries = [symbol for symbol in CANARY_SYMBOLS if symbol in close.columns]
    canary_breadth = (
        ((close[canaries].shift(1) > sma200[canaries]) & (mom120[canaries] > 0)).sum(axis=1)
        if canaries
        else pd.Series([0] * len(close), index=close.index)
    )
    payload = {
        "close": close,
        "prior": close.shift(1),
        "momentum": {
            lookback: (close.shift(1) / close.shift(lookback + 1) - 1) * 100
            for lookback in (20, 60, 120, 252)
        },
        "symbol_sma": {50: sma50, 200: sma200},
        "qqq_above_sma100": close[market].shift(1) > sma100.shift(1),
        "qqq_above_sma200": close[market].shift(1) > sma200[market],
        "qqq_mom120": (close[market].shift(1) / close[market].shift(121) - 1) * 100,
        "qqq_dd20": (close[market].shift(1) / close[market].rolling(20).max().shift(1) - 1) * 100,
        "qqq_dd60": (close[market].shift(1) / close[market].rolling(60).max().shift(1) - 1) * 100,
        "vol_rank": vol20.rolling(252, min_periods=126).rank(pct=True).shift(1),
        "tqqq_recovery10": (close[benchmark].shift(1) / close[benchmark].shift(11) - 1) * 100,
        "vol60": returns.rolling(60, min_periods=60).std(ddof=0).shift(1) * math.sqrt(252) * 100,
        "dd20": (close.shift(1) / close.rolling(20, min_periods=20).max().shift(1) - 1) * 100,
        "dd60": (close.shift(1) / close.rolling(60, min_periods=60).max().shift(1) - 1) * 100,
        "mom252": (close.shift(1) / close.shift(253) - 1) * 100,
        "extension_sma50": (close.shift(1) / sma50 - 1) * 100,
        "canary_breadth": canary_breadth,
    }
    dataset.runtime_cache["post_drawdown_reentry_features"] = payload
    return payload


def _trend_ok(features: dict[str, Any], index: int) -> bool:
    q200 = bool(features["qqq_above_sma200"].iloc[index])
    mom120 = _safe(features["qqq_mom120"].iloc[index], default=-100.0) > 0
    return q200 or mom120


def _defensive_asset(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> str:
    if params.defensive_mode in frozenset({"GLD", "BIL"}):
        return params.defensive_mode
    if params.defensive_mode != "dual60":
        raise ValueError(f"unsupported defensive_mode: {params.defensive_mode}")
    best_score = -1_000_000_000.0
    best_asset = "BIL"
    for asset in ("GLD", "BIL"):
        mom60 = _safe(features["momentum"][60][asset].iloc[index], default=-100.0)
        sma_value = _safe(features["symbol_sma"][200][asset].iloc[index], default=float("nan"))
        prior = _safe(features["prior"][asset].iloc[index], default=float("nan"))
        trend_bonus = (
            2.0 if math.isfinite(prior) and math.isfinite(sma_value) and prior > sma_value else 0.0
        )
        score = mom60 + trend_bonus
        if score > best_score:
            best_score = score
            best_asset = asset
    return best_asset


def _transition_asset(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> str:
    if params.cooldown_asset in frozenset({"QQQ", "QLD"}):
        return params.cooldown_asset
    if params.cooldown_asset != "adaptive":
        raise ValueError(f"unsupported cooldown_asset: {params.cooldown_asset}")
    qqq_dd20 = _safe(features["qqq_dd20"].iloc[index], default=-100.0)
    tqqq_dd20 = _safe(features["dd20"]["TQQQ"].iloc[index], default=-100.0)
    tqqq_mom20 = _safe(features["momentum"][20]["TQQQ"].iloc[index], default=-100.0)
    if qqq_dd20 <= -2.0 or tqqq_dd20 <= -6.0 or tqqq_mom20 <= 0.0:
        return "QQQ"
    return "QLD"


def _reentry_ok(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> bool:
    recovery10 = _safe(features["tqqq_recovery10"].iloc[index], default=-100.0)
    mom60 = _safe(features["momentum"][60]["TQQQ"].iloc[index], default=100.0)
    dd20 = _safe(features["dd20"]["TQQQ"].iloc[index], default=-100.0)
    extension = _safe(features["extension_sma50"]["TQQQ"].iloc[index], default=100.0)
    return (
        recovery10 >= params.reentry_recovery10_min_pct
        and mom60 <= params.reentry_momentum60_max_pct
        and dd20 > -12.0
        and extension < params.extension_guard_pct
    )


def _post_stress_confirmed(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> bool:
    if params.confirmation_days <= 0:
        return True
    start = max(0, index - params.confirmation_days + 1)
    for check_index in range(start, index + 1):
        qqq_dd20 = _safe(features["qqq_dd20"].iloc[check_index], default=-100.0)
        qqq_mom120 = _safe(features["qqq_mom120"].iloc[check_index], default=-100.0)
        tqqq_mom20 = _safe(features["momentum"][20]["TQQQ"].iloc[check_index], default=-100.0)
        tqqq_dd20 = _safe(features["dd20"]["TQQQ"].iloc[check_index], default=-100.0)
        if qqq_dd20 <= -params.hard_drawdown_pct * 0.5 or qqq_mom120 <= 0.0:
            return False
        if tqqq_mom20 <= 0.0 or tqqq_dd20 <= -12.0:
            return False
    return True


def _meltup_guard(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> bool:
    mom60 = _safe(features["momentum"][60]["TQQQ"].iloc[index], default=-100.0)
    extension = _safe(features["extension_sma50"]["TQQQ"].iloc[index], default=-100.0)
    return mom60 >= params.meltup_momentum60_min_pct and extension >= params.meltup_extension_pct


def _early_deterioration_guard(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> bool:
    if params.deterioration_tqqq_dd20_pct <= 0.0:
        return False
    tqqq_dd20 = _safe(features["dd20"]["TQQQ"].iloc[index], default=0.0)
    tqqq_mom60 = _safe(features["momentum"][60]["TQQQ"].iloc[index], default=100.0)
    qqq_dd20 = _safe(features["qqq_dd20"].iloc[index], default=0.0)
    return (
        tqqq_dd20 <= -params.deterioration_tqqq_dd20_pct
        and tqqq_mom60 <= params.deterioration_momentum60_max_pct
        and qqq_dd20 <= -1.0
    )


def _selected_asset_blocked(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    asset: str,
    index: int,
) -> bool:
    dd20 = _safe(features["dd20"][asset].iloc[index], default=-100.0)
    dd60 = _safe(features["dd60"][asset].iloc[index], default=-100.0)
    return dd20 <= -12.0 or dd60 <= -25.0 or _is_overextended(params, features, asset, index)


def _select_asset(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    index: int,
) -> str:
    candidates = (
        ["TQQQ", "QLD"]
        if params.risk_universe == "tqqq_qld"
        else [
            "TQQQ",
            "QLD",
            "SOXL",
            "USD",
        ]
    )
    semi_ok = (
        _safe(features["prior"]["SMH"].iloc[index], default=float("nan"))
        > _safe(features["symbol_sma"][200]["SMH"].iloc[index], default=float("nan"))
        and _safe(features["mom252"]["SMH"].iloc[index], default=-999.0) >= 100.0
    )
    scores: list[tuple[float, str]] = []
    for symbol in candidates:
        if symbol == "SOXL" and not semi_ok:
            continue
        prior = _safe(features["prior"][symbol].iloc[index], default=float("nan"))
        sma200 = _safe(features["symbol_sma"][200][symbol].iloc[index], default=float("nan"))
        if not math.isfinite(prior) or not math.isfinite(sma200) or prior <= sma200:
            continue
        mom120 = _safe(features["momentum"][120][symbol].iloc[index], default=-999.0)
        if mom120 < 0.0:
            continue
        mom20 = _safe(features["momentum"][20][symbol].iloc[index], default=-999.0)
        mom60 = _safe(features["momentum"][60][symbol].iloc[index], default=-999.0)
        vol60 = max(_safe(features["vol60"][symbol].iloc[index], default=999.0), 1.0)
        dd20 = _safe(features["dd20"][symbol].iloc[index], default=-100.0)
        dd60 = _safe(features["dd60"][symbol].iloc[index], default=-100.0)
        scores.append((_score_symbol(mom20, mom60, mom120, vol60, dd20, dd60), symbol))
    if not scores:
        return "QQQ"
    scores.sort(reverse=True)
    return scores[0][1]


def _is_overextended(
    params: PostDrawdownReentryParams,
    features: dict[str, Any],
    symbol: str,
    index: int,
) -> bool:
    extension = _safe(features["extension_sma50"][symbol].iloc[index], default=0.0)
    mom20 = _safe(features["momentum"][20][symbol].iloc[index], default=0.0)
    return extension >= params.extension_guard_pct and mom20 >= params.extension_guard_pct


def _score_symbol(
    mom20: float,
    mom60: float,
    mom120: float,
    vol60: float,
    dd20: float,
    dd60: float,
) -> float:
    del mom20, vol60, dd20
    return mom120 + 0.25 * mom60 - 0.6 * abs(min(dd60, 0.0))


def _safe(value: Any, *, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default
