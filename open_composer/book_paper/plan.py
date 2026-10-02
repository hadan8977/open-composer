"""Order plan for one execution date: whole shares, borrow filter, pre-trade checks, CLS orders.

``build_plan`` is pure given an :class:`AccountState` (read-only broker snapshot), an asset lookup
and the target file.  It never sends anything.  ``submit_plan`` is the only function that writes to
the broker; it needs an unblocked plan, the CLS submission window, a clear kill switch and a client
created by the strict paper factory, and it is idempotent through deterministic
``client_order_id``s.  Failing any pre-trade check blocks the whole plan; nothing is trimmed
silently (names rejected by the easy-to-borrow filter are removed and reported, and the residual
exposure goes through the same checks).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from open_composer.book_paper.targets import BookTarget, book_dir
from open_composer.market_sessions import (
    NEW_YORK,
    next_us_equity_session,
    previous_us_equity_session,
    us_equity_session_close,
)

SCHEMA_VERSION = 1
SUBMISSION_MARGIN_MINUTES = 15  # refuse at or after close - 15 min (15:45 ET on a normal day)
MARKET_OPEN = time(9, 30)
ORDER_PAGE_LIMIT = 500


class BookEngineError(RuntimeError):
    """Refusal to build or send a plan (window, blocked plan, unverified client, ...)."""


@dataclass(frozen=True)
class RiskLimits:
    max_abs_net: float = 0.05  # |net dollar| of the stock overlay, fraction of equity
    gross_tolerance: float = 1.05  # post-trade stock gross <= 1.05 x target gross
    max_name_weight: float = 0.0125
    max_gross_leverage: float = 1.98  # long + short + T-bill/core, Reg T overnight 2x with buffer
    max_abs_beta: float = 0.05


@dataclass(frozen=True)
class AccountState:
    """Read-only broker snapshot."""

    equity: float
    positions: dict[str, float]  # signed share quantity, short < 0
    last_equity: float | None = None
    buying_power: float | None = None
    status: str = "ACTIVE"
    shorting_enabled: bool = True
    trading_blocked: bool = False
    open_orders: tuple[tuple[str, str], ...] = ()  # (symbol, client_order_id)


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    easy_to_borrow: bool
    shortable: bool
    tradable: bool
    status: str = "active"


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    value: float | str | None
    limit: float | str | None
    detail: str = ""


@dataclass
class OrderPlan:
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return str(self.payload["status"])

    @property
    def execution_date(self) -> date:
        return date.fromisoformat(self.payload["execution_date"])

    @property
    def orders(self) -> list[dict[str, Any]]:
        return list(self.payload["orders"])

    def to_dict(self) -> dict[str, Any]:
        return self.payload


# --------------------------------------------------------------------------------------
# broker reads (read-only)
# --------------------------------------------------------------------------------------


def read_account_state(client: Any) -> AccountState:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    from open_composer.adapters.broker.alpaca_paper import _client_positions

    account = client.get_account()
    positions: dict[str, float] = {}
    for position in _client_positions(client):
        qty = float(getattr(position, "qty", 0) or 0)
        if _text(getattr(position, "side", "")) == "short" and qty > 0:
            qty = -qty
        positions[str(position.symbol)] = qty
    open_orders = client.get_orders(
        filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=ORDER_PAGE_LIMIT)
    )
    return AccountState(
        equity=float(getattr(account, "equity", 0) or 0),
        positions=positions,
        last_equity=_optional_float(getattr(account, "last_equity", None)),
        buying_power=_optional_float(getattr(account, "buying_power", None)),
        status=_text(getattr(account, "status", "")).upper(),
        shorting_enabled=bool(getattr(account, "shorting_enabled", False)),
        trading_blocked=bool(getattr(account, "trading_blocked", False)),
        open_orders=tuple(
            (str(o.symbol), str(getattr(o, "client_order_id", "") or "")) for o in open_orders
        ),
    )


def make_asset_lookup(client: Any) -> Callable[[str], AssetInfo | None]:
    """GET /v2/assets/{symbol}; ``None`` when the broker does not know the symbol."""

    def lookup(symbol: str) -> AssetInfo | None:
        try:
            asset = client.get_asset(symbol)
        except Exception as exc:
            if (
                getattr(exc, "status_code", None) == 404
                or exc.__class__.__name__ == "NotFoundError"
            ):
                return None
            raise
        return AssetInfo(
            symbol=symbol,
            easy_to_borrow=bool(getattr(asset, "easy_to_borrow", False)),
            shortable=bool(getattr(asset, "shortable", False)),
            tradable=bool(getattr(asset, "tradable", False)),
            status=_text(getattr(asset, "status", "")),
        )

    return lookup


class OrderLookup:
    """Idempotency lookup: broker orders of the execution day by ``client_order_id``."""

    def __init__(self, client: Any, execution_date: date) -> None:
        from alpaca.common.enums import Sort
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        self._client = client
        since = datetime.combine(execution_date, time(0, 0), NEW_YORK).astimezone(UTC)
        orders = list(
            client.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.ALL,
                    after=since,
                    limit=ORDER_PAGE_LIMIT,
                    direction=Sort.DESC,
                )
            )
        )
        self._by_id = {str(getattr(o, "client_order_id", "")): o for o in orders}
        self._truncated = len(orders) >= ORDER_PAGE_LIMIT

    def find(self, client_order_id: str) -> Any | None:
        if client_order_id in self._by_id:
            return self._by_id[client_order_id]
        if not self._truncated or not hasattr(self._client, "get_order_by_client_id"):
            return None
        try:
            return self._client.get_order_by_client_id(client_order_id)
        except Exception as exc:
            if (
                getattr(exc, "status_code", None) == 404
                or exc.__class__.__name__ == "NotFoundError"
            ):
                return None
            raise BookEngineError(f"broker order lookup failed: {exc}") from exc

    def ids(self) -> frozenset[str]:
        return frozenset(self._by_id)


# --------------------------------------------------------------------------------------
# sizing
# --------------------------------------------------------------------------------------


def round_half_away(x: float) -> int:
    """Whole shares, halves away from zero; longs and shorts alike."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x)) if x else 0


