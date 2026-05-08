from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.data.sample import load_sample_ohlcv
from open_composer.config import data_feed
from open_composer.models.strategy_spec import StrategySpec


def load_ohlcv_for_spec(spec: StrategySpec, root: Path) -> pd.DataFrame:
    if spec.data.source == "sample":
        return load_sample_ohlcv(root, spec)
    if spec.data.source == "alpaca":
        return fetch_alpaca_bars(
            root=root,
            symbol=spec.primary_symbol,
            timeframe=spec.timeframe,
            start=None,
            end=None,
            feed=spec.data.feed or data_feed(),
        )
    raise ValueError(f"unsupported data source: {spec.data.source}")


def fetch_ohlcv(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    feed: str | None = None,
) -> pd.DataFrame:
    return fetch_alpaca_bars(
        root=root,
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        feed=feed or data_feed(),
    )
