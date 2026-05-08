from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuleBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: list[str] = Field(default_factory=list)
    any: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_rules(self) -> RuleBlock:
        if not self.all and not self.any:
            msg = "rule block must define at least one rule in 'all' or 'any'"
            raise ValueError(msg)
        return self


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_trades_per_day: int = Field(default=3, ge=1)
    max_position_weight: float = Field(default=0.2, gt=0, le=1)
    stop_loss_pct: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual_signal", "paper_auto"] = "manual_signal"
    signal_on: Literal["bar_close"] = "bar_close"
    fill_assumption: Literal["next_bar_open"] = "next_bar_open"
    broker: Literal["none", "alpaca_paper"] = "none"

    @model_validator(mode="after")
    def broker_matches_mode(self) -> ExecutionConfig:
        if self.mode == "paper_auto" and self.broker != "alpaca_paper":
            msg = "paper_auto execution requires broker=alpaca_paper"
            raise ValueError(msg)
        if self.mode == "manual_signal" and self.broker == "alpaca_paper":
            msg = "manual_signal execution must use broker=none"
            raise ValueError(msg)
        return self


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["sample", "alpaca"] = "sample"
    symbol: str | None = None
    path: str | None = None
    feed: str | None = None


class DataAssumptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sample"
    adjusted: bool = True
    timezone: str = "America/New_York"


class LLMReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str | None = None


class NotesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: str = ""
    open_questions: list[str] = Field(default_factory=list)


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    timeframe: Literal["15m", "1h", "daily", "weekly"]
    universe: list[str] = Field(min_length=1)
    lifecycle: Literal["draft", "approved", "active", "retired"]
    entry: RuleBlock
    exit: RuleBlock
    risk: RiskConfig
    execution: ExecutionConfig
    data: DataConfig = Field(default_factory=DataConfig)
    data_assumptions: DataAssumptions = Field(default_factory=DataAssumptions)
    llm_review: LLMReviewConfig = Field(default_factory=LLMReviewConfig)
    notes: NotesConfig = Field(default_factory=NotesConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            msg = "name may only contain letters, numbers, underscores, and hyphens"
            raise ValueError(msg)
        return value

    @field_validator("universe")
    @classmethod
    def normalize_universe(cls, value: list[str]) -> list[str]:
        return [symbol.upper().strip() for symbol in value]

    @property
    def primary_symbol(self) -> str:
        return (self.data.symbol or self.universe[0]).upper()

    def all_expressions(self) -> list[str]:
        return [*self.entry.all, *self.entry.any, *self.exit.all, *self.exit.any]


def load_strategy_spec(path: Path | str) -> StrategySpec:
    spec_path = Path(path)
    with spec_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        msg = f"{spec_path} must contain a YAML mapping"
        raise ValueError(msg)
    spec = StrategySpec.model_validate(raw)

    from open_composer.expressions import validate_expression

    for expression in spec.all_expressions():
        validate_expression(expression)
    return spec