def client_order_id(
    book_id: str, account: str, execution_date: date, symbol: str, side: str, qty: int
) -> str:
    raw = f"{book_id}|{account}|{execution_date.isoformat()}|{symbol}|{side}|{qty}"
    return "bk1-" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def build_plan(
    target: BookTarget,
    state: AccountState,
    *,
    as_of: date,
    now: datetime,
    asset_lookup: Callable[[str], AssetInfo | None],
    existing_client_order_ids: Iterable[str] = (),
    min_notional: float = 100.0,
    limits: RiskLimits | None = None,
    kill_switch_check: Callable[[], None] | None = None,
) -> OrderPlan:
    limits = limits or RiskLimits()
    basis = target.equity_basis
    prices = dict(target.reference_prices)
    existing_ids = set(existing_client_order_ids)
    symbols = sorted(set(target.weights) | set(state.positions))
    unpriced = [s for s in symbols if s not in prices]
    fractional_held = [s for s, q in state.positions.items() if abs(q - round(q)) > 1e-9]

    # 1. whole-share targets and raw deltas
    target_qty: dict[str, int] = {}
    for symbol in symbols:
        if symbol in unpriced:
            continue
        weight = target.weights.get(symbol, 0.0)
        target_qty[symbol] = round_half_away(weight * basis / prices[symbol])
    rounding_drift = _one_sided_drift(target, target_qty, prices)

    candidates: list[dict[str, Any]] = []
    for symbol in symbols:
        if symbol in unpriced or symbol in fractional_held:
            continue
        current = int(round(state.positions.get(symbol, 0.0)))
        delta = target_qty[symbol] - current
        if delta:
            candidates.append({"symbol": symbol, "current": current, "delta": delta})

    # 2. minimum notional
    kept: list[dict[str, Any]] = []
    dropped_min: list[dict[str, Any]] = []
    for row in candidates:
        notional = abs(row["delta"]) * prices[row["symbol"]]
        if notional < min_notional:
            dropped_min.append(
                {"symbol": row["symbol"], "delta": row["delta"], "notional": round(notional, 2)}
            )
        else:
            kept.append(row)

    # 3. easy-to-borrow filter for orders that open or increase a short
    accepted: list[dict[str, Any]] = []
    etb_rejections: list[dict[str, Any]] = []
    for row in kept:
        post = row["current"] + row["delta"]
        if row["delta"] < 0 and post < 0:
            reason = _borrow_rejection(asset_lookup(row["symbol"]))
            if reason:
                price = prices[row["symbol"]]
                etb_rejections.append(
                    {
                        "symbol": row["symbol"],
                        "reason": reason,
                        "intended_qty": row["delta"],
                        "intended_notional": round(abs(row["delta"]) * price, 2),
                        "target_weight": target.weights.get(row["symbol"], 0.0),
                        "residual_weight_vs_target": round(
                            row["current"] * price / basis - target.weights.get(row["symbol"], 0.0),
                            8,
                        ),
                    }
                )
                continue
        accepted.append(row)

    post_qty: dict[str, float] = {s: state.positions.get(s, 0.0) for s in symbols}
    for row in accepted:
        post_qty[row["symbol"]] = row["current"] + row["delta"]

    orders = []
    for row in accepted:
        side = "buy" if row["delta"] > 0 else "sell"
        qty = abs(row["delta"])
        cid = client_order_id(
            target.book_id, target.account, target.execution_date, row["symbol"], side, qty
        )
        price = prices[row["symbol"]]
        orders.append(
            {
                "symbol": row["symbol"],
                "side": side,
                "qty": qty,
                "type": "market",
                "time_in_force": "cls",
                "reference_price": price,
                "notional": round(qty * price, 2),
                "current_qty": row["current"],
                "post_qty": row["current"] + row["delta"],
                "opens_or_increases_short": side == "sell" and row["current"] + row["delta"] < 0,
                "client_order_id": cid,
                "already_submitted": cid in existing_ids,
            }
        )

    checks = _risk_checks(
        target,
        state,
        post_qty=post_qty,
        prices=prices,
        planned_symbols={o["symbol"] for o in orders},
        existing_ids=existing_ids,
        as_of=as_of,
        unpriced=unpriced,
        fractional_held=fractional_held,
        limits=limits,
        kill_switch_check=kill_switch_check,
    )
    blocked = [c.name for c in checks if not c.passed]
    final_drift = _one_sided_drift(target, post_qty, prices)
    long_notional, short_notional = _long_short(post_qty, prices, exclude={target.core_symbol})

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": True,
        "as_of": as_of.isoformat(),
        "book_id": target.book_id,
        "account": target.account,
        "form": target.form,
        "decision_date": target.decision_date.isoformat(),
        "execution_date": target.execution_date.isoformat(),
        "target_sha256": target.payload_sha256,
        "equity_basis": basis,
        "equity_live": state.equity,
        "status": "blocked" if blocked else "ok",
        "blocked_by": blocked,
        "min_notional": min_notional,
        "summary": {
            "n_target_names": len(target.stock_weights),
            "n_orders": len(orders),
            "n_buy": sum(o["side"] == "buy" for o in orders),
            "n_sell": sum(o["side"] == "sell" for o in orders),
            "buy_notional": round(sum(o["notional"] for o in orders if o["side"] == "buy"), 2),
            "sell_notional": round(sum(o["notional"] for o in orders if o["side"] == "sell"), 2),
            "post_trade_long_notional": round(long_notional, 2),
            "post_trade_short_notional": round(short_notional, 2),
            "n_etb_rejections": len(etb_rejections),
            "n_dropped_min_notional": len(dropped_min),
            "rounding_drift_one_sided": round(rounding_drift, 8),
            "final_drift_one_sided": round(final_drift, 8),
        },
        "orders": orders,
        "dropped_min_notional": dropped_min,
        "etb_rejections": etb_rejections,
        "checks": [asdict(c) for c in checks],
        "post_trade_qty": {s: q for s, q in sorted(post_qty.items()) if q},
    }
    payload["plan_sha256"] = _plan_hash(payload)
    return OrderPlan(payload)


