"""One-shot, strictly GET-only operation for an authorized empty source sleeve.

This is the usable cash-only branch before the frozen monthly entry. It never
claims monthly trading readiness and has no submit/cancel/producer/source route.
Existing Main integration must supply exact scoped authorization after account
access/identity/funds verification. The module does not create that authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from open_composer.adapters.broker.alpaca_paper import (
    _atomic_write_text,
    _optional_broker_account_hash,
    _require_kill_switch_clear,
    _require_verified_paper_client,
)
from open_composer.book_paper.accounts import make_trading_client
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_operation_lock import source_account_operation
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
from open_composer.paper_lock import paper_control_lock, paper_submission_lock

KIND = "dia_base_cash_only_observation_v1"
CAP = 20000.0
END = datetime(2026, 11, 14, tzinfo=UTC)


def _clock(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("aware authority clock required")
    return result.astimezone(UTC)


def _value(obj, field):
    return obj.get(field) if isinstance(obj, dict) else getattr(obj, field, None)


def _amount(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite account quantity/amount")
    return number


def validate_authority(root: Path, auth: dict, now: datetime) -> None:
    """No client construction until exact Main-installed cash-only scope passes."""
    if now.tzinfo is None or (
        auth.get("kind") != KIND
        or auth.get("account") != "quant2"
        or auth.get("paper_only") is not True
        or auth.get("orders_permitted") is not False
        or auth.get("capital_usd") != CAP
        or auth.get("policy") != "DIA_BASE"
        or auth.get("active") is not True
    ):
        raise ValueError("missing exact active cash-only authority")
    if (
        not _clock(auth["authorized_at"])
        <= now
        < min(_clock(auth["expires_at"]), _clock(auth["account_authority_expires_at"]), END)
    ):
        raise ValueError("cash-only authority inactive/expired")
    if len(auth.get("account_hash", "")) != 64:
        raise ValueError("verified account identity binding required")
    if (
        auth.get("own_initial_cash_verified") is not True
        or auth.get("scope_conflicts_verified") is not True
    ):
        raise ValueError("account/capital scope not accepted")
    if _amount(auth["other_reserved_cash_usd"]) < 0:
        raise ValueError("invalid other-sleeve cash reservation")
    required = auth.get("bindings", {})
    for key in (
        "spec",
        "scientific_contract",
        "account_scope",
        "implementation_review",
        "native_cash_acceptance",
    ):
        if key not in required:
            raise ValueError("missing scoped binding")
        bound_bytes(root, required[key])
    account_scope = json.loads(bound_bytes(root, required["account_scope"]))
    if (
        account_scope.get("status") != "accepted_account_sleeve_scope"
        or account_scope.get("account_hash") != auth["account_hash"]
        or account_scope.get("capital_usd") != CAP
        or account_scope.get("foreign_positions") != auth["foreign_positions"]
    ):
        raise ValueError("actual accepted account/sleeve binding differs")
    acceptance = json.loads(bound_bytes(root, required["native_cash_acceptance"]))
    if (
        acceptance.get("accepted") is not True
        or acceptance.get("scope") != KIND
        or acceptance.get("orders_permitted") is not False
    ):
        raise ValueError("native receipt does not admit cash-only operation")
    code = auth.get("code_bindings", [])
    if not code or not any(Path(x["path"]).resolve() == Path(__file__).resolve() for x in code):
        raise ValueError("current entry not bound")
    for binding in code:
        bound_bytes(root, binding)
    if acceptance.get("code_bindings") != code:
        raise ValueError("native acceptance is for different code")
    _require_kill_switch_clear(root)


def _read_only_client(*, read_guard):
    """Private verified client: no SDK retry, no redirect or write route."""
    if read_guard() is not None:
        raise ValueError("read scope guard must raise or return None")
    client = make_trading_client("quant2")
    _require_verified_paper_client(client)
    client._retry = 0
    from requests.adapters import HTTPAdapter

    client._session.mount("https://", HTTPAdapter(max_retries=0))
    request = client._session.request

    def read_only(method, url, **kwargs):
        parsed = urlparse(str(url))
        if (
            str(method).upper() != "GET"
            or parsed.scheme != "https"
            or parsed.netloc != "paper-api.alpaca.markets"
            or parsed.path not in {"/v2/account", "/v2/positions", "/v2/orders"}
        ):
            raise ValueError("outside the exact GET-only paper observation route")
        if client._retry != 0 or client._session.get_adapter(str(url)).max_retries.total != 0:
            raise ValueError("read-only retry configuration drift")
        if read_guard() is not None:
            raise ValueError("read scope guard must raise or return None")
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = 15
        return request(method, url, **kwargs)

    client._session.request = read_only
    return client


def _empty_owned_checkpoint(store: SourceStateCheckpoint, capital: float):
    latest = store.load()
    if latest is None:
        raise ValueError("accepted owned cash checkpoint absent; no implicit reset")
    value = latest["snapshot"]
    cash = value["cashbook"]
    if (
        value["pending"]
        or cash["sales"]
        or cash["purchases"]
        or cash["dividends"]
        or any(cash["lots"].values())
    ):
        raise ValueError(
            "nonempty own book requires trading/rights reconciliation, not cash-only branch"
        )
    if _amount(cash["cash"]) != capital:
        raise ValueError("own cash differs from accepted allocation")
    return latest


def observe(
    root: Path,
    authority_path: Path,
    checkpoint: Path,
    output: Path,
    *,
    expected_authority_binding,
    client_factory=_read_only_client,
    clock=lambda: datetime.now(UTC),
) -> dict:
    """Current observation only. Exceptions are failures, never no-trade receipts."""
    if authority_path.resolve() != (root / expected_authority_binding["path"]).resolve():
        raise ValueError("authority path differs from native bound path")
    raw = bound_bytes(root, expected_authority_binding)
    auth = json.loads(raw)
    validate_authority(root, auth, clock())
    if checkpoint.resolve() != Path(auth["state_directory"]).resolve():
        raise ValueError("cash observation checkpoint differs from scoped owned book")
    store = SourceStateCheckpoint(
        checkpoint, account_hash=auth["account_hash"], sleeve_id="dia-base"
    )
    # Existing global paper locks serialize this read with order/control paths.
    # No broker write or data producer can be invoked from this branch.
    with source_account_operation(root), paper_submission_lock(root), paper_control_lock(root):
        validate_authority(root, auth, clock())
        if authority_path.read_bytes() != raw:
            raise ValueError("authority changed while acquiring locks")
        owned = _empty_owned_checkpoint(store, auth["capital_usd"])
        from open_composer.intraday_runner.source_scientific_entry import kernel_evidence

        kernel_evidence()

        def read_guard():
            if bound_bytes(root, expected_authority_binding) != raw:
                raise ValueError("native-bound authority changed")
            validate_authority(root, auth, clock())

        read_guard()
        client = (
            _read_only_client(read_guard=read_guard)
            if client_factory is _read_only_client
            else client_factory()
        )
        calls = 0
        try:
            read_guard()
            account = client.get_account()
            calls += 1
            actual = _optional_broker_account_hash(_value(account, "id"))
            if actual != auth["account_hash"]:
                raise ValueError("actual account identity differs")
            if (
                _value(account, "trading_blocked") is not False
                or _value(account, "account_blocked") is not False
                or str(_value(account, "status")).split(".")[-1].lower() != "active"
            ):
                raise ValueError("unknown/blocked account status")
            read_guard()
            positions = client.get_all_positions()
            calls += 1
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            read_guard()
            orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
            calls += 1
            if len(orders) >= 500:
                raise ValueError("open-order completeness not established")
            reserved_buys = 0.0
            for order in orders:
                side = str(_value(order, "side")).lower().split(".")[-1]
                if side == "buy":
                    remainder = _amount(_value(order, "qty")) - _amount(_value(order, "filled_qty"))
                    limit = _amount(_value(order, "limit_price"))
                    if remainder < 0 or limit <= 0:
                        raise ValueError("unknown existing buy liability")
                    reserved_buys += remainder * limit
                elif side != "sell":
                    raise ValueError("unknown open-order side")
            cash = _amount(_value(account, "cash"))
            buying_power = _amount(_value(account, "buying_power"))
            equity = _amount(_value(account, "equity"))
            if (
                equity <= 0
                or min(cash, buying_power) - reserved_buys - auth["other_reserved_cash_usd"] < CAP
            ):
                raise ValueError("unencumbered allocation no longer supported")
            for order in orders:
                if str(_value(order, "client_order_id")).startswith("dia-base-"):
                    raise ValueError("own working order prevents cash-only success")
            parsed_positions = {
                str(_value(p, "symbol")): _amount(_value(p, "qty")) for p in positions
            }
            if len(parsed_positions) != len(positions):
                raise ValueError("duplicate position observation")
            if parsed_positions != auth["foreign_positions"]:
                raise ValueError("actual positions differ from accepted other-scope baseline")
            # No own shares: all actual account positions remain other-scope.
            # Their existence is not own holdings, a liquidation instruction or PnL.
            validate_authority(root, auth, clock())
            if authority_path.read_bytes() != raw or store.load() != owned:
                raise ValueError("authority or owned state changed during observation")
            result = dict(
                kind=KIND,
                observed_at=clock().isoformat(),
                status="actual_cash_only_no_trade",
                account_hash=actual,
                own_cash=CAP,
                own_positions={},
                account_positions=parsed_positions,
                open_order_count=len(orders),
                reserved_open_buy_notional=reserved_buys,
                broker_equity=equity,
                broker_cash=cash,
                buying_power=buying_power,
                method_invocations=calls,
                wire_HTTP_count="UNKNOWN",
                order_writes=0,
                monthly_entry_ready=False,
                first_entry_or_profit=False,
                authority_sha256=hashlib.sha256(raw).hexdigest(),
                accounting=dict(broker_PnL=None, incremental_net=None, simulation_net=None),
                qualification=(
                    "Current empty owned sleeve observation only; future BASE waves require "
                    "separate complete native/execution/source acceptance"
                ),
            )
            _ensure_durable_directory(output.parent.absolute())
            if output.exists():
                raise ValueError("observation receipt already exists; preserve prior bytes")
            _atomic_write_text(output, json.dumps(result, indent=2, allow_nan=False) + "\n")
            return result
        finally:
            session = getattr(client, "_session", None)
            if session is not None:
                session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authority-binding", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.authority_binding.read_text())
    result = observe(
        args.root.resolve(),
        args.root.resolve() / expected["path"],
        args.checkpoint.resolve(),
        args.output.resolve(),
        expected_authority_binding=expected,
    )
    print(json.dumps({k: result[k] for k in ("status", "order_writes", "monthly_entry_ready")}))


if __name__ == "__main__":
    main()
