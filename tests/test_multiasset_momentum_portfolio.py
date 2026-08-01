from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research import multiasset_momentum_portfolio as portfolio


class _FixedPredictionModel:
    def __init__(self, predictions: list[float]) -> None:
        self.predictions = np.asarray(predictions, dtype=float)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.predictions[: len(frame)]


def _manifest() -> dict[str, object]:
    selected = [
        {"symbol": "AAA", "sector": "Technology"},
        {"symbol": "BBB", "sector": "Financials"},
        {"symbol": "CCC", "sector": "Industrials"},
        {"symbol": "DDD", "sector": "Health Care"},
        {"symbol": "EEE", "sector": "Consumer"},
    ]
    return {"selected_symbols": [row["symbol"] for row in selected], "selected": selected}


def _evaluation() -> dict[str, object]:
    return {
        "selections": [
            {
                "path": "P1_etf_absolute_relative",
                "trial_id": "p1_lb252_reb5_gate0",
                "params": {"lookback": 252, "rebalance_days": 5, "absolute_gate": False},
            },
            {
                "path": "P3_stock_cross_sectional",
                "trial_id": "p3_12_1_vol0_top5",
                "params": {
                    "score": "12_1",
                    "volatility_adjusted": False,
                    "top_n": 5,
                    "rebalance_days": 21,
                },
            },
            {
                "path": "P5_stock_residual_sector_relative",
                "trial_id": "p5_sector_relative_126_top10_cap2",
                "params": {
                    "score": "sector_relative_126",
                    "top_n": 10,
                    "sector_cap": 2,
                    "rebalance_days": 21,
                },
            },
            {
                "path": "P4_stock_trend_quality",
                "trial_id": "p4_high_52w_plus_6m_dvol0_top10",
                "params": {
                    "score": "high_52w_plus_6m",
                    "downside_vol_penalty": False,
                    "top_n": 10,
                    "rebalance_days": 21,
                },
            },
        ]
    }


def _ml_report() -> dict[str, object]:
    return {
        "selection": {"lockbox_pass_trials": []},
        "frozen_models": [
            {
                "trial_id": "rank_lgbm_l15",
                "model_family": "lightgbm",
                "model_path": "models/rank_lgbm_l15.joblib",
                "status": "lockbox_failed_diagnostic_shadow",
            },
            {
                "trial_id": "rank_hist_leaf15",
                "model_family": "hist_gradient_boosting",
                "model_path": "models/rank_hist_leaf15.joblib",
                "status": "lockbox_failed_diagnostic_shadow",
            },
        ],
    }


def test_portfolio_materializes_six_observation_only_sleeves(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = tmp_path / portfolio.SOURCE_ITER / "universe-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    (manifest_path.parent / "evaluation-report.json").write_text(
        json.dumps(_evaluation()), encoding="utf-8"
    )
    ml_path = tmp_path / portfolio.ML_ITER / "model-comparison.json"
    ml_path.parent.mkdir(parents=True)
    ml_path.write_text(json.dumps(_ml_report()), encoding="utf-8")
    dates = pd.date_range("2025-01-01", periods=3, freq="B", tz="UTC")
    data = {
        "close": pd.DataFrame(index=dates),
        "data_as_of": dates[-1].isoformat(),
    }
    monkeypatch.setattr(portfolio, "_load_panels", lambda *_args, **_kwargs: data)
    monkeypatch.setattr(
        portfolio,
        "_build_panel_dataset",
        lambda *_args, **_kwargs: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        portfolio,
        "_deterministic_latest_weights",
        lambda *_args, **_kwargs: ({"AAA": 1.0}, "2026-07-13", "2026-07-14"),
    )
    monkeypatch.setattr(
        portfolio,
        "_ml_latest_weights",
        lambda *_args, **_kwargs: ({"BBB": 1.0}, "2026-07-13", "2026-07-14"),
    )

    def fake_artifacts(root, _spec_path, spec, *_args, **_kwargs):
        execution = root / "reports" / "execution"
        execution.mkdir(parents=True, exist_ok=True)
        target = execution / f"{spec.name}-target-weights.json"
        observation = execution / f"{spec.name}-execution-observation.json"
        target.write_text("{}", encoding="utf-8")
        observation.write_text("{}", encoding="utf-8")
        return {
            "router_target_weights": target,
            "router_execution_observation": observation,
        }

    monkeypatch.setattr(portfolio, "_write_execution_artifacts", fake_artifacts)

    payload = portfolio.write_multiasset_momentum_portfolio(tmp_path)

    assert [row["sleeve_id"] for row in payload["sleeves"]] == [
        "D1",
        "D2",
        "D3",
        "D4",
        "M1",
        "M2",
    ]
    assert payload["simulation"]["broker_writes"] is False
    assert payload["paper_ready_pass"] is False
    assert all(row["broker_writes"] is False for row in payload["sleeves"])
    assert {row["status"] for row in payload["sleeves"] if row["sleeve_id"].startswith("M")} == {
        "lockbox_failed_diagnostic_shadow"
    }
    for row in payload["sleeves"]:
        spec = load_strategy_spec(tmp_path / row["spec_path"])
        assert spec.lifecycle == "draft"
        assert spec.execution.mode == "manual_signal"
        assert spec.execution.broker == "none"
        assert spec.portfolio.mode == "cross_sectional_momentum"


