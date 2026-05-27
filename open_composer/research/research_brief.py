from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import prod
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.source_card import load_source_cards
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.kernel import build_default_research_brief
from open_composer.research.metadata import workspace_relative_path
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

DEFAULT_SEARCH_BUDGET = 64
LARGE_SEARCH_THRESHOLD = 64
METHOD_FAMILIES_REQUIRING_SOURCE = {
    "inverse_etf",
    "leveraged_inverse_etf",
    "shorting",
    "short_selling",
    "vix",
    "volatility_etp",
    "llm_feature",
    "news",
    "macro",
    "event",
}


@dataclass(frozen=True)
class ResearchBriefValidation:
    strategy_name: str
    path: Path
    status: str
    blocked: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def research_brief_paths(strategy_name: str, root: Path | None = None) -> tuple[Path, Path]:
    base = root or project_root()
    stem = base / "reports" / "research" / f"{strategy_name}-research-brief"
    return stem.with_suffix(".json"), stem.with_suffix(".md")


def init_research_brief(
    spec_path: Path,
    root: Path | None = None,
    *,
    search_budget: int | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    json_path, md_path = research_brief_paths(spec.name, base)
    if json_path.exists() and not overwrite:
        return json_path, md_path
    brief = build_default_research_brief(spec).model_dump(mode="json")
    budget = int(search_budget or _candidate_budget_from_spec(spec) or DEFAULT_SEARCH_BUDGET)
    payload = {
        "schema_version": 1,
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "source_spec_path": workspace_relative_path(spec_path, base),
        "status": "draft",
        "central_hypothesis": brief.get("hypothesis") or brief.get("objective"),
        "objective": brief.get("objective"),
        "user_preferences": [],
        "source_cards_required": _source_cards_required(spec),
        "method_families": _method_families(spec),
        "search_budget": budget,
        "justification_for_large_search": _large_search_justification(spec, budget),
        "acceptance_criteria": [
            "candidate discovery must be followed by OOS, walk-forward, cost, benchmark, "
            "factor, and execution review before research_pass",
        ],
        "rejection_criteria": [
            "missing research brief",
            "stale spec hash",
            "candidate count exceeds search budget",
            "high-return candidate fails drawdown, OOS, walk-forward, or data quality gates",
        ],
        "known_failure_modes": [
            "overfit from large parameter searches",
            "survivorship bias from current-symbol universes",
            "sample or fallback data mistaken for paper-ready evidence",
        ],
        "notes": {
            "default_search_budget": DEFAULT_SEARCH_BUDGET,
            "large_search_threshold": LARGE_SEARCH_THRESHOLD,
        },
    }
    write_json(json_path, payload)
    _write_research_brief_markdown(md_path, payload)
    return json_path, md_path


def validate_research_brief(
    spec_path: Path,
    root: Path | None = None,
    *,
    planned_candidate_count: int | None = None,
    require_for_optimization: bool = True,
) -> ResearchBriefValidation:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    json_path, _ = research_brief_paths(spec.name, base)
    if not json_path.exists():
        return ResearchBriefValidation(
            strategy_name=spec.name,
            path=json_path,
            status="blocked" if require_for_optimization else "warning",
            blocked=["research_brief_missing"] if require_for_optimization else [],
            warnings=[] if require_for_optimization else ["research_brief_missing"],
        )
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ResearchBriefValidation(
            strategy_name=spec.name,
            path=json_path,
            status="blocked",
            blocked=[f"research_brief_invalid_json:{exc}"],
        )
    if not isinstance(payload, dict):
        payload = {}
    blocked: list[str] = []
    warnings: list[str] = []
    if payload.get("spec_hash") != strategy_content_hash(spec):
        blocked.append("research_brief_stale_spec_hash")
    for field_name in [
        "central_hypothesis",
        "search_budget",
        "acceptance_criteria",
        "rejection_criteria",
        "known_failure_modes",
    ]:
        if payload.get(field_name) in (None, "", [], {}):
            blocked.append(f"research_brief_missing_{field_name}")
    if "source_cards_required" not in payload or not isinstance(
        payload.get("source_cards_required"), list
    ):
        blocked.append("research_brief_missing_source_cards_required")
    budget = _int_or_none(payload.get("search_budget")) or DEFAULT_SEARCH_BUDGET
    if budget < 1:
        blocked.append("research_brief_invalid_search_budget")
    if (
        budget > LARGE_SEARCH_THRESHOLD
        and not str(payload.get("justification_for_large_search") or "").strip()
    ):
        blocked.append("large_search_missing_justification")
    if planned_candidate_count is not None and planned_candidate_count > budget:
        blocked.append(f"candidate_count_exceeds_search_budget:{planned_candidate_count}>{budget}")
    blocked.extend(_source_card_link_blockers(spec, payload, base))
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return ResearchBriefValidation(
        strategy_name=spec.name,
        path=json_path,
        status=status,
        blocked=blocked,
        warnings=warnings,
        payload=payload,
    )


def ensure_research_brief_for_sweep(
    spec_path: Path,
    parameters: dict[str, list[str]],
    root: Path | None = None,
) -> ResearchBriefValidation:
    result = validate_research_brief(
        spec_path,
        root,
        planned_candidate_count=parameter_candidate_count(parameters),
        require_for_optimization=True,
    )
    if not result.ok:
        raise ValueError(_validation_message(result))
    return result


def parameter_candidate_count(parameters: dict[str, list[Any]]) -> int:
    if not parameters:
        return 0
    return prod(max(len(values), 1) for values in parameters.values())


def _validation_message(result: ResearchBriefValidation) -> str:
    reasons = result.blocked or result.warnings
    return (
        "research brief validation failed for "
        f"{result.strategy_name}: {', '.join(reasons)}; "
        f"run `uv run oc strategy research-brief init <spec>` and fix {result.path}"
    )


def _write_research_brief_markdown(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    lines = [
        f"# Research Brief: {payload['strategy_name']}",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Spec hash: `{payload.get('spec_hash')}`",
        f"- Source spec: `{payload.get('source_spec_path')}`",
        f"- Search budget: `{payload.get('search_budget')}`",
        "",
        "## Central Hypothesis",
        "",
        str(payload.get("central_hypothesis") or "n/a"),
        "",
        "## Method Families",
        "",
    ]
    method_families = payload.get("method_families")
    if isinstance(method_families, list) and method_families:
        lines.extend(f"- `{item}`" for item in method_families)
    else:
        lines.append("- n/a")
    lines.extend(["", "## Source Cards Required", ""])
    required = payload.get("source_cards_required")
    if isinstance(required, list) and required:
        lines.extend(f"- `{item}`" for item in required)
    else:
        lines.append("- none")
    lines.extend(["", "## Acceptance Criteria", ""])
    lines.extend(f"- {item}" for item in payload.get("acceptance_criteria", []))
    lines.extend(["", "## Rejection Criteria", ""])
    lines.extend(f"- {item}" for item in payload.get("rejection_criteria", []))
    lines.extend(["", "## Known Failure Modes", ""])
    lines.extend(f"- {item}" for item in payload.get("known_failure_modes", []))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _candidate_budget_from_spec(spec: StrategySpec) -> int | None:
    if spec.research_design and spec.research_design.candidate_budget:
        return int(spec.research_design.candidate_budget)
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    if isinstance(legacy, dict):
        return _int_or_none(legacy.get("candidate_budget") or legacy.get("candidate_cap"))
    return None


def _large_search_justification(spec: StrategySpec, budget: int) -> str:
    if budget <= LARGE_SEARCH_THRESHOLD:
        return ""
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    if isinstance(legacy, dict) and legacy.get("justification_for_large_search"):
        return str(legacy["justification_for_large_search"])
    return (
        "Existing StrategySpec research_design declares a candidate budget above the "
        "default threshold; keep OOS, walk-forward, and overfit-risk review outside "
        "the optimizer."
    )


def _method_families(spec: StrategySpec) -> list[str]:
    families: set[str] = set()
    if spec.position_direction == "long_short":
        families.add("shorting")
    universe = {symbol.upper() for symbol in spec.universe}
    if {"SQQQ", "SOXS", "TECS", "SPXU", "FNGD", "LABD", "UVXY"} & universe:
        families.add("inverse_etf")
    if any("VIX" in symbol.upper() or symbol.upper() == "UVXY" for symbol in spec.universe):
        families.add("vix")
    for factor in spec.factors.values():
        if factor.source == "llm_feature":
            families.add("llm_feature")
        if factor.source == "feature_packet":
            families.add("event")
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    if isinstance(legacy, dict):
        for item in legacy.get("method_variants", []) or []:
            text = str(item).lower()
            if "short" in text:
                families.add("shorting")
            if "inverse" in text or "sqqq" in text:
                families.add("inverse_etf")
            if "vix" in text or "vol" in text:
                families.add("vix")
    return sorted(families)


def _source_cards_required(spec: StrategySpec) -> list[str]:
    return [
        family for family in _method_families(spec) if family in METHOD_FAMILIES_REQUIRING_SOURCE
    ]


def _source_card_link_blockers(
    spec: StrategySpec,
    payload: dict[str, Any],
    root: Path,
) -> list[str]:
    required = [str(item) for item in payload.get("source_cards_required", []) if item]
    if not required:
        return []
    exploratory = {
        str(item) for item in payload.get("exploratory_method_families", []) if item is not None
    }
    cards = load_source_cards(spec.name, root)
    blockers: list[str] = []
    for family in required:
        if family in exploratory:
            continue
        if not any(_card_matches_family(card.model_dump(mode="json"), family) for card in cards):
            blockers.append(f"source_card_missing_for_method_family:{family}")
    return blockers


def _card_matches_family(card: dict[str, Any], family: str) -> bool:
    values: list[str] = []
    for key in ["method_family", "applies_to", "claim_id", "claim", "impact_on_spec"]:
        value = card.get(key)
        if isinstance(value, list):
            values.extend(str(item).lower() for item in value)
        elif value is not None:
            values.append(str(value).lower())
    return any(family.lower() in value for value in values)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
