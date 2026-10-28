from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.capabilities import load_registry
from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

RepoCheckStatus = Literal["ok", "warning", "blocked"]

NO_CONTEXT_START_DOC = "research/README.md"

# These are required entry points, not a closed inventory of project history.
CURRENT_DOCS = {
    NO_CONTEXT_START_DOC,
    "docs/rules.md",
    "docs/research-mission.zh.md",
    "docs/research-plan-review-standard.zh.md",
    "docs/owner-reporting.zh.md",
    "docs/user-guide.md",
    "docs/archive/owner-rules-register-20261028.zh.md",
}

REQUIRED_ENTRY_FILES = CURRENT_DOCS | {
    "AGENTS.md",
    "CLAUDE.md",
    "control.json",
    "board.md",
    "research/workflow.json",
    "research/schemas/reply.schema.json",
    "research/schemas/results.schema.json",
    "research/templates/brief.md",
    "research/templates/decisions.tsv",
    "prompts/lead.md",
    "prompts/worker.md",
    "prompts/reviewer.md",
}

REQUIRED_SKILLS = [
    "capability-evaluator",
    "idea-to-paper",
    "nautilus-trader-adapter",
    "python-backtest-writer",
    "research-plan-reviewer",
    "risk-reviewer",
    "strategy-designer",
    "windows-paseo-worker",
]

HARNESS_SKILLS = [
    "strategy-research-orchestrator",
    "source-researcher",
    "execution-reality-reviewer",
    "backtest-forensics",
    "data-capability-reviewer",
    "paper-auto-safety-reviewer",
]

REQUIRED_CAPABILITIES = {
    "market.sample_ohlcv",
    "market.alpaca_bars",
    "market.longbridge_bars",
    "events.sec_filings",
    "macro.fred_series",
    "news.alpha_vantage",
    "news.gdelt",
    "options.trial_chain",
}


class RepoConsistencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: RepoCheckStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)


class RepoConsistencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: RepoCheckStatus
    ready: bool
    checks: list[RepoConsistencyCheck]
    report_json_path: str | None = None
    report_markdown_path: str | None = None


def build_repo_check_report(root: Path | None = None) -> RepoConsistencyReport:
    base = root or project_root()
    checks = [
        _license_check(base),
        _no_context_start_doc_check(base),
        _readme_project_docs_check(base),
        _readme_research_controls_check(base),
        _agents_rules_check(base),
        _current_product_docs_check(base),
        _docs_inventory_check(base),
        _claude_parity_check(base),
        _repo_skills_check(base),
        _capability_registry_check(base),
        _no_live_llm_backtest_check(base),
        _makefile_verify_check(base),
        _harness_policy_check(base),
        _evaluation_standard_changelog_check(base),
    ]
    status = _overall_status(checks)
    return RepoConsistencyReport(
        status=status,
        ready=status != "blocked",
        checks=checks,
    )


def write_repo_check_report(
    report: RepoConsistencyReport,
    root: Path | None = None,
    output_path: Path | None = None,
) -> tuple[Path, Path]:
    base = root or project_root()
    json_path = output_path or base / "reports" / "repo" / "repo-check.json"
    md_path = json_path.with_suffix(".md")
    report.report_json_path = str(json_path)
    report.report_markdown_path = str(md_path)
    write_json(json_path, report)
    ensure_dir(md_path.parent)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _license_check(root: Path) -> RepoConsistencyCheck:
    path = root / "LICENSE"
    if not path.exists():
        return RepoConsistencyCheck(
            name="license",
            status="blocked",
            message="LICENSE file is missing.",
            suggested_actions=["Add an explicit project license file"],
        )
    text = path.read_text(encoding="utf-8")
    missing = [item for item in ["MIT License", "Permission is hereby granted"] if item not in text]
    if missing:
        return RepoConsistencyCheck(
            name="license",
            status="blocked",
            message="LICENSE exists but does not look like the expected MIT license.",
            details={"missing": missing},
            suggested_actions=["Update LICENSE"],
        )
    return RepoConsistencyCheck(
        name="license",
        status="ok",
        message="MIT license file is present.",
        details={"path": "LICENSE"},
    )


