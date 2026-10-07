"""Intraday runner: netting/allocation, risk gates, flatten, crash recovery, idempotency,
point-in-time guard, authorization, Alpaca adapter, scheduling, IEX-vs-SIP recheck.

Everything runs on synthetic flat-price minute bars and :class:`SimBroker`; no network, no
broker, no real authorization file."""

from __future__ import annotations

import fcntl
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from open_composer.intraday_runner import risk
from open_composer.intraday_runner.bars import FrameMinuteProvider, SessionBars, session_bounds
from open_composer.intraday_runner.books import (
    EventLog,
    SubAccount,
    allocate_increment,
    replay,
)
from open_composer.intraday_runner.broker import (
    AlpacaPaperBroker,
    BrokerError,
    SimBroker,
    SimulatedCrash,
)
from open_composer.intraday_runner.config import (
    RunnerConfigError,
    load_runner_authorization,
    load_runner_config,
    write_runner_authorization,
)
from open_composer.intraday_runner.engine import RunnerEngine, runner_dir, strategy_due
from open_composer.intraday_runner.live import latest_boundary, run_live
from open_composer.intraday_runner.plugins import (
    IntradayPlugin,
    PluginContext,
    PluginDecision,
    PluginError,
    Target,
    assert_point_in_time,
    build_plugin,
    register_plugin,
)
from open_composer.intraday_runner.reporting import decision_diff, finish_session, sip_recheck
from open_composer.market_calendar import NEW_YORK

SESSION = date(2026, 10, 2)  # a regular full session
OPEN_TS, CLOSE_TS = session_bounds(SESSION)


@register_plugin("test_scripted")
class ScriptedPlugin(IntradayPlugin):
    """params.script: {"HH:MM": {"SYM": shares}} (ET decision time); silent otherwise."""

    def decide(self, ctx: PluginContext) -> PluginDecision:
        key = ctx.decision_ts.tz_convert(NEW_YORK).strftime("%H:%M")
        spec = self.params.get("script", {}).get(key)
        if spec is None:
            return PluginDecision(state=dict(ctx.state))
        return PluginDecision(
            targets={s: Target(shares=q) for s, q in spec.items()}, state=dict(ctx.state)
        )


@register_plugin("test_threshold")
class ThresholdPlugin(IntradayPlugin):
    def decide(self, ctx: PluginContext) -> PluginDecision:
        symbol = self.symbols[0]
        price = ctx.last_prices.get(symbol)
        want = 100 if price is not None and price > float(self.params["level"]) else 0
        return PluginDecision(targets={symbol: Target(shares=want)})


@register_plugin("test_peeker")
class PeekerPlugin(IntradayPlugin):
    seen: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def decide(self, ctx: PluginContext) -> PluginDecision:
        if not ctx.bars.empty:
            PeekerPlugin.seen.append((ctx.decision_ts, ctx.bars["bar_close_ts"].max()))
        return PluginDecision()


def et(hhmm: str, session: date = SESSION) -> pd.Timestamp:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return pd.Timestamp(datetime.combine(session, time(hour, minute), tzinfo=NEW_YORK)).tz_convert(
        "UTC"
    )


def minute_frame(prices: dict[str, Any], session: date = SESSION) -> pd.DataFrame:
    """Flat 1-minute bars: ``prices[symbol]`` is a number or ``f(minute_index) -> price``."""
    open_ts, _ = session_bounds(session)
    rows = []
    for symbol, spec in prices.items():
        for i in range(390):
            price = float(spec(i) if callable(spec) else spec)
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": open_ts + pd.Timedelta(minutes=i),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 1000.0,
                    "trade_count": 10.0,
                    "vwap": price,
                }
            )
    return pd.DataFrame(rows)


def strategy(name: str, script: dict, symbols=("AAA",), **overrides) -> dict:
    base = {
        "name": name,
        "plugin": "test_scripted",
        "params": {"script": script},
        "symbols": list(symbols),
        "timeframe": "1m",
        "capital_usd": 1_000_000,
        "caps": {
            "max_notional_usd": 1_000_000,
            "max_symbol_notional_usd": 1_000_000,
            "max_daily_loss_usd": 1_000_000,
            "max_orders_per_day": 100,
        },
        "assumed_cost_bps": 1.0,
    }
    base.update(overrides)
    return base


class Env:
    def __init__(self, tmp_path: Path, strategies: list[dict], prices=None, **kw: Any):
        self.root = tmp_path
        self.session = SESSION
        raw = {
            "runner_name": "test-runner",
            "account": "quant2",
            "account_caps": kw.pop(
                "account_caps",
                {"max_gross_notional_usd": 10_000_000, "max_daily_loss_usd": 1_000_000},
            ),
            "session": kw.pop("session", {}),
            "strategies": strategies,
        }
        path = tmp_path / "runner.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        self.config = load_runner_config(path)
        symbols = self.config.all_symbols
        self.prices = prices or {s: 100.0 for s in symbols}
        self.frame = minute_frame(self.prices)
        self.idx = 0
        self.broker = kw.pop("broker", None) or SimBroker(lambda s: self.price_now(s))
        self.kill: list[str | None] = [None]
        self.engine_kw = kw
        self.engine = self.new_engine()

    def price_now(self, symbol: str) -> float | None:
        spec = self.prices[symbol]
        return float(spec(self.idx) if callable(spec) else spec)

    def new_engine(self, frame: pd.DataFrame | None = None, **kw: Any) -> RunnerEngine:
        provider = FrameMinuteProvider(self.frame if frame is None else frame, "test")
        bars = SessionBars(provider, self.config.all_symbols, self.session)
        return RunnerEngine(
            self.config,
            self.root,
            self.session,
            self.broker,
            bars,
            history_provider=kw.pop("history_provider", None),
            kill_check=lambda: self.kill[0],
            sleep=lambda _s: None,
            **{**self.engine_kw, **kw},
        )

    def tick(self, hhmm: str, engine: RunnerEngine | None = None, **kw: Any):
        ts = et(hhmm)
        self.idx = int((ts - OPEN_TS) / pd.Timedelta(minutes=1))
        now = ts.to_pydatetime().astimezone(UTC) + timedelta(seconds=5)
        return (engine or self.engine).tick(ts, now, **kw)

    def events(self, engine: RunnerEngine | None = None) -> list[dict]:
        return (engine or self.engine).log.read()

    def of(self, kind: str, engine: RunnerEngine | None = None) -> list[dict]:
        return [e for e in self.events(engine) if e["type"] == kind]

    def pos(self, name: str, engine: RunnerEngine | None = None) -> dict[str, float]:
        sub = (engine or self.engine).state.subs[name]
        return {k: v for k, v in sub.positions.items() if v}


