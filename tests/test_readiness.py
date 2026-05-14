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
    assert checks["dashboard_catalog"].status == "ok"
    assert checks["dashboard_bundle"].status == "warning"
    assert checks["dashboard_bundle"].suggested_actions == [
        "make dashboard-build",
        "uv run oc dashboard html",
    ]
    assert checks["dashboard_api_auth"].details["token_configured"] is False
    assert checks["dashboard_api_auth"].suggested_actions == [
        "export OPEN_COMPOSER_DASHBOARD_TOKEN=<local-token>"
    ]
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
    assert "Suggested actions" in markdown
