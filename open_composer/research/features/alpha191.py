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
``035`` (need ``DECAYLINEAR``, not implemented this round), ``030``
(the fetched source itself marks this one "unfinished/TODO"), ``033``
(needs a turnover-rate ``turn`` column this repo does not have). Ids
041-191 outside this round's US-17 additions (below) were never fetched or
verified.

**Step 15 Track A addition (2026-09-14): 14 of the 15 "US-surviving"
ids added -- ``{039, 046, 049, 054, 063, 071, 073, 084, 086, 123, 155,
161, 184, 190}``.** Du/Walter/Ulrich (arXiv 2601.06499) found 17 GTJA
Alpha191 ids survive a double-selection-LASSO screen against 151
fundamental factors in the S&P 500 (2002-2022, monthly, t>2): ``046,
084, 073, 123, 049, 071, 184, 155, 054, 181, 161, 190, 039, 015, 063,
001, 086`` -- ``001``/``015`` were already implemented; this round adds
14 of the remaining 15. Formula text cross-checked against 3 independent
sources (BigQuant wiki, ChannelCMT/OFO wiki, a kangchihlun gist), plus
the already-fetched Daic115 reference, before writing any code -- see
``reports/harness/source_cards/step15_us_alpha17_formulas.jsonl``. The
new ``_panel_ops.decay_linear`` primitive implements ``DECAYLINEAR``
(needed by 039/073), used here for the first time.

Three more corrections/interpretation choices, same "quoted text over a
possibly-buggy fetched code sample" discipline as the original round's
three (see above):

* ``gtja073``/``gtja086``: the Daic115 fetch (retrieved this round via an
  automated fetch-and-summarize tool, not a raw file read) contained two
  real transcription errors caught by cross-referencing the two
  independent formula-text sources that agree with each other: 073's
  outer ``* -1`` was applied to only one of its two terms (should
  distribute over both, i.e. the correct form is ``RANK(...) -
  TSRANK(...)``, not ``-TSRANK(...) - RANK(...)``), and 086's nested
  ``IF/ELIF/ELSE`` branches for ``-1``/``1``/the close-diff term were
  swapped relative to its own quoted formula. Both ids are implemented
  here from the verified formula text directly, not from that fetch's
  code.
* ``gtja054``: the original formula's ``STD(ABS(CLOSE-OPEN)[, window])``
  term has no consistent explicit window across sources (one source
  omits it, another gives 5, a third implies 10 by reusing the formula's
  only other explicit window). This module uses window ``10`` (tied to
  the formula's ``CORR(CLOSE,OPEN,10)`` window) -- a disclosed
  interpretation choice, not a verified single answer; see source card
  ``gtja191_alpha054_std_window_ambiguity``.

**Not implemented -- ``gtja181`` is genuinely blocked, not merely
deferred**: its formula needs a ``BANCHMARKINDEXCLOSE`` (benchmark index
close) input this module's ``PANEL_FIELDS`` do not carry, and that
variable's own semantics are ambiguous across every source found (a
literal raw index price level is dimensionally inconsistent with the
return-scale terms it is added to and divided against; the only source
with a working implementation silently redefines it as the
cross-sectional mean of every stock's own daily return instead of an
actual index series -- an unstated modeling substitution, not a literal
transcription). Two of three independent sources decline to implement
this id at all. Encoding either guessed interpretation would silently
feed every downstream screen/backtest with an unverified formula --
judged not worth the risk this round; see source card
``gtja191_alpha181_benchmarkindexclose_blocked`` for the full reasoning.
Reported as not-implemented (not silently dropped from the US-17 table)
in the Step 15 report chapter.

