"""Wide-panel (index=trade_date, columns=symbol) operator vocabulary shared
by :mod:`alpha101` and :mod:`alpha191`.

Both WorldQuant's *101 Formulaic Alphas* (Kakushadze 2016) and GTJA's 2017
Alpha191 research report are written in the same small operator vocabulary
(``rank`` = cross-sectional percentile rank on a date, ``delta``/``delay`` =
time-series diff/shift within a symbol, ``correlation``/``covariance`` =
rolling correlation/covariance between two aligned series, ``ts_*`` =
rolling time-series versions of ``min``/``max``/``sum``/``rank``/``argmax``/
``argmin``). Every real open pandas port of either paper (spot-checked here
against ``yli188/WorldQuant_alpha101_code`` and ``Daic115/alpha191`` -- see
``reports/harness/source_cards/step13f_open_factor_libraries.jsonl``)
represents a field as a **wide** ``DataFrame`` (dates as the index, symbols
as columns) rather than a long ``(symbol, trade_date)`` table, because that
makes ``rank`` a one-line ``axis=1`` operation and every ``ts_*`` operator a
plain vectorized ``pandas`` ``Rolling`` call applied to every symbol/column
at once -- no per-symbol Python loop anywhere in this module.

``ts_argmax``/``ts_argmin`` have no ``pandas`` built-in; both use
:func:`numpy.lib.stride_tricks.sliding_window_view` with ``axis=0`` to get
one strided view of every trailing window *for every column at once*, then
one vectorized ``numpy.argmax``/``argmin`` over the last axis -- the same
"numpy closed-form instead of a per-row callback" approach used in
``alpha158.py``, extended here to the whole panel in one call instead of
one call per symbol (verified faster and no less correct: a 2-D
``sliding_window_view`` with ``axis=0`` keeps every column's window
independent along axis 0, confirmed against a hand-built loop in this
module's tests).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def rank(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank (0-1) across symbols, per date."""
    return panel.rank(axis=1, pct=True)


def delta(panel: pd.DataFrame, period: int = 1) -> pd.DataFrame:
    return panel.diff(period)


def delay(panel: pd.DataFrame, period: int = 1) -> pd.DataFrame:
    return panel.shift(period)


def ts_sum(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window).sum()


def sma(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """Simple (equal-weight) moving average -- the paper's "SMA/MEAN(X,d)"."""
    return panel.rolling(window).mean()


def stddev(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window).std()


def correlation(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).corr(y)


def covariance(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).cov(y)


def ts_min(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window).min()


def ts_max(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window).max()


def ts_rank(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """Rolling percentile rank (0-1) of today's value within its own
    trailing ``window`` -- pandas' native ``Rolling.rank(pct=True)``, not a
    cross-sectional rank.
    """
    return panel.rolling(window).rank(pct=True)


def _ts_extremum_position(panel: pd.DataFrame, window: int, *, use_max: bool) -> pd.DataFrame:
    """0-based position (0 = oldest day in the window, ``window - 1`` =
    today) of the window's max (``use_max=True``) or min value, for every
    column at once. NaN for the first ``window - 1`` rows of each column.
    """
    values = panel.to_numpy(dtype="float64")
    n_rows, n_cols = values.shape
    out = np.full((n_rows, n_cols), np.nan, dtype="float64")
    if n_rows >= window:
        windows = sliding_window_view(values, window, axis=0)  # (n-w+1, n_cols, w)
        position = np.argmax(windows, axis=-1) if use_max else np.argmin(windows, axis=-1)
        out[window - 1 :, :] = position.astype("float64")
    return pd.DataFrame(out, index=panel.index, columns=panel.columns)


def ts_argmax(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return _ts_extremum_position(panel, window, use_max=True)


def ts_argmin(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return _ts_extremum_position(panel, window, use_max=False)


def sign(panel: pd.DataFrame) -> pd.DataFrame:
    return np.sign(panel)


def safe_log(panel: pd.DataFrame) -> pd.DataFrame:
    """``log(x)`` (natural log, the paper's ``Log`` operator -- NOT
    ``log1p``) guarded against non-positive input (returns ``NaN`` there
    rather than raising/``-inf``).
    """
    return panel.where(panel > 0).apply(np.log)


def recursive_ewm(panel: pd.DataFrame, n: int, m: int = 1) -> pd.DataFrame:
    """The Chinese sell-side research convention ``SMA(X, N, M)``: the
    recursive exponential average ``y_t = (M/N) * x_t + (1 - M/N) * y_{t-1}``
    (GTJA Alpha191 formulas 009/022/023/024/027/028/040 and others).
    ``adjust=False`` is required for fidelity to that recursive definition
    (pandas' default ``adjust=True`` reweights the early terms differently
    and was confirmed, by inspection, to be what the fetched
    ``Daic115/alpha191`` reference uses -- this module deliberately departs
    from that reference to match the recursive formula as published).
    """
    return panel.ewm(alpha=m / n, adjust=False).mean()


def replace_inf_with_nan(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.replace([np.inf, -np.inf], np.nan)
