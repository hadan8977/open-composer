"""Step 13-F 3.2: WorldQuant's *101 Formulaic Alphas* (Kakushadze 2016,
arXiv 1601.00991), spot-verified subset.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.2. ``py-alpha-lib`` (the plan's preferred implementation path)
does not run in this project's venv (Python 3.11; the wheel's generated
code needs 3.12 -- see the ``py_alpha_lib_polars_unusable_on_this_box``
source card), so this is the plan's pandas-fallback path.

**Implemented: alphas 001-020 only, not all 101.** These 20 are exactly
Kakushadze's Table 1 formulas that need only
``open, high, low, close, volume, vwap, returns`` -- no ``cap`` or industry
membership (which this repo does not have). Formula fidelity was checked
against a real fetched reference,
``yli188/WorldQuant_alpha101_code/101Alpha_code_1.py`` (no LICENSE file
found in that repo -- its code is not vendored here, only used to confirm
each formula before this independent implementation; see the
``worldquant_alpha101_verbatim_formulas_001_020`` source card). Alphas
021-101 (81 ids) are not implemented this round -- most need ``cap``,
industry classification, or ``adv{d}`` for ``d`` values this table does not
special-case; see ``data/features/alpha101/MANIFEST.json`` for the
per-id ``skipped`` list rather than guessing at them here.

**Operators**: every alpha below is written in the wide-panel operator
vocabulary in ``_panel_ops.py`` (``rank`` = cross-sectional percentile
rank per date; ``ts_*`` = rolling time-series versions). ``correlation``
results are cleaned of ``+-inf`` (a flat window over ``window`` days makes
correlation undefined) before being rank-transformed, matching the
reference's own ``replace([-inf, inf], 0)`` convention.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from open_composer.research.features import _panel_ops as ops

DEFAULT_MEMORY_LIMIT = "1.2GB"
PANEL_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "vwap")

#: 001-020 -- see module docstring. Kept in a tuple (not just "range(1,21)")
#: so a future round that adds ids out of order still has an explicit,
#: reviewable list.
IMPLEMENTED_IDS: tuple[int, ...] = tuple(range(1, 21))

ALPHA101_COLUMNS: tuple[str, ...] = tuple(f"alpha{i:03d}" for i in IMPLEMENTED_IDS)


def _pivot_wide(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    return frame.pivot(index="trade_date", columns="symbol", values=field)


def compute_alpha101(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute the 20 implemented Alpha101 columns for an in-memory OHLCV+
    vwap frame (``symbol, trade_date, open, high, low, close, volume,
    vwap``). Returns long-format ``symbol, trade_date`` plus
    :data:`ALPHA101_COLUMNS`.
    """
    required = {"symbol", "trade_date", *PANEL_FIELDS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"alpha101 input frame missing columns: {sorted(missing)}")

    wide = {field: _pivot_wide(frame, field) for field in PANEL_FIELDS}
    open_, high, low, close, volume, vwap = (wide[f] for f in PANEL_FIELDS)
    returns = close.pct_change()
    adv20 = ops.sma(volume, 20)

    alphas: dict[str, pd.DataFrame] = {}

    # alpha001: rank(Ts_ArgMax(SignedPower(((returns<0)?stddev(returns,20):close),2),5))-0.5
    inner = close.where(returns >= 0, ops.stddev(returns, 20))
    alphas["alpha001"] = ops.rank(ops.ts_argmax(inner**2, 5)) - 0.5

    # alpha002: -1 * correlation(rank(delta(log(volume),2)), rank((close-open)/open), 6)
    alphas["alpha002"] = -1 * ops.replace_inf_with_nan(
        ops.correlation(
            ops.rank(ops.delta(ops.safe_log(volume), 2)),
            ops.rank((close - open_) / open_),
            6,
        )
    )

    # alpha003: -1 * correlation(rank(open), rank(volume), 10)
    alphas["alpha003"] = -1 * ops.replace_inf_with_nan(
        ops.correlation(ops.rank(open_), ops.rank(volume), 10)
    )

    # alpha004: -1 * Ts_Rank(rank(low), 9)
    alphas["alpha004"] = -1 * ops.ts_rank(ops.rank(low), 9)

    # alpha005: rank(open - (sum(vwap,10)/10)) * (-1 * abs(rank(close-vwap)))
    # (the paper's "abs(rank(...))" is a no-op since rank in [0,1] -- kept
    # for fidelity to the published formula, not simplified away.)
    alphas["alpha005"] = ops.rank(open_ - (ops.ts_sum(vwap, 10) / 10.0)) * (
        -1 * ops.rank(close - vwap).abs()
    )

    # alpha006: -1 * correlation(open, volume, 10)
    alphas["alpha006"] = -1 * ops.replace_inf_with_nan(ops.correlation(open_, volume, 10))

    # alpha007: adv20<volume ? -1*Ts_Rank(abs(delta(close,7)),60)*sign(delta(close,7)) : -1
    delta_close_7 = ops.delta(close, 7)
    computed_007 = -1 * ops.ts_rank(delta_close_7.abs(), 60) * ops.sign(delta_close_7)
    alphas["alpha007"] = computed_007.where(adv20 < volume, -1.0)

    # alpha008: -1 * rank((sum(open,5)*sum(returns,5)) - delay(sum(open,5)*sum(returns,5),10))
    product_5 = ops.ts_sum(open_, 5) * ops.ts_sum(returns, 5)
    alphas["alpha008"] = -1 * ops.rank(product_5 - ops.delay(product_5, 10))

    # alpha009: (min(delta_c1,5)>0 or max(delta_c1,5)<0) ? delta_c1 : -delta_c1
    delta_close_1 = ops.delta(close, 1)
    cond9 = (ops.ts_min(delta_close_1, 5) > 0) | (ops.ts_max(delta_close_1, 5) < 0)
    alphas["alpha009"] = delta_close_1.where(cond9, -1 * delta_close_1)

    # alpha010: same shape as alpha009 with window 4
    cond10 = (ops.ts_min(delta_close_1, 4) > 0) | (ops.ts_max(delta_close_1, 4) < 0)
    alphas["alpha010"] = delta_close_1.where(cond10, -1 * delta_close_1)

    # alpha011: (rank(max(vwap-close,3)) + rank(min(vwap-close,3))) * rank(delta(volume,3))
    vwap_minus_close = vwap - close
    alphas["alpha011"] = (
        ops.rank(ops.ts_max(vwap_minus_close, 3)) + ops.rank(ops.ts_min(vwap_minus_close, 3))
    ) * ops.rank(ops.delta(volume, 3))

    # alpha012: sign(delta(volume,1)) * (-1 * delta(close,1))
    alphas["alpha012"] = ops.sign(ops.delta(volume, 1)) * (-1 * delta_close_1)

    # alpha013: -1 * rank(covariance(rank(close), rank(volume), 5))
    alphas["alpha013"] = -1 * ops.rank(ops.covariance(ops.rank(close), ops.rank(volume), 5))

    # alpha014: (-1 * rank(delta(returns,3))) * correlation(open,volume,10)
    alphas["alpha014"] = (-1 * ops.rank(ops.delta(returns, 3))) * ops.replace_inf_with_nan(
        ops.correlation(open_, volume, 10)
    )

    # alpha015: -1 * sum(rank(correlation(rank(high),rank(volume),3)),3)
    corr_high_volume = ops.replace_inf_with_nan(
        ops.correlation(ops.rank(high), ops.rank(volume), 3)
    )
    alphas["alpha015"] = -1 * ops.ts_sum(ops.rank(corr_high_volume), 3)

    # alpha016: -1 * rank(covariance(rank(high), rank(volume), 5))
    alphas["alpha016"] = -1 * ops.rank(ops.covariance(ops.rank(high), ops.rank(volume), 5))

    # alpha017: -1 * rank(Ts_Rank(close,10)) * rank(delta(delta_c1,1))
    #              * rank(Ts_Rank(volume/adv20,5))
    alphas["alpha017"] = (
        -1
        * ops.rank(ops.ts_rank(close, 10))
        * ops.rank(ops.delta(delta_close_1, 1))
        * ops.rank(ops.ts_rank(volume / adv20, 5))
    )

    # alpha018: -1 * rank((stddev(abs(close-open),5) + (close-open)) + correlation(close,open,10))
    alphas["alpha018"] = -1 * ops.rank(
        (ops.stddev((close - open_).abs(), 5) + (close - open_))
        + ops.replace_inf_with_nan(ops.correlation(close, open_, 10))
    )

    # alpha019: (-1*sign((close-delay(close,7))+delta(close,7))) * (1+rank(1+sum(returns,250)))
    alphas["alpha019"] = (-1 * ops.sign((close - ops.delay(close, 7)) + ops.delta(close, 7))) * (
        1 + ops.rank(1 + ops.ts_sum(returns, 250))
    )

    # alpha020: -1 * rank(open-delay(high,1)) * rank(open-delay(close,1)) * rank(open-delay(low,1))
    alphas["alpha020"] = (
        -1
        * ops.rank(open_ - ops.delay(high, 1))
        * ops.rank(open_ - ops.delay(close, 1))
        * ops.rank(open_ - ops.delay(low, 1))
    )

    frames = []
    for name in ALPHA101_COLUMNS:
        melted = (
            alphas[name]
            .reset_index()
            .melt(id_vars="trade_date", var_name="symbol", value_name=name)
        )
        frames.append(melted.set_index(["symbol", "trade_date"]))
    combined = pd.concat(frames, axis=1).reset_index()
    combined[list(ALPHA101_COLUMNS)] = combined[list(ALPHA101_COLUMNS)].replace(
        [float("inf"), float("-inf")], float("nan")
    )
    return (
        combined[["symbol", "trade_date", *ALPHA101_COLUMNS]]
        .sort_values(["symbol", "trade_date"])
        .reset_index(drop=True)
    )


