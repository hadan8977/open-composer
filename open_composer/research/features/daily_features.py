"""Step 11 Wave A 3.3.2 (phase 1: daily-archive-only columns).

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 2. One row
per (symbol, trading day), computed entirely from ``data/sip/daily/`` (all
prices already ``adjustment=all``), restricted to the PIT universe's
full-history symbol union.

**Phased scope, recorded here rather than silently shipped partial**: the
plan's full ~40-column daily feature table also includes 5d/21d rolling means
of the minute-bar-derived intraday columns (``intraday_daily.py``, Wave A
3.3.1). That backfill is the multi-hour job the plan itself calls "本轮最重的
一次性计算" and this module does not block on it: it ships the ~23
daily-archive-only columns below (return, risk, liquidity, position, and
market-relative blocks -- every category in the plan's list except the
minute-derived rolling block), and :func:`join_intraday_rolling_features`
adds the remaining ~18 columns once ``data/features/intraday_daily/`` is
available for a given year. Wave B's own grid already plans to A/B test
"daily-only" vs "daily+intraday" feature sets, so this phasing lines up with
a distinction the plan wants measured anyway rather than working around it.

**Implementation choices not fully pinned by the plan text**:

* Volatility columns (``vol_21``, ``vol_63``, ``idio_vol_63``) are raw daily
  standard deviations, not annualized -- annualization is a monotonic
  rescaling that a tree model (LightGBM) is invariant to and a standardized
  linear model (ridge on ``StandardScaler``-ed inputs) also normalizes away;
  keeping it in native daily units avoids an arbitrary ``sqrt(252)`` choice
  that has no effect on either downstream model.
* ``idio_vol_63`` uses the closed-form identity for simple-OLS residual
  variance, ``Var(residual) = Var(y)*(1-corr(x,y)^2)``, rather than a
  self-join to materialize per-day residuals -- mathematically exact for a
  one-regressor OLS (``beta_63`` is not separately persisted as a feature;
  the plan asks for a 252-day beta, and a second, shorter-window beta is an
  intermediate of this formula only).
* "离252日最高价的距离" (``dist_from_252d_high``) includes the current day in
  its trailing high-water mark (``close / MAX(close) OVER 252d - 1``, always
  ``<= 0``), not a high computed strictly before today -- the plan does not
  pin this down either way and this is the more common convention.
* Market-relative features subtract the **cross-sectional median** (plan's
  own wording: "每个收益类特征减去当日宇宙中位数") computed over exactly the
  rows present in this table for that date -- i.e. the PIT universe as
  already filtered by the caller, not the full raw archive.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

#: 1.2GB (not the 2GB the plan's machine budget allows in general) so this
#: can safely run concurrently with the much heavier intraday_daily.py
#: backfill on this 3.8GB box -- the daily archive itself is small (545MB
#: total across all years/symbols) so the tighter cap costs nothing here.
DEFAULT_MEMORY_LIMIT = "1.2GB"
DEFAULT_MARKET_SYMBOL = "SPY"
DEFAULT_RETURN_WINDOWS: tuple[int, ...] = (1, 5, 21, 63, 126, 252)
DEFAULT_VOL_WINDOWS: tuple[int, ...] = (21, 63)
DEFAULT_BETA_WINDOW = 252
DEFAULT_IDIO_VOL_WINDOW = 63
DEFAULT_MAX_RETURN_WINDOW = 21
DEFAULT_ADV_WINDOWS: tuple[int, ...] = (21, 63)
DEFAULT_AMIHUD_WINDOW = 21
DEFAULT_HIGH_WINDOW = 252
#: Skip-most-recent-month momentum: trailing-252-day return minus trailing-21
#: -day return, per plan section 3.3 ("动量 ret_252 − ret_21（跳过最近一月）").
DEFAULT_MOMENTUM_LONG_WINDOW = 252
DEFAULT_MOMENTUM_SKIP_WINDOW = 21

RETURN_RELATIVE_SUFFIX = "_rel"


def _return_column(window: int) -> str:
    return f"ret_{window}"


def build_daily_features(
    daily_glob: str,
    universe_symbols: list[str],
    *,
    market_symbol: str = DEFAULT_MARKET_SYMBOL,
    return_windows: tuple[int, ...] = DEFAULT_RETURN_WINDOWS,
    vol_windows: tuple[int, ...] = DEFAULT_VOL_WINDOWS,
    beta_window: int = DEFAULT_BETA_WINDOW,
    idio_vol_window: int = DEFAULT_IDIO_VOL_WINDOW,
    max_return_window: int = DEFAULT_MAX_RETURN_WINDOW,
    adv_windows: tuple[int, ...] = DEFAULT_ADV_WINDOWS,
    amihud_window: int = DEFAULT_AMIHUD_WINDOW,
    high_window: int = DEFAULT_HIGH_WINDOW,
    momentum_long_window: int = DEFAULT_MOMENTUM_LONG_WINDOW,
    momentum_skip_window: int = DEFAULT_MOMENTUM_SKIP_WINDOW,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Daily-archive-only feature block (see module docstring for the phased
    scope). Every window is a trailing, PIT-safe ``ROWS BETWEEN N-1 PRECEDING
    AND CURRENT ROW`` computation -- no column ever uses same-day-or-later
    information from another symbol or the future.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    if not symbols:
        return pd.DataFrame(columns=_all_columns(return_windows, vol_windows, adv_windows))

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

        def _guard(min_rows: int, expr: str) -> str:
            # DuckDB's ``ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW`` frame is
            # happy to compute an aggregate over however many rows physically
            # exist even when fewer than N are present (a 5-row stddev with
            # only 2 real observations near the start of a symbol's history).
            # That silently fabricates a "5-day" statistic from 2 days of
            # data. Guarding on ``rn`` (this symbol's 1-indexed row number)
            # makes every windowed column NULL until it has truly seen a full
            # window, matching pandas' ``rolling(window).std()`` default
            # (``min_periods=window``) -- verified against it in
            # tests/test_daily_features.py.
            return f"CASE WHEN rn >= {min_rows} THEN {expr} ELSE NULL END"

        return_selects = ",\n".join(
            f"    close / LAG(close, {window}) OVER (PARTITION BY symbol ORDER BY trade_date) "
            f"- 1.0 AS {_return_column(window)}"
            for window in return_windows
            if window != 1
        )
        # ret_1 is needed by several other columns (vol, beta, Amihud) so it
        # is always computed even if 1 is not in ``return_windows``. Every
        # ret_1-consuming window needs ``window + 1`` physical rows (row 1 of
        # each symbol has a NULL ret_1, since there is no prior close to
        # divide by) to see ``window`` real ret_1 observations.
        vol_selects = ",\n".join(
            f"    {_guard(window + 1, f'STDDEV_SAMP(ret_1) OVER w{window}')} AS vol_{window}"
            for window in vol_windows
        )
        adv_selects = ",\n".join(
            f"    {_guard(window, f'AVG(close * volume) OVER w{window}')} AS dollar_adv_{window}"
            for window in adv_windows
        )
        window_defs = ",\n".join(
            f"        w{window} AS ("
            f"PARTITION BY symbol ORDER BY trade_date "
            f"ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW)"
            for window in sorted(
                set(vol_windows)
                | {beta_window, idio_vol_window, max_return_window}
                | set(adv_windows)
                | {amihud_window, high_window}
            )
        )
        relative_selects = ",\n".join(
            f"                ({_return_column(window)} "
            f"- MEDIAN({_return_column(window)}) OVER (PARTITION BY trade_date)) "
            f"AS {_return_column(window)}{RETURN_RELATIVE_SUFFIX}"
            for window in return_windows
        )
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, close, volume
                FROM read_parquet({daily_glob!r})
                WHERE symbol IN (SELECT symbol FROM _universe_symbols) OR symbol = '{market_symbol}'
            ),
            priced AS (
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) AS trade_date,
                    close,
                    volume,
                    close / LAG(close) OVER w1 - 1.0 AS ret_1,
                    ROW_NUMBER() OVER w1 AS rn
                FROM raw
                WINDOW w1 AS (PARTITION BY symbol ORDER BY timestamp)
            ),
            market AS (
                SELECT trade_date, ret_1 AS mkt_ret_1 FROM priced WHERE symbol = '{market_symbol}'
            ),
            joined AS (
                SELECT priced.*, market.mkt_ret_1
                FROM priced
                JOIN market USING (trade_date)
                WHERE priced.symbol != '{market_symbol}'
            ),
            windowed AS (
                SELECT
                    symbol, trade_date, close, ret_1,
{return_selects},
{vol_selects},
                    {
            _guard(beta_window + 1, f"REGR_SLOPE(ret_1, mkt_ret_1) OVER w{beta_window}")
        } AS beta_{beta_window}_{market_symbol.lower()},
                    {
            _guard(
                idio_vol_window + 1,
                f"STDDEV_SAMP(ret_1) OVER w{idio_vol_window} * SQRT("
                f"1.0 - POWER(COALESCE(CORR(ret_1, mkt_ret_1) OVER w{idio_vol_window}, 0.0), 2))",
            )
        } AS idio_vol_{idio_vol_window},
                    {
            _guard(max_return_window + 1, f"MAX(ret_1) OVER w{max_return_window}")
        } AS max_ret_1_{max_return_window},
{adv_selects},
                    {
            _guard(
                amihud_window + 1,
                f"AVG(ABS(ret_1) / NULLIF(close * volume, 0)) OVER w{amihud_window}",
            )
        } AS amihud_{amihud_window},
                    {
            _guard(high_window, f"(close / MAX(close) OVER w{high_window} - 1.0)")
        } AS dist_from_{high_window}d_high
                FROM joined
                WINDOW
{window_defs}
            ),
            with_momentum AS (
                SELECT
                    *,
                    ({_return_column(momentum_long_window)} - {
            _return_column(momentum_skip_window)
        })
                        AS momentum_{momentum_long_window}_{momentum_skip_window},
                    (
                        dollar_adv_{adv_windows[0]}
                        / NULLIF(dollar_adv_{adv_windows[-1]}, 0)
                    ) AS dollar_adv_{adv_windows[0]}_over_{adv_windows[-1]}
                FROM windowed
            )
            SELECT
                *,
{relative_selects},
                (
                    momentum_{momentum_long_window}_{momentum_skip_window}
                    - MEDIAN(momentum_{momentum_long_window}_{momentum_skip_window})
                        OVER (PARTITION BY trade_date)
                ) AS momentum_{momentum_long_window}_{momentum_skip_window}{RETURN_RELATIVE_SUFFIX}
            FROM with_momentum
            ORDER BY symbol, trade_date
        """
        frame = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def _all_columns(
    return_windows: tuple[int, ...], vol_windows: tuple[int, ...], adv_windows: tuple[int, ...]
) -> list[str]:
    columns = ["symbol", "trade_date", "close", "ret_1"]
    columns += [_return_column(w) for w in return_windows if w != 1]
    columns += [f"vol_{w}" for w in vol_windows]
    columns += [f"dollar_adv_{w}" for w in adv_windows]
    return columns


