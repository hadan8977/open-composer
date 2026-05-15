from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app


def test_strategy_promotion_report_writes_promotion_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    comparison_path = (
        sample_workspace / "reports" / "data" / "comparisons" / "qqq_15m_alpaca_vs_longbridge.json"
    )
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(
        json.dumps(
            {
                "symbol": "QQQ",
                "timeframe": "15m",
                "left_source": "alpaca",
                "right_source": "longbridge",
                "left_feed": "iex",
                "right_feed": "nasdaq_basic",
                "left_rows": 10,
                "right_rows": 10,
                "matched_rows": 10,
                "missing_left_rows": 0,
                "missing_right_rows": 0,
                "matched_coverage_pct": 100.0,
                "max_abs_close_diff": 0.0,
                "mean_abs_close_diff": 0.0,
                "max_abs_close_diff_bps": 0.0,
                "mean_abs_close_diff_bps": 0.0,
                "max_abs_volume_diff": 0.0,
                "max_volume_diff_ratio": 0.0,
                "first_matched_timestamp": "2026-01-02T14:30:00+00:00",
                "last_matched_timestamp": "2026-01-02T16:00:00+00:00",
                "sample_missing_left_timestamps": [],
                "sample_missing_right_timestamps": [],
                "left_manifest_path": "data/cache/manifests/qqq_15m_alpaca_iex.json",
                "right_manifest_path": "data/cache/manifests/qqq_15m_longbridge_nasdaq_basic.json",
                "caveats": ["fixture replay"],
                "report_json_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.json",
                "report_markdown_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.md",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "strategy",
            "promotion-report",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
            "--oos-ratio",
            "0.3",
            "--walk-forward-folds",
            "3",
            "--cost-slippage-bps",
            "0",
            "--cost-slippage-bps",
            "5",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Promotion Report" in result.output

    json_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.json"
    report_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.md"
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["checks"]
    assert {item["name"] for item in payload["checks"]} == {
        "in_sample",
        "out_of_sample",
        "walk_forward",
        "cost_sensitivity",
        "data_comparison",
        "strict_data",
        "feature_packets",
        "benchmark_family",
    }
    assert payload["gate_summary"]["workflow_pass"] is True
    assert payload["gate_summary"]["research_pass"] is False
    assert payload["gate_summary"]["paper_ready_pass"] is False
    assert payload["benchmark_family"]["benchmarks"]["same_symbol_buy_hold"]["status"] == "ok"
    assert "market_proxy" in payload["benchmark_family"]["missing"]
    assert payload["data_profile"]["source_mode"] == "sample"
    assert payload["research_manifest"]["trial_count"] >= 1
    assert payload["research_manifest"]["spec_hash"]
    assert payload["data_comparisons"]
    assert payload["out_of_sample"] is not None
    assert "buy_hold_return_pct" in payload["full_window"]
    assert "alpha_vs_buy_hold_pct" in payload["full_window"]
    assert payload["walk_forward"]
    assert payload["cost_sensitivity"]
    text = report_path.read_text(encoding="utf-8")
    assert "## Checks" in text
    assert "## Out Of Sample" in text
    assert "Alpha vs Buy/Hold" in text
    assert "## Walk Forward" in text
    assert "## Cost Sensitivity" in text
    assert "## Data Comparisons" in text
    assert "## Benchmark Family" in text
    assert "## Research Manifest" in text
    assert "workflow_pass" in text