def test_execution_artifacts_never_require_orders(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    definition = {
        "sleeve_id": "D2",
        "strategy_name": "us_multiasset_test_d2",
        "kind": "deterministic",
        "status": "primary_deterministic_exploratory_history",
        "trial_id": "p3_12_1_vol0_top5",
        "route_label": "multiasset:deterministic:p3_12_1_vol0_top5",
        "params": {"top_n": 5},
    }
    ml_report = {"selection": {"lockbox_pass_trials": []}}
    spec_path = portfolio._write_specs(
        tmp_path,
        [definition],
        stock_symbols=["AAA", "BBB", "CCC", "DDD", "EEE"],
        manifest_path=manifest_path,
        ml_report=ml_report,
    )["us_multiasset_test_d2"]
    spec = load_strategy_spec(spec_path)

    artifacts = portfolio._write_execution_artifacts(
        tmp_path,
        spec_path,
        spec,
        {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.2},
        signal_session="2026-07-13",
        rebalance_session="2026-07-14",
        data_as_of="2026-07-13T20:00:00+00:00",
        status="primary_deterministic_exploratory_history",
    )

    target = json.loads(artifacts["router_target_weights"].read_text())
    intents = json.loads(artifacts["router_rebalance_intents"].read_text())
    observation = json.loads(artifacts["router_execution_observation"].read_text())
    gross = sum(abs(row["target_weight"]) for row in target["target_weights"])
    assert gross == 1.0
    assert all(row["requires_order"] is False for row in intents["intents"])
    assert observation["execution_substate"] == "observation_only"


def test_target_weights_cli_rejects_unregistered_multiasset_identity(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    definition = {
        "sleeve_id": "D1",
        "strategy_name": "us_multiasset_cli_d1",
        "kind": "deterministic",
        "status": "primary_deterministic",
        "trial_id": "p1_lb252_reb5_gate0",
        "route_label": "multiasset:deterministic:p1_lb252_reb5_gate0",
        "params": {"top_n": 1},
    }
    spec_path = portfolio._write_specs(
        tmp_path,
        [definition],
        stock_symbols=["AAA"],
        manifest_path=manifest_path,
        ml_report={"selection": {"lockbox_pass_trials": []}},
    )["us_multiasset_cli_d1"]
    result = CliRunner().invoke(app, ["strategy", "target-weights", str(spec_path)])

    assert result.exit_code == 2, result.output
    assert "unsupported cross_sectional_momentum strategy identity" in result.output


def test_ai_roles_switch_or_fallback_without_order_authority(tmp_path: Path) -> None:
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    latest = pd.DataFrame(
        {
            "symbol": symbols,
            "baseline_score": [6, 5, 4, 3, 2, 1],
            "market_spy_mom_63": [0.1] * 6,
            "feature": [0.1] * 6,
        }
    )
    frozen = []
    predictions = {
        "model_a": [1, 2, 3, 4, 5, 6],
        "model_b": [6, 5, 4, 3, 2, 1],
        "model_c": [1, 6, 2, 5, 3, 4],
    }
    for trial_id, values in predictions.items():
        path = tmp_path / f"{trial_id}.joblib"
        joblib.dump(
            {
                "model": _FixedPredictionModel(values),
                "features": ["feature"],
                "fill_values": {"feature": 0.0},
            },
            path,
        )
        frozen.append({"trial_id": trial_id, "model_path": path.name})
    report = {"frozen_models": frozen}
    data = {"close": pd.DataFrame(index=pd.date_range("2026-07-11", periods=2, tz="UTC"))}
    baseline = {symbol: 0.2 for symbol in symbols[:5]}

    regime_weights, _, _ = portfolio._ai_latest_weights(
        tmp_path,
        {
            "role": "regime_switch",
            "component_trials": ["model_a"],
            "top_n": 5,
        },
        report,
        latest,
        baseline,
        data,
    )
    fallback_weights, _, _ = portfolio._ai_latest_weights(
        tmp_path,
        {
            "role": "disagreement_abstention",
            "component_trials": ["model_a", "model_b", "model_c"],
            "parameter": 5,
            "top_n": 5,
        },
        report,
        latest,
        baseline,
        data,
    )

    assert set(regime_weights) == {"BBB", "CCC", "DDD", "EEE", "FFF"}
    assert fallback_weights == baseline
    assert sum(regime_weights.values()) == 1.0
