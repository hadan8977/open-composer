from __future__ import annotations

import pandas as pd
import pytest

from open_composer.expressions import ExpressionError, evaluate_expression
from open_composer.indicators import ema, rsi, sma


def test_sma_ema_rsi_outputs() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma_values = sma(series, 2).round(2)
    assert pd.isna(sma_values.iloc[0])
    assert sma_values.iloc[1:].tolist() == [1.5, 2.5, 3.5, 4.5]
    assert ema(series, 3).iloc[-1] == pytest.approx(
        series.ewm(span=3, adjust=False, min_periods=3).mean().iloc[-1]
    )
    assert rsi(series, 3).iloc[-1] == 100


def test_expression_uses_supported_ohlcv_and_functions() -> None:
    frame = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6],
            "high": [2, 3, 4, 5, 6, 7],
            "low": [0, 1, 2, 3, 4, 5],
            "close": [1, 2, 3, 4, 5, 6],
            "volume": [10, 11, 12, 13, 14, 15],
        }
    )
    result = evaluate_expression("close > ema(close, 3)", frame)
    assert result.dtype == bool
    assert result.iloc[-1]


def test_expression_rejects_unknown_name() -> None:
    frame = pd.DataFrame(
        {
            "close": [1, 2, 3],
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "volume": [1, 2, 3],
        }
    )
    with pytest.raises(ExpressionError):
        evaluate_expression("adj_close > close", frame)
