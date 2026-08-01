from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from open_composer.config import (
    alpaca_api_key_id,
    alpaca_api_secret_key,
    alpaca_paper_enabled,
    alpaca_sdk_base_url,
)
from open_composer.execution_policy import (
    ExecutionPolicyBinding,
    require_orderable_execution_policy,
)
from open_composer.models.paper import (
    PaperAccountSnapshot,
    PaperOrderIntent,
    PaperOrderRecord,
    PaperPositionRecord,
)
from open_composer.models.signal import Signal, signal_record_hash
from open_composer.models.strategy_spec import StrategySpec
from open_composer.paper_authorization import (
    PaperOrderAuthorizationStatus,
    assess_paper_canary_authorization,
    assess_paper_order_authorization,
    broker_account_id_hash,
    require_paper_submission_authorization_effective_at,
    revalidate_paper_submission_authorization,
)
from open_composer.paper_controls import load_paper_kill_switch
from open_composer.paper_freshness import require_fresh_paper_signal, require_paper_order_window
from open_composer.paper_lock import paper_control_lock, paper_submission_lock
from open_composer.storage import find_signal_record, write_json
from open_composer.strategy_versions import strategy_content_hash, strategy_version_id


class PaperOrderError(RuntimeError):
    pass


class PaperTargetSatisfiedError(PaperOrderError):
    """The broker position or pending order already satisfies a target signal."""


ALPACA_PAPER_ORIGIN = "https://paper-api.alpaca.markets"
_PAPER_CLIENT_VERIFICATION_TOKEN = object()
_PAPER_BROKER_WRITE_TOKEN = object()
_CONSUMED_WRITE_GUARDS: set[str] = set()
_WRITE_GUARD_LOCK = threading.Lock()
TERMINAL_ORDER_STATUSES = {
    "canceled",
    "cancelled",
    "done_for_day",
    "expired",
    "filled",
    "rejected",
    "replaced",
}
KNOWN_ORDER_STATUSES = TERMINAL_ORDER_STATUSES | {
    "accepted",
    "accepted_for_bidding",
    "calculated",
    "held",
    "new",
    "partially_filled",
    "pending_cancel",
    "pending_new",
    "pending_replace",
    "stopped",
    "submitted",
    "suspended",
}


@dataclass(frozen=True)
class PaperSubmissionContext:
    policy: ExecutionPolicyBinding
    authorization: PaperOrderAuthorizationStatus


@dataclass(frozen=True)
class _PaperBrokerWriteGuard:
    root: Path
    spec: StrategySpec
    context: PaperSubmissionContext
    nonce: str
    signal_id: str
    signal_record_hash: str
    intent_id: str
    intent_hash: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    order_style: str
    time_in_force: str
    limit_price: float | None
    target_resolution: _TargetOrderResolution | None
    verification_token: object


@dataclass(frozen=True)
class _TargetOrderResolution:
    qty: float | None
    requested_target_weight: float
    effective_target_weight: float
    pretrade_position_qty: float
    target_position_qty: float
    canary_position_limit_usd: float | None
    risk_effect: Literal["increase", "reduce"] | None


def submit_paper_order(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    qty: float | None = None,
) -> PaperOrderRecord:
    with paper_submission_lock(root):
        return _submit_paper_order_locked(signal, spec, root, client=client, qty=qty)


def _submit_paper_order_locked(
    signal: Signal,
    spec: StrategySpec,
    root: Path,
    client: Any | None = None,
    qty: float | None = None,
) -> PaperOrderRecord:
    _require_kill_switch_clear(root)
    context = _validate_paper_allowed(spec, root)
    signal_binding = _validate_logged_signal(signal, spec, root)
    try:
        require_fresh_paper_signal(signal_binding.signal)
        require_paper_order_window(spec, context.policy)
    except ValueError as exc:
        raise PaperOrderError(str(exc)) from exc
    existing_order = _existing_order(root, signal.id)
    if existing_order:
        _validate_existing_order(existing_order, signal_binding.record_hash, context)
        return existing_order

    client = client or _trading_client()
    _require_verified_paper_client(client)
    _require_broker_reconciliation(client)
    signal_qty = getattr(signal, "qty", None)
    if context.authorization.kind == "canary" and (
        qty is not None or signal_qty is not None or signal.target_weight is None
    ):
        raise PaperOrderError(
            "paper canary orders require a position-aware target_weight and prohibit "
            "quantity overrides"
        )
    reference_price = _estimated_order_reference_price(signal_binding.signal, context.policy)
    target_resolution = (
        _resolve_target_order(
            client,
            spec,
            signal,
            reference_price=reference_price,
            canary_limits=(
                context.authorization.payload.get("limits")
                if context.authorization.kind == "canary"
                else None
            ),
        )
        if signal.target_weight is not None
        else None
    )
    target_qty = target_resolution.qty if target_resolution is not None else None
    if target_resolution is not None and target_qty is None:
        raise PaperTargetSatisfiedError("target is already satisfied or has a pending broker order")
    if target_resolution is not None:
        for label, supplied in (("requested", qty), ("signal", signal_qty)):
            if supplied is not None and abs(float(supplied) - target_qty) > 1e-9:
                raise PaperOrderError(
                    f"{label} qty={float(supplied):.8g} does not match "
                    f"target delta qty={target_qty:.8g}"
                )
        order_qty = target_qty
    else:
        safe_quantity = _default_quantity(client, spec, signal)
        order_qty = (
            qty if qty is not None else signal_qty if signal_qty is not None else safe_quantity
        )
        if float(order_qty) > safe_quantity + 1e-9:
            raise PaperOrderError(
                f"paper order qty={float(order_qty):.8g} exceeds safe qty={safe_quantity:.8g}"
            )
    if not math.isfinite(float(order_qty)) or float(order_qty) <= 0:
        raise PaperOrderError("paper order quantity must be finite and positive")
    client_order_id = f"oc-{signal.id}"
    estimated_notional = float(order_qty) * reference_price
    intent_id = _order_intent_id(
        client_order_id,
        signal_binding.record_hash,
        context,
    )
    if context.authorization.kind == "canary":
        _enforce_canary_order_limits(
            root,
            client,
            spec,
            signal_binding.signal,
            context,
            intent_id=intent_id,
            order_qty=float(order_qty),
            reference_price=reference_price,
            estimated_notional=estimated_notional,
            risk_effect=(target_resolution.risk_effect if target_resolution else None),
        )
    intent, intent_hash = _prepare_order_intent(
        root,
        signal_binding.signal,
        signal_binding.log_path,
        signal_binding.record_hash,
        context,
        intent_id=intent_id,
        order_qty=float(order_qty),
        reference_price=reference_price,
        estimated_notional=estimated_notional,
        client_order_id=client_order_id,
        target_resolution=target_resolution,
    )
    _require_kill_switch_clear(root)
    order = _broker_order_by_client_id(client, client_order_id)
    if order is None:
        context, write_guard = _build_paper_broker_write_guard(
            spec,
            root,
            context,
            signal=signal_binding.signal,
            signal_record_hash=signal_binding.record_hash,
            intent=intent,
            intent_hash=intent_hash,
            order_qty=float(order_qty),
            client_order_id=client_order_id,
            target_resolution=target_resolution,
        )
        order = _submit_policy_order(
            client,
            signal_binding.signal,
            context.policy,
            float(order_qty),
            client_order_id,
            write_guard=write_guard,
        )
    authorization_payload = context.authorization.payload
    order_style = str(context.policy.payload.get("order_style") or "").lower()
    time_in_force = str(context.policy.payload.get("time_in_force") or "").lower()
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
        execution_policy_id=context.policy.policy_id,
        execution_policy_hash=context.policy.content_hash,
        order_style=order_style,
        time_in_force=time_in_force,
        authorization_id=str(authorization_payload["authorization_id"]),
        authorization_hash=str(context.authorization.content_hash),
        authorization_kind=(
            context.authorization.kind if context.authorization.kind != "none" else None
        ),
        signal_record_hash=signal_binding.record_hash,
        signal_log_path=_relpath(signal_binding.log_path, root),
        order_intent_id=intent.id,
        order_intent_hash=intent_hash,
        symbol=signal.symbol,
        side=signal.side,
        qty=float(order_qty),
        reference_price=reference_price,
        estimated_notional=estimated_notional,
        requested_target_weight=(
            target_resolution.requested_target_weight if target_resolution else None
        ),
        effective_target_weight=(
            target_resolution.effective_target_weight if target_resolution else None
        ),
        pretrade_position_qty=(
            target_resolution.pretrade_position_qty if target_resolution else None
        ),
        target_position_qty=(target_resolution.target_position_qty if target_resolution else None),
        canary_position_limit_usd=(
            target_resolution.canary_position_limit_usd if target_resolution else None
        ),
        risk_effect=(target_resolution.risk_effect if target_resolution else None),
        status=str(getattr(order, "status", "submitted")),
        paper=True,
    )
    initial_order = _normalize_broker_order(order)
    initial_order["client_order_id"] = initial_order["client_order_id"] or client_order_id
    initial_order["symbol"] = initial_order["symbol"] or signal.symbol
    initial_order["side"] = initial_order["side"] or signal.side
    initial_order["qty"] = initial_order["qty"] or float(order_qty)
    initial_order["order_type"] = initial_order["order_type"] or _broker_order_type(order_style)
    initial_order["time_in_force"] = initial_order["time_in_force"] or time_in_force
    initial_receipt = _write_immutable_broker_receipt(
        root,
        initial_order,
        record,
        broker_account_hash=_client_broker_account_hash(client, root),
        captured_at=datetime.now(UTC),
        local_binding_status="prepared",
    )
    initial_receipt_payload = json.loads(initial_receipt.read_text(encoding="utf-8"))
    record = record.model_copy(
        update={
            "initial_broker_receipt_path": _relpath(initial_receipt, root),
            "initial_broker_receipt_hash": _sha256_file(initial_receipt),
            "broker_state_hash": initial_receipt_payload["state_sha256"],
        }
    )
    _append_jsonl_durable(root / "reports" / "paper" / "orders.jsonl", record)
    return record


