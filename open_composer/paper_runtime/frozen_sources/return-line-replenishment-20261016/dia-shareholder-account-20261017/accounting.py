"""Narrow raw-share adapter to the accepted close/NAV funded-account convention.

The old funded root and cashbook event order are retained. Added state translates
frozen multi-stock targets into raw shares, dated dividends and funded lots.
No signal, provider, order API, strategy search or general execution platform.
"""

import bisect
import copy
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.tseries.holiday import GoodFriday, USFederalHolidayCalendar


def settlement_calendar(start="2024-01-01", end="2027-02-01"):
    # Standard regular-way calendar: federal-bank holidays and Good Friday.
    # Jan9,2025 was a valid settlement date despite the exchange closure.
    holidays = set(USFederalHolidayCalendar().holidays(start, end).strftime("%Y-%m-%d"))
    holidays.update(GoodFriday.dates(start, end).strftime("%Y-%m-%d"))
    return [
        str(d.date())
        for d in pd.date_range(start, end)
        if d.weekday() < 5 and str(d.date()) not in holidays
    ]


def cash_due_date(day, calendar, dividend=False):
    offset = 1 if dividend else (2 if day < "2024-05-28" else 1)
    i = bisect.bisect_right(calendar, day)
    assert i + offset - 1 < len(calendar), "Settlement calendar exhausted"
    return calendar[i + offset - 1]


@dataclass
class CashState:
    cash: float = 20000.0
    sales: list = field(default_factory=list)
    purchases: list = field(default_factory=list)
    dividends: list = field(default_factory=list)
    lots: dict = field(default_factory=dict)
    next_id: int = 0

    def quantity(self, symbol):
        return sum(v["quantity"] for v in self.lots.get(symbol, []))

    def nav_cash(self):
        return (
            self.cash
            + sum(v["amount"] for v in self.sales)
            + sum(v["amount"] for v in self.dividends)
            - sum(v["amount"] for v in self.purchases)
        )

    def settle(self, day):
        received_sales = [v for v in self.sales if v["due"] <= day]
        received_div = [v for v in self.dividends if v["due"] <= day]
        paid = [v for v in self.purchases if v["due"] <= day]
        # Net same-day credits/debits once; receivables/liabilities are removed.
        self.cash += (
            sum(v["amount"] for v in received_sales)
            + sum(v["amount"] for v in received_div)
            - sum(v["amount"] for v in paid)
        )
        ids = {v["id"] for v in received_sales}
        for ap in self.purchases:
            for part in ap["funding"]:
                if part["source"] in ids:
                    part["source"] = "cash"
        self.sales = [v for v in self.sales if v["due"] > day]
        self.dividends = [v for v in self.dividends if v["due"] > day]
        self.purchases = [v for v in self.purchases if v["due"] > day]
        assert self.cash >= -1e-7, "Settlement deficit / borrowing"
        return dict(
            sale_cash=sum(v["amount"] for v in received_sales),
            dividend_cash=sum(v["amount"] for v in received_div if v.get("kind") == "dividend"),
            terminal_cash=sum(
                v["amount"] for v in received_div if v.get("kind") == "terminal_cash"
            ),
            purchase_cash=sum(v["amount"] for v in paid),
        )

    def free_cash(self):
        reserved = sum(
            part["amount"]
            for ap in self.purchases
            for part in ap["funding"]
            if part["source"] == "cash"
        )
        assert self.cash - reserved >= -1e-7, "Cash reused across obligations"
        return max(0.0, self.cash - reserved)

    def available(self, due):
        return self.free_cash() + sum(v["unreserved"] for v in self.sales if v["due"] <= due)

    def sell(self, symbol, quantity, price, fee, day, due):
        unlocked = sum(v["quantity"] for v in self.lots.get(symbol, []) if v["funded"] <= day)
        quantity = min(quantity, unlocked)
        remaining = quantity
        for lot in self.lots.get(symbol, []):
            if lot["funded"] > day:
                continue
            used = min(remaining, lot["quantity"])
            lot["quantity"] -= used
            remaining -= used
        self.lots[symbol] = [v for v in self.lots.get(symbol, []) if v["quantity"] > 1e-10]
        amount = quantity * price * (1 - fee)
        self.next_id += 1
        if quantity > 1e-10:
            self.sales.append(
                dict(id="sale" + str(self.next_id), due=due, amount=amount, unreserved=amount)
            )
        return quantity

    def buy(self, symbol, quantity, price, fee, day, due):
        amount = quantity * price * (1 + fee)
        assert amount <= self.available(due) + 1e-7, "Unaffordable ordinary purchase"
        remaining = amount
        parts = []
        paid = min(remaining, self.free_cash())
        if paid > 0:
            parts.append(dict(source="cash", amount=paid, funded=day))
            remaining -= paid
        for sale in sorted(self.sales, key=lambda v: (v["due"], v["id"])):
            if sale["due"] > due:
                continue
            used = min(remaining, sale["unreserved"])
            if used > 0:
                parts.append(dict(source=sale["id"], amount=used, funded=sale["due"]))
                sale["unreserved"] -= used
                remaining -= used
        assert remaining < 1e-7
        if quantity > 1e-10:
            self.purchases.append(dict(symbol=symbol, due=due, amount=amount, funding=parts))
            for part in parts:
                self.lots.setdefault(symbol, []).append(
                    dict(quantity=quantity * part["amount"] / amount, funded=part["funded"])
                )
        return parts


