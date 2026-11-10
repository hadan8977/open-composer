from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.p1s1_build import (
    build_test_blocks,
    composition_identity_error,
    daily_returns,
    load_store,
    monthly_universes,
    project_residuals,
)


def _store(tmp_path: Path):
    dates = pd.bdate_range("2020-01-01", periods=270)
    symbols = ["A", "B", "C"]
    close = np.ones((len(dates), 3), dtype="float64")
    close[:, 0] = np.arange(1, len(dates) + 1)
    close[:, 1] = np.arange(2, len(dates) + 2)
    close[:, 2] = np.arange(3, len(dates) + 3)
    meta = {"dates": [str(x.date()) for x in dates], "symbols": symbols, "shape": [len(dates), 3]}
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    adv_rank = np.ones_like(close)
    adv_rank[:, 2] = 3
    for name, values in {
        "close": close,
        "adv_rank": adv_rank,
        "is_tradeable": np.ones_like(close),
        "short_elig": np.ones_like(close),
    }.items():
        np.save(tmp_path / f"{name}.npy", values)
    return load_store(tmp_path)


def test_monthly_universe_uses_previous_month_end(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rows, trade, residual = monthly_universes(store, trade_rank=2, residual_rank=3, lookback=2)
    assert rows
    first = pd.Timestamp(rows[0]["effective_date"])
    assert first.month == 2
    assert not trade[store.dates.get_loc(first) - 1].any()
    assert trade[store.dates.get_loc(first)].sum() == 2
    assert residual[store.dates.get_loc(first)].sum() == 3


def test_blocks_keep_embargo_and_fixed_size() -> None:
    dates = pd.bdate_range("2020-01-01", periods=260)
    blocks = build_test_blocks(dates, first_test="2020-02-13", block_size=125, embargo=2)
    assert blocks[0]["start"] == "2020-02-13"
    assert blocks[0]["train_end_index_exclusive"] == blocks[0]["start_index"] - 2
    assert blocks[0]["sessions"] == 125


def test_residual_projection_and_composition_identity() -> None:
    returns = daily_returns(np.array([[10.0, 20.0], [11.0, 18.0]]))[-1]
    beta = np.array([[0.2], [-0.4]])
    weights = np.array([[0.5, -0.25]])
    residuals = project_residuals(returns, beta, weights)
    assert composition_identity_error(returns, residuals, beta, weights) < 1e-12
