"""Anchored (expanding-origin) walk-forward folds for out-of-sample evaluation.

Each fold's training window starts at the earliest available observation and
ends strictly before that fold's test window begins, with an embargo gap in
between. Test windows default to successive calendar years, so a strategy's
statistical evidence is a stitched stream of genuinely out-of-sample returns
that grows every time new data arrives, rather than a single frozen holdout
that can only ever be spent once.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from open_composer.research.kernel.windows import (
    PurgedEmbargoConfig,
    ResearchWindowSplit,
    WalkForwardSlice,
)

DEFAULT_FOLD_COUNT = 5
DEFAULT_EMBARGO_BARS = 5
DEFAULT_EMBARGO_REASON = "rolling_origin_embargo"


def returns_from_ohlcv(frame: pd.DataFrame, *, price_column: str = "close") -> pd.Series:
    """Compute a chronologically sorted daily simple-return series from OHLCV rows."""
    if "timestamp" not in frame.columns:
        raise ValueError("frame must have a 'timestamp' column")
    if price_column not in frame.columns:
        raise ValueError(f"frame is missing price column: {price_column}")
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    working = working.sort_values("timestamp").drop_duplicates(subset="timestamp")
    prices = pd.to_numeric(working[price_column], errors="raise")
    prices.index = pd.DatetimeIndex(working["timestamp"])
    returns = prices.pct_change(fill_method=None).dropna()
    returns.name = "return"
    return returns


def rolling_origin_folds(
    returns: pd.Series,
    *,
    fold_count: int = DEFAULT_FOLD_COUNT,
    embargo_bars: int = DEFAULT_EMBARGO_BARS,
    embargo_reason: str = DEFAULT_EMBARGO_REASON,
    test_years: Sequence[int] | None = None,
) -> tuple[list[WalkForwardSlice], pd.Series]:
    """Split ``returns`` into anchored walk-forward folds and a stitched OOS stream.

    Parameters
    ----------
    returns:
        Daily (or other bar-frequency) returns indexed by a sorted, duplicate-free
        ``DatetimeIndex``. Use :func:`returns_from_ohlcv` to build this from raw
        OHLCV rows.
    fold_count:
        Number of test folds. Ignored if ``test_years`` is given.
    embargo_bars:
        Number of trailing training bars dropped immediately before each fold's
        test window, so training data never abuts a label horizon that leaks
        into the test period.
    test_years:
        Explicit calendar years to use as test windows, in chronological order.
        Defaults to the last ``fold_count`` distinct years present in ``returns``.

    Returns
    -------
    A tuple of (per-fold ``WalkForwardSlice`` records, the chronologically
    sorted, non-overlapping concatenation of every fold's test-window returns).
    """
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise ValueError("returns must be indexed by a DatetimeIndex")
    if returns.index.has_duplicates:
        raise ValueError("returns index must not contain duplicate timestamps")
    ordered = returns.sort_index()

    if test_years is None:
        if fold_count < 1:
            raise ValueError("fold_count must be at least 1")
        available_years = sorted({timestamp.year for timestamp in ordered.index})
        if len(available_years) < fold_count:
            raise ValueError(
                f"only {len(available_years)} distinct calendar year(s) available, "
                f"cannot build {fold_count} fold(s)"
            )
        resolved_test_years: Sequence[int] = available_years[-fold_count:]
    else:
        resolved_test_years = list(test_years)
        if not resolved_test_years:
            raise ValueError("test_years must not be empty")
        if list(resolved_test_years) != sorted(resolved_test_years):
            raise ValueError("test_years must be in chronological order")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")

    folds: list[WalkForwardSlice] = []
    stitched_parts: list[pd.Series] = []
    for fold_number, year in enumerate(resolved_test_years, start=1):
        test_slice = ordered.loc[ordered.index.year == year]
        if test_slice.empty:
            raise ValueError(f"no observations found for test year {year}")
        test_start, test_end = test_slice.index[0], test_slice.index[-1]

        train_slice = ordered.loc[ordered.index < test_start]
        if len(train_slice) <= embargo_bars:
            raise ValueError(
                f"only {len(train_slice)} training observation(s) available before "
                f"{test_start.date()}, not enough to embargo {embargo_bars} bar(s)"
            )
        if embargo_bars:
            train_slice = train_slice.iloc[:-embargo_bars]
        train_start, train_end = train_slice.index[0], train_slice.index[-1]
        if train_end >= test_start:
            raise ValueError(
                f"fold {fold_number}: train_end {train_end} is not strictly before "
                f"test_start {test_start} after embargo"
            )

        split = ResearchWindowSplit(
            train_start=train_start.isoformat(),
            train_end=train_end.isoformat(),
            test_start=test_start.isoformat(),
            test_end=test_end.isoformat(),
            train_rows=len(train_slice),
            test_rows=len(test_slice),
            embargo=PurgedEmbargoConfig(
                purged=True,
                embargo_bars=embargo_bars,
                reason=embargo_reason,
            ),
        )
        folds.append(WalkForwardSlice(fold=fold_number, train=split, test=split))
        stitched_parts.append(test_slice)

    stitched = pd.concat(stitched_parts).sort_index()
    if stitched.index.has_duplicates:
        raise ValueError("stitched out-of-sample series contains duplicate/overlapping dates")
    if not stitched.index.is_monotonic_increasing:
        raise ValueError("stitched out-of-sample series is not chronologically ordered")
    return folds, stitched