def _no_context_start_doc_check(root: Path) -> RepoConsistencyCheck:
    path = root / NO_CONTEXT_START_DOC
    required = ["scripts/research_round.py", "control.json", "brief.md", "results.json"]
    missing = _missing_text(path, required)
    return RepoConsistencyCheck(
        name="no_context_start_doc",
        status="blocked" if missing else "ok",
        message=(
            "Research starting document is missing required workflow entry points."
            if missing
            else "Research starting document describes the current file workflow."
        ),
        details={"path": NO_CONTEXT_START_DOC, "missing": missing},
        suggested_actions=[f"Update {NO_CONTEXT_START_DOC}"] if missing else [],
    )


def _readme_project_docs_check(root: Path) -> RepoConsistencyCheck:
    missing = _missing_text(root / "README.md", [NO_CONTEXT_START_DOC, "docs/user-guide.md"])
    return RepoConsistencyCheck(
        name="readme_project_docs",
        status="blocked" if missing else "ok",
        message=(
            "README Project Docs is missing the current research or user entry."
            if missing
            else "README links the current research and user entry points."
        ),
        details={"missing": missing},
        suggested_actions=["Update README.md entry links"] if missing else [],
    )


def _readme_research_controls_check(root: Path) -> RepoConsistencyCheck:
    path = root / "docs" / "user-guide.md"
    required = [
        "uv run oc strategy parameter-sweep",
        "uv run oc strategy exposure-switch",
        "uv run oc strategy llm-exposure-switch",
        "uv run oc strategy rotate-universe",
        "uv run oc strategy market-time",
        "--walk-forward-top-k",
        "research_cost",
        "runtime_seconds",
        "data_profile",
        "estimated backtest passes",
        "Dashboard research records",
        "research_brief",
        "search_space",
        "hypothesis_ledger",
        "llm_contribution",
        "llm_contribution_ok",
        "llm_contribution_level",
        "strategy_distinctiveness_ok",
        "llm_assisted_selection_only",
        "prompt artifact",
        "acceptance gate stays failed",
        "--local-choice-label",
        "codex_local_choice",
    ]
    missing = _missing_text(path, required)
    if missing:
        return RepoConsistencyCheck(
            name="readme_research_controls",
            status="blocked",
            message=(
                "User guide is missing Codex-facing research cost, data, hypothesis, "
                "or LLM controls."
            ),
            details={"missing": missing},
            suggested_actions=["Update docs/user-guide.md Bounded Research"],
        )
    return RepoConsistencyCheck(
        name="readme_research_controls",
        status="ok",
        message=(
            "User guide documents research cost, data freshness, hypothesis, "
            "and LLM fallback gates."
        ),
    )


def _agents_rules_check(root: Path) -> RepoConsistencyCheck:
    required = ["docs/rules.md", "control.json", "research/workflow.json"]
    missing = _missing_text(root / "AGENTS.md", required)
    return RepoConsistencyCheck(
        name="agents_rules",
        status="blocked" if missing else "ok",
        message=(
            "AGENTS.md must point to the shared rules, authority index and role bindings."
            if missing
            else "AGENTS.md points to the shared instruction and authority entries."
        ),
        details={"missing": missing},
        suggested_actions=["Restore shared entry references in AGENTS.md"] if missing else [],
    )


