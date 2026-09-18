"""FINRA short-interest "avoid list" layers over an existing weekly pick book.

Why this is a module and not inline in
``scripts/run_h20260916_07_short_interest.py`` (H-20260916-07, 2026-09-17): the
card's stop conditions are read off an exposure-normalized book, and the whole
point of lesson ``L-20260916-03`` is that comparing a de-leveraged book against
a fully invested one measures leverage rather than information. Lesson
``L-20260916-01`` adds the second half: because these layers change the *number*
of names held, they also need a "same number of names, randomly chosen" control.
Both operations are therefore defined once, here, with tests
(``tests/test_kernel_short_interest_gate.py``).

This module deliberately reuses ``insider_gate``'s
``normalize_weights_to_full_exposure``, ``state_shares``,
``gate_state_changes_per_year`` and ``rebalances_with_gate_change_per_year``
rather than re-implementing them: those four are generic over any
``state_{gate}`` column and a second copy is exactly how two rounds' numbers
start disagreeing.

Nothing here selects stocks, prices a book or touches a gate contract. It takes
a frame with one row per (rebalance date, held symbol) carrying that date's
point-in-time short-interest columns -- the ``PickCollector`` export joined to
``data/features/short_interest/`` -- and returns states and rescaled weights.
The short-interest columns are already point-in-time (a snapshot is visible on
the session after FINRA publishes it, never on its settlement date); nothing in
this module can change that.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from open_composer.research.features.short_interest import AVOID_PERCENTILE_THRESHOLD
from open_composer.research.kernel.insider_gate import FULL, HALF, VETO

__all__ = [
    "AVOID_SPECS",
    "AVOID_FEATURE_COLUMNS",
    "AvoidSpec",
    "avoid_states",
    "shuffle_states_within_date",
]


@dataclass(frozen=True)
class AvoidSpec:
    """One avoid layer: which columns it reads and what it does with them."""

    name: str
    description: str
    columns: tuple[str, ...]
    #: State applied to a name that meets the avoid condition.
    hit_state: str


AVOID_SPECS: Mapping[str, AvoidSpec] = {
    "avoid_drop": AvoidSpec(
        name="avoid_drop",
        description=(
            "剔除：days-to-cover 在当日点时 top-500 池的最高 20%"
            f"（`dtc_cross_sectional_pct >= {AVOID_PERCENTILE_THRESHOLD}`）则权重 0，"
            "其余满仓；比较前归一化到 100% 暴露"
        ),
        columns=("dtc_cross_sectional_pct",),
        hit_state=VETO,
    ),
    "avoid_half": AvoidSpec(
        name="avoid_half",
        description=(
            "减半：days-to-cover 在当日点时 top-500 池的最高 20%"
            f"（`dtc_cross_sectional_pct >= {AVOID_PERCENTILE_THRESHOLD}`）则权重减半，"
            "其余满仓；比较前归一化到 100% 暴露"
        ),
        columns=("dtc_cross_sectional_pct",),
        hit_state=HALF,
    ),
}

#: Every short-interest column any avoid layer reads, for one-shot loading.
AVOID_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    sorted({column for spec in AVOID_SPECS.values() for column in spec.columns})
)


def avoid_states(
    frame: pd.DataFrame,
    gate: str,
    *,
    threshold: float = AVOID_PERCENTILE_THRESHOLD,
) -> pd.Series:
    """The per-row state (``full``/``half``/``veto``) that ``gate`` assigns.

    A **missing** ``dtc_cross_sectional_pct`` is treated as "not in the avoid
    bucket", i.e. ``full``. That is the conservative reading in the one
    direction that matters here: the card's claim is that removing names helps,
    so letting an unmeasured name stay in the book can only make the layer look
    *weaker*, never stronger. The opposite convention (drop everything we
    cannot measure) would quietly turn "no FINRA record" -- which is a data
    gap, not a short-interest signal -- into the layer's main effect, and the
    coverage row in the pre-check exists precisely so that gap is quoted rather
    than traded.
    """
    spec = AVOID_SPECS[gate]
    missing = [column for column in spec.columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{gate} needs columns {missing} which the frame does not have")
    percentile = pd.to_numeric(frame["dtc_cross_sectional_pct"], errors="coerce")
    hit = (percentile >= threshold).fillna(False)
    return pd.Series(
        np.where(hit.to_numpy(), spec.hit_state, FULL), index=frame.index, dtype="object"
    )


def shuffle_states_within_date(
    states: pd.DataFrame,
    gates: Iterable[str],
    seed: int,
    *,
    date_column: str = "rebalance_date",
) -> pd.DataFrame:
    """``states`` with each gate's state column permuted **within each
    rebalance date** -- the same-size random control the card requires.

    Permuting inside the week (not across the whole frame) keeps each week's
    full/half/veto counts exactly as the real layer produced them, so the
    shuffled book holds the same number of names, has the same gross exposure
    after normalization and a comparable turnover profile; only *which* names
    are dropped is randomized. An improvement that this control reproduces is
    a concentration effect, not short-interest information.
    """
    rng = np.random.default_rng(seed)
    out = states.copy()
    groups = out.groupby(date_column).indices
    for gate in gates:
        column = f"state_{gate}"
        if column not in out.columns:
            raise KeyError(f"frame has no {column}")
        values = out[column].to_numpy(copy=True)
        for index in groups.values():
            values[index] = rng.permutation(values[index])
        out[column] = values
    return out
