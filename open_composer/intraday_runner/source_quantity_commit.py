"""Original whole-share sizing with explicit real seal and nominal effective clocks.

No fetching, signal fit, time backdating or off-cycle adoption. The actual
received close/account/rights packet and original forecast are caller-owned
native input receptions. Early computation is conditional on subsequently
proved unchanged applicable own-state version through the nominal commitment.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import _atomic_write_text
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory, _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes, source_module
from open_composer.intraday_runner.source_method_controls import primary_calendar
from open_composer.intraday_runner.source_state_checkpoint import restore
from open_composer.market_sessions import NEW_YORK, us_equity_session_close


def clock(value):
    if re.search(r"\.\d{7,}", value):
        raise ValueError("native clock precision must not silently truncate")
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("actual aware clock required")
    return value


def confirm_continuity(commit: dict, proof: dict, *, actual_sealed_at: str):
    """Proof must come from the authenticated receiver, not a caller boolean."""
    if proof.get("accepted") is not True or proof.get("complete_own_state") is not True:
        raise ValueError("applicable own-state continuity is not verified")
    if (
        proof.get("state_sha256") != commit["state_sha256"]
        or proof.get("account_hash") != commit["account_hash"]
    ):
        raise ValueError("relevant own cash/holding/NAV version changed before commitment")
    if (
        not clock(commit["actual_created_at"])
        <= clock(actual_sealed_at)
        <= clock(commit["committed_at"])
        <= clock(proof["observed_at"])
    ):
        raise ValueError("subsecond/late/future commitment continuity violated")
    if clock(proof["reconciled_through"]) < clock(commit["committed_at"]):
        raise ValueError("receiver has not covered nominal commitment")


def prepare_commit(
    root: Path,
    *,
    forecast_reception: dict,
    quantity_input: dict,
    revision: dict,
    account_hash: str,
    output: Path,
    now=lambda: datetime.now(UTC),
) -> dict:
    import numpy as np

    received = json.loads(bound_bytes(root, forecast_reception))
    q = json.loads(bound_bytes(root, quantity_input))
    forecast = received["forecast"]
    contract = json.loads(bound_bytes(root, q["scientific_contract"]))
    if (
        received.get("accepted") is not True
        or forecast.get("policy") != "DIA28_BASE_SEQUENTIAL_ORIGINAL"
        or forecast["symbols"] != contract["output_identity"]
        or forecast["formation_month"] != "2026-10"
        or q.get("formation_month") != "2026-10"
        or q.get("accepted") is not True
    ):
        raise ValueError("not actual accepted October formation input")
    cal = primary_calendar(date(2026, 10, 31))
    deadline = cal["commit_at"]
    created = now()
    closed = datetime.combine(cal["decision"], us_equity_session_close(cal["decision"]), NEW_YORK)
    if not closed <= clock(q["received_at"]) <= created <= deadline:
        raise ValueError("decision close not received or quantity computation late")
    if not clock(received["completed_at"]) <= created or q.get("held_rights_complete") is not True:
        raise ValueError("forecast/held rights unavailable")
    if q.get("account_hash") != account_hash or q.get("state_sha256") != _hash(revision):
        raise ValueError("price/NAV/own-state reception identity mismatch")
    if (
        q.get("price_basis") != "raw_completed_decision_close"
        or q.get("price_session") != cal["decision"].isoformat()
    ):
        raise ValueError("wrong price basis/session")
    state, _, _, _ = restore(root, revision["snapshot"])
    symbols = forecast["symbols"]
    weights = np.asarray(forecast["weights"], float)
    if (
        len(symbols) != 28
        or len(set(symbols)) != 28
        or len(weights) != 28
        or not np.isfinite(weights).all()
        or any(w not in (0.0, 0.2) for w in weights)
        or sum(weights) > 0.999999999 + 1e-8
    ):
        raise ValueError("not frozen BASE weights/identity")
    if any(state.cashbook.quantity(s) for s in set(state.cashbook.lots) - set(symbols)):
        raise ValueError("nonordinary held asset must remain explicitly accounted; no deletion")
    if state.pending:
        raise ValueError("pending liabilities prevent quantity commitment")
    prices = np.asarray([q["prices"].get(s, float("nan")) for s in symbols], float)
    holdings = np.asarray([state.cashbook.quantity(s) for s in symbols], float)
    needed = (holdings > 0) | (weights > 0)
    if not np.isfinite(prices[needed]).all() or any(prices[needed] <= 0):
        raise ValueError("missing needed close")
    if any(
        q["hygiene_valid"].get(s) is not True or q["split_trigger"].get(s) is not False
        for s in np.asarray(symbols)[needed]
    ):
        raise ValueError("raw price/unit hygiene unavailable")
    nav = state.cashbook.nav_cash() + sum(holdings[needed] * prices[needed])
    if abs(nav - float(q["own_nav"])) > 1e-7:
        raise ValueError("own NAV differs from received basis")
    source = source_module(root, "cash")
    quantities, sizing = source.target_quantities(nav, holdings, prices, weights, 0.001, True)
    # The accepted reference returns target quantities, never an actual fee debit.
    result = dict(
        formation_month_end="2026-10-31",
        execution_day=cal["execution"].isoformat(),
        source_cutoff=cal["signal_cutoff"].isoformat(),
        produced_at=received["completed_at"],
        committed_at=deadline.isoformat(),
        actual_created_at=created.isoformat(),
        state_sha256=_hash(revision),
        account_hash=account_hash,
        forecast_reception=forecast_reception,
        quantity_input_reception=quantity_input,
        settlement_due=source.cash_due_date(
            cal["execution"].isoformat(), source.settlement_calendar()
        ),
        sell=[
            dict(symbol=s, max_quantity=int(max(0, h - t)))
            for s, h, t in zip(symbols, holdings, quantities, strict=True)
        ],
        buy=[
            dict(symbol=s, max_quantity=int(max(0, t - h)))
            for s, h, t in zip(symbols, holdings, quantities, strict=True)
        ],
        publication_started_at=now().isoformat(),
        planning_buffer_only=sizing,
        effective_clock_not_actual_timestamp=True,
    )
    _ensure_durable_directory(output.parent.absolute())
    if output.exists():
        raise ValueError("quantity slot already consumed")
    _atomic_write_text(output, json.dumps(result, indent=2, allow_nan=False) + "\n")
    # Completion after durable publication must also meet the deadline; retain
    # a late file as failure and never relabel it as a successful commitment.
    if now() > deadline:
        raise ValueError("actual durable publication completed late; no trade")
    completed = now()
    completion = dict(
        status="completed", commit_sha256=_hash(result), actual_sealed_at=completed.isoformat()
    )
    if completed > deadline:
        raise ValueError("quantity completion late; retain output without success receipt")
    _atomic_write_text(
        output.with_suffix(output.suffix + ".completed.json"),
        json.dumps(completion, indent=2) + "\n",
    )
    return result
