"""Rolling evaluation, sleeve drawdown stops, regime tilt, bootstrap drawdown budget.

Everything follows ``reports/research/program/portfolio-layer-2026-10-07/prereg.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import rules as R
from .riskmodel import ewma_cov, ledoit_wolf, sample_cov

WINDOW = 252
BOOT_BLOCK = 21
BOOT_SEED = 20261008
FIN_RATE = 0.07  # annual cost of borrowed notional above 1x (to be checked against Alpaca)
RECENT = ("2024-01-08", "2026-09-15")
STRESS = ("2017-10-02", "2023-08-31")


def rebalance_dates(index: pd.DatetimeIndex, start: str | pd.Timestamp) -> list[pd.Timestamp]:
    """First session of each month at/after ``start`` with a full 252-day window behind it."""
    s = pd.Series(index, index=index)
    firsts = s.groupby([index.year, index.month]).min()
    out = [d for d in firsts if d >= pd.Timestamp(start)]
    return [d for d in out if index.get_loc(d) >= WINDOW]


@dataclass
class RuleSpec:
    name: str
    kind: str  # A0 A1 A2 A3 A4
    k: float | None = None
    cov: str = "lw"  # lw | ewma | sample


def _cov(win: np.ndarray, kind: str) -> np.ndarray:
    if kind == "ewma":
        return ewma_cov(win)
    if kind == "sample":
        return sample_cov(win)
    return ledoit_wolf(win)[0]


def target_weights(
    spec: RuleSpec,
    win: np.ndarray,
    statuses: list[str],
    capital: np.ndarray,
    mu_scale: np.ndarray | None = None,
) -> np.ndarray:
    n = len(statuses)
    if spec.kind == "A0":
        return R.current_capital_weights(capital)
    cov = _cov(win, spec.cov)
    a1 = R.risk_budgeting(cov, R.budgets(statuses))
    if spec.kind == "A1":
        return a1
    mu = R.prior_mu(statuses, cov)
    if mu_scale is not None:
        mu = mu * mu_scale
    obs = np.array([s == "observation" for s in statuses])
    w, _ = R.max_sharpe(cov, mu, R.share_cap(n), obs, a1)
    return w


def stop_multipliers(r: pd.DataFrame, k: float) -> pd.DataFrame:
    """Daily weight multiplier (1 or 0.5) per sleeve from its own drawdown, known at t-1.

    Drawdown of the sleeve's wealth from its trailing-252-day high; stop when it exceeds
    ``k`` times the trailing-252-day annualised volatility, release below ``0.5 k`` times it.
    """
    wealth = (1.0 + r).cumprod()
    hi = wealth.rolling(WINDOW, min_periods=WINDOW).max()
    dd = 1.0 - wealth / hi
    vol = r.rolling(WINDOW, min_periods=WINDOW).std() * np.sqrt(252.0)
    m = pd.DataFrame(1.0, index=r.index, columns=r.columns)
    for c in r.columns:
        on = False
        vals = np.ones(len(r))
        d, v = dd[c].to_numpy(), vol[c].to_numpy()
        for t in range(1, len(r)):
            if np.isfinite(d[t - 1]) and np.isfinite(v[t - 1]):
                if not on and d[t - 1] > k * v[t - 1]:
                    on = True
                elif on and d[t - 1] < 0.5 * k * v[t - 1]:
                    on = False
            vals[t] = 0.5 if on else 1.0
        m[c] = vals
    return m


def run_rule(
    r: pd.DataFrame,
    spec: RuleSpec,
    statuses: list[str],
    capital: np.ndarray,
    start: str,
    end: str,
    regime: pd.Series | None = None,
    regime_scale: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    """Rolling allocation: (daily return, weights by rebalance, turnover per rebalance)."""
    idx = r.index
    reb = rebalance_dates(idx, start)
    mult = stop_multipliers(r, spec.k) if spec.kind == "A4" else None
    a = None
    out, wrows, turn = [], {}, {}
    reb_set = set(reb)
    first = reb[0]
    for t, d in enumerate(idx):
        if d < first or d > pd.Timestamp(end):
            continue
        if d in reb_set:
            win = r.iloc[t - WINDOW : t].to_numpy()
            scale = None
            if spec.kind == "A3" and regime is not None and regime_scale is not None:
                st = bool(regime.reindex([idx[t - 1]]).iloc[0])
                scale = regime_scale.loc["risk_off" if st else "risk_on"].to_numpy()
            w = target_weights(
                RuleSpec(
                    spec.name, "A2" if spec.kind in ("A3", "A4") else spec.kind, spec.k, spec.cov
                ),
                win,
                statuses,
                capital,
                scale,
            )
            if a is not None:
                turn[d] = float(np.abs(w - a / a.sum()).sum() / 2)
            a = w * (a.sum() if a is not None else 1.0)
            wrows[d] = w
        m = mult.iloc[t].to_numpy() if mult is not None else 1.0
        rr = r.iloc[t].to_numpy()
        gain = a * m * rr
        out.append((d, float(gain.sum() / a.sum())))
        a = a + gain
    return (
        pd.Series(dict(out)),
        pd.DataFrame(wrows, index=r.columns).T,
        pd.Series(turn, dtype=float),
    )


def sharpe(x: pd.Series | np.ndarray) -> float:
    v = np.asarray(x, dtype=float)
    sd = v.std(ddof=1)
    return float(v.mean() / sd * np.sqrt(252.0)) if sd > 0 else 0.0


def max_drawdown(x: pd.Series | np.ndarray) -> float:
    v = np.asarray(x, dtype=float)
    w = np.cumprod(1.0 + v)
    return float((w / np.maximum.accumulate(w) - 1.0).min())


def stationary_indices(n: int, length: int, sims: int, mean_block: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    idx = np.empty((sims, length), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, sims)
    jump = rng.random((sims, length)) < 1.0 / mean_block
    fresh = rng.integers(0, n, (sims, length))
    for t in range(1, length):
        idx[:, t] = np.where(jump[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def boot_drawdown_q95(
    r: np.ndarray,
    lev: float,
    daily_mean: float | None = None,
    sims: int = 2000,
    length: int = 504,
    seed: int = BOOT_SEED,
    fin_rate: float = FIN_RATE,
    idx: np.ndarray | None = None,
    fin_base: float = 1.0,
) -> float:
    """95th percentile of the 2-year maximum drawdown magnitude of ``lev`` x the series.

    ``daily_mean`` replaces the sample mean (returns are demeaned first); borrowed notional above
    1x of equity pays ``fin_rate`` per year, where ``lev * fin_base`` is the series' notional as a
    multiple of equity (``fin_base`` < 1 when only part of the account is deployed).
    """
    x = np.asarray(r, dtype=float)
    if daily_mean is not None:
        x = x - x.mean() + daily_mean
    if idx is None:
        idx = stationary_indices(len(x), length, sims, BOOT_BLOCK, seed)
    path = lev * x[idx] - max(lev * fin_base - 1.0, 0.0) * fin_rate / 252.0
    w = np.cumprod(1.0 + path, axis=1)
    dd = 1.0 - w / np.maximum.accumulate(w, axis=1)
    return float(np.quantile(dd.max(axis=1), 0.95))


def solve_leverage(
    r: np.ndarray,
    budget: float = 0.30,
    daily_mean: float | None = None,
    lo: float = 0.1,
    hi: float = 6.0,
    **kw,
) -> float:
    """Largest L in [lo, hi] with q95 2-year max drawdown <= budget (bisection, monotone in L)."""
    x = np.asarray(r, dtype=float)
    idx = stationary_indices(
        len(x), kw.get("length", 504), kw.get("sims", 2000), BOOT_BLOCK, BOOT_SEED
    )
    kw = {k: v for k, v in kw.items() if k not in ("length", "sims")}
    if boot_drawdown_q95(x, lo, daily_mean, idx=idx, **kw) > budget:
        return lo
    if boot_drawdown_q95(x, hi, daily_mean, idx=idx, **kw) <= budget:
        return hi
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if boot_drawdown_q95(x, mid, daily_mean, idx=idx, **kw) <= budget:
            lo = mid
        else:
            hi = mid
    return lo


def paired_sharpe_diff(a: pd.Series, b: pd.Series, sims: int = 2000, seed: int = BOOT_SEED) -> dict:
    """Stationary-block bootstrap of Sharpe(a) - Sharpe(b) (same dates)."""
    df = pd.concat([a, b], axis=1).dropna().to_numpy()
    n = len(df)
    idx = stationary_indices(n, n, sims, BOOT_BLOCK, seed)
    d = np.empty(sims)
    for i in range(sims):
        s = df[idx[i]]
        d[i] = sharpe(s[:, 0]) - sharpe(s[:, 1])
    lo, hi = np.quantile(d, [0.05, 0.95])
    return {"diff": sharpe(df[:, 0]) - sharpe(df[:, 1]), "ci90": [float(lo), float(hi)]}


def simulate_equal_vol_sharpe(
    n: int, rho: float, sr: float, days: int = 400_000, seed: int = 7
) -> float:
    """Monte-Carlo check of ``rules.equal_vol_sharpe`` (equal vol, equal weights)."""
    rng = np.random.default_rng(seed)
    sigma = 0.01
    common = rng.standard_normal(days)
    eps = rng.standard_normal((days, n))
    z = np.sqrt(rho) * common[:, None] + np.sqrt(1 - rho) * eps
    x = sr * sigma / np.sqrt(252.0) + sigma * z
    return sharpe(x.mean(axis=1))
