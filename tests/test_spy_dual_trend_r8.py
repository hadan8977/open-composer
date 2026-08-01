from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.spy_dual_trend_r8 import (
    compute_target_states,
    simulate_entry_only_target,
)


def test_r8_target_requires_127_bars_and_executes_one_session_later() -> None:
    close = pd.Series(np.arange(1.0, 130.0))

    states = compute_target_states(close)

    assert states["decision_state"].iloc[:126].isna().all()
    assert bool(states["decision_state"].iloc[126]) is True
    assert states["target_state"].iloc[:127].isna().all()
    assert bool(states["target_state"].iloc[127]) is True


def test_r8_entry_only_target_does_not_rebuy_and_tracks_terminal_drift() -> None:
    opens = pd.Series([100.0, 110.0, 120.0, 200.0])
    target = pd.Series([True, True, True, True])

    result = simulate_entry_only_target(opens, target, cost_bps=10.0)

    assert result.metrics["entry_count"] == 1
    assert result.metrics["terminal_liquidation_count"] == 1
    assert result.metrics["maximum_drifted_weight"] > 0.4
    assert [trade["action"] for trade in result.trades] == ["entry", "terminal_exit"]
    assert np.isfinite(result.daily["daily_return"]).all()


def test_r8_fold_like_runs_each_charge_their_own_entry_and_terminal_cost() -> None:
    opens = pd.Series([100.0, 100.0, 100.0, 100.0])
    target = pd.Series([True, True, True, True])

    aggregate = simulate_entry_only_target(opens, target, cost_bps=100.0)
    first = simulate_entry_only_target(
        opens.iloc[:2].reset_index(drop=True), target.iloc[:2], cost_bps=100.0
    )
    second = simulate_entry_only_target(
        opens.iloc[2:].reset_index(drop=True),
        target.iloc[2:].reset_index(drop=True),
        cost_bps=100.0,
    )

    assert aggregate.metrics["order_count"] == 2
    assert first.metrics["order_count"] == 2
    assert second.metrics["order_count"] == 2
    assert (
        first.metrics["total_cost"] + second.metrics["total_cost"] > aggregate.metrics["total_cost"]
    )


def test_r8_simulation_fails_on_nonfinite_prices() -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        simulate_entry_only_target(
            pd.Series([100.0, float("nan")]),
            pd.Series([False, False]),
            cost_bps=10.0,
        )
