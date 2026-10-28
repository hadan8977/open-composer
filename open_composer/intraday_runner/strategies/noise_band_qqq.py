"""QQQ noise-band intraday momentum (T-20261006-15, group A; spec paper-sleeve-noiseband-qqq.md).

Zarattini-Aziz-Barbon (2024) rule: band = max/min(open, previous close) x (1 +/- M sigma), sigma the
mean |close/open - 1| of the same minute slot over the previous ``lookback`` sessions; positions are
set only at HH:00 / HH:30 (10:00 ... 15:30), stopped by the current band and the session VWAP,
sized min(cap, 2% / sigma of the last 14 daily returns).  Flat at 15:55 ET is done by the runner.

The signal is computed by the research code itself (``scripts/t15_engine.py``: ``noise_sigma``,
``a_position_paths``, ``vol_target_lev``): the plugin builds a small minute frame (history plus
today's completed bars) and asks the same functions for the position held after this check.  The
state machine is replayed from the open each time, so it needs no persisted state.

Previous close: the research anchors on the official (raw, unadjusted) daily close.  The plugin
uses ``ctx.prev_close_raw`` when the engine provides it, else the raw daily file at
``raw_daily_path`` when it covers the previous session, else the last minute close of the previous
session.  That last one differs from the official close by about 1 bp (closing auction print) and,
on ex-dividend days in the adjusted SIP archive, by about 0.15 percent for QQQ.  The raw daily file
is read only up to the previous session.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.intraday_runner.plugins import (
    IntradayPlugin,
    PluginContext,
    PluginDecision,
    Target,
    register_plugin,
)
from open_composer.market_calendar import NEW_YORK

ROOT = Path(__file__).resolve().parents[3]
CHECK_FIRST = 10 * 60  # 10:00 ET in minutes of the day
CHECK_LAST = 15 * 60 + 30
INTERVAL = 30
_ENGINE = None


def research_engine():
    """Import ``scripts/t15_engine.py`` (the research code) without copying it."""
    global _ENGINE
    if _ENGINE is None:
        path = ROOT / "scripts" / "t15_engine.py"
        scripts = str(path.parent)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        spec = importlib.util.spec_from_file_location("t15_engine", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["t15_engine"] = module
        spec.loader.exec_module(module)
        _ENGINE = module
    return _ENGINE


def is_check_minute(minute_of_day: int) -> bool:
    """Decision time (close of the bar that just completed) at 10:00, 10:30, ... 15:30 ET."""
    return (
        CHECK_FIRST <= minute_of_day <= CHECK_LAST and (minute_of_day - CHECK_FIRST) % INTERVAL == 0
    )


def _session_frame(history: pd.DataFrame, bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Minute frame in the research layout: date, minute (ET minute of day), OHLCV, session VWAP."""
    parts = []
    if not history.empty:
        h = history[history["symbol"] == symbol][
            ["timestamp", "open", "high", "low", "close", "volume"]
        ]
        parts.append(h.assign(timestamp=pd.to_datetime(h["timestamp"], utc=True)))
    if not bars.empty:
        b = bars[bars["symbol"] == symbol]
        start = pd.to_datetime(b["bar_close_ts"], utc=True) - pd.Timedelta(minutes=1)
        parts.append(
            b[["open", "high", "low", "close", "volume"]].assign(timestamp=start.to_numpy())
        )
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    local = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
    d["date"] = local.dt.tz_localize(None).dt.normalize()
    d["minute"] = local.dt.hour * 60 + local.dt.minute
    d = d[(d["minute"] >= 570) & (d["minute"] <= 959)].drop(columns=["timestamp"])
    d = d.drop_duplicates(["date", "minute"]).sort_values(["date", "minute"]).reset_index(drop=True)
    typical = (d["high"] + d["low"] + d["close"]) / 3.0
    pv = (typical * d["volume"]).groupby(d["date"]).cumsum()
    vv = d["volume"].groupby(d["date"]).cumsum()
    d["vwap"] = np.where(vv > 0, pv / vv, d["close"])
    return d


