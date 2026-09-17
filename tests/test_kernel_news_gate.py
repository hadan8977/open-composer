"""Tests for ``open_composer.research.kernel.news_gate`` (H-20260916-02).

These pin the five things the card's stop conditions are read off, so a later
edit cannot quietly change what a gate means: the state predicates (including
their boundary values, which *are* the hypothesis), the missing-value
convention, the exposure normalization that lesson ``L-20260916-03`` made
mandatory, the within-week same-size random control that lesson
``L-20260916-01`` made mandatory, and the two switch counters.

The within-week shuffle gets the most attention here, because its whole value
as a control rests on one property -- it must not change any week's tier counts
-- and that property is silent when broken.
"""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.kernel.news_gate import (
    FULL,
    GATE_FEATURE_COLUMNS,
    GATE_NONEWS,
    GATE_SPECS,
    GATE_SURGE,
    GATE_TIERED,
    HALF,
    PARTIAL,
    STATE_WEIGHT_MULTIPLIER,
    gate_state_changes_per_year,
    gate_states,
    normalize_weights_to_full_exposure,
    rebalances_with_gate_change_per_year,
    shuffle_states_within_date,
    state_shares,
)


def _frame(**columns: list[float]) -> pd.DataFrame:
    return pd.DataFrame(columns)


# --------------------------------------------------------------------------
# state predicates
# --------------------------------------------------------------------------


def test_surge_gate_needs_both_the_surge_and_the_novelty() -> None:
    frame = _frame(
        attention_surge_5d=[2.0, 1.99, 3.0, 5.0],
        novelty_5d=[0.5, 0.9, 0.49, 0.5],
        novelty_median_ref=[0.5, 0.5, 0.5, 0.5],
    )
    assert list(gate_states(frame, GATE_SURGE)) == [FULL, HALF, HALF, FULL]


def test_nonews_gate_boundary_is_exactly_zero_articles_in_twenty_sessions() -> None:
    frame = _frame(news_count_20d=[0.0, 1.0, 40.0])
    assert list(gate_states(frame, GATE_NONEWS)) == [HALF, FULL, FULL]


def test_tiered_gate_puts_everything_else_in_the_middle() -> None:
    frame = _frame(
        attention_surge_5d=[3.0, 1.0, 0.0],
        novelty_5d=[0.9, 0.9, float("nan")],
        novelty_median_ref=[0.5, 0.5, 0.5],
        news_count_20d=[10.0, 10.0, 0.0],
    )
    assert list(gate_states(frame, GATE_TIERED)) == [FULL, PARTIAL, HALF]


def test_a_name_with_no_news_can_never_be_confirmed() -> None:
    """No article in 20 sessions implies none in 5, so surge is 0 and novelty is
    undefined; the two clauses of the card's sentence therefore never conflict,
    which is the claim ``news_gate``'s docstring makes.
    """
    frame = _frame(
        attention_surge_5d=[0.0],
        novelty_5d=[float("nan")],
        novelty_median_ref=[0.5],
        news_count_20d=[0.0],
    )
    assert list(gate_states(frame, GATE_SURGE)) == [HALF]
    assert list(gate_states(frame, GATE_TIERED)) == [HALF]


def test_missing_values_are_treated_as_no_news() -> None:
    """The news table has a row for every stock-day in the PIT top-1000 cohort
    with 0 -- not null -- where nothing was published, so a null in a joined
    book means "no row at all for that (date, symbol)". Reading that as "no
    news" is the conservative direction; reading it as "confirmed" would let a
    join miss silently upgrade a position.
    """
    frame = _frame(
        attention_surge_5d=[float("nan")],
        novelty_5d=[float("nan")],
        novelty_median_ref=[float("nan")],
        news_count_20d=[float("nan")],
    )
    assert list(gate_states(frame, GATE_SURGE)) == [HALF]
    assert list(gate_states(frame, GATE_NONEWS)) == [HALF]
    assert list(gate_states(frame, GATE_TIERED)) == [HALF]


def test_unknown_gate_raises() -> None:
    with pytest.raises(KeyError):
        gate_states(_frame(news_count_20d=[1.0]), "gate_that_does_not_exist")


def test_missing_column_raises_rather_than_defaulting() -> None:
    with pytest.raises(KeyError, match="novelty_median_ref"):
        gate_states(_frame(attention_surge_5d=[3.0], novelty_5d=[0.9]), GATE_SURGE)


def test_gate_feature_columns_covers_every_spec() -> None:
    for spec in GATE_SPECS.values():
        for column in spec.columns:
            assert column in GATE_FEATURE_COLUMNS


def test_state_multipliers_are_monotone_and_complete() -> None:
    assert STATE_WEIGHT_MULTIPLIER[FULL] > STATE_WEIGHT_MULTIPLIER[PARTIAL]
    assert STATE_WEIGHT_MULTIPLIER[PARTIAL] > STATE_WEIGHT_MULTIPLIER[HALF]
    assert set(STATE_WEIGHT_MULTIPLIER) == {FULL, PARTIAL, HALF}


def test_state_shares_reports_unused_states_as_zero() -> None:
    shares = state_shares(pd.Series([FULL, FULL, HALF]))
    assert shares == {FULL: pytest.approx(2 / 3), PARTIAL: 0.0, HALF: pytest.approx(1 / 3)}
    assert state_shares(pd.Series([], dtype="object")) == {}


