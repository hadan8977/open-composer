from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(series: pd.Series, window: int) -> pd.Series:
    """Standard RSI with Wilder smoothing (α = 1/window).

    Matches TradingView ``ta.rsi`` and the original Welles Wilder 1978 definition.
    Returns 100 when avg_loss is 0 (all gains).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(100)


def rsi_simple(series: pd.Series, window: int) -> pd.Series:
    """RSI with simple rolling-mean smoothing (legacy non-Wilder form).

    Kept for backward compatibility with strategies authored before the Wilder
    upgrade. Pine export still maps this to ``ta.rsi`` and writes a parity
    warning into the parity report because TradingView uses Wilder smoothing.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(100)


def roc(series: pd.Series, window: int) -> pd.Series:
    return ((series / series.shift(window)) - 1) * 100


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()