def _raw_prev_close(path: str | None, prev_session: date) -> float | None:
    if not path:
        return None
    file = Path(path) if Path(path).is_absolute() else ROOT / path
    if not file.is_file():
        return None
    # read only up to the day after the prior session (no later data is touched)
    stop = pd.Timestamp(prev_session, tz="UTC") + pd.Timedelta(days=2)
    raw = pd.read_parquet(file, filters=[("timestamp", "<", stop)])
    days = pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(NEW_YORK).dt.date
    hit = raw[days == prev_session]
    return float(hit["close"].iloc[-1]) if len(hit) else None


@register_plugin("noise_band_qqq")
class NoiseBandQQQ(IntradayPlugin):
    """Params: symbol (QQQ), mult (1.0), lookback (14), cap (1.0), raw_daily_path (optional)."""

    history_days = 16

    def decide(self, ctx: PluginContext) -> PluginDecision:
        local = ctx.decision_ts.tz_convert(NEW_YORK)
        minute_now = local.hour * 60 + local.minute
        if not is_check_minute(minute_now):
            return PluginDecision(state=dict(ctx.state), note="not_check_time")
        symbol = str(self.params.get("symbol", "QQQ")).upper()
        mult = float(self.params.get("mult", 1.0))
        lookback = int(self.params.get("lookback", 14))
        cap = float(self.params.get("cap", 1.0))
        frame = _session_frame(ctx.history, ctx.bars, symbol)
        today = pd.Timestamp(ctx.session)
        if frame.empty or not (frame["date"] == today).any():
            return PluginDecision(state=dict(ctx.state), note="no_data")
        prior = frame[frame["date"] < today]
        if prior["date"].nunique() < lookback + 1:
            return PluginDecision(state=dict(ctx.state), note="no_history")
        eng = research_engine()
        panel = eng.Panel(symbol, frame=frame)
        # the research function requires the next bar to exist; this check fills at the next open
        panel.last_slot[-1] = eng.NSLOT - 1
        # the spec anchors on the official previous close (unadjusted SIP daily bar). Order of
        # preference: ctx.prev_close_raw (engine field, Alpaca daily bar adjustment=raw), the raw
        # daily file when it covers the prior session (replay), the last history minute close
        # (about 1 bp different, see runner-parity.md). The source is written to the signal note.
        prev_source = "history_last_close"
        engine_prev = (getattr(ctx, "prev_close_raw", None) or {}).get(symbol)
        if engine_prev is not None and np.isfinite(float(engine_prev)) and float(engine_prev) > 0:
            panel.prev_close[-1] = float(engine_prev)
            prev_source = "ctx.prev_close_raw"
        else:
            raw = _raw_prev_close(self.params.get("raw_daily_path"), prior["date"].max().date())
            if raw is not None:
                panel.prev_close[-1] = raw
                prev_source = "raw_daily"
        sigma = eng.noise_sigma(panel, lookback)
        paths = eng.a_position_paths(panel, sigma, INTERVAL, [mult], ["both"])
        checks = eng.check_slots(INTERVAL)
        slot = minute_now - 570 - 1  # the bar that just completed
        hit = np.flatnonzero(checks == slot)
        if len(hit) != 1 or not np.isfinite(sigma[-1, slot]):
            return PluginDecision(state=dict(ctx.state), note="no_sigma")
        side = float(paths[(mult, "both")][-1, hit[0]])
        lev = float(eng.vol_target_lev(panel)[-1])
        weight = min(cap, lev)
        notional = side * weight * float(self.params.get("sleeve_nav_usd", ctx.capital_usd))
        reason = f"side={side:+.0f} w={weight:.3f} prev={prev_source}"
        return PluginDecision(
            targets={symbol: Target(notional_usd=notional, reason=reason)},
            state={"side": side, "weight": weight, "check_slot": int(slot)},
            note=reason,
        )