def _require_kill_switch_clear(
    root: Path,
) -> None:
    try:
        kill_switch = load_paper_kill_switch(root, require_control_file=True)
    except FileNotFoundError as exc:
        raise PaperOrderError("paper kill-switch control file is missing") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PaperOrderError("paper kill-switch control file is invalid") from exc
    if kill_switch.enabled:
        raise PaperOrderError(
            "paper kill switch is enabled"
            + (f": {kill_switch.reason}" if kill_switch.reason else "")
        )


def _revalidate_submission_authorization(
    spec: StrategySpec,
    root: Path,
    context: PaperSubmissionContext,
) -> PaperSubmissionContext:
    try:
        authorization = revalidate_paper_submission_authorization(
            spec,
            root,
            context.authorization,
        )
    except ValueError as exc:
        raise PaperOrderError(str(exc)) from exc
    return PaperSubmissionContext(policy=context.policy, authorization=authorization)


def _build_paper_broker_write_guard(
    spec: StrategySpec,
    root: Path,
    context: PaperSubmissionContext,
    *,
    signal: Signal,
    signal_record_hash: str,
    intent: PaperOrderIntent,
    intent_hash: str,
    order_qty: float,
    client_order_id: str,
    target_resolution: _TargetOrderResolution | None,
) -> tuple[PaperSubmissionContext, _PaperBrokerWriteGuard]:
    current = _revalidate_submission_authorization(spec, root, context)
    _require_kill_switch_clear(root)
    order_style = str(current.policy.payload.get("order_style") or "").lower()
    time_in_force = str(current.policy.payload.get("time_in_force") or "").lower()
    return current, _PaperBrokerWriteGuard(
        root=root,
        spec=spec,
        context=current,
        nonce=secrets.token_hex(16),
        signal_id=signal.id,
        signal_record_hash=signal_record_hash,
        intent_id=intent.id,
        intent_hash=intent_hash,
        client_order_id=client_order_id,
        symbol=signal.symbol,
        side=signal.side,
        qty=order_qty,
        order_style=order_style,
        time_in_force=time_in_force,
        limit_price=_policy_limit_price(signal, current.policy.payload),
        target_resolution=target_resolution,
        verification_token=_PAPER_BROKER_WRITE_TOKEN,
    )


def sync_paper_orders(root: Path, client: Any | None = None) -> Path:
    client = client or _trading_client()
    _require_verified_paper_client(client)
    captured_at = datetime.now(UTC)
    orders = _get_broker_orders(client, include_closed=True)
    account_hash = _client_broker_account_hash(client, root)
    if account_hash is None:
        raise PaperOrderError("Alpaca Paper order sync could not bind the broker account")
    local_orders = _local_orders_by_client_id(root)
    broker_client_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for order in orders:
        normalized = _normalize_broker_order(order)
        _validate_normalized_broker_order(normalized)
        broker_client_ids.add(str(normalized["client_order_id"]))
        local_order = local_orders.get(str(normalized["client_order_id"]))
        if local_order is not None:
            _validate_broker_local_order_match(normalized, local_order)
        receipt_path = _write_immutable_broker_receipt(
            root,
            normalized,
            local_order,
            broker_account_hash=account_hash,
            captured_at=captured_at,
        )
        receipt_ref = {
            "order_id": normalized["id"],
            "path": _relpath(receipt_path, root),
            "sha256": _sha256_file(receipt_path),
            "state_sha256": json.loads(receipt_path.read_text(encoding="utf-8"))["state_sha256"],
        }
        receipts.append(receipt_ref)
        rows.append(
            {
                **normalized,
                "observed_at": captured_at.isoformat(),
                "broker_account_id_hash": account_hash,
                "broker_receipt_path": receipt_ref["path"],
                "broker_receipt_sha256": receipt_ref["sha256"],
                "paper": True,
            }
        )
    missing_local = sorted(set(local_orders) - broker_client_ids)
    if missing_local:
        raise PaperOrderError(
            "Alpaca Paper sync omitted locally submitted orders: " + ", ".join(missing_local)
        )
    path = root / "reports" / "paper" / "sync.jsonl"
    for row in rows:
        _append_jsonl_durable(path, row)
    open_rows = [row for row in rows if str(row.get("status")) not in TERMINAL_ORDER_STATUSES]
    write_json(
        root / "reports" / "paper" / "open_orders.json",
        {
            "generated_at": captured_at.isoformat(),
            "orders": open_rows,
            "paper": True,
        },
    )
    _write_broker_sync_receipt(
        root,
        captured_at=captured_at,
        broker_account_hash=account_hash,
        receipts=receipts,
        local_order_count=len(local_orders),
    )
    return path


def sync_paper_account(root: Path, client: Any | None = None) -> tuple[Path, Path]:
    client = client or _trading_client()
    _require_verified_paper_client(client)
    account = client.get_account()
    account_id_hash = _optional_broker_account_hash(getattr(account, "id", None))
    if account_id_hash is None:
        raise PaperOrderError("Alpaca Paper account sync requires a broker account id")
    positions = _client_positions(client)
    generated_at = datetime.now(UTC)
    account_snapshot = PaperAccountSnapshot(
        generated_at=generated_at,
        equity=_optional_float(getattr(account, "equity", None)),
        cash=_optional_float(getattr(account, "cash", None)),
        buying_power=_optional_float(getattr(account, "buying_power", None)),
        portfolio_value=_optional_float(getattr(account, "portfolio_value", None)),
        broker_account_id_hash=account_id_hash,
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
            updated_at=generated_at,
            paper=True,
        )
        for position in positions
    ]
    account_path = root / "reports" / "paper" / "account.json"
    positions_path = root / "reports" / "paper" / "positions.json"
    write_json(account_path, account_snapshot)
    write_json(
        positions_path,
        {
            "generated_at": generated_at.isoformat(),
            "paper": True,
            "positions": [item.model_dump(mode="json") for item in position_records],
        },
    )
    return account_path, positions_path


