"""``kernel.pick_export`` -- the additive pick tap on ``build_weight_schedule``.

The load-bearing assertion here is ``test_pick_observer_does_not_change_the
_schedule``: the hook exists so a meta-labeling round can see the inside of
each rebalance, and it is only safe if attaching it leaves the produced
weight schedule byte-for-byte identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel import pick_export
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy
from open_composer.research.kernel.loop import RebalanceEvent, build_weight_schedule

SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2016-01-04", "2018-06-29")
    rng = np.random.default_rng(11)
    rows = []
    for index, symbol in enumerate(SYMBOLS):
        for date in dates:
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "momentum_252_21": index * 0.1 + rng.normal(0, 0.001),
                    "vol_63": 0.2 + index * 0.01,
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
    universe_panel = pd.DataFrame(
        [{"month_end": end, "symbol": symbol} for end in month_ends for symbol in SYMBOLS]
    )
    return panel, universe_panel


def _build(pick_observer=None):
    panel, universe_panel = _panel()
    return build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=MomentumFactorStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=[2018],
        top_k=2,
        hedge="none",
        pick_observer=pick_observer,
    )


def test_pick_observer_does_not_change_the_schedule() -> None:
    without = _build()
    collector = pick_export.PickCollector(feature_columns=("momentum_252_21", "vol_63"))
    with_observer = _build(pick_observer=collector)
    assert with_observer == without
    assert collector.rows


def test_pick_collector_records_weight_score_rank_percentile_and_features() -> None:
    collector = pick_export.PickCollector(feature_columns=("momentum_252_21", "vol_63"))
    schedule = _build(pick_observer=collector)
    frame = collector.to_frame()
    active = [event for event in schedule if event.selected]
    assert len(frame) == 2 * len(active)
    assert set(frame["symbol"]) == {"DDD", "EEE"}  # the two highest-momentum names
    assert np.allclose(frame["weight"], 0.5)
    assert set(frame.columns) == {*pick_export.PICK_FRAME_COLUMNS, "momentum_252_21", "vol_63"}
    # EEE has the highest score every week: rank 1, percentile 1.0 out of 5.
    top = frame.loc[frame["symbol"] == "EEE"]
    assert (top["score_rank"] == 1.0).all()
    assert np.allclose(top["score_pct"], 1.0)
    assert (frame["cohort_size"] == len(SYMBOLS)).all()
    assert (frame["universe_size"] == len(SYMBOLS)).all()
    # the carried feature column is the same value the panel holds, and the
    # score is the scored column itself (MomentumFactorStrategy)
    assert np.allclose(frame["score"], frame["momentum_252_21"])
    assert frame["vol_63"].between(0.2, 0.25).all()


def test_pick_collector_records_a_cash_only_gate_closed_week_as_its_cash_leg() -> None:
    panel, universe_panel = _panel()
    weekly = pd.DatetimeIndex(
        sorted(panel.loc[panel["trade_date"].dt.year == 2018, "trade_date"].unique())
    )
    gate = pd.Series(False, index=weekly)
    collector = pick_export.PickCollector(feature_columns=("momentum_252_21",))
    build_weight_schedule(
        panel=panel,
        universe_panel=universe_panel,
        strategy_factory=MomentumFactorStrategy,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=[2018],
        top_k=2,
        hedge="none",
        trend_gate_series=gate,
        trend_gate_cash_symbol="BIL",
        pick_observer=collector,
    )
    frame = collector.to_frame()
    assert set(frame["symbol"]) == {"BIL"}
    assert np.allclose(frame["weight"], 1.0)
    # a cash leg is not in the scored cohort -- score/rank/percentile are null,
    # never a fabricated zero
    assert frame["score"].isna().all()
    assert frame["score_rank"].isna().all()
    assert frame["momentum_252_21"].isna().all()


def test_weight_schedule_from_pick_frame_drops_zeros_and_fills_cash() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(
                ["2024-01-05", "2024-01-05", "2024-01-05", "2024-01-12"]
            ),
            "symbol": ["AAA", "BBB", "CCC", "AAA"],
            "weight": [0.02, 0.01, 0.0, 0.02],
        }
    )
    schedule = pick_export.weight_schedule_from_pick_frame(
        frame, cash_symbol="BIL", universe_size_column=None
    )
    assert [event.date for event in schedule] == [
        pd.Timestamp("2024-01-05").isoformat(),
        pd.Timestamp("2024-01-12").isoformat(),
    ]
    assert schedule[0].selected == {"AAA": 0.02, "BBB": 0.01, "BIL": 0.97}
    assert schedule[1].selected == {"AAA": 0.02, "BIL": 0.98}
    assert all(pytest.approx(sum(event.selected.values()), abs=1e-12) == 1.0 for event in schedule)


def test_weight_schedule_from_pick_frame_without_cash_symbol_leaves_the_residual_alone() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(["2024-01-05"]),
            "symbol": ["AAA"],
            "weight": [0.02],
        }
    )
    schedule = pick_export.weight_schedule_from_pick_frame(frame, universe_size_column=None)
    assert schedule[0].selected == {"AAA": 0.02}


def test_weight_schedule_from_pick_frame_all_zero_week_becomes_full_cash() -> None:
    frame = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(["2024-01-05", "2024-01-05"]),
            "symbol": ["AAA", "BBB"],
            "weight": [0.0, 0.0],
        }
    )
    schedule = pick_export.weight_schedule_from_pick_frame(
        frame, cash_symbol="BIL", universe_size_column=None
    )
    assert schedule[0].selected == {"BIL": 1.0}


def test_turnover_per_rebalance_is_two_sided_and_skips_empty_events() -> None:
    schedule = [
        RebalanceEvent(
            date="2024-01-05",
            universe_size=5,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        ),
        RebalanceEvent(date="2024-01-12", universe_size=5, selected={}, portfolio_beta=None),
        RebalanceEvent(
            date="2024-01-19",
            universe_size=5,
            selected={"AAA": 0.5, "CCC": 0.5},
            portfolio_beta=None,
        ),
    ]
    turnover = pick_export.turnover_per_rebalance(schedule)
    assert turnover == pytest.approx([1.0, 1.0])
