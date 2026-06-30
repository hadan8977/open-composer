from __future__ import annotations

import json
from pathlib import Path

from open_composer.research.promotion import build_promotion_report
from tests.test_ml_backend_training import _write_syn_ml_spec


def test_promotion_report_adds_ml_baseline_gate(sample_workspace: Path) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)

    result = build_promotion_report(
        spec_path,
        sample_workspace,
        walk_forward_folds=1,
        cost_slippage_bps=[5],
    )

    gate = next(item for item in result.checks if item.name == "ml_beats_linear_baseline")
    assert gate.status in {"ok", "warning", "blocked"}
    comparison_path = (
        sample_workspace
        / "reports"
        / "research"
        / "ml"
        / "syn_daily_ml_probe"
        / "ml_vs_baseline.json"
    )
    assert comparison_path.exists()
    payload = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert payload["ml"]["signals"] >= 1
    assert payload["baseline"]["signals"] >= 1
