"""Session-keyed equity evidence shared by paper projection and publication."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from open_composer.market_sessions import (
    next_us_equity_session,
    previous_us_equity_session,
    us_equity_session_close,
)

NY = ZoneInfo("America/New_York")
D = Decimal


def parse_stamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def snapshot_session(captured_at: datetime) -> date | None:
    """Use an after-close observation only before the next premarket begins.

    This remains an explicitly timestamped account observation, not an official
    closing print. Once next-session prices may move (04:00 New York), current
    equity cannot supply the previous session's missing historical equity.
    """
    local = captured_at.astimezone(NY)
    close = us_equity_session_close(local.date())
    day = (
        local.date()
        if close is not None and local.time() >= close
        else previous_us_equity_session(local.date())
    )
    next_premarket = datetime.combine(next_us_equity_session(day), time(4), tzinfo=NY)
    return day if local < next_premarket else None


def account_equity_points(capture: dict) -> dict[date, dict]:
    """Positive, nondegenerate daily observations and one eligible snapshot."""
    captured_at = parse_stamp(capture["captured_at"])
    local = captured_at.astimezone(NY)
    close = us_equity_session_close(local.date())
    completed = (
        local.date()
        if close is not None and local.time() >= close
        else previous_us_equity_session(local.date())
    )
    history = capture["portfolio_history"]
    result = {}
    previous = None
    for stamp, value in sorted(zip(history["timestamp"], history["equity"], strict=True)):
        equity = D(str(value)) if value is not None else D(0)
        if not equity.is_finite() or equity <= 0:
            continue
        at = datetime.fromtimestamp(stamp, UTC)
        day = at.astimezone(NY).date()
        if day > completed or us_equity_session_close(day) is None:
            continue
        if previous is not None and equity <= previous * D("0.1"):
            continue
        result[day] = dict(
            at=at.isoformat(),
            equity_usd=equity,
            source="alpaca_portfolio_history_1D",
            valuation="broker_daily_equity_snapshot",
        )
        previous = equity
    day = snapshot_session(captured_at)
    live = D(str((capture.get("account") or {}).get("equity") or 0))
    if (
        day is not None
        and day not in result
        and live.is_finite()
        and live > 0
        and (previous is None or live > previous * D("0.1"))
    ):
        result[day] = dict(
            at=captured_at.isoformat(),
            equity_usd=live,
            source="alpaca_account_snapshot",
            valuation="broker_account_snapshot_after_close",
        )
    return result
