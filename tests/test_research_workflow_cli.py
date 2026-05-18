from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app


def test_strategy_research_workflow_writes_artifacts_and_harness_log(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    result = CliRunner().invoke(
        app,
        ["strategy", "research-workflow", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "research workflow complete" in result.output
    assert "promotion=blocked" in result.output
    assert "harness=blocked" in result.output

    promotion_json = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.json"
    promotion_report = promotion_json.with_suffix(".md")
    harness_log = sample_workspace / "reports" / "research" / "harness-runs.jsonl"

    assert promotion_json.exists()
    assert promotion_report.exists()
    assert harness_log.exists()

    records = [
        json.loads(line)
        for line in harness_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    record = records[0]
    assert record["workflow"] == "strategy.research_workflow"
    assert record["stage"] == "promotion"
    assert record["status"] == "blocked"
    assert record["promotion_status"] == "blocked"
    assert (
        record["artifacts"]["promotion_json"] == "reports/research/qqq_pullback_15m-promotion.json"
    )
    assert (
        record["artifacts"]["promotion_report"] == "reports/research/qqq_pullback_15m-promotion.md"
    )
    assert any(gate["name"] == "promotion_report" for gate in record["gate_results"])
