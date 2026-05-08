from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def load_sample_ohlcv(root: Path, spec: StrategySpec) -> pd.DataFrame:
    relative = spec.data.path or f"data/sample/{spec.primary_symbol.lower()}_{spec.timeframe}.csv"
    path = root / relative
    if not path.exists():
        raise FileNotFoundError(f"sample data not found: {path}")
    frame = pd.read_csv(path)
    return normalize_ohlcv(frame)


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV data missing columns: {', '.join(missing)}")
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    return normalized.sort_values("timestamp").reset_index(drop=True)
