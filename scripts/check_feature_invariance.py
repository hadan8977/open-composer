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

T-20261002-02 adds optional modes (the default behaviour is unchanged):

* ``--columns`` / ``--exclude-cols``: restrict the compared columns (comma
  separated names; an item starting with ``re:`` is a regular expression);
* ``--start``: only rows with ``date_col >= --start`` (a window ``start..cut``);
* price-aware tolerance (``--price-col``, ``--price-tol``, ``--price-aware-cols``):
  for those columns a row is "changed" only when
  ``|new - old| > max(tol * max(1, |old|), price_tol / old[price_col])``, which
  absorbs the rounding of a vendor's adjusted prices to the cent; for columns
  that are a price ratio minus one (``--price-ratio-cols``, a subset of the
  price-aware columns) the bound is multiplied by ``(1 + |old|)(2 + |old|) / 2``
  because the base price is ``close / (1 + old)`` and its rounding error counts too;
* ``--exclude-symbols FILE``: rows of those symbols are left out of every share
  and reported as ``excluded_rows`` / ``excluded_changed_rows``;
* ``--attribute-symbols FILE`` (``--attribute-col``): ``unattributed_changed_rows``
  counts changed rows whose key value is not in the file;
* ``--allow-only-new FILE`` / ``--allow-only-old FILE``: keys present on one side
  only must be listed (``SYMBOL`` or ``SYMBOL,YYYY-MM-DD`` per line), otherwise
  they count as ``n_keys_only_new_unallowed`` / ``..._old_unallowed`` and
  ``keys_ok`` is false (without the files ``keys_ok`` equals ``keys_equal``);
* rank parity (``--rank-parity-cols``, ``--rank-min``): per date and column the
  Spearman rank correlation of old and new on the common keys;
  ``rank_parity_share`` is the share of (date, column) cells at or above
  ``--rank-min``; ``--gate rank|both`` makes it part of ``pass``
  (``--rank-share-min``, default 0.99).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import polars as pl

DEFAULT_TOL = 1e-9
DEFAULT_MAX_SHARE = 0.001
TOP_SYMBOLS = 20
DEFAULT_RANK_MIN = 0.99
DEFAULT_RANK_SHARE_MIN = 0.99
WORST_RANK_CELLS = 10


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


def _changed_expr(
    name: str,
    dtype: pl.DataType,
    tol: float,
    *,
    price_tol: float | None = None,
    ratio_scale: bool = False,
) -> pl.Expr:
    """Boolean "row changed" expression; ``price_tol`` needs a ``__price_old`` column."""
    new = pl.col(name)
    old = pl.col(f"{name}__old")
    if _is_numeric(dtype) and dtype != pl.Boolean:
        new_f = new.cast(pl.Float64)
        old_f = old.cast(pl.Float64)
        new_missing = _missing(new_f, pl.Float64)
        old_missing = _missing(old_f, pl.Float64)
        threshold = tol * pl.max_horizontal(pl.lit(1.0), old_f.abs())
        if price_tol is not None:
            price = pl.col("__price_old").cast(pl.Float64)
            rounding = pl.when(price > 0).then(price_tol / price).otherwise(0.0).fill_null(0.0)
            if ratio_scale:
                # x = P_a / P_b - 1 with P_b = P_a / (1 + x): rounding error of both
                # endpoints gives (1 + |x|) * (2 + |x|) / 2 times the same-level bound.
                rounding = rounding * (1.0 + old_f.abs()) * (2.0 + old_f.abs()) / 2.0
            threshold = pl.max_horizontal(threshold, rounding)
        moved = (new_f - old_f).abs() > threshold
        return (new_missing != old_missing) | (~new_missing & ~old_missing & moved.fill_null(False))
    return (new != old).fill_null(False) | (new.is_null() != old.is_null())


def _select_columns(names: list[str], spec: list[str] | None) -> list[str]:
    """Names matched by ``spec`` (exact names or ``re:<regex>`` items), in table order."""
    if not spec:
        return []
    exact = {item for item in spec if not item.startswith("re:")}
    patterns = [re.compile(item[3:]) for item in spec if item.startswith("re:")]
    return [n for n in names if n in exact or any(p.search(n) for p in patterns)]


def _split_spec(text: str | None) -> list[str] | None:
    """Split a comma separated option; a ``re:`` item keeps its commas-free regex."""
    if not text:
        return None
    return [item.strip() for item in text.split(",") if item.strip()]


def read_symbol_file(path: Path) -> tuple[set[str], set[tuple[str, str]]]:
    """Read ``SYMBOL`` / ``SYMBOL,YYYY-MM-DD`` lines into (symbols, symbol-date pairs)."""
    symbols: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            sym, day = (part.strip() for part in line.split(",", 1))
            pairs.add((sym, day[:10]))
        else:
            symbols.add(line)
    return symbols, pairs


