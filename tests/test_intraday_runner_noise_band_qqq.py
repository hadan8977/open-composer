"""QQQ noise-band plugin (T-20261006-15): bands, VWAP, check times, reversal, 15:30 cut-off."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.intraday_runner.plugins import PluginContext, build_plugin
from open_composer.intraday_runner.strategies import noise_band_qqq as nb

SESSION = pd.Timestamp("2026-09-17").date()
SLEEVE = 100_000.0


def _minutes():
    return pd.date_range("2026-01-01 09:30", periods=390, freq="min")


def _history(base=500.0, sigma_move=0.0010, day_step=0.0, days=16):
    """16 prior sessions; every minute close sits ``sigma_move`` above the open, flat day to day."""
    rows = []
    sessions = pd.bdate_range(end=pd.Timestamp("2026-09-16"), periods=days)
    for i, day in enumerate(sessions):
        level = base * (1 + day_step * (-1) ** i)
        for k in range(390):
            local = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + k
            )
            close = level * (1 + sigma_move) if k > 0 else level
            rows.append(
                {
                    "symbol": "QQQ",
                    "timestamp": local.tz_convert("UTC"),
                    "open": level if k == 0 else close,
                    "high": close * 1.0001,
                    "low": min(level, close) * 0.9999,
                    "close": close,
                    "volume": 1000.0,
                }
            )
    return pd.DataFrame(rows)


def _today(path, last_minute):
    """Completed 1-minute bars of today up to the bar starting at ``last_minute``."""
    rows = []
    day = pd.Timestamp(SESSION).tz_localize("America/New_York")
    for minute in range(570, last_minute + 1):
        close = float(path(minute))
        open_ = float(path(minute - 1)) if minute > 570 else close
        start = day + pd.Timedelta(minutes=minute)
        rows.append(
            {
                "symbol": "QQQ",
                "bar_close_ts": (start + pd.Timedelta(minutes=1)).tz_convert("UTC"),
                "open": open_,
                "high": max(open_, close) * 1.00005,
                "low": min(open_, close) * 0.99995,
                "close": close,
                "volume": 1000.0,
                "feed": "sip",
            }
        )
    return pd.DataFrame(rows)


def _ctx(hist, bars, hhmm, state=None, capital=SLEEVE):
    minute = hhmm[0] * 60 + hhmm[1]
    ts = (
        pd.Timestamp(SESSION).tz_localize("America/New_York") + pd.Timedelta(minutes=minute)
    ).tz_convert("UTC")
    return PluginContext(
        strategy="noiseband_qqq_obs",
        session=SESSION,
        decision_ts=ts,
        timeframe="1m",
        bars=bars[bars["bar_close_ts"] <= ts].reset_index(drop=True),
        history=hist,
        positions={},
        last_prices={},
        state=state or {},
        capital_usd=capital,
        day_pnl_usd=0.0,
    )


@pytest.fixture(scope="module")
def plugin():
    return build_plugin("noise_band_qqq", {"symbol": "QQQ"}, ("QQQ",), "1m")


@pytest.fixture(scope="module")
def hist():
    return _history()


def _notional(decision):
    return decision.targets["QQQ"].notional_usd


def test_check_minutes():
    assert nb.is_check_minute(10 * 60) and nb.is_check_minute(10 * 60 + 30)
    assert nb.is_check_minute(15 * 60 + 30)
    assert not nb.is_check_minute(9 * 60 + 30)
    assert not nb.is_check_minute(10 * 60 + 15)
    assert not nb.is_check_minute(15 * 60 + 45)


def test_registered_and_history_days(plugin):
    assert plugin.history_days >= 15


def test_nothing_between_checks(plugin, hist):
    bars = _today(lambda m: 500.0, 10 * 60 + 14)
    out = plugin.decide(_ctx(hist, bars, (10, 15)))
    assert out.targets == {} and out.note == "not_check_time"


def test_inside_band_stays_flat(plugin, hist):
    bars = _today(lambda m: 500.0 * (1 + 0.0002), 10 * 60 - 1)
    out = plugin.decide(_ctx(hist, bars, (10, 0)))
    assert _notional(out) == 0.0


def test_breakout_up_goes_long_full_sleeve(plugin, hist):
    # sigma ~ 0.10 percent; price 1 percent above the open at 10:00 is far outside the band
    bars = _today(lambda m: 500.0 * (1 + 0.01 * min(1.0, (m - 570) / 29)), 10 * 60 - 1)
    out = plugin.decide(_ctx(hist, bars, (10, 0)))
    assert _notional(out) == pytest.approx(SLEEVE)  # min(1, 2% / tiny sigma) = 1


def test_breakout_down_goes_short(plugin, hist):
    bars = _today(lambda m: 500.0 * (1 - 0.01 * min(1.0, (m - 570) / 29)), 10 * 60 - 1)
    out = plugin.decide(_ctx(hist, bars, (10, 0)))
    assert _notional(out) == pytest.approx(-SLEEVE)


def test_vwap_stop_exits_long_when_price_falls_to_vwap(plugin, hist):
    def path(m):
        if m < 600:
            return 500.0 * (1 + 0.01 * min(1.0, (m - 570) / 29))
        if m < 630:
            return 505.0 + (m - 600) * 0.05  # keeps rising: long stays on
        return 502.0  # back above the upper band but below the session VWAP

    bars = _today(path, 10 * 60 + 59)  # decision 11:00 ET
    held = plugin.decide(_ctx(hist, bars, (10, 30)))
    assert _notional(held) == pytest.approx(SLEEVE)
    out = plugin.decide(_ctx(hist, bars, (11, 0)))
    assert _notional(out) == 0.0


def test_reversal_long_to_short(plugin, hist):
    def path(m):
        if m < 600:
            return 500.0 * (1 + 0.01 * min(1.0, (m - 570) / 29))
        if m < 630:
            return 505.0
        return 505.0 - (m - 629) * 0.5  # collapses below the lower band by 11:00

    bars = _today(path, 11 * 60 - 1)
    assert _notional(plugin.decide(_ctx(hist, bars, (10, 30)))) == pytest.approx(SLEEVE)
    out = plugin.decide(_ctx(hist, bars, (11, 0)))
    assert _notional(out) == pytest.approx(-SLEEVE)


def test_no_new_position_after_1530(plugin, hist):
    bars = _today(lambda m: 500.0 if m < 15 * 60 else 500.0 * 1.02, 15 * 60 + 44)
    assert plugin.decide(_ctx(hist, bars, (15, 45))).targets == {}
    # the 15:30 check itself still acts
    bars = _today(lambda m: 500.0 if m < 15 * 60 + 15 else 500.0 * 1.02, 15 * 60 + 29)
    assert _notional(plugin.decide(_ctx(hist, bars, (15, 30)))) == pytest.approx(SLEEVE)


def test_weight_is_vol_targeted_and_capped(plugin):
    noisy = _history(day_step=0.04)  # daily returns of about +-8 percent
    bars = _today(lambda m: 500.0 * (1 + 0.05 * min(1.0, (m - 570) / 29)), 10 * 60 - 1)
    ctx = _ctx(noisy, bars, (10, 0))
    out = plugin.decide(ctx)
    closes = noisy.groupby(pd.to_datetime(noisy["timestamp"]).dt.date)["close"].last()
    sd = closes.pct_change().dropna().iloc[-14:].std(ddof=1)
    w = _notional(out) / SLEEVE
    assert 0 < w < 1
    assert w == pytest.approx(0.02 / sd, rel=0.05)


def test_scales_with_sleeve_nav(plugin, hist):
    bars = _today(lambda m: 500.0 * (1 + 0.01 * min(1.0, (m - 570) / 29)), 10 * 60 - 1)
    out = plugin.decide(_ctx(hist, bars, (10, 0), capital=40_000.0))
    assert _notional(out) == pytest.approx(40_000.0)


def test_short_history_gives_no_target(plugin):
    short = _history(days=5)
    bars = _today(lambda m: 500.0 * 1.01, 10 * 60 - 1)
    out = plugin.decide(_ctx(short, bars, (10, 0)))
    assert out.targets == {} and out.note == "no_history"


def test_same_position_as_research_engine(plugin, hist):
    """The plugin calls scripts/t15_engine.py; recompute the check directly and compare."""
    eng = nb.research_engine()
    bars = _today(lambda m: 500.0 * (1 + 0.01 * min(1.0, (m - 570) / 29)), 10 * 60 - 1)
    ctx = _ctx(hist, bars, (10, 0))
    frame = nb._session_frame(ctx.history, ctx.bars, "QQQ")
    panel = eng.Panel("QQQ", frame=frame)
    panel.last_slot[-1] = eng.NSLOT - 1
    sigma = eng.noise_sigma(panel, 14)
    path = eng.a_position_paths(panel, sigma, 30, [1.0], ["both"])[(1.0, "both")]
    j = int(np.flatnonzero(eng.check_slots(30) == 29)[0])
    assert path[-1, j] == 1.0
    assert plugin.decide(ctx).state["side"] == 1.0


def test_raw_daily_close_overrides_history_close(hist, tmp_path):
    """A lower official previous close lowers the upper band: the same bars become a long."""
    day = pd.Timestamp("2026-09-16", tz="America/New_York") + pd.Timedelta(hours=16)
    raw = pd.DataFrame({"timestamp": [day.tz_convert("UTC")], "close": [495.0]})
    path = tmp_path / "QQQ.parquet"
    raw.to_parquet(path)
    # open 500, then 500.8 (0.16 percent up): inside the band anchored on the history close
    # (about 500.5), outside the band anchored on 495 (upper band 500 * 1.001 = 500.5)
    bars = _today(lambda m: 500.0 if m == 570 else 500.8, 10 * 60 - 1)
    base = build_plugin("noise_band_qqq", {"symbol": "QQQ"}, ("QQQ",), "1m")
    anchored = build_plugin(
        "noise_band_qqq", {"symbol": "QQQ", "raw_daily_path": str(path)}, ("QQQ",), "1m"
    )
    assert _notional(base.decide(_ctx(hist, bars, (10, 0)))) == 0.0
    out = anchored.decide(_ctx(hist, bars, (10, 0)))
    assert "raw_daily" in out.note
    assert _notional(out) == pytest.approx(SLEEVE)


def test_engine_prev_close_has_priority(hist, tmp_path):
    """ctx.prev_close_raw beats the raw daily file; without it the plugin falls back as before."""
    day = pd.Timestamp("2026-09-16", tz="America/New_York") + pd.Timedelta(hours=16)
    path = tmp_path / "QQQ.parquet"
    pd.DataFrame({"timestamp": [day.tz_convert("UTC")], "close": [530.0]}).to_parquet(path)
    bars = _today(lambda m: 500.0 if m == 570 else 500.8, 10 * 60 - 1)
    plugin = build_plugin(
        "noise_band_qqq", {"symbol": "QQQ", "raw_daily_path": str(path)}, ("QQQ",), "1m"
    )
    ctx = _ctx(hist, bars, (10, 0))
    assert "raw_daily" in plugin.decide(ctx).note  # 530 as anchor: upper band 530, no long
    assert _notional(plugin.decide(ctx)) == 0.0
    object.__setattr__(ctx, "prev_close_raw", {"QQQ": 495.0})
    out = plugin.decide(ctx)
    assert "ctx.prev_close_raw" in out.note
    assert _notional(out) == pytest.approx(SLEEVE)