def join_intraday_rolling_features(
    daily_frame: pd.DataFrame,
    intraday_daily_frame: pd.DataFrame,
    *,
    rolling_windows: tuple[int, ...] = (5, 21),
) -> pd.DataFrame:
    """Left-join 5d/21d trailing means of every ``intraday_daily.py`` column
    onto ``daily_frame`` (plan section 3.3: "上表每列的5日与21日均值"). A
    symbol/date with no ``intraday_daily`` coverage yet (backfill in
    progress, or a date before the minute archive starts) gets ``NaN`` for
    these columns rather than dropping the row -- the daily-only columns
    remain usable even where the intraday backfill has not caught up.
    """
    from open_composer.research.features.intraday_daily import INTRADAY_DAILY_COLUMNS

    intraday_value_columns = [
        column for column in INTRADAY_DAILY_COLUMNS if column not in ("symbol", "trade_date")
    ]
    sorted_intraday = intraday_daily_frame.sort_values(["symbol", "trade_date"]).copy()
    rolled = sorted_intraday[["symbol", "trade_date"]].copy()
    grouped = sorted_intraday.groupby("symbol", group_keys=False, sort=False)
    for window in rolling_windows:
        means = grouped[intraday_value_columns].rolling(window, min_periods=1).mean()
        means.index = sorted_intraday.index
        means = means.add_suffix(f"_{window}d_mean")
        rolled = pd.concat([rolled, means], axis=1)

    merged = daily_frame.merge(rolled, on=["symbol", "trade_date"], how="left")
    return merged