def target_quantities(nav, holdings, prices, weights, cost, whole):
    """Accepted after-fee root, with a discrete floor in the whole-share arm.

    The discrete map may cycle near a share boundary. The minimum point in the
    cycle reserves at least actual fees; no fitted buffer or opportunistic cash
    sweep is introduced. Fractional root is the accepted continuous fixed point.
    """
    weights = np.asarray(weights, float)
    holdings = np.asarray(holdings, float)
    prices = np.asarray(prices, float)
    assert (
        nav > 0
        and np.isfinite(weights).all()
        and (weights >= 0).all()
        and weights.sum() <= 1 + 1e-9
    )
    needed = (weights > 0) | (holdings > 1e-10)
    assert np.isfinite(prices[needed]).all() and (prices[needed] > 0).all(), (
        "Missing mandatory fill/mark"
    )
    safe = np.where(needed, prices, 1.0)

    def qty(budget):
        result = weights * budget / safe
        return np.floor(result + 1e-12) if whole else result

    budget = nav
    visited = []
    for _ in range(200):
        updated = nav - cost * float(np.abs(qty(budget) - holdings) @ safe)
        assert updated > 0
        if abs(updated - budget) < 1e-10:
            budget = min(budget, updated)
            break
        if whole and any(abs(updated - v) < 1e-10 for v in visited):
            start = next(i for i, v in enumerate(visited) if abs(updated - v) < 1e-10)
            budget = min(visited[start:] + [budget, updated])
            break
        visited.append(budget)
        budget = updated
    else:
        raise ValueError("After-fee share root did not converge")
    result = qty(budget)
    actualfee = cost * float(np.abs(result - holdings) @ safe)
    assert budget + actualfee <= nav + 1e-7, "Cost reserve not funded"
    return result, dict(after_fee_budget=budget, proposed_fees=actualfee)


def convert_shares(state, parent, ratio, child=None):
    """No cash-in-lieu fabrication; conversion preserves lot funding clocks."""
    before = state.quantity(parent)
    if child:
        state.lots.setdefault(child, []).extend(
            dict(quantity=v["quantity"] * ratio, funded=v["funded"])
            for v in state.lots.get(parent, [])
        )
    else:
        for v in state.lots.get(parent, []):
            v["quantity"] *= ratio
    return before * ratio