def _validate_paper_allowed(spec: StrategySpec, root: Path) -> PaperSubmissionContext:
    from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec

    if spec.lifecycle != "active":
        raise PaperOrderError("paper orders require an active StrategySpec")
    if spec.execution.mode != "paper_auto" or spec.execution.broker != "alpaca_paper":
        raise PaperOrderError(
            "paper orders require execution.mode=paper_auto and broker=alpaca_paper"
        )
    readiness = assess_paper_strategy_readiness_for_spec(spec, root)
    if readiness.execution_substate == "order_authorized" and readiness.status == "ok":
        authorization = assess_paper_order_authorization(spec, root)
    elif readiness.execution_substate == "canary_authorized" and readiness.status == "warning":
        authorization = assess_paper_canary_authorization(spec, root)
    else:
        raise PaperOrderError("paper orders require an explicit bounded canary authorization")
    if spec.position_direction in {"short_only", "long_short"}:
        raise PaperOrderError("short paper orders require separate short-readiness authorization")
    try:
        policy = require_orderable_execution_policy(spec, root)
    except ValueError as exc:
        raise PaperOrderError(str(exc)) from exc
    if not authorization.authorized:
        raise PaperOrderError(authorization.message)
    if not alpaca_paper_enabled():
        raise PaperOrderError("ALPACA_PAPER must be true; live broker writes are out of scope")
    if not alpaca_api_key_id() or not alpaca_api_secret_key():
        raise PaperOrderError("Alpaca paper credentials are missing")
    return PaperSubmissionContext(policy=policy, authorization=authorization)


def _trading_client() -> Any:
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:
        raise PaperOrderError("alpaca-py is required for Alpaca Paper orders") from exc
    base_url = _require_configured_paper_origin()
    client = TradingClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
        paper=True,
        url_override=base_url,
    )
    return _mark_verified_paper_client(client, origin=base_url)