def _unallowed(
    keys_frame: pl.DataFrame,
    allowed: tuple[set[str], set[tuple[str, str]]] | None,
    date_col: str,
    symbol_col: str,
) -> list[tuple[str, str]]:
    """(symbol, date) key rows neither in the allowed symbols nor in the allowed pairs."""
    if keys_frame.height == 0:
        return []
    symbols, pairs = allowed if allowed is not None else (set(), set())
    sym = keys_frame[symbol_col].cast(pl.Utf8).to_list()
    days = keys_frame[date_col].cast(pl.Utf8).str.slice(0, 10).to_list()
    return [
        (s_, d_)
        for s_, d_ in zip(sym, days, strict=True)
        if s_ not in symbols and (s_, d_) not in pairs
    ]


def _rank_parity_cells(
    joined: pl.DataFrame, column: str, date_col: str, rank_min: float
) -> list[dict]:
    """Per-date Spearman correlation of ``column`` and ``column__old`` on the common keys."""
    frame = (
        joined.select(
            pl.col(date_col),
            pl.col(column).cast(pl.Float64).alias("n"),
            pl.col(f"{column}__old").cast(pl.Float64).alias("o"),
        )
        .filter(pl.col("n").is_finite() & pl.col("o").is_finite())
        .with_columns(
            pl.col("n").rank("average").over(date_col).alias("rn"),
            pl.col("o").rank("average").over(date_col).alias("ro"),
        )
    )
    per_date = frame.group_by(date_col).agg(
        pl.corr("rn", "ro").alias("rho"),
        pl.len().alias("n_rows"),
        (pl.col("n") == pl.col("o")).all().alias("all_equal"),
    )
    cells = []
    for row in per_date.sort(date_col).to_dicts():
        if row["n_rows"] < 2:
            continue
        rho = row["rho"]
        if rho is None or rho != rho:  # constant column on that date
            rho = 1.0 if row["all_equal"] else 0.0
        cells.append(
            {
                "column": column,
                date_col: str(row[date_col]),
                "rho": float(rho),
                "n_rows": row["n_rows"],
            }
        )
    return cells


