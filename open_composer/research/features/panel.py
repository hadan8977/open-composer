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


def _root_schema_columns(
    con: duckdb.DuckDBPyConnection, root: Path, years: Sequence[int] | None
) -> set[str]:
    """The column names available under ``root`` (a ``{year}.parquet``
    feature table), read from the parquet footer only (``LIMIT 0`` -- no
    row data is scanned). Empty set if the glob matches no files.
    """
    glob = _year_glob(root, years)
    existing = [g for g in glob if "*" in g or Path(g).exists()]
    if not existing:
        return set()
    probe = con.execute(
        f"SELECT * FROM read_parquet({existing!r}, union_by_name=true) LIMIT 0"
    ).fetch_arrow_table()
    return set(probe.schema.names)


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
    extra_feature_roots: Sequence[Path] = (),
    symbol_filter: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Feature + label rows, joined on (symbol, trade_date), cast to float32,
    ``symbol`` as a shared ``category``. Pass ``dates`` (typically
    ``loop.weekly_rebalance_dates(calendar)``) to load rebalance-day rows
    only; omit it for every trading day. ``include_prices`` keeps
    ``open``/``close`` on the rows (needed when no separate price panel is
    used). Sorted by symbol, trade_date.

    ``symbol_filter`` (Step 13-M, 2026-09-10): restrict rows to this set of
    symbols, applied inside the DuckDB query (a registered temp table
    joined via ``IN``, same mechanism as ``dates``) before the Arrow table
    is materialized -- never a post-load pandas filter. A caller that only
    ever trains/scores a sub-universe (e.g. a PIT top-N cohort of ~500-800
    names out of the ~2,700 symbols in the full daily table) should pass
    that sub-universe here: it cuts both the join's row count and the
    final frame's memory footprint roughly in proportion to
    in-filter/total symbols, which is what makes wide feature sets (e.g.
    158 columns) fit in a bounded-memory run. ``None`` (default) keeps
    every symbol -- exactly the prior behavior, unchanged for every
    existing caller.

    ``extra_feature_roots`` (Step 13-F 3.4): additional ``{year}.parquet``
    feature tables (e.g. ``data/features/alpha158``, ``alpha101``,
    ``alpha191``, ``osap_price``) to pull requested columns from. Each root
    is **left**-joined on ``(symbol, trade_date)`` -- a row present in
    ``daily_root`` but missing from an extra root (a symbol/date the extra
    table never computed, or a table that doesn't cover every year) keeps
    its NaN rather than being dropped, since LightGBM handles NaN natively
    and this repo's convention is to never fabricate a value for missing
    history. Only requested columns are pulled from each root (never
    ``SELECT *``): every root's own parquet schema is probed once (a
    zero-row ``LIMIT 0`` query, footer-only) to see which of
    ``feature_columns`` it actually has; a column present in more than one
    root is taken from the first root that has it, in the order given.
    """
    feature_columns = list(dict.fromkeys(feature_columns))
    label_columns = list(dict.fromkeys(label_columns))
    con = _connect(memory_limit)
    try:
        remaining = list(feature_columns)
        extra_joins: list[tuple[str, Path, list[str]]] = []
        for index, root in enumerate(extra_feature_roots):
            root_columns = _root_schema_columns(con, Path(root), years) - {"symbol", "trade_date"}
            matched = [c for c in remaining if c in root_columns]
            if not matched:
                continue
            for column in matched:
                remaining.remove(column)
            extra_joins.append((f"x{index}", Path(root), matched))
        daily_feature_columns = remaining

        feature_select = ", ".join(f"CAST(d.{c} AS FLOAT) AS {c}" for c in daily_feature_columns)
        label_select = ", ".join(f"CAST(l.{c} AS FLOAT) AS {c}" for c in label_columns)
        price_select = ", ".join(f"CAST(d.{c} AS FLOAT) AS {c}" for c in PRICE_COLUMNS)
        extra_selects = [
            ", ".join(f"CAST({alias}.{c} AS FLOAT) AS {c}" for c in matched)
            for alias, _root, matched in extra_joins
        ]
        selects = [
            s
            for s in (
                price_select if include_prices else "",
                feature_select,
                label_select,
                *extra_selects,
            )
            if s
        ]
        where_clauses: list[str] = []
        if dates is not None:
            date_frame = pd.DataFrame({"trade_date": pd.to_datetime(pd.Index(dates)).normalize()})
            con.register("_wanted_dates", date_frame)
            where_clauses.append(
                "d.trade_date IN (SELECT CAST(trade_date AS DATE) FROM _wanted_dates)"
            )
        if symbol_filter is not None:
            # dtype=object even when empty -- an untyped empty list infers
            # float64, which DuckDB then refuses to compare against the
            # VARCHAR symbol column ("Cannot compare values of type VARCHAR
            # and DOUBLE"). An empty symbol_filter is a legitimate input
            # (e.g. a cohort union that happened to be empty) and must
            # still produce a valid, zero-row query, not a binder error.
            symbol_frame = pd.DataFrame(
                {"symbol": list(dict.fromkeys(symbol_filter))}, dtype=object
            )
            con.register("_wanted_symbols", symbol_frame)
            where_clauses.append("d.symbol IN (SELECT symbol FROM _wanted_symbols)")
        row_filter = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        # Step 13-F/M (2026-09-10): each extra root is joined as a filtered,
        # projected subquery -- the same ``dates``/``symbol_filter`` IN-filters
        # as the daily table, applied to the root's own columns -- instead of
        # a bare ``read_parquet`` scan. DuckDB cannot push the driving table's
        # row filter through a LEFT JOIN into the right side, so a bare scan
        # builds a hash table over every symbol/date the root has (~2.6M rows
        # per root for the open libraries); with five roots that overflowed
        # the 1GB DuckDB limit (screened_top40_recent cell,
        # ``OutOfMemoryException`` at 953 MiB). The filtered subquery keeps
        # each build side to the requested cohort/dates only. Results are
        # identical: a LEFT JOIN on (symbol, trade_date) never needs right
        # rows outside the left side's filter.
        extra_row_filter = (
            ("WHERE " + " AND ".join(c.replace("d.", "", 1) for c in where_clauses))
            if where_clauses
            else ""
        )
        extra_join_sql = "\n".join(
            f"LEFT JOIN (SELECT symbol, trade_date, {', '.join(matched)} "
            f"FROM read_parquet({_year_glob(root, years)!r}, union_by_name=true) "
            f"{extra_row_filter}) {alias} USING (symbol, trade_date)"
            for alias, root, matched in extra_joins
        )
        query = f"""
            SELECT d.symbol, d.trade_date, {", ".join(selects)}
            FROM read_parquet({_year_glob(daily_root, years)!r}, union_by_name=true) d
            JOIN read_parquet({_year_glob(labels_root, years)!r}, union_by_name=true) l
              USING (symbol, trade_date)
            {extra_join_sql}
            {row_filter}
            ORDER BY d.symbol, d.trade_date
        """
        return _to_pandas(con.execute(query).fetch_arrow_table())
    finally:
        con.close()
