from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.compiler.spec_to_pine import render_pine_strategy
from open_composer.expressions import ExpressionError, evaluate_expression
from open_composer.indicators import (
    atr,
    bollinger_lower,
    bollinger_mid,
    bollinger_upper,
    crossover,
    ema,
    highest,
    lag,
    macd,
    macd_hist,
    macd_signal,
    roc,
    rsi,
    sma,
    stddev,
    zscore,
)
from open_composer.models.strategy_spec import load_strategy_spec


def test_sma_ema_rsi_outputs() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma_values = sma(series, 2).round(2)
    assert pd.isna(sma_values.iloc[0])
    assert sma_values.iloc[1:].tolist() == [1.5, 2.5, 3.5, 4.5]
    assert ema(series, 3).iloc[-1] == pytest.approx(
        series.ewm(span=3, adjust=False, min_periods=3).mean().iloc[-1]
    )
    assert rsi(series, 3).iloc[-1] == 100


def test_advanced_factor_outputs() -> None:
    series = pd.Series([1.0, 2.0, 1.5, 3.0, 4.0])
    assert highest(series, 3).iloc[-1] == 4.0
    assert lag(series, 1).iloc[-1] == 3.0
    assert roc(series, 2).iloc[-1] == pytest.approx((4.0 / 1.5 - 1) * 100)
    cross = crossover(pd.Series([1.0, 1.0, 3.0]), pd.Series([2.0, 2.0, 2.0]))
    assert bool(cross.iloc[-1])
    atr_value = atr(
        pd.Series([3.0, 4.0, 5.0]),
        pd.Series([1.0, 2.0, 3.0]),
        pd.Series([2.0, 3.0, 4.0]),
        2,
    ).iloc[-1]
    assert atr_value == pytest.approx(2.0)


def test_statistical_factor_outputs() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 6.0, 7.0])
    assert stddev(series, 3).iloc[-1] == pytest.approx(series.iloc[-3:].std(ddof=0))
    assert bollinger_mid(series, 3).iloc[-1] == pytest.approx(series.iloc[-3:].mean())
    assert bollinger_upper(series, 3).iloc[-1] > bollinger_mid(series, 3).iloc[-1]
    assert bollinger_lower(series, 3).iloc[-1] < bollinger_mid(series, 3).iloc[-1]
    assert macd(series, 2, 4).iloc[-1] == pytest.approx(
        ema(series, 2).iloc[-1] - ema(series, 4).iloc[-1]
    )
    assert macd_signal(series, 2, 4, 2).iloc[-1] == pytest.approx(
        ema(macd(series, 2, 4), 2).iloc[-1]
    )
    assert macd_hist(series, 2, 4, 2).iloc[-1] == pytest.approx(
        macd(series, 2, 4).iloc[-1] - macd_signal(series, 2, 4, 2).iloc[-1]
    )
    assert zscore(series, 3).iloc[-1] == pytest.approx(
        (series.iloc[-1] - series.iloc[-3:].mean()) / series.iloc[-3:].std(ddof=0)
    )


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


def test_expression_uses_advanced_and_statistical_factor_functions() -> None:
    frame = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6, 7],
            "high": [2, 3, 4, 5, 6, 7, 8],
            "low": [0, 1, 2, 3, 4, 5, 6],
            "close": [1, 2, 3, 4, 5, 6, 7],
            "volume": [10, 11, 12, 13, 14, 15, 20],
        }
    )
    result = evaluate_expression(
        "macd(close, 2, 4) > macd_signal(close, 2, 4, 2) "
        "and zscore(close, 3) > 0 "
        "and close < bollinger_upper(close, 3)",
        frame,
    )
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


def test_statistical_factor_export_to_pine(tmp_path: Path) -> None:
    spec_path = tmp_path / "pine_statistical.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "pine_statistical",
                "description": "Statistical factor export fixture.",
                "timeframe": "15m",
                "universe": ["QQQ"],
                "lifecycle": "draft",
                "factors": {
                    "trend_score": {
                        "source": "expression",
                        "expression": "zscore(close, 3)",
                    },
                    "vol_band": {
                        "source": "expression",
                        "expression": "bollinger_upper(close, 3)",
                    },
                    "momentum": {
                        "source": "expression",
                        "expression": "macd(close, 2, 4) - macd_signal(close, 2, 4, 2)",
                    },
                },
                "entry": {"all": ["trend_score > 0", "close < vol_band", "momentum > 0"]},
                "exit": {"any": ["trend_score < 0", "close > vol_band"]},
                "risk": {
                    "max_trades_per_day": 1,
                    "max_position_weight": 0.1,
                    "stop_loss_pct": 1.0,
                    "take_profit_pct": 2.0,
                },
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {
                    "source": "sample",
                    "symbol": "QQQ",
                    "path": "data/sample/qqq_15m.csv",
                },
                "llm_review": {"enabled": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    spec = load_strategy_spec(spec_path)
    pine = render_pine_strategy(spec)

    assert "ta.stdev" in pine
    assert "ta.ema" in pine
    assert "nz((" in pine
    assert "trend_score = nz((" in pine
