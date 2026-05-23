from __future__ import annotations

from dataclasses import dataclass, field

from open_composer.research.kernel.datamodel import ResearchDataModel


@dataclass(frozen=True)
class PurgedEmbargoConfig(ResearchDataModel):
    purged: bool = False
    embargo_bars: int = 0
    reason: str = "not_configured"


@dataclass(frozen=True)
class ResearchWindowSplit(ResearchDataModel):
    train_start: str | None = None
    train_end: str | None = None
    test_start: str | None = None
    test_end: str | None = None
    train_rows: int = 0
    test_rows: int = 0
    embargo: PurgedEmbargoConfig = field(default_factory=PurgedEmbargoConfig)


@dataclass(frozen=True)
class WalkForwardSlice(ResearchDataModel):
    fold: int
    train: ResearchWindowSplit
    test: ResearchWindowSplit
    selected_candidate_ids: list[str] = field(default_factory=list)
