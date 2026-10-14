"""Unfunded fractional reference-price diagnostics, never a physical 20k account."""

import bisect
import math

import numpy as np

EVENT_DTYPE = np.dtype(
    [
        ("day", "i2"),
        ("minute", "i2"),
        ("target", "i1"),
        ("status", "i1"),
        ("q_before", "f8"),
        ("q_after", "f8"),
        ("price", "f8"),
        ("fee", "f8"),
    ]
)


RULES = ("Sign", "Positive", "SSign", "SPositive")


def diagnostic_inventory(ids):
    assert len(ids) == 20 and len(set(ids)) == 20
    return [(name, bps, rule, lag)
            for name in ids for bps in (0, 1, 5, 20, 40)
            for rule in RULES for lag in (0, 1)]


def desired(score, cost, rule, held):
    if rule not in RULES:
        raise ValueError("Unknown signal rule: " + str(rule))
    if score is None or not math.isfinite(score):
        return 0
    if rule in ("Sign", "Positive"):
        # Source equations 4/5 include zero in the positive branch.
        return 1 if score >= 0 else (-1 if rule == "Sign" else 0)
    if score > cost:
        return 1
    if score < -cost:
        return -1 if rule == "SSign" else 0
    return held


def run_fractional(days, bars, marks, scores, actions, eligible, cost, rule, night, latency):
    cash, q = 1.0, 0.0
    receivable = []
    pending = None
    events = []
    nav = np.ones(len(days))
    fees = np.zeros(len(days))
    borrow = np.zeros(len(days))
    gross = np.zeros(len(days))
    exposure = []
    overnight_gross = np.full(len(days), np.nan)
    overnight_exposure = np.zeros(len(days), dtype=np.int8)
    overnight_gross[0] = 0.0
    fees_total = 0.0
    borrow_total = 0.0
    for i, clock in enumerate(days):
        day = clock["date"]
        n = clock["regular15_windows"]
        if i == 0:
            exposure.extend([0] * n)
            continue
        overnight_exposure[i] = int(np.sign(q))
        matured = [r for r in receivable if r[0] <= day]
        cash += sum(r[1] for r in matured)
        for r in matured:
            receivable.remove(r)
        for a in actions:
            if a["symbol"] == "SPY" and a["type"] == "cash_dividends" and a["ex_date"] == day and q:
                due = eligible[bisect.bisect_right(eligible, a["payable_date"])]
                receivable.append((due, q * a["amount"]))
        before_fees, before_borrow = fees_total, borrow_total
        daybars = bars.get(day, {})
        opening = daybars.get(0)
        if q == 0 or (opening and opening["first_price_age_minutes"] == 0):
            pretrade_nav = cash + sum(r[1] for r in receivable)
            if q:
                pretrade_nav += q * opening["open"]
            overnight_gross[i] = (pretrade_nav - nav[i - 1]) / nav[i - 1]


        def fill(target, minute, price, age=0, i=i):
            nonlocal cash, q, fees_total
            held = int(np.sign(q))
            if held == target:
                return
            old = q
            if price is None or age > 0:
                events.append(
                    (i, minute, target, 0, old, q, np.nan if price is None else price, 0.0)
                )
                return
            wealth = cash + sum(r[1] for r in receivable) + q * price
            # Deliberate zero-latency fractional diagnostic sizing, no funding/ETB promise.
            new = target * wealth / price
            fee = abs(new - old) * price * cost
            cash -= (new - old) * price + fee
            q = new
            fees_total += fee
            events.append((i, minute, target, 1, old, q, price, fee))

        def attempt(k, target, daybars=daybars):
            row = daybars.get(k)
            fill(
                target,
                570 + 15 * k,
                row["open"] if row else None,
                row["first_price_age_minutes"] if row else 0,
            )

        attempt(0, 0)
        pending = None
        for k in range(n):
            if pending is not None:
                target, due = pending
                assert due == k
                attempt(k, target)
                pending = None
            if 0 < k < n - 1:
                score = scores.get((day, 570 + 15 * k)) if k >= 4 else None
                target = desired(score, cost, rule, int(np.sign(q)))
                if latency == 0:
                    attempt(k, target)
                else:
                    pending = (target, k + 1)
            if k == n - 1:
                pending = None  # Night rule supersedes closing-due intraday decisions.
            exposure.append(int(np.sign(q)))
            row = daybars.get(k)
            if q < 0 and row:
                charge = abs(q) * row["close"] * 0.02 / (252 * 26)
                cash -= charge
                borrow_total += charge
        last = daybars.get(n - 1)
        fill(1 if night else 0, 570 + 15 * n, last["close"] if last else None)
        if q < 0:
            # APP overnight slab; source annual borrowing basis is not exactly reproduced.
            charge = abs(q) * marks[day] * 0.02 / 252
            cash -= charge
            borrow_total += charge
        nav[i] = cash + sum(r[1] for r in receivable) + q * marks[day]
        fees[i] = fees_total - before_fees
        borrow[i] = borrow_total - before_borrow
        gross[i] = (nav[i] - nav[i - 1] + fees[i] + borrow[i]) / nav[i - 1]
    return dict(
        nav=nav,
        gross_daily=gross,
        overnight_gross_daily=overnight_gross,
        intraday_gross_daily=gross - overnight_gross,
        intraday_net_daily=gross - overnight_gross - (fees + borrow) / np.r_[1.0, nav[:-1]],
        overnight_exposure=overnight_exposure,
        overnight_attribution=(
            "Prior independent daily close to current nominal 09:30 raw open, "
            "including ex-date entitlement; unavailable opening with holdings is N/A. "
            "All same-day turnover fees/borrow are attributed to the intraday component; "
            "components are additive to that day's continuous net NAV return, "
            "not separately reinvested or independently simulated accounts."
        ),
        rule=rule,
        overnight_target=1 if night else 0,
        fees=fees,
        borrow=borrow,
        events=np.array(events, dtype=EVENT_DTYPE),
        exposure=np.array(exposure, dtype=np.int8),
        funded=False,
        borrow_ETB_verified=False,
        actual_quotes_fills=False,
        borrowing_APP=(
            "2%/252/26 per completed intraday interval plus2%/252 if a short remains overnight; "
            "incomplete observed interval is not invented"
        ),
        source_exact_original_quoted_cost_or_grossvol_Sharpe_reproduction=False,
    )
