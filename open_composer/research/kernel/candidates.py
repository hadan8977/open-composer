from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from open_composer.research.kernel.datamodel import ResearchDataModel


@dataclass(frozen=True)
class CandidateSpec(ResearchDataModel):
    candidate_id: str
    strategy_name: str
    params: dict[str, Any] = field(default_factory=dict)
    source_spec_path: str | None = None
    spec_path: str | None = None


@dataclass(frozen=True)
class CandidateScore(ResearchDataModel):
    candidate_id: str
    rank: int
    score: float
    metrics: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)
    gate_status: str = "warning"


@dataclass(frozen=True)
class CandidateSet(ResearchDataModel):
    family: str
    candidates: list[CandidateSpec] = field(default_factory=list)
    scores: list[CandidateScore] = field(default_factory=list)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)
