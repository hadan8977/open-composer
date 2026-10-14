"""Policy views over native cash/fill reports, not a fill or account engine.

Actual cash debits/credits and order matching belong to NautilusTrader. This
adapter supplies the explicit reservations, T+1 restriction and feedback view.
No IO and no automatic execution entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from decision_system import Book, Intent, State


@dataclass
class Lot:
    submitted_R0: float
    bought_dollars: float = 0
    sold_dollars: float = 0
    fees: float = 0
    quantity: int = 0


class NativeBookView:
    def __init__(self, parameters: dict, cost_bps_per_side: float):
        self.p = parameters
        self.cost_bps = cost_bps_per_side
        self.reserved: dict[str, Intent] = {}
        self.unsettled: list[tuple[int, float]] = []
        self.lots: dict[str, Lot] = {}
        self.closed_R: list[float] = []
        self.month: str | None = None
        self.month_start = 20_000.0
        self.month_peak = 20_000.0
        self.month_new_risk = 0.0
        self.pause_session: int | None = None
        self.resume_session: int | None = None
        self.resume_peak: float | None = None
        self.closed_at_pause = 0
        self.path_unknown = False
        self.unknown_reasons: list[str] = []
        self.first_unknown: dict | None = None
        self.unknown_callback = None

    def mark_unknown(self, reason: str):
        if self.path_unknown:
            return
        self.path_unknown = True
        self.unknown_reasons.append(reason)
        self.first_unknown = dict(
            reason=reason,
            known_prefix_closed_R=list(self.closed_R),
            feedback=dict(
                pause_session=self.pause_session,
                resume_session=self.resume_session,
                resume_peak=self.resume_peak,
                closed_at_pause=self.closed_at_pause,
                month=self.month,
                month_peak=self.month_peak,
                month_new_risk=self.month_new_risk,
            ),
        )
        if self.unknown_callback is not None:
            self.unknown_callback(self.first_unknown)

    def reserve(self, order: Intent):
        if self.path_unknown or order.id in self.reserved:
            raise ValueError("unknown path or duplicate native-policy reservation")
        self.reserved[order.id] = order
        self.month_new_risk += order.reserved_risk

    def terminal_entry(self, order_id: str, *, quantity: int, price: float, fee: float):
        if self.path_unknown:
            raise ValueError("uninterpretable native entry after first unknown")
        # Only called after the native terminal/cancel acknowledgment, not on
        # an assumed full fill. Reservation release does not reset attempt risk.
        order = self.reserved[order_id]
        if quantity == 0:
            self.reserved.pop(order_id)
            return
        if not 0 < quantity <= order.quantity:
            raise ValueError("native fill exceeds frozen reservation")
        if order.symbol in self.lots:
            raise ValueError("second live entry lot without a completed original lot")
        self.reserved.pop(order_id)
        self.lots[order.symbol] = Lot(
            order.quantity * (order.reference - order.stop),
            quantity * price,
            0,
            fee,
            quantity,
        )

    def terminal_exit(self, symbol: str, *, quantity: int, price: float, fee: float, session: int):
        if self.path_unknown:
            raise ValueError("uninterpretable native exit after first unknown")
        lot = self.lots[symbol]
        if not 0 < quantity <= lot.quantity:
            raise ValueError("native sale exceeds actual lot")
        lot.quantity -= quantity
        lot.sold_dollars += quantity * price
        lot.fees += fee
        # Native CASH accounts credit the sale; policy blocks using that same
        # credit until the next scheduled-session ordinal supplied by calendar.
        self.unsettled.append((session + 1, quantity * price - fee))
        if lot.quantity == 0:
            self.closed_R.append(
                (lot.sold_dollars - lot.bought_dollars - lot.fees) / lot.submitted_R0
            )
            del self.lots[symbol]

    def view(
        self,
        *,
        native_cash: float,
        marks: dict[str, float],
        states: dict[str, State],
        session: int,
        month: str,
    ) -> tuple[Book, int]:
        if self.path_unknown:
            raise ValueError("sticky unknown joint native account path")
        held = {s: st for s, st in states.items() if st.quantity}
        if any(st.path_unknown or s not in marks for s, st in held.items()):
            self.mark_unknown("missing/unknown held mark")
            raise ValueError("unknown held account mark")
        gross = sum(st.quantity * marks[s] for s, st in held.items())
        equity = native_cash + gross
        self.unsettled = [row for row in self.unsettled if row[0] > session]
        if month != self.month:
            self.month = month
            self.month_start = self.month_peak = equity
            self.month_new_risk = 0
        self.month_peak = max(self.month_peak, equity)
        drawdown = 1 - equity / self.month_peak
        if self.pause_session is None and drawdown >= self.p["feedback_pause_drawdown"]:
            self.pause_session = session
            self.closed_at_pause = len(self.closed_R)
        age = 0 if self.pause_session is None else session - self.pause_session
        if self.pause_session is not None and age >= self.p["feedback_pause_sessions"]:
            if self.resume_session is None:
                self.resume_session = session
                self.resume_peak = equity
            self.resume_peak = max(self.resume_peak, equity)
            if 1 - equity / self.resume_peak >= self.p["feedback_pause_drawdown"]:
                self.pause_session = session
                self.closed_at_pause = len(self.closed_R)
                self.resume_session = self.resume_peak = None
                age = 0
            elif (
                len(self.closed_R) - self.closed_at_pause >= 2
                and len(self.closed_R) >= self.p["feedback_closed_trades"]
                and sum(self.closed_R[-self.p["feedback_closed_trades"] :]) >= 0
            ):
                self.pause_session = self.resume_session = self.resume_peak = None
                drawdown = 0
        reserve_cash = sum(o.reserved_cash for o in self.reserved.values())
        reserve_gross = sum(
            o.reserved_cash / (1 + self.cost_bps / 10000) for o in self.reserved.values()
        )
        held_initial_risk = sum(
            st.quantity
            * (
                st.reference * (1 + self.p["entry_price_cap_bps"] / 10000)
                - st.initial_stop
                + self.cost_bps
                / 10000
                * (st.reference * (1 + self.p["entry_price_cap_bps"] / 10000) + st.initial_stop)
            )
            for st in held.values()
        )
        reserved_risk = sum(o.reserved_risk for o in self.reserved.values())
        unsettled = sum(usd for _, usd in self.unsettled)
        names = set(held) | {o.symbol for o in self.reserved.values()}
        feedback_drawdown = (
            max(drawdown, self.p["feedback_pause_drawdown"])
            if self.pause_session is not None
            else 0
        )
        return Book(
            equity,
            max(0, native_cash - unsettled - reserve_cash),
            gross + reserve_gross,
            held_initial_risk + reserved_risk,
            self.month_new_risk,
            self.month_start,
            feedback_drawdown,
            tuple(self.closed_R),
            len(names),
        ), age
