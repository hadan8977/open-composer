"""Live scheduling: one idempotent loop per account, safe to start from cron every few minutes.

``run_live`` takes a non-blocking file lock (a second copy exits quietly), waits for the open,
ticks once per minute boundary (each strategy only computes on its own timeframe boundaries),
and finishes the session after the close.  Process death is handled by starting it again: the
engine rebuilds its state from the event log and re-checks unresolved orders by client id.
"""

from __future__ import annotations

import fcntl
import json
import time as _time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.intraday_runner.bars import (
    AlpacaMinuteProvider,
    ArchiveMinuteProvider,
    MinuteProvider,
    SessionBars,
    session_bounds,
)
from open_composer.intraday_runner.broker import AlpacaPaperBroker, Broker
from open_composer.intraday_runner.config import (
    RunnerConfig,
    load_runner_authorization,
    load_runner_config,
)
from open_composer.intraday_runner.engine import RunnerEngine, runner_dir
from open_composer.intraday_runner.ratelimit import RateLimiter
from open_composer.intraday_runner.reporting import finish_session
from open_composer.market_calendar import NEW_YORK, us_equity_session_close

PRE_OPEN_START_MINUTES = 20
POST_CLOSE_FINISH_MINUTES = 3


def today_et(now: datetime) -> date:
    return now.astimezone(NEW_YORK).date()


def latest_boundary(now: datetime) -> pd.Timestamp:
    return pd.Timestamp(now).tz_convert("UTC").floor("min")


def load_opening(root: Path, config: RunnerConfig, session: date) -> dict[str, Any]:
    """Overnight positions of strategies that may hold them: carry file of the last session."""
    base = runner_dir(root, config.account)
    if not base.is_dir():
        return {}
    earlier = sorted(p for p in base.iterdir() if p.is_dir() and p.name[:10] < session.isoformat())
    for folder in reversed(earlier):
        carry = folder / "carry.json"
        if carry.is_file():
            payload = json.loads(carry.read_text(encoding="utf-8"))
            allowed = {s.name for s in config.strategies if s.allow_overnight}
            return {k: v for k, v in payload.get("carry", {}).items() if k in allowed}
    return {}


def build_engine(
    config: RunnerConfig,
    root: Path,
    session: date,
    broker: Broker,
    *,
    allow_paper_orders: bool,
    live_provider: MinuteProvider | None = None,
    now: datetime | None = None,
    limiter: RateLimiter | None = None,
    **kwargs: Any,
) -> RunnerEngine:
    snap = broker.account_snapshot()
    auth_id = "plan-only"
    if allow_paper_orders:
        auth = load_runner_authorization(config, root, account_id_hash=snap.id_hash, now=now)
        auth_id = auth.authorization_id
    provider = live_provider or AlpacaMinuteProvider(
        config.live_feed, account=config.account, limiter=limiter
    )
    bars = SessionBars(provider, config.all_symbols, session)
    return RunnerEngine(
        config,
        root,
        session,
        broker,
        bars,
        history_provider=ArchiveMinuteProvider(),
        submit_orders=allow_paper_orders,
        mode="paper" if allow_paper_orders else "plan_only",
        auth_id=auth_id,
        opening=load_opening(root, config, session),
        **kwargs,
    )


def make_alpaca_broker(account: str, limiter: RateLimiter | None = None) -> Broker:
    from open_composer.book_paper.accounts import make_trading_client

    return AlpacaPaperBroker(make_trading_client(account), limiter)


def preflight(broker: Broker, opening: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read-only: the account must hold nothing but declared overnight carry and have no open
    orders before the first paper order of a session.  Reports only, never closes or cancels."""
    expected: dict[str, float] = {}
    for item in (opening or {}).values():
        for symbol, qty in item.get("positions", {}).items():
            expected[symbol] = expected.get(symbol, 0.0) + float(qty)
    positions = {k: v for k, v in broker.positions().items() if abs(v) > 1e-9}
    unexpected = {s: q for s, q in positions.items() if abs(q - expected.get(s, 0.0)) > 1e-6} | {
        s: -q for s, q in expected.items() if s not in positions and abs(q) > 1e-9
    }
    orders = broker.open_orders()
    return {
        "ok": not unexpected and not orders,
        "positions": positions,
        "unexpected_positions": unexpected,
        "open_orders": [
            {"symbol": o.symbol, "side": o.side, "qty": o.qty, "status": o.status} for o in orders
        ],
    }


def replay_started(base: Path, session: date) -> bool:
    events = base / session.isoformat() / "events.jsonl"
    return events.is_file() and events.stat().st_size > 0


def run_live(
    config_path: Path,
    root: Path,
    *,
    allow_paper_orders: bool,
    once: bool = False,
    broker: Broker | None = None,
    live_provider: MinuteProvider | None = None,
    kill_check: Callable[[], str | None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = _time.sleep,
) -> dict[str, Any]:
    config = load_runner_config(config_path)
    base = runner_dir(root, config.account)
    base.mkdir(parents=True, exist_ok=True)
    lock = (base / "run.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"status": "already_running"}
    try:
        now = clock()
        session = today_et(now)
        if us_equity_session_close(session) is None:
            return {"status": "not_a_session", "session": session.isoformat()}
        open_ts, close_ts = session_bounds(session)
        if pd.Timestamp(now) > close_ts + pd.Timedelta(hours=2):
            return {"status": "after_hours", "session": session.isoformat()}
        limiter = RateLimiter(config.api_calls_per_minute)
        broker = broker or make_alpaca_broker(config.account, limiter)
        if allow_paper_orders and not replay_started(base, session):
            check = preflight(broker, load_opening(root, config, session))
            if not check["ok"]:
                (base / f"preflight-{session.isoformat()}.json").write_text(
                    json.dumps(check, indent=2, sort_keys=True), encoding="utf-8"
                )
                return {"status": "preflight_failed", **check}
        engine = build_engine(
            config,
            root,
            session,
            broker,
            allow_paper_orders=allow_paper_orders,
            live_provider=live_provider,
            now=now,
            kill_check=kill_check,
            limiter=limiter,
        )
        engine.start(now)
        if engine.state.summarized:
            return {"status": "already_finished", "session": session.isoformat()}
        engine.preload()
        ticked = 0
        last: pd.Timestamp | None = None
        while True:
            now = clock()
            stamp = pd.Timestamp(now)
            if stamp >= close_ts + pd.Timedelta(minutes=POST_CLOSE_FINISH_MINUTES):
                break
            boundary = latest_boundary(now)
            ready = boundary + pd.Timedelta(seconds=config.bar_delay_seconds)
            if boundary > open_ts and boundary < close_ts and stamp >= ready and boundary != last:
                stale = (stamp - boundary).total_seconds() > config.max_tick_staleness_seconds
                engine.tick(boundary, now, stale=stale)
                last = boundary
                ticked += 1
                if once:
                    return {"status": "ticked", "tick": boundary.isoformat(), "ticks": ticked}
            elif once:
                return {"status": "not_due", "now": stamp.isoformat()}
            next_wake = boundary + pd.Timedelta(minutes=1, seconds=config.bar_delay_seconds)
            if stamp < open_ts - pd.Timedelta(minutes=PRE_OPEN_START_MINUTES):
                return {"status": "too_early", "now": stamp.isoformat()}
            sleep(max(1.0, (next_wake - stamp).total_seconds()))
        outcome = finish_session(engine, clock())
        return {"status": "finished", "ticks": ticked, **{"report": outcome["report"]}}
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def minutes_to(ts: pd.Timestamp, now: datetime) -> float:
    return (ts - pd.Timestamp(now)) / timedelta(minutes=1)
