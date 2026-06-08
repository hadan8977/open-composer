from __future__ import annotations

import json

from open_composer.research.auto_compare import (
    build_cross_thesis_compare,
    write_cross_thesis_compare,
)


def test_compare_aggregates_existing_runs(repo_root) -> None:
    payload = build_cross_thesis_compare(repo_root)

    assert payload["total_runs"] >= 1
    assert payload["total_factors_seen"] >= 1
    assert isinstance(payload["factors"], list)
    first = payload["factors"][0]
    assert "factor_id" in first
    assert "appearances" in first
    assert "selection_rate" in first


def test_compare_writes_json_and_md(repo_root) -> None:
    json_path, md_path = write_cross_thesis_compare(repo_root)

    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "factors" in data
    assert "# Cross-Thesis Factor Comparison" in md_path.read_text(encoding="utf-8")
