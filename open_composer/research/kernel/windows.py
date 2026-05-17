from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PurgedEmbargoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purged: bool = False
    embargo_bars: int = Field(default=0, ge=0)
    reason: str = "not_configured"


class ResearchWindowSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train_start: str | None = None
    train_end: str | None = None
    test_start: str | None = None
    test_end: str | None = None
    train_rows: int = 0
    test_rows: int = 0
    embargo: PurgedEmbargoConfig = Field(default_factory=PurgedEmbargoConfig)


class WalkForwardSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fold: int
    train: ResearchWindowSplit
    test: ResearchWindowSplit
    selected_candidate_ids: list[str] = Field(default_factory=list)
