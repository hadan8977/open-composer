"""Matched PCA projection and continuous fractional-account reference math.

No data access, optimization, source acquisition or broker interface.
"""

import numpy as np


def pca_projection(history, k=5, loading_window=60):
    """At decision t use only returns strictly before t. Source 252/60 windows."""
    history = np.asarray(history, dtype=float)
    if history.shape[0] != 252 or not np.isfinite(history).all():
        raise ValueError("PCA needs 252 finite, dated observations; no future intersection")
    sigma = history.std(axis=0, ddof=1)
    if np.any(sigma <= 1e-8) or k >= history.shape[1]:
        raise ValueError("insufficient eligible assets/variance")
    standardized = (history - history.mean(axis=0)) / sigma
    corr = standardized.T @ standardized / (len(history) - 1)
    _, vectors = np.linalg.eigh(corr)
    eigenportfolios = vectors[:, -k:].T / sigma
    factor_returns = history[-loading_window:] @ eigenportfolios.T
    # No fitted intercept in the traded projection: any cash intercept would
    # otherwise break residual/stock P&L equality. This choice is an adaptation.
    loadings = np.linalg.lstsq(factor_returns, history[-loading_window:], rcond=None)[0].T
    return np.eye(history.shape[1]) - loadings @ eigenportfolios


def project(raw, projection):
    mapped = np.einsum("...i,...ij->...j", np.asarray(raw), np.asarray(projection))
    norm = np.abs(mapped).sum(axis=-1, keepdims=True)
    return np.divide(mapped, norm, out=np.zeros_like(mapped), where=norm > 1e-8)


def path_windows(residuals, execution_rows, lookback=30):
    """Execution at close e uses residual observations only through e-1."""
    x = np.asarray(residuals)
    result = []
    for e in execution_rows:
        if e < lookback:
            raise ValueError("insufficient causal lookback")
        result.append(np.cumsum(x[e - lookback : e], axis=0).T)
    return np.asarray(result)


def threshold_policy(paths, previous=None):
    """Fixed contrarian residual path; deterministic, not fitted/optimized."""
    paths = np.asarray(paths)
    center = paths.mean(axis=-1)
    scale = paths.std(axis=-1, ddof=0)
    score = np.divide(paths[..., -1] - center, scale, out=np.zeros_like(scale), where=scale > 1e-8)
    previous = np.zeros_like(score) if previous is None else np.asarray(previous)
    result = previous.copy()
    result[np.abs(score) < 0.5] = 0
    result[score > 1.25] = -1
    result[score < -1.25] = 1
    return result


def source_ou_policy(paths):
    """Accepted public OUThreshold equations, including original variance conventions."""
    x = np.asarray(paths, dtype=float)
    xs, ys = x[..., :-1], x[..., 1:]
    mx, my = xs.mean(axis=-1), ys.mean(axis=-1)
    vx, vy = xs.var(axis=-1, ddof=1) + 1e-16, ys.var(axis=-1, ddof=1) + 1e-16
    cov = ((xs - mx[..., None]) * (ys - my[..., None])).mean(axis=-1)
    beta = cov / vx
    alpha = my - beta * mx
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = alpha / (1 - beta)
        errors = ys - beta[..., None] * xs - alpha[..., None]
        sigma = np.sqrt(errors.var(axis=-1, ddof=1) / np.abs(1 - beta**2))
        score = (mean - ys[..., -1]) / sigma
    valid = (
        (beta > 0)
        & (beta < 1)
        & (sigma > 1e-16)
        & ((cov**2 / (vx * vy)) > 0.25)
        & np.isfinite(score)
    )
    return np.where(valid, (score > 1.25).astype(float) - (score < -1.25).astype(float), 0.0)


