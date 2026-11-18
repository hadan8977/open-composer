"""A held instruction must still repair a book that drifted away from it.

``hold`` used to mean "never touch this book" and was computed from
target-vs-target equality, so a rebalance that failed to execute persisted
forever (BASE kept its October roster for four sessions on 2026-11-04..10, H5
stayed in cash for a week). The repair path is a bounded share drift.
"""

from open_composer.intraday_runner.six_paper_service import (
    HOLD_DRIFT_TOLERANCE_FRACTION,
    hold_drift,
)


def test_drift_below_tolerance_is_ignored():
    # one cheap share is rounding, not a missing position
    assert hold_drift({"A": 101}, {"A": 100}, {"A": 60.0}, capital=20_000, nav=20_000) == {}


def test_drift_above_tolerance_trades_the_gap():
    drift = hold_drift({"A": 300}, {"A": 100}, {"A": 10.0}, capital=20_000, nav=20_000)
    assert drift == {"A": 200}


def test_absolute_share_targets_are_not_drift():
    # integer sizing rounds the target; identical quantities are never drift
    assert hold_drift({"A": 3}, {"A": 3}, {"A": 1055.0}, capital=20_000, nav=20_000) == {}


def test_missing_or_zero_price_is_skipped():
    assert hold_drift({"A": 300}, {"A": 100}, {}, capital=20_000, nav=20_000) == {}


def test_small_book_uses_its_own_capital():
    drift = hold_drift({"A": 5}, {"A": 3}, {"A": 500.0}, capital=1_666.67, nav=1_666.67)
    assert drift == {"A": 2}


def test_tolerance_band_matches_the_deployed_sleeve_convention():
    assert HOLD_DRIFT_TOLERANCE_FRACTION == 0.05
