from __future__ import annotations

import json
from pathlib import Path

from open_composer.research.strategy_data_compare import run_strategy_data_compare


def test_strategy_data_compare_writes_blocker_safe_artifact(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = run_strategy_data_compare(
        spec_path,
        sample_workspace,
        primary="sample",
        secondary="sample",
    )

    assert result.status == "ok"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["strict_data_status"] == "ok"
    assert payload["compared_symbols"] == ["QQQ"]
    assert result.report_path.exists()


def test_strategy_data_compare_captures_missing_secondary_as_blocked(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = run_strategy_data_compare(
        spec_path,
        sample_workspace,
        primary="sample",
        secondary="missing_source",
    )

    assert result.status == "blocked"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["strict_data_status"] == "blocked"
    assert payload["blockers"]
