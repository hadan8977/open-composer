#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-01 F axis: minute-derived daily features for 2026-09-01..2026-09-17 only (the existing
``data/features/intraday_daily/2026.parquet`` stops at 2026-09-04).  Same query as
``open_composer.research.features.intraday_daily.build_intraday_daily_features`` with one added
predicate: bars after 2026-09-17 are filtered out before any aggregation (2026-09-18 on is the hold-out).
The existing file is not touched; output ``data/research/t0701_store/intraday_daily_2026_09.parquet``.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t0701_build_intraday_sep.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import open_composer.research.features.intraday_daily as idf  # noqa: E402
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

LAST = "2026-09-17"
OUT = ROOT / "data/research/t0701_store/intraday_daily_2026_09.parquet"
BATCH = 300


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    paths = sorted(str(p) for p in (ROOT / "data/sip/minute/2026/09").glob("shard-*.parquet"))
    symbols = sorted(universe_union_symbols(ROOT / "data/features/universe"))
    src = Path(idf.__file__).read_text()
    # the library query, with a timestamp predicate that stops at LAST
    m = re.search(r'query = f"""(.*?)"""', src, re.S)
    assert m, "query not found"
    q = m.group(1)
    q = q.replace(
        "WHERE symbol IN (SELECT symbol FROM _universe_symbols)",
        f"WHERE symbol IN (SELECT symbol FROM _universe_symbols) AND timestamp < TIMESTAMP '{LAST} 23:59:59' + INTERVAL 1 DAY",
        1,
    )
    q = (
        q.replace("{minute_paths!r}", "{PATHS}")
        .replace("{REGULAR_SESSION_START}", str(idf.REGULAR_SESSION_START))
        .replace("{REGULAR_SESSION_END}", str(idf.REGULAR_SESSION_END))
        .replace("{OPENING_WINDOW_END}", str(idf.OPENING_WINDOW_END))
        .replace("{CLOSING_WINDOW_START}", str(idf.CLOSING_WINDOW_START))
    )
    frames = []
    for i in range(0, len(symbols), BATCH):
        t0 = time.time()
        con = duckdb.connect()
        con.execute("SET memory_limit='0.5GB'")
        con.execute("SET threads=2")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET temp_directory='/tmp/t0701_duckdb'")
        con.register("_universe_symbols", pd.DataFrame({"symbol": symbols[i : i + BATCH]}))
        df = con.execute(q.replace("{PATHS}", repr(paths))).fetchdf()
        con.close()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        frames.append(df[df["trade_date"] <= pd.Timestamp(LAST)])
        print(
            f"batch {i // BATCH + 1}/{(len(symbols) + BATCH - 1) // BATCH}: {len(df)} rows {time.time() - t0:.0f}s",
            flush=True,
        )
    out = pd.concat(frames, ignore_index=True)[list(idf.INTRADAY_DAILY_COLUMNS)].sort_values(
        ["symbol", "trade_date"]
    )
    out.to_parquet(OUT, index=False)
    print("rows", len(out), "dates", out["trade_date"].min(), out["trade_date"].max(), flush=True)


if __name__ == "__main__":
    main()
