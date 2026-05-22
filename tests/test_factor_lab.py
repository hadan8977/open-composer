from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.factor_lab import run_factor_lab


def test_factor_lab_writes_factor_diagnostics(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = _write_factor_spec(sample_workspace)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "factor-lab",
            str(spec_path),
            "--forward-bars",
            "1",
            "--quantiles",
            "4",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "factor lab complete" in result.output
    json_path = sample_workspace / "reports" / "research" / "factor_lab_fixture-factor-lab.json"
    report_path = sample_workspace / "reports" / "research" / "factor_lab_fixture-factor-lab.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "warning"
    assert payload["forward_bars"] == 1
    assert {item["name"] for item in payload["factor_metrics"]} == {"mom3", "mom3_copy"}
    assert payload["factor_correlation_matrix"]["mom3"]["mom3_copy"] == 1.0
    assert any(flag.startswith("high_factor_correlation") for flag in payload["quality_flags"])
    text = report_path.read_text(encoding="utf-8")
    assert "## Factor Metrics" in text
    assert "## Factor Correlation Matrix" in text
    assert "`mom3`" in text


def test_factor_lab_blocks_specs_without_custom_factors(sample_workspace: Path) -> None:
    result = run_factor_lab(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
    )

    assert result.status == "blocked"
    assert result.quality_flags == ["no_custom_factors"]
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["factor_metrics"] == []


def _write_factor_spec(root: Path) -> Path:
    spec_path = root / "strategy_specs" / "drafts" / "factor_lab_fixture.yaml"
    source = yaml.safe_load(
        (root / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    source["name"] = "factor_lab_fixture"
    source["description"] = "Factor Lab fixture."
    source["entry"] = {"all": ["mom3 > 0"], "any": []}
    source["exit"] = {"all": [], "any": ["mom3 < 0"]}
    source["factors"] = {
        "mom3": {"source": "expression", "expression": "close / lag(close, 3) - 1"},
        "mom3_copy": {"source": "expression", "expression": "close / lag(close, 3) - 1"},
    }
    spec_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return spec_path
