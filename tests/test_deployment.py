from __future__ import annotations

from pathlib import Path

from open_composer.deployment import prepare_workspace


def test_prepare_workspace_writes_deployment_artifacts(sample_workspace: Path) -> None:
    report = prepare_workspace(sample_workspace)
    step_names = [step.name for step in report.steps]

    assert report.status in {"ok", "warning"}
    assert report.ready is True
    assert step_names == [
        "runtime_dirs",
        "feature_validation",
        "paper_monitor",
        "readiness",
        "dashboard_artifacts",
    ]
    assert report.report_json_path == "reports/deployment/prepare.json"
    assert report.report_markdown_path == "reports/deployment/prepare.md"
    assert (sample_workspace / "reports" / "deployment" / "prepare.json").exists()
    assert (sample_workspace / "reports" / "deployment" / "prepare.md").exists()
    assert (sample_workspace / "reports" / "features" / "manifest.json").exists()
    assert any(path.startswith("reports/dashboard/") for path in report.output_paths)
    assert any(path.startswith("reports/features/") for path in report.output_paths)
    assert any(path.startswith("reports/paper/") for path in report.output_paths)
    assert any(step.suggested_actions for step in report.steps if step.status == "warning")
    readiness_step = next(step for step in report.steps if step.name == "readiness")
    assert all(
        action != "export OPEN_COMPOSER_DASHBOARD_TOKEN=<local-token>"
        for action in readiness_step.suggested_actions
    )
    dashboard_step = next(step for step in report.steps if step.name == "dashboard_artifacts")
    assert dashboard_step.details["readiness_status"] in {"ok", "warning", "blocked"}
    assert dashboard_step.details["deployment_status"] in {"ok", "warning", "blocked"}
    markdown = (sample_workspace / "reports" / "deployment" / "prepare.md").read_text(
        encoding="utf-8"
    )
    assert "Suggested actions" in markdown
