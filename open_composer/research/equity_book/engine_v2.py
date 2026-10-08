# ruff: noqa: E501
"""Pure pieces of the cost-aware engine (``t20261007_01_cost_aware_engine``, T-20261007-01).

No data access.  The runner is ``scripts/t0701_engine.py``; the v1.2 construction itself stays in
``book_v12`` / ``trading_rules`` (unchanged, production uses them).  Three ways to bring a fast composite
into the slow book:

* ``combine_score`` (I1): ``z(slow) + w_f z(fast)`` as the input of the unchanged v1.2 target;
* ``defer_days`` / ``deferred_block`` (I2): the target is unchanged, a trade whose sign the fast score
  contradicts (``sign(delta) z_f < -c``) is postponed day by day, at most ``max_defer`` sessions;
* ``gp_score`` / ``partial_adjust`` (I3): Garleanu-Pedersen style aim book with partial adjustment at
  rate ``kappa`` every session; each signal enters the aim with ``b_k / (1 + phi_k / kappa)``.
"""

from __future__ import annotations

import math

import numpy as np

MAX_DEFER = 4
PRUNE = 1e-6  # |weight| below this (fraction of equity, $1 on $1M) is set to zero


# ---------------------------------------------------------------------------
# I1
# ---------------------------------------------------------------------------
def combine_score(slow: np.ndarray, fast: np.ndarray, w_f: float) -> np.ndarray:
    """``slow + w_f * fast`` on rank-normal inputs; a missing fast value contributes 0, a missing slow
    value keeps the name out (NaN)."""
    f = np.where(np.isfinite(fast), fast, 0.0)
    return np.asarray(slow, dtype="float64") + w_f * f


# ---------------------------------------------------------------------------
# I3
# ---------------------------------------------------------------------------
def gp_weights(b: dict[str, float], phi: dict[str, float], kappa: float) -> dict[str, float]:
    """Aim weight of each signal: ``b_k / (1 + phi_k / kappa)`` (decay-discounted)."""
    return {k: b[k] / (1.0 + phi[k] / kappa) for k in b}


def gp_score(
    slow: np.ndarray,
    fast: np.ndarray,
    b: dict[str, float],
    phi: dict[str, float],
    kappa: float,
) -> np.ndarray:
    w = gp_weights(b, phi, kappa)
    f = np.where(np.isfinite(fast), fast, 0.0)
    return w["slow"] * np.asarray(slow, dtype="float64") + w["fast"] * f


def partial_adjust(
    x_old: np.ndarray,
    aim: np.ndarray,
    kappa: float,
    eligible: np.ndarray,
    fill_ok: np.ndarray,
) -> np.ndarray:
    """``x = (1 - kappa) x_old + kappa aim``; no position in a name without tomorrow's fill price;
    names outside ``eligible`` are never short; dust below ``PRUNE`` is closed."""
    x = (1.0 - kappa) * np.asarray(x_old, dtype="float64") + kappa * np.asarray(
        aim, dtype="float64"
    )
    x = np.where(np.asarray(fill_ok, dtype=bool), x, 0.0)
    el = np.asarray(eligible, dtype=bool)
    x = np.where(el, x, np.maximum(x, 0.0))
    return np.where(np.abs(x) < PRUNE, 0.0, x)


def phi_from_half_life(half_life: float) -> float:
    return math.log(2.0) / half_life


# ---------------------------------------------------------------------------
# I2
# ---------------------------------------------------------------------------
def defer_days(
    delta: np.ndarray, zf: np.ndarray, c: float | None, max_defer: int = MAX_DEFER
) -> np.ndarray:
    """Execution day (0 = the normal day) of every name.

    ``delta``: (N,) intended trade (target minus the drifted position) at the decision; ``zf``: (L, N)
    fast score known before each fill day (row d is the score at the close before fill day d).  A name
    waits while ``sign(delta) * zf < -c`` and is traded at the latest on day ``min(max_defer, L - 1)``.
    ``c is None`` disables the rule (everything on day 0)."""
    n = len(delta)
    length = zf.shape[0]
    if c is None:
        return np.zeros(n, dtype="int64")
    cap = min(max_defer, length - 1)
    sgn = np.sign(delta)[None, :]
    with np.errstate(invalid="ignore"):
        wait = np.isfinite(zf) & (sgn * zf < -c)
    ok = ~wait
    ok[cap, :] = True
    ok[cap + 1 :, :] = True
    return np.argmax(ok, axis=0).astype("int64")


def deferred_block(
    x_old: np.ndarray,
    w_tgt: np.ndarray,
    exec_day: np.ndarray,
    r: np.ndarray,
    spy_r: np.ndarray,
    beta: np.ndarray,
    h_prev: float,
) -> dict[str, np.ndarray | float]:
    """One tranche block with per-name execution days (``exec_day`` all zero reproduces ``hold_block``
    of ``book_v12`` with the hedge ``-sum(w beta)``).

    ``x_old``: drifted weights before the block; ``w_tgt``: weights (fraction of equity) set when a name
    executes; ``r`` (L, N): stock returns of the block's labels (NaN = 0); ``spy_r`` (L,); ``beta`` (N,)
    hedge betas; ``h_prev``: drifted SPY hedge before the block.  The hedge is reset to ``-sum(pos beta)``
    on every day on which a stock trade executes and is held in fixed shares otherwise.

    Returns the per-label ``pnl`` (stock + hedge), trade matrix ``d_w`` (L, N) and hedge trades ``d_h`` (L,)
    in fractions of equity (a trade on day j is filled at the close before label j), ``short_notional``
    (L,), ``w_end``, ``h_end``."""
    length, n = r.shape
    r = np.where(np.isfinite(r), r, 0.0)
    g_after = np.cumprod(1.0 + r, axis=0)
    g_before = np.vstack([np.ones((1, n)), g_after[:-1]])
    cols = np.arange(n)
    scale_new = g_before[exec_day, cols]
    executed = np.arange(length)[:, None] >= exec_day[None, :]
    pos = np.where(
        executed, w_tgt[None, :] * g_before / scale_new[None, :], x_old[None, :] * g_before
    )
    pnl_stock = (pos * r).sum(axis=1)
    d_w = np.zeros((length, n))
    d_w[exec_day, cols] = w_tgt - x_old * scale_new
    d_h = np.zeros(length)
    h_start = np.zeros(length)
    cur = float(h_prev)
    for j in range(length):
        if j > 0:
            cur = h_start[j - 1] * (1.0 + spy_r[j - 1])
        if (exec_day == j).any():
            tgt = float(-np.nansum(pos[j] * beta))
            d_h[j] = tgt - cur
            cur = tgt
        h_start[j] = cur
    pnl_hedge = h_start * spy_r
    short = -(np.where(pos < 0, pos, 0.0)).sum(axis=1)
    return {
        "pnl": pnl_stock + pnl_hedge,
        "stock_pnl": pnl_stock,
        "hedge_pnl": pnl_hedge,
        "d_w": d_w,
        "d_h": d_h,
        "short_notional": short,
        "w_end": pos[-1] * (1.0 + r[-1]),
        "h_end": float(h_start[-1] * (1.0 + spy_r[-1])),
    }
