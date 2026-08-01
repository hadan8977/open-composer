from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from open_composer.execution_policy import ExecutionPolicyBinding
from open_composer.market_calendar import us_equity_session_close
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec

NEW_YORK = ZoneInfo("America/New_York")
MAX_SIGNAL_CREATION_AGE = timedelta(minutes=15)
PAPER_SNAPSHOT_STALE_SECONDS = 15 * 60
_INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}
OPEN_ORDER_START = time(9, 20)
OPEN_ORDER_CUTOFF = time(9, 27)


def require_fresh_paper_signal(
    signal: Signal,
    *,
    observed_at: datetime | None = None,
) -> None:
    now = (observed_at or datetime.now(UTC)).astimezone(UTC)
    if signal.created_at.tzinfo is None or signal.timestamp.tzinfo is None:
        raise ValueError("paper signal timestamps must be timezone-aware")
    created_at = signal.created_at.astimezone(UTC)
    creation_age = now - created_at
    if creation_age < timedelta(minutes=-1) or creation_age > MAX_SIGNAL_CREATION_AGE:
        raise ValueError("paper signal creation timestamp is stale or in the future")

    timestamp = signal.timestamp.astimezone(UTC)
    if timestamp > now + timedelta(minutes=1):
        raise ValueError("paper signal market timestamp is in the future")
    if signal.timeframe == "daily":
        expected_session = latest_completed_us_equity_session(now)
        signal_session = timestamp.astimezone(NEW_YORK).date()
        if signal_session != expected_session:
            raise ValueError(
                "daily paper signal does not reference the latest completed US equity session"
            )
        return
    if signal.timeframe == "weekly":
        if now - timestamp > timedelta(days=8):
            raise ValueError("weekly paper signal market timestamp is stale")
        return
    minutes = _INTRADAY_MINUTES.get(signal.timeframe)
    if minutes is None:
        raise ValueError(f"paper signal freshness is unsupported for {signal.timeframe}")
    local_now = now.astimezone(NEW_YORK)
    session_close = us_equity_session_close(local_now.date())
    if session_close is None:
        raise ValueError("intraday paper signal cannot be submitted on a non-trading day")
    local_time = local_now.timetz().replace(tzinfo=None)
    if local_time < time(9, 30) or local_time > session_close:
        raise ValueError("intraday paper signal is outside regular trading hours")
    max_market_age = timedelta(minutes=(minutes * 2) + 5)
    if now - timestamp > max_market_age:
        raise ValueError("intraday paper signal market timestamp is stale")
    if timestamp.astimezone(NEW_YORK).date() != local_now.date():
        raise ValueError("intraday paper signal is not from the current US session date")


def latest_completed_us_equity_session(observed_at: datetime) -> date:
    local = observed_at.astimezone(NEW_YORK)
    candidate = local.date()
    close = us_equity_session_close(candidate)
    if close is None or local.timetz().replace(tzinfo=None) < close:
        candidate -= timedelta(days=1)
        while us_equity_session_close(candidate) is None:
            candidate -= timedelta(days=1)
    return candidate


def require_paper_order_window(
    spec: StrategySpec,
    policy: ExecutionPolicyBinding,
    *,
    observed_at: datetime | None = None,
) -> None:
    now = (observed_at or datetime.now(UTC)).astimezone(NEW_YORK)
    session_close = us_equity_session_close(now.date())
    if session_close is None:
        raise ValueError("paper orders cannot be submitted on a non-trading day")
    current_time = now.timetz().replace(tzinfo=None)
    style = str(policy.payload.get("order_style") or "").lower()
    opening_order = style in {"moo_market", "opg_limit", "loo_limit"} or (
        style == "day_market"
        and spec.execution.fill_assumption in {"next_bar_open", "next_regular_open"}
        and spec.timeframe == "daily"
    )
    if opening_order:
        if not OPEN_ORDER_START <= current_time <= OPEN_ORDER_CUTOFF:
            raise ValueError("opening paper orders are only allowed from 09:20 through 09:27 ET")
        return
    if not time(9, 30) <= current_time <= session_close:
        raise ValueError("regular-session paper orders are outside market hours")
