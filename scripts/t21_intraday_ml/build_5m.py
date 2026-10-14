"""T-20261006-21 step 2: aggregate SIP 1-minute bars into 5-minute bars, one month at a time.

    flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- \
        uv run python scripts/t21_intraday_ml/build_5m.py [--months 2023-01 2023-02 ...]

Output (format frozen, see data/features/intraday5m/README.md):
    data/features/universe_t21.parquet                universe table (month, symbol, adv_rank, dollar_adv, close)
    data/features/intraday5m/<YYYY>/<MM>.parquet      5-minute bars, full 78-bar grid per symbol-day
    data/features/intraday5m/<YYYY>/<MM>.READY        empty marker written after the parquet is complete
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
MIN_DIR = ROOT / "data/sip/minute"
OUT = ROOT / "data/features/intraday5m"
UNIVERSE_SRC = ROOT / "data/features/universe_broad"
UNIVERSE_OUT = ROOT / "data/features/intraday5m/universe.parquet"
TOP_MAX = 600
ETFS = ["SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
FIRST_MONTH, LAST_MONTH = "2023-01", "2026-10"
BARS = 78
COLS = ["open", "high", "low", "close", "vwap"]


def months(first: str, last: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def build_universe() -> pd.DataFrame:
    """Top-600 rows per trading month: the snapshot of the previous month end, close >= 5."""
    frames = []
    for y in range(2022, 2027):
        f = UNIVERSE_SRC / f"{y}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
    u = pd.concat(frames, ignore_index=True)
    u["month_end"] = pd.to_datetime(u["month_end"])
    u = u[u["close"] >= 5.0].sort_values(["month_end", "adv_rank"])
    u["pos"] = u.groupby("month_end").cumcount() + 1
    u = u[u["pos"] <= TOP_MAX].copy()
    u["month"] = (u["month_end"] + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m")
    u = u[(u["month"] >= FIRST_MONTH) & (u["month"] <= LAST_MONTH)]
    u = u.rename(columns={"pos": "rank_in_pool"})[
        ["month", "month_end", "symbol", "adv_rank", "rank_in_pool", "dollar_adv", "close"]
    ]
    return u.reset_index(drop=True)


def build_month(
    con: duckdb.DuckDBPyConnection, month: str, symbols: list[str], raw_path: Path
) -> None:
    y, m = month.split("-")
    files = str(MIN_DIR / y / m / "shard-*.parquet")
    con.execute("CREATE OR REPLACE TEMP TABLE syms(symbol VARCHAR)")
    con.executemany("INSERT INTO syms VALUES (?)", [(s,) for s in symbols])
    q = f"""
    WITH t AS (
      SELECT symbol, timezone('America/New_York', "timestamp") AS ts, "timestamp" AS tsu,
             open, high, low, close, volume, trade_count, vwap
      FROM read_parquet('{files}', union_by_name=true)
      WHERE symbol IN (SELECT symbol FROM syms)
    ), u AS (
      SELECT *, CAST(ts AS DATE) AS d,
             extract(hour FROM ts) * 60 + extract(minute FROM ts) AS mod
      FROM t
    )
    SELECT symbol, d, CAST(floor((mod - 570) / 5) AS INTEGER) AS bar,
           arg_min(open, tsu) AS open, max(high) AS high, min(low) AS low,
           arg_max(close, tsu) AS close, sum(volume) AS volume,
           sum(trade_count) AS trade_count,
           sum(vwap * volume) / nullif(sum(volume), 0) AS vwap, count(*) AS n_min
    FROM u WHERE mod >= 570 AND mod < 960
    GROUP BY symbol, d, bar
    """
    con.execute(f"COPY ({q}) TO '{raw_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def fill_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Full 78-bar grid per symbol-day; empty bars carry the previous close (volume 0, filled=1)."""
    df = df.sort_values(["symbol", "d", "bar"]).reset_index(drop=True)
    sd = df[["symbol", "d"]].drop_duplicates().reset_index(drop=True)
    n = len(sd)
    grid = pd.DataFrame(
        {
            "symbol": np.repeat(sd["symbol"].to_numpy(), BARS),
            "d": np.repeat(sd["d"].to_numpy(), BARS),
            "bar": np.tile(np.arange(BARS, dtype=np.int16), n),
        }
    )
    df["bar"] = df["bar"].astype(np.int16)
    g = grid.merge(df, on=["symbol", "d", "bar"], how="left")
    g["n_min"] = g["n_min"].fillna(0).astype(np.int16)
    g["filled"] = (g["n_min"] == 0).astype(np.int8)
    key = [g["symbol"], g["d"]]
    g["close"] = g.groupby(key)["close"].ffill()
    for c in ("open", "high", "low", "vwap"):
        g[c] = g[c].where(g["filled"] == 0, g["close"])
    g["volume"] = g["volume"].fillna(0.0)
    g["trade_count"] = g["trade_count"].fillna(0.0)
    for c in COLS + ["volume", "trade_count"]:
        g[c] = g[c].astype(np.float32)
    g["d"] = pd.to_datetime(g["d"])
    return g[
        [
            "symbol",
            "d",
            "bar",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_count",
            "vwap",
            "n_min",
            "filled",
        ]
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--debug-symbols",
        type=int,
        default=0,
        help="debug: only this many symbols, output to /tmp/t21_debug",
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    u = build_universe()
    if not args.debug_symbols:
        u.to_parquet(UNIVERSE_OUT, index=False)
    union = sorted(set(u["symbol"]) | set(ETFS))
    out_dir = OUT
    if args.debug_symbols:
        union = sorted(
            set(sorted(set(u["symbol"]))[: args.debug_symbols]) | {"SPY", "AAPL", "MSFT"}
        )
        out_dir = Path("/tmp/t21_debug")
    print(f"universe rows {len(u)}, union symbols {len(union)}", flush=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='300MB'; SET threads=2; SET preserve_insertion_order=false")
    for month in args.months or months(FIRST_MONTH, LAST_MONTH):
        y, m = month.split("-")
        ready = out_dir / y / f"{m}.READY"
        if ready.exists() and not args.force:
            print(month, "ready, skip", flush=True)
            continue
        if not (MIN_DIR / y / m).is_dir():
            print(month, "no minute data", flush=True)
            continue
        t0 = time.time()
        raw_path = Path(f"/tmp/t21_raw_{month}.parquet")
        build_month(con, month, union, raw_path)
        (out_dir / y).mkdir(parents=True, exist_ok=True)
        tmp = out_dir / y / f"{m}.parquet.tmp"
        syms_present = [
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT symbol FROM read_parquet('{raw_path}') ORDER BY 1"
            ).fetchall()
        ]
        writer = None
        nrows = ndays = 0
        days = set()
        for i in range(0, len(syms_present), 100):
            chunk = syms_present[i : i + 100]
            raw = pd.read_parquet(raw_path, filters=[("symbol", "in", chunk)])
            g = fill_grid(raw)
            del raw
            tbl = pa.Table.from_pandas(g, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(tmp, tbl.schema, compression="zstd")
            writer.write_table(tbl)
            nrows += len(g)
            days.update(g["d"].unique())
            del g, tbl
        writer.close()
        raw_path.unlink()
        tmp.replace(out_dir / y / f"{m}.parquet")
        ready.touch()
        print(
            f"{month}: {nrows} rows, {len(syms_present)} symbols, {len(days)} days, {time.time() - t0:.0f}s",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
