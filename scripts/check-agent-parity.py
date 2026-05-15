from __future__ import annotations

import filecmp
import json
from pathlib import Path

REQUIRED_CLAUDE_ANCHORS = [
    "StrategySpec",
    "capabilities/registry.yaml",
    "parameter ranges",
    "workflow_pass",
    "research_pass",
    "llm_contribution_pass",
    "paper_ready_pass",
    "Remote Dashboard commands",
    "uv run oc repo check --strict",
]

REQUIRED_COMMANDS = [
    "repo-check.md",
    "remote-doctor.md",
    "verify.md",
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems: list[str] = []
    problems.extend(_check_claude_doc(root))
    problems.extend(_check_settings(root))
    problems.extend(_check_commands(root))
    problems.extend(_check_skill_mirror(root))
    if problems:
        for problem in problems:
            print(f"agent-parity: {problem}")
        return 1
    print("agent-parity: ok")
    return 0


def _check_claude_doc(root: Path) -> list[str]:
    path = root / "CLAUDE.md"
    if not path.exists():
        return ["CLAUDE.md is missing"]
    text = path.read_text(encoding="utf-8")
    return [
        f"CLAUDE.md missing anchor: {anchor}"
        for anchor in REQUIRED_CLAUDE_ANCHORS
        if anchor not in text
    ]


def _check_settings(root: Path) -> list[str]:
    path = root / ".claude" / "settings.json"
    if not path.exists():
        return [".claude/settings.json is missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f".claude/settings.json is invalid JSON: {exc}"]
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        return [".claude/settings.json missing permissions object"]
    required_text = json.dumps(permissions, sort_keys=True)
    missing = [
        anchor
        for anchor in [
            "uv run oc *",
            "uv run oc dashboard command-run*",
            "git reset --hard*",
            "Read(.env)",
        ]
        if anchor not in required_text
    ]
    return [f".claude/settings.json missing permission anchor: {anchor}" for anchor in missing]


def _check_commands(root: Path) -> list[str]:
    command_root = root / ".claude" / "commands"
    problems = []
    for filename in REQUIRED_COMMANDS:
        if not (command_root / filename).exists():
            problems.append(f".claude/commands/{filename} is missing")
    return problems


def _check_skill_mirror(root: Path) -> list[str]:
    source_root = root / ".agents" / "skills"
    target_root = root / ".claude" / "skills"
    if not source_root.exists():
        return [".agents/skills is missing"]
    if not target_root.exists():
        return [".claude/skills is missing; run scripts/sync-agent-skills.py"]
    problems: list[str] = []
    source_skills = sorted(path.name for path in source_root.iterdir() if path.is_dir())
    target_skills = sorted(path.name for path in target_root.iterdir() if path.is_dir())
    if source_skills != target_skills:
        problems.append(".claude/skills names do not match .agents/skills")
    for skill in source_skills:
        source = source_root / skill / "SKILL.md"
        target = target_root / skill / "SKILL.md"
        if not target.exists():
            problems.append(f".claude/skills/{skill}/SKILL.md is missing")
        elif not filecmp.cmp(source, target, shallow=False):
            problems.append(f".claude/skills/{skill}/SKILL.md differs from .agents/skills")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
