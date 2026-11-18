"""Unexecuted task-local feature/label/target adapter over accepted return math.

No source access, estimator fitting or broker interface. Market use occurs only
through the later admitted preparation/runtime after priority resource release.
"""

import numpy as np
import pandas as pd

STOCK = [
    "return1",
    "return5",
    "return21",
    "return63",
    "momentum252_skip21",
    "vol21",
    "vol63",
    "downside_vol21",
    "drawdown63",
]
STATE = [
    "SPY_return5",
    "SPY_return21",
    "SPY_return63",
    "SPY_drawdown252",
    "SPY_vol21",
    "SPY_vol21_over_vol63",
    "cohort_breadth21",
    "cohort_dispersion21",
]
INTERACTIONS = [
    "return21_x_SPY_return21",
    "return5_x_SPY_drawdown252",
    "return21_x_SPY_vol21",
    "return21_x_centered_cohort_breadth21",
]
ARMS = ["RIDGE_STOCK", "RIDGE_STATE", "LGBM_STOCK", "LGBM_STATE", "COHORT_EW"]


def rolling_return(returns, periods):
    """Trailing compounded economic returns, preserving missingness and -100%."""
    r = np.asarray(returns, dtype=float)
    if np.any(np.isfinite(r) & (r < -1)):
        raise ValueError("Economic simple return below -100%")
    valid = pd.DataFrame(np.isfinite(r)).rolling(periods, min_periods=periods).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        logs = np.where(r > -1, np.log1p(r), 0.0)
    logs[~np.isfinite(r)] = np.nan
    cumulative = pd.DataFrame(logs).rolling(periods, min_periods=periods).sum().to_numpy()
    zero = (
        pd.DataFrame((r == -1).astype(float)).rolling(periods, min_periods=periods).sum().to_numpy()
    )
    result = np.where(zero > 0, -1.0, np.expm1(cumulative))
    result[valid != periods] = np.nan
    return result


def trailing_drawdown(returns, periods):
    r = np.asarray(returns, dtype=float)
    out = np.full_like(r, np.nan)
    for d in range(periods - 1, len(r)):
        window = r[d - periods + 1 : d + 1]
        valid = np.isfinite(window).all(axis=0)
        wealth = np.cumprod(1 + np.where(np.isfinite(window), window, 0.0), axis=0)
        peak = np.maximum(1.0, wealth.max(axis=0))
        value = wealth[-1] / peak - 1
        out[d, valid] = value[valid]
    return out


def features(returns, available, spy):
    """Features at close d use only returns/availability through d."""
    r = np.asarray(returns, dtype=float)
    available = np.asarray(available)
    spy = np.asarray(spy, dtype=float)
    assert r.ndim == 2 and available.shape == r.shape and spy.shape == (len(r),)
    assert available.dtype == np.bool_
    if np.any(np.isfinite(r) & (r < -1)) or np.any(np.isfinite(spy) & (spy < -1)):
        raise ValueError("Invalid economic return")
    ret5, ret21, ret63 = [rolling_return(r, k) for k in [5, 21, 63]]
    momentum = np.full_like(r, np.nan)
    momentum[21:] = rolling_return(r, 231)[:-21]
    vol21 = pd.DataFrame(r).rolling(21, min_periods=21).std(ddof=1).to_numpy()
    vol63 = pd.DataFrame(r).rolling(63, min_periods=63).std(ddof=1).to_numpy()
    downside = np.sqrt(
        pd.DataFrame(np.minimum(r, 0.0) ** 2).rolling(21, min_periods=21).mean().to_numpy()
    )
    stock = np.stack(
        [r, ret5, ret21, ret63, momentum, vol21, vol63, downside, trailing_drawdown(r, 63)], axis=-1
    )
    eligible = available & np.isfinite(stock).all(axis=-1)
    sr = spy[:, None]
    s5, s21, s63 = [rolling_return(sr, k)[:, 0] for k in [5, 21, 63]]
    sv21 = pd.Series(spy).rolling(21, min_periods=21).std(ddof=1).to_numpy()
    sv63 = pd.Series(spy).rolling(63, min_periods=63).std(ddof=1).to_numpy()
    ratio = np.divide(sv21, sv63, out=np.full_like(sv21, np.nan), where=sv63 > 0)
    breadth, dispersion = np.full(len(r), np.nan), np.full(len(r), np.nan)
    for d in range(len(r)):
        current = ret21[d, eligible[d]]
        if len(current):
            breadth[d] = np.mean(current > 0)
        if len(current) >= 2:
            dispersion[d] = np.std(current, ddof=1)
    state = np.column_stack(
        [s5, s21, s63, trailing_drawdown(sr, 252)[:, 0], sv21, ratio, breadth, dispersion]
    )
    shared = np.broadcast_to(state[:, None, :], (*r.shape, len(STATE))).copy()
    interaction = np.stack(
        [
            ret21 * s21[:, None],
            ret5 * state[:, 3, None],
            ret21 * sv21[:, None],
            ret21 * (2 * breadth[:, None] - 1),
        ],
        axis=-1,
    )
    return dict(
        stock=stock,
        state=np.concatenate([stock, shared, interaction], axis=-1),
        raw_state=state,
        eligible=eligible,
        state_missing=~np.isfinite(shared),
        eligible_count=eligible.sum(axis=1),
    )


