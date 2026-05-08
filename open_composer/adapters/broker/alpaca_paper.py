from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from open_composer.config import (
    alpaca_api_base_url,
    alpaca_api_key_id,
    alpaca_api_secret_key,
    alpaca_paper_enabled,
)
from open_composer.models.paper import PaperOrderRecord
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import append_jsonl


class PaperOrderError(RuntimeError):
    pass


def submit_paper_order(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    qty: float | None = None,
) -> PaperOrderRecord:
    _validate_paper_allowed(spec)
    existing_order = _existing_order(root, signal.id)
    if existing_order:
        return existing_order

    client = client or _trading_client()
    order_qty = qty or _default_quantity(client, spec, signal)
    client_order_id = f"oc-{signal.id}"
    order = _submit_market_order(client, signal, order_qty, client_order_id)
    record = PaperOrderRecord(
        id=str(getattr(order, "id", client_order_id)),
        signal_id=signal.id,
        client_order_id=client_order_id,
        strategy_name=signal.strategy_name,
        symbol=signal.symbol,
        side=signal.side,
        qty=float(order_qty),
        status=str(getattr(order, "status", "submitted")),
        paper=True,
    )
    append_jsonl(root / "reports" / "paper" / "orders.jsonl", [record])
    return record


def sync_paper_orders(root: Path, client: Any | None = None) -> Path:
    client = client or _trading_client()
    orders = client.get_orders()
    rows = [
        {
            "id": str(getattr(order, "id", "")),
            "client_order_id": str(getattr(order, "client_order_id", "")),
            "symbol": str(getattr(order, "symbol", "")),
            "side": str(getattr(order, "side", "")),
            "qty": float(getattr(order, "qty", 0) or 0),
            "status": str(getattr(order, "status", "")),
            "paper": True,
        }
        for order in orders
    ]
    path = root / "reports" / "paper" / "sync.jsonl"
    append_jsonl(path, rows)
    return path


def _validate_paper_allowed(spec: StrategySpec) -> None:
    if spec.lifecycle != "active":
        raise PaperOrderError("paper orders require an active StrategySpec")
    if spec.execution.mode != "paper_auto" or spec.execution.broker != "alpaca_paper":
        raise PaperOrderError(
            "paper orders require execution.mode=paper_auto and broker=alpaca_paper"
        )
    if not alpaca_paper_enabled():
        raise PaperOrderError("ALPACA_PAPER must be true; live broker writes are out of scope")
    if not alpaca_api_key_id() or not alpaca_api_secret_key():
        raise PaperOrderError("Alpaca paper credentials are missing")


def _trading_client() -> Any:
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:
        raise PaperOrderError("alpaca-py is required for Alpaca Paper orders") from exc
    return TradingClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
        paper=True,
        url_override=alpaca_api_base_url(),
    )


def _default_quantity(client: Any, spec: StrategySpec, signal: Signal) -> float:
    try:
        account = client.get_account()
        equity = float(getattr(account, "equity", 0) or 0)
        max_notional = equity * spec.risk.max_position_weight
        return max(1.0, float(math.floor(max_notional / signal.price)))
    except Exception:
        return 1.0


def _submit_market_order(client: Any, signal: Signal, qty: float, client_order_id: str) -> Any:
    try:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
    except ImportError as exc:
        raise PaperOrderError("alpaca-py trading request classes are unavailable") from exc

    side = OrderSide.BUY if signal.side == "buy" else OrderSide.SELL
    request = MarketOrderRequest(
        symbol=signal.symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )
    return client.submit_order(request)


def _existing_order(root: Path, signal_id: str) -> PaperOrderRecord | None:
    path = root / "reports" / "paper" / "orders.jsonl"
    if not path.exists():
        return None
    import json

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("signal_id") == signal_id:
                return PaperOrderRecord.model_validate(record)
    return None
