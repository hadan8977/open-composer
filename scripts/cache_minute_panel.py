"""Cache one symbol's regular-session minute bars into a compact parquet.

Reads the month-sharded archives the way `run_h20260918_02_orb_etf.py` proved is
safe on this box: one DuckDB query per (symbol, year) against the fixed shard
glob, which expands to at most 12 month files -- never the whole-archive glob.
Output keeps only what an intraday engine needs: session date, New York minute,
OHLC, volume, and the running session VWAP.
"""

from __future__ import annotations

import argparse
import glob as glob_module
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "data/features/minute_panel"
NY = "America/New_York"

SHARDS = {
    "sip": {
        "root": ROOT / "data/sip/minute",
        "years": range(2023, 2027),
        "shards": {
            "SPY": 927,
            "QQQ": 811,
            "TQQQ": 986,
            "SPXL": 926,
            "IWM": 529,
            "SSO": 933,
            "UPRO": 1018,
        },
    },
    "hist": {
        "root": ROOT / "data/sip-hist/minute",
        "years": range(2016, 2023),
        "shards": {"SPY": 927, "QQQ": 812, "TQQQ": 987, "SPXL": 927},
    },
}


def year_glob(symbol: str, year: int) -> str | None:
    for cfg in SHARDS.values():
        if year in cfg["years"] and symbol in cfg["shards"]:
            root = cfg["root"]
            if not (root / str(year)).is_dir():
                return None
            return str(root / str(year) / "*" / f"shard-{cfg['shards'][symbol]:04d}.parquet")
    return None


def read_year(symbol: str, year: int) -> pd.DataFrame:
    pattern = year_glob(symbol, year)
    if pattern is None or not glob_module.glob(pattern):
        return pd.DataFrame()
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='800MB'")
        con.execute("SET threads=2")
        df = con.execute(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM read_parquet(?) WHERE symbol = ?",
            [pattern, symbol],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        return df
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(NY)
    df = df.assign(
        date=ts.dt.normalize().dt.tz_localize(None), minute=ts.dt.hour * 60 + ts.dt.minute
    )
    df = df[(df["minute"] >= 9 * 60 + 30) & (df["minute"] <= 15 * 60 + 59)]
    return df.drop(columns=["timestamp"]).sort_values(["date", "minute"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["SPY"])
    ap.add_argument("--years", nargs="+", type=int, default=list(range(2016, 2027)))
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sym in args.symbols:
        frames = []
        for y in args.years:
            f = read_year(sym, y)
            if not f.empty:
                frames.append(f)
                print(f"{sym} {y}: {len(f):,} bars, {f.date.nunique()} sessions", flush=True)
        if not frames:
            print(f"{sym}: nothing")
            continue
        d = pd.concat(frames, ignore_index=True)
        tp = (d["high"] + d["low"] + d["close"]) / 3.0
        pv = (tp * d["volume"]).groupby(d["date"]).cumsum()
        vv = d["volume"].groupby(d["date"]).cumsum()
        d["vwap"] = pv / vv.replace(0, pd.NA)
        d["vwap"] = d.groupby("date")["vwap"].ffill().fillna(d["close"])
        out = OUT_DIR / f"{sym}.parquet"
        d.to_parquet(out, index=False)
        print(f"{sym}: {len(d):,} bars, {d.date.nunique()} sessions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