def fixed_labels(returns, eligible, horizon=5, cost=0.001):
    """Next-close unit entry; five held endpoints d+2..d+6, maturity d+6."""
    if horizon != 5 or cost != 0.001:
        raise ValueError("Frozen five-session/10bp target only; no search")
    r = np.asarray(returns, dtype=float)
    eligible = np.asarray(eligible)
    assert eligible.shape == r.shape and eligible.dtype == np.bool_
    if np.any(np.isfinite(r) & (r < -1)):
        raise ValueError("Invalid economic return")
    labels = np.full_like(r, np.nan)
    # 0=not decision-eligible,1=matured,2=tailcensored,3=unknown held path.
    status = np.zeros(r.shape, dtype=np.int8)
    maturity = np.arange(len(r)) + 6
    for d in range(len(r)):
        if d + 6 >= len(r):
            status[d, eligible[d]] = 2
            continue
        path = r[d + 2 : d + 7]
        finite = np.isfinite(path).all(axis=0)
        usable = eligible[d] & finite
        value = np.prod(1 + np.where(np.isfinite(path), path, 0.0), axis=0)
        labels[d, usable] = value[usable] * (1 - cost) - (1 + cost)
        status[d, usable] = 1
        status[d, eligible[d] & ~finite] = 3
    return dict(labels=labels, label_status=status, maturity=maturity)


def monthly_folds(dates, eligible, labels, maturity, first="2024-01-02"):
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    evaluation = np.flatnonzero(dates >= pd.Timestamp(first))
    for month in sorted(set(dates[evaluation].to_period("M"))):
        cutoff = np.flatnonzero(dates < month.start_time)[-1]
        calendar = np.arange(cutoff + 1)[-756:]
        calendar = calendar[dates[calendar] >= pd.Timestamp("2021-01-04")]
        mature_dates = calendar[maturity[calendar] <= cutoff]
        ii, jj = np.where(eligible[mature_dates] & np.isfinite(labels[mature_dates]))
        training_dates = mature_dates[ii]
        counts = np.bincount(training_dates, minlength=len(dates))
        weights = 1 / counts[training_dates] if len(training_dates) else np.array([])
        evaluation_dates = evaluation[dates[evaluation].to_period("M") == month]
        yield dict(
            month=str(month),
            cutoff=int(cutoff),
            calendar_dates=calendar,
            train_d=training_dates,
            train_j=jj,
            weights=weights,
            evaluation_d=evaluation_dates,
            supported=(
                len(training_dates) >= 5000
                and len(np.unique(training_dates)) >= 252
                and len(np.unique(jj)) >= 20
            ),
        )


def targets(dates, returns, eligible, predictions):
    """Thin existing-style drift controller; no fees or account simulation here."""
    dates = np.asarray(dates)
    r = np.asarray(returns, dtype=float)
    eligible = np.asarray(eligible)
    assert r.ndim == 2 and eligible.shape == r.shape and len(dates) == len(r)
    first = int(np.flatnonzero(dates >= "2024-01-02")[0])
    names = list(predictions) + ["COHORT_EW"]
    assert set(predictions) == set(ARMS[:-1])
    events = {name: {} for name in names}
    decision_rows = []
    for d in range(first, len(dates) - 1, 5):
        # Exact bound calendar was checked before outcomes; no hidden tail trade.
        if d + 2 >= len(dates):
            raise ValueError("Scheduled close has no held return mark in frozen calendar")
        valid = np.flatnonzero(eligible[d])
        event = dict(
            decision=str(dates[d]),
            execution_close=str(dates[d + 1]),
            first_held_return=str(dates[d + 2]),
            maturity_index=d + 6,
            full_horizon_matured=d + 6 < len(dates),
            eligible_count=len(valid),
            arms={},
        )
        for name, scores in predictions.items():
            scores = np.asarray(scores)
            assert scores.shape == r.shape
            candidates = [int(j) for j in valid if np.isfinite(scores[d, j]) and scores[d, j] > 0]
            # Original episode order is fixed and used as the stable tie break.
            ranking = sorted(candidates, key=lambda j: (-float(scores[d, j]), j))[:5]
            q = np.zeros(r.shape[1])
            q[ranking] = 0.2
            events[name][d + 2] = q
            event["arms"][name] = dict(
                selected=ranking,
                gross_budget=float(q.sum()),
                missing_scores=int(np.sum(~np.isfinite(scores[d, valid]))),
            )
        q = np.zeros(r.shape[1])
        q[valid] = 1 / max(5, len(valid))
        events["COHORT_EW"][d + 2] = q
        event["arms"]["COHORT_EW"] = dict(selected=valid.tolist(), gross_budget=float(q.sum()))
        decision_rows.append(event)
    out = {}
    for name in names:
        q = np.zeros(r.shape[1])
        values = np.zeros((len(dates) - first, r.shape[1]))
        for ii, day in enumerate(range(first, len(dates))):
            if day in events[name]:
                q = events[name][day].copy()
            elif ii:
                previous_return = r[day - 1]
                if not np.isfinite(previous_return[np.abs(q) > 1e-12]).all():
                    raise ValueError("Unknown actually held return; no cash substitution")
                rr = np.where(np.isfinite(previous_return), previous_return, 0.0)
                denominator = 1 + q @ rr
                if denominator <= 0:
                    raise ValueError("Insolvent account path")
                q = q * (1 + rr) / denominator
            assert (q >= -1e-12).all() and q.sum() <= 1 + 1e-8
            values[ii] = q
        out[name] = values
    return out, decision_rows


