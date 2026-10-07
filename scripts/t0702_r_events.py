#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02: release-type event table from the local Kalshi hourly candles (built by T-20261002-44).
Signals use only candles ending at or before T-5min (T = official release time, ET), never later."""

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
import build_kalshi_release_uncertainty as B
import t0702_pm_grid as G

ET = ZoneInfo("America/New_York")
RAW_CORE = Path("data/research/prediction_markets/kalshi/raw")
RAW_EXT = Path("data/research/pm_event_study/kalshi_raw")
RAW_EXT2 = Path("data/research/pm_event_study/kalshi_raw2")
rows = []
for series, cls in G.R_CLASSES.items():
    RAW = (
        RAW_CORE
        if cls in G.R_CORE
        else (RAW_EXT2 if series in ("KXJOBLESSCLAIMS", "KXISMPMI", "KXJOLTSOPEN") else RAW_EXT)
    )
    metas = []
    for mf in sorted((RAW / series).glob("*.markets.json")):
        try:
            metas.append(json.loads(mf.read_text()))
        except Exception:
            continue
    ev = []
    for meta in metas:
        mk = [m for m in meta["markets"] if m.get("strike_type") in ("greater", "greater_or_equal")]
        closes = sorted({m["close_time"] for m in mk if m.get("close_time")})
        if not mk or not closes:
            continue
        close = datetime.fromisoformat(closes[-1].replace("Z", "+00:00"))
        rel_date = close.astimezone(ET).date()
        hh, mm = map(int, G.R_RELEASE_TIME_ET[cls].split(":"))
        rel = datetime(rel_date.year, rel_date.month, rel_date.day, hh, mm, tzinfo=ET).astimezone(
            UTC
        )
        vals = [
            m.get("expiration_value") for m in mk if m.get("expiration_value") not in (None, "")
        ]
        act = None
        if vals:
            try:
                act = float(re.sub(r"[^0-9.\-]", "", str(vals[0])))
            except ValueError:
                act = None
        ev.append((rel, meta, mk, act, close))
    ev.sort(key=lambda x: x[0])
    prev_act = None
    for rel, meta, mk, act, close in ev:
        cf = RAW / series / f"{meta['event_ticker']}.parquet"
        row = dict(
            close_et=close.astimezone(ET).strftime("%H:%M"),
            cls=cls,
            series=series,
            event=meta["event_ticker"],
            release_utc=rel,
            actual=act,
            baseline=prev_act,
            n_strikes=0,
            E_pre=np.nan,
            E_ref=np.nan,
            U_pre=np.nan,
        )
        if act is not None:
            prev_act = act
        if cf.exists() and rel >= datetime(2022, 12, 1, tzinfo=UTC):
            c = pd.read_parquet(cf)
            if len(c):
                end_pre = int((rel - timedelta(minutes=5)).timestamp())
                end_pre -= end_pre % 3600  # last full hour boundary
                sbm = {
                    m["ticker"]: float(m["floor_strike"])
                    for m in mk
                    if m.get("floor_strike") is not None
                }
                d1 = B.event_distribution(c, sbm, end_pre)
                d0 = B.event_distribution(c, sbm, end_pre - 24 * 3600)
                row.update(
                    n_strikes=int(d1["n_usable_strikes"]),
                    E_pre=d1["pmf_mean"],
                    U_pre=d1["U"],
                    E_ref=d0["pmf_mean"],
                    age_h=d1["median_candle_age_h"],
                    n_strikes_ref=int(d0["n_usable_strikes"]),
                )
        rows.append(row)
df = pd.DataFrame(rows)
df["valid"] = (df.n_strikes >= G.R_MIN_USABLE_STRIKES) & df.E_pre.notna()
df["release_utc"] = pd.to_datetime(df.release_utc, utc=True)
Path("data/research/pm_event_study").mkdir(parents=True, exist_ok=True)
df.to_parquet("data/research/pm_event_study/r_events.parquet")
print(df.groupby(["cls", "close_et"]).size().to_string())
print(
    df.groupby("cls").agg(
        n=("event", "size"),
        valid=("valid", "sum"),
        first=("release_utc", "min"),
        last=("release_utc", "max"),
    )
)
print(
    df[df.release_utc >= "2024-01-08"]
    .groupby("cls")
    .agg(
        n=("event", "size"),
        valid=("valid", "sum"),
        ref=("E_ref", lambda s: s.notna().sum()),
        base=("baseline", lambda s: s.notna().sum()),
        act=("actual", lambda s: s.notna().sum()),
    )
)
