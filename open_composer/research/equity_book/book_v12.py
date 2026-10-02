"""Pure contract logic of book v1.2 (``t20261002_book_v12``, hypotheses.md frozen 05:31 UTC).

Nothing here reads data.  The backtest scripts (``scripts/book_v12_account.py``,
``scripts/book_v12_placebo.py``) and the production target generator (T-20261002-27) import the same
functions, so the contract is implemented once.

Sections
--------
* strategy rules of T-25 R6 (``target_weights``, ``restrict_shorts``, ``hedge_size``,
  ``vix_scale``, ``tranche_target``, ``hold_block``): bit-identical copies of
  ``scripts/realism_ladder_book_ls.py``;
* account scaling of section 3 (``f1_k_eff``, ``f2_k2_eff``, ``tbill_fraction``);
* five-tranche netting into whole shares with the order-engine rules (``round_half_away_array``,
  ``virtual_shares``, ``aggregate_targets``);
* Alpaca margin (``initial_margin_requirement``, ``maintenance_requirement``);
* the delisting bound (``delist_adjustment``, ``delist_flags``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# constants fixed by the contract
# ---------------------------------------------------------------------------
EQUITY = 1_000_000.0
N_TRANCHES = 5
G_CAP = 1.8  # total gross cap (Reg T overnight 2.0 minus a 10% buffer)
F1_K = 0.5  # F1 scale (5% annual vol target)
F2_CORE = 1.0  # F2 SPY core, fraction of equity
F2_OVERLAY_MAX = 0.3
VIX_THRESHOLD = 20.60
MIN_NOTIONAL = 100.0  # engine default of ``build_plan``
DELIST_LONG_RETURN = -0.30  # Shumway (1997) performance-delisting mean, applied to every delisting
DELIST_SHORT_RETURN = 0.0
DELIST_GUARD_SESSIONS = 5
DEBIT_RATE = 0.065  # Alpaca non-elite margin rate
DEBIT_DAY_COUNT = 360
BORROW_BP_YEAR_T25 = 25.0
INITIAL_MARGIN = 0.5


# ---------------------------------------------------------------------------
# strategy rules (copies of T-25; do not edit without re-running the identity check)
# ---------------------------------------------------------------------------
def target_weights(score: pd.Series, ind: pd.Series) -> pd.Series:
    """Industry-demeaned score scaled to long 1 / short 1 (``w = 2 s_dm / sum|s_dm|``)."""
    s = score.dropna()
    if s.empty:
        return s.astype(float)
    g = ind.reindex(s.index).fillna(-1)
    dm = s - s.groupby(g.to_numpy()).transform("mean")
    gross = float(dm.abs().sum())
    if not gross > 0:
        return dm * 0.0
    return 2.0 * dm / gross


def restrict_shorts(w: pd.Series, eligible: pd.Series) -> pd.Series:
    """Short names outside the easy-to-borrow set get weight 0; the short leg is rescaled to -1."""
    ok = eligible.reindex(w.index).fillna(False).astype(bool)
    out = w.where((w >= 0) | ok, 0.0)
    neg = out < 0
    s = -float(out[neg].sum())
    if s > 0:
        out[neg] = out[neg] / s
    return out


def hedge_size(w: np.ndarray, beta: np.ndarray) -> float:
    """SPY position (fraction of equity) that offsets the weighted beta: ``-sum w_i beta_i``."""
    return float(-np.nansum(w * beta))


def vix_scale(vix: float, threshold: float = VIX_THRESHOLD) -> float:
    """1 normally, 0.5 when the VIX at the decision date is above the threshold (NaN: 1)."""
    return 0.5 if (np.isfinite(vix) and vix > threshold) else 1.0


@dataclass
class TrancheTarget:
    """One tranche's target at a decision date, in fractions of tranche-relative equity.

    ``w_unit`` (dense over the symbol index) is the ETB-restricted, fill-valid weight vector before
    the VIX scale; ``h_unit`` is its SPY hedge; ``vscale`` the VIX scale.  ``w`` and ``h`` are the
    strategy-level (k = 1) values of T-25 R6 (``w_unit * vscale`` and the hedge of that vector)."""

    w_unit: np.ndarray
    h_unit: float
    vscale: float
    w: np.ndarray
    h: float
    n_members: int


def tranche_target(
    score: pd.Series,
    ind: pd.Series,
    eligible: pd.Series,
    symbols: pd.Index,
    fill_ok: np.ndarray,
    beta_ewma: pd.Series,
    vix: float,
) -> TrancheTarget:
    """T-25 R6 weights at one decision date.

    ``score``: composite (rank-normal) of the universe members; ``ind``: industry code;
    ``eligible``: proxy easy-to-borrow flags aligned with ``score``; ``symbols``: the global symbol
    index of the dense vectors; ``fill_ok``: dense bool, True where the fill price of D+1 exists;
    ``beta_ewma``: saved EWMA betas (missing is 1.0, clipped to [-1, 4]); ``vix``: VIXCLS at D."""
    n = len(symbols)
    w_full_s = target_weights(score, ind)
    idx = symbols.get_indexer(w_full_s.index)
    keep = idx >= 0
    w_etb_s = restrict_shorts(w_full_s, eligible)
    w_etb = np.zeros(n)
    w_etb[idx[keep]] = w_etb_s.to_numpy()[keep]
    b_ewma = np.ones(n)
    ev = beta_ewma.reindex(w_full_s.index).fillna(1.0).clip(-1.0, 4.0)
    b_ewma[idx[keep]] = ev.to_numpy()[keep]
    w_unit = w_etb.copy()
    w_unit[~fill_ok] = 0.0
    vs = vix_scale(vix)
    w = w_unit * vs
    return TrancheTarget(
        w_unit=w_unit,
        h_unit=hedge_size(w_unit, b_ewma),
        vscale=vs,
        w=w,
        h=hedge_size(w, b_ewma),
        n_members=int(len(w_full_s)),
    )


def hold_block(
    w0: np.ndarray, r: np.ndarray, spy_r: np.ndarray, *, h0: float = 0.0
) -> dict[str, np.ndarray | float]:
    """Hold fixed shares for ``len(r)`` labels (T-25 ``hold_block`` with the SPY hedge ``h0``).

    ``w0``: weights (fraction of equity) at the start; ``r``: (L, N) stock returns (NaN = 0);
    ``spy_r``: (L,) SPY returns.  Label j earns ``w0 * G_j * r_j`` with ``G_j`` the cumulative
    growth before day j; ``h0`` is a SPY position held in fixed shares."""
    r = np.where(np.isfinite(r), r, 0.0)
    g_after = np.cumprod(1.0 + r, axis=0)
    g_before = np.vstack([np.ones((1, r.shape[1])), g_after[:-1]])
    pos = w0[None, :] * g_before
    pnl = (pos * r).sum(axis=1)
    s_after = np.cumprod(1.0 + spy_r)
    s_before = np.concatenate([[1.0], s_after[:-1]])
    pnl_hedge = h0 * s_before * spy_r
    short = -(np.where(pos < 0, pos, 0.0)).sum(axis=1)
    return {
        "pnl": pnl + pnl_hedge,
        "stock_pnl": pnl,
        "hedge_pnl": pnl_hedge,
        "w_end": w0 * g_after[-1],
        "h_end": float(h0 * s_after[-1]),
        "short_notional": short,
    }


# ---------------------------------------------------------------------------
# account scaling (hypotheses.md section 3)
# ---------------------------------------------------------------------------
def f1_k_eff(vscale: float, h_unit: float, *, k: float = F1_K, g: float = G_CAP) -> float:
    """F1 tranche scale: ``0.5 * vix_scale``, pressed to ``G / (2 + |h|)`` when that would exceed
    the gross cap.  ``h_unit`` is the k = 1 hedge of the tranche (before the VIX scale)."""
    k_eff = k * vscale
    if k_eff * (2.0 + abs(h_unit)) > g:
        k_eff = g / (2.0 + abs(h_unit))
    return k_eff


def f2_k2_eff(
    vscale: float, h_unit: float, *, cap: float = F2_OVERLAY_MAX, g: float = G_CAP
) -> float:
    """F2 overlay scale: ``min(0.3, (G - 1) / (2 + |h|)) * vix_scale``."""
    return min(cap, (g - 1.0) / (2.0 + abs(h_unit))) * vscale


def tbill_fraction(long_frac: float, short_frac: float, *, g: float = G_CAP) -> float:
    """T-bill leg as a fraction of equity: ``max(0, min(G - L - S, 1 - L + S))``.

    ``long_frac`` and ``short_frac`` are the long and short market values (the short value as a
    positive number, hedge ETF included, T-bill excluded) as fractions of equity.  The leg neither
    breaks the gross cap nor needs a margin loan (cash ``1 - L + S`` stays non-negative)."""
    return max(0.0, min(g - long_frac - short_frac, 1.0 - long_frac + short_frac))


def gross_scale(long_frac: float, short_frac: float, *, g: float = G_CAP) -> float:
    """Scale that brings ``L + S`` back to the cap when it is above (1 otherwise)."""
    tot = long_frac + short_frac
    return g / tot if tot > g else 1.0


# ---------------------------------------------------------------------------
# whole shares, netting of the five tranches
# ---------------------------------------------------------------------------
def round_half_away_array(x: np.ndarray) -> np.ndarray:
    """Vector form of ``open_composer.book_paper.plan.round_half_away`` (halves away from zero)."""
    x = np.asarray(x, dtype="float64")
    return np.where(x == 0, 0.0, np.copysign(np.floor(np.abs(x) + 0.5), x)).astype("int64")


def virtual_shares(
    w_unit: np.ndarray,
    k: float,
    equity: float,
    p_ref: np.ndarray,
    *,
    n_tranches: int = N_TRANCHES,
) -> np.ndarray:
    """Fractional shares of one tranche: ``w * k * (E / n_tranches) / P_ref``.  A name without a
    reference price (NaN or non-positive) gets 0 shares (it cannot be sized)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        out = w_unit * k * (equity / n_tranches) / p_ref
    return np.where(np.isfinite(out) & (p_ref > 0), out, 0.0)