def _borrow_rejection(asset: AssetInfo | None) -> str:
    if asset is None:
        return "asset_not_found"
    if asset.status.lower() != "active":
        return "asset_not_active"
    if not asset.tradable:
        return "not_tradable"
    if not asset.shortable:
        return "not_shortable"
    if not asset.easy_to_borrow:
        return "not_easy_to_borrow"
    return ""


def _one_sided_drift(
    target: BookTarget, qty: dict[str, int | float], prices: dict[str, float]
) -> float:
    """0.5 * sum |realized - target weight|, weights measured against the equity basis."""
    total = 0.0
    for symbol in set(target.weights) | set(qty):
        price = prices.get(symbol)
        if price is None:
            continue
        realized = qty.get(symbol, 0) * price / target.equity_basis
        total += abs(realized - target.weights.get(symbol, 0.0))
    return total / 2.0


def _long_short(
    qty: dict[str, float], prices: dict[str, float], *, exclude: set[str]
) -> tuple[float, float]:
    long_n = short_n = 0.0
    for symbol, q in qty.items():
        if symbol in exclude or symbol not in prices:
            continue
        value = q * prices[symbol]
        if value > 0:
            long_n += value
        else:
            short_n += -value
    return long_n, short_n


# --------------------------------------------------------------------------------------
# pre-trade risk checks on the post-trade book
# --------------------------------------------------------------------------------------


