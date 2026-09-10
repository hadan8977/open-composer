"""Tests for open_composer.research.kernel.loop."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel import loop
from open_composer.research.kernel.baseline_strategies import (
    EqualWeightUniverseStrategy,
    MomentumFactorStrategy,
)

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]


def test_weekly_rebalance_dates_picks_last_trading_day_per_iso_week() -> None:
    # A short holiday week (Mon/Tue/Wed only) still yields exactly one date.
    dates = pd.to_datetime(
        [
            "2024-01-01",
            "2024-01-02",  # week 1 -> last is 01-02
            "2024-01-08",
            "2024-01-09",
            "2024-01-10",
            "2024-01-11",
            "2024-01-12",  # week 2 -> last is 01-12 (a Friday)
        ]
    )
    result = loop.weekly_rebalance_dates(dates)
    assert result == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-12")]


def test_weekly_rebalance_dates_empty_input() -> None:
    assert loop.weekly_rebalance_dates([]) == []


def _universe_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month_end": pd.to_datetime(
                ["2020-01-31", "2020-01-31", "2020-02-28", "2020-02-28", "2020-02-28"]
            ),
            "symbol": ["AAA", "BBB", "AAA", "BBB", "CCC"],
        }
    )


def test_universe_as_of_calendar_month_uses_most_recent_month_end() -> None:
    panel = _universe_panel()
    # A date inside February, before the Feb cohort exists in the raw
    # column-value sense, should still resolve to the Feb cohort because
    # 2020-02-28 <= 2020-02-28.
    assert loop.universe_as_of_calendar_month(panel, pd.Timestamp("2020-02-28")) == {
        "AAA",
        "BBB",
        "CCC",
    }
    # A date early in February before the Feb month-end has posted falls back
    # to January's cohort.
    assert loop.universe_as_of_calendar_month(panel, pd.Timestamp("2020-02-10")) == {
        "AAA",
        "BBB",
    }


def test_universe_as_of_calendar_month_before_any_cohort_is_empty() -> None:
    panel = _universe_panel()
    assert loop.universe_as_of_calendar_month(panel, pd.Timestamp("2019-01-01")) == set()


def test_universe_as_of_respects_the_consumer_note_on_exact_month_end_dates() -> None:
    # Mirrors the real-archive quirk documented in universe.py: two symbols
    # in the "same" February cohort with different exact month_end dates
    # (one delisted mid-month) must still be grouped together by calendar
    # month, not treated as two different cohorts.
    panel = pd.DataFrame(
        {
            "month_end": pd.to_datetime(["2020-02-14", "2020-02-28"]),
            "symbol": ["DELISTED", "SURVIVOR"],
        }
    )
    assert loop.universe_as_of_calendar_month(panel, pd.Timestamp("2020-02-28")) == {
        "DELISTED",
        "SURVIVOR",
    }


def _synthetic_panel(n_days: int = 400, seed: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A 4-symbol panel spanning ~1.5 years with a deterministic momentum
    ranking (AAA always strongest, DDD always weakest) so B1's selection is
    directly checkable, plus a universe_panel admitting all 4 symbols from
    day one.
    """
    dates = pd.bdate_range("2016-06-01", periods=n_days)
    rng = np.random.default_rng(seed)
    drift = {"AAA": 0.0020, "BBB": 0.0006, "CCC": -0.0002, "DDD": -0.0015}
    rows = []
    for symbol in SYMBOLS:
        price = 100.0
        for date in dates:
            price *= 1.0 + drift[symbol] + rng.normal(0, 0.003)
            # momentum_252_21 is fabricated directly (not derived from price)
            # to keep the fixture small and the ranking unambiguous: AAA is
            # always the highest-momentum name, DDD always the lowest.
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "close": price,
                    "momentum_252_21": drift[symbol] * 100 + rng.normal(0, 0.001),
                    "beta_252_spy": {"AAA": 1.4, "BBB": 1.0, "CCC": 0.8, "DDD": 0.5}[symbol],
                    "label_rank_5": rng.uniform(0, 1),
                }
            )
    panel = pd.DataFrame(rows)
    month_ends = (
        panel[["trade_date"]]
        .drop_duplicates()
        .assign(month_key=lambda d: d["trade_date"].dt.to_period("M"))
        .groupby("month_key")["trade_date"]
        .max()
    )
    universe_rows = [
        {"month_end": month_end, "symbol": symbol} for month_end in month_ends for symbol in SYMBOLS
    ]
    universe_panel = pd.DataFrame(universe_rows)
    return panel, universe_panel


