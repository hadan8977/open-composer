"""H-20260928-20 recent-regime optimization: variant search over the two
batch-2 candidates the owner liked on 2026-09-28 (EOM_REVERSAL_SPY,
FRONT_RUN_SECTOR_TOP2), for `scripts/screen_batch.py --batch
h20260928_20_recent_opt --iteration h20260928_20_recent_regime_opt`.

Imports and reuses, unedited, the pure helper functions from
`scripts/screen_batches/h20260928_05_batch2.py` (`SECTOR_ETFS`,
`_is_month_end`, `_fourth_friday`, `_nearest_trading_day_at_or_before`,
`_holding_month_and_year`, `month_end_signal_dates`) rather than
re-implementing them -- see that module's own docstring for the primary
source citations for the two base rules. This module adds no new base rule;
every weight function here is a parameterized generalization of
`w_eom_reversal_spy` (E family) or `w_front_run_sector_top2` (S family), or a
combination of both (C family), verified in
`tests/test_screen_recent_opt_rules.py` to reproduce the batch-2 base weights
exactly at `formation_sessions=None, threshold=0.0` (E family) / `top_n=2,
shift=1, avg_years=1` (S family) on both synthetic and the real panel.

Candidates (20 gated; see `candidate-manifest.json` for the owner's literal
replacement rule and per-variant source grounding)
----------------------------------------------------------------------------
E family (base E0 + 7 variants), all long SPY (or QQQ for E4) or cash:
  E0             base: 4th-Friday-to-month-end return < 0 -> long next month.
  E1 / E2        formation window = last 5 / 10 sessions instead of the 4th
                 Friday.
  E3             entry threshold < -1% instead of < 0%.
  E4             QQQ instead of SPY.
  E5 / E6        hold only the first 10 sessions of the next month, or only
                 until the next month's 4th Friday, then force cash.
  E7             magnitude-scaled weight min(1, |r| / 2%).

S family (base S0 + 9 variants), sector SPDR seasonality:
  S0             base: top-2 of 9 sectors, 1-year-lag/1-month-shift score.
  S1 / S2        top-1 / top-3 instead of top-2.
  S_AVG3/S_AVG5  score = average of the same shifted window over the last 3
                 or 5 years instead of 1.
  S_SHIFT0       shift 0 (true seasonality) instead of 1 (front-running).
  S_SHIFT2       shift 2 months instead of 1.
  S_11SECTORS    11 sectors (adds XLC, XLRE) instead of 9.
  S_INVVOL       inverse-63-session-vol weights within the top-2, instead of
                 equal weight.
  S_ABSFILTER    hold a picked sector only if its trailing 12-month return is
                 positive, else that portion goes to SHY.

C family (2 combination variants):
  C1             EOM signal (SPY) decides risk-on/off; risk-on holds S0's
                 top-2 sectors instead of SPY.
  C2             50/50 capital mix of E0 and S0, reset monthly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402

SECTOR_ETFS: tuple[str, ...] = b2.SECTOR_ETFS
SECTOR_ETFS_11: tuple[str, ...] = (*b2.SECTOR_ETFS, "XLC", "XLRE")

VOL_LOOKBACK = 63
TRAILING_FILTER_LOOKBACK = 252

# --------------------------------------------------------------------------
# E family: shared formation/threshold/magnitude-scale logic
# --------------------------------------------------------------------------


def _eom_signal_return(
    hist: pd.DataFrame, symbol: str, asof: pd.Timestamp, formation_sessions: int | None
) -> float | None:
    """Return over the formation window ending at `asof`'s close.
    `formation_sessions=None` reproduces batch-2's 4th-Friday anchor exactly;
    `formation_sessions=N` anchors on the Nth-to-last trading day of the
    month (the close N-1 sessions and N calendar trading days before
    `asof`), reading only `hist.loc[:asof]` -- no look-ahead."""
    if symbol not in hist.columns:
        return None
    month_days = hist.index[(hist.index.year == asof.year) & (hist.index.month == asof.month)]
    if formation_sessions is None:
        fri = b2._fourth_friday(asof.year, asof.month)
        if fri is None:
            return None
        anchor = b2._nearest_trading_day_at_or_before(hist.index, fri)
        if anchor is None or anchor >= asof:
            return None
    else:
        if len(month_days) < formation_sessions:
            return None
        anchor = month_days[-formation_sessions]
        if anchor >= asof:
            return None
    p0 = hist[symbol].loc[anchor]
    p1 = hist[symbol].loc[asof]
    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
        return None
    return float(p1 / p0 - 1.0)


def make_eom_reversal_fn(
    *,
    symbol: str = "SPY",
    formation_sessions: int | None = None,
    threshold: float = 0.0,
    magnitude_scale: bool = False,
):
    """E-family weight function factory. `formation_sessions=None,
    threshold=0.0, magnitude_scale=False` reproduces
    `h20260928_05_batch2.w_eom_reversal_spy` exactly (E0)."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if symbol not in close.columns:
            return {}
        if not b2._is_month_end(close.index, asof):
            return {}
        hist = close.loc[:asof]
        r = _eom_signal_return(hist, symbol, asof, formation_sessions)
        if r is None or not (r < threshold):
            return {}
        if magnitude_scale:
            w = min(1.0, abs(r) / 0.02)
            return {symbol: w} if w > 0 else {}
        return {symbol: 1.0}

    return fn