def freshness_ok(decision_date: date, execution_date: date, as_of: date) -> tuple[bool, str]:
    """The decision date must be the previous session of the execution date, and ``as_of`` must be
    that execution day (or the evening before it, for a dry-run plan)."""
    if us_equity_session_close(execution_date) is None:
        return False, "execution date is not a session"
    if previous_us_equity_session(execution_date) != decision_date:
        return False, "decision date is not the previous session of the execution date"
    if us_equity_session_close(as_of) is not None and as_of != decision_date:
        expected = as_of
    else:
        expected = next_us_equity_session(as_of)
    if expected != execution_date:
        return False, f"as_of {as_of.isoformat()} expects execution on {expected.isoformat()}"
    return True, ""


def _risk_checks(
    target: BookTarget,
    state: AccountState,
    *,
    post_qty: dict[str, float],
    prices: dict[str, float],
    planned_symbols: set[str],
    existing_ids: set[str],
    as_of: date,
    unpriced: list[str],
    fractional_held: list[str],
    limits: RiskLimits,
    kill_switch_check: Callable[[], None] | None,
) -> list[CheckResult]:
    basis = target.equity_basis
    core = target.core_symbol
    results: list[CheckResult] = []

    fresh, why = freshness_ok(target.decision_date, target.execution_date, as_of)
    results.append(
        CheckResult(
            "data_freshness",
            fresh,
            target.decision_date.isoformat(),
            "previous session of the execution date",
            why,
        )
    )

    ks_detail = ""
    ks_ok = True
    if kill_switch_check is not None:
        try:
            kill_switch_check()
        except Exception as exc:
            ks_ok, ks_detail = False, str(exc)
    results.append(
        CheckResult("kill_switch_clear", ks_ok, "clear" if ks_ok else "blocked", "clear", ks_detail)
    )

    short_names = [s for s, q in post_qty.items() if q < 0]
    account_ok = (
        state.status == "ACTIVE"
        and not state.trading_blocked
        and (state.shorting_enabled or not short_names)
    )
    results.append(
        CheckResult(
            "account_ready",
            account_ok,
            f"status={state.status} trading_blocked={state.trading_blocked} "
            f"shorting_enabled={state.shorting_enabled}",
            "ACTIVE, not blocked, shorting enabled when short",
        )
    )
    results.append(
        CheckResult(
            "reference_prices_complete", not unpriced, len(unpriced), 0, ", ".join(unpriced)
        )
    )
    results.append(
        CheckResult(
            "whole_share_positions",
            not fractional_held,
            len(fractional_held),
            0,
            ", ".join(fractional_held),
        )
    )
    foreign = sorted(
        {
            sym
            for sym, cid in state.open_orders
            if sym in planned_symbols and cid not in existing_ids
        }
    )
    results.append(
        CheckResult("no_conflicting_open_orders", not foreign, len(foreign), 0, ", ".join(foreign))
    )

    weights = {s: q * prices[s] / basis for s, q in post_qty.items() if s in prices}
    stock = {s: w for s, w in weights.items() if s != core}
    net = sum(stock.values())
    gross = sum(abs(w) for w in stock.values())
    results.append(
        CheckResult(
            "net_dollar",
            abs(net) <= limits.max_abs_net + 1e-12,
            round(net, 6),
            limits.max_abs_net,
            "stock overlay, core leg excluded",
        )
    )
    gross_limit = limits.gross_tolerance * target.target_gross
    results.append(
        CheckResult(
            "gross_stock",
            gross <= gross_limit + 1e-12,
            round(gross, 6),
            round(gross_limit, 6),
            f"{limits.gross_tolerance} x target gross {target.target_gross:.6f}",
        )
    )
    max_name = max((abs(w) for w in stock.values()), default=0.0)
    over = sorted(s for s, w in stock.items() if abs(w) > limits.max_name_weight + 1e-12)
    results.append(
        CheckResult(
            "max_name_weight",
            not over,
            round(max_name, 6),
            limits.max_name_weight,
            ", ".join(over[:10]),
        )
    )
    leverage = sum(abs(w) for w in weights.values())
    results.append(
        CheckResult(
            "gross_leverage",
            leverage <= limits.max_gross_leverage + 1e-12,
            round(leverage, 6),
            limits.max_gross_leverage,
            "long + short + core leg, fraction of equity",
        )
    )
    missing_exposure = sorted(s for s in stock if abs(stock[s]) > 0 and s not in target.exposures)
    results.append(
        CheckResult(
            "exposures_complete",
            not missing_exposure,
            len(missing_exposure),
            0,
            ", ".join(missing_exposure[:10]),
        )
    )
    beta = sum(target.exposures[s].beta * w for s, w in stock.items() if s in target.exposures)
    results.append(
        CheckResult(
            "beta_neutral",
            abs(beta) <= limits.max_abs_beta + 1e-12,
            round(beta, 6),
            limits.max_abs_beta,
            "sum(beta * weight) over the stock overlay",
        )
    )
    return results