def _current_product_docs_check(root: Path) -> RepoConsistencyCheck:
    missing = sorted(
        name
        for name in REQUIRED_ENTRY_FILES
        if not (root / name).is_file() or not (root / name).stat().st_size
    )
    invalid: dict[str, str] = {}
    for name in (
        "control.json",
        "research/workflow.json",
        "research/schemas/reply.schema.json",
        "research/schemas/results.schema.json",
    ):
        if name in missing:
            continue
        try:
            data = json.loads((root / name).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("must contain a JSON object")
            if name == "control.json":
                for switch in ("draft", "research", "ab_research"):
                    if not isinstance(data.get(switch), bool):
                        raise ValueError(f"{switch} must be an explicit boolean")
            elif name == "research/workflow.json":
                roles = data.get("roles")
                if not isinstance(roles, dict):
                    raise ValueError("roles must contain lead, worker and reviewer bindings")
                for role_name in ("lead", "worker", "reviewer"):
                    role = roles.get(role_name)
                    if not isinstance(role, dict) or any(
                        not isinstance(role.get(key), str) or not role[key].strip()
                        for key in ("provider", "model", "effort", "prompt")
                    ):
                        raise ValueError(f"{role_name} needs provider/model/effort/prompt")
                    prompt = _repository_file(root, role["prompt"])
                    if prompt is None or not prompt.stat().st_size:
                        raise ValueError(f"{role_name} prompt must be a repository file")
            elif data.get("type") != "object":
                raise ValueError("schema must describe an object")
        except (OSError, ValueError) as exc:
            invalid[name] = str(exc)
    blocked = bool(missing or invalid)
    return RepoConsistencyCheck(
        name="current_product_docs",
        status="blocked" if blocked else "ok",
        message=(
            "Required current entry files are missing or invalid."
            if blocked
            else "Current instruction, authority and research entry files are present."
        ),
        details={"missing": missing, "invalid": invalid},
        suggested_actions=["Restore the current entry files and JSON structure"] if blocked else [],
    )


def _docs_inventory_check(root: Path) -> RepoConsistencyCheck:
    docs_root = root / "docs"
    return RepoConsistencyCheck(
        name="docs_inventory",
        status="ok" if docs_root.is_dir() else "blocked",
        message=(
            "Project docs and history may coexist; only current entry files are required."
            if docs_root.is_dir()
            else "docs directory is missing."
        ),
        details={"required_docs": sorted(CURRENT_DOCS)},
    )


def _repo_skills_check(root: Path) -> RepoConsistencyCheck:
    skills = _agent_skill_dirs(root)
    missing = sorted((set(REQUIRED_SKILLS) | set(HARNESS_SKILLS)) - skills)
    metadata_errors = {}
    for skill in sorted(skills):
        path = root / ".agents/skills" / skill / "SKILL.md"
        metadata = _skill_metadata(path)
        if (
            metadata.get("name") != skill
            or not isinstance(metadata.get("description"), str)
            or not metadata["description"].strip()
        ):
            metadata_errors[skill] = "SKILL.md needs matching name and non-empty description"
    blocked = bool(missing or metadata_errors)
    return RepoConsistencyCheck(
        name="repo_skills",
        status="blocked" if blocked else "ok",
        message=(
            "Current skills are missing or have invalid metadata."
            if blocked
            else "Current canonical skills have valid discovery metadata."
        ),
        details={
            "missing": missing,
            "metadata_errors": metadata_errors,
            "skill_count": len(skills),
        },
        suggested_actions=["Restore current skills and valid SKILL.md frontmatter"]
        if blocked
        else [],
    )


def _skill_tree_files(path: Path) -> dict[str, bytes]:
    return {
        file.relative_to(path).as_posix(): file.read_bytes()
        for file in path.rglob("*")
        if file.is_file()
        and "__pycache__" not in file.relative_to(path).parts
        and file.suffix != ".pyc"
    }


def agent_parity_problems(root: Path) -> dict[str, object]:
    """Shared checks for the CLI report and the standalone parity command."""
    required_paths = [
        "AGENTS.md",
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/commands/repo-check.md",
        ".claude/commands/verify.md",
        "scripts/sync-agent-skills.py",
        "scripts/check-agent-parity.py",
        ".agents/skills",
        ".claude/skills",
    ]
    problems: dict[str, object] = {
        "missing_paths": [path for path in required_paths if not (root / path).exists()]
    }
    claude = root / "CLAUDE.md"
    if claude.is_file():
        text = re.sub(r"<!--.*?-->", "", claude.read_text(encoding="utf-8"), flags=re.DOTALL)
        directives = [
            line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
        ]
        if directives != ["@AGENTS.md"]:
            problems["claude_import"] = (
                "CLAUDE.md must import @AGENTS.md without a second rules body"
            )
    settings = root / ".claude/settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            permissions = data.get("permissions") if isinstance(data, dict) else None
            if not isinstance(permissions, dict):
                raise ValueError("permissions must be an object")
            if any(
                not isinstance(permissions.get(group), list)
                or any(not isinstance(rule, str) for rule in permissions[group])
                for group in ("allow", "ask", "deny")
            ):
                raise ValueError("allow, ask and deny must be lists of permission rules")
            required = {
                "allow": "Bash(uv run oc *)",
                "ask": "Bash(uv run oc paper submit*)",
                "deny": "Bash(git reset --hard*)",
            }
            missing_permissions = [
                f"{group}: {anchor}"
                for group, anchor in required.items()
                if anchor not in permissions.get(group, [])
            ]
            if "Read(.env)" not in permissions.get("deny", []):
                missing_permissions.append("deny: Read(.env)")
            if missing_permissions:
                problems["missing_permissions"] = missing_permissions
        except (OSError, ValueError) as exc:
            problems["settings"] = str(exc)
    source_root, target_root = root / ".agents/skills", root / ".claude/skills"
    source_skills = _agent_skill_dirs(root)
    target_skills = _skill_dirs(target_root)
    problems["missing_skills"] = sorted(source_skills - target_skills)
    problems["unexpected_skills"] = sorted(target_skills - source_skills)
    drifted_files = []
    missing_files = []
    unexpected_files = []
    for skill in sorted(source_skills & target_skills):
        source_files = _skill_tree_files(source_root / skill)
        target_files = _skill_tree_files(target_root / skill)
        missing_files.extend(
            f"{skill}/{name}" for name in source_files.keys() - target_files.keys()
        )
        unexpected_files.extend(
            f"{skill}/{name}" for name in target_files.keys() - source_files.keys()
        )
        drifted_files.extend(
            f"{skill}/{name}"
            for name in source_files.keys() & target_files.keys()
            if source_files[name] != target_files[name]
        )
        if "SKILL.md" not in source_files:
            missing_files.append(f"{skill}/SKILL.md (canonical)")
    problems["missing_files"] = sorted(missing_files)
    problems["unexpected_files"] = sorted(unexpected_files)
    problems["drifted_files"] = sorted(drifted_files)
    return {name: value for name, value in problems.items() if value}


def _claude_parity_check(root: Path) -> RepoConsistencyCheck:
    problems = agent_parity_problems(root)
    return RepoConsistencyCheck(
        name="claude_parity",
        status="blocked" if problems else "ok",
        message=(
            "Claude shared instructions, permissions or skill mirrors are missing or drifted."
            if problems
            else "Claude imports the shared instructions and mirrors all skill resources."
        ),
        details=problems,
        suggested_actions=[
            "Inspect mirror-only changes before running scripts/sync-agent-skills.py",
            "Run scripts/check-agent-parity.py",
        ]
        if problems
        else [],
    )


def _capability_registry_check(root: Path) -> RepoConsistencyCheck:
    try:
        registry = load_registry(root)
    except Exception as exc:
        return RepoConsistencyCheck(
            name="capability_registry",
            status="blocked",
            message=f"Capability registry could not be loaded: {exc}",
            suggested_actions=["Fix capabilities/registry.yaml"],
        )

    ids = [capability.id for capability in registry.capabilities]
    duplicate_ids = sorted({capability_id for capability_id in ids if ids.count(capability_id) > 1})
    missing_required = sorted(REQUIRED_CAPABILITIES - set(ids))
    missing_fixtures = sorted(
        capability.id
        for capability in registry.capabilities
        if capability.fixture and not (root / capability.fixture).exists()
    )
    missing_timeframe_matrix = sorted(
        capability.id
        for capability in registry.capabilities
        if capability.kind == "market" and not getattr(capability, "supported_timeframes", None)
    )
    problems = {
        "duplicates": duplicate_ids,
        "missing_required": missing_required,
        "missing_fixtures": missing_fixtures,
        "missing_timeframe_matrix": missing_timeframe_matrix,
    }
    if any(problems.values()):
        return RepoConsistencyCheck(
            name="capability_registry",
            status="blocked",
            message=(
                "Capability registry has missing ids, duplicate ids, missing fixtures, "
                "or market capabilities without timeframe support."
            ),
            details=problems,
            suggested_actions=["Update capabilities/registry.yaml and capability fixtures"],
        )
    status_counts: dict[str, int] = {}
    for capability in registry.capabilities:
        status_counts[capability.status] = status_counts.get(capability.status, 0) + 1
    return RepoConsistencyCheck(
        name="capability_registry",
        status="ok",
        message="Capability registry loads and core data/event/macro/news/options ids are present.",
        details={"capability_count": len(ids), "status_counts": status_counts},
    )


def _no_live_llm_backtest_check(root: Path) -> RepoConsistencyCheck:
    paths = [
        root / "open_composer" / "expressions.py",
        root / "open_composer" / "engines" / "backtest_engine.py",
        root / "open_composer" / "adapters" / "execution" / "nautilus_runtime.py",
    ]
    offenders: list[str] = []
    patterns = ("import openai", "from openai", "import anthropic", "from anthropic")
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in patterns):
            offenders.append(path.relative_to(root).as_posix())
    if offenders:
        return RepoConsistencyCheck(
            name="no_live_llm_backtest",
            status="blocked",
            message="Backtest/replay paths must not import live LLM clients.",
            details={"offenders": offenders},
            suggested_actions=[
                "Move LLM calls to research/llm_materialize.py and replay packets in backtests"
            ],
        )
    return RepoConsistencyCheck(
        name="no_live_llm_backtest",
        status="ok",
        message="Backtest/replay paths do not import live LLM clients.",
    )


