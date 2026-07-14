from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.research import multiasset_momentum_ml as ml


def _panel() -> tuple[dict, list[str], dict[str, str]]:
    rng = np.random.default_rng(77)
    index = pd.date_range("2021-01-01", periods=1000, freq="B", tz="UTC")
    stocks = [f"S{number}" for number in range(20)]
    symbols = [*stocks, "SPY"]
    open_prices = pd.DataFrame(index=index)
    close_prices = pd.DataFrame(index=index)
    volumes = pd.DataFrame(index=index)
    market = rng.normal(0.0004, 0.01, len(index))
    for number, symbol in enumerate(symbols):
        innovations = market + rng.normal(0.0001 * (number % 5), 0.012, len(index))
        prices = 100 * np.exp(np.cumsum(innovations))
        open_prices[symbol] = prices
        close_prices[symbol] = prices * (1 + rng.normal(0, 0.001, len(index)))
        volumes[symbol] = 2_000_000 + rng.integers(0, 500_000, len(index))
    sectors = {symbol: f"Sector {number % 5}" for number, symbol in enumerate(stocks)}
    return (
        {
            "open": open_prices,
            "close": close_prices,
            "volume": volumes,
            "data_as_of": index[-1].isoformat(),
        },
        stocks,
        sectors,
    )


def test_ml_search_space_is_bounded_and_role_diverse() -> None:
    ranking = ml._ranking_trial_specs()
    risk = ml._risk_trial_specs()

    assert len(ranking) == 8
    assert len(risk) == 4
    assert {row["model_family"] for row in ranking} == {
        "elastic_net",
        "lightgbm",
        "extra_trees",
        "hist_gradient",
    }
    assert {row["model_family"] for row in risk} == {"logistic", "lightgbm_classifier"}


def test_panel_features_are_index_minus_one_and_exclude_symbol_identity() -> None:
    data, stocks, sectors = _panel()
    dataset, latest = ml._build_panel_dataset(data, stocks, sectors)
    target_date = pd.Timestamp(dataset["decision_date"].iloc[0])
    original = dataset[dataset["decision_date"] == target_date.isoformat()].copy()

    changed = {
        key: value.copy() if isinstance(value, pd.DataFrame) else value
        for key, value in data.items()
    }
    changed["close"].loc[target_date, stocks] *= 10
    changed_dataset, _ = ml._build_panel_dataset(changed, stocks, sectors)
    changed_rows = changed_dataset[
        changed_dataset["decision_date"] == target_date.isoformat()
    ].copy()

    pd.testing.assert_frame_equal(
        original.sort_values("symbol")[list(ml.FEATURES)].reset_index(drop=True),
        changed_rows.sort_values("symbol")[list(ml.FEATURES)].reset_index(drop=True),
    )
    assert "symbol" not in ml.FEATURES
    assert len(latest) >= 10


def test_development_folds_enforce_horizon_purge_and_embargo() -> None:
    data, stocks, sectors = _panel()
    dataset, _ = ml._build_panel_dataset(data, stocks, sectors)
    dates = sorted(pd.to_datetime(dataset["decision_date"], utc=True).unique())
    folds = ml._build_folds(dataset, dates[: -ml.LOCKBOX_DECISION_DATES])

    assert len(folds) == 4
    for fold in folds:
        assert (
            fold["train"]["label_end_position"].max()
            <= fold["test"]["decision_position"].min() - ml.EMBARGO_BARS
        )
        assert set(fold["train"]["decision_date"]).isdisjoint(fold["test"]["decision_date"])


def test_elastic_ranking_trial_returns_stitched_oos_predictions() -> None:
    data, stocks, sectors = _panel()
    dataset, _ = ml._build_panel_dataset(data, stocks, sectors)
    dates = sorted(pd.to_datetime(dataset["decision_date"], utc=True).unique())
    folds = ml._build_folds(dataset, dates[: -ml.LOCKBOX_DECISION_DATES])

    row, predictions = ml._run_ranking_trial(
        ml._ranking_trial_specs()[0], dataset, folds, cost_bps=10.0
    )

    assert row["status"] == "validation_complete"
    assert len(row["folds"]) == 4
    assert 0 <= row["fold_wins"] <= 4
    assert predictions["prediction"].notna().all()
    assert predictions["decision_date"].nunique() >= 8
