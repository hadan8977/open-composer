from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_id: str
    rank: int | None = None
    candidate_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    status: Literal["ok", "warning", "blocked"] = "warning"
    metrics: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str | None] = Field(default_factory=dict)


class TrialLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    family: str
    trial_count: int = 0
    candidate_count: int = 0
    max_candidates: int | None = None
    random_seed: int | None = None
    local_choice_label: str | None = None
    trials: list[TrialRecord] = Field(default_factory=list)
    selection_bias_note: str = (
        "Trial ledgers are research evidence only until OOS, walk-forward, cost, "
        "benchmark, and paper-readiness gates pass."
    )

    @classmethod
    def from_trials(
        cls,
        *,
        strategy_name: str,
        family: str,
        trials: list[TrialRecord],
        max_candidates: int | None = None,
        local_choice_label: str | None = None,
    ) -> TrialLedger:
        return cls(
            strategy_name=strategy_name,
            family=family,
            trial_count=len(trials),
            candidate_count=len(trials),
            max_candidates=max_candidates,
            local_choice_label=local_choice_label,
            trials=trials,
        )
