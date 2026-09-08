"""Tests for open_composer.research.kernel.b3_grid_strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.b3_grid_strategy import (
    DEFAULT_GRID,
    GridCell,
    GridSelectedLightGBMStrategy,
)


def _synthetic_two_year_frame(
    n_symbols: int = 40, n_dates_per_year: int = 60, seed: int = 11
) -> pd.DataFrame:
    """2020 (train-only) + 2021 (the validation year, since it's the max
    calendar year present -- see GridSelectedLightGBMStrategy.fit). Enough
    rows per date (>=5, _rank_ic_by_date's floor) and enough total rows
    (n_symbols * n_dates_per_year * 2 years = 4800 by default, comfortably
    over FIXED_HYPERPARAMETERS' min_child_samples=200) that a real LightGBM
    fit can do more than underfit to a single constant leaf.

    ``label_rank_5`` is a monotonic (rank) transform of ``signal`` plus a
    little noise -- learnable. ``label_rank_10`` is independent random
    noise -- not learnable from ``signal``. A grid that correctly picks by
    validation rank IC should always prefer whichever cell's label_column is
    ``label_rank_5``.
    """
    rng = np.random.default_rng(seed)
    dates_2020 = pd.bdate_range("2020-01-02", periods=n_dates_per_year)
    dates_2021 = pd.bdate_range("2021-01-04", periods=n_dates_per_year)
    symbols = [f"S{i:03d}" for i in range(n_symbols)]

    rows = []
    for date in list(dates_2020) + list(dates_2021):
        signal = rng.normal(size=n_symbols)
        label_rank_5 = (
            pd.Series(signal + 0.05 * rng.normal(size=n_symbols)).rank(pct=True).to_numpy()
        )
        label_rank_10 = rng.uniform(0, 1, size=n_symbols)  # independent noise
        for i, symbol in enumerate(symbols):
            rows.append(
                {
                    "trade_date": date,
                    "symbol": symbol,
                    "signal": signal[i],
                    "label_rank_5": label_rank_5[i],
                    "label_rank_10": label_rank_10[i],
                }
            )
    return pd.DataFrame(rows)


def _two_cell_grid() -> tuple[GridCell, GridCell]:
    learnable = GridCell(label_horizon_days=5, max_depth=3)
    noise = GridCell(label_horizon_days=10, max_depth=3)
    return learnable, noise


def test_selects_the_cell_with_the_highest_validation_rank_ic() -> None:
    learnable, noise = _two_cell_grid()
    frame = _synthetic_two_year_frame()
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=[learnable, noise])
    strategy.fit(frame)
    assert strategy.selected_cell == learnable
    assert (
        strategy.validation_ic_by_cell[learnable.config_id]
        > strategy.validation_ic_by_cell[noise.config_id]
    )
    # A real, recoverable signal should clear a modest bar, not just "beat
    # noise by an arbitrarily tiny margin".
    assert strategy.validation_ic_by_cell[learnable.config_id] > 0.2


def test_validation_year_is_the_last_calendar_year_in_the_training_window() -> None:
    learnable, noise = _two_cell_grid()
    frame = _synthetic_two_year_frame()
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=[learnable, noise])
    strategy.fit(frame)
    assert strategy.validation_year == 2021


def test_validation_ic_by_cell_has_one_entry_per_grid_cell() -> None:
    frame = _synthetic_two_year_frame()
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=DEFAULT_GRID)
    # DEFAULT_GRID's cells reference label_rank_5/10/21 -- only 5 and 10
    # exist in this fixture, so give the third horizon a column too (all
    # noise, same as label_rank_10) purely so every cell has *something* to
    # fit against; the point of this test is cardinality, not which wins.
    frame["label_rank_21"] = frame["label_rank_10"]
    strategy.fit(frame)
    assert set(strategy.validation_ic_by_cell) == {cell.config_id for cell in DEFAULT_GRID}


def test_score_before_fit_raises() -> None:
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=list(_two_cell_grid()))
    with pytest.raises(RuntimeError, match="before fit"):
        strategy.score(_synthetic_two_year_frame(n_dates_per_year=1))


def test_top_feature_importances_before_fit_raises() -> None:
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=list(_two_cell_grid()))
    with pytest.raises(RuntimeError, match="before fit"):
        strategy.top_feature_importances()


def test_score_delegates_to_the_selected_winner() -> None:
    learnable, noise = _two_cell_grid()
    frame = _synthetic_two_year_frame()
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=[learnable, noise])
    strategy.fit(frame)
    asof_frame = frame.loc[frame["trade_date"] == frame["trade_date"].max()]
    scores = strategy.score(asof_frame)
    assert list(scores.index) == list(asof_frame["symbol"])
    assert scores.notna().all()


def test_top_feature_importances_delegates_to_the_selected_winner() -> None:
    learnable, noise = _two_cell_grid()
    frame = _synthetic_two_year_frame()
    frame["extra_noise_feature"] = np.random.default_rng(3).normal(size=len(frame))
    strategy = GridSelectedLightGBMStrategy(
        ["signal", "extra_noise_feature"], grid=[learnable, noise]
    )
    strategy.fit(frame)
    importances = strategy.top_feature_importances(n=1)
    assert list(importances.index) == ["signal"]


def test_no_usable_grid_cell_raises_value_error() -> None:
    # Training-year (2020) labels stay real so model.fit() itself succeeds
    # on non-empty fit_rows; only the *validation* year's (2021) labels are
    # wiped out, so every cell's eval_rows.dropna(...) is empty and every
    # cell's mean_ic is nan -- that must raise, not silently pick an
    # arbitrary "best" cell (nan-safety: `mean_ic == mean_ic` guards this in
    # the source, this test pins the failure mode it guards against).
    frame = _synthetic_two_year_frame(n_dates_per_year=5)
    is_validation_year = frame["trade_date"].dt.year == 2021
    frame.loc[is_validation_year, "label_rank_5"] = np.nan
    frame.loc[is_validation_year, "label_rank_10"] = np.nan
    strategy = GridSelectedLightGBMStrategy(["signal"], grid=list(_two_cell_grid()))
    with pytest.raises(ValueError, match="no grid cell produced a usable validation rank IC"):
        strategy.fit(frame)
