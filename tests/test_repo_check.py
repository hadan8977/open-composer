from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from shutil import copyfile, copytree

import pytest
from typer.testing import CliRunner

from open_composer.capabilities import load_registry
from open_composer.cli import app
from open_composer.repo_check import REQUIRED_ENTRY_FILES, build_repo_check_report

# Copy only the current entry surface plus the independent machine-check inputs.
_NON_DOC_INPUTS = [
    "README.md",
    "LICENSE",
    "Makefile",
    "scripts/sync-agent-skills.py",
    "scripts/check-agent-parity.py",
]


def _copy_repo_check_inputs(repo_root: Path, target: Path) -> None:
    for relative in [*_NON_DOC_INPUTS, *sorted(REQUIRED_ENTRY_FILES)]:
        source = repo_root / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    copytree(repo_root / ".agents", target / ".agents", dirs_exist_ok=True)
    copytree(repo_root / ".claude", target / ".claude", dirs_exist_ok=True)
    copytree(repo_root / "harness", target / "harness", dirs_exist_ok=True)
    # The live registry may reference a research fixture outside data/fixtures.
    # Copy only declared files absent from the isolated workspace, not entire
    # research output directories or shared writable links to real evidence.
    for capability in load_registry(repo_root).capabilities:
        if not capability.fixture:
            continue
        source = repo_root / capability.fixture
        destination = target / capability.fixture
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, destination)


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
            "research/README.md",
            "docs/missing-entry.zh.md",
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "readme_project_docs")
    assert check.status == "blocked"
    assert "Project Docs" in check.message


def test_repo_check_allows_unrelated_docs_and_history(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    stale = sample_workspace / "docs" / "old-plan.zh.md"
    stale.write_text("# stale\n", encoding="utf-8")

    archive = sample_workspace / "docs/archive"
    archive.mkdir(exist_ok=True)
    (archive / "old-plan.zh.md").write_text("# Frozen history\n", encoding="utf-8")
    report = build_repo_check_report(sample_workspace)

    assert report.status == "ok"
    check = next(item for item in report.checks if item.name == "docs_inventory")
    assert check.status == "ok"


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
        .replace("uv run --no-sync oc repo check --strict", "uv run --no-sync oc repo check")
        .replace("uv run --no-sync oc readiness --strict", "uv run --no-sync oc readiness")
        .replace(
            "uv run --no-sync oc deploy prepare --strict", "uv run --no-sync oc deploy prepare"
        )
        .replace(
            "uv run --no-sync oc feature validate --strict", "uv run --no-sync oc feature validate"
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "makefile_verify")
    assert check.status == "blocked"
    assert "repo-check runs strict" in str(check.details)
    assert "feature-validate runs strict" in str(check.details)


@pytest.mark.parametrize(
    "skill_name", ["risk-reviewer", "backtest-forensics", "research-plan-reviewer"]
)
def test_repo_check_blocks_when_claude_skill_mirror_drifts(
    sample_workspace: Path,
    repo_root: Path,
    skill_name: str,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    skill = sample_workspace / ".claude" / "skills" / skill_name / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nDrifted.\n", encoding="utf-8")

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked"
    assert skill_name in str(check.details)


def test_repo_check_blocks_stale_claude_only_skill(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    stale = sample_workspace / ".claude" / "skills" / "retired-method"
    stale.mkdir()
    (stale / "SKILL.md").write_text("Retired method.", encoding="utf-8")

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked"
    assert check.details["unexpected_skills"] == ["retired-method"]


def test_repo_check_blocks_when_skill_manifest_path_is_missing(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    manifest = sample_workspace / "harness" / "skill_manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            ".agents/skills/risk-reviewer/SKILL.md",
            ".agents/skills/risk-reviewer/MISSING.md",
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "harness_policy")
    assert check.status == "blocked"
    assert "missing_skill_paths" in str(check.details)
    assert "risk-reviewer/MISSING.md" in str(check.details)


def test_repo_check_blocks_when_risk_domain_skill_is_not_manifested(
    sample_workspace: Path,
    repo_root: Path,
) -> None:
    _copy_repo_check_inputs(repo_root, sample_workspace)
    manifest = sample_workspace / "harness" / "skill_manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "  source-researcher:\n",
            "  source-researcher-unlisted:\n",
            1,
        ),
        encoding="utf-8",
    )

    report = build_repo_check_report(sample_workspace)

    assert report.status == "blocked"
    check = next(item for item in report.checks if item.name == "harness_policy")
    assert check.status == "blocked"
    assert "unmanifested_required_skills" in str(check.details)
    assert "source-researcher" in str(check.details)


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


@pytest.mark.parametrize(
    "relative",
    ["docs/rules.md", "control.json", "board.md", "research/README.md", "prompts/reviewer.md"],
)
def test_repo_check_requires_current_entries(sample_workspace, repo_root, relative):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    (sample_workspace / relative).unlink()

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "current_product_docs")
    assert check.status == "blocked"
    assert relative in check.details["missing"]


