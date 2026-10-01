"""Point-in-time invariance check for an incrementally refreshed feature table.

T-20261001-21. A feature library under ``data/features/`` is an append-only
point-in-time table: rebuilding it with more raw data must not change any row
dated on or before the old table's last date. This script compares a rebuilt
table (``--new``) with its backup (``--old``) on the rows with
``date_col <= --cut`` and reports

* ``keys_equal``: the two sides have the same key set (``--keys``) in that range;
* ``columns[<name>].changed_share``: for numeric columns the share of joined
  rows with ``|new - old| > tol * max(1, |old|)`` (both missing counts as equal,
  one missing counts as changed); for other columns plain inequality;
* ``max_changed_share`` and the 20 symbols with the most changed rows;
* the appended part (``date_col > cut`` in ``--new``): ``n_new_dates``,
  ``last_date`` and ``coverage_ratio`` = mean rows per new date divided by the
  mean rows per date over the last ``--baseline-n`` dates of the old range
  (use ``--baseline-n 3`` for monthly or bimonthly tables).

``pass`` is true when ``keys_equal`` and ``max_changed_share <= --max-share``
(default 0.001). Nothing is written except ``--out``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

DEFAULT_TOL = 1e-9
DEFAULT_MAX_SHARE = 0.001
TOP_SYMBOLS = 20


def _as_date(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    dtype = frame.schema[column]
    if dtype == pl.Date:
        return frame
    if isinstance(dtype, pl.Datetime):
        return frame.with_columns(pl.col(column).dt.date().alias(column))
    return frame.with_columns(pl.col(column).cast(pl.Utf8).str.slice(0, 10).str.to_date())


def _is_numeric(dtype: pl.DataType) -> bool:
    return dtype.is_numeric()


def _missing(expr: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    if dtype.is_float():
        return expr.is_null() | expr.is_nan()
    return expr.is_null()


def _changed_expr(name: str, dtype: pl.DataType, tol: float) -> pl.Expr:
    new = pl.col(name)
    old = pl.col(f"{name}__old")
    if _is_numeric(dtype) and dtype != pl.Boolean:
        new_f = new.cast(pl.Float64)
        old_f = old.cast(pl.Float64)
        new_missing = _missing(new_f, pl.Float64)
        old_missing = _missing(old_f, pl.Float64)
        moved = (new_f - old_f).abs() > tol * pl.max_horizontal(pl.lit(1.0), old_f.abs())
        return (new_missing != old_missing) | (~new_missing & ~old_missing & moved.fill_null(False))
    return (new != old).fill_null(False) | (new.is_null() != old.is_null())


def _prep(
    path: Path, columns: list[str], *, date_col: str, cut: date, keys: list[str]
) -> pl.DataFrame:
    """Read ``columns`` of ``path``, keep ``date_col <= cut``, one row per key, key-sorted."""
    frame = _as_date(pl.read_parquet(path, columns=columns), date_col)
    frame = frame.filter(pl.col(date_col) <= cut)
    return frame.sort(keys, maintain_order=True).unique(
        subset=keys, keep="first", maintain_order=True
    )


def _batches(columns: list[str], size: int) -> list[list[str]]:
    return [columns[i : i + size] for i in range(0, len(columns), size)]


def compare(
    new_path: Path,
    old_path: Path,
    *,
    date_col: str,
    cut: date,
    keys: list[str],
    tol: float = DEFAULT_TOL,
    max_share: float = DEFAULT_MAX_SHARE,
    baseline_n: int = 20,
    trim_dates: int = 5,
    batch_size: int = 6,
) -> dict:
    """Run the check and return the result dictionary.

    Columns are compared ``batch_size`` at a time so a wide table (about 50
    columns, one million rows) fits in well under 1 GB.
    """
    if date_col not in keys:
        raise ValueError(f"date column {date_col!r} must be one of the keys {keys}")
    new_schema = pl.read_parquet_schema(new_path)
    old_schema = pl.read_parquet_schema(old_path)
    key_set = set(keys)
    missing_keys = [k for k in keys if k not in new_schema or k not in old_schema]
    if missing_keys:
        raise ValueError(f"key columns {missing_keys} missing from one of the tables")

    # Key-only pass: key sets, duplicates, appended part.
    new_keys_all = _as_date(pl.read_parquet(new_path, columns=keys), date_col)
    old_keys_all = _as_date(pl.read_parquet(old_path, columns=keys), date_col)
    new_cut_k = new_keys_all.filter(pl.col(date_col) <= cut)
    old_cut_k = old_keys_all.filter(pl.col(date_col) <= cut)
    new_appended = new_keys_all.filter(pl.col(date_col) > cut)
    dup_new = int(new_cut_k.height - new_cut_k.unique().height)
    dup_old = int(old_cut_k.height - old_cut_k.unique().height)
    new_ku = new_cut_k.unique().sort(keys)
    old_ku = old_cut_k.unique().sort(keys)
    only_new = new_ku.join(old_ku, on=keys, how="anti", nulls_equal=True)
    only_old = old_ku.join(new_ku, on=keys, how="anti", nulls_equal=True)
    keys_equal = only_new.height == 0 and only_old.height == 0
    joined_keys = new_ku.join(old_ku, on=keys, how="inner", nulls_equal=True).sort(keys)
    n_joined = joined_keys.height
    last_date = new_keys_all[date_col].max() if new_keys_all.height else None
    del new_keys_all, old_keys_all

    # Column classification.
    common: list[str] = []
    dtype_mismatch: list[str] = []
    cast_float: set[str] = set()
    for c in new_schema:
        if c in key_set or c not in old_schema:
            continue
        if new_schema[c] == old_schema[c]:
            common.append(c)
        elif _is_numeric(new_schema[c]) and _is_numeric(old_schema[c]):
            common.append(c)
            cast_float.add(c)
        else:
            dtype_mismatch.append(c)
    cols_only_new = [c for c in new_schema if c not in old_schema]
    cols_only_old = [c for c in old_schema if c not in new_schema]

    # Settled-date boundary for the diagnostic (rows older than ``trim_dates`` dates).
    distinct_dates = joined_keys[date_col].unique().sort().to_list()
    settled_to = distinct_dates[-(trim_dates + 1)] if len(distinct_dates) > trim_dates else None
    settled_rows = (
        int(joined_keys.filter(pl.col(date_col) <= settled_to).height) if settled_to else 0
    )

    columns: dict[str, dict] = {}
    max_share_seen = 0.0
    settled_max = 0.0
    any_changed = [False] * n_joined
    if n_joined and common:
        import numpy as np

        any_changed = np.zeros(n_joined, dtype=bool)
        settled_mask = (
            (joined_keys[date_col] <= settled_to).to_numpy()
            if settled_to
            else np.zeros(n_joined, bool)
        )
        for batch in _batches(common, batch_size):
            cols = keys + batch
            new_b = _prep(new_path, cols, date_col=date_col, cut=cut, keys=keys)
            old_b = _prep(old_path, cols, date_col=date_col, cut=cut, keys=keys)
            for c in batch:
                if c in cast_float:
                    new_b = new_b.with_columns(pl.col(c).cast(pl.Float64))
                    old_b = old_b.with_columns(pl.col(c).cast(pl.Float64))
            joined = (
                joined_keys.join(new_b, on=keys, how="left", nulls_equal=True)
                .join(
                    old_b.rename({c: f"{c}__old" for c in batch}),
                    on=keys,
                    how="left",
                    nulls_equal=True,
                )
                .sort(keys)
            )
            del new_b, old_b
            flags = joined.select([_changed_expr(c, joined.schema[c], tol).alias(c) for c in batch])
            for c in batch:
                col = flags[c].to_numpy()
                n_changed = int(col.sum())
                share = n_changed / n_joined
                columns[c] = {"changed_rows": n_changed, "changed_share": share}
                max_share_seen = max(max_share_seen, share)
                any_changed |= col
                if settled_rows:
                    settled_max = max(settled_max, float(col[settled_mask].sum()) / settled_rows)
            del joined, flags

    top_symbols: list[dict] = []
    diagnostic: dict = {}
    if n_joined and common:
        flag_frame = joined_keys.with_columns(pl.Series("__any", any_changed))
        if "symbol" in flag_frame.columns:
            top_symbols = (
                flag_frame.group_by("symbol")
                .agg(pl.col("__any").sum().alias("rows_changed"), pl.len().alias("rows"))
                .filter(pl.col("rows_changed") > 0)
                .sort(["rows_changed", "symbol"], descending=[True, False])
                .head(TOP_SYMBOLS)
                .to_dicts()
            )
        per_date = (
            flag_frame.group_by(date_col)
            .agg(pl.col("__any").sum().alias("rows_changed"), pl.len().alias("rows"))
            .sort(date_col)
        )
        changed_dates = per_date.filter(pl.col("rows_changed") > 0)
        diagnostic["n_changed_dates"] = int(changed_dates.height)
        if changed_dates.height:
            diagnostic["first_changed_date"] = changed_dates[date_col].min().isoformat()
            diagnostic["last_changed_date"] = changed_dates[date_col].max().isoformat()
            diagnostic["last_changed_dates"] = [
                {date_col: str(r[date_col]), "rows_changed": r["rows_changed"], "rows": r["rows"]}
                for r in changed_dates.tail(10).to_dicts()
            ]
        if settled_to:
            diagnostic["settled_to_date"] = settled_to.isoformat()
            diagnostic["settled_rows"] = settled_rows
            diagnostic["settled_max_changed_share"] = settled_max
            diagnostic["settled_trim_dates"] = trim_dates

    n_new_dates = (
        int(new_appended.select(pl.col(date_col).n_unique()).item()) if new_appended.height else 0
    )
    coverage_ratio = None
    baseline_mean = None
    new_mean = None
    if n_new_dates:
        per_date_new = new_appended.group_by(date_col).len()
        new_mean = float(per_date_new["len"].mean())
        base_dates = (
            old_cut_k.select(pl.col(date_col).unique().sort(descending=True).head(baseline_n))
            .to_series()
            .to_list()
        )
        if base_dates:
            per_date_old = (
                old_cut_k.filter(pl.col(date_col).is_in(base_dates)).group_by(date_col).len()
            )
            baseline_mean = float(per_date_old["len"].mean())
            coverage_ratio = new_mean / baseline_mean if baseline_mean else None
    result = {
        "new": str(new_path),
        "old": str(old_path),
        "date_col": date_col,
        "cut": cut.isoformat(),
        "keys": keys,
        "tol": tol,
        "max_share_threshold": max_share,
        "rows_old_le_cut": int(old_cut_k.height),
        "rows_new_le_cut": int(new_cut_k.height),
        "rows_joined": int(n_joined),
        "duplicate_keys_old": dup_old,
        "duplicate_keys_new": dup_new,
        "keys_equal": bool(keys_equal),
        "n_keys_only_new": int(only_new.height),
        "n_keys_only_old": int(only_old.height),
        "keys_only_new_sample": only_new.head(5).cast(pl.Utf8).to_dicts(),
        "keys_only_old_sample": only_old.head(5).cast(pl.Utf8).to_dicts(),
        "columns_only_new": cols_only_new,
        "columns_only_old": cols_only_old,
        "columns_dtype_mismatch": dtype_mismatch,
        "columns": columns,
        "max_changed_share": max_share_seen,
        "top_changed_symbols": top_symbols,
        "diagnostic": diagnostic,
        "n_new_dates": n_new_dates,
        "last_date": last_date.isoformat() if last_date else None,
        "coverage_ratio": coverage_ratio,
        "mean_rows_per_new_date": new_mean,
        "mean_rows_per_baseline_date": baseline_mean,
        "baseline_n": baseline_n,
    }
    result["pass"] = bool(keys_equal and max_share_seen <= max_share)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--date-col", required=True)
    parser.add_argument("--cut", type=date.fromisoformat, required=True)
    parser.add_argument("--keys", required=True, help="comma separated, must include date-col")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tol", type=float, default=DEFAULT_TOL)
    parser.add_argument("--max-share", type=float, default=DEFAULT_MAX_SHARE)
    parser.add_argument("--baseline-n", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = compare(
        args.new,
        args.old,
        date_col=args.date_col,
        cut=args.cut,
        keys=[k for k in args.keys.split(",") if k],
        tol=args.tol,
        max_share=args.max_share,
        baseline_n=args.baseline_n,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    summary = {
        k: result[k]
        for k in (
            "keys_equal",
            "max_changed_share",
            "n_new_dates",
            "last_date",
            "coverage_ratio",
            "pass",
        )
    }
    print(json.dumps(summary), file=sys.stderr)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
