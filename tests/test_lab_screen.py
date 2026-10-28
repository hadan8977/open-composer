from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.lab.adapters import screen_engine, screen_modules

ROOT = Path(__file__).resolve().parents[1]


def test_screen_adapter_preserves_frozen_source_costs_windows_and_returns():
    _, lane = screen_modules(ROOT)
    index = pd.bdate_range("2015-01-02", "2026-09-17")
    position = np.arange(len(index))
    symbols = sorted(set(lane.salvage.symbols()) | {lane.CASH, lane.RF, "AAA"})
    close = pd.DataFrame(
        {
            symbol: 100
            * np.exp(
                position * (0.0001 + j * 0.00001) + np.sin(position * (0.07 + j * 0.005)) * 0.04
            )
            for j, symbol in enumerate(symbols)
        },
        index=index,
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    leg_open, leg_close = lane.salvage.legs(close, open_)
    candidate = lane.ScreenCandidate(
        id="fixture_screen",
        name="Synthetic screen adapter",
        source_card="fixture",
        universe=("AAA",),
        freq="D",
        weights_fn=lambda frame, date: {"AAA": 0.5},
    )
    rf = close[lane.RF].pct_change(fill_method=None).fillna(0.0)
    panel = {
        "close": close,
        "leg_open": leg_open,
        "leg_close": leg_close,
        "rf": rf,
        "shy_ret": close[lane.CASH].pct_change(fill_method=None).fillna(0),
        "s3_ret10": close[lane.CASH].pct_change(fill_method=None).fillna(0),
    }
    native = lane.evaluate_candidate(candidate, **panel, n_trials=9)
    adapted = screen_engine(ROOT, candidate, panel=panel, n_trials=9, initial_equity_usd=10_000)
    offset = native["judged"]["anchor"]["offset"]
    start = native["per_window"]["anchor"]["actual_start"]
    expected = native["_returns_net10_by_offset"][offset].loc[start : lane.WINDOWS["anchor"][1]]
    pd.testing.assert_series_equal(adapted.net_returns, expected)
    assert adapted.end_equity_usd == pytest.approx(10_000 * (1 + expected).prod())
    assert adapted.native["dsr_anchor"] == native["dsr_anchor"]
    assert adapted.metadata["windows"] == lane.WINDOWS
    assert adapted.metadata["contaminated_windows"] == ["holdout"]
    assert adapted.metadata["cost_bps_primary"] == 10
    assert adapted.metadata["cost_bps_stress"] == 20
