from pathlib import Path

import pandas as pd
import pytest

from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.lab import book_engine, spec_engine
from open_composer.lab.ablation import Ablation, check_ablations
from open_composer.lab.example import synthetic_bars as fixture_frame
from open_composer.lab.example import synthetic_spec as fixture_spec
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.equity_book.backtest import BookConfig


@pytest.mark.parametrize("timeframe", ["daily", "1m"])
def test_reference_adapter_exposes_existing_curve_without_changing_pnl(tmp_path: Path, timeframe):
    spec, frame = fixture_spec(timeframe), fixture_frame(timeframe)
    native = backtest_frame(spec, frame, root=tmp_path, start_equity=10_000)
    adapted = spec_engine(spec, frame, root=tmp_path, run_id="fixture", initial_equity_usd=10_000)
    assert native.run.total_fees > 0
    assert adapted.net_profit_usd == pytest.approx(native.run.end_equity - 10_000)
    assert adapted.native["equity_curve"] == native.equity_curve
    assert adapted.native["run"]["total_fees"] == native.run.total_fees
    assert 10_000 * (1 + adapted.net_returns).prod() == pytest.approx(native.run.end_equity)
    assert len(adapted.net_returns) == (8 if timeframe == "daily" else 1)
    assert BacktestArtifacts(native.run, [], []).equity_curve == []


def test_warmup_boundary_preserves_native_scoring_clock(tmp_path: Path):
    spec, frame = fixture_spec(), fixture_frame()
    native = backtest_frame(spec, frame, root=tmp_path, evaluation_start_index=2)
    adapted = spec_engine(spec, frame, root=tmp_path, run_id="warm", evaluation_start_index=2)
    assert adapted.end_equity_usd == native.run.end_equity
    assert adapted.net_returns.index[0] == frame["timestamp"].iloc[2]


@pytest.mark.parametrize("timeframe", ["daily", "1m"])
def test_event_adapter_exposes_native_curve_and_costs(tmp_path: Path, timeframe):
    pytest.importorskip("nautilus_trader")
    output = spec_engine(
        fixture_spec(timeframe),
        fixture_frame(timeframe),
        root=tmp_path,
        run_id=f"event-fixture-{timeframe}",
        initial_equity_usd=10_000,
        backend="nautilus_trader",
    )
    assert output.native["run"]["execution_backend"] == "nautilus_backtest"
    assert output.native["run"]["total_fees"] > 0
    assert output.native["equity_curve"][-1] == pytest.approx(output.end_equity_usd)
    assert 10_000 * (1 + output.net_returns).prod() == pytest.approx(output.end_equity_usd)


def test_triggering_fixtures_detect_ignored_stop_take_cost_and_size_configs(tmp_path: Path):
    frame = fixture_frame()
    config = {"stop_loss_pct": 99, "take_profit_pct": 99, "commission_pct": 0, "weight": 0.7}

    def observe(params, bars):
        spec = fixture_spec(
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=params["take_profit_pct"],
            max_position_weight=params["weight"],
        )
        raw = spec.model_dump()
        raw["costs"]["commission_pct"] = params["commission_pct"]
        output = spec_engine(
            StrategySpec.model_validate(raw), bars, root=tmp_path, run_id="ablation"
        )
        return {
            "profit": output.net_profit_usd,
            "fees": output.native["run"]["total_fees"],
            "signals": output.native["run"]["signals"],
        }

    cases = [
        Ablation("stop_loss_pct", 5, frame, "91 close breaches the entry's 5% stop"),
        Ablation("take_profit_pct", 5, frame, "115 close crosses the entry's 5% take-profit"),
        Ablation("commission_pct", 0.2, frame, "The first next-open entry pays a fee"),
        Ablation("weight", 0.3, frame, "A nonzero position is opened"),
    ]
    report = check_ablations(config, cases, observe)
    assert len(report) == 4
    with pytest.raises(ValueError, match="No observed effect"):
        check_ablations(config, cases[:1], lambda params, data: {"ignored": 1.0})


def test_no_trigger_can_reasonably_leave_output_equal(tmp_path: Path):
    frame = fixture_frame()
    frame.loc[:, ["open", "close"]] = 100.0
    a = spec_engine(fixture_spec(stop_loss_pct=20), frame, root=tmp_path, run_id="a")
    b = spec_engine(fixture_spec(stop_loss_pct=50), frame, root=tmp_path, run_id="b")
    assert a.end_equity_usd == b.end_equity_usd


def test_daily_book_reuses_cost_ledger_hygiene_and_trigger_exclusion():
    dates = pd.bdate_range("2024-01-02", periods=8)
    close = pd.DataFrame({"AAA": [100, 101, 99, 102, 1, 1.1, 1.2, 1.15]}, index=dates)
    calls = []

    def decide(date, state):
        calls.append(date)
        return {"AAA": 0.5}

    output = book_engine(
        close,
        close.copy(),
        decide,
        config=BookConfig(freq="D", initial_equity=10_000, cost_bp_per_side=10),
    )
    assert dates[4] not in calls
    assert output.native["price_hygiene"]["symbols_masked"] == 1
    assert output.ledger["cost_spread"].sum() > 0
    assert output.end_equity_usd == output.ledger["equity"].iloc[-1]
    assert close.iloc[0, 0] == 100  # Caller data is never mutated.


def test_book_rotation_keeps_old_overnight_and_charges_both_order_sides():
    dates = pd.bdate_range("2024-01-02", periods=4)
    close = pd.DataFrame({"A": [100., 100., 120., 120.],
                          "B": [100., 100., 110., 110.]}, index=dates)
    open_ = close.copy()
    open_.loc[dates[2], "B"] = 80.
    output = book_engine(close, open_, lambda day, state: {"B": 1.},
        config=BookConfig(initial_equity=10_000, initial_weights={"A": 1.},
                          signal_dates=[dates[1]], cost_bp_per_side=10.))
    day = output.ledger.loc[dates[2]]
    # Old A earns +20% overnight. New B earns only 110/80-1 after its open fill.
    # Sell $12k A and buy $12k B: $24 total cost, deducted from account cash.
    assert day.equity_open_pre == pytest.approx(12_000.)
    assert day.turnover == pytest.approx(2.)
    assert day.cost_spread == pytest.approx(24. / 10_000.)
    assert day.equity == pytest.approx(12_000. * (110. / 80.) - 24.)
