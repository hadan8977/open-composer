#!/usr/bin/env python3
"""T-20261007-02: extract minute bars for the fixed ETF list from data/sip/minute (read-only)."""

import glob
import json
import os

import polars as pl

ETFS = [
    "SPY",
    "QQQ",
    "IWM",
    "TLT",
    "XLF",
    "XLE",
    "XLK",
    "XLV",
    "XLY",
    "XLP",
    "XLI",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
]
L = json.load(open("data/sip/minute/_LAYOUT.json"))["shard_symbols"]
where = {s: [k for k, v in L.items() if s in v] for s in ETFS}
frames = []
for y in (2023, 2024, 2025, 2026):
    for mdir in sorted(glob.glob(f"data/sip/minute/{y}/*")):
        shards = sorted({k for s in ETFS for k in where[s]})
        for k in shards:
            p = f"{mdir}/shard-{k}.parquet"
            if os.path.exists(p):
                df = pl.read_parquet(p).filter(pl.col("symbol").is_in(ETFS))
                if df.height:
                    frames.append(
                        df.select(
                            "symbol",
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                            "trade_count",
                        )
                    )
out = pl.concat(frames).unique(["symbol", "timestamp"]).sort("symbol", "timestamp")
out.write_parquet("data/research/pm_event_study/etf_minute.parquet")
print(
    out.group_by("symbol").agg(
        pl.len(), pl.col("timestamp").min().alias("min"), pl.col("timestamp").max().alias("max")
    )
)
