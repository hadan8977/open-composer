"""Pure controls for the fixed source-method quote waves and paper lifecycle.

No signal selection, provider, broker write or new research engine. These
functions consume already-bound source intents and actual account observations;
they cannot themselves certify the observations or authorize a live process.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta

from open_composer.market_sessions import (
    NEW_YORK,
    next_us_equity_session,
    us_equity_session_close,
)


def finite_nonnegative(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not monetary capacity")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("unknown or negative monetary capacity")
    return value


def primary_calendar(formation_month_end: date) -> dict:
    """Calendar only; it cannot turn a late reconstruction into an actual signal."""
    if (formation_month_end + timedelta(days=1)).month == formation_month_end.month:
        raise ValueError("formation month must be complete")
    decision = next_us_equity_session(formation_month_end)
    close = us_equity_session_close(decision)
    if close is None:
        raise ValueError("missing decision session")
    return {
        "decision": decision,
        "signal_cutoff": datetime.combine(decision, time(9, 35), NEW_YORK),
        "commit_at": datetime.combine(decision, close, NEW_YORK) + timedelta(minutes=15),
        "execution": next_us_equity_session(decision),
    }


def require_primary_commit(
    formation_month_end: date,
    execution_day: date,
    *,
    source_cutoff: datetime,
    produced_at: datetime,
    committed_at: datetime,
    authorized_at: datetime,
) -> None:
    """Reject late/backdated/off-cycle adoption; no quantities or fit are invented."""
    clocks = (source_cutoff, produced_at, committed_at, authorized_at)
    if any(clock.tzinfo is None for clock in clocks):
        raise ValueError("naive source/commit clock")
    expected = primary_calendar(formation_month_end)
    if execution_day != expected["execution"] or source_cutoff != expected["signal_cutoff"]:
        raise ValueError("not the original monthly source/execution calendar")
    if not authorized_at <= source_cutoff <= produced_at <= expected["commit_at"]:
        raise ValueError("not an authorized contemporaneously available signal")
    # Fixed quantity commitment: late completion is no order, not a new entry date.
    if committed_at != expected["commit_at"]:
        raise ValueError("quantity commitment missed its frozen clock")


def owned_account_capacity(
    *,
    allocated: float,
    account_unborrowed_available: float,
    other_reserved_cash: float,
    account_gross: float,
    account_gross_cap: float,
    sleeve_gross: float,
    existing_own_buy_reservations: float,
    conflicts: bool,
    identity_matches: bool,
    complete_observation: bool,
) -> float:
    """Pure intersection, not a certification of broker BP or account authority.

    Broker leveraged buying_power is NOT an admissible substitute for the
    verified unborrowed field. The caller must classify other-sleeve encumbrances
    without silently subtracting the same reservation twice.
    """
    if conflicts is not False or identity_matches is not True or complete_observation is not True:
        raise ValueError("account identity, ownership or observation is unresolved")
    values = [
        allocated,
        account_unborrowed_available,
        other_reserved_cash,
        account_gross,
        account_gross_cap,
        sleeve_gross,
        existing_own_buy_reservations,
    ]
    allocation, cash, others, gross, gross_cap, own_gross, reserved = map(
        finite_nonnegative, values
    )
    if not 0 < allocation <= 20000 or gross_cap <= 0:
        raise ValueError("outside bounded sleeve/account envelope")
    return max(
        0.0,
        min(
            cash - others - reserved,
            gross_cap - gross - reserved,
            allocation - own_gross - reserved,
        ),
    )


def cleanup_clock(expiry: datetime) -> tuple[date, datetime, datetime]:
    """Last full eligible regular session, including an earlier account expiry."""
    if expiry.tzinfo is None:
        raise ValueError("expiry must carry timezone")
    day = expiry.astimezone(NEW_YORK).date()
    for _ in range(10):
        close_time = us_equity_session_close(day)
        close = datetime.combine(day, close_time, NEW_YORK) if close_time is not None else None
        if close is not None and close < expiry:
            return day, close - timedelta(minutes=30), close - timedelta(seconds=60)
        day -= timedelta(days=1)
    raise ValueError("no supported cleanup session before expiry")


def risk_state(
    nav: float | None,
    day_open_nav: float,
    high_water: float,
    *,
    marks_complete: bool,
    prior_daily_halt: bool,
    prior_kill: bool,
) -> dict:
    """Same-session halt and persistent kill are latched, never auto-renewed."""
    if any(type(flag) is not bool for flag in (marks_complete, prior_daily_halt, prior_kill)):
        raise ValueError("unknown mark/latch state; no risk decision or latch reset")
    valid = (
        marks_complete
        and nav is not None
        and math.isfinite(float(nav))
        and all(math.isfinite(float(v)) and float(v) > 0 for v in (day_open_nav, high_water))
    )
    if not valid:
        return {
            "new_risk_allowed": False,
            "daily_halt": prior_daily_halt,
            "kill": prior_kill,
            "reason": "incomplete_mark_or_NAV",
            "high_water": high_water,
        }
    daily_halt = prior_daily_halt or nav / day_open_nav - 1 <= -0.05
    kill = prior_kill or nav / high_water - 1 <= -0.25
    return {
        "new_risk_allowed": not daily_halt and not kill,
        "daily_halt": daily_halt,
        "kill": kill,
        "high_water": max(nav, high_water),
        "reason": "killed" if kill else "daily_new_risk_halt" if daily_halt else "ok",
    }


def require_window(
    now: datetime,
    execution_day: date,
    side: str,
    *,
    authorized_at: datetime,
    expires_at: datetime,
    cleanup: bool = False,
    own_exit_allowed: bool = False,
    killed: bool = False,
) -> datetime:
    """Five-second dispatch allowance is explicit prospective latency adaptation."""
    if any(type(flag) is not bool for flag in (cleanup, own_exit_allowed, killed)):
        raise ValueError("unknown cleanup/exit/kill evidence; no order window")
    if any(t.tzinfo is None for t in (now, authorized_at, expires_at)):
        raise ValueError("naive authority clock")
    if not authorized_at <= now < expires_at:
        raise ValueError("outside authorization interval")
    if side not in {"buy", "sell"} or now.astimezone(NEW_YORK).date() != execution_day:
        raise ValueError("wrong side or execution day")
    close_time = us_equity_session_close(execution_day)
    if close_time is None:
        raise ValueError("not a trading session")
    close = datetime.combine(execution_day, close_time, NEW_YORK)
    if cleanup:
        if side != "sell" or not own_exit_allowed:
            raise ValueError("cleanup permits only authorized own-long reductions")
        wind_day, start, last = cleanup_clock(expires_at)
        opened = datetime.combine(execution_day, time(9, 30), NEW_YORK)
        permitted = (
            opened <= now < close - timedelta(seconds=60)
            if killed
            else (execution_day == wind_day and start <= now < last)
        )
        if not permitted:
            raise ValueError("outside bounded owned cleanup interval")
        return now
    wind_day, _, _ = cleanup_clock(expires_at)
    if execution_day >= wind_day:
        raise ValueError("ordinary waves forbidden in the wind-down session")
    wave = datetime.combine(execution_day, time(9, 35 if side == "sell" else 40), NEW_YORK)
    if not wave <= now <= wave + timedelta(seconds=5):
        raise ValueError("outside frozen wave dispatch interval")
    return wave


def live_quote_ok(quote: dict, now: datetime, wave: datetime) -> bool:
    """The source parser must run first; also reject aged quotes at actual dispatch."""
    if quote.get("valid") is not True:
        return False
    timestamp = quote.get("timestamp_ns")
    if type(timestamp) is not int:
        return False
    now_ns = int(now.astimezone(UTC).timestamp()) * 10**9 + now.microsecond * 1000
    wave_ns = int(wave.astimezone(UTC).timestamp()) * 10**9 + wave.microsecond * 1000
    return wave_ns - 5 * 10**9 <= timestamp <= wave_ns and 0 <= now_ns - timestamp <= 5 * 10**9


def buy_batch(
    requests: list[dict],
    quotes: dict[str, dict],
    *,
    now: datetime,
    wave: datetime,
    owned_source_capacity: float,
    accepted_unborrowed_capacity: float,
    sleeve_new_gross_capacity: float,
    fee_buffer_rate: float,
    new_risk_allowed: bool,
) -> list[dict]:
    """Preserve source order, side-size cap, uniform affordability and whole floor.

    No replacement names, greedy remainder, future-sale credit or extra shares
    after a favorable price. The caller separately verifies target/commit hashes.
    """
    if type(new_risk_allowed) is not bool:
        raise ValueError("risk decision must be an explicit boolean")
    budget = min(
        finite_nonnegative(v)
        for v in (
            owned_source_capacity,
            accepted_unborrowed_capacity,
            sleeve_new_gross_capacity,
        )
    )
    if not math.isfinite(fee_buffer_rate) or not 0 <= fee_buffer_rate < 1:
        raise ValueError("invalid fee buffer")
    if len({r["symbol"] for r in requests}) != len(requests):
        raise ValueError("duplicate source name")
    rows = []
    for req in requests:
        q = req["max_quantity"]
        if type(q) is not int or q < 0:
            raise ValueError("non-whole committed request")
        quote = quotes.get(req["symbol"], {})
        valid = new_risk_allowed and live_quote_ok(quote, now, wave)
        size, price = quote.get("ask_shares"), quote.get("ask")
        valid = valid and type(size) is int and size > 0 and type(price) in (int, float)
        valid = valid and math.isfinite(price) and price > 0
        rows.append(
            {
                "symbol": req["symbol"],
                "committed_max": q,
                "capped": min(q, size) if valid else 0,
                "price": price if valid else None,
            }
        )
    needed = sum(r["capped"] * (r["price"] or 0) * (1 + fee_buffer_rate) for r in rows)
    scale = min(1.0, budget / needed) if needed else 1.0
    for row in rows:
        row["quantity"] = math.floor(row["capped"] * scale + 1e-10)
        row["scale"] = scale
        assert 0 <= row["quantity"] <= row["capped"] <= row["committed_max"]
    spent = sum(r["quantity"] * (r["price"] or 0) * (1 + fee_buffer_rate) for r in rows)
    if spent > budget + 1e-7:
        raise ValueError("rounding exceeds actual reserved capacity")
    return rows
