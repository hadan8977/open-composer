"""Fixed L1 HF policies and partial cash accounting; no automatic market execution."""

from __future__ import annotations

import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hf_accounts import FundedBook  # noqa: E402

GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
TOL = 1e-12


def finite_price(value):
    return value is not None and math.isfinite(value) and value > 0


def scheduled_reference_available(row, endpoint):
    """The approved raw15 reference must exist at its scheduled minute.

    Close is the last one-minute close at window_minute+14, not the next
    interval's open. Missing clock metadata never certifies completeness.
    """
    age = (
        "first_price_age_minutes" if endpoint == "open" else "last_price_age_to_window_end_minutes"
    )
    return finite_price(row.get(endpoint)) and row.get(age) == 0


def stamp(day, minute):
    return f"{day} {minute // 60:02d}:{minute % 60:02d}"


@dataclass(frozen=True)
class Clock:
    day: str
    decision_minute: int
    session_close_minute: int

    def __post_init__(self):
        assert self.decision_minute >= 585 and (self.decision_minute - 570) % 15 == 0
        assert self.session_close_minute in (780, 960)

    @property
    def feature_interval(self):
        return self.decision_minute - 15, self.decision_minute

    @property
    def original_label_interval(self):
        return self.decision_minute, self.decision_minute + 15

    @property
    def execution_minute(self):
        return self.decision_minute + 15

    @property
    def remaining_intraday_windows(self):
        return max(0, (self.session_close_minute - self.execution_minute) // 15)

    def payoff_intervals(self, horizon):
        count = min(horizon, self.remaining_intraday_windows)
        return [
            (self.execution_minute + 15 * i, self.execution_minute + 15 * (i + 1))
            for i in range(count)
        ]

    def record(self):
        return {
            "date": self.day,
            "conditional_feature_available_at": stamp(self.day, self.decision_minute),
            "known_sizing_price_interval": self.feature_interval,
            "original_label_interval": self.original_label_interval,
            "execution_at": stamp(self.day, self.execution_minute),
            "original_label_ended_at_execution": True,
            "L_windows": 1,
            "remaining_intraday_windows": self.remaining_intraday_windows,
            "post_delay_payoff_intervals_H16": self.payoff_intervals(16),
            "no_overnight_in_intraday_lifetime": True,
        }


@dataclass(frozen=True)
class Policy:
    policy_id: str
    horizon: int
    rho: float
    gamma: float = 10.0


POLICIES = {
    "CONT_H1_SLOW": Policy("CONT_H1_SLOW", 1, 2 ** (-1 / 4)),
    "DP_H16_FAST": Policy("DP_H16_FAST", 16, 0.5),
    "DP_H16_SLOW": Policy("DP_H16_SLOW", 16, 2 ** (-1 / 4)),
}


def future_mu(score, rho, count):
    assert math.isfinite(score) and 0 < rho < 1 and count >= 0
    return tuple(math.expm1(rho ** (1 + i) * score) for i in range(count))


def _states(held):
    assert -TOL <= held <= 1 + TOL
    held = min(1.0, max(0.0, held))
    return tuple(sorted(set((*GRID, held))))


def path_value(path, held, anchor, mu, variance, cost, gamma):
    """Planning fees are equity-return utility terms, never account cash."""
    assert len(path) == len(mu) == len(variance)
    previous = held
    value = 0.0
    for weight, expected, var in zip(path, mu, variance, strict=True):
        active = weight - anchor
        value += expected * active - gamma / 2 * var * active**2
        value -= cost * abs(weight - previous)
        previous = weight
    value -= cost * abs(previous - anchor)
    return value


def exhaustive_first_action(held, anchor, mu, variance, cost, gamma=10.0):
    states = _states(held)
    if not mu:
        return held, -cost * abs(held - anchor)
    best_path = None
    best_value = -math.inf
    for path in itertools.product(states, repeat=len(mu)):
        value = path_value(path, held, anchor, mu, variance, cost, gamma)
        rank = tuple(
            (abs(w - p), abs(w - anchor), w) for p, w in zip((held, *path[:-1]), path, strict=True)
        )
        if value > best_value + 1e-14 or (
            abs(value - best_value) <= 1e-14 and (best_path is None or rank < best_path[1])
        ):
            best_value, best_path = value, (path, rank)
    return best_path[0][0], best_value


def dynamic_first_action(held, anchor, mu, variance, cost, gamma=10.0):
    assert 0 <= anchor <= 1 and cost >= 0 and gamma >= 0
    assert len(mu) == len(variance) and all(math.isfinite(x) for x in mu)
    assert all(math.isfinite(x) and x >= 0 for x in variance)
    states = _states(held)
    held = min(1.0, max(0.0, held))
    if not mu:
        return held, -cost * abs(held - anchor)
    # Exact upper bound: starting at anchor, any excursion and terminal return
    # costs >=2*c*max_excursion, while total benefit is <=sum(abs(mu))*max_excursion.
    # Risk penalty is non-negative; therefore staying at anchor is optimal here.
    if held == anchor and sum(abs(x) for x in mu) <= 2 * cost:
        return held, 0.0
    values = {w: -cost * abs(w - anchor) for w in states}
    choices = {}
    for expected, var in reversed(list(zip(mu, variance, strict=True))):
        next_values, next_choices = {}, {}
        for previous in states:
            candidates = []
            for weight in states:
                active = weight - anchor
                utility = expected * active - gamma / 2 * var * active**2
                utility -= cost * abs(weight - previous)
                candidates.append((utility + values[weight], weight))
            maximum = max(value for value, _ in candidates)
            ties = [(value, w) for value, w in candidates if maximum - value <= 1e-14]
            value, chosen = min(
                ties, key=lambda item: (abs(item[1] - previous), abs(item[1] - anchor), item[1])
            )
            next_values[previous], next_choices[previous] = value, chosen
        values, choices = next_values, next_choices
    return choices[held], values[held]


@dataclass(frozen=True)
class PartialOrder:
    due: str
    side: str
    quantity: int
    target_quantity: int
    target_weight: float
    frozen_at: str
    reference: float | None
    nav_known: float | None
    available_cash_known: float
    held_quantity_known: int
    receivables_known: float
    decision_cash_sufficient: bool
    reason: str


def target_quantity(held_q, known_nav, known_price, weight, cost):
    """Largest integer satisfying target post-fee weight at the decision-known price."""
    assert isinstance(held_q, int) and held_q >= 0 and 0 <= weight <= 1
    assert finite_price(known_price) and math.isfinite(known_nav) and known_nav > 0
    assert 0 <= cost < 1
    held_weight = held_q * known_price / known_nav
    if math.isclose(weight, held_weight, rel_tol=0, abs_tol=1e-14):
        return held_q
    if weight > held_weight:
        raw = weight * (known_nav + cost * held_q * known_price)
        raw /= known_price * (1 + cost * weight)
    else:
        raw = weight * (known_nav - cost * held_q * known_price)
        raw /= known_price * (1 - cost * weight)
    return max(0, math.floor(raw + 1e-12))


class ShareBook(FundedBook):
    """Reuse accepted actions/receivables/NAV only; replace binary order arithmetic."""

    def freeze(self, *args, **kwargs):
        raise RuntimeError("Binary FundedBook.freeze is forbidden for partial positions")

    def freeze_weight(self, weight, known_price, at, due, reason, reduction_only=False):
        self.pending = None
        assert 0 <= weight <= 1
        nav = self.nav(known_price) if finite_price(known_price) else None
        if nav is None or nav <= 0:
            desired = self.q
            side, quantity = "invalid", 0
        else:
            desired = target_quantity(self.q, nav, known_price, weight, self.cost)
            if reduction_only and desired >= self.q:
                self.events.append(
                    {
                        "at": at,
                        "event": "missing_packet_no_permitted_absolute_risk_reduction",
                        "q": self.q,
                        "anchor_target_quantity": desired,
                    }
                )
                return None
            if desired == self.q:
                return None
            side = "buy" if desired > self.q else "sell"
            quantity = abs(desired - self.q)
        sufficient = side != "buy" or quantity * known_price * (1 + self.cost) <= self.cash + 1e-9
        self.pending = PartialOrder(
            due,
            side,
            quantity,
            desired,
            weight,
            at,
            known_price,
            nav,
            self.cash,
            self.q,
            sum(r["amount"] for r in self.unsettled + self.dividends),
            sufficient,
            reason,
        )
        return self.pending

    def attempt(self, at, day, price, first_age=0):
        pending = self.pending
        if pending is None:
            return None
        assert isinstance(pending, PartialOrder) and pending.due == at
        self.pending = None
        order = {
            **vars(pending),
            "at": at,
            "day": day,
            "frozen_at": pending.frozen_at,
            "known_sizing_reference": pending.reference,
            "actual_reference": price,
            "first_price_age_minutes": first_age,
            "cash_before": self.cash,
            "q_before": self.q,
            "fee": 0.0,
            "status": None,
        }
        if not finite_price(price) or first_age != 0:
            order["status"] = "no_fill_reference_not_available_at_scheduled_time"
        elif self.q != pending.held_quantity_known:
            order["status"] = "no_fill_corporate_action_changed_frozen_inventory"
        elif pending.quantity <= 0 or pending.side == "invalid":
            order["status"] = "no_fill_invalid_frozen_lot"
        elif not pending.decision_cash_sufficient:
            order["status"] = "no_fill_known_settled_cash_shortfall_whole_buy_skip"
        elif pending.side == "buy":
            debit = pending.quantity * price * (1 + self.cost)
            if debit > self.cash + 1e-9:
                order["status"] = "no_fill_cash_gap_whole_buy_skip"
            else:
                self.q += pending.quantity
                self.cash -= debit
                order["fee"] = pending.quantity * price * self.cost
                order["status"] = "reference_filled"
        else:
            assert pending.side == "sell" and pending.quantity <= self.q
            proceeds = pending.quantity * price * (1 - self.cost)
            delay = 4 if day < "2018-01-01" else 3
            self.unsettled.append(
                {
                    "amount": proceeds,
                    "due": self.due_date(day, delay),
                    "sale_date": day,
                }
            )
            self.q -= pending.quantity
            order["fee"] = pending.quantity * price * self.cost
            order["status"] = "reference_filled"
        self.fees += order["fee"]
        if -1e-9 < self.cash < 0:
            self.cash = 0.0
        assert self.cash >= 0 and isinstance(self.q, int) and self.q >= 0
        order.update(cash_after=self.cash, q_after=self.q)
        self.orders.append(order)
        return order


class PassiveAnchor:
    """Same-capital physical passive reference, with its own exact cash/actions events."""

    def __init__(self, capital, cost, eligible, anchor):
        assert anchor in (0, 1)
        self.anchor = anchor
        self.book = ShareBook(capital, cost, eligible)

    def initialize(self, known_price, frozen_at, due, day, actual_open, age=0):
        if self.anchor == 1:
            self.book.freeze_weight(1, known_price, frozen_at, due, "passive_initial_buy")
            self.book.attempt(due, day, actual_open, age)

    def weight(self, known_price):
        nav = self.book.nav(known_price)
        if nav is None or nav <= 0 or not finite_price(known_price):
            return None
        return self.book.q * known_price / nav


class MissingState:
    def __init__(self):
        self.consecutive = 0

    def observe(self, score, structural_immaturity=False):
        if structural_immaturity:
            return "structural_hold"
        if score is not None and math.isfinite(score):
            self.consecutive = 0
            return "forecast"
        self.consecutive += 1
        return "missing_reduce_only" if self.consecutive >= 4 else "missing_hold"


def signal_usable(score, packet_present, decision_minute, session_close_minute):
    """Future label/maturity/outcome masks are intentionally not arguments."""
    return (
        packet_present
        and score is not None
        and math.isfinite(score)
        and decision_minute >= 630
        and Clock("2000-01-01", decision_minute, session_close_minute).remaining_intraday_windows
        > 0
    )


def variance_before_day(history, day):
    """Fixed causal RMS of prior complete session returns; no trained risk estimator."""
    prior = sorted((d, returns) for d, returns in history.items() if d < day)[-63:]
    if len(prior) < 30:
        return 0.004**2
    values = [r * r for _, returns in prior for r in returns if math.isfinite(r)]
    return sum(values) / len(values) if values else 0.004**2


def neutral_weight_before_day(exposure_history, day, anchor):
    """Use exactly the previous63 completed sessions, never today's realized exposure."""
    prior = sorted((d, w) for d, w in exposure_history.items() if d < day)[-63:]
    if len(prior) < 63 or any(w is None or not math.isfinite(w) for _, w in prior):
        return anchor
    return sum(w for _, w in prior) / 63


def run_policy_book(
    days,
    bars_by_day,
    marks,
    scores,
    actions,
    eligible,
    policy,
    anchor,
    cost,
    capital=20000,
    exposure_history=None,
    resume_state=None,
    on_complete_day=None,
):
    """Called only by the guarded financial producer; tests pass synthetic inputs."""
    assert anchor in (0, 1) and cost in (0.002, 0.004)
    book = ShareBook(capital, cost, eligible)
    passive = PassiveAnchor(capital, cost, eligible, anchor)
    missing = MissingState()
    daily, signals, exposure, return_history = [], [], {}, {}
    start = 0
    if resume_state is not None:
        start = resume_state["next_day_index"]
        assert (
            0 < start <= len(days) and resume_state["daily"][-1]["date"] == days[start - 1]["date"]
        )
        book, passive, missing = [resume_state[k] for k in ("book", "passive", "missing")]
        daily, signals, exposure, return_history = [
            resume_state[k] for k in ("daily", "signals", "exposure", "return_history")
        ]

    def publish_completed_day(index):
        if on_complete_day is not None:
            on_complete_day(
                {
                    "next_day_index": index + 1,
                    "book": book,
                    "passive": passive,
                    "missing": missing,
                    "daily": daily,
                    "signals": signals,
                    "exposure": exposure,
                    "return_history": return_history,
                }
            )

    for j, row in enumerate(days):
        if j < start:
            continue
        day, n = row["date"], row["regular15_windows"]
        bars, mark = bars_by_day.get(day, {}), marks.get(day)
        if j == 0:
            daily.append(book.snapshot(day, mark))
            publish_completed_day(j)
            continue
        book.begin_day(day, actions)
        passive.book.begin_day(day, actions)
        current_variance = variance_before_day(return_history, day)
        previous = days[j - 1]["date"]
        at0 = stamp(day, 570)
        opening = bars.get(0, {}).get("open")
        age0 = bars.get(0, {}).get("first_price_age_minutes", 0)
        if j == 1:
            passive.initialize(marks.get(previous), previous + " close", at0, day, opening, age0)
            if anchor == 1:
                book.freeze_weight(
                    1, marks.get(previous), previous + " close", at0, "passive_initial_buy"
                )
                book.attempt(at0, day, opening, age0)
        elif exposure_history is not None:
            book.attempt(at0, day, opening, age0)
        ratios = []
        for k in range(n):
            minute = 570 + 15 * k
            if k > 0 and book.pending is not None:
                book.attempt(
                    stamp(day, minute),
                    day,
                    bars.get(k, {}).get("open"),
                    bars.get(k, {}).get("first_price_age_minutes", 0),
                )
            open_mark = bars.get(k, {}).get("open")
            nav_at_open = book.nav(open_mark)
            ratios.append(
                book.q * open_mark / nav_at_open
                if scheduled_reference_available(bars.get(k, {}), "open")
                and nav_at_open
                and nav_at_open > 0
                else None
            )
            if k == 0 or exposure_history is not None:
                continue
            clock = Clock(day, minute, 570 + 15 * n)
            if clock.remaining_intraday_windows == 0:
                continue
            price = bars.get(k - 1, {}).get("close")
            b = passive.weight(price)
            known_nav = book.nav(price)
            v = book.q * price / known_nav if finite_price(price) and known_nav else None
            score = scores.get((day, minute))
            if score is not None and not math.isfinite(score):
                score = None
            state = missing.observe(score, structural_immaturity=minute < 630)
            info = {
                "date": day,
                "conditional_feature_available_at": stamp(day, minute),
                "original_label_interval": clock.original_label_interval,
                "execution_at": stamp(day, clock.execution_minute),
                "first_post_delay_interval": clock.payoff_intervals(1)[0],
                "remaining_intraday_windows": clock.remaining_intraday_windows,
                "L_windows": 1,
                "no_overnight_in_intraday_lifetime": True,
                "score_log": score,
                "mode": state,
                "passive_anchor_weight": b,
                "actual_weight": v,
                "known_price": price,
                "target_weight": v,
                "planning_utility": None,
            }
            if b is not None and v is not None:
                due = stamp(day, clock.execution_minute)
                if state == "missing_reduce_only":
                    book.freeze_weight(
                        b, price, stamp(day, minute), due, state, reduction_only=True
                    )
                elif state == "forecast":
                    h = min(policy.horizon, clock.remaining_intraday_windows)
                    mu = future_mu(score, policy.rho, h)
                    var = (current_variance,) * h
                    target, value = dynamic_first_action(v, b, mu, var, cost, policy.gamma)
                    info.update(target_weight=target, planning_utility=value, horizon=h)
                    book.freeze_weight(target, price, stamp(day, minute), due, "forecast")
            signals.append(info)
        assert book.pending is None, "No pending forecast is allowed to execute at close"
        daily.append(book.snapshot(day, mark))
        # Exposure is a same-session average of actual regular15 interval-start
        # ratios. Missing marks retain an incomplete session, not a zero exposure.
        exposure[day] = sum(ratios) / n if all(w is not None for w in ratios) else None
        scheduled_bars = [bars.get(k, {}) for k in range(n)]
        if all(
            scheduled_reference_available(r, "open") and scheduled_reference_available(r, "close")
            for r in scheduled_bars
        ):
            return_history[day] = [r["close"] / r["open"] - 1 for r in scheduled_bars]
        if exposure_history is not None and j + 1 < len(days):
            next_day = days[j + 1]["date"]
            b_close = passive.weight(mark)
            target = neutral_weight_before_day(exposure_history, next_day, b_close or 0)
            book.freeze_weight(
                target,
                mark,
                day + " close",
                stamp(next_day, 570),
                "causal_exposure_control",
            )
        publish_completed_day(j)
    return {
        "daily": daily,
        "orders": book.orders,
        "events": book.events,
        "signals": signals,
        "daily_regular_exposure": exposure,
        "physical_book_complete": not book.cash_in_lieu_unknown
        and all(r["nav"] is not None for r in daily),
        "reference_fill_only": True,
        "verified_real_settlement": False,
        "L_windows": 1,
        "no_overnight_alpha_forecast": True,
        "initial": capital,
        "cost_each_side": cost,
        "anchor": anchor,
        "terminal_forced_liquidation": False,
    }
