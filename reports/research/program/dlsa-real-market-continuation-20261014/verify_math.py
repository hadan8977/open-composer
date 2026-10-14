"""Meaningful algebra/input verification. No torch, model fit or strategy backtest."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from method_math import fractional_account, path_windows, pca_projection, project

OUT = Path(__file__).resolve().parent


def main():
    rng = np.random.default_rng(441)
    history = rng.normal(0, 0.01, (252, 12))
    p = pca_projection(history)
    b = rng.normal(size=(7, 12))
    r = rng.normal(0, 0.01, (7, 12))
    matrices = np.repeat(p[None, :, :], 7, axis=0)
    q = project(b, matrices)
    norm = np.abs(np.einsum("bi,bij->bj", b, matrices)).sum(axis=1)
    mapped_identity = np.sum(b * np.einsum("bij,bj->bi", matrices, r), axis=1) / norm
    assert np.max(np.abs(mapped_identity - np.sum(q * r, axis=1))) < 1e-12
    assert q.shape == (7, 12)
    assert np.max(np.abs(np.abs(q).sum(axis=1) - 1)) < 1e-12
    x = rng.normal(size=(75, 12))
    before = path_windows(x, [35, 40])
    x[40:] += 100
    assert np.array_equal(before, path_windows(x, [35, 40]))
    values = fractional_account(np.array([[1.0], [0.0]]), np.zeros((2, 1)), 0.01, 0)
    assert abs(values[0]["nav_after"] - 1 / 1.01) < 1e-12
    assert abs(values[1]["nav_after"] - 0.99 / 1.01) < 1e-12
    # Drifted weights, not yesterday's target weights, determine later turnover.
    q = np.array([[0.5, 0.5], [0.5, 0.5]])
    values = fractional_account(q, np.array([[0.1, 0], [0, 0]]), 0, 0)
    assert abs(values[1]["turnover_per_pretrade_nav"] - 1 / 21) < 1e-12
    try:
        fractional_account(np.array([[1.0]]), np.array([[np.nan]]), 0, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown held return incorrectly became a free mark")
    zero = fractional_account(np.array([[0.0]]), np.array([[np.nan]]), 0, 0)
    assert zero[0]["net_return"] == 0
    raw = json.loads((OUT / "inputs/actual-connected-raw-sample.json").read_text())
    rows = raw["daily_return_rows"]
    finite = [x for x in rows if x["r_t"] is not None]
    for row in finite:
        before = float(row["previous_bar"]["raw"]["c"])
        after = float(row["current_bar"]["raw"]["c"])
        ratio = row["split_ratio_new_per_previous_share"]
        cash = row["economic_distribution_per_previous_share"]
        assert abs((ratio * after + cash) / before - 1 - row["r_t"]) < 1e-12
    feature_count = sum(x["Ret_D1"] is not None for x in raw["price3_feature_rows"])
    eligible_count = sum(
        x["source_component_usable_conditionally"] for x in raw["price3_feature_rows"]
    )
    assert len(rows) == 82 and len(finite) == 74 and feature_count == 66 and eligible_count == 65
    atvi = next(
        x
        for x in raw["unit_terminal_and_action_entitlements"]
        if x["claim_id"] == "ATVI_CASH_CONVERSION"
    )
    assert atvi["cash_per_eligible_share"] == 95 and atvi["actually_spendable_at"] is None
    bars = pd.read_parquet(OUT / "inputs/selected-bars.parquet")
    assert set(bars.symbol) == set(
        json.loads((OUT / "input-contract.json").read_text())["cohort"]["symbols"]
    )
    assert "PBCT" in set(bars.symbol) and not bars[bars.symbol == "PBCT"].empty
    report = {
        "status": "pass",
        "tests": [
            "asset/residual algebra and batched axis parity",
            "L1 asset normalization",
            "future-change invariance of causal path",
            "initial + exit costs charged",
            "drifted actual turnover",
            "unknown held return blocks, zero exposure stays zero",
            "74 actual raw-action return rows recomputed",
            "66 numerical/65 usable price3",
            "95 ATVI cash right retained, settlement unknown",
            "former member PBCT retained",
        ],
        "market_requests": 0,
        "model_fits": 0,
        "optimizer_updates": 0,
        "strategy_backtests": 0,
        "economic_input_acceptance": False,
    }
    (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