def aggregate_targets(
    virtual_total: np.ndarray,
    p_ref: np.ndarray,
    current_qty: np.ndarray,
    *,
    min_notional: float = MIN_NOTIONAL,
    scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Netted whole-share orders.  Returns ``(post_qty, order_qty, dropped)``.

    Target shares are ``round_half_away(scale * sum of tranche virtual shares)``; the order is the
    difference from the current whole-share position; an order whose ``|qty| * P_ref`` is below
    ``min_notional`` is dropped (the position stays), exactly as ``build_plan``."""
    target = round_half_away_array(virtual_total * scale)
    delta = target - current_qty
    with np.errstate(invalid="ignore"):
        notional = np.abs(delta) * np.where(np.isfinite(p_ref), p_ref, 0.0)
    dropped = (delta != 0) & (notional < min_notional)
    order = np.where(dropped, 0, delta)
    return current_qty + order, order, dropped


# ---------------------------------------------------------------------------
# Alpaca margin (hypotheses.md section 3)
# ---------------------------------------------------------------------------
def initial_margin_requirement(long_mv: float, short_mv: float) -> float:
    """Reg T initial margin of the overnight book: 50% of long plus short market value."""
    return INITIAL_MARGIN * (long_mv + short_mv)


def maintenance_requirement(qty: np.ndarray, price: np.ndarray) -> float:
    """Alpaca maintenance margin of a position set (dollars).

    Long: price < 2.50 -> 100% of value; 2.50 .. 6 (inclusive) -> 50%; above 6 -> 30%.
    Short: price < 5 -> max($2.50 per share, 100% of value); price >= 5 -> max($5 per share, 30%).
    The boundary prices fall on the stricter side."""
    q = np.asarray(qty, dtype="float64")
    p = np.asarray(price, dtype="float64")
    ok = np.isfinite(p) & (q != 0)
    q, p = q[ok], p[ok]
    long_ = q > 0
    lq, lp = q[long_], p[long_]
    rate_l = np.where(lp < 2.5, 1.0, np.where(lp <= 6.0, 0.5, 0.3))
    long_req = float(np.sum(rate_l * lq * lp))
    sq, sp = -q[~long_], p[~long_]
    mv = sq * sp
    short_req = np.where(sp < 5.0, np.maximum(2.5 * sq, mv), np.maximum(5.0 * sq, 0.3 * mv))
    return long_req + float(np.sum(short_req))


# ---------------------------------------------------------------------------
# delisting bound (hypotheses.md section 4)
# ---------------------------------------------------------------------------
def delist_adjustment(
    qty: float,
    last_price: float,
    *,
    long_return: float = DELIST_LONG_RETURN,
    short_return: float = DELIST_SHORT_RETURN,
) -> float:
    """One-off P&L (dollars) when a held name has no further close: ``-30%`` of a long's value at
    the last close, 0 for a short (the short is assumed covered at the last close)."""
    if qty > 0:
        return float(long_return * qty * last_price)
    if qty < 0:
        return float(short_return * -qty * last_price)
    return 0.0


def delist_flags(
    close: np.ndarray, *, guard: int = DELIST_GUARD_SESSIONS
) -> tuple[np.ndarray, np.ndarray]:
    """Per symbol: last session index with a close and whether the name counts as delisted
    (``last <= n_sessions - 1 - guard``).  ``close``: (T, N) matrix.  A name without any close
    gets last = -1 and is not flagged."""
    t_n = close.shape[0]
    valid = np.isfinite(close)
    any_valid = valid.any(axis=0)
    last = np.where(any_valid, t_n - 1 - np.argmax(valid[::-1], axis=0), -1)
    flagged = any_valid & (last <= t_n - 1 - guard)
    return last.astype("int64"), flagged


def debit_interest(cash: float, calendar_days: int, *, rate: float = DEBIT_RATE) -> float:
    """Interest (dollars, positive = paid) on a negative cash balance, ``rate / 360`` per day."""
    if not cash < 0:
        return 0.0
    return float(-cash * rate / DEBIT_DAY_COUNT * calendar_days)


def finite_or_nan(x: float) -> float:
    return float(x) if math.isfinite(x) else float("nan")
