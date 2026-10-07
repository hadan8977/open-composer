"""T-20261006-15: cache regular-session 1-minute bars for the ETF universe of groups A/B.

Reads month-sharded SIP archives (data/sip-hist/minute 2016-2022, data/sip/minute 2023-2026).
The shard that holds a symbol differs between the two archives and can shift by a few shards,
so the shard is probed per (year, month) around the SIP layout index and verified by symbol.

Output: data/features/t15_minute/<SYM>.parquet with date, minute (NY minutes of day),
open/high/low/close/volume and the running session VWAP (typical price weighted, regular hours).
Resumable: a symbol whose parquet exists is skipped.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/features/t15_minute"
NY = "America/New_York"
SYMBOLS = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
    "TQQQ", "SPXL",
]  # fmt: skip
ARCHIVES = {
    "hist": (ROOT / "data/sip-hist/minute", range(2016, 2023)),
    "sip": (ROOT / "data/sip/minute", range(2023, 2027)),
}


def sip_layout() -> dict[str, str]:
    shards = json.loads((ROOT / "data/sip/minute/_LAYOUT.json").read_text())["shard_symbols"]
    return {s: k for k, v in shards.items() for s in v}


def read_month(con, files: list[Path], symbol: str) -> tuple[pd.DataFrame, int] | None:
    for i, f in enumerate(files):
        if not f.exists():
            continue
        try:
            df = con.execute(
                "SELECT timestamp, open, high, low, close, volume "
                "FROM read_parquet(?) WHERE symbol=?",
                [str(f), symbol],
            ).fetchdf()
        except duckdb.Error:
            continue  # empty or odd-schema shard (seen near XLC); try the next candidate
        if len(df):
            return df, i
    return None


def _month_job(args) -> pd.DataFrame | None:
    mdir, idx, symbol = args
    con = duckdb.connect()
    con.execute("SET memory_limit='80MB'")
    con.execute("SET threads=1")
    try:
        deltas = (0, 1, -1, 2, -2, 3, -3, 4, -4)
        got = read_month(con, [mdir / f"shard-{idx + x:04d}.parquet" for x in deltas], symbol)
        return None if got is None else got[0]
    finally:
        con.close()


def extract(symbol: str, idx: int) -> pd.DataFrame:
    jobs = []
    for root, years in ARCHIVES.values():
        for year in years:
            for month in range(1, 13):
                mdir = root / str(year) / f"{month:02d}"
                if mdir.is_dir():
                    jobs.append((mdir, idx, symbol))
    with ThreadPoolExecutor(max_workers=8) as ex:
        frames = [f for f in ex.map(_month_job, jobs) if f is not None]
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(NY)
    d["date"] = ts.dt.normalize().dt.tz_localize(None)
    d["minute"] = ts.dt.hour * 60 + ts.dt.minute
    d = d[(d.minute >= 570) & (d.minute <= 959)].drop(columns=["timestamp"])
    d = d.drop_duplicates(["date", "minute"]).sort_values(["date", "minute"]).reset_index(drop=True)
    tp = (d.high + d.low + d.close) / 3.0
    pv = (tp * d.volume).groupby(d.date).cumsum()
    vv = d.volume.groupby(d.date).cumsum()
    d["vwap"] = np.where(vv > 0, pv / vv, d.close)
    return d


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lay = sip_layout()
    for s in SYMBOLS if len(sys.argv) < 2 else sys.argv[1:]:
        p = OUT / f"{s}.parquet"
        if p.exists():
            continue
        d = extract(s, int(lay[s]))
        if d.empty:
            print(s, "EMPTY", flush=True)
            continue
        d.to_parquet(p)
        print(s, len(d), d.date.min().date(), d.date.max().date(), d.date.nunique(), flush=True)
    return 0


def fix_year_level(symbol: str, year: int = 2023) -> None:
    """Symbols whose SIP layout index is < 317 live in year-level old-layout shards (batch 40)."""
    from concurrent.futures import ThreadPoolExecutor as TPE

    base = ROOT / "data/sip/minute" / str(year)

    def probe(i: int):
        f = base / f"shard-{i:04d}.parquet"
        con = duckdb.connect()
        con.execute("SET memory_limit='80MB'")
        con.execute("SET threads=1")
        try:
            n = con.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE symbol=?", [str(f), symbol]
            ).fetchone()[0]
        except Exception:
            return None
        finally:
            con.close()
        return (i, n) if n else None

    with TPE(max_workers=8) as ex:
        hits = [h for h in ex.map(probe, range(0, 317)) if h]
    print(symbol, year, "year-level hits", hits, flush=True)
    if not hits:
        return
    con = duckdb.connect()
    con.execute("SET memory_limit='200MB'")
    df = con.execute(
        "SELECT timestamp, open, high, low, close, volume FROM read_parquet(?) WHERE symbol=?",
        [str(base / f"shard-{hits[0][0]:04d}.parquet"), symbol],
    ).fetchdf()
    p = OUT / f"{symbol}.parquet"
    old = pd.read_parquet(p)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(NY)
    df["date"] = ts.dt.normalize().dt.tz_localize(None)
    df["minute"] = ts.dt.hour * 60 + ts.dt.minute
    df = df[(df.minute >= 570) & (df.minute <= 959)].drop(columns=["timestamp"])
    allr = pd.concat([old.drop(columns=["vwap"]), df], ignore_index=True)
    allr = (
        allr.drop_duplicates(["date", "minute"])
        .sort_values(["date", "minute"])
        .reset_index(drop=True)
    )
    tp = (allr.high + allr.low + allr.close) / 3.0
    pv = (tp * allr.volume).groupby(allr.date).cumsum()
    vv = allr.volume.groupby(allr.date).cumsum()
    allr["vwap"] = np.where(vv > 0, pv / vv, allr.close)
    allr.to_parquet(p)
    print(symbol, "fixed", len(allr), allr.date.nunique(), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "fix2023":
        for sym in sys.argv[2:]:
            fix_year_level(sym)
        raise SystemExit(0)
    raise SystemExit(main())
