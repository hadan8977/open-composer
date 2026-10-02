#!/usr/bin/env python3
"""Build one row per Kalshi macro event: implied-distribution uncertainty U and U_rel.

T-20261002-44, frozen design in
reports/research/iterations/h20261002_pm_macro_uncertainty/hypotheses.md.
No equity return is read or computed here.

Definitions (hypotheses.md, "Definitions (frozen)"):
  * T = US/Eastern date of the market close_time (08:25 ET for data releases;
    for FOMC the decision day, cross-checked against the Fed calendar).
  * Signal time = end of the last hourly candle ending at or before 15:00 ET on
    the previous NYSE session (T-1). Per strike the last candle ending at or
    before that instant is used (Kalshi emits a candle whenever the book or a
    trade changes, so the last candle is the book at the signal time).
  * Strike price P(X > k): yes mid (bid+ask)/2 when both sides exist and the
    spread is at most 0.10, else the last trade price in that candle
    (price.close), else the strike is missing.
  * Middle-out monotone cleaning, then differencing into a mass function on bin
    midpoints. U = standard deviation of that mass function.
  * U_rel = U / median(U of the previous 12 events of the same series); fewer
    than 6 prior events = warm-up; fewer than 4 usable strikes = excluded.

The middle-out cleaning ``clean_middle_out`` is ported from
``adjust_middle_out`` in WillBtK/macro_kalshi
(https://github.com/WillBtK/macro_kalshi, MIT licence, itself a fork of the
Diercks-Katz-Wright replication package for Fed FEDS 2026-010). Their R code
anchors at the strike whose price is closest to 49 cents and enforces a
non-decreasing price toward lower strikes and a non-increasing price toward
higher strikes. The bin midpoints, the probability-mass differencing and the
standard deviation are this project's own, as hypotheses.md specifies.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
RAW_DIR = ROOT / "data/research/prediction_markets/kalshi/raw"
OUT_PATH = ROOT / "data/research/prediction_markets/kalshi/release_uncertainty.parquet"

SPREAD_MAX = 0.10
MIN_USABLE_STRIKES = 4
MIN_PRIOR_EVENTS = 6
U_REL_WINDOW = 12
SIGNAL_HOUR_ET = 15

PRIMARY_SERIES = {"KXCPI": "CPI", "KXPAYROLLS": "PAYROLLS", "KXGDP": "GDP", "KXPCE": "PCE"}
FOMC_SERIES = {"KXFED": "FOMC"}
DIAGNOSTIC_SERIES = {"KXCPICOREYOY": "CORECPI_YOY", "KXU3": "UNEMPLOYMENT"}

# FOMC statement days (second day of each meeting), federalreserve.gov calendars.
FOMC_DECISION_DAYS = {
    date.fromisoformat(d)
    for d in (
        "2021-09-22 2021-11-03 2021-12-15 "
        "2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14 "
        "2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13 "
        "2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18 "
        "2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10 "
        "2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09"
    ).split()
}


# --------------------------------------------------------------- distribution


def clean_middle_out(prices: Sequence[float], target: float = 0.5) -> np.ndarray:
    """Middle-out monotone cleaning of P(X > k_i) for strikes sorted ascending.

    Port of ``adjust_middle_out`` (WillBtK/macro_kalshi, MIT). The anchor is the
    strike whose price is closest to ``target``; moving to lower strikes the
    price may not fall, moving to higher strikes it may not rise.
    """
    yes = np.asarray(prices, dtype=float)
    n = len(yes)
    if n == 0:
        return yes.copy()
    k = int(np.argmin(np.abs(yes - target)))
    adj = yes.copy()
    if k > 0:
        seq_left = np.concatenate([[yes[k]], yes[:k][::-1]])
        cm_left = np.maximum.accumulate(seq_left)
        adj[:k] = cm_left[1:][::-1]
    if k < n - 1:
        seq_right = np.concatenate([[yes[k]], yes[k + 1 :]])
        cm_right = np.minimum.accumulate(seq_right)
        adj[k + 1 :] = cm_right[1:]
    return adj


def implied_pmf(
    strikes: Sequence[float], cleaned: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    """Mass function on bin midpoints from a monotone P(X > k) curve.

    Interior bin (k_i, k_{i+1}] has mass c_i - c_{i+1} at its midpoint; the
    lower tail (X <= k_1) has mass 1 - c_1 and the upper tail (X > k_n) has mass
    c_n, placed half a typical strike step beyond the outermost strikes.
    """
    k = np.asarray(strikes, dtype=float)
    c = np.asarray(cleaned, dtype=float)
    if len(k) < 2:
        raise ValueError("need at least two strikes")
    step = float(np.median(np.diff(k)))
    mids = np.concatenate([[k[0] - step / 2], (k[:-1] + k[1:]) / 2, [k[-1] + step / 2]])
    mass = np.concatenate([[1.0 - c[0]], c[:-1] - c[1:], [c[-1]]])
    mass = np.clip(mass, 0.0, None)
    total = mass.sum()
    if total <= 0:
        raise ValueError("degenerate pmf")
    return mids, mass / total


def pmf_moments(mids: np.ndarray, mass: np.ndarray) -> tuple[float, float]:
    mean = float(np.dot(mids, mass))
    var = float(np.dot((mids - mean) ** 2, mass))
    return mean, math.sqrt(max(var, 0.0))


# --------------------------------------------------------------- signal prices


def signal_end_ts(prev_session: date) -> int:
    """UTC epoch of 15:00 ET on the previous session."""
    local = datetime(
        prev_session.year, prev_session.month, prev_session.day, SIGNAL_HOUR_ET, tzinfo=ET
    )
    return int(local.astimezone(UTC).timestamp())


def strike_price(row: pd.Series) -> tuple[float | None, str]:
    """Yes price for one strike from its signal candle, and which rule produced it."""
    bid, ask = row["yes_bid_close"], row["yes_ask_close"]
    if pd.notna(bid) and pd.notna(ask) and ask >= bid and (ask - bid) <= SPREAD_MAX + 1e-12:
        return float((bid + ask) / 2.0), "mid"
    last = row["price_close"]
    if pd.notna(last):
        return float(last), "last_trade"
    return None, "missing"


def signal_candles(candles: pd.DataFrame, end_ts: int) -> pd.DataFrame:
    """Per market, the last candle ending at or before ``end_ts`` (never later)."""
    sub = candles[candles["end_period_ts"] <= end_ts]
    if sub.empty:
        return sub
    idx = sub.groupby("market_ticker")["end_period_ts"].idxmax()
    return sub.loc[idx]


def event_distribution(
    candles: pd.DataFrame, strike_by_market: dict[str, float], end_ts: int
) -> dict[str, object]:
    """Usable strikes, cleaned prices and moments for one event at ``end_ts``."""
    last = signal_candles(candles, end_ts)
    strikes, prices, spreads, ages, rules = [], [], [], [], []
    for _, row in last.iterrows():
        price, rule = strike_price(row)
        if price is None:
            rules.append("missing")
            continue
        k = strike_by_market.get(row["market_ticker"])
        if k is None:
            continue
        strikes.append(k)
        prices.append(price)
        rules.append(rule)
        if pd.notna(row["yes_bid_close"]) and pd.notna(row["yes_ask_close"]):
            spreads.append(float(row["yes_ask_close"] - row["yes_bid_close"]))
        ages.append((end_ts - int(row["end_period_ts"])) / 3600.0)
    out: dict[str, object] = {
        "n_usable_strikes": len(strikes),
        "n_mid": rules.count("mid"),
        "n_last_trade": rules.count("last_trade"),
        "n_missing_price": rules.count("missing"),
        "median_spread": float(np.median(spreads)) if spreads else np.nan,
        "median_candle_age_h": float(np.median(ages)) if ages else np.nan,
        "max_candle_age_h": float(np.max(ages)) if ages else np.nan,
        "pmf_mean": np.nan,
        "U": np.nan,
    }
    if len(strikes) >= 2:
        order = np.argsort(strikes)
        k = np.asarray(strikes)[order]
        p = np.asarray(prices)[order]
        # a duplicated strike keeps its first price
        k, first = np.unique(k, return_index=True)
        p = p[first]
        if len(k) >= 2:
            cleaned = clean_middle_out(p)
            mids, mass = implied_pmf(k, cleaned)
            out["pmf_mean"], out["U"] = pmf_moments(mids, mass)
    return out


# ------------------------------------------------------------------- relative U


def add_u_rel(
    df: pd.DataFrame,
    *,
    window: int = U_REL_WINDOW,
    min_prior: int = MIN_PRIOR_EVENTS,
) -> pd.DataFrame:
    """U_rel per series against the median U of the previous ``window`` events.

    ``df`` needs series, release_date, U (NaN when excluded). Only events that
    came strictly earlier in the same series (and have a U) enter the median;
    the order is by release_date then event_ticker.
    """
    out = df.sort_values(["series", "release_date", "event_ticker"]).copy()
    out["n_prior_events"] = 0
    out["median_prior_U"] = np.nan
    out["U_rel"] = np.nan
    for _, idx in out.groupby("series").groups.items():
        history: list[float] = []
        for i in idx:
            u = out.at[i, "U"]
            out.at[i, "n_prior_events"] = len(history)
            if history:
                out.at[i, "median_prior_U"] = float(np.median(history[-window:]))
            if pd.notna(u) and len(history) >= min_prior:
                med = float(np.median(history[-window:]))
                if med > 0:
                    out.at[i, "U_rel"] = float(u) / med
            if pd.notna(u):
                history.append(float(u))
    out["warmup"] = out["n_prior_events"] < min_prior
    return out


def day_level_signal(df: pd.DataFrame, *, value: str = "U_rel") -> pd.DataFrame:
    """One row per release day; a day with several releases takes the larger U_rel."""
    valid = df[df[value].notna()]
    grouped = valid.groupby("release_date")
    day = grouped[value].max().rename(value).to_frame()
    day["n_releases"] = grouped.size()
    day["series_list"] = grouped["series"].agg(lambda s: ",".join(sorted(set(s))))
    return day.reset_index()


# ------------------------------------------------------------------- the build


def load_trading_dates() -> list[date]:
    import duckdb

    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='400MB'")
        df = con.execute(
            "SELECT DISTINCT timestamp FROM read_parquet('data/sip/daily/**/*.parquet') "
            "WHERE symbol = 'SPY' ORDER BY 1"
        ).fetchdf()
    finally:
        con.close()
    stamps = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET).dt.date
    return sorted(set(stamps))


def previous_session(release: date, trading_dates: Sequence[date]) -> date | None:
    earlier = [d for d in trading_dates if d < release]
    if not earlier or trading_dates[-1] < release:
        return None
    return earlier[-1]


def is_early_close(d: date) -> bool:
    """Known 13:00 ET closes: day after Thanksgiving, Dec 24, Jul 3 (when Jul 4 is Tue-Fri)."""
    if d.month == 11 and d.weekday() == 4 and 23 <= d.day <= 29:
        return True
    if d.month == 12 and d.day == 24 and d.weekday() < 5:
        return True
    return d.month == 7 and d.day == 3 and d.weekday() < 4


def release_date_et(close_time_utc: str) -> date:
    stamp = datetime.fromisoformat(close_time_utc.replace("Z", "+00:00"))
    return stamp.astimezone(ET).date()


def build_event_row(
    series: str,
    meta: dict,
    candles: pd.DataFrame,
    trading_dates: Sequence[date],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    markets = [m for m in meta["markets"] if m.get("strike_type") == "greater"]
    closes = sorted({m["close_time"] for m in markets if m.get("close_time")})
    row: dict[str, object] = {
        "series": series,
        "release_type": {**PRIMARY_SERIES, **FOMC_SERIES, **DIAGNOSTIC_SERIES}.get(series, series),
        "event_ticker": meta["event_ticker"],
        "title": meta.get("title"),
        "n_markets": len(markets),
        "is_fomc": series in FOMC_SERIES,
        "diagnostic_only": series in DIAGNOSTIC_SERIES,
    }
    flags: list[str] = []
    if not closes:
        row.update({"release_date": pd.NaT, "excluded": True})
        row["flags"] = "no_close_time"
        return row
    close = closes[-1]
    if len(closes) > 1:
        flags.append("close_times_differ")
    release = release_date_et(close)
    row["close_time_utc"] = close
    row["release_date"] = pd.Timestamp(release)
    row["close_time_et_hhmm"] = (
        datetime.fromisoformat(close.replace("Z", "+00:00")).astimezone(ET).strftime("%H:%M")
    )
    settled = [m for m in markets if m.get("settlement_ts")]
    row["settled"] = len(settled) == len(markets) and bool(markets)
    if series in FOMC_SERIES:
        row["fomc_calendar_match"] = release in FOMC_DECISION_DAYS
        title = f"{meta.get('title') or ''} {meta.get('sub_title') or ''}".lower()
        month = release.strftime("%b").lower()
        row["fomc_title_month_match"] = month in title or release.strftime("%B").lower() in title
        if not row["fomc_calendar_match"]:
            flags.append("fomc_date_not_in_calendar")
    prev = previous_session(release, trading_dates)
    row["T_is_trading_day"] = release in set(trading_dates)
    if release not in set(trading_dates):
        flags.append("T_not_trading_day")
    if prev is None:
        flags.append("no_calendar")
        end_ts = None
    else:
        row["signal_prev_session"] = pd.Timestamp(prev)
        end_ts = signal_end_ts(prev)
        row["signal_end_utc"] = datetime.fromtimestamp(end_ts, UTC).isoformat()
        if is_early_close(prev):
            flags.append("prev_session_early_close")
    if end_ts is None or candles.empty:
        row.update({"n_usable_strikes": 0, "U": np.nan, "pmf_mean": np.nan})
    else:
        strike_by_market = {m["ticker"]: float(m["floor_strike"]) for m in markets}
        row.update(event_distribution(candles, strike_by_market, end_ts))
    row["excluded"] = int(row.get("n_usable_strikes", 0) or 0) < MIN_USABLE_STRIKES
    if row["excluded"]:
        row["U"] = np.nan
        row["pmf_mean"] = np.nan
    row["flags"] = ",".join(flags)
    return row


def build(
    raw_dir: Path,
    trading_dates: Sequence[date],
    *,
    series_list: Sequence[str] | None = None,
    log: Callable[[str], None] = print,
) -> pd.DataFrame:
    known = {**PRIMARY_SERIES, **FOMC_SERIES, **DIAGNOSTIC_SERIES}
    rows = []
    for series in series_list or list(known):
        folder = raw_dir / series
        if not folder.is_dir():
            continue
        for meta_path in sorted(folder.glob("*.markets.json")):
            meta = json.loads(meta_path.read_text())
            parquet = meta_path.with_name(meta_path.name.replace(".markets.json", ".parquet"))
            candles = pd.read_parquet(parquet) if parquet.exists() else pd.DataFrame()
            rows.append(build_event_row(series, meta, candles, trading_dates))
        log(f"{series}: {sum(1 for r in rows if r['series'] == series)} events")
    df = pd.DataFrame(rows)
    df = add_u_rel(df)
    return df.sort_values(["series", "release_date"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    df = build(args.raw_dir, load_trading_dates())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
