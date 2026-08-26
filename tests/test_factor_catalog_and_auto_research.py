from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.auto_research import (
    _select_with_keyword_heuristic,
    run_auto_research,
)


def test_factor_library_source_materializes_expression(repo_root: Path) -> None:
    spec = load_strategy_spec(
        repo_root
        / "tests"
        / "fixtures"
        / "strategy_specs"
        / "factor_library"
        / "example_catalog_factor_daily.yaml"
    )

    assert spec.factors["trend_momentum_signal"].source == "factor_library"
    assert spec.factors["trend_momentum_signal"].expression == (
        "(close - lag(close, 120)) / lag(close, 120)"
    )
    assert spec.factors["overnight_gap"].expression == "(open - lag(close, 1)) / lag(close, 1)"


def test_factor_cli_catalog_status_and_use_in(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    runner = CliRunner()
    status = runner.invoke(app, ["factor", "catalog-status", "--strict"], catch_exceptions=False)
    assert status.exit_code == 0
    assert "catalog size: 84" in status.output
    assert "errors: 0" in status.output

    result = runner.invoke(
        app,
        [
            "factor",
            "use-in",
            str(spec_path),
            "alpha158_kbar_body",
            "--name",
            "catalog_body",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    spec = load_strategy_spec(spec_path)
    assert spec.factors["catalog_body"].source == "factor_library"
    assert spec.factors["catalog_body"].expression == "(close - open) / open"
    lineage = sample_workspace / "reports" / "factors" / "alpha158_kbar_body" / "lineage.json"
    payload = json.loads(lineage.read_text(encoding="utf-8"))
    assert (
        payload["used_in_specs"][0]["spec_path"]
        == "strategy_specs/drafts/fixture_pullback_15m.yaml"
    )


def test_keyword_heuristic_selects_expected_families() -> None:
    trend = _select_with_keyword_heuristic("Find a strong uptrend continuation strategy")
    drawdown = _select_with_keyword_heuristic("Reduce exposure during drawdowns and crashes")

    assert "trend_momentum" in {factor.family for factor in trend}
    assert any("drawdown" in factor.id or factor.family == "risk_regime" for factor in drawdown)


def test_auto_research_blocks_market_data_without_iteration_workflow(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "open_composer.research.auto_research._check_data_source_available",
        lambda source: (True, "available"),
    )

    with pytest.raises(ValueError, match="preregistered iteration workflow"):
        run_auto_research(
            "Trend thesis on QQQ daily.",
            ["QQQ"],
            data_source="alpaca",
            root=sample_workspace,
        )

    assert not (sample_workspace / "reports/research/auto").exists()


def test_auto_research_writes_spec_report_and_lineage(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    metric = SimpleNamespace(
        rank_ic=0.08,
        ir=0.64,
        rolling_rank_ic_mean=0.04,
        stability_score=0.75,
        coverage_pct=96.0,
        observations=250,
        top_bottom_spread_pct=1.2,
        flags=[],
    )

    def fake_factor_lab(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(
            status="ok",
            factor_metrics=[metric],
            json_path=sample_workspace / "reports" / "research" / f"{spec_path.stem}.json",
        )

    def fake_evidence(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(status="warning")

    monkeypatch.setattr("open_composer.research.auto_research.run_factor_lab", fake_factor_lab)
    monkeypatch.setattr("open_composer.research.evidence.build_strategy_evidence", fake_evidence)

    result = run_auto_research(
        "Find a daily trend strategy that exits in high-volatility regimes.",
        ["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=3,
        root=sample_workspace,
    )

    assert result.spec_path.exists()
    assert result.report_path.exists()
    assert result.evidence_status == "warning"
    assert result.selected_factors
    data_profile = json.loads(
        (Path(result.report_path).parent / "data_profile.json").read_text(encoding="utf-8")
    )
    oos_summary = json.loads(
        (Path(result.report_path).parent / "oos_summary.json").read_text(encoding="utf-8")
    )
    assert data_profile["acquisition_tier"] == "sample_smoke"
    assert data_profile["refresh_data"] is False
    assert oos_summary["split"] == "chronological_70_30"
    assert oos_summary["candidate_count"] >= len(result.selected_factors)
    spec = load_strategy_spec(result.spec_path)
    for factor_id in result.selected_factors:
        factor_name = f"{factor_id}_signal"
        assert spec.factors[factor_name].source == "factor_library"
    assert spec.factors["composite_score"].source == "expression"
    assert spec.costs.commission_pct == 0.05
    assert spec.costs.slippage_bps == 5.0
    for factor_id in result.selected_factors:
        assert (sample_workspace / "reports" / "factors" / factor_id / "lineage.json").exists()


def test_auto_research_marks_fallback_when_no_usable_ic(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    metric = SimpleNamespace(
        rank_ic=None,
        ir=None,
        rolling_rank_ic_mean=None,
        stability_score=0.0,
        coverage_pct=96.0,
        observations=250,
        top_bottom_spread_pct=None,
        flags=["zero_variance"],
    )

    def fake_factor_lab(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(
            status="warning",
            factor_metrics=[metric],
            json_path=sample_workspace / "reports" / "research" / f"{spec_path.stem}.json",
        )

    def fake_evidence(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(status="warning")

    monkeypatch.setattr("open_composer.research.auto_research.run_factor_lab", fake_factor_lab)
    monkeypatch.setattr("open_composer.research.evidence.build_strategy_evidence", fake_evidence)

    result = run_auto_research(
        "Find a daily trend strategy that exits in high-volatility regimes.",
        ["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=2,
        root=sample_workspace,
    )

    run_dir = result.report_path.parent
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))

    assert result.selected_factors == []
    assert json.loads((run_dir / "selected_factors.json").read_text(encoding="utf-8")) == []
    assert metadata["usable_selection"] is False
    assert metadata["selected_count"] == 0
    assert "fallback catalog factors" in result.report_path.read_text(encoding="utf-8")


def test_auto_research_downgrades_sample_strict_data_to_warning(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    metric = SimpleNamespace(
        rank_ic=0.08,
        ir=0.64,
        rolling_rank_ic_mean=0.04,
        stability_score=0.75,
        coverage_pct=96.0,
        observations=250,
        top_bottom_spread_pct=1.2,
        flags=[],
    )

    def fake_factor_lab(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(
            status="ok",
            factor_metrics=[metric],
            json_path=sample_workspace / "reports" / "research" / f"{spec_path.stem}.json",
        )

    def fake_evidence(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        report_json = sample_workspace / "reports" / "research" / f"{spec_path.stem}-report.json"
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(
            json.dumps(
                {
                    "promotion": {"status": "blocked"},
                    "paper_readiness": {"status": "blocked"},
                    "checklist": [
                        {"name": "leakage_defaults", "status": "ok", "evidence": {}},
                        {
                            "name": "data_quality",
                            "status": "blocked",
                            "evidence": {
                                "status": "warning",
                                "data_source": "sample",
                                "data_source_mode": "sample",
                                "evidence_level": "E0_sample_smoke",
                                "warnings": ["sample data is workflow smoke-test evidence only"],
                            },
                        },
                        {
                            "name": "paper_gap",
                            "status": "blocked",
                            "evidence": "paper_readiness_status=blocked",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            status="blocked",
            research_report=SimpleNamespace(json_path=report_json),
            control=SimpleNamespace(
                state={
                    "promotion_state": {
                        "status": "blocked",
                        "blocked_checks": ["strict_data"],
                        "strict_data": {
                            "status": "blocked",
                            "message": "sample data is workflow evidence only",
                            "details": {
                                "data_source": "sample",
                                "data_source_mode": "sample",
                                "evidence_level": "E0_sample_smoke",
                            },
                        },
                    },
                    "blocked_items": ["promotion:strict_data"],
                    "warning_items": ["promotion_status=blocked"],
                }
            ),
        )

    monkeypatch.setattr("open_composer.research.auto_research.run_factor_lab", fake_factor_lab)
    monkeypatch.setattr("open_composer.research.evidence.build_strategy_evidence", fake_evidence)

    result = run_auto_research(
        "Find a daily trend strategy that exits in high-volatility regimes.",
        ["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=2,
        root=sample_workspace,
    )

    assert result.evidence_status == "warning"
    assert result.raw_evidence_status == "blocked"
    assert not result.blockers
    assert any("strict_data" in item for item in result.warnings)
    report = result.report_path.read_text(encoding="utf-8")
    assert "- Research status: `warning`" in report
    assert "- Raw strategy evidence status: `blocked`" in report
    assert "## Data Provenance" in report
    assert "## OOS Check" in report
    assert "## Factor Rejections" in report


def test_auto_research_zero_cost_smoke_is_explicit(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    metric = SimpleNamespace(
        rank_ic=0.08,
        ir=0.64,
        rolling_rank_ic_mean=0.04,
        stability_score=0.75,
        coverage_pct=96.0,
        observations=250,
        top_bottom_spread_pct=1.2,
        flags=[],
    )

    def fake_factor_lab(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(
            status="ok",
            factor_metrics=[metric],
            json_path=sample_workspace / "reports" / "research" / f"{spec_path.stem}.json",
        )

    def fake_evidence(spec_path: Path, root: Path, **kwargs):  # noqa: ARG001
        return SimpleNamespace(status="warning")

    monkeypatch.setattr("open_composer.research.auto_research.run_factor_lab", fake_factor_lab)
    monkeypatch.setattr("open_composer.research.evidence.build_strategy_evidence", fake_evidence)

    result = run_auto_research(
        "Find a daily trend strategy that exits in high-volatility regimes.",
        ["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=2,
        zero_cost_smoke=True,
        root=sample_workspace,
    )

    spec = load_strategy_spec(result.spec_path)
    assert spec.costs.slippage_bps == 0.0
    assert "- Zero-cost smoke: `True`" in result.report_path.read_text(encoding="utf-8")


def test_auto_research_rejects_unavailable_market_source_before_writing_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="preregistered iteration workflow"):
        run_auto_research(
            "Trend thesis on QQQ daily.",
            ["QQQ"],
            max_factors=2,
            root=sample_workspace,
        )

    assert not (sample_workspace / "reports/research/auto").exists()