def _prep(
    path: Path,
    columns: list[str],
    *,
    date_col: str,
    cut: date,
    keys: list[str],
    start: date | None = None,
) -> pl.DataFrame:
    """Read ``columns``, keep ``start <= date_col <= cut``, one row per key, key-sorted."""
    frame = _as_date(pl.read_parquet(path, columns=columns), date_col)
    frame = frame.filter(pl.col(date_col) <= cut)
    if start is not None:
        frame = frame.filter(pl.col(date_col) >= start)
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
    start: date | None = None,
    columns_spec: list[str] | None = None,
    exclude_cols_spec: list[str] | None = None,
    price_col: str | None = None,
    price_tol: float = 0.04,
    price_aware_spec: list[str] | None = None,
    price_ratio_spec: list[str] | None = None,
    exclude_symbols: set[str] | None = None,
    attribute_symbols: set[str] | None = None,
    attribute_col: str = "symbol",
    allow_only_new: tuple[set[str], set[tuple[str, str]]] | None = None,
    allow_only_old: tuple[set[str], set[tuple[str, str]]] | None = None,
    rank_parity_spec: list[str] | None = None,
    rank_min: float = DEFAULT_RANK_MIN,
    rank_share_min: float = DEFAULT_RANK_SHARE_MIN,
    gate: str = "changed",
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
    old_cut_full = old_cut_k  # unwindowed old range, baseline of the coverage ratio
    if start is not None:
        new_cut_k = new_cut_k.filter(pl.col(date_col) >= start)
        old_cut_k = old_cut_k.filter(pl.col(date_col) >= start)
    new_appended = new_keys_all.filter(pl.col(date_col) > cut)
    dup_new = int(new_cut_k.height - new_cut_k.unique().height)
    dup_old = int(old_cut_k.height - old_cut_k.unique().height)
    new_ku = new_cut_k.unique().sort(keys)
    old_ku = old_cut_k.unique().sort(keys)
    only_new = new_ku.join(old_ku, on=keys, how="anti", nulls_equal=True)
    only_old = old_ku.join(new_ku, on=keys, how="anti", nulls_equal=True)
    keys_equal = only_new.height == 0 and only_old.height == 0
    unallowed_new = _unallowed(only_new, allow_only_new, date_col, attribute_col)
    unallowed_old = _unallowed(only_old, allow_only_old, date_col, attribute_col)
    keys_ok = bool(keys_equal or (not unallowed_new and not unallowed_old))
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

    all_common = list(common)
    compared = [
        c for c in common if columns_spec is None or c in _select_columns(common, columns_spec)
    ]
    if exclude_cols_spec:
        dropped = set(_select_columns(compared, exclude_cols_spec))
        compared = [c for c in compared if c not in dropped]
    price_aware = (
        set(_select_columns(compared, price_aware_spec))
        if price_col and price_aware_spec
        else set()
    )
    price_ratio = set(_select_columns(compared, price_ratio_spec)) & price_aware
    if price_aware and price_col not in old_schema:
        raise ValueError(f"price column {price_col!r} missing from the old table")
    rank_cols = _select_columns(all_common, rank_parity_spec)
    batch_cols = compared + [c for c in rank_cols if c not in compared]
    compared_set = set(compared)

    import numpy as np

    sym_vals = (
        joined_keys[attribute_col].cast(pl.Utf8) if attribute_col in joined_keys.columns else None
    )
    if exclude_symbols and sym_vals is None:
        raise ValueError(f"--exclude-symbols needs key column {attribute_col!r}")
    if attribute_symbols is not None and sym_vals is None:
        raise ValueError(f"--attribute-symbols needs key column {attribute_col!r}")
    excl_mask = (
        sym_vals.is_in(list(exclude_symbols)).to_numpy()
        if exclude_symbols and sym_vals is not None
        else np.zeros(n_joined, bool)
    )
    attr_mask = (
        sym_vals.is_in(list(attribute_symbols)).to_numpy()
        if attribute_symbols is not None and sym_vals is not None
        else np.ones(n_joined, bool)
    )
    eval_mask = ~excl_mask
    n_eval = int(eval_mask.sum())

    settled_eval = 0
    columns: dict[str, dict] = {}
    rank_cells: list[dict] = []
    max_share_seen = 0.0
    settled_max = 0.0
    any_changed = np.zeros(n_joined, dtype=bool)
    if n_joined and batch_cols:
        settled_mask = (
            (joined_keys[date_col] <= settled_to).to_numpy()
            if settled_to
            else np.zeros(n_joined, bool)
        )
        settled_eval = int((settled_mask & eval_mask).sum())
        for batch in _batches(batch_cols, batch_size):
            cols = keys + batch
            new_b = _prep(new_path, cols, date_col=date_col, cut=cut, keys=keys, start=start)
            old_b = _prep(old_path, cols, date_col=date_col, cut=cut, keys=keys, start=start)
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
            if price_aware & set(batch):
                price_b = _prep(
                    old_path, keys + [price_col], date_col=date_col, cut=cut, keys=keys, start=start
                ).rename({price_col: "__price_old"})
                joined = joined.join(price_b, on=keys, how="left", nulls_equal=True).sort(keys)
                del price_b
            todo = [c for c in batch if c in compared_set]
            flags = joined.select(
                [
                    _changed_expr(
                        c,
                        joined.schema[c],
                        tol,
                        price_tol=price_tol if c in price_aware else None,
                        ratio_scale=c in price_ratio,
                    ).alias(c)
                    for c in todo
                ]
            )
            for c in todo:
                col = flags[c].to_numpy()
                n_changed = int((col & eval_mask).sum())
                share = n_changed / n_eval if n_eval else 0.0
                columns[c] = {
                    "changed_rows": n_changed,
                    "changed_share": share,
                    "price_aware": c in price_aware,
                    "price_ratio": c in price_ratio,
                }
                max_share_seen = max(max_share_seen, share)
                any_changed |= col
                if settled_eval:
                    settled_max = max(
                        settled_max, float((col & settled_mask & eval_mask).sum()) / settled_eval
                    )
            for c in rank_cols:
                if c in batch:
                    rank_cells.extend(_rank_parity_cells(joined, c, date_col, rank_min))
            del joined, flags

    excluded_changed_rows = int((any_changed & excl_mask).sum())
    any_changed = any_changed & eval_mask
    unattributed_changed_rows = int((any_changed & ~attr_mask).sum())
    n_cells = len(rank_cells)
    n_cells_ok = sum(1 for cell in rank_cells if cell["rho"] >= rank_min)
    rank_parity_share = n_cells_ok / n_cells if n_cells else None
    rank_by_column = {}
    for cell in rank_cells:
        agg = rank_by_column.setdefault(cell["column"], [0, 0])
        agg[0] += 1
        agg[1] += 1 if cell["rho"] >= rank_min else 0
    rank_by_column_share = {c: v[1] / v[0] for c, v in rank_by_column.items()}
    worst_rank_cells = sorted(rank_cells, key=lambda cell: (cell["rho"], cell["column"]))[
        :WORST_RANK_CELLS
    ]

    top_symbols: list[dict] = []
    diagnostic: dict = {}
    if n_joined and compared:
        flag_frame = joined_keys.with_columns(pl.Series("__any", any_changed))
        if attribute_col in flag_frame.columns:
            top_symbols = (
                flag_frame.group_by(attribute_col)
                .agg(pl.col("__any").sum().alias("rows_changed"), pl.len().alias("rows"))
                .filter(pl.col("rows_changed") > 0)
                .sort(["rows_changed", attribute_col], descending=[True, False])
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
            diagnostic["settled_rows"] = settled_eval
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
            old_cut_full.select(pl.col(date_col).unique().sort(descending=True).head(baseline_n))
            .to_series()
            .to_list()
        )
        if base_dates:
            per_date_old = (
                old_cut_full.filter(pl.col(date_col).is_in(base_dates)).group_by(date_col).len()
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
        "keys_ok": keys_ok,
        "n_keys_only_new_unallowed": len(unallowed_new),
        "n_keys_only_old_unallowed": len(unallowed_old),
        "keys_only_new_unallowed_sample": [list(k) for k in unallowed_new[:10]],
        "keys_only_old_unallowed_sample": [list(k) for k in unallowed_old[:10]],
        "n_keys_only_new": int(only_new.height),
        "n_keys_only_old": int(only_old.height),
        "keys_only_new_sample": only_new.head(5).cast(pl.Utf8).to_dicts(),
        "keys_only_old_sample": only_old.head(5).cast(pl.Utf8).to_dicts(),
        "columns_only_new": cols_only_new,
        "columns_only_old": cols_only_old,
        "columns_dtype_mismatch": dtype_mismatch,
        "columns": columns,
        "n_columns_compared": len(compared),
        "start": start.isoformat() if start else None,
        "price_col": price_col if price_aware else None,
        "price_tol": price_tol if price_aware else None,
        "rows_evaluated": n_eval,
        "excluded_rows": int(excl_mask.sum()),
        "excluded_changed_rows": excluded_changed_rows,
        "attribute_symbols_given": attribute_symbols is not None,
        "unattributed_changed_rows": unattributed_changed_rows,
        "attributed_changed_rows": int(any_changed.sum()) - unattributed_changed_rows,
        "rank_min": rank_min,
        "rank_cells": n_cells,
        "rank_parity_share": rank_parity_share,
        "rank_parity_share_by_column": rank_by_column_share,
        "rank_parity_worst": worst_rank_cells,
        "gate": gate,
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
    changed_ok = max_share_seen <= max_share
    rank_ok = rank_parity_share is not None and rank_parity_share >= rank_share_min
    if gate == "rank":
        passed = keys_ok and rank_ok
    elif gate == "both":
        passed = keys_ok and changed_ok and rank_ok
    else:
        passed = keys_ok and changed_ok
    result["pass"] = bool(passed)
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
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--columns", default=None, help="names or re:<regex>, comma separated")
    parser.add_argument("--exclude-cols", default=None, help="names or re:<regex>")
    parser.add_argument("--price-col", default=None)
    parser.add_argument("--price-tol", type=float, default=0.04)
    parser.add_argument("--price-aware-cols", default=None, help="names or re:<regex>")
    parser.add_argument("--price-ratio-cols", default=None, help="subset of the price-aware cols")
    parser.add_argument("--exclude-symbols", type=Path, default=None)
    parser.add_argument("--attribute-symbols", type=Path, default=None)
    parser.add_argument("--attribute-col", default="symbol")
    parser.add_argument("--allow-only-new", type=Path, default=None)
    parser.add_argument("--allow-only-old", type=Path, default=None)
    parser.add_argument("--rank-parity-cols", default=None, help="names or re:<regex>")
    parser.add_argument("--rank-min", type=float, default=DEFAULT_RANK_MIN)
    parser.add_argument("--rank-share-min", type=float, default=DEFAULT_RANK_SHARE_MIN)
    parser.add_argument("--gate", choices=("changed", "rank", "both"), default="changed")
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
        start=args.start,
        columns_spec=_split_spec(args.columns),
        exclude_cols_spec=_split_spec(args.exclude_cols),
        price_col=args.price_col,
        price_tol=args.price_tol,
        price_aware_spec=_split_spec(args.price_aware_cols),
        price_ratio_spec=_split_spec(args.price_ratio_cols),
        exclude_symbols=(
            read_symbol_file(args.exclude_symbols)[0] if args.exclude_symbols else None
        ),
        attribute_symbols=(
            read_symbol_file(args.attribute_symbols)[0] if args.attribute_symbols else None
        ),
        attribute_col=args.attribute_col,
        allow_only_new=read_symbol_file(args.allow_only_new) if args.allow_only_new else None,
        allow_only_old=read_symbol_file(args.allow_only_old) if args.allow_only_old else None,
        rank_parity_spec=_split_spec(args.rank_parity_cols),
        rank_min=args.rank_min,
        rank_share_min=args.rank_share_min,
        gate=args.gate,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    summary = {
        k: result[k]
        for k in (
            "keys_equal",
            "keys_ok",
            "max_changed_share",
            "unattributed_changed_rows",
            "rank_parity_share",
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
