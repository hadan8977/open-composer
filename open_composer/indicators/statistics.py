from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.indicators.trend import ema, sma

__all__ = [
    "bollinger_lower",
    "bollinger_mid",
    "bollinger_upper",
    "macd",
    "macd_hist",
    "macd_signal",
    "stddev",
    "zscore",
]


def stddev(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).std(ddof=0)


def zscore(series: pd.Series, window: int) -> pd.Series:
    center = sma(series, window)
    spread = stddev(series, window).replace(0, np.nan)
    return ((series - center) / spread).fillna(0)


def macd(series: pd.Series, fast: int, slow: int) -> pd.Series:
    return ema(series, fast) - ema(series, slow)


def macd_signal(series: pd.Series, fast: int, slow: int, signal: int) -> pd.Series:
    return ema(macd(series, fast, slow), signal)


def macd_hist(series: pd.Series, fast: int, slow: int, signal: int) -> pd.Series:
    line = macd(series, fast, slow)
    return line - macd_signal(series, fast, slow, signal)


def bollinger_mid(series: pd.Series, window: int) -> pd.Series:
    return sma(series, window)


def bollinger_upper(series: pd.Series, window: int, mult: float = 2.0) -> pd.Series:
    mid = bollinger_mid(series, window)
    spread = stddev(series, window)
    return mid + spread * mult


def bollinger_lower(series: pd.Series, window: int, mult: float = 2.0) -> pd.Series:
    mid = bollinger_mid(series, window)
    spread = stddev(series, window)
    return mid - spread * mult