def fractional_account(targets, realized_returns, trans_cost, short_cost, initial_nav=1.0):
    """All initial legs charged; drifted holdings carried across refit boundaries.

    Inputs must already contain accepted economic action/terminal returns.
    NAV after trading solves z = 1 - c ||z*q - w_pre||_1. Dividend reinvestment/
    entitlement-valued synthetic units are a method convention, not broker cash.
    There is no fabricated final liquidation or fee/state reset.
    """
    targets = np.asarray(targets, dtype=float)
    returns = np.asarray(realized_returns, dtype=float)
    if targets.shape != returns.shape or not np.isfinite(targets).all():
        raise ValueError("target/return alignment or invalid target")
    if not 0 <= trans_cost < 0.1 or not 0 <= short_cost < 0.1:
        raise ValueError("costs are decimal, per dollar turnover/short notional")
    nav, previous = float(initial_nav), np.zeros(targets.shape[1])
    rows = []
    for i, (q, r) in enumerate(zip(targets, returns, strict=True)):
        # Previous holdings were marked in the preceding iteration. If they can
        # be sold at this known endpoint, a missing NEXT mark does not invalidate
        # their completed exit. Every currently held unknown return still fails.
        exposed = np.abs(q) > 1e-12
        if not np.isfinite(r[exposed]).all():
            raise ValueError(f"unresolved held return at row {i}; no zero/drop/forced exit")
        r = np.where(np.isfinite(r), r, 0.0)  # only never-held/zero-target cells
        if np.abs(q).sum() > 1 + 1e-8:
            raise ValueError("gross exposure exceeds fixed L1 limit")
        z = 1.0
        for _ in range(100):
            updated = 1 - trans_cost * np.abs(z * q - previous).sum()
            if abs(updated - z) < 1e-13:
                z = updated
                break
            z = updated
        if z <= 0 or abs(z - (1 - trans_cost * np.abs(z * q - previous).sum())) > 1e-10:
            raise ValueError("cost-funded target solution invalid")
        turnover = float(np.abs(z * q - previous).sum())
        gross = float(q @ r)
        short = float(np.maximum(-q, 0).sum())
        holding = short_cost * short
        multiplier = z * (1 + gross - holding)
        if multiplier <= 0:
            raise ValueError("account insolvent")
        before = nav
        nav *= multiplier
        previous = q * (1 + r) / (1 + gross - holding)
        rows.append(
            {
                "row": i,
                "nav_before": before,
                "nav_after": nav,
                "net_return": multiplier - 1,
                "gross_portfolio_return": gross,
                "turnover_per_pretrade_nav": turnover,
                "transaction_cost_per_pretrade_nav": trans_cost * turnover,
                "short_cost_per_pretrade_nav": z * holding,
                "long_notional": float(np.maximum(q, 0).sum()),
                "short_notional": short,
                "posttrade_gross_leverage": float(np.abs(q).sum()),
            }
        )
    return rows


def paired_summary(cost, gross, simple, seed=20261014):
    """Paired date-block bootstrap; no seed, fee or date winner selection."""
    cost, gross, simple = map(lambda x: np.asarray(x, dtype=float), (cost, gross, simple))
    if len(cost) < 500 or any(x.shape != cost.shape for x in (gross, simple)):
        raise ValueError("complete common 500-date matrix required")
    if not all(np.isfinite(x).all() for x in (cost, gross, simple)):
        raise ValueError("missing net returns: inference N/A")
    rng = np.random.default_rng(seed)
    result = {}
    for name, base in [("vs_gross_trained", gross), ("vs_simple_residual", simple)]:
        difference = cost - base
        starts = rng.integers(0, len(cost), size=(1000, 50))
        idx = (starts[..., None] + np.arange(10)) % len(cost)
        sample = difference[idx].reshape(1000, 500).mean(axis=1)
        lo, hi = np.quantile(sample, [0.025, 0.975])
        result[name] = {
            "daily_mean_delta": float(difference.mean()),
            "annualized_arithmetic_delta": float(252 * difference.mean()),
            "paired_95pct_daily_CI": [float(lo), float(hi)],
            "recent_250_day_mean_delta": float(difference[-250:].mean()),
            "positive_125_day_blocks": int(
                sum(difference[i : i + 125].mean() > 0 for i in range(0, 500, 125))
            ),
            "power_limit": "single exposed cohort; cross-stock/date dependence retained",
            "conditional_evidence_pass": bool(
                lo > 0
                and difference[-250:].mean() > 0
                and sum(difference[i : i + 125].mean() > 0 for i in range(0, 500, 125)) >= 3
            ),
        }
    return result


def performance_summary(rows):
    """Continuous method metrics; never silently invent a cash-excess series."""
    if not rows:
        raise ValueError("empty economic ledger")
    returns = np.asarray([r["net_return"] for r in rows])
    nav = np.asarray([rows[0]["nav_before"]] + [r["nav_after"] for r in rows])
    peak = np.maximum.accumulate(nav)
    below = nav < peak - 1e-12
    longest = current = 0
    for flag in below:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    std = float(returns.std(ddof=1))
    return {
        "sessions": len(rows),
        "net_profit_fraction": float(nav[-1] / nav[0] - 1),
        "CAGR": float((nav[-1] / nav[0]) ** (252 / len(rows)) - 1),
        "annualized_arithmetic_mean": float(252 * returns.mean()),
        "annualized_volatility": float(np.sqrt(252) * std),
        "Sharpe_zero_cash_convention": float(np.sqrt(252) * returns.mean() / std)
        if std > 0
        else None,
        "Sharpe_excess_BIL": None,
        "cash_excess_scope": "requires actual matched BIL input",
        "max_drawdown": float(np.min(nav / peak - 1)),
        "longest_underwater_sessions": longest,
        "terminal_unrecovered": bool(below[-1]),
        "terminal_recovery_time": None if below[-1] else 0,
        "turnover_sum": float(sum(r["turnover_per_pretrade_nav"] for r in rows)),
        "transaction_cost_sum_pretrade_NAV_units": float(
            sum(r["transaction_cost_per_pretrade_nav"] for r in rows)
        ),
        "short_cost_sum_pretrade_NAV_units": float(
            sum(r["short_cost_per_pretrade_nav"] for r in rows)
        ),
        "mean_short_notional": float(np.mean([r["short_notional"] for r in rows])),
    }