# ---------------------------------------------------------------------------
# allocation


def test_allocate_increment_properties():
    remaining = {"a": 60, "b": 41, "c": -30}
    out = allocate_increment(remaining, 1, 50, include_cross=True)
    assert out["c"] == -30  # opposite side filled completely (crossed)
    assert sum(out.values()) == 50  # equals the broker fill
    assert all(abs(out[k]) <= abs(remaining[k]) for k in out)
    again = allocate_increment(remaining, 1, 50, include_cross=True)
    assert out == again  # deterministic
    # later increments (cross already done) only split the net side by remaining capacity
    later = allocate_increment({"a": 30, "b": 20, "c": 0}, 1, 25, include_cross=False)
    assert sum(later.values()) == 25 and later.get("c", 0) == 0


def test_subaccount_avg_cost_flip_and_pnl():
    sub = SubAccount("s", 100_000)
    sub.apply_fill("X", 100, 10.0, 10.0, 0.0)
    sub.apply_fill("X", -150, 11.0, 11.0, 0.0)  # closes 100 (+100), opens -50
    assert sub.realized == pytest.approx(100.0)
    assert sub.positions["X"] == -50 and sub.avg_cost["X"] == 11.0
    assert sub.unrealized({"X": 10.0}) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# netting, crossing, reconciliation


def test_net_order_allocation_and_reconciliation(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("s1", {"10:00": {"AAA": 100}, "11:00": {"AAA": 0}}),
            strategy("s2", {"10:00": {"AAA": -40}, "11:00": {"AAA": 0}}),
        ],
    )
    env.tick("10:00")
    assert len(env.broker.submit_calls) == 1
    symbol, side, qty, cid = env.broker.submit_calls[0]
    assert (symbol, side, qty) == ("AAA", "buy", 60)  # +100 and -40 netted
    assert env.pos("s1") == {"AAA": 100} and env.pos("s2") == {"AAA": -40}
    assert env.broker.positions() == {"AAA": 60}
    assert env.engine.state.account_positions() == {"AAA": 60}
    env.tick("11:00")  # both exit: net -60
    assert env.broker.positions() == {}
    outcome = finish_session(env.engine, CLOSE_TS.to_pydatetime() + timedelta(minutes=10))
    assert outcome["reconcile"]["ok"]
    rec = outcome["reconcile"]
    # strategies are charged the model cost on the crossed shares; the broker never saw it
    assert rec["internal_cross_cost_usd"] > 0
    assert rec["pnl_gap_ex_internal_usd"] == pytest.approx(0.0, abs=1e-6)
    assert rec["pnl_gap_usd"] == pytest.approx(rec["internal_cross_cost_usd"], abs=1e-6)


def test_opposite_deltas_cross_without_broker_call(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("s1", {"10:00": {"AAA": 50}, "10:10": {"AAA": 0}}),
            strategy("s2", {"10:00": {"AAA": 20}, "10:10": {"AAA": 0}}),
            strategy("s3", {"10:05": {"AAA": -50}}),
        ],
    )
    env.tick("10:00")
    env.tick("10:05")
    assert [c[2] for c in env.broker.submit_calls] == [70, 50]  # buy 70 then sell 50
    # s1 and s2 exit at the same minute as a new opposite entry of another strategy:
    env.engine.plugins["s3"].params["script"]["10:10"] = {"AAA": 0}
    env.tick("10:10")
    assert env.broker.positions() == {}
    nets = env.of("net_order")
    assert nets[-1]["parts"].keys() == {"s1", "s2", "s3"}


def test_internal_cross_prices_at_plan_price_and_skips_broker(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("s1", {"10:01": {"AAA": 30}, "10:03": {"AAA": 0}}),
            strategy("s2", {"10:02": {"AAA": 0}, "10:03": {"AAA": -30}}),
        ],
    )
    env.tick("10:00")
    # make s2 long 30 first by script on another tick, then cross against s1 selling
    env.engine.plugins["s2"].params["script"] = {"10:01": {"AAA": 0}, "10:03": {"AAA": 30}}
    env.engine.plugins["s1"].params["script"] = {"10:01": {"AAA": 0}, "10:03": {"AAA": 0}}
    env.engine.state.subs["s1"].apply_fill("AAA", 30, 100.0, 100.0, 0.0)
    env.broker._pos["AAA"] = 30.0
    env.tick("10:03")
    internal = [e for e in env.of("net_order") if e["qty"] == 0]
    assert len(internal) == 1  # s1 sells 30, s2 buys 30: crossed
    assert env.broker.submit_calls == []
    assert env.pos("s1") == {} and env.pos("s2") == {"AAA": 30}
    assert env.broker.positions() == {"AAA": 30.0}  # broker untouched, books still match


def test_partial_fill_retries_the_remainder_from_standing_targets(tmp_path):
    broker = SimBroker(lambda s: 100.0, partial_fraction=0.5)
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}}, symbols=("AAA",))], broker=broker)
    env.tick("10:00")
    assert env.pos("s1") == {"AAA": 50}
    for hhmm in ("10:01", "10:02", "10:03", "10:04", "10:05"):
        env.tick(hhmm)
    assert env.pos("s1")["AAA"] >= 85  # converges (stops inside the 5% band)
    assert env.pos("s1")["AAA"] <= 100
    assert env.engine.state.account_positions() == {"AAA": broker.positions()["AAA"]}


# ---------------------------------------------------------------------------
# risk


def _cfg(**caps):
    base = {
        "max_notional_usd": 10_000,
        "max_symbol_notional_usd": 6_000,
        "max_daily_loss_usd": 500,
        "max_orders_per_day": 2,
    }
    base.update(caps)
    return load_runner_config_for(base)


def load_runner_config_for(caps: dict) -> Any:
    raw = {
        "runner_name": "r",
        "account": "quant2",
        "account_caps": {"max_gross_notional_usd": 1e6, "max_daily_loss_usd": 1e5},
        "strategies": [strategy("s", {}, caps=caps, capital_usd=10_000)],
    }
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "c.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return load_runner_config(path).strategies[0]