def test_build_weight_schedule_b1_always_selects_the_highest_momentum_name() -> None:
    panel, universe_panel = _synthetic_panel()
    schedule = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=MomentumFactorStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=1,
        hedge="none",
    )
    assert schedule  # at least one rebalance happened in the test year
    for event in schedule:
        assert set(event.selected) == {"AAA"}


def test_build_weight_schedule_b0_equal_weights_the_full_universe() -> None:
    panel, universe_panel = _synthetic_panel()
    schedule = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=EqualWeightUniverseStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="none",
    )
    for event in schedule:
        assert set(event.selected) == set(SYMBOLS)
        for weight in event.selected.values():
            assert weight == pytest.approx(1.0 / len(SYMBOLS))


def test_build_weight_schedule_spy_beta_hedge_matches_weighted_average_beta() -> None:
    panel, universe_panel = _synthetic_panel()
    schedule = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=EqualWeightUniverseStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="spy_beta_hedge",
    )
    event = schedule[0]
    expected_beta = np.mean([1.4, 1.0, 0.8, 0.5])  # equal-weighted book of all 4
    assert event.portfolio_beta == pytest.approx(expected_beta)
    assert event.selected["__SPY_HEDGE__"] == pytest.approx(-expected_beta)


def test_build_weight_schedule_never_uses_a_fit_that_saw_the_test_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel, universe_panel = _synthetic_panel()
    seen_max_dates: list[pd.Timestamp] = []

    class _RecordingStrategy:
        def fit(self, train_frame: pd.DataFrame) -> None:
            seen_max_dates.append(train_frame["trade_date"].max())

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_RecordingStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="none",
    )
    assert seen_max_dates, "fit() was never called"
    first_test_date = pd.Timestamp("2017-01-01")
    for train_max in seen_max_dates:
        assert train_max < first_test_date


def test_build_weight_schedule_extra_train_columns_ride_along_without_default() -> None:
    # Wave B's B3 grid needs several label horizons in one train_frame at
    # once (see loop.build_weight_schedule's extra_train_columns docstring).
    panel, universe_panel = _synthetic_panel()
    panel["label_rank_21"] = 1.0 - panel["label_rank_5"]
    seen_columns: list[frozenset[str]] = []

    class _RecordingStrategy:
        def fit(self, train_frame: pd.DataFrame) -> None:
            seen_columns.append(frozenset(train_frame.columns))

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_RecordingStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="none",
        extra_train_columns=["label_rank_21"],
    )
    assert seen_columns, "fit() was never called"
    for columns in seen_columns:
        assert "label_rank_21" in columns

    # Omitting extra_train_columns (every existing B0-B3 caller) leaves
    # train_frame exactly as narrow as before -- no accidental default leak.
    seen_columns.clear()
    loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_RecordingStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="none",
    )
    for columns in seen_columns:
        assert "label_rank_21" not in columns


def test_build_weight_schedule_extra_train_columns_nan_does_not_shrink_training_rows() -> None:
    # A strategy juggling several label horizons already does its own
    # per-column dropna one horizon at a time (see GridSelectedLightGBMStrategy).
    # build_weight_schedule's own row mask must therefore ignore NaNs in
    # extra_train_columns -- otherwise one unresolved long-horizon label
    # would wrongly drop rows a shorter-horizon cell could still have used.
    panel, universe_panel = _synthetic_panel()
    panel["label_rank_21"] = np.nan  # entirely unresolved, on purpose
    row_counts: list[int] = []

    class _RecordingStrategy:
        def fit(self, train_frame: pd.DataFrame) -> None:
            row_counts.append(len(train_frame))

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_RecordingStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=None,
        hedge="none",
        extra_train_columns=["label_rank_21"],
    )
    assert row_counts and all(count > 0 for count in row_counts)