def simulate(z, intents, dividends, actions, cost, whole, initial_nav=20000):
    """Frozen daily-close cashbook adapter; no account runs on import."""
    all_dates = z["dates"]
    names = z["symbols"].tolist()
    ix = {s: j for j, s in enumerate(names)}
    first = int(z["decisions"][0])
    dates = all_dates[first:].tolist()
    index = {str(d): i for i, d in enumerate(all_dates)}
    calendar = settlement_calendar()
    state = CashState(cash=initial_nav)
    scheduled = {v["execution_close"]: v for v in intents}
    assert len(scheduled) == 33
    rows = []
    orders = []
    events = []
    cvr = 0.0
    locked = {}
    oldmarks = np.zeros(len(names))
    previous = initial_nav
    cumdiv = cumpaid = 0.0
    between_income = np.zeros(len(names))
    credits_since = dict(sale_cash=0.0, dividend_cash=0.0, terminal_cash=0.0, purchase_cash=0.0)
    for stamp in pd.date_range(dates[0], dates[-1]):
        day = str(stamp.date())
        settled = state.settle(day)
        for k, v in settled.items():
            credits_since[k] += v
        cumpaid += settled["dividend_cash"]
        # Apply only legal actions on held source shares. Provider acquisition
        # rows naming a cohort acquirer create no shareholder entitlement.
        # Child ratios are per PRE-conversion parent. Distribute before the
        # simultaneous HON reverse split so .5 child is not multiplied twice.
        for a in actions.get("spin_offs", []):
            if a["ex_date"] != day:
                continue
            amount = convert_shares(
                state, a["source_symbol"], a["new_rate"] / a["source_rate"], a["new_symbol"]
            )
            events.append(dict(date=day, event="child_entitlement", id=a["id"], quantity=amount))
            if whole and abs(amount - round(amount)) > 1e-9:
                # Ordinary whole-share trades cannot sell this fraction. Actual
                # CIL value/timing remain unknown, never spendable cash.
                frac = amount - math.floor(amount)
                locked[a["new_symbol"]] = locked.get(a["new_symbol"], 0.0) + frac
        for a in actions.get("reverse_splits", []) + actions.get("forward_splits", []):
            if a["ex_date"] != day:
                continue
            assert not locked.get(a["symbol"], 0.0), (
                "Unreceived conversion of an already locked fractional entitlement"
            )
            amount = convert_shares(state, a["symbol"], a["new_rate"] / a["old_rate"])
            events.append(dict(date=day, event="share_conversion", id=a["id"], result=amount))
            if whole and abs(amount - round(amount)) > 1e-9:
                locked[a["symbol"]] = amount - math.floor(amount)
        if day == "2025-08-28":
            amount = state.quantity("WBA")
            state.lots["WBA"] = []
            cvr += amount
            state.dividends.append(
                dict(id="WBA_cash", due="2025-08-29", amount=amount * 11.45, kind="terminal_cash")
            )
            between_income[ix["WBA"]] += amount * 11.45
            events.append(
                dict(
                    date=day,
                    event="WBA_legal_conversion",
                    quantity=amount,
                    CVR_added=amount,
                    cash_receivable=amount * 11.45,
                )
            )
        for a in dividends:
            if a["ex_date"] != day:
                continue
            qty = state.quantity(a["symbol"])
            amount = qty * a["rate"]
            cumdiv += amount
            between_income[ix[a["symbol"]]] += amount
            state.dividends.append(
                dict(
                    id=a["id"],
                    due=cash_due_date(a["payable_date"], calendar, dividend=True),
                    amount=amount,
                    kind="dividend",
                )
            )
            events.append(
                dict(
                    date=day,
                    event="dividend_entitlement",
                    id=a["id"],
                    symbol=a["symbol"],
                    preopen_shares=qty,
                    amount=amount,
                    payable_date=a["payable_date"],
                    credit_date=cash_due_date(a["payable_date"], calendar, dividend=True),
                )
            )
        if day not in dates:
            continue
        i = index[day]
        price = z["raw_close"][i]
        hold = np.array([state.quantity(s) for s in names])
        assert np.isfinite(price[hold > 1e-10]).all() and (price[hold > 1e-10] > 0).all(), (
            "Unknown held ordinary mark"
        )
        values = hold * np.where(np.isfinite(price), price, 0.0)
        nav_pre = state.nav_cash() + float(values.sum())
        gross_by_asset = values - oldmarks + between_income
        assert abs(gross_by_asset.sum() - (nav_pre - previous)) < 1e-6, (
            "Daily economic conservation before trades"
        )
        fee = turnover = blocked = shortfall = 0.0
        root = None
        if day in scheduled:
            intent = scheduled[day]
            weights = np.zeros(len(names))
            for s in intent["selected"]:
                if s == "WBA" and day >= "2025-08-28":
                    continue
                weights[ix[s]] = 0.2
            desired, root = target_quantities(nav_pre, hold, price, weights, cost, whole)
            due = cash_due_date(day, calendar)
            # Sell first; funded lots alone may be liquidated. No change to the
            # desired selection when a lot or purchasing budget is unavailable.
            for j, s in enumerate(names):
                request = max(0.0, hold[j] - desired[j] - locked.get(s, 0.0))
                if whole:
                    request = float(math.floor(request + 1e-9))
                if request < 1e-9:
                    continue
                unlocked = sum(v["quantity"] for v in state.lots.get(s, []) if v["funded"] <= day)
                allowed = min(request, float(math.floor(unlocked + 1e-9)) if whole else unlocked)
                filled = state.sell(s, allowed, float(price[j]), cost, day, due)
                if whole and abs(filled - round(filled)) > 1e-7:
                    raise ValueError("Unfunded partial whole-share sale")
                blocked += request - filled
                notional = filled * price[j]
                turnover += notional
                fee += notional * cost
                orders.append(
                    dict(
                        date=day,
                        symbol=s,
                        side="sell",
                        requested=request,
                        filled=filled,
                        price=float(price[j]),
                        fee=float(notional * cost),
                        settlement=due,
                        reason=None if filled >= request - 1e-8 else "funding_not_yet_settled",
                    )
                )
            now = np.array([state.quantity(s) for s in names])
            buys = np.maximum(0.0, desired - now)
            needed = float(buys @ np.where(np.isfinite(price), price, 0.0) * (1 + cost))
            capacity = state.available(due)
            scale = min(1.0, capacity / needed) if needed > 0 else 1.0
            filled_buys = buys * scale
            if whole:
                filled_buys = np.floor(filled_buys + 1e-10)
            shortfall = float((buys - filled_buys) @ np.where(np.isfinite(price), price, 0.0))
            for j, s in enumerate(names):
                qty = float(filled_buys[j])
                if buys[j] < 1e-9:
                    continue
                funding = state.buy(s, qty, float(price[j]), cost, day, due) if qty > 1e-9 else []
                notional = qty * price[j]
                turnover += notional
                fee += notional * cost
                orders.append(
                    dict(
                        date=day,
                        symbol=s,
                        side="buy",
                        requested=float(buys[j]),
                        filled=qty,
                        price=float(price[j]),
                        fee=float(notional * cost),
                        settlement=due,
                        funding=funding,
                        reason=None if qty >= buys[j] - 1e-8 else "cash_shortage_or_whole_floor",
                    )
                )
        hold = np.array([state.quantity(s) for s in names])
        values = hold * np.where(np.isfinite(price), price, 0.0)
        nav = state.nav_cash() + float(values.sum())
        assert nav > 0 and abs(nav - (nav_pre - fee)) < 1e-6
        assert state.free_cash() >= 0 and values.sum() <= nav + 1e-6, "Borrowed leverage"
        if whole:
            for j, s in enumerate(names):
                assert (
                    abs(hold[j] - locked.get(s, 0.0) - round(hold[j] - locked.get(s, 0.0))) < 1e-7
                )
        identified = not cvr and not any(v > 1e-10 for v in locked.values())
        rows.append(
            dict(
                date=day,
                nav_before=previous,
                nav_after=nav,
                net_return=nav / previous - 1,
                pretrade_NAV=nav_pre,
                gross_pnl=float(gross_by_asset.sum()),
                gross_asset_PnL=gross_by_asset.tolist(),
                fees=fee,
                turnover=turnover,
                settled_cash=state.cash,
                free_settled_cash=state.free_cash(),
                sale_receivables=sum(v["amount"] for v in state.sales),
                purchase_payables=sum(v["amount"] for v in state.purchases),
                dividend_receivables=sum(
                    v["amount"] for v in state.dividends if v.get("kind") == "dividend"
                ),
                terminal_cash_receivables=sum(
                    v["amount"] for v in state.dividends if v.get("kind") == "terminal_cash"
                ),
                dividends_earned_cumulative=cumdiv,
                dividends_received_cumulative=cumpaid,
                settlements=credits_since,
                shares=hold.tolist(),
                inventory_values=values.tolist(),
                gross_exposure=float(values.sum() / nav),
                CVR_units=cvr,
                CVR_value_bounds=[0.0, 3 * cvr],
                locked_fractional_entitlements=dict(locked),
                total_wealth_point_identified=identified,
                blocked_sale_shares=blocked,
                unfilled_buy_notional=shortfall,
                cost_root=root,
                pending_sales=[dict(v) for v in state.sales],
                pending_purchases=copy.deepcopy(state.purchases),
                pending_dividends=[dict(v) for v in state.dividends],
            )
        )
        previous = nav
        oldmarks = values.copy()
        between_income = np.zeros(len(names))
        credits_since = dict(sale_cash=0.0, dividend_cash=0.0, terminal_cash=0.0, purchase_cash=0.0)
    assert len(rows) == len(dates)
    return rows, orders, events
