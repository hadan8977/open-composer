from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_composer.config import project_root
from open_composer.research.control import ResearchControlResult, update_research_control
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
    research_report = build_strategy_research_report(spec_path, base)
    control = update_research_control(spec_path, base)
    return StrategyEvidenceResult(
        strategy_name=research_report.strategy_name,
        status=research_report.status,
        research_report=research_report,
        control=control,
    )
