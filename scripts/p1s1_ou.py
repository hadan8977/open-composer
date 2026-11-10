"""Pure OU-T benchmark helpers for T-20261008-31."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OUFit:
    intercept: float
    slope: float
    mean: float
    sigma_eq: float
    kappa: float
    r2: float
    valid: bool


def fit_ar1(path: np.ndarray, annualization: int = 252) -> OUFit:
    """Fit ``y[t+1] = a + b*y[t]`` and reject non-mean-reverting fits."""
    y = np.asarray(path, dtype="float64")
    if y.ndim != 1 or y.size < 3 or not np.isfinite(y).all():
        return OUFit(*(float("nan"),) * 6, False)
    x, target = y[:-1], y[1:]
    design = np.column_stack([np.ones(x.size), x])
    a, b = np.linalg.lstsq(design, target, rcond=None)[0]
    resid = target - (a + b * x)
    var = float(np.var(resid, ddof=1)) if resid.size > 1 else float("nan")
    sigma_eq = float(np.sqrt(var / (1.0 - b * b))) if 0 < b < 1 and var >= 0 else float("nan")
    mean = float(a / (1.0 - b)) if b != 1 else float("nan")
    kappa = float(-np.log(b) * annualization) if b > 0 else float("nan")
    ss_tot = float(np.sum((target - target.mean()) ** 2))
    r2 = float(1.0 - np.sum(resid**2) / ss_tot) if ss_tot > 0 else float("nan")
    valid = bool(0 < b < 1 and np.isfinite(sigma_eq) and kappa > annualization / 30)
    return OUFit(float(a), float(b), mean, sigma_eq, kappa, r2, valid)


def score(fit: OUFit, level: float, cross_section_mean: float = 0.0) -> float:
    if not fit.valid or fit.sigma_eq <= 0:
        return float("nan")
    return float((level - (fit.mean - cross_section_mean)) / fit.sigma_eq)


def update_position(previous: int, s: float) -> int:
    """OU-T state machine: -1 short, 0 flat, +1 long."""
    if not np.isfinite(s):
        return 0
    if previous > 0:
        return 0 if s > -0.50 else 1
    if previous < 0:
        return 0 if s < 0.75 else -1
    if s < -1.25:
        return 1
    if s > 1.25:
        return -1
    return 0


def path_signal(path: np.ndarray, previous: int = 0) -> tuple[int, OUFit, float]:
    y = np.asarray(path, dtype="float64")
    fit = fit_ar1(y)
    s = score(fit, float(y[-1])) if y.size else float("nan")
    return update_position(previous, s), fit, s