# --------------------------------------------------------------------------------------
# submission window and submit
# --------------------------------------------------------------------------------------


def require_submission_window(now: datetime, execution_date: date) -> None:
    """Refuse before 09:30 ET on the execution date and at or after close - 15 min (15:45 ET)."""
    if now.tzinfo is None:
        raise BookEngineError("submission time must be timezone-aware")
    local = now.astimezone(NEW_YORK)
    close = us_equity_session_close(execution_date)
    if close is None:
        raise BookEngineError("execution date is not a US equity session")
    if local.date() != execution_date:
        raise BookEngineError(
            f"orders are only sent on the execution date {execution_date.isoformat()} "
            f"(ET date is {local.date().isoformat()})"
        )
    if local < datetime.combine(execution_date, MARKET_OPEN, NEW_YORK):
        raise BookEngineError("refusing to send before 09:30 ET on the execution date")
    cutoff = datetime.combine(execution_date, close, NEW_YORK) - timedelta(
        minutes=SUBMISSION_MARGIN_MINUTES
    )
    if local >= cutoff:
        raise BookEngineError(
            f"refusing to send at or after {cutoff.strftime('%H:%M')} ET (CLS margin)"
        )


def submit_plan(
    client: Any,
    plan: OrderPlan,
    *,
    now: datetime,
    kill_switch_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Send the plan's CLS market orders.  Needs an unblocked plan and a verified paper client."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    from open_composer.adapters.broker.alpaca_paper import (
        PaperOrderError,
        _require_verified_paper_client,
    )

    if str(plan.payload.get("book_id", "")).startswith("synthetic"):
        raise BookEngineError("synthetic dry-run targets are never submitted")
    if plan.status != "ok":
        raise BookEngineError("plan is blocked: " + ", ".join(plan.payload.get("blocked_by", [])))
    require_submission_window(now, plan.execution_date)
    try:
        _require_verified_paper_client(client)
    except PaperOrderError as exc:
        raise BookEngineError(str(exc)) from exc
    if kill_switch_check is not None:
        try:
            kill_switch_check()
        except Exception as exc:
            raise BookEngineError(f"kill switch blocks submission: {exc}") from exc

    lookup = OrderLookup(client, plan.execution_date)
    sent: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    ordered = sorted(plan.orders, key=lambda o: (o["side"] != "sell", o["symbol"]))  # sells first
    for order in ordered:
        cid = order["client_order_id"]
        if lookup.find(cid) is not None:
            skipped.append(
                {"symbol": order["symbol"], "client_order_id": cid, "reason": "already at broker"}
            )
            continue
        request = MarketOrderRequest(
            symbol=order["symbol"],
            qty=order["qty"],
            side=OrderSide.BUY if order["side"] == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.CLS,
            client_order_id=cid,
        )
        try:
            result = client.submit_order(request)
        except Exception as exc:
            failed.append(
                {"symbol": order["symbol"], "client_order_id": cid, "error": exc.__class__.__name__}
            )
            continue
        sent.append(
            {
                "symbol": order["symbol"],
                "client_order_id": cid,
                "broker_order_id": str(getattr(result, "id", "")),
                "status": _text(getattr(result, "status", "")),
            }
        )
    return {
        "submitted_at_utc": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan_sha256": plan.payload["plan_sha256"],
        "sent": sent,
        "skipped_existing": skipped,
        "failed": failed,
    }


# --------------------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------------------


def plan_path(root: Path, account: str, execution_date: date) -> Path:
    return book_dir(root, account) / "plans" / f"{execution_date.isoformat()}.json"


def orders_receipt_path(root: Path, account: str, execution_date: date) -> Path:
    return book_dir(root, account) / "orders" / f"{execution_date.isoformat()}.json"


def write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def write_plan_file(root: Path, plan: OrderPlan) -> Path:
    return write_json_atomic(
        plan_path(root, plan.payload["account"], plan.execution_date), plan.to_dict()
    )


def load_plan_file(path: Path) -> OrderPlan:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("plan_sha256") != _plan_hash(payload):
        raise BookEngineError(f"plan file hash mismatch: {Path(path).name}")
    return OrderPlan(payload)


def _plan_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "plan_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _text(value: Any) -> str:
    return (
        str(getattr(value, "value", value) or "").lower()
        if not isinstance(value, str)
        else value.lower()
    )


def _optional_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
