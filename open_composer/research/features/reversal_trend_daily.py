"""Step 13-P scope addition, Track F part: reversal-trend daily factor table.

docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section A1 ("F 轨代理，作为第 5 个库" -- the 5th open factor library, alongside
Alpha158/Alpha101/Alpha191/OSAP). One row per (symbol, trade_date), float32,
the named ``rt_*`` columns listed there.

This module reuses Track P's Pine port
(``open_composer/research/pine_port/reversal_trend.py::compute_reversal_trend``)
rather than re-deriving the EMA/RMA/RSI/ATR/MACD/DMI-ADX indicators and the
arm/lock/cooldown state machine a second time -- one implementation of the
Pine semantics, not two that could silently diverge. This module only adds
the handful of derived columns the daily factor table needs beyond what that
port already returns (macd_hist_slope, atr_ext_ema20, the three EMA/price
ratios, and four "bars since last True" counters), then selects/renames/casts
to the plan's exact column list.

**Column split for section 3.5's screen vs A2's event study** (plan A1's
closing sentence: "连续列按 rank IC；0/1 列按事件研究" -- continuous columns go
into rank-IC, 0/1 columns go into the event study): the four discrete
trade-trigger *signal* columns (``rt_bull_signal``/``rt_recl_signal``/
``rt_bear_signal``/``rt_recs_signal`` -- ``compute_reversal_trend``'s own
docstring calls these "signal columns", ``f_bull`` etc., distinct from its
"state columns" ``os_active``/``ob_active``/``dwell_*``/``bars_since_*``) are
:data:`REVERSAL_TREND_SIGNAL_COLUMNS`, event-study-only per plan A2 ("对四个
信号各算" -- compute for each of the four signals). Every other ``rt_*``
column -- including ``rt_os_active``/``rt_ob_active``, which are also
mechanically 0/1-valued but are not "signals" in that vocabulary and behave
more like a decaying regime indicator than a single-bar event -- is
:data:`REVERSAL_TREND_CONTINUOUS_COLUMNS` and goes into the 3.5 rank-IC
screen. The plan text does not spell out this specific boundary; this is a
documented judgment call, not a stated requirement.

**Lookback**: unlike OSAP (``osap_price.py``, ``LOOKBACK_YEARS=6``), this
table's indicators are recursive EMA/RMA filters (converge geometrically, no
hard N-row NaN warm-up the way a fixed rolling window does) and the state
machine's longest cross-bar memory is ``arm_max_bars=35``/``bull_cooldown=30``
bars -- both far shorter than a year. ``LOOKBACK_YEARS=1`` (matching
``daily_features.py``/``alpha158.py``/``build_alpha101_alpha191_features.py``)
is enough for the recursive filters to burn in before the target year begins.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from open_composer.research.pine_port.reversal_trend import compute_reversal_trend

DEFAULT_MEMORY_LIMIT = "1.2GB"

#: Exact order from plan section A1's column list.
REVERSAL_TREND_COLUMNS: tuple[str, ...] = (
    "rt_rsi14",
    "rt_macd_hist",
    "rt_macd_hist_slope",
    "rt_bars_since_macd_bull_cross",
    "rt_bars_since_macd_bear_cross",
    "rt_adx14",
    "rt_close_over_ema20",
    "rt_close_over_ema50",
    "rt_ema20_over_ema50",
    "rt_ema50_over_ema200",
    "rt_atr_ext_ema20",
    "rt_dwell_os",
    "rt_dwell_ob",
    "rt_rsi_low15",
    "rt_rsi_high15",
    "rt_os_active",
    "rt_ob_active",
    "rt_bars_since_os_event",
    "rt_bars_since_ob_event",
    "rt_bull_signal",
    "rt_recl_signal",
    "rt_bear_signal",
    "rt_recs_signal",
    "rt_bars_since_bull_or_recl",
    "rt_bars_since_bear_or_recs",
)

#: The four discrete trade-trigger signals -- event-study-only (see module
#: docstring).
REVERSAL_TREND_SIGNAL_COLUMNS: tuple[str, ...] = (
    "rt_bull_signal",
    "rt_recl_signal",
    "rt_bear_signal",
    "rt_recs_signal",
)

#: Everything else -- goes into the 3.5 rank-IC screen.
REVERSAL_TREND_CONTINUOUS_COLUMNS: tuple[str, ...] = tuple(
    column for column in REVERSAL_TREND_COLUMNS if column not in REVERSAL_TREND_SIGNAL_COLUMNS
)


def _bars_since_last_true(cond: np.ndarray) -> np.ndarray:
    """ "Bars since the most recent True in ``cond``" -- ``NaN`` before the
    first-ever True, ``0.0`` on the bar a True occurs, ``1.0`` the bar after,
    etc. Same running-max-over-event-positions trick
    ``compute_reversal_trend``'s own ``_consecutive_true_run`` uses, but for
    "distance since last True" rather than "length of the current True run";
    matches the existing ``bars_since_os_event``/``bars_since_ob_event``
    convention that module's state machine already returns.
    """
    n = len(cond)
    idx = np.arange(n)
    event_positions = np.where(cond, idx, -1)
    last_event = np.maximum.accumulate(event_positions)
    return np.where(last_event >= 0, (idx - last_event).astype(float), np.nan)


def _bars_since_last_true_by_symbol(frame: pd.DataFrame, cond: pd.Series) -> pd.Series:
    """Groups ``cond`` by ``frame['symbol']`` before applying
    :func:`_bars_since_last_true`, so the counter resets at every symbol
    boundary instead of leaking across symbols in a multi-symbol batch.
    """
    return cond.groupby(frame["symbol"], sort=False).transform(
        lambda group: _bars_since_last_true(group.to_numpy())
    )


def compute_reversal_trend_daily(bars: pd.DataFrame) -> pd.DataFrame:
    """``bars`` needs ``symbol, trade_date, open, high, low, close, volume``,
    sorted ascending by ``trade_date`` within each ``symbol`` (this function
    does not re-sort -- ``compute_reversal_trend`` raises if it is not).
    Returns ``symbol, trade_date, *REVERSAL_TREND_COLUMNS`` (float32 for the
    ``rt_*`` columns, per the plan's explicit dtype).
    """
    working = bars.copy()
    working["timestamp"] = working["trade_date"]
    computed = compute_reversal_trend(working)

    macd_hist_slope = computed.groupby("symbol", sort=False)["macd_hist"].transform(
        lambda group: group.diff()
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_ext_ema20 = (computed["close"] - computed["ema_fast"]) / computed["atr"]
    atr_ext_ema20 = atr_ext_ema20.where(computed["atr"] > 0)

    bull_or_recl = computed["f_bull"] | computed["f_recl"]
    bear_or_recs = computed["f_bear"] | computed["f_recs"]

    out = pd.DataFrame(
        {
            "symbol": computed["symbol"],
            "trade_date": computed["trade_date"],
            "rt_rsi14": computed["rsi"],
            "rt_macd_hist": computed["macd_hist"],
            "rt_macd_hist_slope": macd_hist_slope,
            "rt_bars_since_macd_bull_cross": _bars_since_last_true_by_symbol(
                computed, computed["macd_bull_cross"]
            ),
            "rt_bars_since_macd_bear_cross": _bars_since_last_true_by_symbol(
                computed, computed["macd_bear_cross"]
            ),
            "rt_adx14": computed["adx"],
            "rt_close_over_ema20": computed["close"] / computed["ema_fast"],
            "rt_close_over_ema50": computed["close"] / computed["ema_mid"],
            "rt_ema20_over_ema50": computed["ema_fast"] / computed["ema_mid"],
            "rt_ema50_over_ema200": computed["ema_mid"] / computed["ema_slow"],
            "rt_atr_ext_ema20": atr_ext_ema20,
            "rt_dwell_os": computed["dwell_os"],
            "rt_dwell_ob": computed["dwell_ob"],
            "rt_rsi_low15": computed["rsi_lowest_15"],
            "rt_rsi_high15": computed["rsi_highest_15"],
            "rt_os_active": computed["os_active"].astype(np.float32),
            "rt_ob_active": computed["ob_active"].astype(np.float32),
            "rt_bars_since_os_event": computed["bars_since_os_event"],
            "rt_bars_since_ob_event": computed["bars_since_ob_event"],
            "rt_bull_signal": computed["f_bull"].astype(np.float32),
            "rt_recl_signal": computed["f_recl"].astype(np.float32),
            "rt_bear_signal": computed["f_bear"].astype(np.float32),
            "rt_recs_signal": computed["f_recs"].astype(np.float32),
            "rt_bars_since_bull_or_recl": _bars_since_last_true_by_symbol(computed, bull_or_recl),
            "rt_bars_since_bear_or_recs": _bars_since_last_true_by_symbol(computed, bear_or_recs),
        }
    )
    for column in REVERSAL_TREND_COLUMNS:
        out[column] = out[column].astype(np.float32)
    return out.reset_index(drop=True)


def _load_ohlcv_batch(
    glob_paths: list[str], batch_symbols: list[str], memory_limit: str
) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=2")
        con.execute("SET preserve_insertion_order=false")
        con.register("_batch_symbols", pd.DataFrame({"symbol": batch_symbols}))
        query = f"""
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date,
                   open, high, low, close, volume
            FROM read_parquet({glob_paths!r})
            WHERE symbol IN (SELECT symbol FROM _batch_symbols)
            ORDER BY symbol, trade_date
        """
        raw = con.execute(query).fetchdf()
    finally:
        con.close()
    if not raw.empty:
        raw["trade_date"] = pd.to_datetime(raw["trade_date"])
    return raw


def build_reversal_trend_features(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
) -> pd.DataFrame:
    """Load OHLCV for ``universe_symbols`` from ``daily_glob`` and compute
    :func:`compute_reversal_trend_daily`. ``temp_directory`` is accepted for
    interface parity with the other Step 13-F build functions but unused --
    this table's DuckDB step is a plain OHLCV scan, never large enough on a
    300-symbol/1-2-year batch to need spill-to-disk.
    """
    del temp_directory
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    if not symbols:
        return pd.DataFrame(columns=["symbol", "trade_date", *REVERSAL_TREND_COLUMNS])
    raw = _load_ohlcv_batch(
        glob_paths=daily_glob if isinstance(daily_glob, list) else [daily_glob],
        batch_symbols=symbols,
        memory_limit=memory_limit,
    )
    if raw.empty:
        return pd.DataFrame(columns=["symbol", "trade_date", *REVERSAL_TREND_COLUMNS])
    return compute_reversal_trend_daily(raw)
