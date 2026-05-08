from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OptionOverlaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    underlying_strategy: str
    symbol: str
    overlay_type: Literal["long_call", "debit_call_spread"]
    dte: int = Field(ge=1)
    long_moneyness_pct: float
    short_moneyness_pct: float | None = None
    implied_volatility: float = Field(gt=0)
    risk_free_rate: float = 0.04
    spread_pct: float = Field(ge=0)
    max_premium_weight: float = Field(gt=0, le=1)
    contract_multiplier: int = 100
    pricing_model: Literal["black_scholes_approx"] = "black_scholes_approx"
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_spread_strikes(self) -> OptionOverlaySpec:
        if self.overlay_type == "long_call" and self.short_moneyness_pct is not None:
            raise ValueError("long_call overlays must not set short_moneyness_pct")
        if self.overlay_type == "debit_call_spread":
            if self.short_moneyness_pct is None:
                raise ValueError("debit_call_spread overlays require short_moneyness_pct")
            if self.short_moneyness_pct <= self.long_moneyness_pct:
                raise ValueError("short_moneyness_pct must be above long_moneyness_pct")
        return self


class OptionBacktestTrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_time: datetime
    exit_time: datetime
    underlying_entry: float
    underlying_exit: float
    underlying_return_pct: float
    long_strike: float
    short_strike: float | None = None
    entry_debit: float
    exit_value: float
    contracts: int
    premium_at_risk: float
    pnl: float
    return_pct: float


class OptionBacktestRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    overlay_name: str
    underlying_strategy: str
    symbol: str
    overlay_type: Literal["long_call", "debit_call_spread"]
    trades: int
    skipped_trades: int
    start_equity: float
    end_equity: float
    total_return_pct: float
    underlying_total_return_pct: float | None = None
    underlying_trades: int | None = None
    assumptions: list[str] = Field(default_factory=list)
    report_path: str | None = None
