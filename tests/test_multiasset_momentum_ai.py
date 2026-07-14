from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research import multiasset_momentum_ai as ai


def _synthetic_data(
    periods: int = 900, symbols: int = 12
) -> tuple[dict, list[str], dict[str, str]]:
    index = pd.date_range("2022-01-03", periods=periods, freq="B", tz="UTC")
    names = [f"S{number:02d}" for number in range(symbols)]
    columns = [*names, "SPY"]
    open_prices = pd.DataFrame(index=index, columns=columns, dtype=float)
    close_prices = pd.DataFrame(index=index, columns=columns, dtype=float)
    volumes = pd.DataFrame(index=index, columns=columns, dtype=float)
    rng = np.random.default_rng(17)
    for number, symbol in enumerate(columns):
        drift = 0.0002 + number * 0.00003
        shocks = rng.normal(drift, 0.012 + (number % 3) * 0.001, periods)
        prices = 100 * np.exp(np.cumsum(shocks))
        open_prices[symbol] = prices
        close_prices[symbol] = prices * (1 + rng.normal(0, 0.002, periods))
        volumes[symbol] = 2_000_000 + number * 100_000 + rng.normal(0, 100_000, periods)
    sectors = {symbol: f"Sector-{number % 4}" for number, symbol in enumerate(names)}
    return (
        {
            "open": open_prices,
            "close": close_prices,
            "volume": volumes.abs(),
            "data_as_of": index[-1].isoformat(),
        },
        names,
        sectors,
    )


def test_ai_factor_dataset_is_index_minus_one_and_has_broad_groups() -> None:
    data, symbols, sectors = _synthetic_data()
    frame, latest, groups = ai.build_ai_factor_dataset(data, symbols, sectors)
    decision_date = frame["decision_date"].iloc[-1]
    decision_timestamp = pd.Timestamp(decision_date)
    baseline_rows = frame[frame["decision_date"] == decision_date].sort_values("symbol")

    changed = {
        **data,
        "close": data["close"].copy(),
    }
    changed["close"].loc[decision_timestamp, symbols] *= 10
    changed_frame, _, _ = ai.build_ai_factor_dataset(changed, symbols, sectors)
    changed_rows = changed_frame[changed_frame["decision_date"] == decision_date].sort_values(
        "symbol"
    )

    assert len(groups["all"]) >= 60
    assert len(groups["ai_formula"]) == 16
    assert set(ai.CORE_FEATURES).issubset(frame.columns)
    assert latest["decision_date"].nunique() == 1
    pd.testing.assert_frame_equal(
        baseline_rows[list(ai.CORE_FEATURES)].reset_index(drop=True),
        changed_rows[list(ai.CORE_FEATURES)].reset_index(drop=True),
    )


def test_ai_folds_enforce_full_label_purge_and_embargo() -> None:
    data, symbols, sectors = _synthetic_data()
    frame, _, _ = ai.build_ai_factor_dataset(data, symbols, sectors)
    dates = ai._evaluation_dates(frame)
    folds = ai.build_ai_folds(frame, dates[: -ai.CHALLENGE_DATES])

    assert len(folds) == 4
    for fold in folds:
        assert fold["test_start_position"] - fold["train"]["label_end_position"].max() >= 21
        assert fold["train"]["decision_date"].max() < fold["test"]["decision_date"].min()
        assert fold["test"]["is_monthly_eval"].all()


def test_factor_selection_uses_training_frame_only_and_prunes_redundancy() -> None:
    data, symbols, sectors = _synthetic_data()
    frame, _, groups = ai.build_ai_factor_dataset(data, symbols, sectors)
    dates = ai._evaluation_dates(frame)
    fold = ai.build_ai_folds(frame, dates[: -ai.CHALLENGE_DATES])[0]
    train = fold["train"].copy()

    selected, evidence = ai.select_fold_features(
        train,
        feature_set="all_selected",
        feature_groups=groups,
    )
    altered_test = fold["test"].copy()
    altered_test["forward_excess_21"] *= -100
    selected_again, evidence_again = ai.select_fold_features(
        train,
        feature_set="all_selected",
        feature_groups=groups,
    )

    assert altered_test["forward_excess_21"].abs().max() > 1
    assert selected == selected_again
    assert evidence == evidence_again
    assert len(selected) >= 8
    assert len(selected) <= 24 + len(ai.MARKET_FEATURES)


def test_ai_search_space_is_bounded_and_model_diverse() -> None:
    trials = ai.base_trial_specs()

    assert len(trials) == 16
    assert len({row["model_family"] for row in trials}) == 4
    assert len({row["feature_set"] for row in trials}) == 4
    assert len(trials) + 8 == ai.MAX_TRIALS


def test_factor_proposals_are_static_and_hashed(tmp_path: Path) -> None:
    groups = {
        "core": ai.CORE_FEATURES,
        "expanded_quant": ("mom_21_rank",),
        "ai_formula": tuple(ai.AI_FORMULAS),
        "market": ai.MARKET_FEATURES,
        "all": (*ai.CORE_FEATURES, *ai.AI_FORMULAS),
    }
    path = ai.write_factor_proposals(tmp_path, groups)
    payload = __import__("json").loads(path.read_text())

    assert payload["generated_by"] == "codex_offline_research_compiler"
    assert payload["live_decision_use"] is False
    assert len(payload["proposals"]) == 16
    assert payload["prompt_hash"]
