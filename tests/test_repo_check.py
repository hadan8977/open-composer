from __future__ import annotations

from pathlib import Path
from shutil import copytree

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.repo_check import build_repo_check_report


def _copy_repo_check_inputs(repo_root: Path, target: Path) -> None:
    for relative in [
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "LICENSE",
        "Makefile",
        "scripts/sync-agent-skills.py",
        "scripts/check-agent-parity.py",
        "docs/product-golden-path-codex-quant-review-2026-05-13.zh.md",
        "docs/user-guide.md",
        "docs/remote-dashboard-deploy.zh.md",
        "docs/setup-local.zh.md",
        "docs/longbridge-integration.md",
        "docs/research-contract-p0-p2-plan-2026-05-17.zh.md",
        "docs/product-structure-efficiency-review-2026-05-17.zh.md",
        "docs/product-efficiency-optimization-roadmap-2026-05-17.zh.md",
        "docs/product-mvp-hardening-research-plan-2026-05-17.zh.md",
        "docs/harness-engineering-agent-quant-review-2026-05-17.zh.md",
        "docs/harness-engineering-expanded-research-log-2026-05-17.zh.md",
        "docs/harness-engineering-expanded-architecture-review-2026-05-17.zh.md",
    ]:
        source = repo_root / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    copytree(repo_root / ".agents", target / ".agents", dirs_exist_ok=True)
    copytree(repo_root / ".claude", target / ".claude", dirs_exist_ok=True)


def test_repo_check_passes_for_repo_control_surface(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)

    report = build_repo_check_report(sample_workspace)

    assert report.status == "ok"
    assert report.ready is True
    assert {check.name: check.status for check in report.checks}["no_context_start_doc"] == "ok"
    assert {check.name: check.status for check in report.checks}["capability_registry"] == "ok"
    assert {check.name: check.status for check in report.checks}["docs_inventory"] == "ok"
    assert {check.name: check.status for check in report.checks}["claude_parity"] == "ok"
    assert {check.name: check.status for check in report.checks}["readme_research_controls"] == "ok"


def test_repo_check_blocks_when_readme_entry_is_missing(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    readme = sample_workspace / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "docs/product-golden-path-codex-quant-review-2026-05-13.zh.md",
            "docs/missing-entry.zh.md",
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "readme_project_docs")
    assert check.status == "blocked"
    assert "Project Docs" in check.message


def test_repo_check_blocks_extra_historical_docs(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    stale = sample_workspace / "docs" / "old-plan.zh.md"
    stale.write_text("# stale\n", encoding="utf-8")

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "docs_inventory")
    assert check.status == "blocked"
    assert "old-plan.zh.md" in str(check.details)


def test_repo_check_blocks_when_research_controls_are_missing(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    user_guide = sample_workspace / "docs" / "user-guide.md"
    user_guide.write_text(
        user_guide.read_text(encoding="utf-8").replace(
            "uv run oc strategy llm-exposure-switch",
            "uv run oc strategy removed-llm-command",
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "readme_research_controls")
    assert check.status == "blocked"
    assert "llm-exposure-switch" in str(check.details)


def test_repo_check_blocks_when_research_metadata_controls_are_missing(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    user_guide = sample_workspace / "docs" / "user-guide.md"
    user_guide.write_text(
        user_guide.read_text(encoding="utf-8").replace(
            "research_brief",
            "removed_brief_anchor",
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "readme_research_controls")
    assert check.status == "blocked"
    assert "research_brief" in str(check.details)


def test_repo_check_blocks_non_strict_verify_gates(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    makefile = sample_workspace / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8")
        .replace("uv run oc repo check --strict", "uv run oc repo check")
        .replace("uv run oc readiness --strict", "uv run oc readiness")
        .replace("uv run oc deploy prepare --strict", "uv run oc deploy prepare")
        .replace("uv run oc feature validate --strict", "uv run oc feature validate"),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "makefile_verify")
    assert check.status == "blocked"
    assert "repo-check runs strict" in str(check.details)
    assert "feature-validate runs strict" in str(check.details)


def test_repo_check_blocks_when_claude_skill_mirror_drifts(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    skill = sample_workspace / ".claude" / "skills" / "risk-reviewer" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nDrifted.\n", encoding="utf-8")

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked"
    assert "risk-reviewer" in str(check.details)


def test_repo_check_cli_writes_reports(
    sample_workspace: Path,
    repo_root: Path,
    monkeypatch,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(app, ["repo", "check"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Open Composer Repository Check" in result.output
    assert (sample_workspace / "reports" / "repo" / "repo-check.json").exists()
    assert (sample_workspace / "reports" / "repo" / "repo-check.md").exists()
