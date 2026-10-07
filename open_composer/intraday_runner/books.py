"""Virtual sub-accounts, fill allocation and the append-only event log with replay.

Every state change is an event in ``events.jsonl`` (one file per account and session).  The
in-memory :class:`SessionState` is only ever changed by :meth:`SessionState.apply`, which is
also what the restart path replays, so a recovered process sees exactly the state the crashed
one had written down.  A ``fill_sync`` event carries its allocations inline: one JSON line is
the commit unit, so a torn write loses the whole fill record (it is then re-synced from the
broker) and never half of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_composer.intraday_runner.config import RunnerConfig
from open_composer.storage import append_jsonl, ensure_dir

TERMINAL = frozenset({"filled", "canceled", "cancelled", "expired", "rejected", "replaced"})


class EventLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, event: dict[str, Any]) -> None:
        ensure_dir(self.path.parent)
        append_jsonl(self.path, [event])

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn trailing write after a crash; the next sync repairs it
        return events


@dataclass
class SubAccount:
    name: str
    capital_usd: float
    positions: dict[str, float] = field(default_factory=dict)
    avg_cost: dict[str, float] = field(default_factory=dict)
    realized: float = 0.0
    fees: float = 0.0
    internal_cost: float = 0.0  # model cost charged on shares crossed inside the account
    slippage_usd: float = 0.0
    traded_notional: float = 0.0
    fills: int = 0

    def apply_fill(
        self,
        symbol: str,
        qty: float,
        price: float,
        plan_price: float,
        fee: float,
        internal_cost: float = 0.0,
    ) -> None:
        pos = self.positions.get(symbol, 0.0)
        avg = self.avg_cost.get(symbol, 0.0)
        new = pos + qty
        if pos == 0 or pos * qty > 0:
            avg = (abs(pos) * avg + abs(qty) * price) / abs(new)
        else:
            closed = min(abs(qty), abs(pos))
            self.realized += closed * (price - avg) * (1.0 if pos > 0 else -1.0)
            if abs(qty) > abs(pos):
                avg = price
            elif new == 0:
                avg = 0.0
        self.positions[symbol] = new
        self.avg_cost[symbol] = avg
        self.fees += fee
        self.internal_cost += internal_cost
        self.slippage_usd += qty * (price - plan_price)
        self.traded_notional += abs(qty) * price
        self.fills += 1

    def unrealized(self, prices: dict[str, float]) -> float:
        total = 0.0
        for symbol, qty in self.positions.items():
            if qty:
                price = prices.get(symbol)
                if price:
                    total += qty * (price - self.avg_cost.get(symbol, price))
        return total

    def day_pnl(self, prices: dict[str, float]) -> float:
        """Net P&L at actual fills: realized + unrealized - fees - internal-cross cost."""
        return self.realized + self.unrealized(prices) - self.fees - self.internal_cost

    def gross_exposure(self, prices: dict[str, float]) -> float:
        return sum(
            abs(qty) * (prices.get(sym) or self.avg_cost.get(sym, 0.0))
            for sym, qty in self.positions.items()
        )


@dataclass
class OrderRecord:
    cid: str
    symbol: str
    side: str
    qty: int
    purpose: str
    tick: str
    plan_price: float
    parts: dict[str, int]
    created_at: str
    flatten: bool = False
    status: str = "planned"  # planned | submitted | resolved | abandoned
    broker_order_id: str | None = None
    broker_status: str | None = None
    filled_cum: float = 0.0
    avg_cum: float = 0.0
    alloc: dict[str, int] = field(default_factory=dict)
    cross_done: bool = False

    @property
    def sign(self) -> int:
        return 1 if self.side == "buy" else -1

    @property
    def internal(self) -> bool:
        return self.qty == 0

    def remaining(self) -> dict[str, int]:
        return {k: v - self.alloc.get(k, 0) for k, v in self.parts.items()}


def _largest_remainder(amount: int, weights: dict[str, int]) -> dict[str, int]:
    total = sum(weights.values())
    if total <= 0 or amount <= 0:
        return {k: 0 for k in weights}
    exact = {k: amount * w / total for k, w in weights.items()}
    out = {k: int(v) for k, v in exact.items()}
    left = amount - sum(out.values())
    order = sorted(weights, key=lambda k: (-(exact[k] - out[k]), k))
    for key in order[:left]:
        out[key] += 1
    return out


def allocate_increment(
    remaining: dict[str, int], sign: int, filled_incr: int, include_cross: bool
) -> dict[str, int]:
    """Split a broker fill increment of a netted order back to the strategies.

    ``remaining`` is each strategy's still-unfilled signed delta, ``sign`` the sign of the net
    order.  On the first positive fill, strategies on the opposite side are filled completely
    (their shares were crossed internally against the net side) and the net-side strategies
    receive ``filled_incr`` plus the crossed amount, pro rata to their remaining deltas
    (integer largest-remainder, never above a strategy's own remaining delta)."""
    net_side = {k: abs(v) for k, v in remaining.items() if v * sign > 0}
    opposite = {k: v for k, v in remaining.items() if v * sign < 0}
    out: dict[str, int] = {}
    crossed = 0
    if include_cross:
        out.update(opposite)
        crossed = sum(abs(v) for v in opposite.values())
    amount = min(filled_incr + crossed, sum(net_side.values()))
    for key, qty in _largest_remainder(amount, net_side).items():
        if qty:
            out[key] = sign * qty
    return out


@dataclass
class SessionState:
    config: RunnerConfig
    session: str
    subs: dict[str, SubAccount] = field(default_factory=dict)
    orders: dict[str, OrderRecord] = field(default_factory=dict)
    ticks_done: set[tuple[str, str]] = field(default_factory=set)
    halts: dict[str, str] = field(default_factory=dict)
    plugin_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    standing: dict[str, dict[str, int]] = field(default_factory=dict)
    intents: dict[str, int] = field(default_factory=dict)
    drift_reported: set[str] = field(default_factory=set)
    intent_keys: set[tuple[str, str, str]] = field(default_factory=set)
    started: bool = False
    summarized: bool = False
    last_tick: str | None = None
    stops: dict[str, str] = field(
        default_factory=dict
    )  # 'strategy:SYMBOL' -> cooldown end (UTC iso)

    def __post_init__(self) -> None:
        for item in self.config.strategies:
            self.subs.setdefault(item.name, SubAccount(item.name, item.capital_usd))
            self.standing.setdefault(item.name, {})
            self.intents.setdefault(item.name, 0)

    # -- queries -----------------------------------------------------------------------
    def pending_symbols(self) -> set[str]:
        return {o.symbol for o in self.orders.values() if o.status in {"planned", "submitted"}}

    def account_positions(self) -> dict[str, float]:
        total: dict[str, float] = {}
        for sub in self.subs.values():
            for symbol, qty in sub.positions.items():
                total[symbol] = total.get(symbol, 0.0) + qty
        return {k: v for k, v in total.items() if v}

    def account_order_count(self) -> int:
        return sum(1 for o in self.orders.values() if not o.internal)

    def unresolved(self) -> list[OrderRecord]:
        return [o for o in self.orders.values() if o.status in {"planned", "submitted"}]

    # -- the only mutator ----------------------------------------------------------------
    def apply(self, event: dict[str, Any]) -> None:  # noqa: C901 - flat dispatch
        kind = event.get("type")
        if kind == "session_start":
            self.started = True
            for name, opening in (event.get("opening") or {}).items():
                sub = self.subs.get(name)
                if sub is not None and not sub.positions:
                    sub.positions = {k: float(v) for k, v in opening.get("positions", {}).items()}
                    sub.avg_cost = {k: float(v) for k, v in opening.get("avg_cost", {}).items()}
        elif kind == "signal":
            self.plugin_state[event["strategy"]] = dict(event.get("state") or {})
        elif kind == "standing":
            self.standing[event["strategy"]] = {k: int(v) for k, v in event["targets"].items()}
        elif kind == "intent":
            key = (event["strategy"], event["tick"], event["symbol"])
            if event.get("counted") and key not in self.intent_keys:
                self.intent_keys.add(key)
                self.intents[event["strategy"]] = self.intents.get(event["strategy"], 0) + 1
        elif kind == "net_order":
            self.orders[event["cid"]] = OrderRecord(
                cid=event["cid"],
                symbol=event["symbol"],
                side=event["side"],
                qty=int(event["qty"]),
                purpose=event["purpose"],
                tick=event["tick"],
                plan_price=float(event["plan_price"]),
                parts={k: int(v) for k, v in event["parts"].items()},
                created_at=event["ts"],
                flatten=bool(event.get("flatten")),
            )
        elif kind == "submit_result":
            order = self.orders.get(event["cid"])
            if order is not None:
                order.status = "submitted"
                order.broker_order_id = event.get("broker_order_id")
                order.broker_status = event.get("status")
        elif kind == "fill_sync":
            self._apply_fill_sync(event)
        elif kind == "order_abandoned":
            order = self.orders.get(event["cid"])
            if order is not None:
                order.status = "abandoned"
        elif kind == "halt":
            self.halts[f"{event['scope']}:{event['name']}"] = event.get("reason", "")
        elif kind == "tick_done":
            self.ticks_done.add((event["strategy"], event["tick"]))
            self.last_tick = event["tick"]
        elif kind == "stop":
            self.stops[f"{event['strategy']}:{event['symbol']}"] = event["until"]
        elif kind == "drift":
            self.drift_reported.add(event["symbol"])
        elif kind == "summary":
            self.summarized = True

    def _apply_fill_sync(self, event: dict[str, Any]) -> None:
        order = self.orders.get(event["cid"])
        if order is None:
            return
        order.filled_cum = float(event.get("filled_cum", order.filled_cum))
        order.avg_cum = float(event.get("avg_cum", order.avg_cum))
        order.broker_status = event.get("status", order.broker_status)
        for item in event.get("allocs", []):
            sub = self.subs[item["strategy"]]
            sub.apply_fill(
                item["symbol"],
                float(item["qty"]),
                float(item["price"]),
                float(item["plan_price"]),
                float(item.get("fee", 0.0)),
                float(item.get("internal_cost", 0.0)),
            )
            order.alloc[item["strategy"]] = order.alloc.get(item["strategy"], 0) + int(item["qty"])
        if event.get("allocs") and (order.internal or order.filled_cum > 0):
            order.cross_done = True
        if event.get("terminal") or order.internal:
            order.status = "resolved"


def replay(config: RunnerConfig, session: str, log: EventLog) -> SessionState:
    state = SessionState(config=config, session=session)
    for event in log.read():
        state.apply(event)
    return state
