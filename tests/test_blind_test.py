from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.blind_test import run_blind_test
from open_composer.research.promotion import build_promotion_report


def test_blind_test_writes_four_mode_report(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    report = run_blind_test(spec_path, sample_workspace, seed=11)

    assert [result.mode for result in report.results] == [
        "real",
        "anonymous",
        "random_remap",
        "sector_preserved",
    ]
    assert report.results[1].correlation_with_real == 1.0
    assert "structure-driven" in report.interpretation
    assert (sample_workspace / "reports" / "blind_test" / "fixture_pullback_15m.json").exists()
    assert (sample_workspace / "reports" / "blind_test" / "fixture_pullback_15m.md").exists()


def test_blind_test_cli_command_writes_report(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "blind-test",
            str(sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"),
            "--seed",
            "7",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Blind Test" in result.output
    payload = json.loads(
        (sample_workspace / "reports" / "blind_test" / "fixture_pullback_15m.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["results"]) == 4
    assert payload["results"][1]["mode"] == "anonymous"


def test_promotion_report_requires_blind_test_for_llm_contribution(
    sample_workspace: Path,
) -> None:
    spec_path = _llm_review_spec(sample_workspace, "qqq_pullback_llm_review_15m")

    report = build_promotion_report(spec_path, sample_workspace)

    assert report.five_pass_checks
    assert report.llm_contribution_pass is False
    assert report.five_pass_checks["llm_contribution_pass"] == "fail"
    assert "missing BlindTrade" in report.pass_reasons["llm_contribution"]


def test_promotion_report_accepts_matching_blind_test_for_llm_contribution(
    sample_workspace: Path,
) -> None:
    spec_path = _llm_review_spec(sample_workspace, "qqq_pullback_llm_review_15m")
    run_blind_test(spec_path, sample_workspace)

    report = build_promotion_report(spec_path, sample_workspace)

    assert report.five_pass_checks
    assert report.llm_contribution_pass is True
    assert report.five_pass_checks["llm_contribution_pass"] == "pass"
    assert "BlindTrade anonymous mode" in report.pass_reasons["llm_contribution"]


def _llm_review_spec(sample_workspace: Path, name: str) -> Path:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    target = sample_workspace / "strategy_specs" / "drafts" / f"{name}.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = name
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return target
