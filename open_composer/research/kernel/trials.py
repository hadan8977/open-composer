from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from open_composer.research.kernel.datamodel import ResearchDataModel


@dataclass(frozen=True)
class TrialRecord(ResearchDataModel):
    trial_id: str
    candidate_name: str
    parent_trial_id: str | None = None
    rank: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    changed_from: dict[str, Any] = field(default_factory=dict)
    change_summary: str | None = None
    score: float | None = None
    status: Literal["ok", "warning", "blocked"] = "warning"
    metrics: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)
    lesson_tags: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class TrialLedger(ResearchDataModel):
    strategy_name: str
    family: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    trial_count: int = 0
    candidate_count: int = 0
    max_candidates: int | None = None
    random_seed: int | None = None
    local_choice_label: str | None = None
    trials: list[TrialRecord] = field(default_factory=list)
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