def account_summary(rows, target_weights, realized, dates, fee):
    """Preserve accepted core money, recognize fees at actual execution close."""
    raw = np.asarray([row["nav_after"] for row in rows])
    before = np.asarray([row["nav_before"] for row in rows])
    tc = np.asarray([row["transaction_cost_per_pretrade_nav"] for row in rows])
    z = 1 - tc
    closing = raw * np.r_[z[1:], 1.0]
    nav = np.r_[20000.0, closing]
    if not np.allclose(
        raw,
        before * z * (1 + np.asarray([row["gross_portfolio_return"] for row in rows])),
        rtol=1e-11,
    ):
        raise ValueError("Core accounting identity mismatch")
    q = np.asarray(target_weights)
    r = np.asarray(realized)
    if not np.isfinite(r[np.abs(q) > 1e-12]).all():
        raise ValueError("Unknown held return in saved-account reconciliation")
    safe_r = np.where(np.isfinite(r), r, 0.0)
    prev = np.zeros(q.shape[1])
    asset_gross, asset_cost = np.zeros(q.shape[1]), np.zeros(q.shape[1])
    trade_rows, daily_gross, daily_cost = [], [], []
    for k in range(len(rows)):
        traded = before[k] * (z[k] * q[k] - prev)
        costs = np.abs(traded) * fee
        assert np.isclose(costs.sum(), before[k] * tc[k], atol=1e-7)
        assert before[k] * z[k] * (1 - q[k].sum()) >= -1e-7
        asset_cost += costs
        daily_cost.append(costs)
        gross_pnl = before[k] * z[k] * q[k] * safe_r[k]
        daily_gross.append(gross_pnl)
        asset_gross += gross_pnl
        if np.any(np.abs(traded) > 1e-8):
            assert k > 0, "Frozen account starts cash; no unobserved pre-window trade"
            trade_rows.append(
                dict(
                    return_endpoint=str(dates[k]),
                    execution_close=str(dates[k - 1]),
                    signed_notional=traded.tolist(),
                    fees=costs.tolist(),
                    cash_after_trade=float(before[k] * z[k] * (1 - q[k].sum())),
                )
            )
        previous_gross = float(q[k] @ safe_r[k])
        prev = q[k] * (1 + safe_r[k]) / (1 + previous_gross)
    assert np.isclose(asset_gross.sum() - asset_cost.sum(), nav[-1] - 20000, atol=1e-7)
    # Close after any same-close rebalance; finalclose has no fictitious next trade.
    exposure = np.r_[q[1:].sum(axis=1), prev.sum()]
    close_weights = np.vstack([q[1:], prev])
    close_pnl = np.asarray(daily_gross) - np.vstack([daily_cost[1:], np.zeros(q.shape[1])])
    assert np.allclose(close_pnl.sum(axis=1), np.diff(nav), atol=1e-7)
    return dict(
        daily_NAV_with_initial=nav.tolist(),
        daily_net_return=(nav[1:] / nav[:-1] - 1).tolist(),
        mean_actual_executionclose_gross_exposure=float(exposure.mean()),
        mean_pre_return_posttrade_gross_exposure=float(q.sum(axis=1).mean()),
        actual_close_gross_exposure=exposure.tolist(),
        actual_close_stock_values=(close_weights * closing[:, None]).tolist(),
        actual_close_cash=(closing * (1 - exposure)).tolist(),
        daily_stock_net_pnl_USD=close_pnl.tolist(),
        transaction_cost_USD=float(asset_cost.sum()),
        gross_stock_pnl_USD=asset_gross.tolist(),
        net_stock_pnl_USD=(asset_gross - asset_cost).tolist(),
        fees_by_stock_USD=asset_cost.tolist(),
        turnover_pretrade_NAV=float(sum(row["turnover_per_pretrade_nav"] for row in rows)),
        actual_transactions=trade_rows,
        terminal_liquidated=False,
    )
