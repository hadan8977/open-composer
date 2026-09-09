"""Memory-lean loading of the feature/label panel for the experiment loop.

Why this exists (2026-09-09): loading the daily+intraday feature table for
2016-2026 the pandas way -- read each year, merge with labels, concat --
peaked above 2.6 GB before a single model was fit, and was killed by its
memory cgroup five times in three days on this 3.9 GB box. Two things
drive that peak, and this module removes both:

* **Only rebalance days need feature rows.** The walk-forward loop scores
  on weekly rebalance days and (with ``train_row_dates="rebalance_dates"``)
  trains on them too; every other trading day contributes nothing but its
  ``close``/``open`` to the mark-to-market. So the feature panel is loaded
  for rebalance days only (~1/5 of the rows) and a separate, narrow price
  panel carries prices for every day. ``loop.run_experiment`` accepts that
  split through its ``price_panel`` argument.
* **The join and the casts happen in DuckDB, not pandas.** One SQL join
  over the parquet files yields an Arrow table already cast to FLOAT
  (float32) with ``symbol`` dictionary-encoded, which pandas receives as a
  ``category`` column with one shared category set -- no 6M-row object
  column, no per-year categorical unification problem, no intermediate
  pandas frames. DuckDB's own ``memory_limit`` bounds the join.

Both loaders return frames that are drop-in inputs for
``loop.run_experiment`` (``panel=`` and ``price_panel=``).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[3]
DAILY_FEATURES_ROOT = ROOT / "data" / "features" / "daily"
LABELS_ROOT = ROOT / "data" / "features" / "labels"
DEFAULT_MEMORY_LIMIT = "1GB"
PRICE_COLUMNS: tuple[str, ...] = ("open", "close")


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET enable_progress_bar=false")
    con.execute(f"SET temp_directory='{ROOT / 'data' / '_duckdb_tmp'}'")
    return con


def _year_glob(root: Path, years: Sequence[int] | None) -> list[str]:
    if years is None:
        return [str(root / "*.parquet")]
    return [str(root / f"{year}.parquet") for year in years if (root / f"{year}.parquet").exists()]


def _to_pandas(table: pa.Table) -> pd.DataFrame:
    # Dictionary-encode symbol so pandas gets a single shared Categorical;
    # self_destruct lets Arrow release its buffers as pandas takes them over.
    idx = table.schema.get_field_index("symbol")
    table = table.set_column(idx, "symbol", table.column("symbol").dictionary_encode())
    frame = table.to_pandas(self_destruct=True, split_blocks=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def load_price_panel(
    *,
    years: Sequence[int] | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    daily_root: Path = DAILY_FEATURES_ROOT,
) -> pd.DataFrame:
    """``symbol, trade_date, open, close`` (float32) for every trading day of
    every symbol in the daily feature table -- the mark-to-market source for
    :func:`loop.run_experiment` when the feature panel holds rebalance days
    only. Sorted by symbol, trade_date.
    """
    con = _connect(memory_limit)
    try:
        query = f"""
            SELECT symbol, trade_date, CAST(open AS FLOAT) AS open, CAST(close AS FLOAT) AS close
            FROM read_parquet({_year_glob(daily_root, years)!r}, union_by_name=true)
            ORDER BY symbol, trade_date
        """
        return _to_pandas(con.execute(query).fetch_arrow_table())
    finally:
        con.close()


def load_feature_panel(
    feature_columns: Sequence[str],
    label_columns: Sequence[str],
    *,
    years: Sequence[int] | None = None,
    dates: pd.DatetimeIndex | Sequence[pd.Timestamp] | None = None,
    include_prices: bool = True,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    daily_root: Path = DAILY_FEATURES_ROOT,
    labels_root: Path = LABELS_ROOT,
) -> pd.DataFrame:
    """Feature + label rows, joined on (symbol, trade_date), cast to float32,
    ``symbol`` as a shared ``category``. Pass ``dates`` (typically
    ``loop.weekly_rebalance_dates(calendar)``) to load rebalance-day rows
    only; omit it for every trading day. ``include_prices`` keeps
    ``open``/``close`` on the rows (needed when no separate price panel is
    used). Sorted by symbol, trade_date.
    """
    feature_columns = list(dict.fromkeys(feature_columns))
    label_columns = list(dict.fromkeys(label_columns))
    con = _connect(memory_limit)
    try:
        feature_select = ", ".join(f"CAST(d.{c} AS FLOAT) AS {c}" for c in feature_columns)
        label_select = ", ".join(f"CAST(l.{c} AS FLOAT) AS {c}" for c in label_columns)
        price_select = ", ".join(f"CAST(d.{c} AS FLOAT) AS {c}" for c in PRICE_COLUMNS)
        selects = [
            s for s in (price_select if include_prices else "", feature_select, label_select) if s
        ]
        date_filter = ""
        if dates is not None:
            date_frame = pd.DataFrame({"trade_date": pd.to_datetime(pd.Index(dates)).normalize()})
            con.register("_wanted_dates", date_frame)
            date_filter = (
                "WHERE d.trade_date IN (SELECT CAST(trade_date AS DATE) FROM _wanted_dates)"
            )
        query = f"""
            SELECT d.symbol, d.trade_date, {", ".join(selects)}
            FROM read_parquet({_year_glob(daily_root, years)!r}, union_by_name=true) d
            JOIN read_parquet({_year_glob(labels_root, years)!r}, union_by_name=true) l
              USING (symbol, trade_date)
            {date_filter}
            ORDER BY d.symbol, d.trade_date
        """
        return _to_pandas(con.execute(query).fetch_arrow_table())
    finally:
        con.close()
