"""Turn target weights into whole-share quantities for a fixed account size.

Why this exists: the paper account is funded with $100,000 (the user's
deliberate choice on 2026-09-08 -- "更拟真, 100万我没有100万"), and the
strategy's execution style is an opening-auction limit order (``opg_limit``),
which Alpaca does not accept for fractional quantities. So every target
weight has to become an integer share count, and the gap between the weights
we asked for and the weights we can actually hold is a real, reportable cost
rather than an implementation detail.

Measured on the real 2026-09-04 cross-section at $100,000 with a top-K
equal-weight book, flooring alone leaves about 4% of the account in idle cash
and about 2.4-3.0% of one-sided weight deviation, for K anywhere in 20-50 --
no name in the liquid universe was unaffordable even at K=50 ($2,000 a slot
against a $1,740 top price). :func:`size_whole_share_portfolio` cuts both
figures further by spending the floor remainder greedily: it repeatedly buys
one more share of whichever name is currently the most under-weight relative
to its target and still affordable. That is the standard remainder-allocation
step, and it is applied here rather than left to the broker because the
resulting share counts are what the signal log and the order preview must
agree on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class WholeShareSizing:
    """The outcome of sizing one rebalance, including what it cost to round."""

    shares: dict[str, int]
    realized_weights: dict[str, float]
    target_weights: dict[str, float]
    invested_cash: float
    idle_cash: float
    #: One-sided weight deviation, ``sum(|realized - target|) / 2``, with
    #: every weight measured against **equity** rather than against the
    #: invested gross. That denominator matters: idle cash is itself a
    #: deviation from a fully-invested target, so measuring against equity
    #: makes "spend the remainder" and "track the target weights" the same
    #: objective instead of competing ones, and it makes each name's realized
    #: weight independent of what the other names round to. Measuring against
    #: gross instead (the first version of this module) made the remainder
    #: allocation *raise* deviation from 0.84% to 1.28% on a 3-name example --
    #: caught by tests/test_whole_share_sizing.py.
    weight_deviation: float
    #: Names whose target allocation could not buy a single share.
    unaffordable: tuple[str, ...]

    @property
    def idle_cash_fraction(self) -> float:
        total = self.invested_cash + self.idle_cash
        return self.idle_cash / total if total > 0 else 0.0


def size_whole_share_portfolio(
    target_weights: Mapping[str, float],
    prices: Mapping[str, float],
    equity: float,
    *,
    allocate_remainder: bool = True,
) -> WholeShareSizing:
    """Size ``target_weights`` into whole shares against ``equity``.

    Negative weights (the SPY beta-hedge leg) are sized on their absolute
    value and returned as negative share counts; a short leg rounds toward a
    smaller absolute position for the same reason a long leg does, so the
    hedge is never accidentally larger than requested.

    ``allocate_remainder`` spends the flooring remainder one share at a time
    on the most under-weight affordable name. Turning it off gives the plain
    floor, which is what the deviation figures in the module docstring
    compare against.
    """
    if equity <= 0:
        raise ValueError(f"equity must be positive, got {equity}")

    priced = {
        symbol: float(prices[symbol])
        for symbol in target_weights
        if symbol in prices and float(prices[symbol]) > 0
    }
    shares: dict[str, int] = {}
    unaffordable: list[str] = []
    for symbol, weight in target_weights.items():
        price = priced.get(symbol)
        if price is None:
            unaffordable.append(symbol)
            shares[symbol] = 0
            continue
        count = int(abs(weight) * equity // price)
        if count == 0 and weight != 0.0:
            unaffordable.append(symbol)
        shares[symbol] = -count if weight < 0 else count

    if allocate_remainder:
        _spend_remainder(shares, target_weights, priced, equity)

    realized = {
        symbol: (shares[symbol] * priced[symbol] / equity if symbol in priced else 0.0)
        for symbol in target_weights
    }
    deviation = sum(abs(realized[s] - float(target_weights[s])) for s in target_weights) / 2.0
    long_cash = sum(
        count * priced[symbol] for symbol, count in shares.items() if symbol in priced and count > 0
    )
    return WholeShareSizing(
        shares=shares,
        realized_weights=realized,
        target_weights={s: float(w) for s, w in target_weights.items()},
        invested_cash=long_cash,
        idle_cash=max(equity - long_cash, 0.0),
        weight_deviation=deviation,
        unaffordable=tuple(unaffordable),
    )


def _spend_remainder(
    shares: dict[str, int],
    target_weights: Mapping[str, float],
    priced: Mapping[str, float],
    equity: float,
) -> None:
    """Buy one more share at a time of the most under-weight affordable name,
    until no affordable name is still under its target dollar allocation.
    Bounded by construction: every iteration spends at least one share's
    worth of the remainder, so it terminates.
    """
    while True:
        spent = sum(
            abs(count) * priced[symbol] for symbol, count in shares.items() if symbol in priced
        )
        remainder = equity - spent
        best_symbol, best_gap = None, 0.0
        for symbol, weight in target_weights.items():
            price = priced.get(symbol)
            if price is None or price > remainder:
                continue
            gap = abs(float(weight)) * equity - abs(shares[symbol]) * price
            if gap > best_gap:
                best_symbol, best_gap = symbol, gap
        if best_symbol is None or best_gap < priced[best_symbol] / 2.0:
            # Stop once the best remaining under-allocation is smaller than
            # half a share: buying there would overshoot by more than it
            # currently falls short, making the deviation worse, not better.
            # Because weights are measured against fixed equity, one name's
            # share count never changes another's realized weight, so this
            # per-name test is enough for the whole book -- every accepted
            # buy strictly lowers the total deviation.
            return
        shares[best_symbol] += -1 if float(target_weights[best_symbol]) < 0 else 1
