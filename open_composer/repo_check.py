from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from open_composer.capabilities import load_registry
from open_composer.config import ensure_dir, project_root
from open_composer.models.dashboard_command import DashboardCommandAction
from open_composer.storage import write_json

RepoCheckStatus = Literal["ok", "warning", "blocked"]

NO_CONTEXT_START_DOC = "docs/product-golden-path-codex-quant-review-2026-05-13.zh.md"

CURRENT_DOCS = {
    NO_CONTEXT_START_DOC,
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
    "docs/harness-engineering-implementation-plan-2026-05-17.zh.md",
    "docs/harness-engineering-implementation-plan-v2-2026-05-17.zh.md",
    "docs/nasdaq-core-beta-satellite-router-standard-2026-05-20.zh.md",
    "docs/nasdaq-intraday-theme-momentum-router-standard-2026-05-20.zh.md",
    "docs/nasdaq-theme-intraday-rotation-router-standard-2026-05-20.zh.md",
    "docs/skill-first-harness-engineering-roadmap-2026-05-20.zh.md",
    "docs/llm-quant-epistemological-loop-roadmap-2026-05-21.zh.md",
    "docs/strategy-iteration-execution-architecture-plan-2026-05-22.zh.md",
}

REQUIRED_SKILLS = [
    "capability-evaluator",
    "nautilus-trader-adapter",
    "pine-exporter",
    "python-backtest-writer",
    "risk-reviewer",
    "signal-parity-reviewer",
    "strategy-designer",
    "strategy-researcher",
    "weekly-reviewer",
]

