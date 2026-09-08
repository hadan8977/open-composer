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
