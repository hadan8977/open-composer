#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02: 2023 minute bars of the ETF list (for the R crash diagnostic), memory-light via pyarrow filters."""

import glob
import json
import os

import pyarrow as pa
import pyarrow.parquet as pq

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
shards = sorted({k for s in ETFS for k, v in L.items() if s in v})
tabs = []
for mdir in sorted(glob.glob("data/sip/minute/2023/*")):
    for k in shards:
        p = f"{mdir}/shard-{k}.parquet"
        if os.path.exists(p):
            t = pq.read_table(
                p,
                columns=["symbol", "timestamp", "open", "close", "volume"],
                filters=[("symbol", "in", ETFS)],
            )
            if t.num_rows:
                tabs.append(t)
out = pa.concat_tables(tabs)
pq.write_table(out, "data/research/pm_event_study/etf_minute_2023.parquet")
print(out.num_rows)