def test_repo_check_rejects_ambiguous_control_switch(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    control = sample_workspace / "control.json"
    data = json.loads(control.read_text())
    data["research"] = "false"
    control.write_text(json.dumps(data))

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "current_product_docs")
    assert check.status == "blocked" and "control.json" in check.details["invalid"]


def test_repo_check_requires_a_real_role_prompt(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    config = sample_workspace / "research/workflow.json"
    data = json.loads(config.read_text())
    data["roles"]["reviewer"]["prompt"] = "prompts/missing.md"
    config.write_text(json.dumps(data))

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "current_product_docs")
    assert check.status == "blocked" and "research/workflow.json" in check.details["invalid"]


@pytest.mark.parametrize("body", ["# Own rules\n", "@AGENTS.md\nRun all paper orders.\n"])
def test_claude_must_only_import_shared_instructions(sample_workspace, repo_root, body):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    (sample_workspace / "CLAUDE.md").write_text(body)

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked" and "claude_import" in check.details


def test_skill_metadata_must_match_directory(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    skill = sample_workspace / ".agents/skills/risk-reviewer/SKILL.md"
    skill.write_text(skill.read_text().replace("name: risk-reviewer", "name: another-skill", 1))

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "repo_skills")
    assert check.status == "blocked"
    assert "risk-reviewer" in check.details["metadata_errors"]


def test_manifest_cannot_reference_a_different_skill_file(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    manifest = sample_workspace / "harness/skill_manifest.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            ".agents/skills/risk-reviewer/SKILL.md",
            ".claude/skills/risk-reviewer/SKILL.md",
        )
    )

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "harness_policy")
    assert check.status == "blocked"
    assert ".claude/skills/risk-reviewer/SKILL.md" in check.details["missing_skill_paths"]


@pytest.mark.parametrize("mutation", ["missing", "drift", "extra"])
def test_parity_covers_skill_resources(sample_workspace, repo_root, mutation):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    source = sample_workspace / ".agents/skills/risk-reviewer/references/example.md"
    target = sample_workspace / ".claude/skills/risk-reviewer/references/example.md"
    source.parent.mkdir(exist_ok=True)
    target.parent.mkdir(exist_ok=True)
    if mutation != "extra":
        source.write_text("Original resource.\n")
    if mutation != "missing":
        target.write_text("Changed resource.\n")

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked"
    key = {"missing": "missing_files", "drift": "drifted_files", "extra": "unexpected_files"}
    assert "risk-reviewer/references/example.md" in check.details[key[mutation]]


def test_parity_ignores_generated_python_cache(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    cache = sample_workspace / ".claude/skills/risk-reviewer/__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "generated.pyc").write_bytes(b"generated")

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "ok"


def test_parity_script_uses_shared_import_and_resource_checks(
    sample_workspace, repo_root, monkeypatch, capsys
):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    spec = importlib.util.spec_from_file_location(
        "check_agent_parity", repo_root / "scripts/check-agent-parity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", sample_workspace)
    assert module.main() == 0
    assert "agent-parity: ok" in capsys.readouterr().out
    (sample_workspace / "CLAUDE.md").write_text("@missing.md\n")
    assert module.main() == 1
    assert "claude_import" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mutation", ["write_format", "parallel_tests", "missing_feature_gate", "sync_environment"]
)
def test_make_verify_preserves_read_only_serial_release_checks(
    sample_workspace, repo_root, mutation
):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    path = sample_workspace / "Makefile"
    text = path.read_text()
    if mutation == "write_format":
        text = text.replace("ruff format --check", "ruff format")
    elif mutation == "parallel_tests":
        text = text.replace(
            "uv run --no-sync pytest --runslow", "uv run --no-sync pytest --runslow -n 2"
        )
    elif mutation == "missing_feature_gate":
        text = text.replace("deploy-prepare feature-validate readiness", "deploy-prepare readiness")
    else:
        text = text.replace("uv run --no-sync ruff format --check", "uv run ruff format --check")
    path.write_text(text)

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "makefile_verify")
    assert check.status == "blocked"


def test_repo_check_still_rejects_live_llm_clients_in_replay(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    path = sample_workspace / "open_composer/engines/backtest_engine.py"
    path.parent.mkdir(parents=True)
    path.write_text("import openai\n")

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "no_live_llm_backtest")
    assert check.status == "blocked"


def test_parity_keeps_paper_submission_in_guarded_permissions(sample_workspace, repo_root):
    _copy_repo_check_inputs(repo_root, sample_workspace)
    path = sample_workspace / ".claude/settings.json"
    settings = json.loads(path.read_text())
    rule = "Bash(uv run oc paper submit*)"
    settings["permissions"]["ask"].remove(rule)
    settings["permissions"]["allow"].append(rule)
    path.write_text(json.dumps(settings))

    report = build_repo_check_report(sample_workspace)

    check = next(item for item in report.checks if item.name == "claude_parity")
    assert check.status == "blocked"
    assert f"ask: {rule}" in check.details["missing_permissions"]