def test_returns_from_weight_schedule_applies_cost_on_the_first_day() -> None:
    dates = pd.bdate_range("2020-01-06", periods=10)  # starts on a Monday
    price_wide = pd.DataFrame({"AAA": [100.0 * (1.01**i) for i in range(len(dates))]}, index=dates)
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(), universe_size=1, selected={"AAA": 1.0}, portfolio_beta=None
        )
    ]
    zero_cost = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=False
    )
    with_cost = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=50.0, include_hedge=False
    )
    # First day should differ by exactly the cost; later days identical.
    # turnover Sigma|delta w| = |1.0 - 0.0| = 1.0 (a fresh 100% allocation)
    # is already two-sided; cost = turnover * cost_bps_per_side / 10_000, not
    # turnover * 2 * cost_bps_per_side / 10_000 (see loop.py's cost_rate
    # comment -- that extra factor of 2 double-counted the two-sidedness
    # already baked into turnover).
    assert with_cost.iloc[0] == pytest.approx(zero_cost.iloc[0] - 50.0 / 10_000.0)
    pd.testing.assert_series_equal(with_cost.iloc[1:], zero_cost.iloc[1:])


def test_returns_from_weight_schedule_steady_state_turnover_cost() -> None:
    # Rebalance from a full AAA book into a half-AAA-half-BBB book: turnover
    # Sigma|delta w| = |0.5-1.0| + |0.5-0.0| = 1.0 (selling half of AAA,
    # buying half of BBB -- "half the book" turns over). Cost should be
    # exactly 1.0 * cost_bps_per_side / 10_000, not double that.
    dates = pd.bdate_range("2020-01-06", periods=10)
    price_wide = pd.DataFrame(
        {"AAA": [100.0] * len(dates), "BBB": [50.0] * len(dates)}, index=dates
    )
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(), universe_size=2, selected={"AAA": 1.0}, portfolio_beta=None
        ),
        loop.RebalanceEvent(
            date=dates[3].isoformat(),
            universe_size=2,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        ),
    ]
    zero_cost = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=False
    )
    with_cost = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=10.0, include_hedge=False
    )
    # The second event's window starts the first trading day *after* its
    # signal date (dates[3]) -- i.e. dates[4] -- per the module's "signal
    # close -> execute next session" convention. Label-based lookup avoids
    # having to re-derive that offset positionally.
    rebalance_execution_date = dates[4]
    assert with_cost.loc[rebalance_execution_date] == pytest.approx(
        zero_cost.loc[rebalance_execution_date] - 1.0 * 10.0 / 10_000.0
    )


def test_returns_from_weight_schedule_hedge_leg_subtracts_spy_return() -> None:
    dates = pd.bdate_range("2020-01-06", periods=5)
    price_wide = pd.DataFrame({"AAA": [100.0] * len(dates)}, index=dates)  # AAA flat
    spy_returns = pd.Series([0.0, 0.02, -0.01, 0.0, 0.0], index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(),
            universe_size=1,
            selected={"AAA": 1.0, "__SPY_HEDGE__": -1.0},
            portfolio_beta=1.0,
        )
    ]
    with_hedge = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=True
    )
    without_hedge = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=False
    )
    # AAA itself never moves, so without the hedge every return is 0.
    assert (without_hedge == 0.0).all()
    # With a -1.0 SPY hedge, the day-2 return should be -1.0 * 0.02.
    assert with_hedge.loc[dates[1]] == pytest.approx(-0.02)


def test_returns_from_weight_schedule_matches_simple_compounding_when_no_dispersion() -> None:
    """When every held name has the identical daily return, buy-and-hold and
    daily-rebalance-to-constant-weight are mathematically the same thing
    (rebalancing a basket of identical assets back to any fixed weights is
    a no-op) -- this is the degenerate case the pre-2026-09-10-fix formula
    got right, which is exactly why no existing single-asset/single-day
    test caught the compounding bug the next test below exercises: the two
    formulas only diverge once held names have real return dispersion
    within a multi-day holding window.
    """
    dates = pd.bdate_range("2020-01-06", periods=3)
    common = [100.0, 110.0, 99.0]  # +10%, then -10%
    price_wide = pd.DataFrame({"AAA": common, "BBB": common}, index=dates)
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(),
            universe_size=2,
            selected={"AAA": 0.3, "BBB": 0.7},  # deliberately uneven weights
            portfolio_beta=None,
        )
    ]
    returns = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=False
    )
    expected = pd.Series([0.10, -0.10], index=dates[1:])
    pd.testing.assert_series_equal(returns, expected, check_names=False, check_freq=False)


