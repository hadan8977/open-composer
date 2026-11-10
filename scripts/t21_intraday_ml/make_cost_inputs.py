"""Small extract of daily_broad for the T-21 feature job (symbols of the T-21 universe, 6 columns)."""

import duckdb
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/features/t21_cost_inputs"
OUT.mkdir(parents=True, exist_ok=True)
u = pd.read_parquet(ROOT / "data/features/intraday5m/universe.parquet")
syms = sorted(set(u["symbol"]))
con = duckdb.connect()
con.execute("SET memory_limit='400MB'; SET threads=2")
con.execute("CREATE TEMP TABLE syms(symbol VARCHAR)")
con.executemany("INSERT INTO syms VALUES (?)", [(s,) for s in syms])
for y in range(2022, 2027):
    src = ROOT / f"data/features/daily_broad/{y}.parquet"
    if not src.exists():
        continue
    con.execute(
        f"COPY (SELECT symbol, trade_date, close, dollar_adv_21, vol_21, beta_252_spy FROM read_parquet('{src}') "
        f"WHERE symbol IN (SELECT symbol FROM syms)) TO '{OUT}/{y}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    print(y, flush=True)
