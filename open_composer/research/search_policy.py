from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SearchStrategy = Literal["grid", "random", "evolutionary"]


@dataclass(frozen=True)
class ObjectiveSet:
    primary_metric: str
    secondary_metrics: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    tie_breakers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchPolicy:
    strategy: SearchStrategy
    candidate_budget: int
    random_seed: int | None = None
    objective_set: ObjectiveSet | None = None
    prune_rules: list[str] = field(default_factory=list)
    requires_nested_validation: bool = True

    def validate(self) -> None:
        if self.candidate_budget < 1:
            raise ValueError("candidate_budget must be at least 1")
        if self.strategy == "evolutionary" and self.objective_set is None:
            raise ValueError("evolutionary search requires objective_set")


@dataclass(frozen=True)
class TrialDecision:
    trial_id: str
    decision: Literal["kept", "pruned", "rejected", "failed"]
    reason: str
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