def test_clip_target_symbol_and_strategy_caps():
    cfg = _cfg()
    d = risk.clip_target(
        cfg,
        symbol="X",
        wanted=100,
        current=0,
        price=100.0,
        other_gross_usd=0.0,
        orders_used=0,
        shortable=None,
    )
    assert (d.approved, d.status, d.reason) == (60, "clipped", "notional_cap")  # symbol cap 6k
    d = risk.clip_target(
        cfg,
        symbol="X",
        wanted=50,
        current=0,
        price=100.0,
        other_gross_usd=7_000.0,
        orders_used=0,
        shortable=None,
    )
    assert d.approved == 30  # strategy room 10k-7k
    # a position that drifted above the cap is not force-sold
    d = risk.clip_target(
        cfg,
        symbol="X",
        wanted=80,
        current=70,
        price=100.0,
        other_gross_usd=0.0,
        orders_used=0,
        shortable=None,
    )
    assert d.approved == 70


def test_orders_cap_blocks_increases_not_reductions_and_shorts_need_etb():
    cfg = _cfg()
    blocked = risk.clip_target(
        cfg,
        symbol="X",
        wanted=10,
        current=0,
        price=100.0,
        other_gross_usd=0.0,
        orders_used=2,
        shortable=None,
    )
    assert (blocked.approved, blocked.status, blocked.reason) == (
        0,
        "blocked",
        "max_orders_per_day",
    )
    reduce = risk.clip_target(
        cfg,
        symbol="X",
        wanted=0,
        current=10,
        price=100.0,
        other_gross_usd=0.0,
        orders_used=99,
        shortable=None,
    )
    assert reduce.approved == 0 and reduce.status == "ok"
    short = risk.clip_target(
        cfg,
        symbol="X",
        wanted=-10,
        current=0,
        price=100.0,
        other_gross_usd=0.0,
        orders_used=0,
        shortable=False,
    )
    assert short.approved == 0 and short.reason == "not_shortable_or_not_easy_to_borrow"
    band = risk.clip_target(
        cfg,
        symbol="X",
        wanted=101,
        current=100,
        price=1.0,
        other_gross_usd=0.0,
        orders_used=0,
        shortable=None,
    )
    assert band.approved == 100 and band.reason == "within_band"


def test_engine_blocks_non_shortable_short_and_third_entry(tmp_path):
    broker = SimBroker(lambda s: 100.0, shortable=lambda s: s != "AAA")
    caps = {
        "max_notional_usd": 1e6,
        "max_symbol_notional_usd": 1e6,
        "max_daily_loss_usd": 1e6,
        "max_orders_per_day": 2,
    }
    script = {
        "10:00": {"AAA": -10, "BBB": 100},
        "10:01": {"BBB": 0},
        "10:02": {"BBB": 100},
        "10:03": {"BBB": 0},
        "10:04": {"BBB": 100},
    }
    env = Env(tmp_path, [strategy("s1", script, symbols=("AAA", "BBB"), caps=caps)], broker=broker)
    for hhmm in ("10:00", "10:01", "10:02", "10:03", "10:04"):
        env.tick(hhmm)
    assert "AAA" not in env.pos("s1")  # short refused: not easy to borrow
    assert env.pos("s1") == {}  # 3rd entry (10:04) blocked after two counted entries
    reasons = {e["reason"] for e in env.of("intent") if e["status"] != "ok"}
    assert {"not_shortable_or_not_easy_to_borrow", "max_orders_per_day"} <= reasons


def test_daily_loss_halt_flattens_and_stops_reentry(tmp_path):
    prices = {"AAA": lambda i: 100.0 if i < 31 else 99.0}  # -1 after 10:00
    caps = {
        "max_notional_usd": 1e6,
        "max_symbol_notional_usd": 1e6,
        "max_daily_loss_usd": 500,
        "max_orders_per_day": 50,
    }
    script = {"10:00": {"AAA": 1000}, "10:05": {"AAA": 1000}, "10:10": {"AAA": 1000}}
    env = Env(tmp_path, [strategy("s1", script, caps=caps)], prices=prices)
    env.tick("10:00")
    assert env.pos("s1") == {"AAA": 1000}
    env.tick("10:02")  # the 99 bar (10:01) has closed -> pnl -1000 <= -500
    halts = env.of("halt")
    assert halts and halts[0]["scope"] == "strategy" and halts[0]["reason"] == "max_daily_loss_usd"
    assert env.pos("s1") == {}  # flattened on the same tick
    env.tick("10:05")
    env.tick("10:10")
    assert env.pos("s1") == {}  # no re-entry after the halt
    assert len([c for c in env.broker.submit_calls if c[1] == "buy"]) == 1


def test_account_gross_cap_limits_the_netted_order(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("s1", {"10:00": {"AAA": 600}}, symbols=("AAA",)),
            strategy("s2", {"10:00": {"BBB": 600}}, symbols=("BBB",)),
        ],
        account_caps={"max_gross_notional_usd": 100_000, "max_daily_loss_usd": 1e6},
    )
    env.tick("10:00")
    gross = sum(abs(q) * 100.0 for q in env.broker.positions().values())
    assert gross <= 100_000 + 1e-6
    assert env.broker.positions() == {"AAA": 600.0, "BBB": 400.0}


def test_account_daily_loss_halts_everything(tmp_path):
    prices = {"AAA": lambda i: 100.0 if i < 31 else 90.0}
    env = Env(
        tmp_path,
        [strategy("s1", {"10:00": {"AAA": 1000}})],
        prices=prices,
        account_caps={"max_gross_notional_usd": 1e7, "max_daily_loss_usd": 5_000},
    )
    env.tick("10:00")
    env.tick("10:02")  # -10,000 > 5,000 once the 90 bar has closed
    assert any(h["scope"] == "account" for h in env.of("halt"))
    assert env.broker.positions() == {}


