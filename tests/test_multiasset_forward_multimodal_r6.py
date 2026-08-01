from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import open_composer.research.multiasset_forward_multimodal_r6 as r6
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.multiasset_forward_multimodal_r5 import ExactSimulationResult


def test_r6_specs_satisfy_execution_contract(repo_root: Path) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in r6.SPEC_PATHS.items()
    }

    r6._validate_specs(specs)

    bad_specs = dict(specs)
    bad_spec = specs["R6D01"]
    bad_specs["R6D01"] = bad_spec.model_copy(
        update={"portfolio": bad_spec.portfolio.model_copy(update={"reserve_symbol": "QQQ"})}
    )
    with pytest.raises(ValueError, match="reserve"):
        r6._validate_specs(bad_specs)


def test_r6_pbo_identical_streams_are_half() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=80)
    stream = np.sin(np.arange(len(sessions), dtype=float) / 7.0) * 0.01 + 0.0002
    returns = pd.DataFrame(
        {candidate_id: stream for candidate_id in ("A", "B", "C", "D")},
        index=sessions,
    )

    result = r6.probability_backtest_overfitting_r6(
        returns,
        candidate_ids=["A", "B", "C", "D"],
    )

    assert result["partition_count"] == 70
    assert result["probability"] == pytest.approx(0.5)
    assert all(
        row["fractional_overfit_contribution"] == pytest.approx(0.5) for row in result["partitions"]
    )


def test_r6_pbo_is_candidate_id_and_order_invariant() -> None:
    rng = np.random.default_rng(6101)
    sessions = pd.bdate_range("2023-01-03", periods=160)
    returns = pd.DataFrame(
        {
            "A": rng.normal(0.0004, 0.010, len(sessions)),
            "B": rng.normal(0.0002, 0.009, len(sessions)),
            "C": rng.normal(0.0001, 0.011, len(sessions)),
        },
        index=sessions,
    )
    original = r6.probability_backtest_overfitting_r6(
        returns,
        candidate_ids=["A", "B", "C"],
    )
    renamed = returns.rename(columns={"A": "Z", "B": "X", "C": "Y"})
    permuted = r6.probability_backtest_overfitting_r6(
        renamed,
        candidate_ids=["Y", "Z", "X"],
    )

    assert permuted["probability"] == pytest.approx(original["probability"])
    assert [row["fractional_overfit_contribution"] for row in permuted["partitions"]] == (
        pytest.approx([row["fractional_overfit_contribution"] for row in original["partitions"]])
    )


def test_r6_dsr_uses_sharpe_influence_newey_west_variance() -> None:
    rng = np.random.default_rng(6102)
    innovations = rng.normal(0.0, 0.008, 504)
    values = np.empty_like(innovations)
    values[0] = innovations[0]
    for index in range(1, len(values)):
        values[index] = 0.35 * values[index - 1] + innovations[index] + 0.00035
    scopes = ["F1"] * 252 + ["F2"] * 252

    result = r6.deflated_sharpe_ratio_r6(
        pd.Series(values),
        trial_count=100_000,
        scope_ids=scopes,
        hac_lag=21,
    )

    centered = values - values.mean()
    sample_std = values.std(ddof=1)
    daily_sharpe = values.mean() / sample_std
    z = centered / sample_std
    influence = z - 0.5 * daily_sharpe * (z**2 - 1.0)
    influence -= influence.mean()
    expected = float(np.dot(influence, influence) / len(values))
    for lag in range(1, 22):
        products = [
            influence[index] * influence[index - lag]
            for index in range(lag, len(values))
            if scopes[index] == scopes[index - lag]
        ]
        expected += 2.0 * (1.0 - lag / 22.0) * math.fsum(products) / len(values)

    assert result["hac_long_run_variance"] == pytest.approx(max(expected, 0.0))
    assert result["promotion_probability"] == min(
        result["iid_probability"], result["hac_probability"]
    )
    assert 0.0 <= result["promotion_probability"] <= 1.0