def _makefile_verify_check(root: Path) -> RepoConsistencyCheck:
    path = root / "Makefile"
    if not path.is_file():
        return RepoConsistencyCheck(
            name="makefile_verify", status="blocked", message="Makefile is missing."
        )
    text = path.read_text(encoding="utf-8")
    missing = []
    for target, command in {
        "repo-check": "uv run --no-sync oc repo check --strict",
        "capability-test": "uv run --no-sync oc capability test",
        "agent-parity": "scripts/check-agent-parity.py",
        "deploy-prepare": "uv run --no-sync oc deploy prepare --strict",
        "feature-validate": "uv run --no-sync oc feature validate --strict",
        "readiness": "uv run --no-sync oc readiness --strict",
    }.items():
        _, recipe = _makefile_target(text, target)
        if command not in "\n".join(recipe):
            missing.append(
                f"{target} runs strict" if "--strict" in command else f"{target} command"
            )
    dependencies, _ = _makefile_target(text, "verify")
    for target in (
        "format-check",
        "lint",
        "test-full",
        "repo-check",
        "capability-test",
        "agent-parity",
        "deploy-prepare",
        "feature-validate",
        "readiness",
    ):
        if target not in dependencies:
            missing.append(f"verify depends on {target}")
    if "format" in dependencies:
        missing.append("verify must not run the modifying format target")
    for target in dependencies:
        _, recipe = _makefile_target(text, target)
        command = "\n".join(recipe)
        if re.search(r"\buv\s+run(?!\s+--no-sync\b)", command) or re.search(
            r"\buv\s+sync\b", command
        ):
            missing.append(f"{target} must not sync the live Python environment")
    _, format_recipe = _makefile_target(text, "format-check")
    if "ruff format --check $(MAINTAINED_PYTHON)" not in "\n".join(format_recipe):
        missing.append("format-check validates maintained code without writes")
    maintained = re.search(r"(?m)^MAINTAINED_PYTHON\s*:?=\s*(.+)$", text)
    paths = maintained.group(1).split() if maintained else []
    if not {"open_composer", "scripts", "tests"}.issubset(paths) or any(
        name in {".", "reports", "data", "drafts"} or name.startswith("reports/") for name in paths
    ):
        missing.append("format scope includes maintained code and excludes frozen evidence")
    for target in ("test", "test-fast", "test-full"):
        _, recipe = _makefile_target(text, target)
        command = "\n".join(recipe)
        if "pytest" not in command or re.search(r"(?:^|\s)-n(?:\s|=|[0-9])", command):
            missing.append(f"{target} uses one pytest process")
    if not re.search(r"(?m)^\.NOTPARALLEL:\s*$", text):
        missing.append("release recipes run serially")
    return RepoConsistencyCheck(
        name="makefile_verify",
        status="blocked" if missing else "ok",
        message=(
            "Makefile verify is missing read-only or release checks."
            if missing
            else "make verify validates code read-only and retains serial release checks."
        ),
        details={"missing": missing},
        suggested_actions=["Restore the read-only format and full strict release checks"]
        if missing
        else [],
    )


