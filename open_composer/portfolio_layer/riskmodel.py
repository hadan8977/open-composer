"""Sleeve covariance: Ledoit-Wolf shrinkage (primary) and EWMA (robustness only).

Ledoit-Wolf 2004 (J. Multivariate Analysis 88(2):365-411): the shrinkage target is ``mu * I`` with
``mu = tr(S)/p`` and the intensity is ``min(b2, d2)/d2`` with ``d2 = ||S - mu I||_F^2 / p`` and
``b2 = (1/n^2) sum_t ||x_t x_t' - S||_F^2 / p``, the same estimator as scikit-learn's ``LedoitWolf``
(the tests compare the two).
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def ledoit_wolf(x: np.ndarray, center: bool = True) -> tuple[np.ndarray, float]:
    """Return ``(shrunk covariance, shrinkage intensity)`` of the rows-as-observations matrix."""
    x = np.asarray(x, dtype=float)
    n, p = x.shape
    if n < 2:
        raise ValueError("need at least 2 observations")
    xc = x - x.mean(axis=0) if center else x
    s = xc.T @ xc / n
    mu = np.trace(s) / p
    d2 = np.sum((s - mu * np.eye(p)) ** 2) / p
    b2 = 0.0
    for t in range(n):
        v = xc[t][:, None]
        b2 += np.sum((v @ v.T - s) ** 2)
    b2 = min(b2 / (n * n) / p, d2)
    shrink = 0.0 if d2 == 0 else b2 / d2
    return shrink * mu * np.eye(p) + (1 - shrink) * s, float(shrink)


def ewma_cov(x: np.ndarray, halflife: float = 63.0) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = 0.5 ** (np.arange(n)[::-1] / halflife)
    w /= w.sum()
    xc = x - (w[:, None] * x).sum(axis=0)
    return (xc * w[:, None]).T @ xc


def annualize(cov_daily: np.ndarray) -> np.ndarray:
    return cov_daily * TRADING_DAYS


def sample_cov(x: np.ndarray) -> np.ndarray:
    return np.cov(np.asarray(x, dtype=float), rowvar=False, ddof=1)
