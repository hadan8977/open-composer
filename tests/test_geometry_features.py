from __future__ import annotations

import json

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.geometry_features import build_geometry_feature_report


def test_geometry_features_writes_research_only_report(sample_workspace, monkeypatch) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "geometry-features",
            str(spec_path),
            "--window-bars",
            "8",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "geometry features complete" in result.output
    json_path = (
        sample_workspace / "reports" / "research" / "qqq_pullback_15m-geometry-features.json"
    )
    report_path = (
        sample_workspace / "reports" / "research" / "qqq_pullback_15m-geometry-features.md"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["research_only"] is True
    assert payload["kind"] == "geometry_features"
    assert (
        payload["feature_summary"]["path_signature_low_order"]["cumulative_log_return"] is not None
    )
    assert "requires_simple_baseline_comparison" in payload["promotion_blockers"]
    assert payload["research_run_index_record"]["kind"] == "geometry_features"
    assert report_path.exists()

    index_records = [
        json.loads(line)
        for line in (sample_workspace / "reports" / "research" / "index.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert index_records[-1]["kind"] == "geometry_features"
    assert index_records[-1]["status"] == "blocked"


def test_geometry_features_rejects_too_small_window(sample_workspace) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    try:
        build_geometry_feature_report(spec_path, sample_workspace, window_bars=4)
    except ValueError as exc:
        assert "window-bars" in str(exc)
    else:
        raise AssertionError("expected ValueError")
