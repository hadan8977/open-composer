from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.research.dynamic_theme_stock_r9_evaluation import (
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
    development_folds,
)


def test_r9_development_folds_preserve_train_purge_and_four_test_windows() -> None:
    sessions = pd.bdate_range("2022-11-01", periods=620)

    folds = development_folds(sessions)

    assert len(folds) == 4
    assert all(row["purge_sessions"] == 10 for row in folds)
    assert all(row["embargo_sessions"] == 10 for row in folds)
    assert all(row["test_interval_count"] >= 63 for row in folds)
    assert folds[0]["train_start"] == sessions[0].date().isoformat()
    assert folds[-1]["test_end"] == sessions[-1].date().isoformat()


def test_r9_dsr_uses_frozen_cumulative_trial_count() -> None:
    rng = np.random.default_rng(9009)
    returns = pd.Series(rng.normal(0.001, 0.01, 500))

    result = deflated_sharpe_probability(returns, 8022)

    assert result["trial_count"] == 8022
    assert result["session_count"] == 500
    assert 0.0 <= result["probability"] <= 1.0


def test_r9_stage_d_pbo_uses_all_70_directional_partitions() -> None:
    sessions = pd.bdate_range("2023-01-03", periods=400)
    x = np.linspace(-0.01, 0.012, len(sessions))
    returns = {
        "R9D01": pd.Series(x, index=sessions),
        "R9D02": pd.Series(x[::-1] + 0.0001, index=sessions),
    }

    result = cscv_probability_backtest_overfitting(returns, block_count=8)

    assert result["partition_count"] == 70
    assert result["candidate_ids"] == ["R9D01", "R9D02"]
    assert result["status"] == "provisional_until_R9M01_R9M02_are_frozen"
    assert 0.0 <= result["probability"] <= 1.0