def test_returns_from_weight_schedule_is_buy_and_hold_not_daily_rebalanced() -> None:
    """2026-09-10 fix regression (Step 13 Track M, coordinator-directed
    reconciliation against an independent from-scratch weekly momentum
    check -- see loop.py's returns_from_weight_schedule docstring). The
    pre-fix formula recomputed every day's return with the *same*,
    never-updated target weight -- mathematically rebalancing the book
    back to that exact weight every single day -- which is provably
    different from holding the position bought at the window's start
    whenever held names have return dispersion within the window.

    AAA (+20% then -20%) and BBB (-20% then +20%) each round-trip to
    exactly the same -4% total return over the two days
    (1.2*0.8 - 1 == 0.8*1.2 - 1 == -0.04). Any fixed-weight buy-and-hold
    combination of two names with identical total returns must itself
    realize that same total return, by a trivial weighted-average
    identity -- regardless of the day-by-day path. The pre-fix formula
    instead computed 0.5*(+0.20)+0.5*(-0.20) = 0.0 on day 1 and
    0.5*(-0.20)+0.5*(+0.20) = 0.0 on day 2, compounding to a flat 0.0%: an
    entirely fabricated "volatility harvesting" gain of +4 percentage
    points that a real, weekly-rebalanced buy-and-hold position never
    earns. This is the same mechanism that overstated a real top-20
    momentum backtest's CAGR by ~8.6 percentage points when checked against
    133 real weekly signals (see the loop.py docstring and the Step 13
    progress log).
    """
    dates = pd.bdate_range("2020-01-06", periods=3)  # signal day + 2 holding days
    price_wide = pd.DataFrame(
        {
            "AAA": [100.0, 120.0, 96.0],  # +20%, then -20%
            "BBB": [100.0, 80.0, 96.0],  # -20%, then +20%
        },
        index=dates,
    )
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(),
            universe_size=2,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        )
    ]
    returns = loop.returns_from_weight_schedule(
        schedule, price_wide, spy_returns, cost_bps_per_side=0.0, include_hedge=False
    )
    total_return = (1.0 + returns).prod() - 1.0
    assert total_return == pytest.approx(-0.04, abs=1e-9)
    # Day 1: real dispersion (+20% vs -20%) happens to net to a 0 weighted
    # average -- both the pre- and post-fix formulas agree here, same as
    # the no-dispersion test above.
    assert returns.iloc[0] == pytest.approx(0.0, abs=1e-9)
    # Day 2 must reflect AAA/BBB's now-drifted (unequal) dollar weights,
    # not another 0.5/0.5 constant-weight recombination -- the pre-fix
    # formula would have given 0.0 here (and thus 0.0 total, not -4%).
    assert returns.iloc[1] == pytest.approx(-0.04, abs=1e-9)


def test_dsr_trial_count_grows_with_distinct_configs_in_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(loop, "LEDGER_PATH", ledger_path)
    assert loop._dsr_trial_count_for_family("fam_x", "hash_a") == loop._MIN_DSR_TRIAL_COUNT

    loop._append_ledger({"config_hash": "hash_a", "family": "fam_x"})
    loop._append_ledger({"config_hash": "hash_b", "family": "fam_x"})
    loop._append_ledger({"config_hash": "hash_c", "family": "fam_y"})  # different family

    assert loop._dsr_trial_count_for_family("fam_x", "hash_a") == 2
    assert loop._dsr_trial_count_for_family("fam_x", "hash_new") == 3


def test_append_ledger_does_not_duplicate_the_same_config_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(loop, "LEDGER_PATH", ledger_path)
    first = loop._append_ledger({"config_hash": "hash_a", "family": "fam_x", "v": 1})
    second = loop._append_ledger({"config_hash": "hash_a", "family": "fam_x", "v": 2})
    assert first is True
    assert second is False
    assert len(ledger_path.read_text().splitlines()) == 1


def test_experiment_config_hash_is_stable_and_sensitive_to_hyperparameters() -> None:
    base = loop.ExperimentConfig(
        experiment_id="e1",
        family="fam",
        model_kind="ridge",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=("ret_21", "ret_63"),
    )
    same = loop.ExperimentConfig(
        experiment_id="e1-rerun",
        family="fam",
        model_kind="ridge",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=("ret_63", "ret_21"),  # order should not matter
    )
    different = loop.ExperimentConfig(
        experiment_id="e2",
        family="fam",
        model_kind="ridge",
        feature_set="daily_only",
        label_horizon_days=10,
        feature_columns=("ret_21", "ret_63"),
    )
    assert base.config_hash() == same.config_hash()
    assert base.config_hash() != different.config_hash()


