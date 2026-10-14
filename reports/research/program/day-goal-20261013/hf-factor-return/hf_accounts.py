"""Frozen funded share/cash events; reference prices are not certified fills."""

import bisect
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Pending:
    due: str
    side: str
    quantity: int
    target: int
    frozen_at: str
    reference: float | None
    reason: str


class FundedBook:
    def __init__(self, capital, cost, eligible_dates, symbol="SPY"):
        self.initial = float(capital)
        self.cost = float(cost)
        self.cash = float(capital)
        self.q = 0
        self.symbol = symbol
        self.eligible = list(eligible_dates)
        self.pending = None
        self.unsettled = []
        self.dividends = []
        self.orders = []
        self.events = []
        self.fees = 0.0
        self.cash_in_lieu_unknown = False
        self.first_unknown_cil_date = None
        self.cash_roundoff_tolerance = 1e-9

    def due_date(self, day, delay):
        i = bisect.bisect_right(self.eligible, day) + delay - 1
        if i >= len(self.eligible):
            raise ValueError("bound cash calendar does not cover this receivable")
        return self.eligible[i]

    def begin_day(self, day, actions):
        for queue in [self.unsettled, self.dividends]:
            matured = [r for r in queue if r["due"] <= day]
            self.cash += sum(r["amount"] for r in matured)
            for r in matured:
                self.events.append(dict(at=day + " 09:30", event="proxy_cash_available", **r))
                queue.remove(r)
        prior_close_q = self.q
        for a in actions:
            if a["symbol"] != self.symbol or a["ex_date"] != day:
                continue
            if a["type"] == "cash_dividends":
                amount = prior_close_q * a["amount"]
                if amount:
                    self.dividends.append(
                        dict(
                            amount=amount,
                            due=self.due_date(a["payable_date"], 1),
                            ex_date=day,
                            payable_date=a["payable_date"],
                            source_id=a["id"],
                        )
                    )
                    self.events.append(
                        dict(
                            at=day + " 09:30",
                            event="actual_exdate_entitlement",
                            quantity=prior_close_q,
                            amount=amount,
                            source_id=a["id"],
                        )
                    )
            else:
                converted = self.q * a["ratio"]
                whole = math.floor(converted)
                if converted != whole:
                    self.cash_in_lieu_unknown = True
                    self.first_unknown_cil_date = self.first_unknown_cil_date or day
                self.events.append(
                    dict(
                        at=day + " 09:30",
                        event="actual_split",
                        old_quantity=self.q,
                        ratio=a["ratio"],
                        whole_quantity=whole,
                        fractional_entitlement=converted - whole,
                        fractional_cash_and_paydate=None if converted != whole else "not_required",
                        source_id=a["id"],
                    )
                )
                self.q = whole

    def freeze(self, target, known_price, at, due, reason):
        self.pending = None  # Superseded attempts never roll forward.
        actual = int(self.q > 0)
        if target == actual:
            return
        if target == 0:
            quantity, side = self.q, "sell"
        else:
            side = "buy"
            quantity = (
                math.floor(self.cash / (known_price * (1 + self.cost)))
                if known_price is not None and math.isfinite(known_price) and known_price > 0
                else 0
            )
        self.pending = Pending(due, side, quantity, target, at, known_price, reason)

    def attempt(self, at, day, price, first_age=0):
        pending = self.pending
        if pending is None:
            return
        assert pending.due == at, "only the single scheduled reference attempt is allowed"
        self.pending = None
        order = dict(
            at=at,
            day=day,
            side=pending.side,
            quantity=pending.quantity,
            target=pending.target,
            frozen_at=pending.frozen_at,
            known_sizing_reference=pending.reference,
            reason=pending.reason,
            actual_reference=price,
            first_price_age_minutes=first_age,
            cash_before=self.cash,
            q_before=self.q,
            fee=0.0,
            status=None,
        )
        if price is None or not math.isfinite(price) or price <= 0 or first_age > 0:
            order["status"] = "no_fill_reference_not_available_at_scheduled_time"
        elif pending.quantity <= 0:
            order["status"] = "no_fill_invalid_frozen_lot"
        elif pending.side == "buy":
            debit = pending.quantity * price * (1 + self.cost)
            if debit > self.cash + self.cash_roundoff_tolerance:
                order["status"] = "no_fill_cash_gap_whole_buy_skip"
            else:
                assert self.q == 0
                self.q = pending.quantity
                self.cash -= debit
                order["fee"] = pending.quantity * price * self.cost
                order["status"] = "reference_filled"
        else:
            assert pending.quantity == self.q
            proceeds = pending.quantity * price * (1 - self.cost)
            delay = 4 if day < "2018-01-01" else 3
            self.unsettled.append(
                dict(amount=proceeds, due=self.due_date(day, delay), sale_date=day)
            )
            self.q = 0
            order["fee"] = pending.quantity * price * self.cost
            order["status"] = "reference_filled"
        self.fees += order["fee"]
        if -self.cash_roundoff_tolerance < self.cash < 0:
            self.cash = 0.0
        assert self.cash >= 0 and self.q >= 0 and isinstance(self.q, int)
        order.update(cash_after=self.cash, q_after=self.q)
        self.orders.append(order)

    def nav(self, raw_daily_close):
        if self.cash_in_lieu_unknown:
            return None
        if self.q and (raw_daily_close is None or not math.isfinite(raw_daily_close)):
            return None
        return (
            self.cash
            + sum(r["amount"] for r in self.unsettled)
            + sum(r["amount"] for r in self.dividends)
            + (self.q * raw_daily_close if self.q else 0)
        )

    def snapshot(self, day, raw_daily_close):
        return dict(
            date=day,
            nav=self.nav(raw_daily_close),
            cash=self.cash,
            q=self.q,
            unsettled=sum(r["amount"] for r in self.unsettled),
            dividend_receivable=sum(r["amount"] for r in self.dividends),
            unknown_fractional_CIL=self.cash_in_lieu_unknown,
            first_unknown_CIL_date=self.first_unknown_cil_date,
            raw_daily_closing_mark=raw_daily_close,
            fees=self.fees,
            pending=None if self.pending is None else vars(self.pending),
        )


