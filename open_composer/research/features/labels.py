"""Step 11 Wave A 3.3.3: forward-return labels for the ranking models.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 3: "未来 h
日收益减去当日宇宙中位数（h ∈ {5, 10, 21}），训练时按日期做排名变换（每天转成
0-1 的分位）。禁运期 = h。"

One row per (symbol, trade_date) in the universe. For each horizon ``h``:

* ``label_excess_{h}``: ``close[t+h]/close[t] - 1`` minus that date's
  cross-sectional median forward return (over exactly the universe rows
  present in this table for that date) -- the raw, sign-and-scale-meaningful
  quantity used for rank-IC diagnostics (Wave B).
* ``label_rank_{h}``: the same date's ``label_excess_{h}`` values converted to
  a 0-1 percentile via DuckDB's ``PERCENT_RANK()`` -- the training TARGET
  for the ridge/LightGBM ranking models (plan: "训练时按日期做排名变换").

**This table is only valid for historical training, never for live
inference**: the last ``h`` trading days of the archive have no future price
to look up, so ``LEAD(close, h)`` -- and therefore both label columns -- are
correctly ``NULL`` there (not fabricated, not back-filled). Any caller that
embargoes ``h`` days before a walk-forward cutoff (as ``loop.py`` does) never
touches these trailing NULLs anyway; this is recorded so a future reader does
not mistake the NULL tail for a bug.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_HORIZONS: tuple[int, ...] = (5, 10, 21)
DEFAULT_MEMORY_LIMIT = "1.5GB"


def build_labels(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    columns = ["symbol", "trade_date"]
    for h in horizons:
        columns += [f"label_excess_{h}", f"label_rank_{h}"]
    if not symbols:
        return pd.DataFrame(columns=columns)

    owns_connection = con is None
    connection = con or duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        if temp_directory is not None:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory='{temp_directory}'")
        connection.register("_universe_symbols", pd.DataFrame({"symbol": symbols}))

        fwd_return_selects = ",\n".join(
            f"    (LEAD(close, {h}) OVER w / close - 1.0) AS fwd_return_{h}" for h in horizons
        )
        excess_selects = ",\n".join(
            f"    (fwd_return_{h} - MEDIAN(fwd_return_{h}) OVER (PARTITION BY trade_date)) "
            f"AS label_excess_{h}"
            for h in horizons
        )
        rank_selects = ",\n".join(
            f"    PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY label_excess_{h}) "
            f"AS label_rank_{h}"
            for h in horizons
        )
        final_selects = ",\n".join(
            f"                label_excess_{h}, "
            f"(CASE WHEN label_excess_{h} IS NULL THEN NULL ELSE label_rank_{h} END) "
            f"AS label_rank_{h}"
            for h in horizons
        )
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, close
                FROM read_parquet({daily_glob!r})
                WHERE symbol IN (SELECT symbol FROM _universe_symbols)
            ),
            priced AS (
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) AS trade_date,
                    close,
{fwd_return_selects}
                FROM raw
                WINDOW w AS (PARTITION BY symbol ORDER BY timestamp)
            ),
            with_excess AS (
                SELECT *,
{excess_selects}
                FROM priced
            ),
            with_rank AS (
                SELECT *,
{rank_selects}
                FROM with_excess
                -- PERCENT_RANK is defined even with a NULL ORDER BY key (DuckDB
                -- sorts NULLs last), which would silently rank a NULL-label row
                -- (the archive's un-embargoable trailing h days) as though it
                -- were the best forward return of the day. Force it back to
                -- NULL wherever the underlying excess label is NULL.
                -- (Guarded below in the final SELECT instead of here, so the
                -- window sees the same partition either way.)
            )
            SELECT
                symbol,
                trade_date,
{final_selects}
            FROM with_rank
            ORDER BY symbol, trade_date
        """
        frame = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame[columns]
