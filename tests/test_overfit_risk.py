from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.pbo import build_overfit_risk_report


def _write_sweep_payload(root: Path, strategy_name: str, trial_count: int) -> Path:
    path = root / "reports" / "research" / f"{strategy_name}-parameter-sweep.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "trial_count": trial_count,
                "candidate_count": trial_count,
                "stability": {"neighbor_success_rate": 0.20},
                "dsr_inputs": {"computed_dsr": 0.75, "computed_pbo": 0.80},
                "candidates": [
                    {"score": float(trial_count - index)} for index in range(trial_count)
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_pbo_proxy_triggers_for_large_trial_count(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    _write_sweep_payload(sample_workspace, "fixture_pullback_15m", 101)

    result = build_overfit_risk_report(spec_path, sample_workspace)

    assert result.status == "blocked"
    assert result.trial_count == 101
    assert "high_trial_count:101>100" in result.warnings
    assert result.blockers == ["pbo_proxy_high:0.800"]
    assert result.json_path is not None
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["pbo_proxy"] == 0.8


def test_overfit_risk_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    _write_sweep_payload(sample_workspace, "fixture_pullback_15m", 101)

    result = CliRunner().invoke(
        app,
        ["strategy", "overfit-risk", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "overfit risk complete" in result.output
    assert (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-overfit-risk.json"
    ).exists()