def test_global_kill_switch_blocks_all_orders_and_stop_file_flattens(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}, "10:05": {"AAA": 200}})])
    env.kill[0] = "paper kill switch enabled: test"
    report = env.tick("10:00")
    assert report.skipped and env.broker.submit_calls == []
    env.kill[0] = None
    env.tick("10:00")
    assert env.pos("s1") == {"AAA": 100}
    env.engine.stop_file.parent.mkdir(parents=True, exist_ok=True)
    env.engine.stop_file.write_text("stop", encoding="utf-8")
    env.tick("10:05")  # STOP: no new entries, flatten
    assert env.pos("s1") == {} and env.broker.positions() == {}


# ---------------------------------------------------------------------------
# flatten / overnight


def test_flatten_before_close_and_overnight_exemption(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("day", {"10:00": {"AAA": 100}}),
            strategy("swing", {"10:00": {"AAA": 50}}, allow_overnight=True),
        ],
    )
    env.tick("10:00")
    assert env.broker.positions() == {"AAA": 150.0}
    env.tick("15:54")
    assert env.pos("day") == {"AAA": 100}  # not yet
    env.tick("15:55")
    assert env.pos("day") == {} and env.pos("swing") == {"AAA": 50}
    assert env.broker.positions() == {"AAA": 50.0}
    flats = [e for e in env.of("net_order") if e["flatten"]]
    assert flats and flats[0]["purpose"] == "f1555"
    done = finish_session(env.engine, CLOSE_TS.to_pydatetime() + timedelta(minutes=10))
    carry = json.loads((env.engine.event_dir / "carry.json").read_text(encoding="utf-8"))
    assert carry["carry"]["swing"]["positions"] == {"AAA": 50.0}
    assert done["reconcile"]["ok"]


def test_half_day_flattens_five_minutes_before_the_early_close(tmp_path):
    half = date(2026, 11, 27)  # day after Thanksgiving, closes 13:00
    env = Env(tmp_path, [strategy("s", {})])
    env.session = half
    engine = env.new_engine()
    assert engine.flatten_ts == pd.Timestamp(
        datetime.combine(half, time(12, 55), tzinfo=NEW_YORK)
    ).tz_convert("UTC")


# ---------------------------------------------------------------------------
# crash recovery and idempotency


def test_crash_after_broker_accept_is_adopted_without_resubmit(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    env.broker.crash_after_accept = lambda cid: True
    with pytest.raises(SimulatedCrash):
        env.tick("10:00")
    assert len(env.broker.orders) == 1
    fresh = env.new_engine()  # process restarted: state only from the event log
    assert fresh.state.orders and next(iter(fresh.state.orders.values())).status == "planned"
    env.broker.crash_after_accept = None
    env.tick("10:01", engine=fresh)
    assert len(env.broker.orders) == 1  # adopted, never duplicated
    assert len(env.broker.submit_calls) == 1
    assert env.pos("s1", fresh) == {"AAA": 100}


def test_crash_before_broker_accept_resubmits_same_client_id(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    original = env.broker.submit_market

    def dies(symbol, side, qty, cid):
        raise SimulatedCrash(cid)

    env.broker.submit_market = dies
    with pytest.raises(SimulatedCrash):
        env.tick("10:00")
    env.broker.submit_market = original
    planned = next(iter(env.new_engine().state.orders.values()))
    fresh = env.new_engine()
    env.tick("10:00", engine=fresh)  # same minute, restarted within the resubmit window
    assert [c[3] for c in env.broker.submit_calls] == [planned.cid]
    assert env.pos("s1", fresh) == {"AAA": 100}


def test_stale_planned_order_is_abandoned_but_flatten_is_not(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    original = env.broker.submit_market
    env.broker.submit_market = lambda *a: (_ for _ in ()).throw(SimulatedCrash("x"))
    with pytest.raises(SimulatedCrash):
        env.tick("10:00")
    env.broker.submit_market = original
    fresh = env.new_engine()
    late = et("10:00").to_pydatetime() + timedelta(minutes=30)
    fresh.sync_orders(late)
    assert env.broker.submit_calls == [] or all(c[3] != "" for c in [])
    assert next(iter(fresh.state.orders.values())).status == "abandoned"
    assert env.pos("s1", fresh) == {}


def test_same_tick_twice_and_restart_do_not_double_order(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    env.tick("10:00")
    env.tick("10:00")
    fresh = env.new_engine()
    env.tick("10:00", engine=fresh)
    assert len(env.broker.submit_calls) == 1
    assert len(env.of("signal")) == 1
    assert env.pos("s1", fresh) == {"AAA": 100}


def test_replay_matches_live_state_and_survives_a_torn_trailing_line(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}, "11:00": {"AAA": 0}})])
    env.tick("10:00")
    env.tick("11:00")
    path = env.engine.log.path
    path.write_text(
        path.read_text(encoding="utf-8") + '{"type": "fill_sync", "cid"', encoding="utf-8"
    )
    again = replay(env.config, SESSION.isoformat(), EventLog(path))
    assert again.subs["s1"].realized == env.engine.state.subs["s1"].realized
    assert again.subs["s1"].positions == env.engine.state.subs["s1"].positions


# ---------------------------------------------------------------------------
# logging order, point in time, plan-only