def _require_configured_paper_origin() -> str:
    value = alpaca_sdk_base_url().rstrip("/")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    valid = (
        parsed.scheme == "https"
        and parsed.hostname == "paper-api.alpaca.markets"
        and port in {None, 443}
        and parsed.path in {"", "/"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise PaperOrderError("Alpaca Paper submissions require https://paper-api.alpaca.markets")
    return ALPACA_PAPER_ORIGIN


def _default_quantity(client: Any, spec: StrategySpec, signal: Signal) -> float:
    try:
        account = client.get_account()
        equity = float(getattr(account, "equity", 0) or 0)
        if not math.isfinite(equity) or equity <= 0:
            raise PaperOrderError("paper account equity must be finite and positive")
        if not math.isfinite(float(signal.price)) or float(signal.price) <= 0:
            raise PaperOrderError("signal price must be finite and positive")
        if signal.action == "exit":
            current_qty = _position_quantity(client, signal.symbol)
            if current_qty <= 0:
                raise PaperOrderError(f"cannot exit {signal.symbol}: paper position is flat")
            return current_qty
        max_notional = equity * spec.risk.max_position_weight
        quantity = float(math.floor(max_notional / signal.price))
        if quantity < 1:
            raise PaperOrderError(
                f"target notional {max_notional:.2f} cannot buy one share at {signal.price:.2f}"
            )
        return quantity
    except PaperOrderError:
        raise
    except Exception as exc:
        raise PaperOrderError(f"could not calculate paper order quantity: {exc}") from exc


def resolve_target_order_quantity(
    client: Any,
    spec: StrategySpec,
    signal: Signal,
) -> float | None:
    return _resolve_target_order(
        client,
        spec,
        signal,
        reference_price=float(signal.price),
        canary_limits=None,
    ).qty


def _resolve_target_order(
    client: Any,
    spec: StrategySpec,
    signal: Signal,
    *,
    reference_price: float,
    canary_limits: Any,
) -> _TargetOrderResolution:
    if (
        spec.portfolio.mode == "single_symbol"
        and spec.portfolio.position_weight_enforcement != "entry_only"
    ):
        raise PaperOrderError("continuous single-symbol target enforcement is not implemented")
    if signal.target_weight is None:
        raise PaperOrderError("target order resolution requires target_weight")
    target_weight = float(signal.target_weight or 0.0)
    allowed_weight = (
        float(spec.risk.max_position_weight)
        if spec.portfolio.mode == "single_symbol"
        else min(
            float(spec.portfolio.gross_exposure_limit or 1.0),
            float(spec.portfolio.max_symbol_weight or 1.0),
        )
    )
    if target_weight < 0 or target_weight > allowed_weight:
        raise PaperOrderError(
            f"target_weight must be between 0 and {allowed_weight:.8g}; "
            f"received {target_weight:.8g}"
        )
    if spec.portfolio.mode == "single_symbol" and target_weight not in {0.0, allowed_weight}:
        raise PaperOrderError(
            f"single-symbol target_weight must be 0 or {allowed_weight:.8g}; "
            f"received {target_weight:.8g}"
        )
    if not math.isfinite(reference_price) or reference_price <= 0:
        raise PaperOrderError("paper order reference price must be finite and positive")
    current_qty = _position_quantity(client, signal.symbol)
    if current_qty < 0:
        raise PaperOrderError("short paper position is outside the long-only target contract")
    if spec.portfolio.mode == "single_symbol":
        if target_weight == 0.0:
            if signal.action != "exit":
                raise PaperOrderError("zero target_weight requires an exit action")
        elif signal.action != "entry":
            raise PaperOrderError("positive target_weight requires an entry action")
    account = client.get_account()
    equity = float(getattr(account, "equity", 0) or 0)
    if not math.isfinite(equity) or equity <= 0:
        raise PaperOrderError("paper account equity must be finite and positive")
    canary_position_limit = (
        _effective_canary_position_limit(canary_limits, equity)
        if canary_limits is not None
        else None
    )
    target_notional = equity * target_weight
    if canary_position_limit is not None:
        target_notional = min(target_notional, canary_position_limit)
    desired_qty = float(math.floor(target_notional / reference_price))
    if target_weight > 0 and desired_qty < 1:
        raise PaperOrderError(
            f"effective target notional {target_notional:.2f} cannot buy one share "
            f"at {reference_price:.2f}"
        )
    effective_target_weight = (desired_qty * reference_price) / equity
    no_change = _has_open_symbol_order(client, signal.symbol) or (
        spec.portfolio.mode == "single_symbol" and target_weight > 0 and current_qty > 0
    )
    delta = desired_qty - current_qty
    if no_change or abs(delta) < 1e-9:
        return _TargetOrderResolution(
            qty=None,
            requested_target_weight=target_weight,
            effective_target_weight=effective_target_weight,
            pretrade_position_qty=current_qty,
            target_position_qty=desired_qty,
            canary_position_limit_usd=canary_position_limit,
            risk_effect=None,
        )
    expected_side = "buy" if delta > 0 else "sell"
    if signal.side != expected_side:
        raise PaperOrderError(
            f"signal side={signal.side} conflicts with broker target delta side={expected_side}"
        )
    return _TargetOrderResolution(
        qty=abs(delta),
        requested_target_weight=target_weight,
        effective_target_weight=effective_target_weight,
        pretrade_position_qty=current_qty,
        target_position_qty=desired_qty,
        canary_position_limit_usd=canary_position_limit,
        risk_effect="increase" if delta > 0 else "reduce",
    )


def _effective_canary_position_limit(limits: Any, equity: float) -> float:
    if not isinstance(limits, dict):
        raise PaperOrderError("paper canary authorization limits are missing")
    try:
        max_order_notional = float(limits["max_order_notional_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PaperOrderError("paper canary authorization limits are malformed") from exc
    if not math.isfinite(max_order_notional) or max_order_notional <= 0:
        raise PaperOrderError("paper canary authorization limits are malformed")
    return min(max_order_notional, equity * 0.01)


def _position_quantity(client: Any, symbol: str) -> float:
    if not hasattr(client, "get_all_positions") and not hasattr(client, "get_positions"):
        raise PaperOrderError("paper position reconciliation is unavailable")
    selected = symbol.upper()
    for position in _client_positions(client):
        if str(getattr(position, "symbol", "")).upper() != selected:
            continue
        quantity = float(getattr(position, "qty", 0) or 0)
        if not math.isfinite(quantity):
            raise PaperOrderError(f"paper position quantity for {selected} is nonfinite")
        return quantity
    return 0.0


def _has_open_symbol_order(client: Any, symbol: str) -> bool:
    if not hasattr(client, "get_orders"):
        raise PaperOrderError("paper open-order reconciliation is unavailable")
    selected = symbol.upper()
    for order in _get_broker_orders(client, include_closed=False):
        order_symbol = str(getattr(order, "symbol", "")).upper()
        status = str(getattr(order, "status", "")).lower().split(".")[-1]
        if status not in KNOWN_ORDER_STATUSES:
            raise PaperOrderError(f"unrecognized Alpaca Paper order status={status}")
        if order_symbol == selected and status not in TERMINAL_ORDER_STATUSES:
            return True
    return False


def _submit_policy_order(
    client: Any,
    signal: Signal,
    policy: ExecutionPolicyBinding,
    qty: float,
    client_order_id: str,
    *,
    write_guard: _PaperBrokerWriteGuard,
) -> Any:
    payload = policy.payload
    style = str(payload["order_style"]).lower()
    time_in_force = str(payload["time_in_force"]).lower()
    limit_price = _policy_limit_price(signal, payload)
    _require_paper_broker_write_guard(
        write_guard,
        policy=policy,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style=style,
        time_in_force=time_in_force,
        limit_price=limit_price,
    )
    if style in {"opg_limit", "loo_limit"}:
        if limit_price is None:
            raise PaperOrderError(f"execution policy {policy.policy_id} has no limit price")
        return _submit_limit_order(
            client,
            signal,
            qty,
            client_order_id,
            limit_price=limit_price,
            time_in_force=time_in_force,
            write_guard=write_guard,
        )
    if style in {"day_market", "moo_market"}:
        return _submit_market_order(
            client,
            signal,
            qty,
            client_order_id,
            time_in_force=time_in_force,
            write_guard=write_guard,
        )
    raise PaperOrderError(f"unsupported paper order_style: {style}")


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


def _submit_market_order(
    client: Any,
    signal: Signal,
    qty: float,
    client_order_id: str,
    *,
    time_in_force: str,
    write_guard: _PaperBrokerWriteGuard | None = None,
) -> Any:
    _require_paper_broker_write_guard(
        write_guard,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style="day_market" if time_in_force == "day" else "moo_market",
        time_in_force=time_in_force,
        limit_price=None,
    )
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
        time_in_force=getattr(TimeInForce, time_in_force.upper()),
        client_order_id=client_order_id,
    )
    return _submit_verified_paper_request(
        client,
        request,
        write_guard,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style="day_market" if time_in_force == "day" else "moo_market",
        time_in_force=time_in_force,
        limit_price=None,
    )


def _submit_limit_order(
    client: Any,
    signal: Signal,
    qty: float,
    client_order_id: str,
    *,
    limit_price: float,
    time_in_force: str,
    write_guard: _PaperBrokerWriteGuard | None = None,
) -> Any:
    _require_paper_broker_write_guard(
        write_guard,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style=(
            str(write_guard.order_style) if isinstance(write_guard, _PaperBrokerWriteGuard) else ""
        ),
        time_in_force=time_in_force,
        limit_price=limit_price,
    )
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
    return _submit_verified_paper_request(
        client,
        request,
        write_guard,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style=(
            str(write_guard.order_style) if isinstance(write_guard, _PaperBrokerWriteGuard) else ""
        ),
        time_in_force=time_in_force,
        limit_price=limit_price,
    )


def _require_paper_broker_write_guard(
    guard: _PaperBrokerWriteGuard | None,
    *,
    policy: ExecutionPolicyBinding | None = None,
    signal: Signal | None = None,
    qty: float | None = None,
    client_order_id: str | None = None,
    order_style: str | None = None,
    time_in_force: str | None = None,
    limit_price: float | None = None,
) -> _PaperBrokerWriteGuard:
    if not isinstance(guard, _PaperBrokerWriteGuard) or (
        guard.verification_token is not _PAPER_BROKER_WRITE_TOKEN
    ):
        raise PaperOrderError("Alpaca Paper broker write requires a verified submission guard")
    current_policy_hash = _canonical_payload_hash(guard.context.policy.payload)
    if current_policy_hash != guard.context.policy.content_hash:
        raise PaperOrderError("Alpaca Paper broker write guard policy payload was mutated")
    if policy is not None and (
        guard.context.policy.policy_id != policy.policy_id
        or guard.context.policy.content_hash != policy.content_hash
        or _canonical_payload_hash(policy.payload) != policy.content_hash
    ):
        raise PaperOrderError("Alpaca Paper broker write guard policy binding is stale")
    mismatches: list[str] = []
    if signal is not None:
        if signal.id != guard.signal_id or signal_record_hash(signal) != guard.signal_record_hash:
            mismatches.append("signal")
        if signal.symbol != guard.symbol:
            mismatches.append("symbol")
        if signal.side != guard.side:
            mismatches.append("side")
    if qty is not None and abs(float(qty) - guard.qty) > 1e-9:
        mismatches.append("qty")
    if client_order_id is not None and client_order_id != guard.client_order_id:
        mismatches.append("client_order_id")
    if order_style is not None and order_style != guard.order_style:
        mismatches.append("order_style")
    if time_in_force is not None and time_in_force != guard.time_in_force:
        mismatches.append("time_in_force")
    if (limit_price is None) != (guard.limit_price is None) or (
        limit_price is not None
        and guard.limit_price is not None
        and abs(float(limit_price) - guard.limit_price) > 1e-9
    ):
        mismatches.append("limit_price")
    if mismatches:
        raise PaperOrderError(
            "Alpaca Paper broker write guard request binding is stale: "
            + ", ".join(sorted(set(mismatches)))
        )
    return guard


def _submit_verified_paper_request(
    client: Any,
    request: Any,
    guard: _PaperBrokerWriteGuard | None,
    *,
    signal: Signal,
    qty: float,
    client_order_id: str,
    order_style: str,
    time_in_force: str,
    limit_price: float | None,
) -> Any:
    verified = _require_paper_broker_write_guard(
        guard,
        signal=signal,
        qty=qty,
        client_order_id=client_order_id,
        order_style=order_style,
        time_in_force=time_in_force,
        limit_price=limit_price,
    )
    _require_verified_paper_client(client)
    if verified.context.authorization.kind == "canary":
        _revalidate_canary_broker_target(client, verified, signal)
    with paper_control_lock(verified.root):
        _require_paper_broker_write_guard(
            verified,
            signal=signal,
            qty=qty,
            client_order_id=client_order_id,
            order_style=order_style,
            time_in_force=time_in_force,
            limit_price=limit_price,
        )
        current = _revalidate_submission_authorization(
            verified.spec,
            verified.root,
            verified.context,
        )
        _require_kill_switch_clear(verified.root)
        _revalidate_local_write_evidence(verified)
        decision_at = _paper_broker_write_decision_time()
        try:
            require_paper_submission_authorization_effective_at(
                current.authorization,
                decision_at,
            )
            require_fresh_paper_signal(signal, observed_at=decision_at)
            require_paper_order_window(
                verified.spec,
                current.policy,
                observed_at=decision_at,
            )
        except ValueError as exc:
            raise PaperOrderError(str(exc)) from exc
        _consume_paper_broker_write_guard(verified)
        return client.submit_order(request)


def _paper_broker_write_decision_time() -> datetime:
    return datetime.now(UTC)


def _consume_paper_broker_write_guard(guard: _PaperBrokerWriteGuard) -> None:
    with _WRITE_GUARD_LOCK:
        if guard.nonce in _CONSUMED_WRITE_GUARDS:
            raise PaperOrderError("Alpaca Paper broker write guard was already consumed")
        _CONSUMED_WRITE_GUARDS.add(guard.nonce)


def _revalidate_local_write_evidence(guard: _PaperBrokerWriteGuard) -> None:
    try:
        signal_binding = find_signal_record(guard.signal_id, guard.root)
    except FileNotFoundError as exc:
        raise PaperOrderError("paper broker write signal evidence disappeared") from exc
    if signal_binding.record_hash != guard.signal_record_hash:
        raise PaperOrderError("paper broker write signal evidence changed after reservation")
    intent = _existing_intent(guard.root, guard.intent_id)
    if intent is None:
        raise PaperOrderError("paper broker write intent evidence disappeared")
    intent_hash = _canonical_payload_hash(intent.model_dump(mode="json"))
    if intent_hash != guard.intent_hash:
        raise PaperOrderError("paper broker write intent evidence changed after reservation")


def _revalidate_canary_broker_target(
    client: Any,
    guard: _PaperBrokerWriteGuard,
    signal: Signal,
) -> None:
    authorization = guard.context.authorization.payload
    account_hash, _ = _require_live_broker_account(client)
    if account_hash != authorization.get("broker_account_id_hash"):
        raise PaperOrderError("paper canary authorization is bound to a different broker account")
    _require_canary_open_orders_bound(guard.root, client, guard.context)
    expected = guard.target_resolution
    if expected is None:
        raise PaperOrderError("paper canary broker write is missing target-state binding")
    current = _resolve_target_order(
        client,
        guard.spec,
        signal,
        reference_price=(
            guard.limit_price if guard.limit_price is not None else float(signal.price)
        ),
        canary_limits=authorization.get("limits"),
    )
    if (
        current.qty is None
        or abs(current.qty - guard.qty) > 1e-9
        or abs(current.pretrade_position_qty - expected.pretrade_position_qty) > 1e-9
        or abs(current.target_position_qty - expected.target_position_qty) > 1e-9
        or current.risk_effect != expected.risk_effect
    ):
        raise PaperOrderError("paper canary broker target state changed after intent reservation")


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


def _validate_logged_signal(signal: Signal, spec: StrategySpec, root: Path):
    try:
        binding = find_signal_record(signal.id, root)
    except FileNotFoundError as exc:
        raise PaperOrderError("paper order signal must be persisted before submission") from exc
    if signal_record_hash(signal) != binding.record_hash:
        raise PaperOrderError("submitted signal does not match the persisted signal record")
    expected_spec_hash = strategy_content_hash(spec)
    expected_version_id = strategy_version_id(spec)
    mismatches = []
    if signal.strategy_name != spec.name or signal.strategy_id not in {None, spec.name}:
        mismatches.append("strategy_name")
    if signal.spec_hash != expected_spec_hash:
        mismatches.append("spec_hash")
    if signal.version_id != expected_version_id:
        mismatches.append("version_id")
    if signal.symbol.upper() not in spec.universe:
        mismatches.append("symbol")
    if signal.lifecycle != spec.lifecycle or signal.execution_mode != spec.execution.mode:
        mismatches.append("lifecycle_or_execution_mode")
    if mismatches:
        raise PaperOrderError(
            "persisted signal does not bind the current deployment: " + ", ".join(mismatches)
        )
    return binding


def _validate_existing_order(
    order: PaperOrderRecord,
    record_hash: str,
    context: PaperSubmissionContext,
) -> None:
    authorization_id = context.authorization.payload.get("authorization_id")
    expected = {
        "signal_record_hash": record_hash,
        "execution_policy_id": context.policy.policy_id,
        "execution_policy_hash": context.policy.content_hash,
        "authorization_id": authorization_id,
        "authorization_hash": context.authorization.content_hash,
        "authorization_kind": (
            context.authorization.kind if context.authorization.kind != "none" else None
        ),
    }
    mismatches = [name for name, value in expected.items() if getattr(order, name) != value]
    if mismatches:
        raise PaperOrderError(
            "existing local order audit binding is stale: " + ", ".join(mismatches)
        )


def _require_broker_reconciliation(client: Any) -> None:
    if not hasattr(client, "get_order_by_client_id") and not hasattr(client, "get_orders"):
        raise PaperOrderError("broker client-order reconciliation is unavailable")


def _broker_order_by_client_id(client: Any, client_order_id: str) -> Any | None:
    if hasattr(client, "get_orders"):
        for order in _get_broker_orders(client, include_closed=True):
            if str(getattr(order, "client_order_id", "")) == client_order_id:
                return order
    if hasattr(client, "get_order_by_client_id"):
        try:
            return client.get_order_by_client_id(client_order_id)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code != 404 and exc.__class__.__name__ != "NotFoundError":
                raise PaperOrderError(f"broker order reconciliation failed: {exc}") from exc
    return None


def _prepare_order_intent(
    root: Path,
    signal: Signal,
    log_path: Path,
    record_hash: str,
    context: PaperSubmissionContext,
    *,
    intent_id: str,
    order_qty: float,
    reference_price: float,
    estimated_notional: float,
    client_order_id: str,
    target_resolution: _TargetOrderResolution | None,
) -> tuple[PaperOrderIntent, str]:
    authorization = context.authorization.payload
    existing = _existing_intent(root, intent_id)
    if existing is not None:
        expected = {
            "client_order_id": client_order_id,
            "signal_id": signal.id,
            "signal_record_hash": record_hash,
            "authorization_id": str(authorization["authorization_id"]),
            "authorization_hash": str(context.authorization.content_hash),
            "qty": order_qty,
            "reference_price": reference_price,
            "estimated_notional": estimated_notional,
            "requested_target_weight": (
                target_resolution.requested_target_weight if target_resolution else None
            ),
            "effective_target_weight": (
                target_resolution.effective_target_weight if target_resolution else None
            ),
            "pretrade_position_qty": (
                target_resolution.pretrade_position_qty if target_resolution else None
            ),
            "target_position_qty": (
                target_resolution.target_position_qty if target_resolution else None
            ),
            "canary_position_limit_usd": (
                target_resolution.canary_position_limit_usd if target_resolution else None
            ),
            "risk_effect": target_resolution.risk_effect if target_resolution else None,
            "order_style": str(context.policy.payload.get("order_style") or "").lower(),
            "time_in_force": str(context.policy.payload.get("time_in_force") or "").lower(),
        }
        mismatches = [
            field_name
            for field_name, value in expected.items()
            if getattr(existing, field_name) != value
        ]
        if mismatches:
            raise PaperOrderError(
                "existing order intent does not match the current immutable intent: "
                + ", ".join(mismatches)
            )
        payload = existing.model_dump(mode="json")
        return existing, _canonical_payload_hash(payload)
    intent = PaperOrderIntent(
        id=intent_id,
        created_at=signal.created_at,
        client_order_id=client_order_id,
        signal_id=signal.id,
        signal_record_hash=record_hash,
        signal_log_path=_relpath(log_path, root),
        strategy_name=signal.strategy_name,
        version_id=str(signal.version_id),
        spec_hash=str(signal.spec_hash),
        execution_policy_id=context.policy.policy_id,
        execution_policy_hash=context.policy.content_hash,
        order_style=str(context.policy.payload.get("order_style") or "").lower(),
        time_in_force=str(context.policy.payload.get("time_in_force") or "").lower(),
        authorization_id=str(authorization["authorization_id"]),
        authorization_hash=str(context.authorization.content_hash),
        authorization_kind=(
            context.authorization.kind if context.authorization.kind != "none" else None
        ),
        symbol=signal.symbol,
        side=signal.side,
        qty=order_qty,
        reference_price=reference_price,
        estimated_notional=estimated_notional,
        requested_target_weight=(
            target_resolution.requested_target_weight if target_resolution else None
        ),
        effective_target_weight=(
            target_resolution.effective_target_weight if target_resolution else None
        ),
        pretrade_position_qty=(
            target_resolution.pretrade_position_qty if target_resolution else None
        ),
        target_position_qty=(target_resolution.target_position_qty if target_resolution else None),
        canary_position_limit_usd=(
            target_resolution.canary_position_limit_usd if target_resolution else None
        ),
        risk_effect=target_resolution.risk_effect if target_resolution else None,
        reserved_at=datetime.now(UTC),
    )
    payload = intent.model_dump(mode="json")
    intent_hash = _canonical_payload_hash(payload)
    _append_jsonl_durable(root / "reports" / "paper" / "order_intents.jsonl", intent)
    return intent, intent_hash


def _order_intent_id(
    client_order_id: str,
    record_hash: str,
    context: PaperSubmissionContext,
) -> str:
    seed = "|".join(
        [
            client_order_id,
            record_hash,
            context.policy.content_hash,
            str(context.authorization.content_hash),
        ]
    )
    return "intent_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _existing_intent(root: Path, intent_id: str) -> PaperOrderIntent | None:
    path = root / "reports" / "paper" / "order_intents.jsonl"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("id") == intent_id:
                return PaperOrderIntent.model_validate(payload)
    return None


def _estimated_order_reference_price(
    signal: Signal,
    policy: ExecutionPolicyBinding,
) -> float:
    limit_price = _policy_limit_price(signal, policy.payload)
    price = float(limit_price if limit_price is not None else signal.price)
    if not math.isfinite(price) or price <= 0:
        raise PaperOrderError("paper order reference price must be finite and positive")
    return price


def _enforce_canary_order_limits(
    root: Path,
    client: Any,
    spec: StrategySpec,
    signal: Signal,
    context: PaperSubmissionContext,
    *,
    intent_id: str,
    order_qty: float,
    reference_price: float,
    estimated_notional: float,
    risk_effect: Literal["increase", "reduce"] | None,
) -> None:
    authorization = context.authorization.payload
    _require_verified_canary_client(client)
    limits = authorization.get("limits")
    if not isinstance(limits, dict):
        raise PaperOrderError("paper canary authorization limits are missing")
    if signal.symbol.upper() not in {
        str(symbol).upper() for symbol in authorization.get("allowed_symbols", [])
    }:
        raise PaperOrderError(f"{signal.symbol} is outside the paper canary symbol scope")
    live_account_hash, account_equity = _require_live_broker_account(client)
    if live_account_hash != authorization.get("broker_account_id_hash"):
        raise PaperOrderError("paper canary authorization is bound to a different broker account")
    if abs(order_qty - round(order_qty)) > 1e-9:
        raise PaperOrderError("paper canary permits whole-share quantities only")
    _require_canary_open_orders_bound(root, client, context)

    try:
        max_order = float(limits["max_order_notional_usd"])
        max_session = float(limits["max_session_notional_usd"])
        max_total = float(limits["max_total_notional_usd"])
        max_session_orders = int(limits["max_orders_per_session"])
        max_total_orders = int(limits["max_total_orders"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PaperOrderError("paper canary authorization limits are malformed") from exc
    if risk_effect not in {"increase", "reduce"}:
        raise PaperOrderError("paper canary target order is missing its risk effect")
    effective_order_limit = min(max_order, account_equity * 0.01)
    if risk_effect == "increase" and estimated_notional > effective_order_limit + 1e-9:
        raise PaperOrderError(
            "paper canary order notional "
            f"{estimated_notional:.2f} exceeds {effective_order_limit:.2f}"
        )

    now = datetime.now(UTC)
    session_date = now.astimezone(ZoneInfo("America/New_York")).date()
    total_count = 0
    total_notional = 0.0
    session_count = 0
    session_notional = 0.0
    lifetime_count = 0
    lifetime_notional = 0.0
    existing_reservation = False
    for intent in _load_order_intents(root):
        if (
            intent.authorization_kind != "canary"
            or intent.strategy_name != spec.name
            or intent.spec_hash != strategy_content_hash(spec)
        ):
            continue
        if intent.estimated_notional is None or intent.reserved_at is None:
            raise PaperOrderError("canary authorization ledger contains an incomplete reservation")
        if not math.isfinite(intent.estimated_notional) or intent.estimated_notional <= 0:
            raise PaperOrderError("canary authorization ledger contains invalid notional")
        if intent.id == intent_id:
            existing_reservation = True
            if (
                abs(intent.qty - order_qty) > 1e-9
                or intent.reference_price is None
                or abs(intent.reference_price - reference_price) > 1e-9
                or abs(intent.estimated_notional - estimated_notional) > 1e-9
            ):
                raise PaperOrderError("existing canary reservation conflicts with the order intent")
        if intent.risk_effect == "reduce" or (intent.risk_effect is None and intent.side == "sell"):
            continue
        lifetime_count += 1
        lifetime_notional += float(intent.estimated_notional)
        reserved_session = intent.reserved_at.astimezone(ZoneInfo("America/New_York")).date()
        if reserved_session == session_date:
            session_count += 1
            session_notional += float(intent.estimated_notional)
        if intent.authorization_id == authorization.get("authorization_id"):
            total_count += 1
            total_notional += float(intent.estimated_notional)
    if risk_effect == "reduce":
        return
    if not existing_reservation:
        total_count += 1
        total_notional += estimated_notional
        lifetime_count += 1
        lifetime_notional += estimated_notional
        session_count += 1
        session_notional += estimated_notional
    if session_count > max_session_orders:
        raise PaperOrderError("paper canary session order-count limit exceeded")
    if total_count > max_total_orders:
        raise PaperOrderError("paper canary total order-count limit exceeded")
    if session_notional > max_session + 1e-9:
        raise PaperOrderError("paper canary session notional limit exceeded")
    if total_notional > max_total + 1e-9:
        raise PaperOrderError("paper canary total notional limit exceeded")
    if lifetime_count > 40:
        raise PaperOrderError("paper canary lifetime reservation limit exceeded")
    if lifetime_notional > 30_000 + 1e-9:
        raise PaperOrderError("paper canary lifetime notional limit exceeded")


def _require_verified_canary_client(client: Any) -> None:
    try:
        _require_verified_paper_client(client)
    except PaperOrderError as exc:
        raise PaperOrderError(
            "paper canary requires a verified Open Composer Alpaca Paper client"
        ) from exc


def _mark_verified_paper_client(client: Any, *, origin: str = ALPACA_PAPER_ORIGIN) -> Any:
    base_url = str(getattr(client, "_base_url", "")).rstrip("/")
    if (
        origin.rstrip("/") != ALPACA_PAPER_ORIGIN
        or base_url != ALPACA_PAPER_ORIGIN
        or getattr(client, "_sandbox", None) is not True
    ):
        raise PaperOrderError(
            "broker client verification requires an SDK client configured for Alpaca Paper"
        )
    client._open_composer_paper_verified = True
    client._open_composer_paper_origin = origin
    client._open_composer_paper_verification_token = _PAPER_CLIENT_VERIFICATION_TOKEN
    return client


def _is_verified_paper_client(client: Any) -> bool:
    return (
        getattr(client, "_open_composer_paper_verified", False) is True
        and getattr(client, "_open_composer_paper_origin", None) == ALPACA_PAPER_ORIGIN
        and getattr(client, "_open_composer_paper_verification_token", None)
        is _PAPER_CLIENT_VERIFICATION_TOKEN
        and str(getattr(client, "_base_url", "")).rstrip("/") == ALPACA_PAPER_ORIGIN
        and getattr(client, "_sandbox", None) is True
    )


def _require_verified_paper_client(client: Any) -> None:
    if not _is_verified_paper_client(client):
        raise PaperOrderError(
            "broker operation requires a client created by the strict Alpaca Paper factory"
        )


def _require_canary_open_orders_bound(
    root: Path,
    client: Any,
    context: PaperSubmissionContext,
) -> None:
    local_orders = _local_orders_by_client_id(root)
    authorization_id = context.authorization.payload.get("authorization_id")
    open_count = 0
    for broker_order in _get_broker_orders(client, include_closed=True):
        status = _enum_text(getattr(broker_order, "status", ""))
        client_order_id = str(getattr(broker_order, "client_order_id", ""))
        local = local_orders.get(client_order_id)
        if client_order_id.startswith("oc-") and local is None:
            raise PaperOrderError("paper canary found an unreconciled Open Composer broker order")
        if status in TERMINAL_ORDER_STATUSES:
            continue
        if status not in KNOWN_ORDER_STATUSES:
            raise PaperOrderError(f"paper canary found unrecognized broker order status={status}")
        open_count += 1
        if local is None:
            raise PaperOrderError("paper canary found an untracked open broker order")
        if local.authorization_id != authorization_id or local.authorization_kind != "canary":
            raise PaperOrderError("paper canary found an open order outside this authorization")
    if open_count >= 1:
        raise PaperOrderError("paper canary permits at most one account-wide open order")


def _load_order_intents(root: Path) -> list[PaperOrderIntent]:
    path = root / "reports" / "paper" / "order_intents.jsonl"
    if not path.is_file():
        return []
    rows: list[PaperOrderIntent] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(PaperOrderIntent.model_validate_json(line))
    except (OSError, ValueError) as exc:
        raise PaperOrderError("paper order intent ledger is malformed") from exc
    return rows


def _get_broker_orders(client: Any, *, include_closed: bool) -> list[Any]:
    try:
        from alpaca.common.enums import Sort
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL if include_closed else QueryOrderStatus.OPEN,
            limit=500,
            direction=Sort.DESC,
        )
        orders = list(client.get_orders(filter=request))
        if include_closed and len(orders) >= 500:
            raise PaperOrderError(
                "Alpaca Paper order history reached the bounded sync limit; reconcile manually"
            )
        return orders
    except TypeError as exc:
        if _is_verified_paper_client(client):
            raise PaperOrderError(
                "verified Alpaca Paper client rejected the order-history filter"
            ) from exc
        return list(client.get_orders())


def _normalize_broker_order(order: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(order, "id", "")),
        "client_order_id": str(getattr(order, "client_order_id", "")),
        "symbol": str(getattr(order, "symbol", "")).upper(),
        "side": _enum_text(getattr(order, "side", "")),
        "qty": _optional_float(getattr(order, "qty", None)) or 0.0,
        "filled_qty": _optional_float(getattr(order, "filled_qty", None)) or 0.0,
        "filled_avg_price": _optional_float(getattr(order, "filled_avg_price", None)),
        "status": _enum_text(getattr(order, "status", "")),
        "order_type": _enum_text(getattr(order, "order_type", getattr(order, "type", ""))),
        "time_in_force": _enum_text(getattr(order, "time_in_force", "")),
        "limit_price": _optional_float(getattr(order, "limit_price", None)),
        "submitted_at": _timestamp_text(getattr(order, "submitted_at", None)),
        "accepted_at": _timestamp_text(getattr(order, "accepted_at", None)),
        "filled_at": _timestamp_text(getattr(order, "filled_at", None)),
        "updated_at": _timestamp_text(getattr(order, "updated_at", None)),
    }


def _validate_normalized_broker_order(order: dict[str, Any]) -> None:
    for field_name in ("id", "client_order_id", "symbol", "side", "status"):
        if not str(order.get(field_name) or "").strip():
            raise PaperOrderError(f"Alpaca Paper order is missing {field_name}")
    if order["side"] not in {"buy", "sell"}:
        raise PaperOrderError(f"Alpaca Paper order has unsupported side={order['side']}")
    if order["status"] not in KNOWN_ORDER_STATUSES:
        raise PaperOrderError(f"unrecognized Alpaca Paper order status={order['status']}")
    qty = float(order.get("qty") or 0)
    filled_qty = float(order.get("filled_qty") or 0)
    if not math.isfinite(qty) or qty <= 0:
        raise PaperOrderError("Alpaca Paper order quantity must be finite and positive")
    if not math.isfinite(filled_qty) or filled_qty < 0 or filled_qty > qty + 1e-9:
        raise PaperOrderError("Alpaca Paper filled quantity is invalid")
    if filled_qty > 0:
        fill_price = order.get("filled_avg_price")
        if fill_price is None or not math.isfinite(float(fill_price)) or float(fill_price) <= 0:
            raise PaperOrderError("Alpaca Paper filled order is missing a valid average price")
    if order["status"] == "filled" and (
        abs(filled_qty - qty) > 1e-9 or order.get("filled_at") is None
    ):
        raise PaperOrderError("Alpaca Paper filled order is missing complete fill evidence")


def _validate_broker_local_order_match(
    broker_order: dict[str, Any],
    local_order: PaperOrderRecord,
) -> None:
    expected = {
        "id": local_order.id,
        "client_order_id": local_order.client_order_id,
        "symbol": local_order.symbol.upper(),
        "side": local_order.side,
    }
    mismatches = [
        field_name
        for field_name, value in expected.items()
        if str(broker_order.get(field_name) or "") != str(value)
    ]
    if abs(float(broker_order["qty"]) - float(local_order.qty)) > 1e-9:
        mismatches.append("qty")
    if not local_order.order_style or not local_order.time_in_force:
        mismatches.append("local_execution_style")
    else:
        if broker_order.get("order_type") != _broker_order_type(local_order.order_style):
            mismatches.append("order_type")
        if broker_order.get("time_in_force") != local_order.time_in_force:
            mismatches.append("time_in_force")
    if mismatches:
        raise PaperOrderError(
            "broker order does not match the immutable local order: "
            + ", ".join(sorted(set(mismatches)))
        )


def _broker_order_type(order_style: str) -> str:
    if order_style in {"loo_limit", "opg_limit"}:
        return "limit"
    if order_style in {"day_market", "moo_market"}:
        return "market"
    raise PaperOrderError(f"unsupported paper order_style: {order_style or 'missing'}")


def _write_immutable_broker_receipt(
    root: Path,
    broker_order: dict[str, Any],
    local_order: PaperOrderRecord | None,
    *,
    broker_account_hash: str | None,
    captured_at: datetime,
    local_binding_status: str | None = None,
) -> Path:
    _validate_normalized_broker_order(broker_order)
    if not isinstance(broker_account_hash, str) or len(broker_account_hash) != 64:
        raise PaperOrderError("immutable broker receipt requires a bound broker account hash")
    if captured_at.tzinfo is None:
        raise PaperOrderError("immutable broker receipt captured_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)
    local_payload = local_order.model_dump(mode="json") if local_order is not None else None
    local_hash = _canonical_payload_hash(local_payload) if local_payload is not None else None
    binding_status = local_binding_status or ("matched" if local_order is not None else "unmatched")
    state = _broker_receipt_state(
        broker_account_hash=broker_account_hash,
        broker_order=broker_order,
        local_binding_status=binding_status,
        local_order_hash=local_hash,
    )
    state_hash = _canonical_payload_hash(state)
    order_key = hashlib.sha256(str(broker_order["id"]).encode("utf-8")).hexdigest()[:16]
    directory = root / "reports" / "paper" / "broker_receipts" / "orders" / order_key
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{state_hash}.json"

    submitted_at = broker_order.get("submitted_at")
    if submitted_at is None and local_order is not None:
        submitted_at = local_order.submitted_at.astimezone(UTC).isoformat()
    receipt: dict[str, Any] = {
        "receipt_version": 1,
        "receipt_source": "alpaca_paper_sync",
        "receipt_id": "receipt_" + state_hash[:24],
        "state_sha256": state_hash,
        "immutable": True,
        "captured_at": captured_at.isoformat(),
        "observed_at": captured_at.isoformat(),
        "paper": True,
        "broker": "alpaca_paper",
        "broker_account_id_hash": broker_account_hash,
        "order_id": broker_order["id"],
        "client_order_id": broker_order["client_order_id"],
        "symbol": broker_order["symbol"],
        "side": broker_order["side"],
        "qty": broker_order["filled_qty"] or broker_order["qty"],
        "status": broker_order["status"],
        "submitted_at": submitted_at,
        "accepted_at": broker_order.get("accepted_at"),
        "filled_at": broker_order.get("filled_at"),
        "fill_price": broker_order.get("filled_avg_price"),
        "broker_order": broker_order,
        "broker_order_sha256": _canonical_payload_hash(broker_order),
        "local_order_binding_status": binding_status,
        "local_order_record": local_payload,
        "local_order_record_sha256": local_hash,
    }
    if (
        broker_order["status"] == "filled"
        and broker_order.get("filled_at")
        and broker_order.get("filled_avg_price")
        and broker_order.get("filled_qty")
    ):
        receipt["fill_id"] = f"alpaca_aggregate_{order_key}_{state_hash[:12]}"
        receipt["fill_id_source"] = "derived_from_broker_order_aggregate"
    if local_order is not None:
        receipt.update(
            {
                "strategy_name": local_order.strategy_name,
                "spec_hash": local_order.spec_hash,
                "execution_policy_id": local_order.execution_policy_id,
                "execution_policy_hash": local_order.execution_policy_hash,
                "order_style": local_order.order_style,
                "time_in_force": local_order.time_in_force,
                "authorization_id": local_order.authorization_id,
                "authorization_hash": local_order.authorization_hash,
                "authorization_kind": local_order.authorization_kind,
                "signal_id": local_order.signal_id,
            }
        )
    lock_path = directory / ".receipt.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            chain = _load_order_receipt_chain(directory, str(broker_order["id"]))
            existing = next((item for item in chain if item[0] == path), None)
            if existing is not None:
                receipt = existing[1]
            else:
                previous = chain[-1] if chain else None
                receipt["sequence"] = len(chain) + 1
                receipt["previous_state_sha256"] = (
                    previous[1]["state_sha256"] if previous is not None else None
                )
                receipt["previous_receipt_sha256"] = (
                    _sha256_file(previous[0]) if previous is not None else None
                )
                encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
                try:
                    with path.open("x", encoding="utf-8") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError:
                    pass
                if path.read_text(encoding="utf-8") != encoded:
                    raise PaperOrderError("immutable broker receipt collision")
                _validate_broker_receipt_integrity(
                    path,
                    receipt,
                    expected_order_id=str(broker_order["id"]),
                )
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    _append_broker_receipt_index(root, receipt, path)
    return path


def _broker_receipt_state(
    *,
    broker_account_hash: str | None,
    broker_order: dict[str, Any],
    local_binding_status: str,
    local_order_hash: str | None,
) -> dict[str, Any]:
    return {
        "broker": "alpaca_paper",
        "paper": True,
        "broker_account_id_hash": broker_account_hash,
        "broker_order": broker_order,
        "local_order_binding_status": local_binding_status,
        "local_order_record_sha256": local_order_hash,
    }


def _load_order_receipt_chain(
    directory: Path,
    order_id: str,
) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperOrderError("immutable broker receipt chain is malformed") from exc
        if not isinstance(payload, dict):
            raise PaperOrderError("immutable broker receipt chain contains a non-object")
        _validate_broker_receipt_integrity(path, payload, expected_order_id=order_id)
        rows.append((path, payload))
    rows.sort(key=lambda item: int(item[1]["sequence"]))
    for index, (path, payload) in enumerate(rows, start=1):
        if payload["sequence"] != index:
            raise PaperOrderError("immutable broker receipt chain sequence is discontinuous")
        previous = rows[index - 2] if index > 1 else None
        expected_state = previous[1]["state_sha256"] if previous is not None else None
        expected_hash = _sha256_file(previous[0]) if previous is not None else None
        if payload.get("previous_state_sha256") != expected_state:
            raise PaperOrderError("immutable broker receipt state chain is broken")
        if payload.get("previous_receipt_sha256") != expected_hash:
            raise PaperOrderError("immutable broker receipt hash chain is broken")
        if path.name != f"{payload['state_sha256']}.json":
            raise PaperOrderError("immutable broker receipt path does not match its state")
    return rows


def _validate_broker_receipt_integrity(
    path: Path,
    receipt: dict[str, Any],
    *,
    expected_order_id: str,
) -> None:
    broker_order = receipt.get("broker_order")
    local_order = receipt.get("local_order_record")
    if not isinstance(broker_order, dict):
        raise PaperOrderError("immutable broker receipt is missing broker_order")
    if local_order is not None and not isinstance(local_order, dict):
        raise PaperOrderError("immutable broker receipt has invalid local_order_record")
    local_hash = _canonical_payload_hash(local_order) if local_order is not None else None
    if receipt.get("local_order_record_sha256") != local_hash:
        raise PaperOrderError("immutable broker receipt local order hash is invalid")
    if receipt.get("broker_order_sha256") != _canonical_payload_hash(broker_order):
        raise PaperOrderError("immutable broker receipt broker order hash is invalid")
    state = _broker_receipt_state(
        broker_account_hash=receipt.get("broker_account_id_hash"),
        broker_order=broker_order,
        local_binding_status=str(receipt.get("local_order_binding_status") or ""),
        local_order_hash=local_hash,
    )
    state_hash = _canonical_payload_hash(state)
    if receipt.get("state_sha256") != state_hash:
        raise PaperOrderError("immutable broker receipt state hash is invalid")
    if receipt.get("receipt_id") != "receipt_" + state_hash[:24]:
        raise PaperOrderError("immutable broker receipt id is invalid")
    if str(receipt.get("order_id") or "") != expected_order_id:
        raise PaperOrderError("immutable broker receipt order id is inconsistent")
    order_key = hashlib.sha256(expected_order_id.encode("utf-8")).hexdigest()[:16]
    if path.parent.name != order_key or path.name != f"{state_hash}.json":
        raise PaperOrderError("immutable broker receipt is stored under the wrong order key")
    sequence = receipt.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise PaperOrderError("immutable broker receipt sequence is invalid")


def _append_broker_receipt_index(root: Path, receipt: dict[str, Any], path: Path) -> None:
    index_path = root / "reports" / "paper" / "broker_receipts" / "index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "receipt_id": receipt["receipt_id"],
        "order_id": receipt["order_id"],
        "status": receipt["status"],
        "path": _relpath(path, root),
        "sha256": _sha256_file(path),
        "captured_at": receipt["captured_at"],
        "paper": True,
    }
    with index_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            existing_ids = {
                str(json.loads(line).get("receipt_id"))
                for line in handle.read().splitlines()
                if line.strip()
            }
            if row["receipt_id"] not in existing_ids:
                handle.seek(0, 2)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_broker_sync_receipt(
    root: Path,
    *,
    captured_at: datetime,
    broker_account_hash: str | None,
    receipts: list[dict[str, Any]],
    local_order_count: int,
) -> Path:
    payload = {
        "receipt_version": 1,
        "receipt_source": "alpaca_paper_sync",
        "captured_at": captured_at.isoformat(),
        "paper": True,
        "broker_account_id_hash": broker_account_hash,
        "order_count": len(receipts),
        "local_order_count": local_order_count,
        "complete_local_order_reconciliation": True,
        "order_receipts": receipts,
    }
    payload["sync_id"] = "sync_" + _canonical_payload_hash(payload)[:24]
    directory = root / "reports" / "paper" / "broker_receipts"
    directory.mkdir(parents=True, exist_ok=True)
    immutable = directory / "syncs" / f"{payload['sync_id']}.json"
    immutable.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if immutable.exists():
        if immutable.read_text(encoding="utf-8") != encoded:
            raise PaperOrderError("immutable broker sync receipt collision")
    else:
        try:
            with immutable.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if immutable.read_text(encoding="utf-8") != encoded:
                raise PaperOrderError("immutable broker sync receipt collision") from None
    latest = directory / "latest-sync.json"
    _atomic_write_text(latest, encoded)
    return immutable


def _local_orders_by_client_id(root: Path) -> dict[str, PaperOrderRecord]:
    path = root / "reports" / "paper" / "orders.jsonl"
    if not path.is_file():
        return {}
    rows: dict[str, PaperOrderRecord] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = PaperOrderRecord.model_validate_json(line)
            existing = rows.get(record.client_order_id)
            if existing is not None and existing.model_dump(mode="json") != record.model_dump(
                mode="json"
            ):
                raise PaperOrderError("paper order ledger has conflicting client_order_id rows")
            rows[record.client_order_id] = record
    except (OSError, ValueError) as exc:
        if isinstance(exc, PaperOrderError):
            raise
        raise PaperOrderError("paper order ledger is malformed") from exc
    return rows


def _client_broker_account_hash(client: Any, root: Path) -> str | None:
    if hasattr(client, "get_account"):
        try:
            account = client.get_account()
        except Exception as exc:
            if _is_verified_paper_client(client):
                raise PaperOrderError("Alpaca Paper account reconciliation failed") from exc
            account = None
        account_hash = _optional_broker_account_hash(getattr(account, "id", None))
        if account_hash:
            return account_hash
        if _is_verified_paper_client(client):
            raise PaperOrderError("Alpaca Paper account id is missing")
    account_path = root / "reports" / "paper" / "account.json"
    if account_path.is_file():
        try:
            payload = json.loads(account_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = str(payload.get("broker_account_id_hash") or "")
        return value if len(value) == 64 else None
    return None


def _require_live_broker_account(client: Any) -> tuple[str, float]:
    if not hasattr(client, "get_account"):
        raise PaperOrderError("paper canary requires live broker account reconciliation")
    try:
        account = client.get_account()
        account_hash = broker_account_id_hash(getattr(account, "id", None))
        equity = float(getattr(account, "equity", 0) or 0)
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("paper account equity is invalid")
        status = str(getattr(account, "status", "ACTIVE") or "").upper()
        if status != "ACTIVE":
            raise ValueError("paper account is not active")
        return account_hash, equity
    except Exception as exc:
        raise PaperOrderError("paper canary could not bind the live broker account") from exc


def _optional_broker_account_hash(value: Any) -> str | None:
    try:
        return broker_account_id_hash(value)
    except ValueError:
        return None


def _enum_text(value: Any) -> str:
    return str(value or "").lower().split(".")[-1]


def _timestamp_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(UTC).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).isoformat()


def _canonical_payload_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _append_jsonl_durable(path: Path, row: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
