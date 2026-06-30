from __future__ import annotations

import json
from pathlib import Path

from open_composer.research.auto_compare import (
    build_cross_thesis_compare,
    write_cross_thesis_compare,
)


def test_compare_aggregates_existing_runs(repo_root) -> None:
    payload = build_cross_thesis_compare(repo_root)

    assert payload["total_runs"] >= 0
    assert payload["total_factors_seen"] >= 0
    assert "excluded_run_count" in payload
    assert isinstance(payload["factors"], list)
    if payload["factors"]:
        first = payload["factors"][0]
        assert "factor_id" in first
        assert "appearances" in first
        assert "selection_rate" in first
    assert "concentration" in payload
    assert "top_factor_selection_share" in payload["concentration"]


def test_compare_writes_json_and_md(repo_root) -> None:
    json_path, md_path = write_cross_thesis_compare(repo_root)

    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "factors" in data
    markdown = md_path.read_text(encoding="utf-8")
    assert "# Cross-Thesis Factor Comparison" in markdown
    assert "## Concentration" in markdown
    assert "IR mean" in markdown


def test_compare_filters_runs_without_current_metadata(tmp_path: Path) -> None:
    auto_dir = tmp_path / "reports" / "research" / "auto"
    good = auto_dir / "20260618T000000Z_good"
    old = auto_dir / "20260618T000001Z_old"
    good.mkdir(parents=True)
    old.mkdir(parents=True)
    for run_dir in [good, old]:
        (run_dir / "thesis.md").write_text("Trend thesis on SYN daily.\n", encoding="utf-8")
        (run_dir / "ic_scores.json").write_text(
            json.dumps(
                {
                    "alpha101_007_price_above_sma_10d": {
                        "rank_ic": 0.08,
                        "ir": 0.52,
                        "coverage_pct": 95,
                        "observations": 250,
                    }
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "selected_factors.json").write_text(
            json.dumps(["alpha101_007_price_above_sma_10d"]),
            encoding="utf-8",
        )
    (good / "run_metadata.json").write_text(
        json.dumps(
            {
                "schema_version": "2",
                "usable_selection": True,
                "primary_symbol": "SYN",
                "timeframe": "daily",
                "data_acquisition_tier": "sample_smoke",
                "research_status": "warning",
            }
        ),
        encoding="utf-8",
    )

    payload = build_cross_thesis_compare(tmp_path)

    assert payload["total_runs"] == 1
    assert payload["excluded_run_count"] == 1
    assert payload["excluded_runs"][0]["reason"] == "missing_run_metadata"
    assert payload["factors"][0]["ir_mean"] == 0.52
