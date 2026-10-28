"""No-write preparation of one frozen BASE wave, with original pure readers.

This component never creates a client, fetches a quote, submits/cancels an order,
or persists a production reservation. It returns a copy for an eventual reviewed
transport to journal atomically before sending. Preparing a request is not a fill
or a native/account authorization; missing live evidence remains a blocker.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from open_composer.intraday_runner.source_method_bindings import quote_metadata, source_module
from open_composer.intraday_runner.source_method_controls import (
    buy_batch,
    live_quote_ok,
    require_primary_commit,
    require_window,
)
from open_composer.intraday_runner.source_reservations import SourceReservations
from open_composer.market_sessions import previous_us_equity_session
from open_composer.research.features.price_hygiene import DEFAULT_MAX_ONE_DAY_PRICE_RATIO


def prepare_wave(
    *,
    root: Path,
    metadata_bindings: dict,
    state: SourceReservations,
    commit: dict,
    commit_sha256: str,
    universe: set[str],
    now: datetime,
    side: str,
    authorized_at: datetime,
    expires_at: datetime,
    quote_response: dict,
    prior_references: dict,
    accepted_unborrowed_capacity: float,
    sleeve_new_gross_capacity: float,
    fee_buffer_rate: float,
    new_risk_allowed: bool,
    global_stop: bool,
) -> tuple[SourceReservations, dict]:
    """Compile bound committed whole quantities, preserving all no-order reasons.

    The quote envelope and account capacities are supplied evidence, not facts
    established here. A live caller still needs current independent source,
    account, ownership, native and authorization checks. No generic market order
    fallback, retry, replacement name, or post-fill quantity resize exists here.
    """
    if type(global_stop) is not bool or type(new_risk_allowed) is not bool:
        raise ValueError("missing explicit kill/risk state")
    encoded = json.dumps(commit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != commit_sha256:
        raise ValueError("quantity commitment binding mismatch")
    day = date.fromisoformat(commit["execution_day"])
    require_primary_commit(
        date.fromisoformat(commit["formation_month_end"]),
        day,
        source_cutoff=datetime.fromisoformat(commit["source_cutoff"]),
        produced_at=datetime.fromisoformat(commit["produced_at"]),
        committed_at=datetime.fromisoformat(commit["committed_at"]),
        authorized_at=authorized_at,
    )
    wave = require_window(now, day, side, authorized_at=authorized_at, expires_at=expires_at)
    rows = commit[side]
    if len({r["symbol"] for r in rows}) != len(rows):
        raise ValueError("duplicate symbol in committed wave")
    if any(r["symbol"] not in universe for r in rows):
        raise ValueError("commit outside frozen owned universe")
    if any(type(r["max_quantity"]) is not int or r["max_quantity"] < 0 for r in rows):
        raise ValueError("committed quantity is not whole nonnegative")
    if any(
        r["max_quantity"] > 0
        and f"dia-base-{day.isoformat()}-{side}-{r['symbol']}" in state.consumed_ids
        for r in rows
    ):
        raise ValueError("intent already consumed; reconcile only, never resize/retry")
    due = commit["settlement_due"]
    cash_reference = source_module(root, "cash")
    expected_due = cash_reference.cash_due_date(
        day.isoformat(), cash_reference.settlement_calendar()
    )
    if due != expected_due:
        raise ValueError("settlement date differs from the accepted source calendar")
    working = copy.deepcopy(state)
    result = {
        "role": "no-write wave preparation, not actual operation",
        "commit_sha256": commit_sha256,
        "wave": wave.isoformat(),
        "side": side,
        "requests": [],
        "not_requested": [],
        "broker_calls": 0,
    }
    if global_stop or quote_response.get("status") != 200 or quote_response.get("feed") != "sip":
        result["blocked"] = "global_stop" if global_stop else "required_source_unavailable"
        result["not_requested"] = [{**r, "reason": result["blocked"]} for r in rows]
        return working, result
    parser = source_module(root, "quotes")
    conditions, venues = quote_metadata(root, metadata_bindings)
    cutoff = parser.timestamp_ns(wave.isoformat())
    quotes = {}
    for row in rows:
        symbol = row["symbol"]
        raw = quote_response.get("quotes", {}).get(symbol, [])
        try:
            quote = parser.select_quote(raw, cutoff, day.isoformat(), conditions, venues)
        except (KeyError, ValueError, TypeError, OverflowError):
            quote = {"valid": False, "reason": "malformed_or_outside_fixed_quote_window"}
        ref = prior_references.get(symbol)
        # Never validate a wave using this execution day's later open/close.
        if (
            not ref
            or ref.get("completed_before_execution") is not True
            or ref.get("session_date") != previous_us_equity_session(day).isoformat()
            or type(ref.get("split_session")) is not bool
            or type(ref.get("hygiene_valid")) is not bool
        ):
            quote = {**quote, "valid": False, "reason": "prior_reference_unavailable"}
        else:
            quote = parser.prior_unit_guard(
                quote,
                ref["close"],
                ref["hygiene_valid"],
                ref["split_session"],
                DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
            )
        if quote["valid"] and not live_quote_ok(quote, now, wave):
            quote = {**quote, "valid": False, "reason": "stale_at_actual_dispatch"}
        quotes[symbol] = quote
    if side == "buy":
        planned = buy_batch(
            rows,
            quotes,
            now=now,
            wave=wave,
            owned_source_capacity=working.available(due),
            accepted_unborrowed_capacity=accepted_unborrowed_capacity,
            sleeve_new_gross_capacity=sleeve_new_gross_capacity,
            fee_buffer_rate=fee_buffer_rate,
            new_risk_allowed=new_risk_allowed,
        )
    else:
        planned = []
        for row in rows:
            quote = quotes[row["symbol"]]
            planned.append(
                {
                    **row,
                    "quantity": min(row["max_quantity"], quote["bid_shares"])
                    if quote["valid"]
                    else 0,
                    "price": quote.get("bid"),
                }
            )
    for row in planned:
        symbol, quantity = row["symbol"], row["quantity"]
        if not quantity:
            result["not_requested"].append(
                {
                    "symbol": symbol,
                    "reason": quotes[symbol].get("reason")
                    if not quotes[symbol]["valid"]
                    else "zero_commit_or_funding_or_risk_capacity",
                }
            )
            continue
        cid = f"dia-base-{day.isoformat()}-{side}-{symbol}"
        if side == "sell":
            reservation = working.reserve_sell(
                cid,
                symbol,
                quantity,
                row["price"],
                day.isoformat(),
                due,
                fee_buffer_rate=fee_buffer_rate,
            )
        else:
            reservation = working.reserve_buy(
                cid,
                symbol,
                quantity,
                row["price"],
                quantity * row["price"] * fee_buffer_rate,
                day.isoformat(),
                due,
            )
        result["requests"].append(
            {
                "client_order_id": cid,
                "symbol": symbol,
                "side": side,
                "qty": quantity,
                "type": "limit",
                "time_in_force": "day",
                "limit_price": row["price"],
                "quote": quotes[symbol],
                "reservation": reservation,
                "commit_sha256": commit_sha256,
                "cancel_policy": (
                    "one immediate own-remainder cancellation; unknown retains reservation"
                ),
            }
        )
    return working, result
