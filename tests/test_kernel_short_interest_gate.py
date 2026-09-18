"""Tests for ``open_composer.research.kernel.short_interest_gate`` (H-20260916-07).

These pin the three things the card's stop conditions are read off, so a later
edit cannot quietly change what the avoid layer means: the percentile boundary
(which *is* the hypothesis -- "highest 20% days-to-cover"), the missing-value
convention (a name with no FINRA record must never be dropped *because* it has
no record), and the same-size within-week shuffle that lesson L-20260916-01
made mandatory for any layer that changes how many names are held.
"""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.features.short_interest import AVOID_PERCENTILE_THRESHOLD
from open_composer.research.kernel.insider_gate import (
    FULL,
    HALF,
    VETO,
    normalize_weights_to_full_exposure,
)
from open_composer.research.kernel.short_interest_gate import (
    AVOID_FEATURE_COLUMNS,
    AVOID_SPECS,
    avoid_states,
    shuffle_states_within_date,
)


def _frame(values: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame({"dtc_cross_sectional_pct": values})


def test_avoid_drop_boundary_is_the_eightieth_percentile_inclusive() -> None:
    frame = _frame([0.0, 0.5, 0.7999, 0.80, 0.95, 1.0])
    assert list(avoid_states(frame, "avoid_drop")) == [FULL, FULL, FULL, VETO, VETO, VETO]


def test_avoid_half_uses_the_same_condition_with_a_different_state() -> None:
    frame = _frame([0.79, 0.81])
    assert list(avoid_states(frame, "avoid_half")) == [FULL, HALF]


def test_threshold_is_the_module_constant_not_a_literal() -> None:
    frame = _frame([AVOID_PERCENTILE_THRESHOLD])
    assert list(avoid_states(frame, "avoid_drop")) == [VETO]


def test_missing_percentile_stays_in_the_book() -> None:
    """A name with no visible FINRA record must not be dropped by the layer.

    Dropping it would turn a coverage gap into the layer's main effect, which
    is the failure the pre-check's coverage row exists to catch.
    """
    frame = _frame([None, float("nan"), 0.9])
    assert list(avoid_states(frame, "avoid_drop")) == [FULL, FULL, VETO]


def test_custom_threshold_is_honoured() -> None:
    frame = _frame([0.5, 0.91])
    assert list(avoid_states(frame, "avoid_drop", threshold=0.9)) == [FULL, VETO]


def test_unknown_gate_and_missing_column_both_raise() -> None:
    with pytest.raises(KeyError):
        avoid_states(_frame([0.5]), "avoid_nothing")
    with pytest.raises(KeyError):
        avoid_states(pd.DataFrame({"other": [1.0]}), "avoid_drop")


def test_feature_columns_cover_every_spec() -> None:
    declared = {column for spec in AVOID_SPECS.values() for column in spec.columns}
    assert set(AVOID_FEATURE_COLUMNS) == declared


def test_shuffle_preserves_the_per_week_state_counts() -> None:
    states = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05"] * 5 + ["2024-01-12"] * 5,
            "symbol": list("ABCDE") * 2,
            "state_avoid_drop": [VETO, FULL, FULL, FULL, FULL, FULL, FULL, VETO, VETO, FULL],
        }
    )
    shuffled = shuffle_states_within_date(states, ["avoid_drop"], seed=20260917)
    for date, group in shuffled.groupby("rebalance_date"):
        original = states.loc[states["rebalance_date"] == date, "state_avoid_drop"]
        assert sorted(group["state_avoid_drop"]) == sorted(original)


def test_shuffle_actually_moves_something_and_is_seed_stable() -> None:
    states = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05"] * 8,
            "symbol": list("ABCDEFGH"),
            "state_avoid_drop": [VETO, VETO, FULL, FULL, FULL, FULL, FULL, FULL],
        }
    )
    first = shuffle_states_within_date(states, ["avoid_drop"], seed=7)
    again = shuffle_states_within_date(states, ["avoid_drop"], seed=7)
    other = shuffle_states_within_date(states, ["avoid_drop"], seed=8)
    assert list(first["state_avoid_drop"]) == list(again["state_avoid_drop"])
    assert list(first["state_avoid_drop"]) != list(states["state_avoid_drop"]) or list(
        other["state_avoid_drop"]
    ) != list(states["state_avoid_drop"])


def test_shuffle_rejects_a_gate_with_no_state_column() -> None:
    states = pd.DataFrame({"rebalance_date": ["2024-01-05"], "state_avoid_drop": [FULL]})
    with pytest.raises(KeyError):
        shuffle_states_within_date(states, ["avoid_half"], seed=1)


def test_dropped_week_renormalizes_to_full_gross_exposure() -> None:
    """The decision-grade book: after dropping names, the rest sums back to 1."""
    book = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05"] * 4,
            "symbol": list("ABCD"),
            "weight": [0.25, 0.25, 0.0, 0.25],
        }
    )
    normalized = normalize_weights_to_full_exposure(book)
    assert normalized["weight"].sum() == pytest.approx(1.0)
    assert normalized.loc[normalized["symbol"] == "C", "weight"].item() == 0.0