def test_train_row_dates_rebalance_dates_restricts_the_fit_to_weekly_rows() -> None:
    # A fit that sees only rebalance-day rows must receive exactly those rows
    # (5x fewer than "all"), while the traded schedule itself is unchanged.
    dates = pd.bdate_range("2019-01-07", "2020-12-31")
    symbols = ["AAA", "BBB", "CCC"]
    rng = np.random.default_rng(11)
    panel = pd.DataFrame(
        {
            "symbol": np.repeat(symbols, len(dates)),
            "trade_date": np.tile(dates, len(symbols)),
            "close": rng.uniform(50, 150, len(dates) * len(symbols)),
            "feature": rng.standard_normal(len(dates) * len(symbols)),
            "label": rng.random(len(dates) * len(symbols)),
            "beta_252_spy": 1.0,
        }
    )
    universe_panel = pd.DataFrame(
        {
            "symbol": symbols,
            "month_end": [pd.Timestamp("2019-01-31")] * len(symbols),
        }
    )
    seen: dict[str, pd.DataFrame] = {}

    class _Recorder:
        def fit(self, train_frame: pd.DataFrame) -> None:
            seen[str(len(seen))] = train_frame

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    common = dict(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_Recorder,
        feature_columns=["feature"],
        label_column="label",
        label_horizon_days=5,
        test_years=[2020],
        top_k=2,
        hedge="none",
    )
    schedule_all = loop.build_weight_schedule(**common, train_row_dates="all")
    rows_all = len(seen["0"])
    seen.clear()
    schedule_weekly = loop.build_weight_schedule(**common, train_row_dates="rebalance_dates")
    weekly_frame = seen["0"]

    weekly_dates = set(loop.weekly_rebalance_dates(pd.DatetimeIndex(sorted(dates))))
    assert set(weekly_frame["trade_date"]) <= weekly_dates
    # ~5 trading days per week, so the weekly fit sees far fewer rows ...
    assert len(weekly_frame) < rows_all / 3
    # ... but the traded weekly schedule is identical either way.
    assert [event.date for event in schedule_weekly] == [event.date for event in schedule_all]


def test_train_row_dates_enters_the_config_hash() -> None:
    base = loop.ExperimentConfig(
        experiment_id="x",
        family="f",
        model_kind="ridge",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=("feature",),
    )
    weekly = dataclasses.replace(base, train_row_dates="rebalance_dates")
    assert base.config_hash() != weekly.config_hash()


def test_execution_enters_the_config_hash() -> None:
    base = loop.ExperimentConfig(
        experiment_id="x",
        family="f",
        model_kind="ridge",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=("feature",),
    )
    assert base.execution == "close_marked"  # default, unchanged from before this field existed
    next_open = dataclasses.replace(base, execution="next_open")
    assert base.config_hash() != next_open.config_hash()


def test_returns_from_weight_schedule_next_open_shifts_window_by_one_day_and_uses_open_prices() -> (
    None
):
    dates = pd.bdate_range("2020-01-06", periods=10)  # starts on a Monday
    open_wide = pd.DataFrame({"AAA": [100.0 * (1.02**i) for i in range(len(dates))]}, index=dates)
    price_wide = pd.DataFrame(
        {"AAA": [999.0] * len(dates)}, index=dates
    )  # sentinel: must be unused
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(), universe_size=1, selected={"AAA": 1.0}, portfolio_beta=None
        )
    ]
    result = loop.returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=0.0,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    # close_marked's window would start at dates[1] (the trading day right
    # after the signal date dates[0]) and mark AAA's close-to-close return
    # that same day. next_open instead fills at dates[1]'s *open* -- the new
    # weights cannot capture dates[1]'s own open-to-close move, so dates[1]
    # only carries the (here zero) execution cost, and the first real
    # open-to-open move realized under the new weights lands on dates[2].
    assert result.loc[dates[1]] == pytest.approx(0.0)
    expected_day2 = open_wide["AAA"].iloc[2] / open_wide["AAA"].iloc[1] - 1.0
    assert result.loc[dates[2]] == pytest.approx(expected_day2)
    assert expected_day2 == pytest.approx(0.02)


