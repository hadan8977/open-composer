"""Pre-trade risk: pure functions on (config, virtual state) -> approved share targets.

Policy: caps limit *increases* of exposure.  A position that drifted above a cap through price
moves alone is not force-sold, exits and reductions are never blocked by the order-count cap,
and a daily-loss breach or the pre-close flatten overrides everything with target 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from open_composer.intraday_runner.books import _largest_remainder
from open_composer.intraday_runner.config import StrategyConfig


@dataclass(frozen=True)
class RiskDecision:
    approved: int
    status: str  # ok | clipped | blocked
    reason: str = ""


def increases_exposure(current: float, approved: float) -> bool:
    return abs(approved) > abs(current) or current * approved < 0


def clip_target(
    cfg: StrategyConfig,
    *,
    symbol: str,
    wanted: int,
    current: float,
    price: float,
    other_gross_usd: float,
    orders_used: int,
    shortable: bool | None,
) -> RiskDecision:
    """Approve ``wanted`` shares for ``symbol`` (signed) or clip/block it."""
    if wanted == current:
        return RiskDecision(int(wanted), "ok")
    if price <= 0:
        return RiskDecision(int(current), "blocked", "no_price")
    if current * wanted > 0 and abs(wanted - current) < cfg.resize_band * abs(current):
        return RiskDecision(int(current), "ok", "within_band")
    status, reason = "ok", ""
    approved = int(wanted)
    if approved < 0 and shortable is not True:
        approved = 0
        status, reason = "clipped", "not_shortable_or_not_easy_to_borrow"
    if increases_exposure(current, approved):
        sym_room = math.floor(cfg.caps.max_symbol_notional_usd / price)
        strat_room = math.floor(max(cfg.caps.max_notional_usd - other_gross_usd, 0.0) / price)
        limit = min(sym_room, strat_room)
        if abs(approved) > limit:
            floor_ = abs(current) if current * approved > 0 else 0
            approved = int(math.copysign(max(limit, floor_), approved)) if approved else 0
            if abs(approved) < floor_:
                approved = int(current)
            status, reason = "clipped", reason or "notional_cap"
        if increases_exposure(current, approved) and orders_used >= cfg.caps.max_orders_per_day:
            return RiskDecision(int(current), "blocked", "max_orders_per_day")
    if approved == current and wanted != current:
        return RiskDecision(int(current), "blocked", reason or "cap")
    if current * approved > 0 and abs(approved - current) < cfg.resize_band * abs(current):
        return RiskDecision(int(current), "ok", "within_band")  # no churn from price-driven sizes
    return RiskDecision(approved, status, reason)


def daily_loss_breached(day_pnl_usd: float, limit_usd: float) -> bool:
    return day_pnl_usd <= -abs(limit_usd)


def shrink_parts(parts: dict[str, int], new_net: int) -> dict[str, int]:
    """Reduce the net-side strategies' deltas pro rata so the netted order becomes ``new_net``."""
    net = sum(parts.values())
    if net == 0 or new_net == net:
        return dict(parts)
    sign = 1 if net > 0 else -1
    excess = abs(net) - abs(new_net)
    net_side = {k: abs(v) for k, v in parts.items() if v * sign > 0}
    cut = _largest_remainder(excess, net_side)
    out = dict(parts)
    for key, qty in cut.items():
        out[key] = sign * (net_side[key] - qty)
    return out
