from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app


def test_strategy_research_workflow_aliases_strategy_evidence(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

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