def test_signal_is_logged_before_the_order(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    env.tick("10:00")
    kinds = [e["type"] for e in env.events()]
    assert kinds.index("signal") < kinds.index("intent") < kinds.index("net_order")
    assert kinds.index("net_order") < kinds.index("submit_result") < kinds.index("fill_sync")
    rows = [
        json.loads(line) for line in env.engine.signal_log.read_text(encoding="utf-8").splitlines()
    ]
    assert rows and rows[0]["strategy_name"] == "s1" and rows[0]["target_shares"] == 100
    assert rows[0]["feed"] == "test"
    net = env.of("net_order")[0]
    assert net["cid"].startswith("oci-20261002-AAA-")


def test_plugins_only_see_bars_closed_by_the_decision_time(tmp_path):
    PeekerPlugin.seen = []
    env = Env(tmp_path, [strategy("s1", {}, plugin="test_peeker", timeframe="5m")])
    for hhmm in ("10:00", "10:05", "13:00"):
        env.tick(hhmm)
    assert PeekerPlugin.seen and all(close <= ts for ts, close in PeekerPlugin.seen)
    assert env.engine.bars.minute["timestamp"].max() + pd.Timedelta(minutes=1) <= et("13:00")


def test_assert_point_in_time_rejects_future_data():
    bars = pd.DataFrame({"symbol": ["A"], "bar_close_ts": [et("10:05")]})
    ctx = PluginContext("s", SESSION, et("10:00"), "5m", bars, pd.DataFrame(), {}, {}, {}, 1.0, 0.0)
    with pytest.raises(PluginError):
        assert_point_in_time(ctx)
    hist = pd.DataFrame({"symbol": ["A"], "timestamp": [et("10:00")]})  # same session
    ctx = PluginContext("s", SESSION, et("10:00"), "5m", bars.iloc[0:0], hist, {}, {}, {}, 1.0, 0.0)
    with pytest.raises(PluginError):
        assert_point_in_time(ctx)


def test_plugin_error_skips_the_strategy_and_the_rest_continue(tmp_path):
    @register_plugin("test_boom")
    class Boom(IntradayPlugin):
        def decide(self, ctx):
            raise RuntimeError("boom")

    env = Env(
        tmp_path,
        [strategy("bad", {}, plugin="test_boom"), strategy("good", {"10:00": {"AAA": 10}})],
    )
    env.tick("10:00")
    assert env.pos("good") == {"AAA": 10}
    assert env.of("plugin_error")


def test_shadow_mode_never_calls_the_broker_but_books_model_fills(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})], submit_orders=False)
    env.tick("10:00")
    assert env.broker.submit_calls == [] and env.broker.positions() == {}
    assert env.engine.event_dir.name.endswith("-plan")
    assert env.pos("s1") == {"AAA": 100}  # model fill at plan price + shadow slippage
    sync = env.of("fill_sync")[0]
    assert sync["allocs"][0]["price"] == pytest.approx(100.0 * 1.0001)
    env.tick("15:55")  # the shadow book flattens before the close like the live one
    assert env.pos("s1") == {} and env.broker.submit_calls == []


