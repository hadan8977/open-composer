from __future__ import annotations

from pathlib import Path

from open_composer.readiness import build_readiness_report, write_readiness_report


def test_readiness_report_covers_deploy_surface(sample_workspace: Path) -> None:
    report = build_readiness_report(sample_workspace)
    json_path, md_path = write_readiness_report(report, sample_workspace)
    checks = {check.name: check for check in report.checks}

    assert report.ready is True
    assert report.status in {"ok", "warning"}
    assert checks["sample_data"].status == "ok"
    assert checks["cockpit_catalog"].status == "ok"
    assert checks["feature_packets"].details["packet_count"] == 0
    assert "paper_monitor" in checks
    assert "strategy_capabilities" in checks
    assert checks["strategy_capabilities"].status == "ok"
    assert checks["strategy_capabilities"].suggested_actions == []
    assert checks["strategy_capabilities"].details["draft_backend_status_counts"]
    assert json_path.exists()
    assert md_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "Open Composer Readiness" in markdown
    assert "## Checks" in markdown
    assert "### cockpit_catalog" in markdown
    if any(check.suggested_actions for check in report.checks):
        assert "Suggested actions" in markdown
