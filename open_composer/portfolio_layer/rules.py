"""Allocation rules A0-A2 (T-20261006-24 preregistration).

Weights are capital fractions of a unit-return sleeve (each sleeve series is the return per dollar
of that sleeve's own capital).  ``cov`` is a daily covariance matrix; risk shares are
``w_i (cov w)_i / w' cov w``.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

OBS_RISK_SHARE_MAX = 0.10
CAP_MULTIPLE = 1.5  # replacement for the 20 percent cap when N < 5: min(1, 1.5 / N)
PRIOR_SHARPE = {"P1": 0.59, "P0": 0.45, "observation": 0.30}  # preregistered, annual


def share_cap(n: int) -> float:
    """Risk-share cap per sleeve: ``min(1, 1.5/N)`` (20 percent is infeasible for N < 5)."""
    return min(1.0, CAP_MULTIPLE / n)


def risk_shares(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    m = cov @ w
    tot = float(w @ m)
    return w * m / tot if tot > 0 else np.zeros_like(w)


def current_capital_weights(capital: np.ndarray) -> np.ndarray:
    """A0: today's dollar allocation."""
    c = np.asarray(capital, dtype=float)
    return c / c.sum()


def budgets(statuses: list[str]) -> np.ndarray:
    """A1 risk budgets: observation sleeves 0.10, the rest share the remainder equally."""
    obs = np.array([s == "observation" for s in statuses])
    n, k = len(statuses), int(obs.sum())
    if k == n:
        return np.full(n, 1.0 / n)
    b = np.where(obs, OBS_RISK_SHARE_MAX, 0.0)
    b[~obs] = (1.0 - b.sum()) / (n - k)
    return b


def risk_budgeting(cov: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Weights whose risk shares equal ``b`` (Spinu: minimise 0.5 w'Sw - sum b log w)."""
    n = len(b)
    scale = float(np.sqrt(np.diag(cov)).mean())
    s = cov / scale**2

    def f(w):
        return 0.5 * w @ s @ w - b @ np.log(w)

    def g(w):
        return s @ w - b / w

    x0 = 1.0 / np.sqrt(np.diag(s))
    res = minimize(f, x0, jac=g, method="L-BFGS-B", bounds=[(1e-9, None)] * n)
    w = res.x / res.x.sum()
    return w


def max_sharpe(
    cov: np.ndarray,
    mu: np.ndarray,
    cap: float,
    obs_mask: np.ndarray,
    fallback: np.ndarray,
) -> tuple[np.ndarray, bool]:
    """A2: long-only max ``mu'w / sqrt(w'Sw)``, sum 1, risk share <= cap (observation <= 0.10).

    Returns ``(weights, solved)``; on failure the fallback (A1) is returned with ``solved=False``.
    """
    n = len(mu)
    caps = np.where(obs_mask, min(cap, OBS_RISK_SHARE_MAX), cap)

    def neg_sr(w):
        v = float(w @ cov @ w)
        return -float(mu @ w) / np.sqrt(v) if v > 0 else 0.0

    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    for i in range(n):
        cons.append(
            {
                "type": "ineq",
                "fun": lambda w, i=i: caps[i] * float(w @ cov @ w) - w[i] * float((cov @ w)[i]),
            }
        )
    res = minimize(
        neg_sr,
        fallback,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=cons,
        options={"maxiter": 300, "ftol": 1e-10},
    )
    w = np.clip(res.x, 0.0, None)
    w = w / w.sum()
    rs = risk_shares(w, cov)
    ok = bool(res.success) and bool((rs <= caps + 1e-4).all())
    return (w, True) if ok else (fallback, False)


def prior_mu(statuses: list[str], cov_daily: np.ndarray) -> np.ndarray:
    """Daily expected return implied by the tier prior Sharpe: ``SR_i * sigma_i / sqrt(252)``."""
    sr = np.array([PRIOR_SHARPE[s] for s in statuses])
    return sr * np.sqrt(np.diag(cov_daily)) / np.sqrt(252.0)


def portfolio_sharpe(w: np.ndarray, mu_daily: np.ndarray, cov_daily: np.ndarray) -> float:
    v = float(w @ cov_daily @ w)
    return float(w @ mu_daily) / np.sqrt(v) * np.sqrt(252.0) if v > 0 else 0.0


def equal_vol_sharpe(n: int, rho: float, sr: float) -> float:
    """Account Sharpe of n equal-vol, equal-weight sleeves with pairwise correlation rho."""
    return n * sr / np.sqrt(n + n * (n - 1) * rho)
