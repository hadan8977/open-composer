from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260929_36_router_sip as run  # noqa: E402

from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402
from open_composer.research import intraday_daily_rotation as idr  # noqa: E402

SYMBOLS = [*run.UNIVERSE, run.MARKET]


def minute_frame(symbol: str, n_days: int, seed: int, extended: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2024-03-04", periods=n_days)
    rows = []
    price = 100.0 + seed
    for day in sessions:
        start = pd.Timestamp(day.date(), tz="America/New_York") + pd.Timedelta(
            hours=4 if extended else 9, minutes=0 if extended else 30
        )
        end = pd.Timestamp(day.date(), tz="America/New_York") + pd.Timedelta(
            hours=17 if extended else 16
        )
        for ts in pd.date_range(start, end, freq="min", inclusive="left"):
            step = rng.normal(0, 0.0007)
            open_ = price
            price = price * (1 + step)
            rows.append(
                (
                    symbol,
                    ts.tz_convert("UTC"),
                    open_,
                    max(open_, price),
                    min(open_, price),
                    price,
                    float(rng.integers(100, 1000)),
                )
            )
    return pd.DataFrame(
        rows, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    )


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("router_cache")
    frames = [minute_frame(s, 30, i) for i, s in enumerate(SYMBOLS)]
    month = pd.concat(frames, ignore_index=True)
    month = run_regular(month)
    month.to_parquet(path / "2024-03.parquet", index=False)
    return path


def run_regular(frame: pd.DataFrame) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_t20260929_36_router_minute as build

    return build.regular_session(frame)


def test_frozen_params_reproduce_label() -> None:
    assert run.FROZEN_PARAMS.label == run.FROZEN_LABEL
    assert run.FROZEN_PARAMS.selection_style == "opening_reversal"
    assert run.FROZEN_PARAMS.market_gate == "qqq_prior_negative"


def test_extraction_keeps_regular_session_only() -> None:
    frame = minute_frame("AAA", 2, 1)
    kept = run_regular(frame)
    local = pd.to_datetime(kept["timestamp"], utc=True).dt.tz_convert("America/New_York")
    assert (local.dt.hour * 60 + local.dt.minute).min() == 9 * 60 + 30
    assert (local.dt.hour * 60 + local.dt.minute).max() == 15 * 60 + 59
    assert len(kept) == 2 * 390


def test_adapter_matches_original_regular_session_days() -> None:
    frame = minute_frame("AAA", 6, 3)
    mine = run.daily_bars_for_frame(frame)
    theirs = idr._regular_session_days(frame)
    assert list(mine) == list(theirs)
    for date in mine:
        assert np.array_equal(mine[date].opens, theirs[date].opens)
        assert np.array_equal(mine[date].closes, theirs[date].closes)
        assert np.array_equal(mine[date].volumes, theirs[date].volumes)
        assert len(mine[date].timestamps) == len(theirs[date].timestamps)


def test_dataset_is_consumable_by_backtest_params(cache_dir: Path) -> None:
    dataset = run.build_dataset(cache_dir)
    spec = load_strategy_spec(run.SPEC_PATH)
    assert len(dataset.dates) == 30
    metrics = idr._backtest_params(
        spec, dataset, run.FROZEN_PARAMS, start_index=0, end_index=len(dataset.dates)
    )
    assert metrics.days == 30 - run.FROZEN_PARAMS.lookback_days
    assert metrics.benchmark_symbol == run.MARKET


def test_series_matches_backtest_params_and_short_leg_is_empty(cache_dir: Path) -> None:
    dataset = run.build_dataset(cache_dir)
    spec = load_strategy_spec(run.SPEC_PATH)
    specs = run.tier_specs(spec)
    series = run.build_series(dataset, run.FROZEN_PARAMS, spec, specs)
    assert series.n_trades["R0_short"].sum() == 0
    assert np.allclose(series.ret["R0"]["c10"], series.ret["R0_long"]["c10"])
    metrics = idr._backtest_params(
        specs["c10"], dataset, run.FROZEN_PARAMS, start_index=0, end_index=len(dataset.dates)
    )
    mine = float(np.prod(1.0 + series.ret["R0"]["c10"]) - 1.0) * 100.0
    assert mine == pytest.approx(metrics.total_return_pct, abs=1e-9)
    ew = float(np.prod(1.0 + series.ret["B_ew"]["c10"]) - 1.0) * 100.0
    assert ew == pytest.approx(metrics.equal_weight_intraday_return_pct, abs=1e-9)


def test_cost_tiers_apply_per_side_cost(cache_dir: Path) -> None:
    dataset = run.build_dataset(cache_dir)
    spec = load_strategy_spec(run.SPEC_PATH)
    specs = run.tier_specs(spec)
    day = idr._day_bars(dataset, "AAPL", 12)
    gross = day.closes[-1] / day.opens[run.FROZEN_PARAMS.entry_after_bars] - 1.0
    net = idr._symbol_intraday_return(dataset, "AAPL", 12, run.FROZEN_PARAMS, specs["c10"])
    expected = (1 - 0.001) / (1 + 0.001) * (1 + gross) - 1.0
    assert net == pytest.approx(expected, rel=1e-9)


def test_unadjusted_split_is_flagged_and_rescaled(cache_dir: Path) -> None:
    dataset = run.build_dataset(cache_dir)
    assert run.overnight_gap_flags(dataset) == []
    split_date = dataset.dates[15]
    broken = {
        date: (
            bars
            if date >= split_date
            else idr._DailyBars(
                bars.timestamps, bars.opens * 10, bars.closes * 10, bars.volumes / 10
            )
        )
        for date, bars in dataset.bars["NVDA"].items()
    }
    dataset.bars["NVDA"] = broken
    flags = run.overnight_gap_flags(dataset)
    assert [f["date"] for f in flags if f["symbol"] == "NVDA"] == [split_date]
    fixed = run.apply_split_factor(broken, split_date, 10.0)
    dataset.bars["NVDA"] = fixed
    assert run.overnight_gap_flags(dataset) == []


def test_placebo_is_reproducible_and_gated(cache_dir: Path) -> None:
    dataset = run.build_dataset(cache_dir)
    spec = load_strategy_spec(run.SPEC_PATH)
    series = run.build_series(dataset, run.FROZEN_PARAMS, spec, run.tier_specs(spec))
    series.gate[:] = True  # synthetic random data rarely passes the QQQ gate
    series.gate[::2] = False
    a = run.placebo_returns(series, 20260929)
    b = run.placebo_returns(series, 20260929)
    c = run.placebo_returns(series, 20260930)
    assert np.array_equal(a["c10"], b["c10"])
    assert not np.array_equal(a["c10"], c["c10"])
    assert np.all(a["c10"][~series.gate] == 0.0)
    assert set(run.PLACEBO_SEEDS.values()) == {20260929, 20260930, 20261001}
    assert len(run.DIST_SEEDS) == 200


def test_metric_block_sharpe_matches_screen_lane_convention() -> None:
    rng = np.random.default_rng(5)
    ret = rng.normal(0.0004, 0.01, 300)
    rf = np.full(300, 0.0001)
    ex = ret - rf
    assert run.fast_sharpe(ret, rf) == pytest.approx(ex.mean() / ex.std(ddof=1) * np.sqrt(252))
