"""Current GET account/positions/orders reconciliation for the bounded own book.

No order, settlement, dividend or fee is inferred from a broker snapshot. A
quantity mismatch requires actual activity reception; it cannot be auto-reset.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import (
    _atomic_write_text,
    _optional_broker_account_hash,
)
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory, _hash
from open_composer.intraday_runner.source_method_controls import owned_account_capacity, risk_state
from open_composer.intraday_runner.source_state_checkpoint import restore
from open_composer.market_sessions import NEW_YORK


def _number(value):
    if isinstance(value, bool):
        raise ValueError("unknown numeric account field")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError("nonfinite account observation")
    return v


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _text(value):
    return str(value).split(".")[-1].lower()


def held_quote_fresh(stamp, now):
    if type(stamp) is not int or now.tzinfo is None:
        return False
    now_ns = int(now.astimezone(UTC).timestamp()) * 10**9 + now.microsecond * 1000
    return 0 <= now_ns - stamp <= 5_000_000_000


def capture_current(
    root: Path,
    client,
    auth: dict,
    revision: dict,
    *,
    quotes: dict,
    journal,
    directory: Path,
    clock=lambda: datetime.now(UTC),
) -> dict:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    from open_composer.intraday_runner.source_method_bindings import bound_bytes

    # Native/authority was validated before client creation; bind this receiver
    # through that same full entry, rather than accepting an invented callback.
    native = json.loads(bound_bytes(root, auth["bindings"]["native_acceptance"]))
    if native.get("accepted") is not True or not any(
        Path(b["path"]).resolve() == Path(__file__).resolve() for b in native["code_bindings"]
    ):
        raise ValueError("actual account receiver not in accepted native code")
    started = clock()
    account = client.get_account()
    if _optional_broker_account_hash(_get(account, "id")) != auth["account_hash"]:
        raise ValueError("actual account identity mismatch")
    if (
        _get(account, "account_blocked") is not False
        or _get(account, "trading_blocked") is not False
        or _text(_get(account, "status")) != "active"
    ):
        raise ValueError("unknown or inactive account")
    positions = client.get_all_positions()
    history = client.get_orders(
        GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=datetime.fromisoformat(auth["authorized_at"]),
            limit=500,
            direction="asc",
        )
    )
    opened = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
    if len(history) >= 500 or len(opened) >= 500:
        raise ValueError("order history truncated; no completeness inference")
    combined = {str(_get(row, "client_order_id")): row for row in history}
    if len(combined) != len(history):
        raise ValueError("duplicate history rows")
    for row in opened:
        combined[str(_get(row, "client_order_id"))] = row
    orders = list(combined.values())
    state, fills, fees, evidence = restore(root, revision["snapshot"])
    if evidence.get("unresolved_actual_liabilities") is not False:
        raise ValueError("actual liability reconciliation is unresolved; no AR masking shortcut")
    actual = {str(_get(p, "symbol")): _number(_get(p, "qty")) for p in positions}
    if len(actual) != len(positions):
        raise ValueError("duplicate position rows")
    own = {s: state.cashbook.quantity(s) for s in state.cashbook.lots if state.cashbook.quantity(s)}
    foreign = auth["foreign_positions"]
    for s in set(actual) | set(own) | set(foreign):
        if abs(actual.get(s, 0) - own.get(s, 0) - _number(foreign.get(s, 0))) > 1e-7:
            raise ValueError("actual position differs from own plus accepted other-scope positions")
    for cid, reservation in state.pending.items():
        if reservation["side"] == "liability_hold":
            if cid not in evidence.get("terminal_liability_holds", {}):
                raise ValueError("terminal hold lacks original provenance")
            continue
        path = journal._path(cid)
        if not path.exists():
            continue  # Reserved locally but never passed the durable dispatch marker.
        row = journal.receive(cid)
        if (
            row["stage"]
            in {
                "dispatch_boundary_consumed_ack_unknown",
                "transport_returned_reconciliation_required",
            }
            and cid not in combined
        ):
            raise ValueError(
                "attempted own order absent from actual history; acknowledgment unknown"
            )
    seen = set()
    open_other_buys = 0.0
    summaries = []
    for o in orders:
        cid = str(_get(o, "client_order_id"))
        qty = _number(_get(o, "qty"))
        done = _number(_get(o, "filled_qty"))
        status = _text(_get(o, "status"))
        side = _text(_get(o, "side"))
        symbol = str(_get(o, "symbol"))
        if cid in seen or not 0 <= done <= qty:
            raise ValueError("duplicate/inconsistent broker order")
        seen.add(cid)
        pending = state.pending.get(cid)
        if cid.startswith("dia-base-"):
            if cid not in state.consumed_ids:
                raise ValueError("unknown source-method order")
            if not journal._path(cid).exists():
                raise ValueError("broker order has no own durable dispatch provenance")
            if pending is not None:
                if (
                    pending["symbol"] != symbol
                    or pending["side"] != side
                    or pending["quantity"] != qty
                    or pending["filled"] != done
                ):
                    raise ValueError("actual own order/fill prefix needs reconciliation")
            else:
                closed = [
                    v
                    for v in evidence.get("terminal_liability_holds", {}).values()
                    if v["original_client_order_id"] == cid
                ]
                if len(closed) != 1 or closed[0]["original_reservation"]["filled"] != done:
                    raise ValueError("closed own order fill history changed/unreceived")
            if pending is None and status not in {
                "filled",
                "canceled",
                "cancelled",
                "expired",
                "rejected",
            }:
                raise ValueError("released own reservation has live broker order")
        elif (
            status
            in {"new", "accepted", "pending_new", "partially_filled", "pending_cancel", "held"}
            and side == "buy"
        ):
            px = _number(_get(o, "limit_price"))
            if px <= 0:
                raise ValueError("unknown foreign buy liability")
            open_other_buys += (qty - done) * px
        summaries.append(
            dict(cid=cid, symbol=symbol, side=side, qty=qty, filled=done, status=status)
        )
    # A locally pending order can precede submit, but a consumed dispatch with
    # uncertain acknowledgment must not be mistaken for free cash/new exposure.
    if evidence.get("unresolved_dispatches"):
        raise ValueError("acknowledgment uncertainty requires owned order lookup")
    marks_complete = evidence.get("held_rights_complete") is True
    own_gross = 0.0
    held_quote_ns = {}
    for symbol, quantity in own.items():
        quote = quotes.get(symbol)
        if not quote or quote.get("valid") is not True or quantity < 0:
            marks_complete = False
            continue
        stamp = quote.get("timestamp_ns")
        if not held_quote_fresh(stamp, clock()):
            marks_complete = False
            continue
        held_quote_ns[symbol] = stamp
        bid = _number(quote["bid"])
        if bid <= 0:
            marks_complete = False
            continue
        own_gross += quantity * bid
    nav = state.cashbook.nav_cash() + own_gross if marks_complete else None
    current_risk_session = (
        evidence.get("risk_session") == started.astimezone(NEW_YORK).date().isoformat()
    )
    # Missing opening baseline forbids new risk, not independently authorized reductions.
    risk_marks_complete = marks_complete and current_risk_session
    risk = risk_state(
        nav,
        evidence["day_open_nav"],
        evidence["high_water"],
        marks_complete=risk_marks_complete,
        prior_daily_halt=evidence["daily_halt"],
        prior_kill=evidence["kill"],
    )
    if not current_risk_session and marks_complete and nav is not None:
        high = _number(evidence["high_water"])
        if high > 0:
            risk["kill"] = risk["kill"] or nav / high - 1 <= -0.25
            risk["high_water"] = max(high, nav)
            risk["reason"] = "missing_session_open_NAV; drawdown_still_evaluated"
    gross = sum(abs(_number(_get(p, "market_value"))) for p in positions)
    # Explicit nonmarginable BP + cash intersection; ordinary leveraged BP is
    # not used. Other-reserved excludes observed open buys in this scope schema.
    available = min(
        _number(_get(account, "cash")), _number(_get(account, "non_marginable_buying_power"))
    )
    capacity = owned_account_capacity(
        allocated=auth["allocated_usd"],
        account_unborrowed_available=available,
        other_reserved_cash=_number(auth["other_reserved_cash_excluding_open_buys"])
        + open_other_buys,
        account_gross=gross,
        account_gross_cap=auth["account_gross_cap"],
        sleeve_gross=own_gross,
        existing_own_buy_reservations=state.cash_reserved(),
        conflicts=False,
        identity_matches=True,
        complete_observation=True,
    )
    tradable = {}
    assets = {}
    for symbol in sorted(set(quotes) | set(own)):
        asset = client.get_asset(symbol)
        assets[symbol] = dict(
            symbol=str(_get(asset, "symbol")),
            status=_text(_get(asset, "status")),
            tradable=_get(asset, "tradable"),
        )
        tradable[symbol] = (
            assets[symbol]["symbol"] == symbol
            and assets[symbol]["status"] == "active"
            and assets[symbol]["tradable"] is True
        )
    completed = clock()
    if completed > started + timedelta(seconds=15):
        raise ValueError("current account batch exceeded its declared freshness")
    row = dict(
        account_hash=auth["account_hash"],
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        valid_until=(started + timedelta(seconds=15)).isoformat(),
        complete=True,
        conflicts=False,
        all_owned_events_applied=True,
        owned_state_sha256=_hash(revision),
        new_risk_allowed=risk["new_risk_allowed"],
        global_stop=False,
        risk=risk,
        own_nav=nav,
        own_gross=own_gross,
        held_quote_ns=held_quote_ns,
        tradable=tradable,
        assets=assets,
        risk_session_current=current_risk_session,
        unborrowed_new_capacity=capacity,
        sleeve_new_gross_capacity=max(
            0.0, auth["allocated_usd"] - own_gross - state.cash_reserved()
        ),
        actual_positions=actual,
        orders=summaries,
        method_invocations=4 + len(assets),
        account_used_fields={
            k: _get(account, k)
            for k in (
                "cash",
                "non_marginable_buying_power",
                "equity",
                "account_blocked",
                "trading_blocked",
            )
        },
        capture_basis="SDK-normalized used fields, not a raw HTTP body or full account export",
        wire_HTTP_count="UNKNOWN",
        receiver_acceptance=auth["bindings"]["native_acceptance"],
        captures=[],
        limit=(
            "API observation and exact declared foreign-position scope; "
            "no fees/dividends/settlement inferred"
        ),
    )
    _ensure_durable_directory(directory.absolute())
    path = directory / "observation.json"
    if path.exists():
        raise ValueError("observation slot already consumed")
    _atomic_write_text(path, json.dumps(row, sort_keys=True, indent=2, allow_nan=False) + "\n")
    import hashlib

    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
