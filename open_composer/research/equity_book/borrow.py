"""D7: easy-to-borrow (ETB) proxy -- the short-eligible set ``SE_t`` (design section 2).

Alpaca exposes ``easy_to_borrow`` only for *today* (``GET /v2/assets``).  History needs a
rule built from point-in-time data.  ``short_eligible`` applies the frozen v1 rule

* ``adv_rank <= ADV_RANK_MAX`` (2000),
* ``price >= PRICE_MIN`` ($10),
* no reverse split in the past 252 sessions (open / previous close within +-3 % of k, k in
  ``REVERSE_SPLIT_DENOMINATORS``; see ``is_reverse_split_ratio`` for the direction),
* short interest / shares outstanding not in the top 5 % of the cross-section (rule is
  skipped where the value is missing: "where available").

Calibration against the 2026-10-01 Alpaca flags and its caveats are in
``reports/research/program/borrow-proxy-v1-2026-10-01/report.md``.  Applying today's flag
history to the past assumes borrow status is stable; this module is a proxy, not a record.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

RULE_VERSION = "v1"
ADV_RANK_MAX = 2000
PRICE_MIN = 10.0
SI_PCT_MAX = 0.95  # exclude names at or above the 95th cross-sectional percentile
RS_WINDOW = 252
REVERSE_SPLIT_DENOMINATORS = (2, 3, 4, 5, 8, 10, 20, 25, 50)
REVERSE_SPLIT_TOL = 0.03

# column names ``short_eligible`` reads from a frame
COL_ADV_RANK = "adv_rank"
COL_PRICE = "price"
COL_REVERSE_SPLIT = "reverse_split_252"
COL_SI_PCT = "si_over_shares_pct"

RULES: dict[str, dict[str, Any]] = {
    "v1": {"adv_rank_max": ADV_RANK_MAX, "price_min": PRICE_MIN, "si_pct_max": SI_PCT_MAX},
}


def is_reverse_split_ratio(
    ratio: Any,
    denominators: tuple[int, ...] = REVERSE_SPLIT_DENOMINATORS,
    tol: float = REVERSE_SPLIT_TOL,
    direction: str = "up",
) -> np.ndarray:
    """True where ``ratio`` (open / previous close) is within +-``tol`` (relative) of a
    reverse-split multiple.

    ``direction="up"`` (default, what the data shows): a k-for-1 reverse split multiplies the
    price by k, so open / previous close is near ``k``.  The repo's panels carry micro-cap
    reverse splits as unadjusted upward jumps (measured 2026: 68 sessions at ``k`` against 34 at
    ``1/k`` in daily_broad).  ``direction="down"`` tests ``1/k`` (the literal reading of the
    brief, which mostly catches forward-split residue and crashes) and exists for comparison."""
    if direction not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")
    r = np.asarray(ratio, dtype="float64")
    hit = np.zeros(r.shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        for k in denominators:
            target = float(k) if direction == "up" else 1.0 / k
            hit |= np.abs(r / target - 1.0) <= tol
    return hit


def detect_reverse_splits(
    open_: pd.DataFrame | pd.Series,
    close: pd.DataFrame | pd.Series,
    direction: str = "up",
) -> pd.DataFrame | pd.Series:
    """Per-session reverse-split flag: ``open_t / close_{t-1}`` within +-3 % of 2, 3, 4, 5, 8,
    10, 20, 25 or 50 (``direction="up"``) or of their reciprocals (``"down"``).

    ``open_`` and ``close`` share an index (sessions in order) and columns (symbols).  The
    first session is always False.  NaN prices give False."""
    prev = close.shift(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = open_ / prev
    flag = is_reverse_split_ratio(ratio.to_numpy(), direction=direction)
    if isinstance(ratio, pd.DataFrame):
        return pd.DataFrame(flag, index=ratio.index, columns=ratio.columns)
    return pd.Series(flag, index=ratio.index, name=ratio.name)


def reverse_split_in_window(flags: pd.DataFrame | pd.Series, window: int = RS_WINDOW) -> Any:
    """True where any reverse-split flag occurred in the past ``window`` sessions
    (including the current one)."""
    return flags.astype(float).rolling(window, min_periods=1).max().astype(bool)


def si_cross_sectional_pct(si_over_shares: pd.Series, group: pd.Series | None = None) -> pd.Series:
    """Cross-sectional percentile rank in (0, 1] of short interest / shares (NaN stays NaN).
    ``group`` (e.g. the date) ranks within groups."""
    if group is None:
        return si_over_shares.rank(pct=True)
    return si_over_shares.groupby(group).rank(pct=True)


def rule_mask(
    adv_rank: Any,
    price: Any,
    reverse_split: Any,
    si_pct: Any = None,
    *,
    adv_rank_max: float = ADV_RANK_MAX,
    price_min: float = PRICE_MIN,
    si_pct_max: float = SI_PCT_MAX,
) -> np.ndarray:
    """Array form of the rule (works for any broadcastable shape, e.g. wide panels).
    Missing ``adv_rank``/``price`` -> False; missing ``si_pct`` -> the SI clause is skipped;
    missing ``reverse_split`` -> treated as False (no evidence of a split)."""
    a = np.asarray(adv_rank, dtype="float64")
    p = np.asarray(price, dtype="float64")
    with np.errstate(invalid="ignore"):
        ok = (a <= adv_rank_max) & (p >= price_min)
        ok &= np.isfinite(a) & np.isfinite(p)
    rs = np.asarray(reverse_split)
    rs = np.where(pd.isna(rs), False, rs).astype(bool)
    ok &= ~rs
    if si_pct is not None:
        s = np.asarray(si_pct, dtype="float64")
        with np.errstate(invalid="ignore"):
            ok &= ~(np.isfinite(s) & (s >= si_pct_max))
    return ok


def short_eligible(
    panel_slice_or_frame: pd.DataFrame | Mapping[str, Any],
    rule: str = RULE_VERSION,
) -> pd.Series | pd.DataFrame:
    """``SE_t``: the boolean short-eligible mask under ``rule`` (``"v1"``).

    Accepts a long frame with columns ``adv_rank``, ``price``, ``reverse_split_252`` (bool)
    and optionally ``si_over_shares_pct`` (cross-sectional percentile of short interest /
    shares, NaN where unavailable); returns a bool ``Series`` on the same index.  A mapping
    of equally-shaped wide frames under the same keys returns a bool ``DataFrame`` (the
    equity-book panel layout: dates x symbols)."""
    if rule not in RULES:
        raise ValueError(f"unknown borrow rule {rule!r}; known: {sorted(RULES)}")
    cfg = RULES[rule]
    if isinstance(panel_slice_or_frame, pd.DataFrame):
        f = panel_slice_or_frame
        si = f[COL_SI_PCT] if COL_SI_PCT in f.columns else None
        rs = f[COL_REVERSE_SPLIT] if COL_REVERSE_SPLIT in f.columns else False
        mask = rule_mask(
            f[COL_ADV_RANK],
            f[COL_PRICE],
            rs,
            si,
            adv_rank_max=cfg["adv_rank_max"],
            price_min=cfg["price_min"],
            si_pct_max=cfg["si_pct_max"],
        )
        return pd.Series(mask, index=f.index, name="short_eligible")
    m = panel_slice_or_frame
    adv = m[COL_ADV_RANK]
    mask = rule_mask(
        adv,
        m[COL_PRICE],
        m.get(COL_REVERSE_SPLIT, False),
        m.get(COL_SI_PCT),
        adv_rank_max=cfg["adv_rank_max"],
        price_min=cfg["price_min"],
        si_pct_max=cfg["si_pct_max"],
    )
    if isinstance(adv, pd.DataFrame):
        return pd.DataFrame(mask, index=adv.index, columns=adv.columns)
    return pd.Series(mask, index=getattr(adv, "index", None), name="short_eligible")