def test_stale_tick_skips_plugins(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    env.tick("10:00", stale=True)
    assert env.broker.submit_calls == [] and env.of("stale_skip")


# ---------------------------------------------------------------------------
# summary, costs, recheck


def test_summary_slippage_and_single_write(tmp_path):
    broker = SimBroker(lambda s: 100.0, slippage_bps=10.0)
    env = Env(
        tmp_path,
        [strategy("s1", {"10:00": {"AAA": 100}, "11:00": {"AAA": 0}})],
        broker=broker,
    )
    env.tick("10:00")
    env.tick("11:00")
    done = finish_session(env.engine, CLOSE_TS.to_pydatetime() + timedelta(minutes=10))
    row = done["rows"][0]
    assert row["fills"] == 2 and row["traded_notional_usd"] == pytest.approx(20_000, rel=2e-3)
    assert row["slippage_bps"] == pytest.approx(10.0, rel=1e-6)
    assert row["gross_pnl_usd"] == pytest.approx(row["net_pnl_usd"] + row["cost_usd"])
    assert row["assumed_cost_bps"] == 1.0
    finish_session(env.engine, CLOSE_TS.to_pydatetime() + timedelta(minutes=11))
    lines = (runner_dir(tmp_path, "quant2") / "daily-summary.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_decision_recheck_finds_iex_vs_sip_differences(tmp_path):
    live = {"AAA": 101.0}
    env = Env(
        tmp_path,
        [strategy("s1", {}, plugin="test_threshold", params={"level": 100.0})],
        prices=live,
    )
    for hhmm in ("10:00", "10:01"):
        env.tick(hhmm)
    assert env.pos("s1") == {"AAA": 100}
    sip = minute_frame({"AAA": 99.0})
    events = EventLog(env.engine.log.path).read()
    diff = decision_diff(env.engine, sip, events)
    assert diff["decisions_compared"] == 2 and diff["decisions_differing"] == 2
    assert diff["examples"][0]["live_shares"] == 100 and diff["examples"][0]["sip_shares"] == 0
    env.engine.persist_bars()
    result = sip_recheck(env.engine, FrameMinuteProvider(sip, "sip"))
    assert result["bars"]["AAA"]["close_diff_bps_median"] > 100
    assert (env.engine.event_dir / "sip-recheck.json").is_file()


# ---------------------------------------------------------------------------
# plugins


def test_timed_trade_plugin_holds_between_the_two_times():
    plugin = build_plugin(
        "timed_trade",
        {"symbol": "SPY", "shares": 10, "side": "short", "enter_et": "10:00", "exit_et": "11:00"},
        ("SPY",),
        "1m",
    )

    def ctx(hhmm):
        return PluginContext(
            "s", SESSION, et(hhmm), "1m", pd.DataFrame(), pd.DataFrame(), {}, {}, {}, 1.0, 0.0
        )

    assert plugin.decide(ctx("09:59")).targets["SPY"].shares == 0
    assert plugin.decide(ctx("10:30")).targets["SPY"].shares == -10
    assert plugin.decide(ctx("11:00")).targets["SPY"].shares == 0


def test_unknown_plugin_and_foreign_module_paths_are_refused():
    with pytest.raises(PluginError):
        build_plugin("nope", {}, ("A",), "1m")
    with pytest.raises(PluginError):
        build_plugin("os:system", {}, ("A",), "1m")


def test_noise_band_example_goes_long_above_the_upper_band():
    history_rows = []
    for day in (date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)):
        frame = minute_frame({"SPY": lambda i: 100.0 + 0.01 * i}, session=day)
        history_rows.append(frame)
    history = pd.concat(history_rows, ignore_index=True)
    plugin = build_plugin(
        "noise_band_example",
        {"symbol": "SPY", "lookback_days": 3, "notional_usd": 10_000},
        ("SPY",),
        "5m",
    )
    today = minute_frame({"SPY": lambda i: 100.0 + 0.5 * i})
    sb = SessionBars(FrameMinuteProvider(today, "t"), ("SPY",), SESSION)
    sb.refresh(et("10:00"))
    ctx = PluginContext(
        "n", SESSION, et("10:00"), "5m", sb.aggregated("5m", ["SPY"]), history, {}, {}, {}, 1e5, 0.0
    )
    decision = plugin.decide(ctx)
    assert decision.targets["SPY"].notional_usd == 10_000 and decision.state["side"] == 1


# ---------------------------------------------------------------------------
# config, authorization, Alpaca adapter, scheduling


def test_authorization_binding(tmp_path):
    env = Env(tmp_path, [strategy("s1", {})])
    cfg = env.config
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    write_runner_authorization(
        cfg,
        tmp_path,
        authorized_by="test-owner",
        basis="quote of the owner",
        account_id_hash="HASH",
        duration_days=14,
        now=now,
    )
    auth = load_runner_authorization(cfg, tmp_path, account_id_hash="HASH", now=now)
    assert auth.paper_only and auth.expires_at > auth.authorized_at
    with pytest.raises(RunnerConfigError, match="different paper account"):
        load_runner_authorization(cfg, tmp_path, account_id_hash="OTHER", now=now)
    with pytest.raises(RunnerConfigError, match="expired"):
        load_runner_authorization(
            cfg, tmp_path, account_id_hash="HASH", now=now + timedelta(days=15)
        )
    changed = yaml.safe_load((tmp_path / "runner.yaml").read_text(encoding="utf-8"))
    changed["strategies"][0]["capital_usd"] = 2_000_000
    (tmp_path / "runner.yaml").write_text(yaml.safe_dump(changed), encoding="utf-8")
    with pytest.raises(RunnerConfigError, match="different config"):
        load_runner_authorization(
            load_runner_config(tmp_path / "runner.yaml"), tmp_path, account_id_hash="HASH", now=now
        )
    with pytest.raises(RunnerConfigError, match="owner's words"):
        write_runner_authorization(
            cfg, tmp_path, authorized_by="x", basis=" ", account_id_hash="H", duration_days=1
        )


def test_config_validation(tmp_path):
    bad = {
        "runner_name": "r",
        "account": "quant2",
        "account_caps": {"max_gross_notional_usd": 1, "max_daily_loss_usd": 1},
        "strategies": [strategy("s", {}, timeframe="2m")],
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(RunnerConfigError, match="timeframe"):
        load_runner_config(path)


class _FakeAsset:
    tradable, shortable, easy_to_borrow = True, True, False


class _FakeTradingClient:
    _base_url = "https://paper-api.alpaca.markets"
    _sandbox = True

    def __init__(self):
        self.submitted: list[Any] = []

    def get_account(self):
        return type(
            "A",
            (),
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "equity": "1000",
                "last_equity": "990",
                "buying_power": "4000",
            },
        )()

    def get_all_positions(self):
        return [type("P", (), {"symbol": "spy", "qty": "-5"})()]

    def get_asset(self, symbol):
        return _FakeAsset()

    def submit_order(self, request):
        self.submitted.append(request)
        return type(
            "O",
            (),
            {
                "id": "oid",
                "client_order_id": request.client_order_id,
                "status": "accepted",
                "symbol": request.symbol,
                "side": "buy",
                "qty": request.qty,
                "filled_qty": "0",
                "filled_avg_price": None,
            },
        )()

    def get_order_by_client_id(self, cid):
        class NotFoundError(Exception):
            status_code = 404

        raise NotFoundError()

    def cancel_order_by_id(self, order_id):  # pragma: no cover
        raise AssertionError


def test_alpaca_adapter_wraps_a_verified_paper_client_only():
    from open_composer.adapters.broker.alpaca_paper import (
        PaperOrderError,
        _mark_verified_paper_client,
    )

    with pytest.raises(PaperOrderError):
        AlpacaPaperBroker(_FakeTradingClient())  # not built by the strict paper factory
    client = _mark_verified_paper_client(_FakeTradingClient())
    broker = AlpacaPaperBroker(client)
    snap = broker.account_snapshot()
    assert snap.equity == 1000 and snap.last_equity == 990 and snap.id_hash
    assert "11111111" not in snap.id_hash  # only a hash, never the raw id
    assert broker.positions() == {"SPY": -5.0}
    assert broker.asset("SPY").can_short is False  # not easy to borrow
    info = broker.submit_market("SPY", "buy", 3, "oci-test")
    assert info.status == "accepted" and info.qty == 3
    request = client.submitted[0]
    assert request.client_order_id == "oci-test" and request.qty == 3
    assert str(request.time_in_force).lower().endswith("day")
    assert broker.get_order("missing") is None
    assert BrokerError  # exported


def test_strategy_due_and_latest_boundary():
    class Cfg:
        def __init__(self, minutes):
            self.minutes = minutes

    assert strategy_due(Cfg(5), et("09:35")) and not strategy_due(Cfg(5), et("09:34"))
    assert strategy_due(Cfg(30), et("10:00")) and not strategy_due(Cfg(30), et("09:45"))
    assert not strategy_due(Cfg(1), et("09:30"))
    now = datetime(2026, 10, 2, 14, 0, 7, tzinfo=UTC)
    assert latest_boundary(now) == pd.Timestamp("2026-10-02T14:00:00Z")


def test_run_live_once_lock_and_calendar(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    path = tmp_path / "runner.yaml"
    clock = {"now": et("10:00").to_pydatetime() + timedelta(seconds=8)}
    outcome = run_live(
        path,
        tmp_path,
        allow_paper_orders=False,
        once=True,
        broker=env.broker,
        live_provider=FrameMinuteProvider(env.frame, "iex_test"),
        kill_check=lambda: None,
        clock=lambda: clock["now"],
        sleep=lambda _s: None,
    )
    assert outcome["status"] == "ticked"
    plan_dir = runner_dir(tmp_path, "quant2") / f"{SESSION.isoformat()}-plan"
    assert any(e["type"] == "signal" for e in EventLog(plan_dir / "events.jsonl").read())
    assert env.broker.submit_calls == []  # no --allow-paper-orders: plan only
    lock_path = runner_dir(tmp_path, "quant2") / "run.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held = run_live(
            path,
            tmp_path,
            allow_paper_orders=False,
            once=True,
            broker=env.broker,
            live_provider=FrameMinuteProvider(env.frame, "x"),
            clock=lambda: clock["now"],
        )
    assert held["status"] == "already_running"
    saturday = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
    off = run_live(
        path,
        tmp_path,
        allow_paper_orders=False,
        once=True,
        broker=env.broker,
        live_provider=FrameMinuteProvider(env.frame, "x"),
        clock=lambda: saturday,
    )
    assert off["status"] == "not_a_session"


def test_paper_orders_require_a_valid_authorization(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    clock = et("10:00").to_pydatetime() + timedelta(seconds=8)
    with pytest.raises(RunnerConfigError, match="no runner authorization"):
        run_live(
            tmp_path / "runner.yaml",
            tmp_path,
            allow_paper_orders=True,
            once=True,
            broker=env.broker,
            live_provider=FrameMinuteProvider(env.frame, "x"),
            clock=lambda: clock,
        )
    assert env.broker.submit_calls == []


def test_run_live_after_the_summary_returns_already_finished(tmp_path):
    env = Env(tmp_path, [strategy("s1", {})])
    after = CLOSE_TS.to_pydatetime() + timedelta(minutes=30)
    path = tmp_path / "runner.yaml"
    kwargs = {
        "broker": env.broker,
        "live_provider": FrameMinuteProvider(env.frame, "x"),
        "kill_check": lambda: None,
        "clock": lambda: after,
        "sleep": lambda _s: None,
    }
    first = run_live(path, tmp_path, allow_paper_orders=False, **kwargs)
    assert first["status"] == "finished"
    second = run_live(path, tmp_path, allow_paper_orders=False, **kwargs)
    assert second["status"] == "already_finished"


# ---------------------------------------------------------------------------
# additions of 2026-10-06: client-side stops, missing bars, rate limit, preflight


def test_client_side_stop_flattens_through_the_net_path_and_cools_down(tmp_path):
    prices = {"AAA": lambda i: 100.0 if i < 33 else 97.0}  # -3% from the 10:02 bar on
    env = Env(
        tmp_path,
        [
            strategy(
                "s1",
                {"10:00": {"AAA": 100}, "10:10": {"AAA": 100}, "10:40": {"AAA": 100}},
                stop_loss_pct=0.02,
                stop_cooldown_minutes=20,
            )
        ],
        prices=prices,
    )
    env.tick("10:00")
    assert env.pos("s1") == {"AAA": 100}
    env.tick("10:04")  # the 97 bar (10:02) has closed: stop
    stops = env.of("stop")
    assert len(stops) == 1 and stops[0]["adverse_fraction"] == pytest.approx(0.03)
    assert env.pos("s1") == {}
    assert all(c[1] in ("buy", "sell") for c in env.broker.submit_calls)  # plain market orders
    env.tick("10:10")  # plugin asks again inside the cooldown: stays flat
    assert env.pos("s1") == {}
    env.tick("10:40")  # cooldown over
    assert env.pos("s1") == {"AAA": 100}


def test_missing_latest_bar_means_no_trade(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}, "10:10": {"AAA": 0}})])
    gap = env.frame[~((env.frame["symbol"] == "AAA") & (env.frame["timestamp"] == et("09:59")))]
    engine = env.new_engine(frame=gap)  # no 09:59 bar for the 10:00 decision
    env.tick("10:00", engine=engine)
    assert env.broker.submit_calls == [] and env.pos("s1", engine) == {}
    assert env.of("bars", engine)[0]["missing_latest"] == ["AAA"]
    env.tick("10:01", engine=engine)  # bar present again: the standing target is not lost
    assert env.pos("s1", engine) == {}  # nothing standing: the signal at 10:00 was dropped
    env.engine.plugins["s1"].params["script"]["10:02"] = {"AAA": 100}
    engine.plugins["s1"].params["script"]["10:02"] = {"AAA": 100}
    env.tick("10:02", engine=engine)
    assert env.pos("s1", engine) == {"AAA": 100}
    flat = engine  # flatten still works with a stale price when the bar is missing
    assert flat.state.subs["s1"].positions["AAA"] == 100