# Harness skills introduced by the skill-first harness foundation (P0-P2).
# These are checked in addition to REQUIRED_SKILLS to ensure the harness
# pack is mirrored to .claude/skills and contains expected anchors.
HARNESS_SKILLS = [
    "strategy-research-orchestrator",
    "source-researcher",
    "execution-reality-reviewer",
    "backtest-forensics",
    "paper-auto-safety-reviewer",
    "evidence-curator",
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

REQUIRED_DASHBOARD_ACTIONS = {
    "paper.status.refresh",
    "paper.monitor.refresh",
    "paper.sync.orders",
    "paper.sync.account",
    "paper.kill_switch.enable",
    "paper.kill_switch.clear",
    "system.prepare_workspace",
    "system.readiness.refresh",
    "strategy.draft",
    "strategy.workflow.verify",
    "strategy.validate",
    "strategy.capabilities.refresh",
    "strategy.approve",
    "strategy.activate.manual",
    "strategy.activate.paper_auto",
    "strategy.backtest.rerun",
    "strategy.scan.rerun",
    "strategy.disable",
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
        _dashboard_command_model_check(),
        _makefile_verify_check(base),
        _harness_policy_check(base),
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
    if not path.exists():
        return RepoConsistencyCheck(
            name="no_context_start_doc",
            status="blocked",
            message="No-context Codex starting review document is missing.",
            details={"path": NO_CONTEXT_START_DOC},
            suggested_actions=[f"Create {NO_CONTEXT_START_DOC}"],
        )
    text = path.read_text(encoding="utf-8")
    required = [
        "no-context Codex",
        "StrategySpec",
        "capabilities/registry.yaml",
        "uv run oc repo check",
        "make verify",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        return RepoConsistencyCheck(
            name="no_context_start_doc",
            status="blocked",
            message="No-context start document exists but is missing required anchors.",
            details={"path": NO_CONTEXT_START_DOC, "missing": missing},
            suggested_actions=[f"Update {NO_CONTEXT_START_DOC}"],
        )
    return RepoConsistencyCheck(
        name="no_context_start_doc",
        status="ok",
        message="No-context Codex starting review document is present.",
        details={"path": NO_CONTEXT_START_DOC},
    )


def _readme_project_docs_check(root: Path) -> RepoConsistencyCheck:
    path = root / "README.md"
    if not path.exists():
        return RepoConsistencyCheck(
            name="readme_project_docs",
            status="blocked",
            message="README.md is missing.",
            suggested_actions=["Restore README.md"],
        )
    text = path.read_text(encoding="utf-8")
    missing = []
    if "## Project Docs" not in text:
        missing.append("## Project Docs")
    if "docs/user-guide.md" not in text:
        missing.append("docs/user-guide.md")
    if NO_CONTEXT_START_DOC not in text:
        missing.append(NO_CONTEXT_START_DOC)
    if "no-context Codex" not in text:
        missing.append("no-context Codex")
    if missing:
        return RepoConsistencyCheck(
            name="readme_project_docs",
            status="blocked",
            message="README Project Docs does not mark the no-context Codex entry.",
            details={"missing": missing},
            suggested_actions=["Update README.md Project Docs"],
        )
    return RepoConsistencyCheck(
        name="readme_project_docs",
        status="ok",
        message="README Project Docs points to the no-context Codex entry.",
        details={"path": "README.md"},
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
    path = root / "AGENTS.md"
    required = [
        "StrategySpec",
        "capabilities/registry.yaml",
        "parameter ranges",
        "benchmark family",
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
        "Sample, fixture, cache fallback, and trial/research-only data",
        "visible_at",
        "untrusted reader input",
        "Real-money broker write access is out of scope",
        "Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest`",
    ]
    missing = _missing_text(path, required)
    if missing:
        return RepoConsistencyCheck(
            name="agents_rules",
            status="blocked",
            message="AGENTS.md is missing required product and safety rules.",
            details={"missing": missing},
            suggested_actions=["Update AGENTS.md"],
        )
    return RepoConsistencyCheck(
        name="agents_rules",
        status="ok",
        message="AGENTS.md carries the core product, workflow, safety, and verification rules.",
    )


def _current_product_docs_check(root: Path) -> RepoConsistencyCheck:
    docs = sorted(CURRENT_DOCS)
    missing_paths = [path for path in docs if not (root / path).exists()]
    if missing_paths:
        return RepoConsistencyCheck(
            name="current_product_docs",
            status="blocked",
            message="One or more current product governance documents are missing.",
            details={"missing": missing_paths},
            suggested_actions=["Restore current product docs"],
        )
    return RepoConsistencyCheck(
        name="current_product_docs",
        status="ok",
        message="Current product governance documents are present.",
        details={"docs": docs},
    )


def _docs_inventory_check(root: Path) -> RepoConsistencyCheck:
    docs_root = root / "docs"
    if not docs_root.exists():
        return RepoConsistencyCheck(
            name="docs_inventory",
            status="blocked",
            message="docs directory is missing.",
            suggested_actions=["Restore docs directory with current product documents"],
        )
    extra_docs = sorted(
        path.relative_to(root).as_posix()
        for path in docs_root.glob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in CURRENT_DOCS
    )
    if extra_docs:
        return RepoConsistencyCheck(
            name="docs_inventory",
            status="blocked",
            message="docs directory contains historical or non-current documents.",
            details={"extra_docs": extra_docs, "allowed_docs": sorted(CURRENT_DOCS)},
            suggested_actions=["Move historical docs out of docs/ or delete obsolete docs"],
        )
    return RepoConsistencyCheck(
        name="docs_inventory",
        status="ok",
        message="docs directory contains only current product documents.",
        details={"doc_count": len(CURRENT_DOCS), "docs": sorted(CURRENT_DOCS)},
    )


def _repo_skills_check(root: Path) -> RepoConsistencyCheck:
    missing = [
        skill
        for skill in REQUIRED_SKILLS
        if not (root / ".agents" / "skills" / skill / "SKILL.md").exists()
    ]
    required_anchors = {
        "capability-evaluator": ["provider timeframe support", "paper-ready market evidence"],
        "nautilus-trader-adapter": ["data manifest", "feature packet", "backend plan"],
        "python-backtest-writer": ["visible_at", "benchmark family", "trial count"],
        "risk-reviewer": ["workflow_pass", "paper_ready_pass", "LLM fallback"],
        "strategy-designer": ["notes.research_design", "parameter ranges", "benchmark family"],
        "strategy-researcher": ["parameter-sweep", "promotion-report", "llm_contribution_pass"],
        "weekly-reviewer": ["LLM contribution evidence", "paper readiness evidence"],
    }
    missing_anchors: dict[str, list[str]] = {}
    for skill, anchors in required_anchors.items():
        skill_path = root / ".agents" / "skills" / skill / "SKILL.md"
        if not skill_path.exists():
            continue
        text = skill_path.read_text(encoding="utf-8")
        missing_for_skill = [anchor for anchor in anchors if anchor not in text]
        if missing_for_skill:
            missing_anchors[skill] = missing_for_skill
    if missing:
        return RepoConsistencyCheck(
            name="repo_skills",
            status="blocked",
            message="Required repo skills are missing.",
            details={"missing": missing},
            suggested_actions=["Restore .agents/skills entries"],
        )
    if missing_anchors:
        return RepoConsistencyCheck(
            name="repo_skills",
            status="blocked",
            message="Required repo skills are missing research, strict-data, or gate anchors.",
            details={"missing_anchors": missing_anchors},
            suggested_actions=["Update .agents/skills/*/SKILL.md"],
        )
    return RepoConsistencyCheck(
        name="repo_skills",
        status="ok",
        message="Required repo skills are present and carry research gate anchors.",
        details={"skill_count": len(REQUIRED_SKILLS)},
    )


def _claude_parity_check(root: Path) -> RepoConsistencyCheck:
    required_paths = [
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/commands/repo-check.md",
        ".claude/commands/remote-doctor.md",
        ".claude/commands/verify.md",
        "scripts/sync-agent-skills.py",
        "scripts/check-agent-parity.py",
    ]
    missing_paths = [path for path in required_paths if not (root / path).exists()]
    missing_skills = [
        skill
        for skill in REQUIRED_SKILLS
        if not (root / ".claude" / "skills" / skill / "SKILL.md").exists()
    ]
    drifted_skills = []
    for skill in REQUIRED_SKILLS:
        source = root / ".agents" / "skills" / skill / "SKILL.md"
        target = root / ".claude" / "skills" / skill / "SKILL.md"
        if (
            source.exists()
            and target.exists()
            and source.read_text(encoding="utf-8") != target.read_text(encoding="utf-8")
        ):
            drifted_skills.append(skill)
    required_anchors = [
        "StrategySpec",
        "capabilities/registry.yaml",
        "parameter ranges",
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
        "Remote Dashboard commands",
    ]
    missing_anchors = _missing_text(root / "CLAUDE.md", required_anchors)
    problems = {
        "missing_paths": missing_paths,
        "missing_skills": missing_skills,
        "drifted_skills": drifted_skills,
        "missing_anchors": missing_anchors,
    }
    if any(problems.values()):
        return RepoConsistencyCheck(
            name="claude_parity",
            status="blocked",
            message="Claude Code parity artifacts are missing or drifted.",
            details=problems,
            suggested_actions=[
                "Run uv run python scripts/sync-agent-skills.py",
                "Run uv run python scripts/check-agent-parity.py",
            ],
        )
    return RepoConsistencyCheck(
        name="claude_parity",
        status="ok",
        message="Claude Code rules, commands, settings, and mirrored skills are present.",
        details={"skill_count": len(REQUIRED_SKILLS)},
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


def _dashboard_command_model_check() -> RepoConsistencyCheck:
    actions = _literal_strings(DashboardCommandAction)
    missing = sorted(REQUIRED_DASHBOARD_ACTIONS - actions)
    if missing:
        return RepoConsistencyCheck(
            name="dashboard_command_model",
            status="blocked",
            message="Dashboard command model is missing required controlled actions.",
            details={"missing": missing, "actions": sorted(actions)},
            suggested_actions=["Update open_composer/models/dashboard_command.py"],
        )
    return RepoConsistencyCheck(
        name="dashboard_command_model",
        status="ok",
        message="Dashboard command model exposes the controlled local action set.",
        details={"action_count": len(actions)},
    )


def _makefile_verify_check(root: Path) -> RepoConsistencyCheck:
    path = root / "Makefile"
    if not path.exists():
        return RepoConsistencyCheck(
            name="makefile_verify",
            status="blocked",
            message="Makefile is missing.",
            suggested_actions=["Restore Makefile"],
        )
    text = path.read_text(encoding="utf-8")
    missing = []
    if "repo-check:" not in text:
        missing.append("repo-check target")
    if "capability-test:" not in text:
        missing.append("capability-test target")
    if "agent-parity:" not in text:
        missing.append("agent-parity target")
    if "uv run oc repo check --strict" not in text:
        missing.append("repo-check runs strict")
    if "uv run oc readiness --strict" not in text:
        missing.append("readiness runs strict")
    if "uv run oc deploy prepare --strict" not in text:
        missing.append("deploy-prepare runs strict")
    if "uv run oc feature validate --strict" not in text:
        missing.append("feature-validate runs strict")
    if not re.search(r"^verify:.*\brepo-check\b", text, re.MULTILINE):
        missing.append("verify depends on repo-check")
    if not re.search(r"^verify:.*\bcapability-test\b", text, re.MULTILINE):
        missing.append("verify depends on capability-test")
    if not re.search(r"^verify:.*\bagent-parity\b", text, re.MULTILINE):
        missing.append("verify depends on agent-parity")
    if not re.search(r"^verify:.*\bdeploy-prepare\b", text, re.MULTILINE):
        missing.append("verify depends on deploy-prepare")
    if not re.search(r"^verify:.*\breadiness\b", text, re.MULTILINE):
        missing.append("verify depends on readiness")
    if missing:
        return RepoConsistencyCheck(
            name="makefile_verify",
            status="blocked",
            message="Makefile verify target does not include the full local closure checks.",
            details={"missing": missing},
            suggested_actions=[
                "Add repo-check, capability-test, deploy-prepare, dashboard-check, "
                "feature-validate, and readiness to make verify"
            ],
        )
    return RepoConsistencyCheck(
        name="makefile_verify",
        status="ok",
        message=(
            "make verify includes repository, capability, deployment, dashboard, feature, "
            "and readiness checks."
        ),
    )


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

    skill_dirs = {p.name for p in (root / ".agents" / "skills").iterdir() if p.is_dir()}
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


def _missing_text(path: Path, required: list[str]) -> list[str]:
    if not path.exists():
        return [str(path)]
    text = path.read_text(encoding="utf-8")
    return [item for item in required if item not in text]


def _literal_strings(annotation: object) -> set[str]:
    origin = get_origin(annotation)
    if origin is Literal:
        return {str(item) for item in get_args(annotation)}
    values: set[str] = set()
    for arg in get_args(annotation):
        values.update(_literal_strings(arg))
    return values


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
