"""Prospective BASE initialization controls; no account, source or order calls.

The current policy is separate from the historical sequential SIP experiment.
Validated observations are broker receipt facts, never exchange-time claims.
"""

from __future__ import annotations

import copy
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, InvalidOperation

from open_composer.market_sessions import NEW_YORK, us_equity_session_close

TASK = "BASE-CURRENT-INITIALIZATION-20261019"
DAY = date(2026, 10, 20)
CAP = Decimal("10000")
CENT = Decimal(".01")
ENV_PATH = "/root/.config/open-composer/paper-validation-20261019.env"
ACCOUNT = "fa6147de4f85f4f14f225c59eebb9ecc4c764e87571f413afebcb63aa76c81d4"
NAMESPACE = "basecur-20261019-fa6147de"


def number(value, *, nonnegative=True):
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid amount") from exc
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError("nonfinite/negative amount")
    return result


def aware(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("naive actual clock")
    return result.astimezone(UTC)


def session(day):
    close = us_equity_session_close(day)
    if close is None:
        raise ValueError("not an equity session")
    return (
        datetime.combine(day, time(9, 30), NEW_YORK).astimezone(UTC),
        datetime.combine(day, close, NEW_YORK).astimezone(UTC),
    )


def winddown(expiry):
    expiry = aware(expiry)
    day = expiry.astimezone(NEW_YORK).date()
    for _ in range(10):
        if us_equity_session_close(day) is not None:
            opening, close = session(day)
            end = min(close, expiry)
            if opening <= end - timedelta(minutes=15):
                return day, end - timedelta(minutes=15), end - timedelta(minutes=5)
        day -= timedelta(days=1)
    raise ValueError("no bounded winddown session")


def require_phase(now, phase, authorized_at, expiry, *, killed=False, prospective=False):
    if type(killed) is not bool or type(prospective) is not bool:
        raise ValueError("unknown kill latch")
    now, start, expiry = map(aware, (now, authorized_at, expiry))
    if not start <= now < expiry or expiry > datetime(2026, 11, 14, tzinfo=UTC):
        raise ValueError("outside exact authority")
    if prospective and phase in {"decision", "opening", "buy", "cancel"}:
        # Explicit new Oct20 contract only. Old job/authority callers retain
        # their original fixed windows. No next-day auto-extension.
        lo = datetime(2026, 10, 20, 14, 40, tzinfo=UTC)
        hi = datetime(2026, 10, 20, 19, 30, tzinfo=UTC)
        if phase == "cancel":
            lo = datetime(2026, 10, 20, 19, 50, tzinfo=UTC)
            hi = datetime(2026, 10, 20, 19, 55, tzinfo=UTC)
    elif phase == "decision":
        lo, hi = datetime.combine(DAY, time(), UTC), session(DAY)[0]
    elif phase in {"opening", "risk", "reconcile", "settle"}:
        actual_day = now.astimezone(NEW_YORK).date()
        if actual_day < DAY:
            raise ValueError("before the prospective initialization")
        opening, close = session(actual_day)
        if phase == "opening":
            lo, hi = opening, opening + timedelta(seconds=60)
        elif phase in {"risk", "settle"}:
            lo, hi = opening, min(close, expiry)
        else:
            lo, hi = close + timedelta(minutes=5), min(close + timedelta(minutes=10), expiry)
    elif phase in {"buy", "cancel"}:
        bounds = {
            "buy": ((13, 40), (13, 41)),
            "cancel": ((14, 0), (14, 5)),
            "reconcile": ((20, 5), (20, 10)),
        }
        a, b = bounds[phase]
        lo = datetime.combine(DAY, time(*a), UTC)
        hi = datetime.combine(DAY, time(*b), UTC)
    elif phase == "exit":
        day = now.astimezone(NEW_YORK).date()
        opening, close = session(day)
        if killed:
            lo, hi = opening, min(close, expiry) - timedelta(seconds=60)
        else:
            wd, lo, hi = winddown(expiry)
            if wd != day:
                raise ValueError("not the authorized winddown day")
    else:
        raise ValueError("unknown finite phase")
    if not lo <= now < hi:
        raise ValueError("outside fixed phase window")
    if phase == "buy" and killed:
        raise ValueError("kill latch blocks entry")


def limit_price(reference, *, exit_order=False):
    p = number(reference)
    if p < 1:
        raise ValueError("this scoped tick rule requires USD price >=1")
    return (p * (Decimal(".995") if exit_order else 1)).quantize(
        CENT, rounding=ROUND_CEILING if exit_order else ROUND_FLOOR
    )


def require_broker_open(observation, now):
    clock = observation.get("broker_clock", {})
    if clock.get("is_open") is not True:
        raise ValueError("broker regular market not observed open")
    stamp = aware(clock["timestamp"])
    received = aware(observation["broker_clock_received_at"])
    now = aware(now)
    if not stamp <= received <= now or now - stamp > timedelta(seconds=15):
        raise ValueError("broker market clock stale/future")


def identity(cid, symbol, side, day=DAY, *, cleanup=False, namespace=NAMESPACE):
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        raise ValueError("invalid symbol")
    if type(cleanup) is not bool or side not in {"buy", "sell"} or (side == "sell") != cleanup:
        raise ValueError("only initial buy or owned exit")
    if namespace not in {
        NAMESPACE,
        "h5cur-20261019-fa6147de",
        "lstmcur-20261019-fa6147de",
        "basest-20261019-fa6147de",
        "multeq-20261019-fa6147de",
        "multhi-20261019-fa6147de",
    }:
        raise ValueError("unselected sleeve namespace")
    expected = f"{namespace}-{day:%m%d}-{'exit' if cleanup else 'buy'}-{symbol}"
    if cid != expected or len(cid) > 48:
        raise ValueError("wrong isolated intent identity")


def receive_observation(
    observation, *, now, now_monotonic, account_hash, checkpoint_hash, purpose="new_risk"
):
    """Check a complete authenticated capture supplied by the bound receiver.

    This function verifies values/coverage, not authentication by a magic flag.
    The runtime must bind immutable actual capture bytes and final GET gateway.
    """
    o = copy.deepcopy(observation)
    start, last, end, now = map(
        aware, (o["started_at"], o["last_response_at"], o["completed_at"], now)
    )
    if not start <= last <= end <= now:
        raise ValueError("future/reversed observation clocks")
    oldest = aware(o["oldest_response_at"])
    if not start <= oldest <= last or now - oldest > timedelta(seconds=15):
        raise ValueError("oldest actual account/mark response stale")
    ms, me, mn = (
        number(x) for x in (o["started_monotonic"], o["completed_monotonic"], now_monotonic)
    )
    if not 0 <= me - ms <= 15 or not 0 <= mn - me <= 15:
        raise ValueError("stale or slow monotonic capture")
    if end - start > timedelta(seconds=15) or now - end > timedelta(seconds=15):
        raise ValueError("stale or slow UTC capture")
    # A discontinuity cannot make a stale snapshot young in another clock.
    if (
        abs(float(me - ms) - (end - start).total_seconds()) > 0.25
        or abs(float(mn - me) - (now - end).total_seconds()) > 0.25
    ):
        raise ValueError("paired clock discontinuity")
    if (
        account_hash != ACCOUNT
        or o["account_hash"] != account_hash
        or o["checkpoint_hash"] != checkpoint_hash
    ):
        raise ValueError("account or checkpoint differs")
    if purpose not in {"new_risk", "owned_exit", "owned_cancel"}:
        raise ValueError("unknown observation purpose")
    required = ["positions_complete", "orders_complete", "actions_complete", "units_reconciled"]
    if purpose == "owned_cancel":
        required = ["orders_complete"]
    if purpose == "new_risk":
        required += ["activities_complete", "cash_reconciled", "fees_complete"]
    for key in required:
        if o.get(key) is not True:
            raise ValueError(f"incomplete observation: {key}")
    if o["currency"] != "USD" or o["account_status"] != "ACTIVE":
        raise ValueError("account status/currency")
    for key in ("trading_blocked", "account_blocked", "trade_suspended"):
        if o.get(key) is not False:
            raise ValueError("unknown or blocked account")
    if purpose == "owned_cancel":
        return {**o, "purpose": "owned_cancel_only", "liability_or_fee_holds_released": False}
    held = o["holdings"]
    seen = set()
    marked = Decimal(0)
    for row in held:
        symbol, qty = row["symbol"], row["quantity"]
        if symbol in seen or type(qty) is not int or qty <= 0 or row.get("owned") is not True:
            raise ValueError("duplicate/foreign/nonwhole holding")
        seen.add(symbol)
        p, value = number(row["current_price"]), number(row["market_value"])
        if p <= 0 or (p * qty).quantize(CENT, rounding=ROUND_HALF_EVEN) != value.quantize(
            CENT, rounding=ROUND_HALF_EVEN
        ):
            raise ValueError("unpriced or inconsistent mark")
        marked += p * qty
    if purpose == "owned_exit":
        return {
            **o,
            "verified_nav": None,
            "marked_value": str(marked),
            "purpose": "owned_exit_only",
            "new_risk_permitted": False,
            "liability_or_fee_holds_released": False,
        }
    amounts = {
        k: number(o[k])
        for k in (
            "own_cash",
            "trade_receivables",
            "valued_rights",
            "purchase_payables",
            "fee_liabilities",
            "other_liabilities",
            "unborrowed_available",
        )
    }
    nav = (
        amounts["own_cash"]
        + marked
        + amounts["trade_receivables"]
        + amounts["valued_rights"]
        - amounts["purchase_payables"]
        - amounts["fee_liabilities"]
        - amounts["other_liabilities"]
    )
    if nav <= 0 or nav != number(o["own_nav"]):
        raise ValueError("invalid/incomplete own NAV")
    return {**o, "verified_nav": str(nav), "marked_value": str(marked)}


def risk_transition(previous, observation, *, now, opening=False, capital=CAP, initializing=False):
    """Pure transition; caller persists before any dependent operation."""
    p = copy.deepcopy(previous)
    if (
        type(opening) is not bool
        or type(initializing) is not bool
        or (initializing and not opening)
        or any(type(p.get(k)) is not bool for k in ("halted", "killed"))
    ):
        raise ValueError("unknown prior risk latches or baseline mode")
    nav, high = number(observation["verified_nav"]), number(p["high_water"])
    capital = number(capital)
    if (
        capital not in {Decimal(10000), Decimal(6000), Decimal(4000), Decimal(20000)}
        or high <= 0
        or number(p["initial_capital"]) + number(p.get("net_allocation_flows", 0)) != capital
    ):
        raise ValueError("invalid durable risk baseline")
    day = aware(now).astimezone(NEW_YORK).date().isoformat()
    if opening:
        start, end = aware(observation["started_at"]), aware(observation["completed_at"])
        if initializing:
            lo = datetime(2026, 10, 20, 14, 40, tzinfo=UTC)
            hi = datetime(2026, 10, 20, 19, 30, tzinfo=UTC)
            if not lo <= start <= end <= aware(now) < hi:
                raise ValueError("not the prospective initialization observation")
            if p.get("day") is not None or p.get("initialization_baseline") is not None:
                raise ValueError("initialization baseline cannot be reset")
            if p.get("day_open_nav") is not None:
                raise ValueError("existing actual opening baseline cannot be relabeled")
            p["initialization_baseline"] = dict(
                day=day,
                nav=str(nav),
                at=end.isoformat(),
                kind="prospective_initialization",
                actual_regular_opening_NAV=False,
            )
            p.update(day=day, halted=p["halted"] or p["killed"])
        else:
            opened = session(date.fromisoformat(day))[0]
            if not opened <= start <= end < opened + timedelta(seconds=60):
                raise ValueError("not an actual opening observation")
            if p.get("day") == day:
                raise ValueError("opening baseline cannot be reset")
            p.update(day=day, day_open_nav=str(nav), halted=p["killed"])
    initial = p.get("initialization_baseline", {})
    baseline = initial.get("nav") if initial.get("day") == day else p.get("day_open_nav")
    if p.get("day") != day or baseline is None or number(baseline) <= 0:
        raise ValueError("missing actual session NAV baseline")
    if initial.get("day") == day and (
        initial.get("kind") != "prospective_initialization"
        or initial.get("actual_regular_opening_NAV") is not False
        or aware(initial["at"]).astimezone(NEW_YORK).date().isoformat() != day
    ):
        raise ValueError("invalid retained initialization baseline")
    p["high_water"] = str(max(high, nav))
    p["killed"] = p["killed"] or nav <= Decimal(".75") * max(high, nav)
    p["halted"] = p["halted"] or p["killed"] or nav <= Decimal(".95") * number(baseline)
    p["last_nav"] = str(nav)
    return p