def test_returns_from_weight_schedule_next_open_charges_cost_on_execution_day() -> None:
    dates = pd.bdate_range("2020-01-06", periods=10)
    open_wide = pd.DataFrame({"AAA": [100.0] * len(dates), "BBB": [50.0] * len(dates)}, index=dates)
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(), universe_size=2, selected={"AAA": 1.0}, portfolio_beta=None
        ),
        loop.RebalanceEvent(
            date=dates[3].isoformat(),
            universe_size=2,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        ),
    ]
    zero_cost = loop.returns_from_weight_schedule(
        schedule,
        open_wide,
        spy_returns,
        cost_bps_per_side=0.0,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    with_cost = loop.returns_from_weight_schedule(
        schedule,
        open_wide,
        spy_returns,
        cost_bps_per_side=10.0,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide,
    )
    # The second event's signal date is dates[3]; its execution (open-fill)
    # day is dates[4] -- one day *before* where its own next_open return
    # window starts (dates[5]), because dates[4] is still the tail of the
    # *first* event's one-day-lagged window. Cost must land on the actual
    # fill day, not on "day zero of this event's own window".
    execution_date = dates[4]
    assert with_cost.loc[execution_date] == pytest.approx(
        zero_cost.loc[execution_date] - 1.0 * 10.0 / 10_000.0
    )


def test_returns_from_weight_schedule_next_open_requires_open_wide() -> None:
    dates = pd.bdate_range("2020-01-06", periods=5)
    price_wide = pd.DataFrame({"AAA": [100.0] * len(dates)}, index=dates)
    spy_returns = pd.Series(0.0, index=dates)
    schedule = [
        loop.RebalanceEvent(
            date=dates[0].isoformat(), universe_size=1, selected={"AAA": 1.0}, portfolio_beta=None
        )
    ]
    with pytest.raises(ValueError, match="next_open"):
        loop.returns_from_weight_schedule(
            schedule,
            price_wide,
            spy_returns,
            cost_bps_per_side=0.0,
            include_hedge=False,
            execution="next_open",
        )


# ---------------------------------------------------------------------------
# Step 13 Track M additions (docs/plan-step-13-recent-high-return-ml-and-llm-
# tracks-2026-09-09.zh.md section 3.3): train_window_months, refit_frequency,
# recency_halflife_days, trend_gate, universe_top_n. Every test in this
# section double-checks the "every existing default stays unchanged"
# requirement alongside the new behavior itself.
# ---------------------------------------------------------------------------


def _pre_step13_config_hash(config: loop.ExperimentConfig) -> str:
    """A frozen copy of ExperimentConfig.config_hash's payload exactly as it
    was before the Step 13 fields existed -- the "golden" reference this
    module's own hash must still reproduce for any config that never touches
    those fields, since already-recorded B0-B3 ledger rows were hashed by
    this exact formula and must stay reproducible.
    """
    import hashlib as _hashlib
    import json as _json

    payload = {
        "family": config.family,
        "model_kind": config.model_kind,
        "feature_set": config.feature_set,
        "label_horizon_days": config.label_horizon_days,
        "feature_columns": sorted(config.feature_columns),
        "top_k": config.top_k,
        "hedge": config.hedge,
        "train_row_dates": config.train_row_dates,
        "execution": config.execution,
        "rebalance": config.rebalance,
        "weighting": config.weighting,
        "cost_bps_per_side": config.cost_bps_per_side,
        "stress_cost_bps_per_side": config.stress_cost_bps_per_side,
        "test_years": list(config.test_years),
        "hyperparameters": config.hyperparameters,
    }
    blob = _json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return _hashlib.sha256(blob).hexdigest()[:16]


def _base_config(**overrides: object) -> loop.ExperimentConfig:
    defaults: dict[str, object] = dict(
        experiment_id="step13_test",
        family="step13_recent_high_return",
        model_kind="rule",
        feature_set="daily27",
        label_horizon_days=5,
        feature_columns=("momentum_252_21",),
    )
    defaults.update(overrides)
    return loop.ExperimentConfig(**defaults)  # type: ignore[arg-type]


def test_experiment_config_hash_matches_pre_step13_formula_when_fields_are_default() -> None:
    config = _base_config()
    assert config.config_hash() == _pre_step13_config_hash(config)


def test_experiment_config_hash_changes_for_each_new_field_when_set() -> None:
    baseline = _base_config().config_hash()
    assert _base_config(train_window_months=24).config_hash() != baseline
    assert _base_config(refit_frequency="quarterly").config_hash() != baseline
    assert _base_config(recency_halflife_days=126.0).config_hash() != baseline
    assert _base_config(trend_gate={"benchmark": "SPY", "sma_days": 200}).config_hash() != baseline
    assert _base_config(universe_top_n=500).config_hash() != baseline


def test_universe_as_of_calendar_month_top_n_restricts_by_adv_rank() -> None:
    panel = pd.DataFrame(
        {
            "month_end": pd.to_datetime(["2020-01-31"] * 3),
            "symbol": ["AAA", "BBB", "CCC"],
            "adv_rank": [1, 2, 3],
        }
    )
    as_of = pd.Timestamp("2020-01-31")
    assert loop.universe_as_of_calendar_month(panel, as_of) == {"AAA", "BBB", "CCC"}
    assert loop.universe_as_of_calendar_month(panel, as_of, top_n=2) == {"AAA", "BBB"}
    assert loop.universe_as_of_calendar_month(panel, as_of, top_n=1) == {"AAA"}


def testrecency_sample_weight_matches_closed_form_half_life() -> None:
    as_of = pd.Timestamp("2024-06-30")
    trade_dates = pd.Series([as_of, as_of - pd.Timedelta(days=126), pd.Timestamp("2024-01-01")])
    weight = loop.recency_sample_weight(trade_dates, as_of=as_of, halflife_days=126.0)
    assert weight.iloc[0] == pytest.approx(1.0)  # age 0 -> full weight
    assert weight.iloc[1] == pytest.approx(0.5)  # age 126 days -> exactly one half-life
    older_age_days = (as_of - trade_dates.iloc[2]).days
    assert weight.iloc[2] == pytest.approx(0.5 ** (older_age_days / 126.0))


def testfit_with_optional_sample_weight_passes_only_when_strategy_declares_it() -> None:
    received: dict[str, object] = {}

    class _AcceptsWeight:
        def fit(self, train_frame: pd.DataFrame, sample_weight: pd.Series | None = None) -> None:
            received["weight"] = sample_weight

    class _DoesNotAcceptWeight:
        def fit(self, train_frame: pd.DataFrame) -> None:
            received["called_without_weight"] = True

    frame = pd.DataFrame({"trade_date": pd.to_datetime(["2024-01-02"])})
    weight_series = pd.Series([0.5])

    loop.fit_with_optional_sample_weight(_AcceptsWeight(), frame, weight_series)
    assert received["weight"] is weight_series

    received.clear()
    # Must not raise TypeError even though this strategy's fit() has no
    # sample_weight parameter at all -- this is exactly what protects every
    # existing/future RankingStrategy this file does not own.
    loop.fit_with_optional_sample_weight(_DoesNotAcceptWeight(), frame, weight_series)
    assert received["called_without_weight"] is True


def test_build_weight_schedule_train_window_months_truncates_the_training_window() -> None:
    panel, universe_panel = _synthetic_panel(n_days=650)  # ~2.6 years of history
    seen_min_dates: dict[str, pd.Timestamp] = {}

    def _make_recorder(key: str) -> type:
        class _Recorder:
            def fit(self, train_frame: pd.DataFrame) -> None:
                seen_min_dates[key] = train_frame["trade_date"].min()

            def score(self, asof_frame: pd.DataFrame) -> pd.Series:
                return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

        return _Recorder

    common_kwargs = dict(
        panel=panel,
        universe_panel=universe_panel,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2018,),
        top_k=None,
        hedge="none",
    )
    loop.build_weight_schedule(strategy_factory=_make_recorder("expanding"), **common_kwargs)
    loop.build_weight_schedule(
        strategy_factory=_make_recorder("trailing_6m"), train_window_months=6, **common_kwargs
    )
    assert seen_min_dates["expanding"] < seen_min_dates["trailing_6m"]
    # The trailing window's earliest training row should be close to (not
    # much earlier than) 6 months before its own latest training row.
    panel_dates = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    trailing_frame_min = seen_min_dates["trailing_6m"]
    assert (panel_dates[panel_dates <= trailing_frame_min]).max() == trailing_frame_min


