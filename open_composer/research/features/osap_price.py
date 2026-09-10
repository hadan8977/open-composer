"""Step 13-F 3.3: Open Source Asset Pricing (Chen & Zimmermann) price-only
signal subset, re-implemented as daily rolling proxies.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.3. Source: ``OpenSourceAP/CrossSection`` ``SignalDoc.csv`` (see
``reports/harness/source_cards/step13f_open_factor_libraries.jsonl``, claim
``osap_crsp_only_signals``): 28 of 313 catalogued signals use CRSP
price/volume data only. Every OSAP signal is originally **monthly**; this
module follows the plan's own framing ("学术月频因子,我们按日频滚动版实现"
-- academic monthly factors, reimplemented as daily rolling versions) and
documents every daily-proxy choice below rather than claiming an exact
replication.

One row per (symbol, trade_date), computed from ``data/sip/daily/`` OHLCV
plus SPY as the market proxy (this repo has no Fama-French factor data, so
every "3-factor" OSAP construction substitutes a single-factor SPY
regression, matching the convention ``daily_features.py`` already uses for
``idio_vol_63``/``beta_252_spy``).

**"Month" proxy used throughout this module**: OSAP's monthly signals are
built from calendar months; this table only has trading days, so a
"month" is approximated as a fixed 21-trading-day block and
``month_return(k) = close[t-21k] / close[t-21(k+1)] - 1`` is "the return
earned from 21*(k+1) trading days ago to 21*k trading days ago" -- e.g.
``month_return(1)`` is roughly last month's return, ``month_return(12)``
is roughly the same calendar month one year ago. This is a coarser,
non-calendar-aligned proxy; documented, not hidden.

**Columns implemented (24 of the ~20 the plan sketches; the plan's count is
approximate, "约 20 列")**, each docstring below names the original OSAP
signal/paper it stands in for:

* ``mom6m`` (OSAP ``Mom6m``, Jegadeesh 1990): 6-month momentum skipping the
  most recent month, using this repo's existing skip-convention
  (``ret_126 - ret_21``, matching ``daily_features.py``'s
  ``momentum_252_21`` construction rather than a shift-based true skip --
  chosen for internal consistency, not because it is a closer replication).
* ``mom12m`` (OSAP ``Mom12m``, Jegadeesh & Titman 1993): ``ret_252 -
  ret_21`` -- deliberately identical in formula to the existing
  ``momentum_252_21`` daily27 column (the plan: "= 现有 momentum_252_21,
  保留以对齐" -- kept so the screen can see the two libraries agree on
  this one factor).
* ``mom12m_offseason`` (OSAP ``Mom12mOffSeason``, Heston & Sadka 2008):
  mean of ``month_return(2..11)`` -- the trailing year excluding both the
  most recent month (reversal contamination) and the 12-months-ago
  "seasonal" month.
* ``momseason_short`` (OSAP ``MomSeasonShort``): ``month_return(12)`` --
  the same "month" one year ago.
* ``momseason_2_5`` (OSAP ``MomSeason`` family, 2-5 years ago average):
  mean of ``month_return(24, 36, 48, 60)``.
* ``momoffseason`` (OSAP ``MomOffSeason``): mean of ``month_return(1..11)``
  -- every trailing-year "month" except the 12-months-ago seasonal one.
* ``streversal`` (OSAP ``STreversal``, Jegadeesh 1990): ``-ret_21``.
* ``lrreversal`` (OSAP ``LRreversal``, De Bondt & Thaler 1985):
  ``-(ret_756 - ret_252)``.
* ``maxret`` (OSAP ``MaxRet``, Bali/Cakici/Whitelaw 2011): max daily
  return over the trailing 21 days.
* ``realizedvol_21``/``realizedvol_63`` (OSAP ``RealizedVol``): trailing
  daily-return sample stddev.
* ``idiovol_spy_63`` (OSAP ``IdioVol3F``, substituting SPY for FF3):
  identical closed-form construction to ``daily_features.py``'s
  ``idio_vol_63`` (recomputed independently here so this module has no
  import-time dependency on that module).
* ``residualmom_252_21`` (OSAP ``ResidualMomentum``, Blitz/Huij/Martens
  2011): cumulative CAPM-residual return, ``sum(residual, 252) -
  sum(residual, 21)`` (same skip-recent-month convention as
  ``momentum_252_21``), where ``residual_t = ret_1_t - beta_252,t *
  spy_ret_1_t`` and ``beta_252,t`` is that day's trailing-252-day SPY beta.
* ``dolvol_63`` (OSAP ``DolVol``): ``log(mean(close*volume, 63))``.
* ``log_price`` (OSAP ``Price``, Miller 1977): ``log(close)``.
* ``pricedelay_rsq`` (OSAP ``PriceDelayRsq``, Hou & Moskowitz 2005): the
  plan specifies a weekly regression; this daily proxy computes
  ``R2_full - R2_restricted`` over a trailing 252-day window, where
  ``R2_restricted`` regresses ``ret_1`` on contemporaneous
  ``spy_ret_1`` and ``R2_full`` adds one lagged ``spy_ret_1`` day as a
  second regressor. Both R-squareds are obtained from the closed-form
  2-regressor formula ``(ry1^2+ry2^2-2*ry1*ry2*r12)/(1-r12^2)`` (``ry1``/
  ``ry2``/``r12`` = pairwise ``CORR`` over the window), not a numerical
  least-squares solve -- exact for OLS, no library needed beyond
  DuckDB's window ``CORR``.
* ``momvol`` (OSAP ``MomVol``): ``momentum_252_21`` (recomputed
  independently) times that day's cross-sectional percentile rank of
  63-day dollar ADV (a turnover proxy -- this repo has no shares
  outstanding for a true turnover ratio). This is the one column that
  needs the *whole universe* for a given date, not just one symbol
  batch, so :func:`build_osap_price_features` returns every other column
  per symbol batch and :func:`add_momvol_cross_sectional` is applied once
  per year after every batch is concatenated (see the build script).
* ``trend_ma{3,5,10,20,50,100,200}`` (OSAP ``TrendFactor``, Han/Zhou/Zhu
  2016, a combination of moving averages): each window's simple moving
  average divided by ``close``, one column per window (7 columns).
* ``coskew_252`` (OSAP ``CoskewACX``, Ang/Chen/Xing-style): the partial
  slope of ``ret_1`` on ``spy_ret_1^2`` controlling for ``spy_ret_1``
  (systematic coskewness), via the same closed-form partial-regression
  identity used for ``pricedelay_rsq``.

**Skipped**: ``betatail_252`` (OSAP ``BetaTailRisk``) -- the plan marks
this one explicitly optional ("可选") and it is not implemented this
round; recorded in ``data/features/osap_price/MANIFEST.json``.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_MARKET_SYMBOL = "SPY"
DEFAULT_MEMORY_LIMIT = "1.2GB"

#: "Month" indices needed by the momentum-seasonality family (see module
#: docstring's month_return proxy).
_SEASON_MONTHS_OFFSEASON = tuple(range(1, 12))  # 1..11
_SEASON_MONTHS_MOM12M_OFFSEASON = tuple(range(2, 12))  # 2..11
_SEASON_MONTHS_2_5Y = (24, 36, 48, 60)
_SEASON_MONTH_SHORT = 12
_ALL_MONTH_KS = sorted({1, _SEASON_MONTH_SHORT, *_SEASON_MONTHS_OFFSEASON, *_SEASON_MONTHS_2_5Y})

TREND_MA_WINDOWS: tuple[int, ...] = (3, 5, 10, 20, 50, 100, 200)

#: Every column this module can produce per symbol batch (``momvol`` is
#: added later, cross-sectionally -- see :func:`add_momvol_cross_sectional`).
PER_SYMBOL_COLUMNS: tuple[str, ...] = (
    "mom6m",
    "mom12m",
    "mom12m_offseason",
    "momseason_short",
    "momseason_2_5",
    "momoffseason",
    "streversal",
    "lrreversal",
    "maxret",
    "realizedvol_21",
    "realizedvol_63",
    "idiovol_spy_63",
    "residualmom_252_21",
    "dolvol_63",
    "log_price",
    "pricedelay_rsq",
    "coskew_252",
    *(f"trend_ma{w}" for w in TREND_MA_WINDOWS),
    # carried through only so the build script can compute momvol once per
    # year without a second data scan; dropped before the final write.
    "_momentum_252_21",
    "_dollar_adv_63",
)
OSAP_PRICE_COLUMNS: tuple[str, ...] = (
    *(c for c in PER_SYMBOL_COLUMNS if not c.startswith("_")),
    "momvol",
)


def _month_return_expr(k: int) -> str:
    return f"LAG(close, {21 * k}) OVER w1 / NULLIF(LAG(close, {21 * (k + 1)}) OVER w1, 0) - 1.0"


def _guard(min_rows: int, expr: str) -> str:
    """DuckDB's ``ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW`` frame happily
    computes an aggregate over however many rows physically exist even
    when fewer than N are present near the start of a symbol's history --
    the same trap ``daily_features.py``'s own ``_guard`` helper documents
    and fixes. ``rn`` is each symbol's 1-indexed row number (``priced``'s
    ``ROW_NUMBER() OVER w1``, carried through to every CTE that needs it).
    """
    return f"CASE WHEN rn >= {min_rows} THEN {expr} ELSE NULL END"


def _safe_ln(expr: str) -> str:
    """DuckDB's ``LN``/``LOG`` raise ``OutOfRangeException: cannot take
    logarithm of zero`` (not a silent ``-inf``/``NULL``) -- real SIP data
    has zero-close bad ticks and zero-volume halted days, both of which
    make ``close`` or ``close * volume`` legitimately ``0`` sometimes, so
    every ``LN`` in this module must be guarded, not just windowed ones.
    """
    return f"CASE WHEN ({expr}) > 0 THEN LN({expr}) ELSE NULL END"


def build_osap_price_features(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    market_symbol: str = DEFAULT_MARKET_SYMBOL,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Every :data:`PER_SYMBOL_COLUMNS` column (``momvol`` excepted -- that
    one is cross-sectional, added later by
    :func:`add_momvol_cross_sectional`) for ``universe_symbols``, computed
    entirely with DuckDB window aggregates (``CORR``, ``STDDEV_SAMP``,
    ``SUM``, ``AVG``, ``MAX``, ``LAG``) -- the same style as
    ``daily_features.py``, no numpy/pandas rolling needed. PIT-safe: every
    window is a trailing ``ROWS BETWEEN ... PRECEDING AND CURRENT ROW``
    frame, never same-day-or-later information from another symbol.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    if not symbols:
        return pd.DataFrame(columns=["symbol", "trade_date", *PER_SYMBOL_COLUMNS])

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

        month_selects = ",\n".join(f"    {_month_return_expr(k)} AS m{k}" for k in _ALL_MONTH_KS)
        trend_ma_selects = ",\n".join(
            f"    {_guard(w, f'AVG(close) OVER w{w} / close')} AS trend_ma{w}"
            for w in TREND_MA_WINDOWS
        )
        trend_ma_passthrough = ",\n".join(f"                trend_ma{w}" for w in TREND_MA_WINDOWS)
        sized_window_defs = ",\n".join(
            f"        w{w} AS (PARTITION BY symbol ORDER BY trade_date "
            f"ROWS BETWEEN {w - 1} PRECEDING AND CURRENT ROW)"
            for w in sorted({21, 63, 252, 756, *TREND_MA_WINDOWS})
        )
        # w1 (used by every month_return(k) LAG expression) is an unbounded
        # ordered partition, not a sized rolling frame -- defined separately
        # from the ROWS BETWEEN windows above.
        window_defs = (
            f"        w1 AS (PARTITION BY symbol ORDER BY trade_date),\n{sized_window_defs}"
        )
        season_2_5_sum = " + ".join(f"m{k}" for k in _SEASON_MONTHS_2_5Y)
        offseason_sum = " + ".join(f"m{k}" for k in _SEASON_MONTHS_OFFSEASON)
        mom12m_offseason_sum = " + ".join(f"m{k}" for k in _SEASON_MONTHS_MOM12M_OFFSEASON)
        # R2_full - R2_restricted (pricedelay_rsq) and the partial slope on
        # the squared regressor (coskew_252), both via the closed-form
        # 2-regressor identity -- see the module docstring.
        pricedelay_rsq_expr = (
            "CASE WHEN (1.0 - POWER(r12_252, 2)) = 0 THEN NULL ELSE "
            "((POWER(ry1_252, 2) + POWER(ry2_252, 2) "
            "- 2 * ry1_252 * ry2_252 * r12_252) / (1.0 - POWER(r12_252, 2))) "
            "- POWER(ry1_252, 2) END"
        )
        coskew_252_expr = (
            "CASE WHEN (1.0 - POWER(r_x_sq_252, 2)) = 0 OR sx_sq_252 = 0 THEN NULL ELSE "
            "((ry_sq_252 - ry1_252 * r_x_sq_252) / (1.0 - POWER(r_x_sq_252, 2))) "
            "* (sy_252 / sx_sq_252) END"
        )
        outer_window_defs = (
            "        w21 AS (PARTITION BY symbol ORDER BY trade_date "
            "ROWS BETWEEN 20 PRECEDING AND CURRENT ROW),\n"
            "        w252 AS (PARTITION BY symbol ORDER BY trade_date "
            "ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)"
        )
        # Warm-up NULL guards (see _guard docstring): ret_1-based windows need
        # min_rows = window_size + 1 (ret_1 itself is NULL on each symbol's
        # first row); close/volume-based windows need min_rows = window_size.
        maxret_expr = _guard(22, "MAX(ret_1) OVER w21")
        realizedvol_21_expr = _guard(22, "STDDEV_SAMP(ret_1) OVER w21")
        realizedvol_63_expr = _guard(64, "STDDEV_SAMP(ret_1) OVER w63")
        idiovol_spy_63_expr = _guard(
            64,
            "STDDEV_SAMP(ret_1) OVER w63 * SQRT(1.0 - POWER("
            "COALESCE(CORR(ret_1, mkt_ret_1) OVER w63, 0.0), 2))",
        )
        beta_252_expr = _guard(253, "REGR_SLOPE(ret_1, mkt_ret_1) OVER w252")
        # NB: DuckDB's LOG(x) is base-10; LN(x) is natural log -- np.log()
        # (numpy, and the OSAP/academic "log dollar volume"/"log price"
        # convention) means natural log, so every log here must be LN, not
        # LOG, to match both the tests and the documented construction.
        dolvol_63_expr = _guard(63, _safe_ln("AVG(close * volume) OVER w63"))
        ry1_252_expr = _guard(253, "CORR(ret_1, mkt_ret_1) OVER w252")
        ry2_252_expr = _guard(253, "CORR(ret_1, mkt_ret_1_lag1) OVER w252")
        r12_252_expr = _guard(253, "CORR(mkt_ret_1, mkt_ret_1_lag1) OVER w252")
        ry_sq_252_expr = _guard(253, "CORR(ret_1, mkt_ret_1_sq) OVER w252")
        r_x_sq_252_expr = _guard(253, "CORR(mkt_ret_1, mkt_ret_1_sq) OVER w252")
        sy_252_expr = _guard(253, "STDDEV_SAMP(ret_1) OVER w252")
        sx_sq_252_expr = _guard(253, "STDDEV_SAMP(mkt_ret_1_sq) OVER w252")
        # residualmom_252_21's two SUM terms each need every row inside their
        # own window to have a valid (non-guarded) beta_252, not just the
        # window to be full: the earliest row in a w21/w252 window ending at
        # rn is rn-20/rn-251, so min_rows = 253 + 20 = 273 / 253 + 251 = 504.
        residualmom_w252_expr = _guard(504, "SUM(ret_1 - beta_252 * mkt_ret_1) OVER w252")
        residualmom_w21_expr = _guard(273, "SUM(ret_1 - beta_252 * mkt_ret_1) OVER w21")

        query = f"""
            WITH raw AS (
                -- Real SIP data has occasional zero-close bad ticks. DuckDB's
                -- float division silently returns +/-inf/nan for x/0 (unlike
                -- LN, which raises) -- nulling a non-positive close here, not
                -- downstream, means every ret_1 touching that row (as either
                -- numerator or LAG denominator) becomes a clean NULL instead
                -- of a silently-propagating inf/nan.
                SELECT symbol, timestamp, CASE WHEN close > 0 THEN close ELSE NULL END AS close,
                       volume
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
                SELECT trade_date, ret_1 AS mkt_ret_1
                FROM priced WHERE symbol = '{market_symbol}'
            ),
            joined AS (
                SELECT
                    priced.*,
                    market.mkt_ret_1,
                    market.mkt_ret_1 * market.mkt_ret_1 AS mkt_ret_1_sq,
                    LAG(market.mkt_ret_1)
                        OVER (PARTITION BY priced.symbol ORDER BY priced.trade_date)
                        AS mkt_ret_1_lag1
                FROM priced
                JOIN market USING (trade_date)
                WHERE priced.symbol != '{market_symbol}'
            ),
            windowed AS (
                SELECT
                    symbol, trade_date, close, ret_1, mkt_ret_1, rn,
{month_selects},
                    {maxret_expr} AS maxret,
                    {realizedvol_21_expr} AS realizedvol_21,
                    {realizedvol_63_expr} AS realizedvol_63,
                    {idiovol_spy_63_expr} AS idiovol_spy_63,
                    {beta_252_expr} AS beta_252,
                    {dolvol_63_expr} AS dolvol_63,
                    {_safe_ln("close")} AS log_price,
{trend_ma_selects},
                    -- partial-regression closed forms for pricedelay_rsq and coskew_252
                    {ry1_252_expr} AS ry1_252,
                    {ry2_252_expr} AS ry2_252,
                    {r12_252_expr} AS r12_252,
                    {ry_sq_252_expr} AS ry_sq_252,
                    {r_x_sq_252_expr} AS r_x_sq_252,
                    {sy_252_expr} AS sy_252,
                    {sx_sq_252_expr} AS sx_sq_252
                FROM joined
                WINDOW
{window_defs}
            )
            SELECT
                symbol,
                trade_date,
                close,
                m{_SEASON_MONTH_SHORT} AS momseason_short,
                ({season_2_5_sum}) / {len(_SEASON_MONTHS_2_5Y)}.0 AS momseason_2_5,
                ({offseason_sum}) / {len(_SEASON_MONTHS_OFFSEASON)}.0 AS momoffseason,
                ({mom12m_offseason_sum}) / {len(_SEASON_MONTHS_MOM12M_OFFSEASON)}.0
                    AS mom12m_offseason,
                maxret, realizedvol_21, realizedvol_63, idiovol_spy_63, dolvol_63, log_price,
{trend_ma_passthrough},
                (
                    {residualmom_w252_expr}
                    - {residualmom_w21_expr}
                ) AS residualmom_252_21,
                {pricedelay_rsq_expr} AS pricedelay_rsq,
                {coskew_252_expr} AS coskew_252
            FROM windowed
            WINDOW
{outer_window_defs}
            ORDER BY symbol, trade_date
        """
        frame = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    # ret_21/126/252/756 are plain per-symbol shifts of a column already in
    # the result (close, sorted by symbol,trade_date) -- simpler and
    # shorter done here than as four more LAG expressions in the query.
    by_symbol_close = frame.groupby("symbol")["close"]
    ret_21 = frame["close"] / by_symbol_close.shift(21) - 1.0
    ret_126 = frame["close"] / by_symbol_close.shift(126) - 1.0
    ret_252 = frame["close"] / by_symbol_close.shift(252) - 1.0
    ret_756 = frame["close"] / by_symbol_close.shift(756) - 1.0
    frame["mom6m"] = ret_126 - ret_21
    frame["mom12m"] = ret_252 - ret_21
    frame["streversal"] = -ret_21
    frame["lrreversal"] = -(ret_756 - ret_252)
    # carried through for the cross-sectional momvol finishing step.
    frame["_momentum_252_21"] = frame["mom12m"]
    frame["_dollar_adv_63"] = frame["dolvol_63"]  # log dollar volume is a fine ADV proxy
    # frame[ordered] below selects only these columns, so `close` (needed
    # above but not part of the published table) is dropped implicitly.
    ordered = ["symbol", "trade_date", *PER_SYMBOL_COLUMNS]
    return frame[ordered]


def add_momvol_cross_sectional(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``momvol`` (OSAP ``MomVol``): ``momentum_252_21`` times that
    day's cross-sectional percentile rank of 63-day dollar ADV. Needs the
    *entire* universe for each ``trade_date`` -- call this once per year
    after every symbol batch from :func:`build_osap_price_features` has
    been concatenated, not per batch. Drops the two ``_``-prefixed helper
    columns afterward.
    """
    turnover_rank = frame.groupby("trade_date")["_dollar_adv_63"].rank(pct=True)
    frame = frame.copy()
    frame["momvol"] = frame["_momentum_252_21"] * turnover_rank
    return frame.drop(columns=["_momentum_252_21", "_dollar_adv_63"])