def _nth_session_dates(index: pd.DatetimeIndex, n: int) -> list[pd.Timestamp]:
    s = pd.Series(index, index=index)
    out: list[pd.Timestamp] = []
    for _, group in s.groupby([index.year, index.month]):
        if len(group) >= n:
            out.append(group.iloc[n - 1])
    return sorted(out)


def _fourth_friday_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(index, index=index)
    out: list[pd.Timestamp] = []
    for (year, month), group in s.groupby([index.year, index.month]):
        fri = b2._fourth_friday(int(year), int(month))
        if fri is None:
            continue
        d = b2._nearest_trading_day_at_or_before(index, fri)
        if d is not None and group.index.min() <= d <= group.index.max():
            out.append(d)
    return sorted(out)


def eom_hold_n_sessions_signal_dates(n: int):
    def fn(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        dates = set(b2.month_end_signal_dates(index)) | set(_nth_session_dates(index, n))
        return sorted(dates)

    return fn


def eom_hold_until_fourth_friday_signal_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    dates = set(b2.month_end_signal_dates(index)) | set(_fourth_friday_dates(index))
    return sorted(dates)


# --------------------------------------------------------------------------
# S family: shared score/selection/weighting logic
# --------------------------------------------------------------------------


def _score_window_lag(
    holding_month: int, holding_year: int, lag: int, *, shift: int
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """`lag=1, shift=1` reproduces batch-2's `_score_window` exactly."""
    base = pd.Timestamp(year=holding_year - lag, month=holding_month, day=1)
    score_start = base + pd.DateOffset(months=shift)
    score_end = score_start + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    return score_start, score_end


def _window_return(
    hist: pd.DataFrame, sym: str, start: pd.Timestamp, end: pd.Timestamp
) -> float | None:
    if sym not in hist.columns:
        return None
    d_start = b2._nearest_trading_day_at_or_before(hist.index, start)
    d_end = b2._nearest_trading_day_at_or_before(hist.index, end)
    if d_start is None or d_end is None or d_start >= d_end:
        return None
    p0 = hist[sym].loc[d_start]
    p1 = hist[sym].loc[d_end]
    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
        return None
    return float(p1 / p0 - 1.0)


def _compute_scores(
    hist: pd.DataFrame,
    universe: tuple[str, ...],
    holding_month: int,
    holding_year: int,
    *,
    shift: int,
    avg_years: int,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for sym in universe:
        vals: list[float] = []
        for lag in range(1, avg_years + 1):
            start, end = _score_window_lag(holding_month, holding_year, lag, shift=shift)
            v = _window_return(hist, sym, start, end)
            if v is not None:
                vals.append(v)
        if vals:
            scores[sym] = float(np.mean(vals))
    return scores


def _trailing_return(hist: pd.DataFrame, sym: str, lookback: int) -> float | None:
    if sym not in hist.columns:
        return None
    series = hist[sym].dropna()
    if len(series) < lookback + 1:
        return None
    p0 = float(series.iloc[-lookback - 1])
    p1 = float(series.iloc[-1])
    if not np.isfinite(p0) or p0 <= 0 or not np.isfinite(p1):
        return None
    return p1 / p0 - 1.0


def _inverse_vol_weights(hist: pd.DataFrame, picks: list[str]) -> dict[str, float] | None:
    vols: dict[str, float] = {}
    for sym in picks:
        series = hist[sym].pct_change().dropna()
        if len(series) < VOL_LOOKBACK:
            return None
        v = float(series.iloc[-VOL_LOOKBACK:].std(ddof=1))
        if not np.isfinite(v) or v <= 0:
            return None
        vols[sym] = v
    inv = {sym: 1.0 / vols[sym] for sym in picks}
    total = sum(inv.values())
    return {sym: inv[sym] / total for sym in picks}


def make_sector_seasonality_fn(
    *,
    universe: tuple[str, ...] = SECTOR_ETFS,
    top_n: int = 2,
    shift: int = 1,
    avg_years: int = 1,
    inverse_vol: bool = False,
    abs_filter: bool = False,
):
    """S-family weight function factory. `universe=SECTOR_ETFS, top_n=2,
    shift=1, avg_years=1, inverse_vol=False, abs_filter=False` reproduces
    `h20260928_05_batch2.w_front_run_sector_top2` exactly (S0)."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not b2._is_month_end(close.index, asof):
            return {}
        hist = close.loc[:asof]
        holding_month, holding_year = b2._holding_month_and_year(asof)
        scores = _compute_scores(
            hist, universe, holding_month, holding_year, shift=shift, avg_years=avg_years
        )
        if len(scores) < top_n:
            return {}
        picks = sorted(scores, key=lambda sym: scores[sym], reverse=True)[:top_n]
        if abs_filter:
            picks = [
                sym
                for sym in picks
                if (r := _trailing_return(hist, sym, TRAILING_FILTER_LOOKBACK)) is not None
                and r > 0
            ]
        if not picks:
            return {}
        if inverse_vol:
            weights = _inverse_vol_weights(hist, picks)
            if weights is not None:
                return weights
        w = 1.0 / len(picks)
        return {sym: w for sym in picks}

    return fn


# --------------------------------------------------------------------------
# C family: combinations
# --------------------------------------------------------------------------


def make_c1_eom_gate_sector_top2_fn():
    """C1: EOM signal (SPY, base formation/threshold) decides risk-on/off;
    risk-on holds S0's top-2 sectors instead of SPY."""
    sector_fn = make_sector_seasonality_fn()

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not b2._is_month_end(close.index, asof):
            return {}
        if "SPY" not in close.columns:
            return {}
        hist = close.loc[:asof]
        r = _eom_signal_return(hist, "SPY", asof, None)
        if r is None or not (r < 0.0):
            return {}
        return sector_fn(close, asof)

    return fn


def make_c2_eom_sector_blend_fn():
    """C2: 50/50 capital mix of E0 and S0, reset monthly (recomputed fresh at
    every month-end signal date, same as any other freq='D' candidate)."""
    eom_fn = make_eom_reversal_fn()
    sector_fn = make_sector_seasonality_fn()

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not b2._is_month_end(close.index, asof):
            return {}
        e_w = eom_fn(close, asof) or {}
        s_w = sector_fn(close, asof) or {}
        combined: dict[str, float] = {}
        for sym, w in e_w.items():
            combined[sym] = combined.get(sym, 0.0) + 0.5 * w
        for sym, w in s_w.items():
            combined[sym] = combined.get(sym, 0.0) + 0.5 * w
        return combined

    return fn


# --------------------------------------------------------------------------
# SPECS
# --------------------------------------------------------------------------

_E_UNIVERSE = ("SPY",)
_E_QQQ_UNIVERSE = ("QQQ",)
_S_UNIVERSE = SECTOR_ETFS
_S_11_UNIVERSE = SECTOR_ETFS_11
_C_UNIVERSE = ("SPY", *SECTOR_ETFS)

SPECS: list[dict[str, object]] = [
    {
        "id": "E0",
        "name": "EOM reversal base: 4th-Friday-to-month-end SPY return < 0 -> long",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(),
    },
    {
        "id": "E1",
        "name": "EOM reversal, formation window = last 5 sessions",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(formation_sessions=5),
    },
    {
        "id": "E2",
        "name": "EOM reversal, formation window = last 10 sessions",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(formation_sessions=10),
    },
    {
        "id": "E3",
        "name": "EOM reversal, entry threshold < -1%",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(threshold=-0.01),
    },
    {
        "id": "E4",
        "name": "EOM reversal, QQQ instead of SPY",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_QQQ_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(symbol="QQQ"),
    },
    {
        "id": "E5",
        "name": "EOM reversal, hold only first 10 sessions of next month",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": eom_hold_n_sessions_signal_dates(10),
        "fn": make_eom_reversal_fn(),
    },
    {
        "id": "E6",
        "name": "EOM reversal, hold only until next month's 4th Friday",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": eom_hold_until_fourth_friday_signal_dates,
        "fn": make_eom_reversal_fn(),
    },
    {
        "id": "E7",
        "name": "EOM reversal, magnitude-scaled weight min(1, |r|/2%)",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": _E_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_eom_reversal_fn(magnitude_scale=True),
    },
    {
        "id": "S0",
        "name": "Front-run sector seasonality base: top-2 of 9, 1yr lag, 1mo shift",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(),
    },
    {
        "id": "S1",
        "name": "Front-run sector seasonality, top-1",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(top_n=1),
    },
    {
        "id": "S2",
        "name": "Front-run sector seasonality, top-3",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(top_n=3),
    },
    {
        "id": "S_AVG3",
        "name": "Front-run sector seasonality, score averaged over last 3 years",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(avg_years=3),
    },
    {
        "id": "S_AVG5",
        "name": "Front-run sector seasonality, score averaged over last 5 years",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(avg_years=5),
    },
    {
        "id": "S_SHIFT0",
        "name": "Sector seasonality, shift 0 (true seasonality, not front-running)",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(shift=0),
    },
    {
        "id": "S_SHIFT2",
        "name": "Front-run sector seasonality, shift 2 months",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(shift=2),
    },
    {
        "id": "S_11SECTORS",
        "name": "Front-run sector seasonality, 11 sectors (adds XLC, XLRE)",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_11_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(universe=_S_11_UNIVERSE),
    },
    {
        "id": "S_INVVOL",
        "name": "Front-run sector seasonality, inverse-63-session-vol weights within top-2",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(inverse_vol=True),
    },
    {
        "id": "S_ABSFILTER",
        "name": "Front-run sector seasonality, absolute trailing-12mo-return filter",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _S_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_sector_seasonality_fn(abs_filter=True),
    },
    {
        "id": "C1",
        "name": "Combination: EOM signal gates risk-on/off, risk-on holds S0 top-2 sectors",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _C_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_c1_eom_gate_sector_top2_fn(),
    },
    {
        "id": "C2",
        "name": "Combination: 50/50 capital mix of E0 and S0, reset monthly",
        "source_card": "quantpedia_front_running_sector_seasonality_variants",
        "universe": _C_UNIVERSE,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": make_c2_eom_sector_blend_fn(),
    },
]

# Sanity: every id above is unique and matches the family prefix convention.
_ids = [spec["id"] for spec in SPECS]
if len(_ids) != len(set(_ids)):
    raise ValueError(f"duplicate SPECS ids: {_ids}")
