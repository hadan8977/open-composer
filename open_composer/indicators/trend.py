from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def highest(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).max()


def lowest(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).min()


def lag(series: pd.Series, periods: int) -> pd.Series:
    return series.shift(periods)


def crossover(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left > right) & (left.shift(1) <= right.shift(1))


def crossunder(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left < right) & (left.shift(1) >= right.shift(1))
