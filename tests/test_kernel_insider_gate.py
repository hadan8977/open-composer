"""Tests for ``open_composer.research.kernel.insider_gate`` (H-20260916-01).

These pin the four things the card's stop conditions are read off, so a later
edit cannot quietly change what a gate means: the state predicates (including
their boundary values, which are the hypothesis), the exposure normalization
that lesson L-20260916-03 made mandatory, and the two switch counters.
"""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.kernel.insider_gate import (
    FULL,
    GATE_FEATURE_COLUMNS,
    GATE_SPECS,
    HALF,
    STATE_WEIGHT_MULTIPLIER,
    VETO,
    gate_state_changes_per_year,
    gate_states,
    normalize_weights_to_full_exposure,
    rebalances_with_gate_change_per_year,
    state_shares,
)


def _frame(**columns: list[float]) -> pd.DataFrame:
    return pd.DataFrame(columns)


def test_gate_a_needs_both_a_buy_and_positive_net_buyers() -> None:
    frame = _frame(
        open_market_buy_count_60d=[1.0, 1.0, 0.0, 3.0],
        net_buyers_60d=[1.0, 0.0, 2.0, -1.0],
    )
    assert list(gate_states(frame, "gate_A")) == [FULL, HALF, HALF, HALF]


def test_gate_b_boundary_is_two_distinct_buyers() -> None:
    frame = _frame(buyers_60d=[0.0, 1.0, 2.0, 7.0])
    assert list(gate_states(frame, "gate_B")) == [HALF, HALF, FULL, FULL]


def test_gate_c_boundary_is_one_cmp_opportunistic_buy() -> None:
    frame = _frame(cmp_opportunistic_buy_60d=[0.0, 1.0, 4.0])
    assert list(gate_states(frame, "gate_C")) == [HALF, FULL, FULL]


def test_gate_a_veto_requires_three_sells_and_no_buys() -> None:
    frame = _frame(
        open_market_sell_count_60d=[3.0, 3.0, 2.0, 9.0],
        open_market_buy_count_60d=[0.0, 1.0, 0.0, 0.0],
    )
    assert list(gate_states(frame, "gate_A_veto")) == [VETO, FULL, FULL, VETO]


def test_missing_values_are_treated_as_no_visible_filing() -> None:
    """The insider table has a row for every pool stock-day with 0 (not null)
    where nothing was visible, so a null can only come from a row the table
    does not cover -- which must read as "not confirmed", never as confirmed.
    """
    frame = _frame(open_market_buy_count_60d=[float("nan")], net_buyers_60d=[float("nan")])
    assert list(gate_states(frame, "gate_A")) == [HALF]
    veto_frame = _frame(
        open_market_sell_count_60d=[float("nan")], open_market_buy_count_60d=[float("nan")]
    )
    assert list(gate_states(veto_frame, "gate_A_veto")) == [FULL]


def test_gate_states_rejects_an_unknown_gate_and_a_frame_missing_columns() -> None:
    with pytest.raises(KeyError):
        gate_states(_frame(buyers_60d=[1.0]), "gate_Z")
    with pytest.raises(KeyError):
        gate_states(_frame(buyers_60d=[1.0]), "gate_A")


def test_gate_feature_columns_covers_every_spec() -> None:
    expected = {column for spec in GATE_SPECS.values() for column in spec.columns}
    assert set(GATE_FEATURE_COLUMNS) == expected


def test_state_multipliers_are_full_half_none() -> None:
    assert STATE_WEIGHT_MULTIPLIER[FULL] == 1.0
    assert STATE_WEIGHT_MULTIPLIER[HALF] == 0.5
    assert STATE_WEIGHT_MULTIPLIER[VETO] == 0.0


def test_state_shares_reports_every_state_including_unused_ones() -> None:
    shares = state_shares(pd.Series([FULL, FULL, HALF, HALF]))
    assert shares == {FULL: 0.5, HALF: 0.5, VETO: 0.0}
    assert state_shares(pd.Series([], dtype="object")) == {}


def test_normalization_restores_full_exposure_per_date_and_keeps_ratios() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05", "2024-01-05", "2024-01-12", "2024-01-12"],
            "symbol": ["A", "B", "A", "B"],
            "weight": [0.02, 0.01, 0.02, 0.02],
        }
    )
    out = normalize_weights_to_full_exposure(frame)
    by_date = out.groupby("rebalance_date")["weight"].sum()
    assert by_date.round(12).tolist() == [1.0, 1.0]
    first = out.loc[out["rebalance_date"] == "2024-01-05", "weight"].tolist()
    # 2:1 before, 2:1 after -- normalization is a pure rescale, not a re-rank.
    assert first[0] == pytest.approx(2.0 / 3.0)
    assert first[1] == pytest.approx(1.0 / 3.0)


def test_normalization_leaves_an_all_zero_date_at_zero() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05", "2024-01-05"],
            "symbol": ["A", "B"],
            "weight": [0.0, 0.0],
        }
    )
    out = normalize_weights_to_full_exposure(frame)
    assert out["weight"].tolist() == [0.0, 0.0]


def _switch_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(
                [
                    "2024-01-05",
                    "2024-01-12",
                    "2024-01-19",
                    "2024-01-05",
                    "2024-01-12",
                    "2025-01-10",
                ]
            ),
            "symbol": ["A", "A", "A", "B", "B", "B"],
            "state_gate_A": [FULL, HALF, HALF, HALF, HALF, FULL],
        }
    )


def test_gate_state_changes_counts_only_changes_on_carried_names() -> None:
    # A: full -> half on 01-12 (1 change), half -> half on 01-19 (none).
    # B: half -> half on 01-12 (none), half -> full on 2025-01-10 (1 change).
    assert gate_state_changes_per_year(_switch_frame(), "gate_A") == {"2024": 1, "2025": 1}


def test_first_appearance_is_not_a_change() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(["2024-01-05", "2024-01-05"]),
            "symbol": ["A", "B"],
            "state_gate_B": [FULL, HALF],
        }
    )
    assert gate_state_changes_per_year(frame, "gate_B") == {}
    assert rebalances_with_gate_change_per_year(frame, "gate_B") == {"2024": 0}


def test_rebalances_with_gate_change_counts_dates_not_names() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(
                ["2024-01-05", "2024-01-12", "2024-01-05", "2024-01-12"]
            ),
            "symbol": ["A", "A", "B", "B"],
            "state_gate_B": [FULL, HALF, FULL, HALF],
        }
    )
    # Two names both switched on the same date -> one date, not two.
    assert rebalances_with_gate_change_per_year(frame, "gate_B") == {"2024": 1}
    assert gate_state_changes_per_year(frame, "gate_B") == {"2024": 2}


def test_every_year_with_rebalances_appears_even_when_the_gate_never_moved() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(["2024-01-05", "2025-01-10"]),
            "symbol": ["A", "A"],
            "state_gate_C": [FULL, FULL],
        }
    )
    assert rebalances_with_gate_change_per_year(frame, "gate_C") == {"2024": 0, "2025": 0}


def test_switch_counters_reject_a_frame_without_the_gate_column() -> None:
    frame = pd.DataFrame({"rebalance_date": ["2024-01-05"], "symbol": ["A"]})
    with pytest.raises(KeyError):
        gate_state_changes_per_year(frame, "gate_A")
    with pytest.raises(KeyError):
        rebalances_with_gate_change_per_year(frame, "gate_A")
