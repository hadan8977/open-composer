from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.control import ResearchControlResult, update_research_control
from open_composer.research.research_brief import validate_research_brief
from open_composer.research.research_report import (
    StrategyResearchReportResult,
    build_strategy_research_report,
)


@dataclass(frozen=True)
class StrategyEvidenceResult:
    strategy_name: str
    status: str
    research_report: StrategyResearchReportResult
    control: ResearchControlResult


def build_strategy_evidence(
    spec_path: Path,
    root: Path | None = None,
) -> StrategyEvidenceResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if _has_optimized_research_design(spec):
        brief = validate_research_brief(spec_path, base, require_for_optimization=True)
        if not brief.ok:
            msg = "research brief validation failed: " + ", ".join(brief.blocked)
            raise ValueError(msg)
    research_report = build_strategy_research_report(spec_path, base)
    control = update_research_control(spec_path, base)
    return StrategyEvidenceResult(
        strategy_name=research_report.strategy_name,
        status=research_report.status,
        research_report=research_report,
        control=control,
    )


def _has_optimized_research_design(spec) -> bool:
    if spec.research_design and spec.research_design.parameter_space:
        return True
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    return isinstance(legacy, dict) and bool(legacy.get("parameter_ranges"))
