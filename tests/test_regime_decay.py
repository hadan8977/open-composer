from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.alpha_decay import assess_alpha_decay
from open_composer.research.regime_performance import _leak_free_regime_labels
from open_composer.research.search_policy import ObjectiveSet, SearchPolicy


def test_backtest_writes_equity_series_artifact(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    artifacts = run_backtest(spec_path, sample_workspace)

    assert artifacts.run.equity_series_path is not None
    path = Path(artifacts.run.equity_series_path)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == artifacts.run.run_id
    assert len(payload["timestamps"]) == len(payload["equity"]) == len(payload["bar_returns"])
    assert payload["bar_returns"][0] == 0.0
    assert all(value == value for value in payload["bar_returns"])


def test_alpha_decay_stationary_positive_returns_ok() -> None:
    result = assess_alpha_decay(
        "stationary",
        "daily",
        [0.001] * 90,
        policy_warnings=[],
    )

    assert result.status == "ok"
    assert result.alpha_stale is False


def test_alpha_decay_front_loaded_returns_blocked() -> None:
    result = assess_alpha_decay(
        "front_loaded",
        "daily",
        [0.02] * 30 + [0.0] * 30 + [-0.001] * 30,
        policy_warnings=[],
    )

    assert result.status == "blocked"
    assert result.alpha_stale is True
    assert any("old_pnl_concentration_high" in item for item in result.blockers)


def test_regime_labels_are_leak_free() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC"),
            "close": [100 + index * 0.2 for index in range(120)],
        }
    )
    baseline = _leak_free_regime_labels(frame)
    changed = frame.copy()
    changed.loc[119, "close"] = 10_000.0

    updated = _leak_free_regime_labels(changed)

    assert baseline[:100] == updated[:100]


def test_evaluation_policy_is_optional_for_legacy_specs(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    spec = load_strategy_spec(spec_path)

    assert spec.evaluation_policy is None


def test_search_policy_budget_and_evolutionary_objective_validation() -> None:
    SearchPolicy(strategy="random", candidate_budget=5).validate()

    try:
        SearchPolicy(strategy="random", candidate_budget=0).validate()
    except ValueError as exc:
        assert "candidate_budget" in str(exc)
    else:
        raise AssertionError("expected candidate budget validation failure")

    try:
        SearchPolicy(strategy="evolutionary", candidate_budget=5).validate()
    except ValueError as exc:
        assert "objective_set" in str(exc)
    else:
        raise AssertionError("expected evolutionary objective validation failure")

    SearchPolicy(
        strategy="evolutionary",
        candidate_budget=5,
        objective_set=ObjectiveSet(primary_metric="return"),
    ).validate()


def test_alpha_decay_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = CliRunner().invoke(
        app,
        ["strategy", "alpha-decay", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Alpha Decay" in result.output
    assert (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-alpha-decay.json"
    ).exists()
