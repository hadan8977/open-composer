"""H-20260928-02: two cross-asset defensive-trend sleeves (D1 Carlson Defense
First TAA, D2 12-month-vs-SHY absolute momentum with inverse-63-session-vol
sizing), screened for whether adding either one to S3 raises the combined
Sharpe over a volatility-matched delevered-S3 control (K2), or, failing that,
whether either is standalone-competitive with S3 (K1). See
`reports/research/iterations/h20260928_02_cross_asset_sleeve/candidate-manifest.json`
for the frozen adoption rule and
`reports/harness/source_cards/h20260928_02_cross_asset_sleeve.jsonl` for the
published-rule sources.

Both candidates are evaluated at signal dates that may fall on any of the 21
monthly rebalance-day offsets the batch harness sweeps (`screen_lane`'s
`MONTHLY_OFFSETS`), not only the true month-end. `calendar_return` below is
the generalization that lets D1's and D2's calendar-month lookbacks be
computed as of an arbitrary trading day `asof` (not just a month-end close),
using only `close.loc[:asof]` -- no look-ahead. At offset 0, `asof` is the
true month-end and D1 reproduces the exact reading
`run_h20260923_12_s3_defense_first.defense_weights` would produce that month.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from screen_lane import ScreenCandidate  # noqa: E402

DEFENSIVE: tuple[str, ...] = ("TLT", "GLD", "DBC", "UUP")
HURDLE = "BIL"
FALLBACK_D1 = "SPY"
RANK_WEIGHTS: tuple[float, ...] = (0.40, 0.30, 0.20, 0.10)
MONTHS: tuple[int, ...] = (1, 3, 6, 12)
D2_HURDLE = "SHY"
D2_MOMENTUM_MONTHS = 12
D2_VOL_LOOKBACK_SESSIONS = 63

SOURCE_CARD = "reports/harness/source_cards/h20260928_02_cross_asset_sleeve.jsonl"


def calendar_return(close: pd.DataFrame, symbol: str, asof: pd.Timestamp, months: int) -> float:
    """`close.at[asof, symbol] / close.at[start, symbol] - 1`, where `start` is
    the last trading day on or before `asof - months` calendar months. Uses
    only `close.loc[:asof]` (no look-ahead); NaN if `asof` itself is missing,
    if no trading day exists on or before the lookback start, or if the start
    price is missing/non-finite."""
    if symbol not in close.columns or asof not in close.index:
        return float("nan")
    end_price = close.at[asof, symbol]
    if not np.isfinite(end_price):
        return float("nan")
    start = asof - pd.DateOffset(months=months)
    eligible = close.index[close.index <= start]
    if len(eligible) == 0:
        return float("nan")
    start_price = close.at[eligible[-1], symbol]
    if not np.isfinite(start_price) or start_price == 0:
        return float("nan")
    return float(end_price / start_price - 1.0)


def defense_first_score(close: pd.DataFrame, symbol: str, asof: pd.Timestamp) -> float:
    """Mean of the 1/3/6/12 calendar-month returns ending at `asof`, NaN until
    all four are computable (matches
    `run_h20260923_12_s3_defense_first.momentum_score`'s blend, generalized
    from month-end-only rows to an arbitrary `asof`)."""
    values = [calendar_return(close, symbol, asof, months) for months in MONTHS]
    if any(not np.isfinite(v) for v in values):
        return float("nan")
    return float(np.mean(values))


def d1_weights_fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """Carlson's Defense First, published rules, unedited: rank TLT/GLD/DBC/UUP
    by `defense_first_score`, weight 0.40/0.30/0.20/0.10 by rank; any tier
    scoring below BIL's own score is redirected to SPY (the paper's fallback,
    not SHY -- this is D1's 'original rules' reading per the queue task,
    distinct from H-20260923-12's DF02 SHY-fallback variant)."""
    hurdle_score = defense_first_score(close, HURDLE, asof)
    scores = {sym: defense_first_score(close, sym, asof) for sym in DEFENSIVE}
    if not np.isfinite(hurdle_score) or any(not np.isfinite(v) for v in scores.values()):
        return {}
    ranked = sorted(DEFENSIVE, key=lambda sym: -scores[sym])
    weights: dict[str, float] = {}
    for sym, weight in zip(ranked, RANK_WEIGHTS, strict=True):
        target = sym if scores[sym] >= hurdle_score else FALLBACK_D1
        weights[target] = weights.get(target, 0.0) + weight
    return weights


def trailing_vol(
    close: pd.DataFrame, symbol: str, asof: pd.Timestamp, lookback_sessions: int
) -> float:
    """std(ddof=1) of daily returns over the `lookback_sessions` sessions
    ending at (and including) `asof`, using only `close.loc[:asof]`. NaN if
    fewer than `lookback_sessions` + 1 prior closes exist."""
    if symbol not in close.columns or asof not in close.index:
        return float("nan")
    pos = close.index.get_loc(asof)
    if not isinstance(pos, int) or pos + 1 < lookback_sessions + 1:
        return float("nan")
    window = close[symbol].iloc[pos - lookback_sessions + 1 : pos + 1]
    prior = close[symbol].iloc[pos - lookback_sessions : pos]
    if window.isna().any() or prior.isna().any() or (prior.to_numpy() == 0).any():
        return float("nan")
    rets = window.to_numpy() / prior.to_numpy() - 1.0
    if not np.all(np.isfinite(rets)):
        return float("nan")
    return float(np.std(rets, ddof=1))


def d2_weights_fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """TLT/GLD/DBC/UUP each held only when its trailing 12-month total return
    exceeds SHY's; held names weighted by inverse 63-session trailing daily-
    return volatility (ddof=1); otherwise (no eligible name, or any eligible
    name's volatility is non-finite/non-positive) empty -- the harness's
    lane.weights_frame then puts the entire remainder in SHY, matching
    'otherwise SHY'."""
    hurdle_return = calendar_return(close, D2_HURDLE, asof, D2_MOMENTUM_MONTHS)
    if not np.isfinite(hurdle_return):
        return {}
    eligible = [
        sym
        for sym in DEFENSIVE
        if np.isfinite(calendar_return(close, sym, asof, D2_MOMENTUM_MONTHS))
        and calendar_return(close, sym, asof, D2_MOMENTUM_MONTHS) > hurdle_return
    ]
    if not eligible:
        return {}
    vols = {sym: trailing_vol(close, sym, asof, D2_VOL_LOOKBACK_SESSIONS) for sym in eligible}
    if any(not np.isfinite(v) or v <= 0 for v in vols.values()):
        return {}
    inverse = {sym: 1.0 / vols[sym] for sym in eligible}
    total = sum(inverse.values())
    return {sym: inverse[sym] / total for sym in eligible}


CANDIDATES: list[ScreenCandidate] = [
    ScreenCandidate(
        id="D1",
        name="Defense First TAA (Carlson 2025): TLT/GLD/DBC/UUP rank 40/30/20/10,"
        " BIL hurdle, SPY fallback",
        source_card=SOURCE_CARD,
        universe=("TLT", "GLD", "DBC", "UUP", "SPY"),
        freq="M",
        weights_fn=d1_weights_fn,
    ),
    ScreenCandidate(
        id="D2",
        name="Absolute momentum vs SHY, inverse-63d-vol sized: TLT/GLD/DBC/UUP",
        source_card=SOURCE_CARD,
        universe=("TLT", "GLD", "DBC", "UUP"),
        freq="M",
        weights_fn=d2_weights_fn,
    ),
]
