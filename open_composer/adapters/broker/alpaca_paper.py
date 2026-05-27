from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import (
    alpaca_api_key_id,
    alpaca_api_secret_key,
    alpaca_paper_enabled,
    alpaca_sdk_base_url,
)
from open_composer.models.paper import (
    PaperAccountSnapshot,
    PaperOrderRecord,
    PaperPositionRecord,
)
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.paper_controls import load_paper_kill_switch
from open_composer.router_authorization import assess_router_order_authorization, is_router_strategy
from open_composer.storage import append_jsonl, write_json


class PaperOrderError(RuntimeError):
    pass


def submit_paper_order(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    qty: float | None = None,
) -> PaperOrderRecord:
    _validate_paper_allowed(spec, root)
    kill_switch = load_paper_kill_switch(root)
    if kill_switch.enabled:
        raise PaperOrderError(
            "paper kill switch is enabled"
            + (f": {kill_switch.reason}" if kill_switch.reason else "")
        )
    existing_order = _existing_order(root, signal.id)
    if existing_order:
        return existing_order

    client = client or _trading_client()
    signal_qty = getattr(signal, "qty", None)
    order_qty = (
        qty
        if qty is not None
        else signal_qty
        if signal_qty is not None
        else _default_quantity(client, spec, signal)
    )
    client_order_id = f"oc-{signal.id}"
    order = _submit_policy_order(client, signal, spec, root, order_qty, client_order_id)
    record = PaperOrderRecord(
        id=str(getattr(order, "id", client_order_id)),
        signal_id=signal.id,
        client_order_id=client_order_id,
        strategy_name=signal.strategy_name,
        strategy_id=signal.strategy_id or spec.name,
        version_id=signal.version_id,
        spec_hash=signal.spec_hash,
        strategy_backend=signal.strategy_backend,
        execution_backend=signal.execution_backend,
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
    write_json(
        root / "reports" / "paper" / "open_orders.json",
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "orders": rows,
            "paper": True,
        },
    )
    return path


def sync_paper_account(root: Path, client: Any | None = None) -> tuple[Path, Path]:
    client = client or _trading_client()
    account = client.get_account()
    positions = _client_positions(client)
    account_snapshot = PaperAccountSnapshot(
        equity=_optional_float(getattr(account, "equity", None)),
        cash=_optional_float(getattr(account, "cash", None)),
        buying_power=_optional_float(getattr(account, "buying_power", None)),
        portfolio_value=_optional_float(getattr(account, "portfolio_value", None)),
        status=str(getattr(account, "status", "")),
        paper=True,
    )
    position_records = [
        PaperPositionRecord(
            symbol=str(getattr(position, "symbol", "")),
            qty=_optional_float(getattr(position, "qty", None)) or 0.0,
            market_value=_optional_float(getattr(position, "market_value", None)),
            cost_basis=_optional_float(getattr(position, "cost_basis", None)),
            unrealized_pl=_optional_float(getattr(position, "unrealized_pl", None)),
            unrealized_plpc=_optional_float(getattr(position, "unrealized_plpc", None)),
            current_price=_optional_float(getattr(position, "current_price", None)),
            side=str(getattr(position, "side", "")),
            paper=True,
        )
        for position in positions
    ]
    account_path = root / "reports" / "paper" / "account.json"
    positions_path = root / "reports" / "paper" / "positions.json"
    write_json(account_path, account_snapshot)
    write_json(
        positions_path, {"positions": [item.model_dump(mode="json") for item in position_records]}
    )
    return account_path, positions_path


def _validate_paper_allowed(spec: StrategySpec, root: Path) -> None:
    if spec.lifecycle != "active":
        raise PaperOrderError("paper orders require an active StrategySpec")
    if spec.execution.mode != "paper_auto" or spec.execution.broker != "alpaca_paper":
        raise PaperOrderError(
            "paper orders require execution.mode=paper_auto and broker=alpaca_paper"
        )
    if spec.position_direction in {"short_only", "long_short"}:
        raise PaperOrderError("short paper orders require separate short-readiness authorization")
    if is_router_strategy(spec):
        router_auth = assess_router_order_authorization(spec, root)
        if not router_auth.authorized:
            raise PaperOrderError(router_auth.message)
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
        url_override=alpaca_sdk_base_url(),
    )


def _default_quantity(client: Any, spec: StrategySpec, signal: Signal) -> float:
    try:
        account = client.get_account()
        equity = float(getattr(account, "equity", 0) or 0)
        max_notional = equity * spec.risk.max_position_weight
        return max(1.0, float(math.floor(max_notional / signal.price)))
    except Exception:
        return 1.0


def _submit_policy_order(
    client: Any,
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    qty: float,
    client_order_id: str,
) -> Any:
    policy = _execution_policy(spec, root)
    if policy and str(policy.get("time_in_force", "")).lower() == "opg":
        limit_price = _policy_limit_price(signal, policy)
        if limit_price is not None:
            return _submit_limit_order(
                client,
                signal,
                qty,
                client_order_id,
                limit_price=limit_price,
                time_in_force="opg",
            )
    return _submit_market_order(client, signal, qty, client_order_id)


def _execution_policy(spec: StrategySpec, root: Path) -> dict[str, Any] | None:
    if spec.execution_policy is not None:
        return spec.execution_policy.model_dump(mode="json")
    path = root / "reports" / "harness" / "execution" / f"{spec.name}-execution-policy.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _policy_limit_price(signal: Signal, policy: dict[str, Any]) -> float | None:
    style = str(policy.get("order_style") or "")
    if style not in {"opg_limit", "loo_limit"}:
        return None
    protection = policy.get("price_protection")
    if not isinstance(protection, dict):
        protection = {}
    offset_bps = protection.get("limit_offset_bps")
    if offset_bps is None:
        return round(float(signal.price), 2)
    offset = float(offset_bps) / 10_000.0
    multiplier = 1 + offset if signal.side == "buy" else 1 - offset
    return round(float(signal.price) * multiplier, 2)


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


def _submit_limit_order(
    client: Any,
    signal: Signal,
    qty: float,
    client_order_id: str,
    *,
    limit_price: float,
    time_in_force: str,
) -> Any:
    try:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest
    except ImportError as exc:
        raise PaperOrderError("alpaca-py trading limit request classes are unavailable") from exc

    side = OrderSide.BUY if signal.side == "buy" else OrderSide.SELL
    tif = getattr(TimeInForce, time_in_force.upper())
    request = LimitOrderRequest(
        symbol=signal.symbol,
        qty=qty,
        side=side,
        time_in_force=tif,
        limit_price=limit_price,
        client_order_id=client_order_id,
    )
    return client.submit_order(request)


def _client_positions(client: Any) -> list[Any]:
    if hasattr(client, "get_all_positions"):
        return list(client.get_all_positions())
    if hasattr(client, "get_positions"):
        return list(client.get_positions())
    return []


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
