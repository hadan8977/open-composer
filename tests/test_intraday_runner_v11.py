"""Runner v1.1: per-strategy flatten time with 30 s retries, official previous close."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from test_intraday_runner import (  # noqa: E402
    CLOSE_TS,
    SESSION,
    Env,
    et,
    strategy,
)

from open_composer.intraday_runner import live  # noqa: E402
from open_composer.intraday_runner.bars import (  # noqa: E402
    AlpacaDailyCloseProvider,
    FrameMinuteProvider,
    StaticPrevClose,
)
from open_composer.intraday_runner.broker import SimBroker  # noqa: E402
from open_composer.intraday_runner.config import RunnerConfigError, load_runner_config  # noqa: E402
from open_composer.intraday_runner.engine import RunnerEngine, TickReport  # noqa: E402
from open_composer.intraday_runner.plugins import (  # noqa: E402
    IntradayPlugin,
    PluginContext,
    PluginDecision,
    Target,
    register_plugin,
)
from open_composer.market_calendar import NEW_YORK  # noqa: E402

HALF_DAY = date(2026, 11, 27)  # closes 13:00 ET


def utc_ts(day: date, hhmm: str) -> pd.Timestamp:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return pd.Timestamp(datetime.combine(day, time(hour, minute), tzinfo=NEW_YORK)).tz_convert(
        "UTC"
    )


# ---------------------------------------------------------------------------
# flatten time


def test_flatten_time_is_per_strategy_and_the_default_stays_1555(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("default", {"10:00": {"AAA": 100}}, symbols=("AAA",)),
            strategy("late", {"10:00": {"BBB": 100}}, symbols=("BBB",), flatten_et="15:58"),
        ],
    )
    env.tick("10:00")
    assert env.pos("default") == {"AAA": 100} and env.pos("late") == {"BBB": 100}
    env.tick("15:54")
    assert env.pos("default") == {"AAA": 100}
    env.tick("15:55")
    assert env.pos("default") == {} and env.pos("late") == {"BBB": 100}  # late holds on
    env.tick("15:57")
    assert env.pos("late") == {"BBB": 100}
    env.tick("15:58")
    assert env.pos("late") == {}
    flats = {e["symbol"]: e["purpose"] for e in env.of("net_order") if e["flatten"]}
    assert flats == {"AAA": "f1555", "BBB": "f1558"}
    assert env.engine.flatten_ts == et("15:55")  # earliest strategy time


def test_flatten_time_range_is_validated(tmp_path):
    def build(value):
        raw = {
            "runner_name": "r",
            "account": "quant2",
            "account_caps": {"max_gross_notional_usd": 1e6, "max_daily_loss_usd": 1e5},
            "strategies": [strategy("s", {}, flatten_et=value)],
        }
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return load_runner_config(path)

    assert build("15:45").strategy("s").flatten_et == time(15, 45)
    assert build("15:59").strategy("s").flatten_et == time(15, 59)
    for bad in ("15:44", "16:00", "09:30"):
        with pytest.raises(RunnerConfigError, match="15:45 and 15:59"):
            build(bad)


def test_half_day_flattens_the_same_minutes_before_the_close(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("a", {}),
            strategy("b", {}, flatten_et="15:58"),
            strategy("c", {}, flatten_et="15:45"),
        ],
    )
    env.session = HALF_DAY
    engine = env.new_engine()
    assert engine.flatten_ts_by == {
        "a": utc_ts(HALF_DAY, "12:55"),  # 5 minutes before the 13:00 close
        "b": utc_ts(HALF_DAY, "12:58"),  # 2 minutes before
        "c": utc_ts(HALF_DAY, "12:45"),  # 15 minutes before
    }


# ---------------------------------------------------------------------------
# retry


def test_unfilled_flatten_is_retried_with_a_new_order_id_until_flat(tmp_path):
    broker = SimBroker(lambda s: 100.0)
    env = Env(tmp_path, [strategy("s", {"10:00": {"AAA": 100}}, flatten_et="15:58")], broker=broker)
    env.tick("10:00")
    assert broker.positions() == {"AAA": 100.0}
    broker.hold_unfilled = True  # the market flatten order is accepted but does not fill
    env.tick("15:58")
    first = broker.submit_calls[-1][3]
    assert env.pos("s") == {"AAA": 100} and env.engine.flatten_open(et("15:58"))
    broker.hold_unfilled = False  # next attempt, 30 s later
    later = et("15:58").to_pydatetime().astimezone(UTC) + timedelta(seconds=35)
    env.engine.tick(et("15:58"), later, retry=1)
    assert broker.cancelled == [first]  # the stale order is cancelled and confirmed first
    second = broker.submit_calls[-1][3]
    assert second != first and len([c for c in broker.submit_calls if c[1] == "sell"]) == 2
    assert broker.positions() == {} and env.pos("s") == {}
    assert not env.engine.flatten_open(et("15:58"))
    purposes = [e["purpose"] for e in env.of("net_order") if e["flatten"]]
    assert purposes == ["f1558", "f1558r1"]


def test_retry_of_the_same_minute_is_idempotent_after_a_restart(tmp_path):
    broker = SimBroker(lambda s: 100.0)
    env = Env(tmp_path, [strategy("s", {"10:00": {"AAA": 100}}, flatten_et="15:58")], broker=broker)
    env.tick("10:00")
    broker.hold_unfilled = True
    env.tick("15:58")
    later = et("15:58").to_pydatetime().astimezone(UTC) + timedelta(seconds=35)
    env.engine.tick(et("15:58"), later, retry=1)
    calls = len(broker.submit_calls)
    restarted = env.new_engine()
    restarted.tick(et("15:58"), later, retry=1)
    # the retry order of that minute is in the log: a restart sends nothing again
    assert len(broker.submit_calls) == calls


class _Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds: float):
        self.now += timedelta(seconds=seconds)


def test_live_loop_retries_every_30_seconds_and_stops_30_seconds_before_the_close(
    tmp_path, monkeypatch
):
    env = Env(tmp_path, [strategy("s", {}, flatten_et="15:57")])
    calls: list[tuple[pd.Timestamp, int, datetime]] = []

    def fake_tick(self, decision_ts, now, *, stale=False, retry=0):
        calls.append((decision_ts, retry, now))
        return TickReport(tick=decision_ts.isoformat())

    monkeypatch.setattr(RunnerEngine, "tick", fake_tick)
    monkeypatch.setattr(RunnerEngine, "preload", lambda self: None)
    monkeypatch.setattr(RunnerEngine, "flatten_open", lambda self, ts: ts >= et("15:57"))
    monkeypatch.setattr(live, "finish_session", lambda engine, now: {"report": "stub"})
    clock = _Clock(et("15:55").to_pydatetime().astimezone(UTC))
    outcome = live.run_live(
        tmp_path / "runner.yaml",
        tmp_path,
        allow_paper_orders=False,
        broker=env.broker,
        live_provider=FrameMinuteProvider(env.frame, "iex_test"),
        kill_check=lambda: None,
        clock=clock,
        sleep=clock.sleep,
    )
    assert outcome["status"] == "finished"
    retries = [(ts, now) for ts, retry, now in calls if retry]
    assert [ts for ts, _ in retries] == [et("15:57"), et("15:58")]  # 15:59:35 is past the limit
    for ts, now in retries:  # 5 s bar delay + 30 s after the minute boundary
        assert 35 <= (now - ts.to_pydatetime()).total_seconds() < 37
    assert max(now for _ts, _r, now in calls if _r) <= CLOSE_TS.to_pydatetime() - timedelta(
        seconds=30
    )


# ---------------------------------------------------------------------------
# previous close


@register_plugin("test_prev_close_probe")
class ProbePlugin(IntradayPlugin):
    seen: list[dict] = []

    def decide(self, ctx: PluginContext) -> PluginDecision:
        ProbePlugin.seen.append(dict(ctx.prev_close_raw))
        return PluginDecision(targets={s: Target(shares=0) for s in self.symbols})


def _history(prev_close: dict[str, float]) -> FrameMinuteProvider:
    """Prior session minute bars whose last close is ``prev_close`` (the fallback source)."""
    prev = date(2026, 10, 1)
    start = utc_ts(prev, "09:30")
    rows = []
    for symbol, last in prev_close.items():
        for i in range(390):
            price = last if i == 389 else last * 0.99
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": start + pd.Timedelta(minutes=i),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 10.0,
                    "trade_count": 1.0,
                    "vwap": price,
                }
            )
    return FrameMinuteProvider(pd.DataFrame(rows), "sip")


def _probe_env(tmp_path, **kw):
    ProbePlugin.seen.clear()
    cfg = strategy("p", {}, symbols=("AAA", "BBB"), plugin="test_prev_close_probe")
    return Env(tmp_path, [cfg], prices={"AAA": 100.0, "BBB": 50.0}, **kw)


def test_prev_close_comes_from_the_provider_and_is_logged(tmp_path):
    env = _probe_env(tmp_path)
    engine = env.new_engine(prev_close_provider=StaticPrevClose({"AAA": 99.5, "BBB": 49.0}))
    env.tick("10:00", engine)
    assert ProbePlugin.seen[-1] == {"AAA": 99.5, "BBB": 49.0}
    event = env.of("prev_close", engine)[0]
    assert event["source"] == "static" and event["from_source"] == ["AAA", "BBB"]
    assert not env.of("prev_close_fallback", engine)
    assert len(env.of("prev_close", engine)) == 1  # loaded once per session


def test_missing_daily_close_falls_back_to_the_last_minute_close_with_a_flag(tmp_path):
    env = _probe_env(tmp_path)
    engine = env.new_engine(
        prev_close_provider=StaticPrevClose({"AAA": 99.5}),  # BBB not returned
        history_provider=_history({"AAA": 1.0, "BBB": 48.0}),
    )
    env.tick("10:00", engine)
    assert ProbePlugin.seen[-1] == {"AAA": 99.5, "BBB": 48.0}
    flag = env.of("prev_close_fallback", engine)[0]
    assert flag["symbols"] == ["BBB"] and flag["used_minute_close"] == ["BBB"]
    assert env.of("prev_close", engine)[0]["from_minute_fallback"] == ["BBB"]


def test_failing_daily_source_falls_back_for_every_symbol_and_never_blocks_the_tick(tmp_path):
    class Broken:
        source = "alpaca_daily_raw_sip"

        def fetch(self, symbols, session):
            raise RuntimeError("HTTP 429")

    env = _probe_env(tmp_path)
    engine = env.new_engine(
        prev_close_provider=Broken(), history_provider=_history({"AAA": 98.0, "BBB": 48.0})
    )
    report = env.tick("10:00", engine)
    assert report.skipped is None
    assert ProbePlugin.seen[-1] == {"AAA": 98.0, "BBB": 48.0}
    flag = env.of("prev_close_fallback", engine)[0]
    assert flag["symbols"] == ["AAA", "BBB"] and "429" in flag["reason"]
    # nothing at all (no provider data, no history): the plugin simply sees no prev close
    (tmp_path / "bare").mkdir()
    bare = _probe_env(tmp_path / "bare")
    engine2 = bare.new_engine(prev_close_provider=Broken())
    bare.tick("10:00", engine2)
    assert ProbePlugin.seen[-1] == {}
    assert bare.of("prev_close", engine2)[0]["unavailable"] == ["AAA", "BBB"]


def test_prev_close_survives_a_restart_without_a_second_request(tmp_path):
    env = _probe_env(tmp_path)
    engine = env.new_engine(prev_close_provider=StaticPrevClose({"AAA": 99.5, "BBB": 49.0}))
    env.tick("10:00", engine)

    class Boom:
        def fetch(self, symbols, session):
            raise AssertionError("must not be called again")

    again = env.new_engine(prev_close_provider=Boom())
    env.tick("10:01", again)
    assert ProbePlugin.seen[-1] == {"AAA": 99.5, "BBB": 49.0}


def test_alpaca_daily_provider_uses_raw_sip_daily_bars_of_the_previous_session():
    seen = {}

    def fake(symbols, start, end):
        seen.update(symbols=symbols, start=start, end=end)
        stamps = [
            pd.Timestamp("2026-09-30 04:00", tz="UTC"),
            pd.Timestamp("2026-10-01 04:00", tz="UTC"),
        ]
        return pd.DataFrame(
            [
                {"symbol": "AAA", "timestamp": stamps[0], "close": 10.0},
                {"symbol": "AAA", "timestamp": stamps[1], "close": 11.0},
                {"symbol": "BBB", "timestamp": stamps[0], "close": 20.0},  # no 10-01 bar
            ]
        )

    class Limiter:
        calls = 0

        def acquire(self, n=1):
            Limiter.calls += n

    provider = AlpacaDailyCloseProvider(fetch_raw=fake, limiter=Limiter())
    assert provider.fetch(["AAA", "BBB"], SESSION) == {"AAA": 11.0}
    assert Limiter.calls == 1  # takes a slot of the shared limiter
    assert seen["start"] == utc_ts(date(2026, 10, 1), "00:00")
    assert seen["end"] == utc_ts(SESSION, "00:00")
    empty = AlpacaDailyCloseProvider(fetch_raw=lambda *a: pd.DataFrame())
    assert empty.fetch(["AAA"], SESSION) == {}


def test_static_prev_close_reads_a_json_file(tmp_path):
    path = tmp_path / "prev.json"
    path.write_text('{"spy": 500.25}', encoding="utf-8")
    provider = StaticPrevClose({"QQQ": 400.0}, path)
    assert provider.fetch(["SPY", "QQQ", "IWM"], SESSION) == {"SPY": 500.25, "QQQ": 400.0}


def test_replay_session_signature_takes_prev_close_arguments():
    import inspect

    from open_composer.intraday_runner.replay import replay_session

    names = inspect.signature(replay_session).parameters
    assert "prev_close_raw" in names and "prev_close_file" in names