def test_r6_raw_open_notional_reconciles_and_is_bound() -> None:
    session = pd.Timestamp("2026-07-30")
    event = {
        "session": session.date().isoformat(),
        "pretrade_equity": 1.0,
        "posttrade_equity_ratio": 0.999,
        "pretrade_asset_weights": {"AAA": 0.0, "BBB": 0.0},
        "target_asset_weights": {"AAA": 0.6, "BBB": 0.4},
        "full_L1_executed_notional_fraction": 0.999,
    }
    simulation = ExactSimulationResult(
        daily=pd.DataFrame(),
        events=[event],
        metrics={},
    )
    raw_opens = pd.DataFrame({"AAA": [25.0], "BBB": [80.0]}, index=[session])

    r6._bind_raw_execution_marks(simulation, raw_opens)

    assert event["execution_price_adjustment"] == "raw"
    assert event["raw_share_notional_fraction"] == pytest.approx(0.999)
    assert len(event["raw_execution_rows_sha256"]) == 64

    bad_event = {**event, "full_L1_executed_notional_fraction": 0.8}
    bad_simulation = ExactSimulationResult(pd.DataFrame(), [bad_event], {})
    with pytest.raises(ValueError, match="raw-open share notional"):
        r6._bind_raw_execution_marks(bad_simulation, raw_opens)


def _calibration_frame() -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for probability, positive_count in ((0.2, 5), (0.4, 10), (0.6, 15), (0.8, 20)):
        for index in range(25):
            rows.append(
                {
                    "label": float(index < positive_count),
                    "probability": probability,
                    "training_base_probability": 0.5,
                }
            )
    return pd.DataFrame(rows)


def test_r6_m02_calibration_fold_gates() -> None:
    folds = [{"fold_id": f"F{index}"} for index in range(1, 5)]
    contract = {
        "probability_clip": 0.000001,
        "expected_observation_count_by_fold": {f"F{index}": 100 for index in range(1, 5)},
        "minimum_class_count_per_fold": 20,
        "brier_skill_vs_fold_train_base_rate_min_exclusive": 0.0,
        "calibration_slope_min": 0.7,
        "calibration_slope_max": 1.3,
        "joint_brier_and_slope_passing_folds_min": 3,
    }
    frames = {str(fold["fold_id"]): _calibration_frame() for fold in folds}

    result = r6._calibration_payload(frames, folds, contract)

    assert result["all_observation_counts_match"] is True
    assert result["joint_brier_and_slope_passing_fold_count"] == 4
    assert all(row["pass"] for row in result["folds"].values())


def test_r6_llm_bootstrap_wrapper_maps_only_contract_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_bootstrap(
        daily_rows: list[dict[str, object]],
        event_rows: list[dict[str, object]],
        *,
        contract: dict[str, object],
    ) -> dict[str, object]:
        captured["daily_rows"] = daily_rows
        captured["event_rows"] = event_rows
        captured["contract"] = contract
        return {
            "candidate_id": "R5C01",
            "comparator_ids": ["R5M01", "R5P01"],
            "pass": True,
        }

    monkeypatch.setattr(r6, "paired_transfer_sharpe_bootstrap", fake_bootstrap)
    contract = r6._remap_ids(
        r6._expected_llm_contribution_bootstrap_contract(),
        {
            "R5C01": "R6C01",
            "R5M01": "R6M01",
            "R5P01": "R6P01",
        },
    )
    daily_rows = [
        {"candidate_id": candidate_id, "value": index}
        for index, candidate_id in enumerate(("R6C01", "R6M01", "R6P01", "R6D01"))
    ]

    result = r6._llm_bootstrap_r6(daily_rows, [], contract)

    assert [row["candidate_id"] for row in captured["daily_rows"]] == [
        "R5C01",
        "R5M01",
        "R5P01",
    ]
    assert captured["contract"] == r6._expected_llm_contribution_bootstrap_contract()
    assert result["candidate_id"] == "R6C01"
    assert result["comparator_ids"] == ["R6M01", "R6P01"]
    assert result["config"] == contract


def test_r6_publication_receipt_binds_final_paths(tmp_path: Path) -> None:
    staging = tmp_path / "reports/evaluation-run.staging-1"
    destination = tmp_path / "reports/evaluation-run"
    staging.mkdir(parents=True)
    artifact = staging / "evaluation-report.json"
    artifact.write_bytes(b"{}\n")

    binding = r6._publication_binding(
        artifact,
        root=tmp_path,
        staging_dir=staging,
        destination_dir=destination,
    )

    assert binding == {
        "path": "reports/evaluation-run/evaluation-report.json",
        "sha256": hashlib.sha256(b"{}\n").hexdigest(),
        "size_bytes": 3,
    }
