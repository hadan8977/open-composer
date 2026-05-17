from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    strategy_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    source_spec_path: str | None = None
    spec_path: str | None = None


class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    rank: int
    score: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    gate_status: str = "warning"


class CandidateSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str
    candidates: list[CandidateSpec] = Field(default_factory=list)
    scores: list[CandidateScore] = Field(default_factory=list)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)