None of the 14 new ids has a ``gtja017``-style (``rank ** delta``)
numerically degenerate sub-expression -- checked individually; the one
formula with a data-dependent exponent (``gtja190``'s
``(CLOSE/DELAY(CLOSE,19)) ** (1/20)``) uses a *fixed* small exponent
(never a raw price delta), which is bounded and safe for any positive
base. Every new id's stored column is still wrapped in
``ops.replace_inf_with_nan`` as blanket insurance against a literal
division-by-zero on a bad-tick (zero-close/zero-volume) row, matching
the risk this repo's ``osap_price.py`` module already documents for this
same SIP daily archive.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
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
    39,
    46,
    49,
    54,
    63,
    71,
    73,
    84,
    86,
    123,
    155,
    161,
    184,
    190,
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
    40: "fetched but not independently re-verified this round",
    181: (
        "Step 15 Track A: needs a BANCHMARKINDEXCLOSE (benchmark index close) "
        "input this module's PANEL_FIELDS do not carry, and that variable's "
        "semantics are ambiguous across every source found (raw index price "
        "level vs. cross-sectional mean return -- dimensionally inconsistent "
        "either way with how the formula uses it); 2 of 3 independent open "
        "references decline to implement this id at all. Blocked, not "
        "guessed -- see source card gtja191_alpha181_benchmarkindexclose_blocked."
    ),
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

    # --- Step 15 Track A: US-17-surviving ids (see module docstring) ---

    # gtja039: (rank(decaylinear(corr(vwap*0.3+open*0.7, sum(mean(volume,180),37), 14), 12))
    #           - rank(decaylinear(delta(close,2), 8))) -- outer *-1 of the quoted
    #           formula already distributed into this sign (see module docstring).
    vol_sum_mean_180_37 = ops.ts_sum(ops.sma(volume, 180), 37)
    corr_039 = ops.replace_inf_with_nan(
        ops.correlation(vwap * 0.3 + open_ * 0.7, vol_sum_mean_180_37, 14)
    )
    alphas["gtja039"] = ops.rank(ops.decay_linear(corr_039, 12)) - ops.rank(
        ops.decay_linear(ops.delta(close, 2), 8)
    )

    # gtja046: (mean(close,3)+mean(close,6)+mean(close,12)+mean(close,24)) / (4*close)
    mean_stack_046 = ops.sma(close, 3) + ops.sma(close, 6) + ops.sma(close, 12) + ops.sma(close, 24)
    alphas["gtja046"] = mean_stack_046 / (4.0 * close)

    # gtja049: sum(term1,12) / (sum(term1,12)+sum(term2,12)), where mx =
    #   max(abs(high-delay(high,1)), abs(low-delay(low,1))):
    #   term1 = (high+low)>=(delay(high,1)+delay(low,1)) ? 0 : mx
    #   term2 = (high+low)<=(delay(high,1)+delay(low,1)) ? 0 : mx
    delay_high1 = ops.delay(high, 1)
    delay_low1 = ops.delay(low, 1)
    up_regime_049 = (high + low) >= (delay_high1 + delay_low1)
    down_regime_049 = (high + low) <= (delay_high1 + delay_low1)
    max_move_049 = np.maximum((high - delay_high1).abs(), (low - delay_low1).abs())
    term1_049 = max_move_049.where(~up_regime_049, 0.0)
    term2_049 = max_move_049.where(~down_regime_049, 0.0)
    num_049 = ops.ts_sum(term1_049, 12)
    den_049 = num_049 + ops.ts_sum(term2_049, 12)
    alphas["gtja049"] = ops.replace_inf_with_nan(num_049 / den_049)

    # gtja054: -1 * rank((std(abs(close-open), 10) + (close-open)) + corr(close,open,10))
    # -- STD window is unspecified in the original formula text; this module uses 10
    # (tied to the formula's only other explicit window), a disclosed interpretation
    # choice -- see module docstring and source card gtja191_alpha054_std_window_ambiguity.
    diff_oc_054 = close - open_
    std_term_054 = ops.stddev(diff_oc_054.abs(), 10)
    corr_term_054 = ops.replace_inf_with_nan(ops.correlation(close, open_, 10))
    alphas["gtja054"] = -1 * ops.rank(std_term_054 + diff_oc_054 + corr_term_054)

    # gtja063: SMA(max(close-delay(close,1),0),6,1) / SMA(abs(close-delay(close,1)),6,1) * 100
    diff_c_063 = close - delay1
    up_part_063 = diff_c_063.clip(lower=0.0)
    alphas["gtja063"] = (
        ops.recursive_ewm(up_part_063, 6, 1) / ops.recursive_ewm(diff_c_063.abs(), 6, 1) * 100
    )

    # gtja071: (close - mean(close,24)) / mean(close,24) * 100
    mean24_071 = ops.sma(close, 24)
    alphas["gtja071"] = (close - mean24_071) / mean24_071 * 100

    # gtja073: rank(decaylinear(corr(vwap, mean(volume,30), 4), 3))
    #          - tsrank(decaylinear(decaylinear(corr(close,volume,10), 16), 4), 5)
    # -- outer *-1 of the quoted formula distributes over BOTH terms (see module
    # docstring's correction note against the Daic115 fetch, which distributed it
    # over only one term).
    corr_close_vol_073 = ops.replace_inf_with_nan(ops.correlation(close, volume, 10))
    decay_inner_073 = ops.decay_linear(ops.decay_linear(corr_close_vol_073, 16), 4)
    tsrank_073 = ops.ts_rank(decay_inner_073, 5)
    corr_vwap_volmean_073 = ops.replace_inf_with_nan(ops.correlation(vwap, ops.sma(volume, 30), 4))
    alphas["gtja073"] = ops.rank(ops.decay_linear(corr_vwap_volmean_073, 3)) - tsrank_073

    # gtja084: sum((close>delay(close,1) ? volume : (close<delay(close,1) ? -volume : 0)), 20)
    signed_vol_084 = volume.where(close > delay1, (-volume).where(close < delay1, 0.0))
    signed_vol_084 = signed_vol_084.where(delay1.notna())
    alphas["gtja084"] = ops.ts_sum(signed_vol_084, 20)

    # gtja086: diff = (delay(close,20)-delay(close,10))/10 - (delay(close,10)-close)/10;
    #   diff>0.25 ? -1 : (diff<0 ? 1 : -1*(close-delay(close,1)))
    # -- reimplemented directly from the verified formula text, not from the fetched
    # Daic115 code (its branch logic for this id was inverted, see module docstring).
    delay20_086 = ops.delay(close, 20)
    delay10_086 = ops.delay(close, 10)
    diff_086 = (delay20_086 - delay10_086) / 10.0 - (delay10_086 - close) / 10.0
    close_diff_term_086 = -1.0 * (close - delay1)
    cond_neg1_086 = diff_086 > 0.25
    cond_pos1_086 = diff_086 < 0
    result_086 = close_diff_term_086.where(~cond_neg1_086, -1.0).where(~cond_pos1_086, 1.0)
    alphas["gtja086"] = result_086.where(diff_086.notna() & delay1.notna())

    # gtja123: (rank(corr(sum((high+low)/2,20), sum(mean(volume,60),20), 9))
    #           < rank(corr(low,volume,6))) * -1
    # -- boolean-cast result masked to NaN (not a fabricated 0) wherever either input
    # rank is itself NaN, matching this file's existing gtja003-style convention.
    corr_a_123 = ops.replace_inf_with_nan(
        ops.correlation(ops.ts_sum((high + low) / 2.0, 20), ops.ts_sum(ops.sma(volume, 60), 20), 9)
    )
    corr_b_123 = ops.replace_inf_with_nan(ops.correlation(low, volume, 6))
    rank_a_123 = ops.rank(corr_a_123)
    rank_b_123 = ops.rank(corr_b_123)
    raw_123 = (rank_a_123 < rank_b_123).astype(float) * -1.0
    alphas["gtja123"] = raw_123.where(rank_a_123.notna() & rank_b_123.notna())

    # gtja155: SMA(volume,13,2) - SMA(volume,27,2) - SMA(SMA(volume,13,2)-SMA(volume,27,2),10,2)
    ema13_155 = ops.recursive_ewm(volume, 13, 2)
    ema27_155 = ops.recursive_ewm(volume, 27, 2)
    macd_like_155 = ema13_155 - ema27_155
    alphas["gtja155"] = macd_like_155 - ops.recursive_ewm(macd_like_155, 10, 2)

    # gtja161: mean(max(max(high-low, abs(delay(close,1)-high)), abs(delay(close,1)-low)), 12)
    true_range_161 = np.maximum(np.maximum(high - low, (delay1 - high).abs()), (delay1 - low).abs())
    alphas["gtja161"] = ops.sma(true_range_161, 12)

    # gtja184: rank(corr(delay(open-close,1), close, 200)) + rank(open-close)
    corr_184 = ops.replace_inf_with_nan(ops.correlation(ops.delay(open_ - close, 1), close, 200))
    alphas["gtja184"] = ops.rank(corr_184) + ops.rank(open_ - close)

    # gtja190: log((count(a>b,20)-1) * sumif((a-b)^2,20,a<b)
    #              / (count(a<b,20) * sumif((a-b)^2,20,a>b)))
    #   where a = close/delay(close,1)-1, b = (close/delay(close,19))^(1/20)-1
    # -- validity-masked to NaN (not a fabricated 0/False) wherever a or b is itself
    # NaN, matching this file's existing gtja003-style warm-up convention, so a
    # rolling 20-window's count/sumif is NaN whenever it includes an undefined day.
    part1_190 = close / delay1 - 1.0
    part2_190 = (close / ops.delay(close, 19)) ** (1.0 / 20.0) - 1.0
    sq_diff_190 = (part1_190 - part2_190) ** 2
    valid_190 = part1_190.notna() & part2_190.notna()
    up_190 = part1_190 > part2_190
    down_190 = part1_190 < part2_190
    up_indicator_190 = up_190.astype(float).where(valid_190)
    down_indicator_190 = down_190.astype(float).where(valid_190)
    sumsq_up_terms_190 = sq_diff_190.where(up_190, 0.0).where(valid_190)
    sumsq_down_terms_190 = sq_diff_190.where(down_190, 0.0).where(valid_190)
    n_up_190 = ops.ts_sum(up_indicator_190, 20)
    n_down_190 = ops.ts_sum(down_indicator_190, 20)
    sumsq_up_190 = ops.ts_sum(sumsq_up_terms_190, 20)
    sumsq_down_190 = ops.ts_sum(sumsq_down_terms_190, 20)
    ratio_190 = ops.replace_inf_with_nan(
        (n_up_190 - 1.0) * sumsq_down_190 / (n_down_190 * sumsq_up_190)
    )
    alphas["gtja190"] = ops.safe_log(ratio_190)

    # Blanket safety net for every Step 15 Track A id (module docstring): guard
    # against a literal division-by-zero on a bad-tick (zero-close/zero-volume) SIP
    # row producing an unbounded inf, without altering any genuine finite value.
    for _new_id in (39, 46, 49, 54, 63, 71, 73, 84, 86, 123, 155, 161, 184, 190):
        _col = f"gtja{_new_id:03d}"
        alphas[_col] = ops.replace_inf_with_nan(alphas[_col])

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
