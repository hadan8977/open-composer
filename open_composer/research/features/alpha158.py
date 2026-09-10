"""Step 13-F 3.1: Qlib's Alpha158 feature set, ported to this repo's daily
SIP archive.

``docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md``
section 3.1. Source: ``microsoft/qlib`` ``qlib/contrib/data/loader.py``
(MIT license; see ``reports/harness/source_cards/
step13f_open_factor_libraries.jsonl``, claim ``qlib_alpha158_definition``).

One row per (symbol, trade_date), computed entirely from
``data/sip/daily/`` OHLCV (no ``vwap`` needed -- every Alpha158 formula in
the plan's section 3.1 list uses only open/high/low/close/volume).

**154 columns, not the nominal "158"**: this module implements exactly the
formula list transcribed into the plan (9 K-bar features + 29 rolling
groups over windows ``{5, 10, 20, 30, 60}`` = 9 + 145 = 154). Qlib's own
default ``Alpha158`` config additionally emits 4 non-rolling ``PRICE``
features (``OPEN0``, ``HIGH0``, ``LOW0``, ``VWAP0`` -- today's open/high/low/
vwap relative to today's close) that would bring the total to the
textbook 158; the plan's section 3.1 formula list never mentions them
(and ``VWAP0`` needs ``vwap``, which the plan explicitly says is optional
for this table). Recorded here rather than silently padded to 158 with an
undocumented extra block -- see the module-level docstring convention this
repo already uses in ``daily_features.py`` for the same kind of honest
scope note.

**Implementation strategy (why some columns use ``numpy`` closed-form
sliding windows instead of ``pandas.Series.rolling``)**: most of the 29
rolling groups map directly onto a vectorized ``pandas`` ``Rolling`` method
(``mean``, ``std``, ``max``, ``min``, ``quantile``, ``sum``, ``rank(pct=True)``,
``corr``) with no per-row Python callback. Five quantities do not have a
``pandas`` built-in: ``BETA``/``RSQR``/``RESI`` (the slope, R-squared, and
last-point residual of an OLS regression of ``close`` on a synthetic time
index ``0..d-1`` inside each trailing window) and ``IMAX``/``IMIN`` (the
position of the window's max/min). Per the plan ("rolling.apply 只在
slope/rsquare/resi/idxmax 上用 numpy 闭式解,别用逐行 apply"), these are
computed with :func:`numpy.lib.stride_tricks.sliding_window_view` per
symbol: one strided, zero-copy view of every trailing window at once, then
one vectorized ``numpy`` reduction over ``axis=1`` for the whole symbol's
history -- never a ``.rolling(d).apply(python_function)`` call, which would
invoke a Python-level callback once per row.

**IMAX/IMIN position convention (not pinned down by the plan text, decided
here)**: within a window's ``d`` observations in chronological order, index
``0`` is the OLDEST observation in the window and index ``d - 1`` is TODAY.
``IMAX = argmax(high) / d`` is therefore close to ``(d-1)/d`` when today (or
a very recent day) set the high, and close to ``0`` when the high happened
at the start of the window -- the intuitive "how recently" reading.
``IMXD = IMAX - IMIN`` (the plan's ``(idxmax(high,d)-idxmin(low,d))/d`` is
algebraically identical once both terms are already divided by ``d``).

**Warm-up**: every rolling column is ``NaN`` until a symbol has ``d`` full
trailing observations (matches ``pandas``' default ``min_periods=window``
and this repo's existing convention in ``daily_features.py``); no column
ever fabricates a value from a partial window.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

DEFAULT_WINDOWS: tuple[int, ...] = (5, 10, 20, 30, 60)
DEFAULT_MEMORY_LIMIT = "1.2GB"
_EPS = 1e-12

#: The plan's exact rolling-group names (order preserved for reproducibility
#: and for the MANIFEST column list).
ROLLING_GROUP_NAMES: tuple[str, ...] = (
    "ROC",
    "MA",
    "STD",
    "BETA",
    "RSQR",
    "RESI",
    "MAX",
    "MIN",
    "QTLU",
    "QTLD",
    "RANK",
    "RSV",
    "IMAX",
    "IMIN",
    "IMXD",
    "CORR",
    "CORD",
    "CNTP",
    "CNTN",
    "CNTD",
    "SUMP",
    "SUMN",
    "SUMD",
    "VMA",
    "VSTD",
    "WVMA",
    "VSUMP",
    "VSUMN",
    "VSUMD",
)

KBAR_COLUMNS: tuple[str, ...] = (
    "KMID",
    "KLEN",
    "KMID2",
    "KUP",
    "KUP2",
    "KLOW",
    "KLOW2",
    "KSFT",
    "KSFT2",
)


def alpha158_columns(windows: Sequence[int] = DEFAULT_WINDOWS) -> list[str]:
    """The full ordered 154-column list (``KBAR_COLUMNS`` then every
    rolling-group name suffixed by each window, group-major)."""
    columns = list(KBAR_COLUMNS)
    for name in ROLLING_GROUP_NAMES:
        columns.extend(f"{name}{window}" for window in windows)
    return columns


def _kbar_frame(frame: pd.DataFrame) -> pd.DataFrame:
    open_ = frame["open"].astype("float64")
    high = frame["high"].astype("float64")
    low = frame["low"].astype("float64")
    close = frame["close"].astype("float64")
    hl_range = (high - low) + _EPS
    max_oc = np.maximum(open_, close)
    min_oc = np.minimum(open_, close)
    return pd.DataFrame(
        {
            "KMID": (close - open_) / open_,
            "KLEN": (high - low) / open_,
            "KMID2": (close - open_) / hl_range,
            "KUP": (high - max_oc) / open_,
            "KUP2": (high - max_oc) / hl_range,
            "KLOW": (min_oc - low) / open_,
            "KLOW2": (min_oc - low) / hl_range,
            "KSFT": (2 * close - high - low) / open_,
            "KSFT2": (2 * close - high - low) / hl_range,
        },
        index=frame.index,
    )


def _sliding_ols_and_extrema(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int
) -> dict[str, np.ndarray]:
    """``BETA``/``RSQR``/``RESI``/``IMAX``/``IMIN`` for one symbol's full
    history and one window size, via one strided view + vectorized numpy
    reductions (no per-row Python callback). Returns arrays the same length
    as the input, ``NaN``-padded for the first ``window - 1`` positions.
    """
    n = close.shape[0]
    out = {
        name: np.full(n, np.nan, dtype="float64")
        for name in ("BETA", "RSQR", "RESI", "IMAX", "IMIN")
    }
    if n < window:
        return out

    x = np.arange(window, dtype="float64")
    x_mean = x.mean()
    xm = x - x_mean
    sxx = float(np.dot(xm, xm))  # > 0 for window >= 2

    y_windows = sliding_window_view(close, window)  # shape (n-window+1, window)
    y_mean = y_windows.mean(axis=1)
    ym = y_windows - y_mean[:, None]
    sxy = ym @ xm  # sum_i xm_i * ym_i, shape (n-window+1,)
    syy = np.einsum("ij,ij->i", ym, ym)

    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    predicted_last = intercept + slope * x[-1]
    resi = y_windows[:, -1] - predicted_last
    with np.errstate(divide="ignore", invalid="ignore"):
        rsquare = np.where(syy > 0, (sxy * sxy) / (sxx * syy), 0.0)

    high_windows = sliding_window_view(high, window)
    low_windows = sliding_window_view(low, window)
    imax = np.argmax(high_windows, axis=1) / window
    imin = np.argmin(low_windows, axis=1) / window

    out["BETA"][window - 1 :] = slope
    out["RSQR"][window - 1 :] = rsquare
    out["RESI"][window - 1 :] = resi
    out["IMAX"][window - 1 :] = imax
    out["IMIN"][window - 1 :] = imin
    return out


def _rolling_group_frame_for_symbol(
    sym_frame: pd.DataFrame, windows: Sequence[int]
) -> pd.DataFrame:
    """The 145 rolling-group columns for one symbol's full (sorted by
    ``trade_date``) history. ``sym_frame`` must already be restricted to a
    single symbol.
    """
    close = sym_frame["close"].astype("float64")
    high = sym_frame["high"].astype("float64")
    low = sym_frame["low"].astype("float64")
    volume = sym_frame["volume"].astype("float64")
    close_prev = close.shift(1)
    volume_prev = volume.shift(1)
    close_ret = close / close_prev  # "close/close[-1]"
    log_volume = np.log(volume + 1.0)
    log_volume_chg = np.log((volume / volume_prev) + 1.0)

    close_diff = close - close_prev
    close_diff_abs = close_diff.abs()
    close_diff_pos = close_diff.clip(lower=0.0)
    close_diff_neg = (-close_diff).clip(lower=0.0)

    vol_diff = volume - volume_prev
    vol_diff_abs = vol_diff.abs()
    vol_diff_pos = vol_diff.clip(lower=0.0)
    vol_diff_neg = (-vol_diff).clip(lower=0.0)

    abs_ret_x_volume = (close_ret - 1.0).abs() * volume

    close_np = close.to_numpy(dtype="float64")
    high_np = high.to_numpy(dtype="float64")
    low_np = low.to_numpy(dtype="float64")

    columns: dict[str, pd.Series] = {}
    for window in windows:
        w = window
        ols_extrema = _sliding_ols_and_extrema(high_np, low_np, close_np, w)

        roll_close = close.rolling(w)
        roll_high = high.rolling(w)
        roll_low = low.rolling(w)
        roll_volume = volume.rolling(w)

        min_low = roll_low.min()
        max_high = roll_high.max()
        cntp = (close > close_prev).rolling(w).mean()
        cntn = (close < close_prev).rolling(w).mean()
        sum_abs = close_diff_abs.rolling(w).sum()
        sum_pos = close_diff_pos.rolling(w).sum()
        sum_neg = close_diff_neg.rolling(w).sum()
        vsum_abs = vol_diff_abs.rolling(w).sum()
        vsum_pos = vol_diff_pos.rolling(w).sum()
        vsum_neg = vol_diff_neg.rolling(w).sum()
        mean_abs_ret_vol = abs_ret_x_volume.rolling(w).mean()
        std_abs_ret_vol = abs_ret_x_volume.rolling(w).std()

        beta = pd.Series(ols_extrema["BETA"], index=sym_frame.index)
        rsqr = pd.Series(ols_extrema["RSQR"], index=sym_frame.index)
        resi = pd.Series(ols_extrema["RESI"], index=sym_frame.index)
        imax = pd.Series(ols_extrema["IMAX"], index=sym_frame.index)
        imin = pd.Series(ols_extrema["IMIN"], index=sym_frame.index)

        columns[f"ROC{w}"] = close.shift(w) / close
        columns[f"MA{w}"] = roll_close.mean() / close
        columns[f"STD{w}"] = roll_close.std() / close
        columns[f"BETA{w}"] = beta / close
        columns[f"RSQR{w}"] = rsqr
        columns[f"RESI{w}"] = resi / close
        columns[f"MAX{w}"] = max_high / close
        columns[f"MIN{w}"] = min_low / close
        columns[f"QTLU{w}"] = roll_close.quantile(0.8) / close
        columns[f"QTLD{w}"] = roll_close.quantile(0.2) / close
        columns[f"RANK{w}"] = roll_close.rank(pct=True)
        columns[f"RSV{w}"] = (close - min_low) / ((max_high - min_low) + _EPS)
        columns[f"IMAX{w}"] = imax
        columns[f"IMIN{w}"] = imin
        columns[f"IMXD{w}"] = imax - imin
        columns[f"CORR{w}"] = close.rolling(w).corr(log_volume)
        columns[f"CORD{w}"] = close_ret.rolling(w).corr(log_volume_chg)
        columns[f"CNTP{w}"] = cntp
        columns[f"CNTN{w}"] = cntn
        columns[f"CNTD{w}"] = cntp - cntn
        columns[f"SUMP{w}"] = sum_pos / (sum_abs + _EPS)
        columns[f"SUMN{w}"] = sum_neg / (sum_abs + _EPS)
        columns[f"SUMD{w}"] = (sum_pos - sum_neg) / (sum_abs + _EPS)
        columns[f"VMA{w}"] = roll_volume.mean() / (volume + _EPS)
        columns[f"VSTD{w}"] = roll_volume.std() / (volume + _EPS)
        columns[f"WVMA{w}"] = std_abs_ret_vol / (mean_abs_ret_vol + _EPS)
        columns[f"VSUMP{w}"] = vsum_pos / (vsum_abs + _EPS)
        columns[f"VSUMN{w}"] = vsum_neg / (vsum_abs + _EPS)
        columns[f"VSUMD{w}"] = (vsum_pos - vsum_neg) / (vsum_abs + _EPS)

    return pd.DataFrame(columns, index=sym_frame.index)


def compute_alpha158(
    frame: pd.DataFrame, *, windows: Sequence[int] = DEFAULT_WINDOWS
) -> pd.DataFrame:
    """Compute all 154 Alpha158 columns for an in-memory OHLCV frame.

    ``frame`` needs ``symbol, trade_date, open, high, low, close, volume``
    (extra columns are ignored). Not sorted in place; a sorted copy is used
    internally. Returns ``symbol, trade_date`` plus the 154 feature columns,
    same row count and order as ``frame`` sorted by ``(symbol, trade_date)``.
    """
    required = {"symbol", "trade_date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"alpha158 input frame missing columns: {sorted(missing)}")

    sorted_frame = frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    kbar = _kbar_frame(sorted_frame)
    rolling_parts = [
        _rolling_group_frame_for_symbol(sym_frame, windows)
        for _, sym_frame in sorted_frame.groupby("symbol", sort=False, group_keys=False)
    ]
    rolling = pd.concat(rolling_parts, axis=0).reindex(sorted_frame.index)
    result = pd.concat(
        [sorted_frame[["symbol", "trade_date"]], kbar, rolling],
        axis=1,
    )
    return result[["symbol", "trade_date"] + alpha158_columns(windows)]


def build_alpha158_features(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Load OHLCV rows for ``universe_symbols`` from ``daily_glob`` (a
    DuckDB ``read_parquet`` glob, typically ``[year-1, year]`` per
    ``scripts/build_alpha158_features.py``) and compute Alpha158.
    Mirrors ``daily_features.build_daily_features``'s DuckDB-load /
    pandas-compute split and per-symbol-batch calling convention.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    if not symbols:
        return pd.DataFrame(columns=["symbol", "trade_date"] + alpha158_columns(windows))

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
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date, open, high, low, close, volume
            FROM read_parquet({daily_glob!r})
            WHERE symbol IN (SELECT symbol FROM _universe_symbols)
            ORDER BY symbol, trade_date
        """
        raw = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    if raw.empty:
        return pd.DataFrame(columns=["symbol", "trade_date"] + alpha158_columns(windows))
    raw["trade_date"] = pd.to_datetime(raw["trade_date"])
    return compute_alpha158(raw, windows=windows)