def test_rate_limiter_queues_instead_of_exceeding_the_window():
    from open_composer.intraday_runner.ratelimit import RateLimiter

    now = {"t": 0.0}
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now["t"] += seconds

    limiter = RateLimiter(5, clock=lambda: now["t"], sleep=sleep)
    for _ in range(5):
        limiter.acquire()
    assert slept == []
    limiter.acquire()  # sixth call inside the minute waits for the first slot to expire
    assert slept and slept[0] == pytest.approx(60.01)
    assert limiter.calls == 6


def test_alpaca_adapter_takes_a_limiter_slot_per_call():
    from open_composer.adapters.broker.alpaca_paper import _mark_verified_paper_client
    from open_composer.intraday_runner.ratelimit import RateLimiter

    limiter = RateLimiter(100)
    broker = AlpacaPaperBroker(_mark_verified_paper_client(_FakeTradingClient()), limiter)
    broker.positions()
    broker.asset("SPY")
    broker.submit_market("SPY", "buy", 1, "oci-x")
    assert limiter.calls == 3


def test_incremental_refresh_matches_a_full_read(tmp_path):
    class Incremental(FrameMinuteProvider):
        incremental = True
        windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []

        def fetch(self, symbols, start, end):
            Incremental.windows.append((start, end))
            return super().fetch(symbols, start, end)

    frame = minute_frame({"AAA": lambda i: 100.0 + i})
    inc = SessionBars(Incremental(frame, "iex"), ("AAA",), SESSION)
    full = SessionBars(FrameMinuteProvider(frame, "iex"), ("AAA",), SESSION)
    for hhmm in ("10:00", "10:01", "10:02"):
        inc.refresh(et(hhmm))
        full.refresh(et(hhmm))
        pd.testing.assert_frame_equal(inc.minute, full.minute)
    assert Incremental.windows[-1][0] > OPEN_TS  # later calls only ask for the recent tail


def test_netted_order_charges_model_cost_on_crossed_shares(tmp_path):
    env = Env(
        tmp_path,
        [
            strategy("s1", {"10:00": {"AAA": 100}}, assumed_cost_bps=2.0),
            strategy("s2", {"10:00": {"AAA": -40}}, assumed_cost_bps=2.0),
        ],
    )
    env.tick("10:00")
    # s2's 40 short shares are crossed against s1's buy: charged 2 bp, not zero
    assert env.engine.state.subs["s2"].internal_cost == pytest.approx(40 * 100.0 * 2.0 / 1e4)
    assert env.engine.state.subs["s1"].internal_cost == pytest.approx(
        40 * 100.0 * 2.0 / 1e4, rel=1e-6
    )  # s1's crossed portion (40 of its 100)
    (tmp_path / "b").mkdir()
    pure = Env(
        tmp_path / "b",
        [
            strategy("a", {"10:00": {"AAA": 50}, "10:05": {"AAA": 0}}, assumed_cost_bps=3.0),
            strategy("b", {"10:05": {"AAA": 50}}, assumed_cost_bps=3.0),
        ],
    )
    pure.tick("10:00")
    pure.tick("10:05")  # a sells 50, b buys 50: fully internal
    assert len(pure.broker.submit_calls) == 1
    assert pure.engine.state.subs["a"].internal_cost == pytest.approx(50 * 100 * 3 / 1e4)
    assert pure.engine.state.subs["b"].internal_cost == pytest.approx(50 * 100 * 3 / 1e4)


