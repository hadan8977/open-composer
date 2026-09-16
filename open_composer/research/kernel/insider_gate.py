"""Form 4 insider confirmation gates over an existing weekly pick book.

Why this is a module and not inline in ``scripts/run_h20260916_01_insider_gate.py``
(H-20260916-01, 2026-09-16): the card's stop conditions are read off two
different books per gate -- the literal "half weight, rest in BIL" version and
the exposure-normalized version -- and lesson ``L-20260916-03`` is precisely
that mixing those two up is how a de-leveraging artifact gets mistaken for an
effect. The state assignment, the normalization and the switch counting are
therefore defined once, in one place, with tests
(``tests/test_kernel_insider_gate.py``), rather than three times inside a
driver script.

Nothing here selects stocks, prices a book, or touches a gate contract. It
takes a frame that already has one row per (rebalance date, held symbol) with
that date's point-in-time insider columns -- the ``PickCollector`` export
joined to ``data/features/insider/`` -- and returns states, rescaled weights
and diagnostics. The insider columns are already point-in-time (a filing is
visible on the next session after its ``FILING_DATE``); nothing in this module
can change that, and nothing here looks at a later date than each row's own.

The gate definitions are the card's own, after its "第 0 步完成后的两处修订"
section replaced the original cross-sectional-median cut (step 0 measured the
strict Cohen-Malloy-Pomorski opportunistic flag at 1-3% of stock-days in the
top-500 pool, which would have made a median cut a degenerate 0/1 split).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

#: The three states a held name can be in. ``veto`` exists only for the
#: veto-style gate; a halving gate never produces it.
FULL = "full"
HALF = "half"
VETO = "veto"

#: State -> multiplier applied to the name's baseline (equal) weight.
STATE_WEIGHT_MULTIPLIER: Mapping[str, float] = {FULL: 1.0, HALF: 0.5, VETO: 0.0}


@dataclass(frozen=True)
class GateSpec:
    """One gate: which insider columns it reads and what it does with them.

    ``columns`` exists so a caller can load exactly the columns a gate needs
    (and so a report can state them) without importing the predicate's body.
    """

    name: str
    description: str
    columns: tuple[str, ...]


GATE_SPECS: Mapping[str, GateSpec] = {
    "gate_A": GateSpec(
        name="gate_A",
        description=(
            "any_buy：过去 60 个交易日内有公开市场买入（TRANS_CODE=P，"
            "`open_market_buy_count_60d >= 1`）且净买入人数为正"
            "（`net_buyers_60d > 0`）则满仓，否则减半"
        ),
        columns=("open_market_buy_count_60d", "net_buyers_60d"),
    ),
    "gate_B": GateSpec(
        name="gate_B",
        description=(
            "cluster：过去 60 个交易日内有 ≥ 2 个不同买家（`buyers_60d >= 2`）则满仓，否则减半"
        ),
        columns=("buyers_60d",),
    ),
    "gate_C": GateSpec(
        name="gate_C",
        description=(
            "cmp_opportunistic：过去 60 个交易日内有 ≥ 1 笔 Cohen-Malloy-Pomorski 严格"
            "口径的机会型买入（`cmp_opportunistic_buy_60d >= 1`）则满仓，否则减半"
        ),
        columns=("cmp_opportunistic_buy_60d",),
    ),
    "gate_A_veto": GateSpec(
        name="gate_A_veto",
        description=(
            "veto：过去 60 个交易日内公开市场卖出 ≥ 3 笔"
            "（`open_market_sell_count_60d >= 3`）且没有任何买入"
            "（`open_market_buy_count_60d == 0`）则剔除（权重 0），其余满仓"
        ),
        columns=("open_market_sell_count_60d", "open_market_buy_count_60d"),
    ),
}

#: Every insider column any gate reads, for one-shot loading.
GATE_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    sorted({column for spec in GATE_SPECS.values() for column in spec.columns})
)


def gate_states(frame: pd.DataFrame, gate: str) -> pd.Series:
    """The per-row state (``full``/``half``/``veto``) that ``gate`` assigns.

    ``frame`` must carry the gate's ``columns``. Missing values count as "no
    visible filing" (i.e. 0), which is the insider table's own convention:
    every stock-day in the pool has a row, and 0 -- not null -- means "no
    filing became visible in the window". A caller that joined the table onto
    a book and got a null therefore has a row the table does not cover, and
    treating that as "not confirmed" is the conservative reading, never the
    permissive one.
    """
    spec = GATE_SPECS[gate]
    missing = [column for column in spec.columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{gate} needs columns {missing} which the frame does not have")
    values = {column: frame[column].fillna(0.0) for column in spec.columns}
    if gate == "gate_A":
        full = (values["open_market_buy_count_60d"] >= 1) & (values["net_buyers_60d"] > 0)
        return pd.Series(np.where(full, FULL, HALF), index=frame.index, dtype="object")
    if gate == "gate_B":
        full = values["buyers_60d"] >= 2
        return pd.Series(np.where(full, FULL, HALF), index=frame.index, dtype="object")
    if gate == "gate_C":
        full = values["cmp_opportunistic_buy_60d"] >= 1
        return pd.Series(np.where(full, FULL, HALF), index=frame.index, dtype="object")
    if gate == "gate_A_veto":
        vetoed = (values["open_market_sell_count_60d"] >= 3) & (
            values["open_market_buy_count_60d"] == 0
        )
        return pd.Series(np.where(vetoed, VETO, FULL), index=frame.index, dtype="object")
    raise KeyError(gate)


def state_shares(states: pd.Series) -> dict[str, float]:
    """``{state: share of rows}`` for all three states, so a state a gate never
    produced reports as an explicit 0.0 rather than silently missing (a caller
    reading ``.get("veto")`` cannot then confuse "never vetoed" with "not
    measured"). ``{}`` only when there are no rows at all.
    """
    total = len(states)
    if total == 0:
        return {}
    counts = states.astype(str).value_counts()
    return {state: float(counts.get(state, 0)) / total for state in (FULL, HALF, VETO)}


def normalize_weights_to_full_exposure(
    frame: pd.DataFrame,
    *,
    weight_column: str = "weight",
    date_column: str = "rebalance_date",
) -> pd.DataFrame:
    """``frame`` with ``weight_column`` rescaled so each date's weights sum to
    1.0 -- the exposure-normalized book required by ``L-20260916-03``.

    A date whose weights all came out zero (every name vetoed) is left at zero
    rather than divided by zero; the caller's schedule builder then turns that
    week into a full cash week, which is the only honest reading of "the gate
    rejected everything".
    """
    out = frame.copy()
    totals = out.groupby(date_column)[weight_column].transform("sum")
    scaled = out[weight_column].where(totals <= 0.0, out[weight_column] / totals)
    out[weight_column] = scaled.fillna(0.0)
    return out


def gate_state_changes_per_year(
    frame: pd.DataFrame,
    gate: str,
    *,
    date_column: str = "rebalance_date",
    symbol_column: str = "symbol",
) -> dict[str, int]:
    """``{year: number of (date, symbol) pairs whose state differs from that
    symbol's state at the previous date it was held}``.

    A name entering the book for the first time is not a change (there is no
    previous state to differ from); neither is a name that left and came back
    at the same state. This counts the gate *acting differently* on a name it
    was already carrying, which is what "the gate switched" means for a
    per-name gate.
    """
    column = f"state_{gate}"
    if column not in frame.columns:
        raise KeyError(f"frame has no {column}")
    ordered = frame.sort_values([symbol_column, date_column])
    previous = ordered.groupby(symbol_column, sort=False)[column].shift(1)
    changed = previous.notna() & (ordered[column].astype(str) != previous.astype(str))
    years = pd.to_datetime(ordered[date_column]).dt.year
    counts = years[changed].value_counts().sort_index()
    return {str(year): int(count) for year, count in counts.items()}


def rebalances_with_gate_change_per_year(
    frame: pd.DataFrame,
    gate: str,
    *,
    date_column: str = "rebalance_date",
    symbol_column: str = "symbol",
) -> dict[str, int]:
    """``{year: number of rebalance dates on which the gate changed at least
    one carried name's state}`` -- the per-year activity count the card's stop
    condition (5) ("门每年切换 < 4 次") is scored on.

    Every year with at least one rebalance date appears in the result, with 0
    when the gate never moved that year; a silently absent year would read as
    "no data" when it actually means "the gate did nothing".
    """
    column = f"state_{gate}"
    if column not in frame.columns:
        raise KeyError(f"frame has no {column}")
    ordered = frame.sort_values([symbol_column, date_column])
    previous = ordered.groupby(symbol_column, sort=False)[column].shift(1)
    changed = previous.notna() & (ordered[column].astype(str) != previous.astype(str))
    dates = pd.to_datetime(ordered[date_column])
    counts = {str(year): 0 for year in sorted(dates.dt.year.unique())}
    for year, date in dates[changed].groupby(dates[changed].dt.year):
        counts[str(year)] = int(date.nunique())
    return counts