# --------------------------------------------------------------------------
# exposure normalization
# --------------------------------------------------------------------------


def test_normalization_rescales_each_date_to_full_exposure() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": ["2024-01-05", "2024-01-05", "2024-01-12"],
            "symbol": ["AAA", "BBB", "AAA"],
            "weight": [0.02, 0.01, 0.01],
        }
    )
    out = normalize_weights_to_full_exposure(frame)
    assert out.groupby("rebalance_date")["weight"].sum().tolist() == [
        pytest.approx(1.0),
        pytest.approx(1.0),
    ]
    # Relative sizing inside the week is preserved: 2:1 stays 2:1.
    week = out.loc[out["rebalance_date"] == "2024-01-05", "weight"].tolist()
    assert week[0] == pytest.approx(2 * week[1])


def test_normalization_leaves_an_all_zero_date_at_zero() -> None:
    frame = pd.DataFrame(
        {"rebalance_date": ["2024-01-05"] * 2, "symbol": ["AAA", "BBB"], "weight": [0.0, 0.0]}
    )
    out = normalize_weights_to_full_exposure(frame)
    assert out["weight"].tolist() == [0.0, 0.0]


# --------------------------------------------------------------------------
# the same-size random control
# --------------------------------------------------------------------------


def _states() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(
                ["2024-01-05"] * 4 + ["2024-01-12"] * 4 + ["2025-01-10"] * 4
            ),
            "symbol": ["AAA", "BBB", "CCC", "DDD"] * 3,
            "weight": [0.25] * 12,
            "state_gate_N_surge": [
                FULL,
                HALF,
                HALF,
                HALF,
                HALF,
                FULL,
                FULL,
                HALF,
                HALF,
                HALF,
                HALF,
                HALF,
            ],
            "state_gate_N_nonews": [FULL] * 11 + [HALF],
        }
    )


def test_shuffle_preserves_every_week_tier_counts_exactly() -> None:
    """The entire value of this control is that it changes *which* names are in
    each tier without changing *how many*: same position count, same gross
    exposure after normalization, same turnover profile.
    """
    states = _states()
    shuffled = shuffle_states_within_date(states, seed=20260916)
    for column in ("state_gate_N_surge", "state_gate_N_nonews"):
        real = states.groupby("rebalance_date")[column].value_counts().sort_index()
        control = shuffled.groupby("rebalance_date")[column].value_counts().sort_index()
        assert real.to_dict() == control.to_dict()


def test_shuffle_is_deterministic_per_seed_and_varies_across_seeds() -> None:
    """Reproducible for a given seed (the report quotes per-seed numbers) and
    genuinely random across seeds (five seeds that all produced the same book
    would be one seed reported five times, which is what L-20260916-03 banned).
    """
    states = _states()
    first = shuffle_states_within_date(states, seed=1)["state_gate_N_surge"].tolist()
    again = shuffle_states_within_date(states, seed=1)["state_gate_N_surge"].tolist()
    assert first == again
    outcomes = {
        tuple(shuffle_states_within_date(states, seed=seed)["state_gate_N_surge"])
        for seed in range(1, 21)
    }
    assert len(outcomes) > 1


def test_shuffle_does_not_move_labels_across_dates() -> None:
    """A permutation that leaked across weeks would quietly give the control
    information from a different week, which is not the control we claim.
    """
    states = _states()
    shuffled = shuffle_states_within_date(states, seed=7)
    assert shuffled["rebalance_date"].tolist() == states["rebalance_date"].tolist()
    assert shuffled["symbol"].tolist() == states["symbol"].tolist()


def test_shuffle_uses_one_permutation_for_all_state_columns_per_date() -> None:
    """Two gates that agreed on a name in the real book must still be
    internally consistent in the control, otherwise the control book is not a
    relabelling of one book but a mixture of two.
    """
    states = _states()
    shuffled = shuffle_states_within_date(states, seed=11)
    real_pairs = list(zip(states["state_gate_N_surge"], states["state_gate_N_nonews"], strict=True))
    control_pairs = list(
        zip(shuffled["state_gate_N_surge"], shuffled["state_gate_N_nonews"], strict=True)
    )
    assert sorted(map(str, real_pairs)) == sorted(map(str, control_pairs))


def test_shuffle_requires_state_columns() -> None:
    with pytest.raises(KeyError):
        shuffle_states_within_date(
            pd.DataFrame({"rebalance_date": ["2024-01-05"], "symbol": ["AAA"]}), seed=1
        )


# --------------------------------------------------------------------------
# switch counters
# --------------------------------------------------------------------------


def test_state_changes_count_only_names_the_gate_already_carried() -> None:
    states = _states()
    changes = gate_state_changes_per_year(states, "gate_N_surge")
    # AAA full->half, BBB half->full, CCC half->full in 2024-01-12; then
    # BBB full->half and CCC full->half in 2025 (AAA and DDD unchanged).
    assert changes == {"2024": 3, "2025": 2}


def test_rebalance_change_counter_reports_quiet_years_as_zero() -> None:
    states = _states()
    counts = rebalances_with_gate_change_per_year(states, "gate_N_nonews")
    assert counts["2024"] == 0
    assert counts["2025"] == 1


def test_switch_counters_require_the_state_column() -> None:
    with pytest.raises(KeyError):
        gate_state_changes_per_year(_states(), "gate_that_does_not_exist")
