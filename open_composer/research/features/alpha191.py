"""Step 13-F 3.2: Guotai Junan (GTJA) Alpha191 (2017 sell-side research
report), spot-verified subset.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.2. Same fallback reasoning as ``alpha101.py``: ``py-alpha-lib``
does not run in this project's Python 3.11 venv, so this is a pandas
implementation of a subset of the 191 formulas.

**Implemented: 20 of 191 ids** -- ``{1,2,3,6,7,8,9,11,12,13,14,15,16,17,18,
19,20,24,27,32}``, chosen because they need only ``open, high, low, close,
volume, vwap`` (no turnover-rate ``turn`` column, no multi-factor
regression, no ``DECAYLINEAR``). Formula text was fetched verbatim from
``Daic115/alpha191/alpha191.py`` (no LICENSE file found -- not vendored,
used only to confirm each formula's docstring-quoted original report text;
see the ``gtja_alpha191_verbatim_formulas_001_040`` source card).

**Three deliberate corrections against the fetched reference** (the
reference code's own behavior did not match its own quoted formula text --
this module follows the quoted text, not the reference's code):

* ``alpha_008``: the reference negates only the ``(HIGH+LOW)`` term before
  differencing (``diff(-0.1*(H+L) + 0.8*VWAP)``), which flips the sign on
  the ``VWAP`` term relative to the quoted formula
  ``RANK(DELTA(...,4)*-1)`` (negate the *whole* bracket, then take delta,
  then the ``*-1`` is already inside -- equivalently: negate the finished
  delta, not one half of its input). This module computes
  ``rank(-1 * delta(0.1*(high+low) + 0.8*vwap, 4))``.
* ``alpha_019``/``alpha_020``: the reference defaults to computing on
  ``vwap`` (``use_vwap=True``), but both quoted original formulas say
  ``CLOSE`` explicitly (``alpha_020``'s own docstring: "(CLOSE-DELAY(CLOSE,
  6))/DELAY(CLOSE,6)*100"). This module uses ``close``.
* ``alpha_029``: the reference multiplies by ``log(volume)``, but the
  quoted formula says ``*VOLUME`` (no log). This module uses raw ``volume``.
* ``alpha_009``/``alpha_024``/``alpha_027``: the report's recursive
  ``SMA(X,N,M)`` operator is implemented here as
  ``_panel_ops.recursive_ewm`` with ``adjust=False`` (exact recursive
  definition); see that function's docstring for why this differs from
  the fetched reference's plain ``.ewm(alpha=...).mean()`` (default
  ``adjust=True``).

Skipped from the fetched 001-040 block, with reasons (see
``data/features/alpha191/MANIFEST.json``): ``004`` (a NaN-carrying
conditional-regime signal the fetched source itself flags as unusual, not
worth the fidelity risk this round), ``005``/``010``/``021``-``023``/
``026``/``028``/``031``/``034``/``036``-``038``/``040`` (not independently
re-verified this round -- fetched but not yet implemented), ``025``/
``035``/``039`` (need ``DECAYLINEAR``, not implemented this round), ``030``
(the fetched source itself marks this one "unfinished/TODO"), ``033``
(needs a turnover-rate ``turn`` column this repo does not have). Ids
041-191 (151 ids) were never fetched or verified this round.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from open_composer.research.features import _panel_ops as ops

DEFAULT_MEMORY_LIMIT = "1.2GB"
PANEL_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "vwap")

IMPLEMENTED_IDS: tuple[int, ...] = (
    1,
    2,
    3,
    6,
    7,
    8,
    9,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    24,
    27,
    32,
)
ALPHA191_COLUMNS: tuple[str, ...] = tuple(f"gtja{i:03d}" for i in IMPLEMENTED_IDS)

#: ids fetched from the reference (1-40) but not implemented, with reasons.
_FETCHED_NOT_IMPLEMENTED: dict[int, str] = {
    4: "NaN-carrying conditional regime signal; not spot-verified enough to trust this round",
    5: "fetched but not independently re-verified this round",
    10: "fetched but not independently re-verified this round",
    21: "needs the same rolling-OLS-slope machinery as alpha158 BETA; not implemented this round",
    22: "fetched but not independently re-verified this round",
    23: "fetched but not independently re-verified this round",
    25: "needs DECAYLINEAR, not implemented this round",
    26: "fetched but not independently re-verified this round (230-day corr window)",
    28: "fetched but not independently re-verified this round",
    30: "reference source itself marks this formula unfinished/TODO",
    31: "fetched but not independently re-verified this round",
    33: "needs a turnover-rate ('turn') column this repo does not have",
    34: "fetched but not independently re-verified this round",
    35: "needs DECAYLINEAR, not implemented this round",
    36: "fetched but not independently re-verified this round",
    37: "fetched but not independently re-verified this round",
    38: "fetched but not independently re-verified this round",
    39: "needs DECAYLINEAR, not implemented this round",
    40: "fetched but not independently re-verified this round",
}


def _pivot_wide(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    return frame.pivot(index="trade_date", columns="symbol", values=field)


def compute_alpha191(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute the 20 implemented Alpha191 columns for an in-memory OHLCV+
    vwap frame (``symbol, trade_date, open, high, low, close, volume,
    vwap``). Returns long-format ``symbol, trade_date`` plus
    :data:`ALPHA191_COLUMNS`.
    """
    required = {"symbol", "trade_date", *PANEL_FIELDS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"alpha191 input frame missing columns: {sorted(missing)}")

    wide = {field: _pivot_wide(frame, field) for field in PANEL_FIELDS}
    open_, high, low, close, volume, vwap = (wide[f] for f in PANEL_FIELDS)
    delay1 = close.shift(1)

    alphas: dict[str, pd.DataFrame] = {}

    # gtja001: -1 * correlation(rank(delta(log(volume),1)), rank((close-open)/open), 6)
    alphas["gtja001"] = -1 * ops.replace_inf_with_nan(
        ops.correlation(
            ops.rank(ops.delta(ops.safe_log(volume), 1)), ops.rank((close - open_) / open_), 6
        )
    )

    # gtja002: -1 * delta(((close-low)-(high-close))/(high-low), 1)
    alphas["gtja002"] = -1 * ops.delta(((close - low) - (high - close)) / (high - low), 1)

    # gtja003: sum(close==delay1?0:close-(close>delay1?min(low,delay1):max(high,delay1)), 6)
    # A row with no delay1 (a symbol's first day) has an undefined comparison,
    # not a "close == delay1" tie -- masked to NaN rather than falling through
    # to a fabricated 0, matching this repo's warm-up convention elsewhere.
    min_low_delay1 = low.where(low <= delay1, delay1)
    max_high_delay1 = high.where(high >= delay1, delay1)
    term_up = close - min_low_delay1
    term_down = close - max_high_delay1
    term = term_up.where(close > delay1, term_down.where(close < delay1, 0.0))
    term = term.where(delay1.notna())
    alphas["gtja003"] = ops.ts_sum(term, 6)

    # gtja006: -1 * rank(sign(delta(open*0.85 + high*0.15, 4)))
    alphas["gtja006"] = -1 * ops.rank(ops.sign(ops.delta(open_ * 0.85 + high * 0.15, 4)))

    # gtja007: (rank(max(vwap-close,3)) + rank(min(vwap-close,3))) * rank(delta(volume,3))
    vwap_minus_close = vwap - close
    alphas["gtja007"] = (
        ops.rank(ops.ts_max(vwap_minus_close, 3)) + ops.rank(ops.ts_min(vwap_minus_close, 3))
    ) * ops.rank(ops.delta(volume, 3))

    # gtja008: rank(-1 * delta(0.1*(high+low) + 0.8*vwap, 4)) -- see module docstring correction
    alphas["gtja008"] = ops.rank(-1 * ops.delta(0.1 * (high + low) + 0.8 * vwap, 4))

    # gtja009: SMA(((high+low)/2 - (delay(high,1)+delay(low,1))/2)*(high-low)/volume, 7, 2)
    inner_009 = (
        ((high + low) / 2 - (ops.delay(high, 1) + ops.delay(low, 1)) / 2) * (high - low) / volume
    )
    alphas["gtja009"] = ops.recursive_ewm(inner_009, 7, 2)

    # gtja011: sum(((2*close-low-high)/(high-low))*volume, 6)
    alphas["gtja011"] = ops.ts_sum(((2 * close - low - high) / (high - low)) * volume, 6)

    # gtja012: rank(open - sum(vwap,10)/10) * (-1 * abs(rank(close-vwap)))
    alphas["gtja012"] = ops.rank(open_ - ops.ts_sum(vwap, 10) / 10.0) * (
        -1 * ops.rank(close - vwap).abs()
    )

    # gtja013: (high*low)**0.5 - vwap
    alphas["gtja013"] = (high * low) ** 0.5 - vwap

    # gtja014: close - delay(close,5)
    alphas["gtja014"] = close - ops.delay(close, 5)

    # gtja015: open/delay(close,1) - 1
    alphas["gtja015"] = open_ / delay1 - 1

    # gtja016: -1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5)
    alphas["gtja016"] = -1 * ops.ts_max(
        ops.rank(ops.replace_inf_with_nan(ops.correlation(ops.rank(volume), ops.rank(vwap), 5))), 5
    )

    # gtja017: rank(vwap - ts_max(vwap,15)) ** delta(close,5)
    alphas["gtja017"] = ops.rank(vwap - ops.ts_max(vwap, 15)) ** ops.delta(close, 5)

    # gtja018: close / delay(close,5)
    alphas["gtja018"] = close / ops.delay(close, 5)

    # gtja019 (corrected to CLOSE, see module docstring):
    # close<delay(close,5) ? (close-delay5)/delay5 : (close-delay5)/close
    delay5 = ops.delay(close, 5)
    alphas["gtja019"] = ((close - delay5) / delay5).where(close < delay5, (close - delay5) / close)

    # gtja020 (corrected to CLOSE): (close-delay(close,6))/delay(close,6)*100
    delay6 = ops.delay(close, 6)
    alphas["gtja020"] = (close - delay6) / delay6 * 100

    # gtja024: SMA(close - delay(close,5), 5, 1)
    alphas["gtja024"] = ops.recursive_ewm(close - ops.delay(close, 5), 5, 1)

    # gtja027: SMA(((close/delay(close,3)-1)*100) + ((close/delay(close,6)-1)*100), 12, 1)
    short_term = (close / ops.delay(close, 3) - 1) * 100
    long_term = (close / ops.delay(close, 6) - 1) * 100
    alphas["gtja027"] = ops.recursive_ewm(short_term + long_term, 12, 1)

    # gtja032: -1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3)
    corr_hv = ops.replace_inf_with_nan(ops.correlation(ops.rank(high), ops.rank(volume), 3))
    alphas["gtja032"] = -1 * ops.ts_sum(ops.rank(corr_hv), 3)

    frames = []
    for name in ALPHA191_COLUMNS:
        melted = (
            alphas[name]
            .reset_index()
            .melt(id_vars="trade_date", var_name="symbol", value_name=name)
        )
        frames.append(melted.set_index(["symbol", "trade_date"]))
    combined = pd.concat(frames, axis=1).reset_index()
    combined[list(ALPHA191_COLUMNS)] = combined[list(ALPHA191_COLUMNS)].replace(
        [float("inf"), float("-inf")], float("nan")
    )
    return (
        combined[["symbol", "trade_date", *ALPHA191_COLUMNS]]
        .sort_values(["symbol", "trade_date"])
        .reset_index(drop=True)
    )


def build_alpha191_features(
    daily_glob: str | list[str],
    universe_symbols: list[str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Load OHLCV+vwap rows for ``universe_symbols`` from ``daily_glob``
    and compute :func:`compute_alpha191`. Mirrors ``alpha101.py``'s
    DuckDB-load / pandas-compute split and per-symbol-batch convention.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    empty_columns = ["symbol", "trade_date", *ALPHA191_COLUMNS]
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
    return compute_alpha191(raw)


def alpha191_skipped_ids(all_ids: range = range(1, 192)) -> list[dict[str, str]]:
    """The MANIFEST ``skipped`` list: every id in 1..191 not implemented,
    with a specific reason where the id was at least fetched (1-40), and a
    generic "not fetched this round" reason for 41-191.
    """
    implemented = set(IMPLEMENTED_IDS)
    skipped = []
    for i in all_ids:
        if i in implemented:
            continue
        reason = _FETCHED_NOT_IMPLEMENTED.get(
            i, "outside the fetched 001-040 block; not fetched or verified this round"
        )
        skipped.append({"id": f"gtja{i:03d}", "reason": reason})
    return skipped
