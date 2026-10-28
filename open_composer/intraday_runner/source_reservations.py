"""Pending-order reservations around the accepted source-method CashState.

No broker, clock scheduler, pricing or alternative backtest engine lives here.
The caller journals raw acknowledgments before applying these operations and
atomically persists state under the existing account lock. A submission is not
a fill. Unknown acknowledgments retain both cash and held-share reservations.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any


def _positive(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not money")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("positive finite amount required")
    return value


def _whole(quantity: int) -> int:
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("positive whole shares required")
    return quantity


@dataclass
class SourceReservations:
    cashbook: Any  # Exact manifest-bound accepted CashState, not a broker balance.
    pending: dict[str, dict] = field(default_factory=dict)
    consumed_ids: set[str] = field(default_factory=set)
    applied_fill_ids: set[str] = field(default_factory=set)

    def _new(self, intent_id: str) -> None:
        if not intent_id or intent_id in self.consumed_ids:
            raise ValueError("intent already consumed or missing")

    def cash_reserved(self) -> float:
        # Moving an unchanged reservation to its terminal-liability identity must
        # not change the total solely because dictionary iteration order changed.
        return math.fsum(
            p["amount"]
            for row in self.pending.values()
            for p in row.get("remaining_funding", [])
            if p["source"] == "cash"
        )

    def available(self, due: str) -> float:
        cash = self.cashbook.free_cash() - self.cash_reserved()
        if cash < -1e-7:
            raise ValueError("cash reserved twice")
        return max(0.0, cash) + sum(
            sale["unreserved"] for sale in self.cashbook.sales if sale["due"] <= due
        )

    def reserve_buy(
        self,
        intent_id: str,
        symbol: str,
        quantity: int,
        limit_price: float,
        fee_buffer: float,
        day: str,
        due: str,
    ) -> dict:
        self._new(intent_id)
        quantity = _whole(quantity)
        limit_price = _positive(limit_price)
        if not math.isfinite(fee_buffer) or fee_buffer < 0:
            raise ValueError("invalid fee reservation")
        needed = quantity * limit_price + fee_buffer
        if needed > self.available(due) + 1e-7:
            raise ValueError("unfunded buy reservation")
        remaining = needed
        parts = []
        cash = min(remaining, max(0.0, self.cashbook.free_cash() - self.cash_reserved()))
        if cash:
            parts.append({"source": "cash", "amount": cash, "funded": day})
            remaining -= cash
        for sale in sorted(self.cashbook.sales, key=lambda x: (x["due"], x["id"])):
            if sale["due"] > due:
                continue
            used = min(remaining, sale["unreserved"])
            if used:
                parts.append({"source": sale["id"], "amount": used, "funded": sale["due"]})
                sale["unreserved"] -= used
                remaining -= used
        if remaining > 1e-7:
            raise ValueError("inconsistent source availability")
        row = {
            "side": "buy",
            "symbol": symbol,
            "quantity": quantity,
            "filled": 0,
            "limit_price": limit_price,
            "due": due,
            "original_funding": copy.deepcopy(parts),
            "remaining_funding": parts,
        }
        self.pending[intent_id] = row
        self.consumed_ids.add(intent_id)
        return copy.deepcopy(row)

    def reserve_sell(
        self,
        intent_id: str,
        symbol: str,
        quantity: int,
        limit_price: float,
        day: str,
        due: str,
        *,
        fee_buffer_rate: float,
    ) -> dict:
        self._new(intent_id)
        quantity = _whole(quantity)
        limit_price = _positive(limit_price)
        if not math.isfinite(fee_buffer_rate) or not 0 <= fee_buffer_rate < 1:
            raise ValueError("invalid sell fee buffer")
        funded = sum(
            lot["quantity"] for lot in self.cashbook.lots.get(symbol, []) if lot["funded"] <= day
        )
        locked = sum(
            row["quantity"] - row["filled"]
            for row in self.pending.values()
            if row["side"] == "sell" and row["symbol"] == symbol
        )
        if quantity > math.floor(funded - locked + 1e-9):
            raise ValueError("sell exceeds unreserved funded own shares")
        row = {
            "side": "sell",
            "symbol": symbol,
            "quantity": quantity,
            "filled": 0,
            "limit_price": limit_price,
            "due": due,
            "fee_buffer_rate": fee_buffer_rate,
            "remaining_funding": [],
            "original_funding": [],
            "confirmed_fee_funding": [],
        }
        self.pending[intent_id] = row
        self.consumed_ids.add(intent_id)
        return copy.deepcopy(row)

    def _fill(self, intent_id: str, fill_id: str, quantity: int, price: float) -> dict:
        if not fill_id or fill_id in self.applied_fill_ids:
            raise ValueError("fill missing or already applied")
        row = self.pending[intent_id]
        _whole(quantity)
        _positive(price)
        if quantity > row["quantity"] - row["filled"]:
            raise ValueError("fill exceeds remaining submitted shares")
        if (row["side"] == "buy" and price > row["limit_price"]) or (
            row["side"] == "sell" and price < row["limit_price"]
        ):
            raise ValueError(
                "actual price breached limit; retain raw fill and halt for reconciliation"
            )
        return row

    @staticmethod
    def _consume(row: dict, amount: float) -> list[dict]:
        if amount > sum(p["amount"] for p in row["remaining_funding"]) + 1e-7:
            raise ValueError("actual liability exceeds reservation; retain raw evidence and halt")
        parts = []
        for source in row["remaining_funding"]:
            used = min(amount, source["amount"])
            if used:
                parts.append({**source, "amount": used})
                source["amount"] -= used
                amount -= used
        return parts

    def confirmed_fill(
        self,
        intent_id: str,
        fill_id: str,
        quantity: int,
        price: float,
        day: str,
    ) -> dict:
        """Apply a NEW confirmed execution delta, never requested/cumulative shares."""
        row = self._fill(intent_id, fill_id, quantity, price)
        symbol = row["symbol"]
        if row["side"] == "sell":
            # No model fee is invented as a broker debit. Actual fees are separate.
            working = copy.deepcopy(self.cashbook)
            done = working.sell(symbol, quantity, price, 0.0, day, row["due"])
            if abs(done - quantity) > 1e-7:
                raise ValueError("confirmed sale does not match owned funded lots; halt")
            self.cashbook = working
            sale = self.cashbook.sales[-1]
            fee_reserve = quantity * price * row["fee_buffer_rate"]
            sale["unreserved"] -= fee_reserve
            fee_part = {"source": sale["id"], "amount": fee_reserve, "funded": sale["due"]}
            row["remaining_funding"].append(fee_part)
            # This source exists only after this actual fill, never at request time.
            row["confirmed_fee_funding"].append(copy.deepcopy(fee_part))
            funding = []
        else:
            amount = quantity * price
            funding = self._consume(row, amount)
            self.cashbook.purchases.append(
                {
                    "symbol": symbol,
                    "due": row["due"],
                    "amount": amount,
                    "funding": copy.deepcopy(funding),
                }
            )
            for part in funding:
                self.cashbook.lots.setdefault(symbol, []).append(
                    {
                        # One complete funding source owns the exact execution
                        # quantity. Multiplying then dividing equal float amounts
                        # can fabricate a fractional share (11.000000000000002).
                        # Split funding retains its original date/amount partition.
                        "quantity": quantity
                        if len(funding) == 1 and part["amount"] == amount
                        else quantity * part["amount"] / amount,
                        "funded": part["funded"],
                    }
                )
        row["filled"] += quantity
        self.applied_fill_ids.add(fill_id)
        return {
            "intent_id": intent_id,
            "fill_id": fill_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "funding": copy.deepcopy(funding),
        }

    def confirmed_fee(self, intent_id: str, fee_id: str, amount: float) -> dict:
        """Actual matched fee only, not the reserved/model amount or a second debit."""
        if not fee_id or fee_id in self.applied_fill_ids:
            raise ValueError("fee missing or already applied")
        amount = _positive(amount)
        row = self.pending[intent_id]
        funding = self._consume(row, amount)
        self.cashbook.purchases.append(
            {
                "symbol": row["symbol"],
                "kind": "actual_fee",
                "due": row["due"],
                "amount": amount,
                "funding": copy.deepcopy(funding),
            }
        )
        self.applied_fill_ids.add(fee_id)
        return {"fee_id": fee_id, "amount": amount, "funding": copy.deepcopy(funding)}

    def release(self, intent_id: str, *, terminal_confirmed: bool, fees_reconciled: bool) -> None:
        if terminal_confirmed is not True or fees_reconciled is not True:
            raise ValueError(
                "unknown/cancel-pending or unreconciled fee cannot release reservation"
            )
        row = self.pending[intent_id]
        sales = {s["id"]: s for s in self.cashbook.sales}
        for part in row.get("remaining_funding", []):
            if part["source"] != "cash":
                sales[part["source"]]["unreserved"] += part["amount"]
        del self.pending[intent_id]

    def settle(
        self,
        day: str,
        *,
        broker_settlement_verified: bool,
        received_cash_ids: set[str],
    ) -> dict:
        if broker_settlement_verified is not True:
            raise ValueError("calendar alone cannot certify actual broker settlement")
        ids = {s["id"] for s in self.cashbook.sales if s["due"] <= day}
        working = copy.deepcopy(self.cashbook)
        unreceived = [d for d in working.dividends if d["id"] not in received_cash_ids]
        working.dividends = [d for d in working.dividends if d["id"] in received_cash_ids]
        result = working.settle(day)
        working.dividends.extend(unreceived)
        self.cashbook = working
        for row in self.pending.values():
            for part in row.get("remaining_funding", []):
                if part["source"] in ids:
                    part["source"] = "cash"
        # original_funding is immutable; settling must not rewrite provenance.
        self.available(day)
        return result
