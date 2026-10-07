"""Broker boundary: a small protocol, the Alpaca Paper adapter and an in-memory simulator.

The simulator is the "fake broker client" of the dry run and the tests; it never imports the
Alpaca SDK.  The Alpaca adapter only accepts a client built by the strict paper factory and
reuses ``paper_intraday._build_market_request`` for the order payload.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from open_composer.adapters.broker.alpaca_paper import (
    _optional_broker_account_hash,
    _require_verified_paper_client,
)
from open_composer.intraday_runner.books import TERMINAL
from open_composer.intraday_runner.ratelimit import RateLimiter


class BrokerError(RuntimeError):
    pass


class DuplicateClientOrderId(BrokerError):
    pass


@dataclass
class OrderInfo:
    cid: str
    broker_order_id: str
    status: str
    symbol: str
    side: str
    qty: float
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    last_equity: float
    buying_power: float
    id_hash: str


@dataclass(frozen=True)
class AssetInfo:
    tradable: bool
    shortable: bool
    easy_to_borrow: bool

    @property
    def can_short(self) -> bool:
        return self.tradable and self.shortable and self.easy_to_borrow


class Broker(Protocol):
    def account_snapshot(self) -> AccountSnapshot: ...
    def positions(self) -> dict[str, float]: ...
    def open_orders(self) -> list[OrderInfo]: ...
    def asset(self, symbol: str) -> AssetInfo: ...
    def submit_market(self, symbol: str, side: str, qty: int, cid: str) -> OrderInfo: ...
    def get_order(self, cid: str) -> OrderInfo | None: ...
    def cancel(self, cid: str) -> None: ...


def _status(order: Any) -> str:
    raw = getattr(order, "status", "")
    return str(getattr(raw, "value", raw)).split(".")[-1].lower()


def _order_info(order: Any, cid: str) -> OrderInfo:
    return OrderInfo(
        cid=str(getattr(order, "client_order_id", None) or cid),
        broker_order_id=str(getattr(order, "id", "")),
        status=_status(order),
        symbol=str(getattr(order, "symbol", "")).upper(),
        side=str(getattr(getattr(order, "side", ""), "value", getattr(order, "side", "")))
        .split(".")[-1]
        .lower(),
        qty=float(getattr(order, "qty", 0) or 0),
        filled_qty=float(getattr(order, "filled_qty", 0) or 0),
        filled_avg_price=float(getattr(order, "filled_avg_price", 0) or 0),
    )


class AlpacaPaperBroker:
    """Adapter over a verified Alpaca Paper ``TradingClient`` (DAY market orders, RTH)."""

    def __init__(self, client: Any, limiter: RateLimiter | None = None):
        _require_verified_paper_client(client)
        self.client = client
        self.limiter = limiter or RateLimiter()

    def _slot(self) -> None:
        self.limiter.acquire()

    def account_snapshot(self) -> AccountSnapshot:
        self._slot()
        account = self.client.get_account()
        return AccountSnapshot(
            equity=float(getattr(account, "equity", 0) or 0),
            last_equity=float(getattr(account, "last_equity", 0) or 0),
            buying_power=float(getattr(account, "buying_power", 0) or 0),
            id_hash=_optional_broker_account_hash(getattr(account, "id", None)) or "",
        )

    def positions(self) -> dict[str, float]:
        self._slot()
        out: dict[str, float] = {}
        for position in self.client.get_all_positions():
            out[str(position.symbol).upper()] = float(position.qty)
        return out

    def open_orders(self) -> list[OrderInfo]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        self._slot()
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
        return [_order_info(o, "") for o in orders]

    def asset(self, symbol: str) -> AssetInfo:
        self._slot()
        asset = self.client.get_asset(symbol)
        return AssetInfo(
            tradable=bool(getattr(asset, "tradable", False)),
            shortable=bool(getattr(asset, "shortable", False)),
            easy_to_borrow=bool(getattr(asset, "easy_to_borrow", False)),
        )

    def submit_market(self, symbol: str, side: str, qty: int, cid: str) -> OrderInfo:
        from open_composer.paper_intraday import IntradayOrderPlan, _build_market_request

        plan = IntradayOrderPlan(
            symbol=symbol, mode="entry", side=side, qty=float(qty), client_order_id=cid
        )
        self._slot()
        try:
            order = self.client.submit_order(_build_market_request(plan))
        except Exception as exc:
            if "client_order_id" in str(exc) and "unique" in str(exc).lower():
                raise DuplicateClientOrderId(str(exc)) from exc
            raise
        return _order_info(order, cid)

    def get_order(self, cid: str) -> OrderInfo | None:
        self._slot()
        try:
            order = self.client.get_order_by_client_id(cid)
        except Exception as exc:
            if (
                getattr(exc, "status_code", None) == 404
                or exc.__class__.__name__ == "NotFoundError"
            ):
                return None
            raise BrokerError(f"broker order lookup failed: {exc}") from exc
        return _order_info(order, cid)

    def cancel(self, cid: str) -> None:
        info = self.get_order(cid)
        if info is not None and not info.terminal:
            self._slot()
            self.client.cancel_order_by_id(info.broker_order_id)


class SimBroker:
    """In-memory paper broker.  Market orders fill at ``price_fn(symbol)`` +/- slippage."""

    def __init__(
        self,
        price_fn: Callable[[str], float | None],
        *,
        slippage_bps: float = 0.0,
        start_equity: float = 1_000_000.0,
        shortable: Callable[[str], bool] | None = None,
        partial_fraction: float | None = None,
        hold_unfilled: bool = False,
        cancel_confirms: bool = True,
    ):
        self.price_fn = price_fn
        self.slippage_bps = slippage_bps
        self.start_equity = start_equity
        self.cash = start_equity
        self._pos: dict[str, float] = {}
        self.orders: dict[str, OrderInfo] = {}
        self.submit_calls: list[tuple[str, str, int, str]] = []
        self.shortable = shortable or (lambda _s: True)
        self.partial_fraction = partial_fraction
        self.hold_unfilled = hold_unfilled
        self.cancel_confirms = cancel_confirms
        self.crash_after_accept: Callable[[str], bool] | None = None
        self.reject: Callable[[str], bool] | None = None
        self.cancelled: list[str] = []

    def account_snapshot(self) -> AccountSnapshot:
        equity = self.cash + sum(q * (self.price_fn(s) or 0.0) for s, q in self._pos.items())
        return AccountSnapshot(equity, self.start_equity, equity * 4, "simbroker")

    def positions(self) -> dict[str, float]:
        return {k: v for k, v in self._pos.items() if v}

    def open_orders(self) -> list[OrderInfo]:
        return [OrderInfo(**{**o.__dict__}) for o in self.orders.values() if not o.terminal]

    def asset(self, symbol: str) -> AssetInfo:
        ok = self.shortable(symbol)
        return AssetInfo(True, ok, ok)

    def submit_market(self, symbol: str, side: str, qty: int, cid: str) -> OrderInfo:
        self.submit_calls.append((symbol, side, qty, cid))
        if cid in self.orders:
            raise DuplicateClientOrderId(f"client_order_id {cid} must be unique")
        for other in self.orders.values():  # Alpaca user protection, paper included
            if other.symbol == symbol and other.side != side and not other.terminal:
                raise BrokerError("potential wash trade detected: opposite-side order is open")
        order = OrderInfo(cid, f"sim-{len(self.orders) + 1}", "new", symbol, side, float(qty))
        if self.reject and self.reject(symbol):
            order.status = "rejected"
            self.orders[cid] = order
            return OrderInfo(**{**order.__dict__})
        self.orders[cid] = order
        if not self.hold_unfilled:
            self._fill(order)
        if self.crash_after_accept and self.crash_after_accept(cid):
            raise SimulatedCrash(cid)
        return OrderInfo(**{**order.__dict__})

    def _fill(self, order: OrderInfo) -> None:
        price = self.price_fn(order.symbol)
        if price is None:
            return
        sign = 1.0 if order.side == "buy" else -1.0
        px = price * (1 + sign * self.slippage_bps / 1e4)
        qty = order.qty
        if self.partial_fraction is not None:
            qty = float(int(order.qty * self.partial_fraction))
        order.filled_qty, order.filled_avg_price = qty, px
        order.status = "filled" if qty == order.qty else "partially_filled"
        self._pos[order.symbol] = self._pos.get(order.symbol, 0.0) + sign * qty
        self.cash -= sign * qty * px

    def release(self, cid: str) -> None:
        """Fill an order that was held (``hold_unfilled``)."""
        self._fill(self.orders[cid])

    def get_order(self, cid: str) -> OrderInfo | None:
        order = self.orders.get(cid)
        return OrderInfo(**{**order.__dict__}) if order else None

    def cancel(self, cid: str) -> None:
        order = self.orders.get(cid)
        if order and order.status not in TERMINAL:
            order.status = "canceled" if self.cancel_confirms else "pending_cancel"
            self.cancelled.append(cid)

    def confirm_cancels(self) -> None:
        for order in self.orders.values():
            if order.status == "pending_cancel":
                order.status = "canceled"


class SimulatedCrash(BaseException):  # noqa: N818 - emulates process death, must not be caught
    """Raised by :class:`SimBroker` to emulate the runner dying right after the broker accepted."""