def _makefile_target(text: str, target: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{target}:"):
            dependencies = line.partition(":")[2].split("#", 1)[0].split()
            recipe = []
            for following in lines[index + 1 :]:
                if following.startswith("\t"):
                    recipe.append(following.strip())
                elif following.strip() and not following.startswith("#"):
                    break
            return dependencies, recipe
    return [], []


def _harness_policy_check(root: Path) -> RepoConsistencyCheck:
    """Validate that harness/*.yaml exists, parses, and references real skills/contracts."""
    import yaml

    harness_dir = root / "harness"
    required_files = [
        "risk_domains.yaml",
        "artifact_contracts.yaml",
        "source_policy.yaml",
        "skill_manifest.yaml",
    ]
    missing_files = [f for f in required_files if not (harness_dir / f).exists()]
    if missing_files:
        return RepoConsistencyCheck(
            name="harness_policy",
            status="blocked",
            message="Harness policy YAML files are missing.",
            details={"missing": missing_files},
            suggested_actions=[f"Create harness/{name}" for name in missing_files],
        )

    parse_errors: dict[str, str] = {}
    parsed: dict[str, object] = {}
    for name in required_files:
        try:
            parsed[name] = yaml.safe_load((harness_dir / name).read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            parse_errors[name] = str(exc)
    if parse_errors:
        return RepoConsistencyCheck(
            name="harness_policy",
            status="blocked",
            message="Harness policy YAML files contain parse errors.",
            details={"errors": parse_errors},
        )

    contracts_doc = parsed.get("artifact_contracts.yaml") or {}
    contract_names = set((contracts_doc.get("artifacts") or {}).keys())  # type: ignore[union-attr]

    domains_doc = parsed.get("risk_domains.yaml") or {}
    domains_map = (domains_doc.get("risk_domains") or {}) if isinstance(domains_doc, dict) else {}
    referenced_skills: set[str] = set()
    referenced_artifacts: set[str] = set()
    for domain_raw in domains_map.values():
        if not isinstance(domain_raw, dict):
            continue
        for skill in domain_raw.get("required_skills") or []:
            referenced_skills.add(skill)
        for artifact in domain_raw.get("required_artifacts") or []:
            referenced_artifacts.add(artifact)

    skill_dirs = _agent_skill_dirs(root)
    manifest_doc = parsed.get("skill_manifest.yaml") or {}
    manifest_problems = _validate_skill_manifest(
        root,
        manifest_doc,
        skill_dirs=skill_dirs,
        required_skills=referenced_skills,
    )
    if manifest_problems:
        return RepoConsistencyCheck(
            name="harness_policy",
            status="blocked",
            message=(
                "Skill manifest references missing or inconsistent skill, hook, or agent files."
            ),
            details=manifest_problems,
            suggested_actions=["Update harness/skill_manifest.yaml or restore referenced files"],
        )

    missing_skills = sorted(referenced_skills - skill_dirs)
    missing_contracts = sorted(referenced_artifacts - contract_names)

    if missing_skills or missing_contracts:
        return RepoConsistencyCheck(
            name="harness_policy",
            status="blocked",
            message=("Risk domains reference skills or artifact contracts that do not exist."),
            details={
                "missing_skills": missing_skills,
                "missing_artifact_contracts": missing_contracts,
            },
        )

    missing_claude_mirrors = [
        skill
        for skill in HARNESS_SKILLS
        if not (root / ".claude" / "skills" / skill / "SKILL.md").exists()
    ]
    if missing_claude_mirrors:
        return RepoConsistencyCheck(
            name="harness_policy",
            status="warning",
            message="Harness skills are missing from .claude/skills mirror.",
            details={"missing_claude_mirrors": missing_claude_mirrors},
            suggested_actions=["uv run python scripts/sync-agent-skills.py"],
        )

    return RepoConsistencyCheck(
        name="harness_policy",
        status="ok",
        message=(
            f"Harness policy ok: {len(domains_map)} risk domains, "
            f"{len(contract_names)} artifact contracts, "
            f"{len(referenced_skills)} skills referenced."
        ),
        details={
            "risk_domain_count": len(domains_map),
            "artifact_contract_count": len(contract_names),
        },
    )


def _skill_dirs(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {
        entry.name
        for entry in path.iterdir()
        if entry.is_dir() and entry.name != "__pycache__" and not entry.name.startswith(".")
    }


def _agent_skill_dirs(root: Path) -> set[str]:
    return _skill_dirs(root / ".agents/skills")


def _repository_file(root: Path, name: str) -> Path | None:
    path = (root / name).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


def _validate_skill_manifest(
    root: Path,
    manifest_doc: object,
    skill_dirs: set[str] | None = None,
    required_skills: set[str] | None = None,
) -> dict[str, object]:
    if not isinstance(manifest_doc, dict):
        return {"manifest": "skill_manifest.yaml must parse as a mapping"}
    skill_dirs = skill_dirs if skill_dirs is not None else _agent_skill_dirs(root)
    problems: dict[str, object] = {}

    skills = manifest_doc.get("skills") or {}
    if not isinstance(skills, dict):
        problems["skills"] = "skills must be a mapping"
    else:
        missing_paths: list[str] = []
        missing_names: dict[str, str] = {}
        name_mismatches: dict[str, str] = {}
        manifest_skill_names = {str(name) for name in skills.keys()}
        for skill_name, raw in skills.items():
            if not isinstance(raw, dict):
                missing_paths.append(str(skill_name))
                continue
            raw_path = str(raw.get("skill_path") or "")
            if not raw_path:
                missing_paths.append(str(skill_name))
                continue
            path = _repository_file(root, raw_path)
            if path is None or raw_path != f".agents/skills/{skill_name}/SKILL.md":
                missing_paths.append(raw_path)
                continue
            frontmatter_name = _skill_frontmatter_name(path)
            if frontmatter_name is None:
                missing_names[str(skill_name)] = raw_path
            elif frontmatter_name != skill_name:
                name_mismatches[str(skill_name)] = frontmatter_name
        unmanifested_skills = sorted(skill_dirs - manifest_skill_names)
        unmanifested_required_skills = sorted((required_skills or set()) - manifest_skill_names)
        if missing_paths:
            problems["missing_skill_paths"] = sorted(missing_paths)
        if missing_names:
            problems["missing_skill_frontmatter_name"] = missing_names
        if name_mismatches:
            problems["skill_name_mismatches"] = name_mismatches
        if unmanifested_skills:
            problems["unmanifested_skills"] = unmanifested_skills
        if unmanifested_required_skills:
            problems["unmanifested_required_skills"] = unmanifested_required_skills

    hooks = manifest_doc.get("hooks") or {}
    if not isinstance(hooks, dict):
        problems["hooks"] = "hooks must be a mapping"
    else:
        missing_hook_paths = sorted(
            str(raw.get("path") or hook_name)
            for hook_name, raw in hooks.items()
            if not isinstance(raw, dict)
            or not raw.get("path")
            or _repository_file(root, str(raw.get("path"))) is None
        )
        if missing_hook_paths:
            problems["missing_hook_paths"] = missing_hook_paths

    agents = manifest_doc.get("agents") or {}
    if not isinstance(agents, dict):
        problems["agents"] = "agents must be a mapping"
    else:
        missing_agent_paths: list[str] = []
        unknown_agent_skills: dict[str, list[str]] = {}
        for agent_name, raw in agents.items():
            if not isinstance(raw, dict):
                missing_agent_paths.append(str(agent_name))
                continue
            raw_path = str(raw.get("path") or "")
            if not raw_path or _repository_file(root, raw_path) is None:
                missing_agent_paths.append(raw_path or str(agent_name))
            used = raw.get("skills_used") or []
            if not isinstance(used, list):
                unknown_agent_skills[str(agent_name)] = ["(skills_used must be a list)"]
                continue
            unknown = sorted(str(skill) for skill in used if str(skill) not in skill_dirs)
            if unknown:
                unknown_agent_skills[str(agent_name)] = unknown
        if missing_agent_paths:
            problems["missing_agent_paths"] = sorted(missing_agent_paths)
        if unknown_agent_skills:
            problems["unknown_agent_skills"] = unknown_agent_skills

    return problems


def _skill_metadata(path: Path) -> dict[str, object]:
    import yaml

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "---":
            return {}
        end = lines.index("---", 1)
        metadata = yaml.safe_load("\n".join(lines[1:end]))
        return metadata if isinstance(metadata, dict) else {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def _skill_frontmatter_name(path: Path) -> str | None:
    name = _skill_metadata(path).get("name")
    return name if isinstance(name, str) else None


def _missing_text(path: Path, required: list[str]) -> list[str]:
    if not path.exists():
        return [str(path)]
    text = path.read_text(encoding="utf-8")
    return [item for item in required if item not in text]


def _overall_status(checks: list[RepoConsistencyCheck]) -> RepoCheckStatus:
    if any(check.status == "blocked" for check in checks):
        return "blocked"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "ok"


def _render_markdown(report: RepoConsistencyReport) -> str:
    lines = [
        "# Open Composer Repository Check",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: `{report.status}`",
        f"- Ready: `{'yes' if report.ready else 'no'}`",
        "",
        "| Check | Status | Message |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(f"| {check.name} | {check.status} | {check.message} |")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for check in report.checks:
        lines.append(f"### {check.name}")
        lines.append(f"- Status: `{check.status}`")
        lines.append(f"- Message: {check.message}")
        if check.details:
            lines.append(f"- Details: `{json.dumps(check.details, sort_keys=True)}`")
        if check.suggested_actions:
            lines.append("- Suggested actions:")
            for action in check.suggested_actions:
                lines.append(f"  - `{action}`")
        lines.append("")
    return "\n".join(lines)


def _evaluation_standard_changelog_check(root: Path) -> RepoConsistencyCheck:
    """Every state of the evaluation standard needs a signed changelog entry."""
    from open_composer.research.gate_additions import evaluation_standard_status

    status = evaluation_standard_status(root)
    if not status.get("present"):
        return RepoConsistencyCheck(
            name="evaluation_standard_changelog",
            status="ok",
            message="No evaluation standard file in this workspace; nothing to log.",
        )
    if status["invalid_entries"] or not status["covered"]:
        return RepoConsistencyCheck(
            name="evaluation_standard_changelog",
            status="blocked",
            message="config/evaluation-standard-v2.json has no valid changelog entry for its "
            "current sha256.",
            details={
                "sha256": status["sha256"],
                "entries": status["entries"],
                "invalid_entries": status["invalid_entries"],
            },
            suggested_actions=[
                "Append a line to config/evaluation-standard-changelog.jsonl with the new "
                "sha256, date, changed_by, reason and signed_by (lead-round signature)"
            ],
        )
    return RepoConsistencyCheck(
        name="evaluation_standard_changelog",
        status="ok",
        message="Evaluation standard hash is covered by the changelog.",
        details={"sha256": status["sha256"], "entries": status["entries"]},
    )