def test_build_weight_schedule_refit_frequency_quarterly_refits_once_per_quarter() -> None:
    panel, universe_panel = _synthetic_panel(n_days=650)
    fit_calls: list[pd.Timestamp] = []

    class _Recorder:
        def fit(self, train_frame: pd.DataFrame) -> None:
            fit_calls.append(train_frame["trade_date"].max())

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    common_kwargs = dict(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_Recorder,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2018,),
        top_k=None,
        hedge="none",
    )
    yearly_events = loop.build_weight_schedule(refit_frequency="yearly", **common_kwargs)
    yearly_fit_calls = len(fit_calls)
    fit_calls.clear()
    quarterly_events = loop.build_weight_schedule(refit_frequency="quarterly", **common_kwargs)

    assert yearly_fit_calls == 1
    assert len(fit_calls) == 4  # one refit per calendar quarter present in 2018

    # No week is dropped or double-counted at a quarter boundary: the set of
    # rebalance dates produced must match exactly between the two modes for
    # the same test year (see build_weight_schedule's docstring on why the
    # quarterly branch filters a *globally* computed weekly-date sequence
    # instead of recomputing "last day of week" on a quarter-only subset).
    yearly_dates = {event.date for event in yearly_events}
    quarterly_dates = {event.date for event in quarterly_events}
    assert yearly_dates == quarterly_dates