def positive_target(score, h, held):
    if score is None or not math.isfinite(score):
        return 0
    if score > h:
        return 1
    if score < -h:
        return 0
    return int(held)


def run_funded(
    days,
    bars_by_day,
    daily_closes,
    scores,
    actions,
    eligible,
    cost,
    capital=20000,
    symbol="SPY",
    mode="forecast",
):
    """Every boundary is scheduled from the bound clock, never an observed future tail."""
    book = FundedBook(capital, cost, eligible, symbol)
    daily = []
    signals = []
    for j, clock in enumerate(days):
        day = clock["date"]
        mark = daily_closes.get(day)
        if j == 0:
            daily.append(book.snapshot(day, mark))
            continue
        book.begin_day(day, actions)
        bars = bars_by_day.get(day, {})
        n = clock["regular15_windows"]

        def at(k, day=day):
            minute = 570 + 15 * k
            return day + f" {minute // 60:02d}:{minute % 60:02d}"

        def reference(k, col, bars=bars):
            return bars[k][col] if k in bars else None

        def attempt(k, at=at, day=day, reference=reference, bars=bars):
            book.attempt(
                at(k),
                day,
                reference(k, "open"),
                bars[k]["first_price_age_minutes"] if k in bars else 0,
            )

        if mode == "buy_hold":
            if j == 1:
                book.freeze(
                    1,
                    daily_closes.get(days[j - 1]["date"]),
                    days[j - 1]["date"] + " close",
                    at(0),
                    "benchmark_one_initial_buy",
                )
                attempt(0)
            daily.append(book.snapshot(day, mark))
            continue
        book.freeze(0, None, day + " before09:30", at(0), "opening_zero_risk")
        attempt(0)
        for k in range(1, n):
            if book.pending is not None:
                attempt(k)
            known = reference(k - 1, "close")
            if k == n - 1:
                # The known preceding close freezes the night lot at lastbar START.
                book.freeze(1, known, at(k), at(n), "night_priority_known_lot")
                continue
            score = scores.get((day, 570 + 15 * k)) if mode == "forecast" and k >= 4 else None
            if score is not None and not math.isfinite(score):
                score = None
            target = positive_target(score, cost, book.q > 0)
            signals.append(
                dict(
                    at=at(k),
                    score=score,
                    target=target,
                    actual_held=bool(book.q),
                    known_price=known,
                    fallback=score is None or not math.isfinite(score),
                )
            )
            book.freeze(
                target,
                known,
                at(k),
                at(k + 1),
                "forecast" if score is not None else "missing_packet_zero_risk",
            )
        if book.pending is not None:
            book.attempt(at(n), day, reference(n - 1, "close"), 0)
        daily.append(book.snapshot(day, mark))
    return dict(
        daily=daily,
        orders=book.orders,
        events=book.events,
        signals=signals,
        physical_book_complete=not book.cash_in_lieu_unknown
        and all(r["nav"] is not None for r in daily),
        initial=capital,
        cost_each_side=cost,
        reference_fill_only=True,
        verified_real_settlement=False,
        first_unknown_CIL_date=book.first_unknown_cil_date,
        terminal_forced_liquidation=False,
    )