def build_alpha101_features(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Load OHLCV+vwap rows for ``universe_symbols`` from ``daily_glob``
    and compute :func:`compute_alpha101`. Mirrors
    ``alpha158.build_alpha158_features``'s DuckDB-load / pandas-compute
    split and per-symbol-batch calling convention.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    empty_columns = ["symbol", "trade_date", *ALPHA101_COLUMNS]
    if not symbols:
        return pd.DataFrame(columns=empty_columns)

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
        query = f"""
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date,
                   open, high, low, close, volume, vwap
            FROM read_parquet({daily_glob!r})
            WHERE symbol IN (SELECT symbol FROM _universe_symbols)
            ORDER BY symbol, trade_date
        """
        raw = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    if raw.empty:
        return pd.DataFrame(columns=empty_columns)
    raw["trade_date"] = pd.to_datetime(raw["trade_date"])
    return compute_alpha101(raw)


def alpha101_skipped_ids(all_ids: Sequence[int] = tuple(range(1, 102))) -> list[dict[str, str]]:
    """The MANIFEST ``skipped`` list: every id in 1..101 not in
    :data:`IMPLEMENTED_IDS`, with a generic reason. Kept as a function
    (not a hardcoded literal) so the count is always derived from
    ``IMPLEMENTED_IDS`` rather than needing to be kept in sync by hand.
    """
    implemented = set(IMPLEMENTED_IDS)
    return [
        {
            "id": f"alpha{i:03d}",
            "reason": (
                "pandas fallback this round only ports Kakushadze Table 1 "
                "alphas 001-020 (py-alpha-lib unusable on this box); this id "
                "was not independently formula-verified and is not guessed at"
            ),
        }
        for i in all_ids
        if i not in implemented
    ]