def test_build_weight_schedule_max_periods_caps_walk_forward_periods() -> None:
    """2026-09-10 memory-fix dry-run support: max_periods=1 processes only
    the first walk-forward period (here, 2018 Q1 under quarterly refit,
    which the test above already established is 4 periods for a full
    year) and stops -- one refit, not four, and every produced event's
    date falls in Q1.
    """
    panel, universe_panel = _synthetic_panel(n_days=650)
    fit_calls: list[pd.Timestamp] = []

    class _Recorder:
        def fit(self, train_frame: pd.DataFrame) -> None:
            fit_calls.append(train_frame["trade_date"].max())

        def score(self, asof_frame: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())

    events = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=_Recorder,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2018,),
        top_k=None,
        hedge="none",
        refit_frequency="quarterly",
        max_periods=1,
    )
    assert len(fit_calls) == 1
    assert events  # the one period that did run still produced real events
    for event in events:
        assert pd.Timestamp(event.date).quarter == 1


def test_build_weight_schedule_trend_gate_series_overrides_closed_weeks_to_cash() -> None:
    panel, universe_panel = _synthetic_panel()
    events = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=MomentumFactorStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=1,
        hedge="none",
    )
    assert events, "no events produced to build a gate series from"
    all_dates = pd.DatetimeIndex([pd.Timestamp(event.date) for event in events])
    # Close the gate for exactly the first half of the test year's rebalance
    # dates, leave the rest open.
    midpoint = len(all_dates) // 2
    gate_series = pd.Series([i >= midpoint for i in range(len(all_dates))], index=all_dates)

    gated_events = loop.build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=MomentumFactorStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=(2017,),
        top_k=1,
        hedge="none",
        trend_gate_series=gate_series,
        trend_gate_cash_symbol="BIL",
    )
    for i, event in enumerate(gated_events):
        if i < midpoint:
            assert event.selected == {"BIL": 1.0}
            assert event.portfolio_beta is None
        else:
            # Gate open: real strategy picks, identical to the ungated run.
            assert event.selected == events[i].selected


def test_run_experiment_requires_trend_gate_series_when_config_declares_trend_gate(
    tmp_path: Path,
) -> None:
    from open_composer.research.kernel import loop as loop_module

    panel, universe_panel = _synthetic_panel()
    config = loop.ExperimentConfig(
        experiment_id="step13_missing_gate_series",
        family="step13_recent_high_return",
        model_kind="rule",
        feature_set="daily27",
        label_horizon_days=5,
        feature_columns=("momentum_252_21",),
        top_k=1,
        test_years=(2017,),
        trend_gate={"benchmark": "SPY", "sma_days": 200, "cash_symbol": "BIL"},
    )
    dates = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    spy_returns = pd.Series(0.0, index=dates)
    with pytest.raises(ValueError, match="trend_gate_series"):
        loop_module.run_experiment(
            config,
            panel=panel,
            universe_panel=universe_panel,
            label_column="label_rank_5",
            strategy_factory=MomentumFactorStrategy,
            spy_returns=spy_returns,
            qqq_returns=spy_returns,
            tqqq_returns=spy_returns,
            bil_returns=spy_returns,
            write_ledger=False,
            write_tearsheet=False,
            write_mlflow=False,
        )
