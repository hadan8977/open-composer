# ruff: noqa: E501, E741
"""T-20261006-15-D step 1: cache regular-session 1-minute bars for the top-50 liquid stock basket.

Symbols = every name that sat in rank_in_pool <= 50 of ``data/features/intraday5m/universe.parquet`` in any
month from 2024-01 on (point-in-time monthly pools; the pool itself is applied later when trading).
Months 2023-09 .. data end (the first four months are indicator warm-up). One DuckDB pass per month over
``data/sip/minute/<Y>/<M>/shard-*.parquet`` with a symbol filter, written per symbol:

    data/features/t15_work/d_min/<SYM>/<YYYY-MM>.parquet   date, minute (NY minute of day), open..volume
    data/features/t15_work/d_min/_done/<YYYY-MM>            checkpoint marker (resume skips it)

Prices are as printed by SIP (not split-adjusted); the engine detects split sessions itself.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15d_extract_stock_minutes.py [--months 2024-01 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MIN_DIR = ROOT / "data/sip/minute"
UNIVERSE = ROOT / "data/features/intraday5m/universe.parquet"
OUT = ROOT / "data/features/t15_work/d_min"
NY = "America/New_York"
FIRST_MONTH = "2023-09"
POOL_START = "2024-01"
TOP_N = 50


def stock_symbols() -> list[str]:
    u = pd.read_parquet(UNIVERSE)
    t = u[(u["rank_in_pool"] <= TOP_N) & (u["month"] >= POOL_START)]
    return sorted(t["symbol"].unique())


def month_list(first: str, last: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


DELTAS = (0, 1, -1, 2, -2, 3, -3, 4, -4)


def layout_index() -> dict[str, int]:
    shards = json.loads((MIN_DIR / "_LAYOUT.json").read_text())["shard_symbols"]
    return {sym: int(k) for k, v in shards.items() for sym in v}


def _finish(df: pd.DataFrame, month: str, out: Path) -> int:
    ts = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    df["date"] = ts.dt.normalize().dt.tz_localize(None)
    df["minute"] = (ts.dt.hour * 60 + ts.dt.minute).astype("int16")
    df = df[(df["minute"] >= 570) & (df["minute"] <= 959)].drop(columns=["ts"])
    df = df.drop_duplicates(["symbol", "date", "minute"]).sort_values(["symbol", "date", "minute"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype("float32")
    for sym, g in df.groupby("symbol", sort=False):
        d = out / sym
        d.mkdir(parents=True, exist_ok=True)
        g.drop(columns=["symbol"]).reset_index(drop=True).to_parquet(d / f"{month}.parquet")
    return len(df)


def extract_month_targeted(
    con: duckdb.DuckDBPyConnection,
    month: str,
    symbols: list[str],
    first_month: dict[str, str],
    out: Path = OUT,
) -> int:
    """Read only the shard that holds each symbol (layout index, probing +-4) instead of the whole
    month glob; symbols that should exist but are not found fall back to the full glob."""
    y, m = month.split("-")
    mdir = MIN_DIR / y / m
    if not mdir.is_dir():
        return -1
    lay = layout_index()
    frames, missing = [], []
    for sym in symbols:
        k = lay.get(sym)
        got = None
        if k is not None:
            for dlt in DELTAS:
                f = mdir / f"shard-{k + dlt:04d}.parquet"
                if not f.exists():
                    continue
                try:
                    df = con.execute(
                        "SELECT symbol, timestamp AS ts, open, high, low, close, volume "
                        "FROM read_parquet(?) WHERE symbol=?",
                        [str(f), sym],
                    ).fetchdf()
                except duckdb.Error:
                    continue
                if len(df):
                    got = df
                    break
        if got is not None:
            frames.append(got)
        else:
            missing.append(sym)
    # a symbol is expected from the month before its first pool month (pools use the prior month end)
    expected_missing = [
        s
        for s in missing
        if (pd.Period(first_month.get(s, "2099-12"), "M") - 1) <= pd.Period(month, "M")
    ]
    if expected_missing:
        print(
            f"  {month}: glob fallback for {len(expected_missing)} symbols: {expected_missing[:8]}",
            flush=True,
        )
        con.execute("CREATE OR REPLACE TEMP TABLE syms(symbol VARCHAR)")
        con.executemany("INSERT INTO syms VALUES (?)", [(s,) for s in expected_missing])
        frames.append(
            con.execute(
                f"""SELECT symbol, "timestamp" AS ts, open, high, low, close, volume
                    FROM read_parquet('{mdir}/shard-*.parquet', union_by_name=true)
                    WHERE symbol IN (SELECT symbol FROM syms)"""
            ).fetchdf()
        )
    if not frames:
        return 0
    return _finish(pd.concat(frames, ignore_index=True), month, out)


def first_pool_month() -> dict[str, str]:
    u = pd.read_parquet(UNIVERSE)
    t = u[(u["rank_in_pool"] <= TOP_N) & (u["month"] >= POOL_START)]
    return t.groupby("symbol")["month"].min().to_dict()


def extract_month(
    con: duckdb.DuckDBPyConnection, month: str, symbols: list[str], out: Path = OUT
) -> int:
    y, m = month.split("-")
    mdir = MIN_DIR / y / m
    if not mdir.is_dir():
        return -1
    con.execute("CREATE OR REPLACE TEMP TABLE syms(symbol VARCHAR)")
    con.executemany("INSERT INTO syms VALUES (?)", [(s,) for s in symbols])
    df = con.execute(
        f"""SELECT symbol, "timestamp" AS ts, open, high, low, close, volume
            FROM read_parquet('{mdir}/shard-*.parquet', union_by_name=true)
            WHERE symbol IN (SELECT symbol FROM syms)"""
    ).fetchdf()
    ts = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    df["date"] = ts.dt.normalize().dt.tz_localize(None)
    df["minute"] = (ts.dt.hour * 60 + ts.dt.minute).astype("int16")
    df = df[(df["minute"] >= 570) & (df["minute"] <= 959)].drop(columns=["ts"])
    df = df.drop_duplicates(["symbol", "date", "minute"]).sort_values(["symbol", "date", "minute"])
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype("float32")
    df["volume"] = df["volume"].astype("float32")
    for sym, g in df.groupby("symbol", sort=False):
        d = out / sym
        d.mkdir(parents=True, exist_ok=True)
        g.drop(columns=["symbol"]).reset_index(drop=True).to_parquet(d / f"{month}.parquet")
    return len(df)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--last", default=None, help="last month YYYY-MM (default: latest on disk)")
    ap.add_argument("--symbols", nargs="*", help="override symbol list (self-test)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--memory-limit", default="500MB")
    ap.add_argument(
        "--glob", action="store_true", help="old whole-month glob read (slow on a loaded box)"
    )
    args = ap.parse_args()
    symbols = args.symbols or stock_symbols()
    out: Path = args.out
    (out / "_done").mkdir(parents=True, exist_ok=True)
    if args.months:
        months = args.months
    else:
        last = args.last
        if last is None:
            ys = sorted(int(p.name) for p in MIN_DIR.iterdir() if p.name.isdigit())
            ms = sorted(int(p.name) for p in (MIN_DIR / str(ys[-1])).iterdir() if p.name.isdigit())
            last = f"{ys[-1]}-{ms[-1]:02d}"
        months = month_list(FIRST_MONTH, last)
    fm = first_pool_month()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET threads=2")
    print(f"{len(symbols)} symbols, {len(months)} months", flush=True)
    for month in months:
        marker = out / "_done" / month
        if marker.exists():
            continue
        t0 = time.time()
        n = (
            extract_month(con, month, symbols, out)
            if args.glob
            else extract_month_targeted(con, month, symbols, fm, out)
        )
        if n >= 0:
            marker.write_text(f"{n}\n")
        print(f"{month}: {n} rows, {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
