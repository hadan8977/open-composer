from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.regime_retrieval import search_similar_regimes
from open_composer.research.skill_attribution import run_skill_attribution


def test_regime_search_writes_report_from_fixtures(sample_workspace: Path) -> None:
    spec = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    report = search_similar_regimes(spec, root=sample_workspace, top_k=2)

    assert report.strategy_name == "qqq_pullback_15m"
    assert len(report.matches) >= 1
    assert (sample_workspace / "reports" / "regime_search" / "qqq_pullback_15m.json").exists()
    assert (sample_workspace / "reports" / "regime_search" / "qqq_pullback_15m.md").exists()


def test_regime_search_cli(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "regime-search",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
            "--top-k",
            "1",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Regime Search" in result.output


def test_skill_attribution_writes_report(sample_workspace: Path, repo_root: Path) -> None:
    copytree(repo_root / ".agents" / "skills", sample_workspace / ".agents" / "skills")
    report_dir = sample_workspace / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "sample-promotion.json").write_text(
        json.dumps({"ready": True}) + "\n",
        encoding="utf-8",
    )

    report = run_skill_attribution(sample_workspace, sample_size=10)

    assert report.rows
    assert any(row.skill_name == "strategy-designer" for row in report.rows)
    assert (sample_workspace / "reports" / "skill_attribution" / "latest.json").exists()
    assert (sample_workspace / "reports" / "skill_attribution" / "latest.md").exists()


def test_skill_attribution_cli(sample_workspace: Path, repo_root: Path, monkeypatch) -> None:
    copytree(repo_root / ".agents" / "skills", sample_workspace / ".agents" / "skills")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    result = CliRunner().invoke(
        app,
        ["strategy", "skill-attribution", "--sample-size", "3"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Skill Attribution" in result.output
