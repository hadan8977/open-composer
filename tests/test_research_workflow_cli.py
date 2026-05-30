from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.research_brief import init_research_brief
from open_composer.research.router_promotion import _strict_data_next_actions


def test_strategy_research_workflow_aliases_strategy_evidence(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    init_research_brief(spec_path, sample_workspace)

    result = CliRunner().invoke(
        app,
        ["strategy", "research-workflow", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[DEPRECATED]" in result.output
    assert "strategy evidence complete" in result.output

    promotion_json = (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-promotion.json"
    )
    promotion_report = promotion_json.with_suffix(".md")

    assert promotion_json.exists()
    assert promotion_report.exists()
    assert not (sample_workspace / "reports" / "research" / "harness-runs.jsonl").exists()


def test_hybrid_adaptive_router_cli_passes_feed(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_research(*args, **kwargs):
        captured.update(kwargs)
        metrics = SimpleNamespace(
            alpha_vs_benchmark_buy_hold_annualized_pct=0.0,
            annualized_return_pct=12.0,
            sharpe_ratio=1.2,
        )
        best = SimpleNamespace(
            params=SimpleNamespace(label="beta_override:test"),
            train=metrics,
            out_of_sample=metrics,
            full_window=metrics,
            quality_flags=[],
        )
        return SimpleNamespace(
            report_path=sample_workspace / "reports" / "research" / "fake.json",
            best=best,
            research_cost={
                "candidate_count": 1,
                "walk_forward_candidate_count": 1,
                "estimated_total_backtest_passes": 1,
            },
            runtime_seconds={"total": 0.01},
        )

    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    monkeypatch.setattr("open_composer.cli.run_hybrid_adaptive_router_research", fake_research)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "hybrid-adaptive-router",
            str(spec_path),
            "--symbols",
            "QQQ,TQQQ",
            "--data-source",
            "alpaca",
            "--feed",
            "iex",
            "--max-candidates",
            "1",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert captured["feed"] == "iex"


def test_strict_data_next_actions_use_daily_wording() -> None:
    actions = _strict_data_next_actions(
        blockers=["research_cross_check"],
        data_profile={},
        timeframe="daily",
    )

    assert any("daily data" in action for action in actions)
    assert not any("intraday data" in action for action in actions)