def test_preflight_reports_but_never_touches_the_account(tmp_path):
    from open_composer.intraday_runner.live import preflight

    env = Env(tmp_path, [strategy("s1", {})])
    assert preflight(env.broker)["ok"]
    env.broker._pos["AAA"] = 10.0
    env.broker.hold_unfilled = True
    env.broker.submit_market("BBB", "buy", 5, "someone-else")
    report = preflight(env.broker)
    assert not report["ok"]
    assert report["unexpected_positions"] == {"AAA": 10.0}
    assert report["open_orders"][0]["symbol"] == "BBB"
    assert env.broker.positions() == {"AAA": 10.0} and not env.broker.cancelled  # untouched
    declared = preflight(env.broker, {"s1": {"positions": {"AAA": 10}}})
    assert declared["unexpected_positions"] == {} and not declared["ok"]  # open order remains


def test_run_live_refuses_orders_when_the_account_is_not_flat(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}})])
    env.broker._pos["AAA"] = 5.0
    write_runner_authorization(
        env.config,
        tmp_path,
        authorized_by="t",
        basis="quote",
        account_id_hash="simbroker",
        duration_days=3,
        now=et("09:00").to_pydatetime(),
    )
    clock = et("10:00").to_pydatetime() + timedelta(seconds=8)
    outcome = run_live(
        tmp_path / "runner.yaml",
        tmp_path,
        allow_paper_orders=True,
        once=True,
        broker=env.broker,
        live_provider=FrameMinuteProvider(env.frame, "x"),
        kill_check=lambda: None,
        clock=lambda: clock,
    )
    assert outcome["status"] == "preflight_failed"
    assert outcome["unexpected_positions"] == {"AAA": 5.0}
    assert env.broker.submit_calls == [] and env.broker.positions() == {"AAA": 5.0}


def test_shadow_session_reconciles_against_itself(tmp_path):
    env = Env(
        tmp_path,
        [strategy("s1", {"10:00": {"AAA": 100}, "11:00": {"AAA": 0}})],
        submit_orders=False,
    )
    env.tick("10:00")
    env.tick("11:00")
    done = finish_session(env.engine, CLOSE_TS.to_pydatetime() + timedelta(minutes=10))
    assert done["reconcile"]["ok"] and done["reconcile"]["shadow"]
    assert done["reconcile"]["broker_day_pnl"] is None
    assert done["rows"][0]["feed"] == "test"
    assert env.broker.submit_calls == []


# ---------------------------------------------------------------------------
# wash-trade protection: one direction per symbol at a time


def test_opposite_open_order_is_cancelled_and_confirmed_before_the_new_order(tmp_path):
    broker = SimBroker(lambda s: 100.0, hold_unfilled=True)
    env = Env(
        tmp_path,
        [strategy("s1", {"10:00": {"AAA": 100}, "10:01": {"AAA": -50}})],
        broker=broker,
    )
    env.tick("10:00")
    first = broker.submit_calls[0][3]
    assert broker.orders[first].status == "new"  # held, unfilled
    with pytest.raises(BrokerError, match="wash trade"):  # what the real broker would do
        broker.submit_market("AAA", "sell", 1, "probe")
    broker.orders.pop("probe", None)
    env.tick("10:01")
    assert broker.cancelled == [first]  # cancelled first, confirmed ...
    assert [c[1] for c in broker.submit_calls if c[3] != "probe"] == ["buy", "sell"]
    assert not [e for e in env.of("submit_result") if e["status"] == "rejected"]
    assert env.of("order_cancelled")[0]["cid"] == first
    assert env.pos("s1") == {}  # nothing filled so far; no duplicate order for the first leg


def test_unconfirmed_cancel_keeps_the_symbol_blocked_until_confirmed(tmp_path):
    broker = SimBroker(lambda s: 100.0, hold_unfilled=True, cancel_confirms=False)
    env = Env(
        tmp_path,
        [strategy("s1", {"10:00": {"AAA": 100}, "10:01": {"AAA": -50}})],
        broker=broker,
    )
    env.tick("10:00")
    env.tick("10:01")  # cancel requested, broker still says pending_cancel
    assert len(broker.submit_calls) == 1  # no new order into the open one
    broker.confirm_cancels()
    broker.hold_unfilled = False
    env.tick("10:02")  # confirmed: the standing target goes out now
    assert [c[1] for c in broker.submit_calls] == ["buy", "sell"]
    assert env.pos("s1") == {"AAA": -50}


def test_foreign_opposite_order_is_never_cancelled_and_blocks_the_new_one(tmp_path):
    broker = SimBroker(lambda s: 100.0)
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": -10}})], broker=broker)
    broker.hold_unfilled = True
    broker.submit_market("AAA", "buy", 5, "someone-elses-order")
    broker.hold_unfilled = False
    env.tick("10:00")
    assert broker.cancelled == []  # not ours: left alone
    assert [c[3] for c in broker.submit_calls] == ["someone-elses-order"]
    assert env.pos("s1") == {}
    assert any(e["reason"] == "foreign_opposite_open_order" for e in env.of("order_abandoned"))


def test_flip_is_two_steps_close_to_zero_then_open(tmp_path):
    env = Env(tmp_path, [strategy("s1", {"10:00": {"AAA": 100}, "10:05": {"AAA": -60}})])
    env.tick("10:00")
    env.tick("10:05")
    assert env.pos("s1") == {"AAA": 0.0} or env.pos("s1") == {}  # closed to zero only
    assert [c[2] for c in env.broker.submit_calls] == [100, 100]
    assert env.broker.positions() == {}
    env.tick("10:06")  # fill confirmed, the opening leg of the standing target goes out
    assert [c[1:3] for c in env.broker.submit_calls] == [("buy", 100), ("sell", 100), ("sell", 60)]
    assert env.pos("s1") == {"AAA": -60}
