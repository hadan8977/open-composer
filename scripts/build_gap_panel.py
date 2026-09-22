"""Point-in-time overnight-gap panel for the cross-sectional gap-fade test.

Every field is computable before the opening bell of its own session: the gap
uses that session's official open against the previous adjusted close, and the
volatility and liquidity filters use only sessions strictly before it. The one
thing measured after the open is ``oc``, which is the return the strategy is
trying to capture, not an input to the decision.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DAILY_GLOB = "data/sip/daily/*/*.parquet"
OUT = ROOT / "data/features/gap_panel.parquet"

SQL = """
WITH bars AS (
    SELECT symbol,
           timestamp::DATE AS date,
           open, close, volume,
           close * volume AS dollar_volume
    FROM read_parquet('{glob}')
    WHERE open > 0 AND close > 0 AND volume > 0
),
ret AS (
    SELECT *,
           LAG(close) OVER w AS prev_close,
           LAG(close, 2) OVER w AS prev_close_2,
           close / NULLIF(LAG(close) OVER w, 0) - 1.0 AS cc
    FROM bars
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
lagged AS (
    SELECT *,
           COUNT(*) OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS history,
           MEDIAN(dollar_volume) OVER (PARTITION BY symbol ORDER BY date
                                       ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING) AS dv21,
           STDDEV_SAMP(cc) OVER (PARTITION BY symbol ORDER BY date
                                 ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING) AS sigma21
    FROM ret
)
SELECT symbol,
       date,
       open,
       close,
       prev_close,
       dv21,
       sigma21,
       history,
       open / prev_close - 1.0 AS gap,
       close / open - 1.0 AS oc,
       (open / prev_close - 1.0) / NULLIF(sigma21, 0) AS z
FROM lagged
WHERE prev_close > 0
  AND prev_close_2 > 0
  AND history >= 60
  AND sigma21 > 0
  AND prev_close >= 5.0
  AND dv21 >= 1e6
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit='1200MB'; SET temp_directory='data/_duckdb_tmp';")
    con.execute(f"COPY ({SQL.format(glob=DAILY_GLOB)}) TO '{out}' (FORMAT PARQUET)")
    n, syms, lo, hi = con.sql(
        f"SELECT count(*), count(DISTINCT symbol), min(date), max(date) FROM read_parquet('{out}')"
    ).fetchone()
    print(f"{out}: {n:,} rows, {syms:,} symbols, {lo} -> {hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
