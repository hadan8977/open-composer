from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from open_composer.research.multiasset_momentum_multimodal import (
    DAY_NIGHT_FEATURES,
    day_night_feature_frames,
    multimodal_trial_specs,
)


def test_multimodal_trial_registry_is_exactly_preregistered_24() -> None:
    rows = multimodal_trial_specs()
    counts = Counter(str(row["path"]) for row in rows)

    assert len(rows) == 24
    assert len({row["trial_id"] for row in rows}) == 24
    assert counts == {
        "champion_and_text_ablations": 6,
        "catalyst_and_risk_roles": 6,
        "regime_and_disagreement_meta": 6,
        "cost_aware_shrinkage": 6,
    }
    assert sum(row["dependency"] == "historical_text" for row in rows) == 10


def test_day_night_features_use_previous_session_only() -> None:
    index = pd.date_range("2026-01-01", periods=100, freq="B", tz="UTC")
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    rng = np.random.default_rng(17)
    overnight = rng.normal(0.0003, 0.01, size=(100, len(symbols)))
    intraday = rng.normal(0.0005, 0.012, size=(100, len(symbols)))
    open_prices = pd.DataFrame(
        100 * np.cumprod(1 + overnight, axis=0), index=index, columns=symbols
    )
    close = open_prices * pd.DataFrame(1 + intraday, index=index, columns=symbols)
    data = {"open": open_prices.copy(), "close": close.copy()}
    changed = {"open": open_prices.copy(), "close": close.copy()}
    changed["open"].iloc[80, 0] *= 0.5
    changed["close"].iloc[80, 0] *= 1.5

    original = day_night_feature_frames(data, symbols)
    perturbed = day_night_feature_frames(changed, symbols)

    assert tuple(original) == DAY_NIGHT_FEATURES
    for name in DAY_NIGHT_FEATURES:
        assert original[name].loc[index[80]].equals(perturbed[name].loc[index[80]])
    assert any(
        not original[name].loc[index[81]].equals(perturbed[name].loc[index[81]])
        for name in DAY_NIGHT_FEATURES
    )


def test_trial_roles_include_missing_and_stale_text_placebos() -> None:
    ids = {str(row["trial_id"]): row for row in multimodal_trial_specs()}

    assert ids["text_only"]["dependency"] == "historical_text"
    assert ids["quant_plus_text"]["dependency"] == "historical_text"
    assert ids["shuffled_text_placebo"]["dependency"] == "historical_text"
    assert ids["stale_text_placebo"]["dependency"] == "historical_text"
    assert "agreement_overlap3" in ids
    assert "shrink_075_cost20" in ids
