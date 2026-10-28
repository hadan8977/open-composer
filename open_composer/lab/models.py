"""Small adapter contract. Native output remains the primary numerical evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd


def checked_series(values: pd.Series) -> pd.Series:
    series = values.astype(float).copy()
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Returns need an explicit DatetimeIndex")
    if series.empty or series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError("Returns need nonempty, unique, increasing timestamps")
    if not np.isfinite(series.to_numpy()).all():
        raise ValueError("Returns must be finite; do not fill missing exposure silently")
    if (series < -1).any():
        raise ValueError("Returns below -100% require a native insolvency contract")
    return series


@dataclass(frozen=True)
class Experiment:
    """Declared interpretation, not an authority or a replacement scientific contract."""

    direction: str
    data_and_exposure: str
    costs: str
    baseline: str
    kind: Literal["financial", "diagnostic"] = "financial"
    baseline_net_profit_usd: float | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.direction, self.data_and_exposure, self.costs, self.baseline):
            if not value.strip():
                raise ValueError("Direction, exposure, costs and baseline must be explicit")
        if self.kind not in ("financial", "diagnostic"):
            raise ValueError("Unknown result kind")
        if self.baseline_net_profit_usd is not None and not math.isfinite(
            self.baseline_net_profit_usd
        ):
            raise ValueError("Baseline PnL must be finite")


@dataclass
class EngineResult:
    engine: str
    initial_equity_usd: float
    end_equity_usd: float
    native: dict[str, Any]
    # This is the engine's accounting ledger, not reconstructed fills or hypothetical returns.
    ledger: pd.DataFrame | None = None
    net_returns: pd.Series | None = None
    return_frequency: Literal["session", "bar"] = "session"
    limitations: list[str] = field(default_factory=list)
    # Supplied by the adapter: costs and window interpretation must stay beside native output.
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.engine.strip():
            raise ValueError("An actual engine name is required")
        if not all(math.isfinite(x) for x in (self.initial_equity_usd, self.end_equity_usd)):
            raise ValueError("Native account equity must be finite")
        if self.initial_equity_usd <= 0:
            raise ValueError("Initial equity must be positive and denominated in USD")
        if self.net_returns is not None:
            self.net_returns = checked_series(self.net_returns)
            implied = self.initial_equity_usd * float((1 + self.net_returns).prod())
            if not math.isclose(implied, self.end_equity_usd, rel_tol=1e-8, abs_tol=1e-6):
                raise ValueError("Native return ledger does not reconcile to account equity")

    @property
    def net_profit_usd(self) -> float:
        return self.end_equity_usd - self.initial_equity_usd
