from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.compiler.spec_to_pine import render_pine_strategy
from open_composer.expressions import (
    ExpressionError,
    evaluate_expression,
    prepare_factor_frame,
    validate_expression,
)
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
    rsi_simple,
    sma,
    stddev,
    zscore,
)
from open_composer.models.strategy_spec import FactorConfig, load_strategy_spec


def test_sma_ema_rsi_outputs() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma_values = sma(series, 2).round(2)
    assert pd.isna(sma_values.iloc[0])
    assert sma_values.iloc[1:].tolist() == [1.5, 2.5, 3.5, 4.5]
    assert ema(series, 3).iloc[-1] == pytest.approx(
        series.ewm(span=3, adjust=False, min_periods=3).mean().iloc[-1]
    )
    assert rsi(series, 3).iloc[-1] == 100


def test_rsi_uses_wilder_smoothing() -> None:
    """Verify standard `rsi` uses Wilder EWMA (matches TradingView ta.rsi)."""
    series = pd.Series(
        [100.0, 102, 101, 103, 102, 105, 104, 106, 105, 108, 110, 109, 111, 113, 112]
    )
    out = rsi(series, 14)
    # Reproduce Wilder smoothing independently to lock the formula.
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    expected = 100 - 100 / (1 + avg_gain / avg_loss)
    assert out.iloc[-1] == pytest.approx(expected.iloc[-1])
    # Sanity: this series ends in a strong uptrend, RSI should be elevated (>= 60).
    assert out.iloc[-1] >= 60


def test_rsi_simple_matches_legacy_rolling_mean() -> None:
    """`rsi_simple` keeps the pre-Wilder rolling-mean form for back-compat."""
    series = pd.Series(
        [100.0, 102, 101, 103, 102, 105, 104, 106, 105, 108, 110, 109, 111, 113, 112]
    )
    legacy = rsi_simple(series, 14)
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=14).mean()
    rs = gain / loss
    expected = (100 - 100 / (1 + rs)).fillna(100)
    assert legacy.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_rsi_simple_differs_from_wilder_rsi() -> None:
    """Wilder vs simple-rolling-mean must produce different values on real-ish data."""
    series = pd.Series([100.0 + i + (i % 3) * 0.7 for i in range(40)])
    wilder = rsi(series, 14).iloc[-1]
    simple = rsi_simple(series, 14).iloc[-1]
    assert abs(wilder - simple) > 0.5  # at least half an RSI unit apart


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


def test_static_validation_does_not_require_future_feature_packet(tmp_path: Path) -> None:
    factor = FactorConfig(
        source="feature_packet",
        path="features/not-materialized-yet.jsonl",
        field="score",
        default=0.0,
    )

    validate_expression("external_score > -1", {"external_score": factor}, root=tmp_path)

    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-02T00:00:00Z"]),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )
    with pytest.raises(ExpressionError, match="packet does not exist"):
        prepare_factor_frame(frame, {"external_score": factor}, root=tmp_path)


def test_feature_packet_replay_uses_published_at_visibility(tmp_path: Path) -> None:
    packet_path = tmp_path / "features.jsonl"
    packet_path.write_text(
        "\n".join(
            [
                (
                    '{"timestamp":"2026-01-01T00:00:00Z",'
                    '"published_at":"2026-01-03T00:00:00Z",'
                    '"fetched_at":"2026-01-03T00:00:00Z",'
                    '"visible_at":"2026-01-03T00:00:00Z",'
                    '"source":"llm","symbol":"QQQ","features":{"theme_score":0.9}}'
                ),
                (
                    '{"timestamp":"2026-01-04T00:00:00Z",'
                    '"published_at":"2026-01-04T00:00:00Z",'
                    '"fetched_at":"2026-01-04T00:00:00Z",'
                    '"visible_at":"2026-01-04T00:00:00Z",'
                    '"source":"llm","symbol":"QQQ","features":{"theme_score":0.2}}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"]
            ),
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "close": [1, 2, 3],
            "volume": [1, 2, 3],
        }
    )
    prepared = prepare_factor_frame(
        frame,
        {
            "theme_score": FactorConfig(
                source="llm_feature",
                path=str(packet_path),
                field="theme_score",
                default=0.0,
            )
        },
    )

    assert prepared["theme_score"].tolist() == [0.0, 0.9, 0.2]


def test_feature_packet_replay_filters_by_symbol(tmp_path: Path) -> None:
    packet_path = tmp_path / "features.jsonl"
    packet_path.write_text(
        "\n".join(
            [
                (
                    '{"timestamp":"2026-01-01T00:00:00Z",'
                    '"published_at":"2026-01-01T00:00:00Z",'
                    '"fetched_at":"2026-01-01T00:00:00Z",'
                    '"visible_at":"2026-01-01T00:00:00Z",'
                    '"source":"llm","symbol":"AAOI","features":{"theme_score":0.9}}'
                ),
                (
                    '{"timestamp":"2026-01-02T00:00:00Z",'
                    '"published_at":"2026-01-02T00:00:00Z",'
                    '"fetched_at":"2026-01-02T00:00:00Z",'
                    '"visible_at":"2026-01-02T00:00:00Z",'
                    '"source":"llm","symbol":"LITE","features":{"theme_score":0.1}}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]),
            "open": [1, 2],
            "high": [1, 2],
            "low": [1, 2],
            "close": [1, 2],
            "volume": [1, 2],
        }
    )
    factors = {
        "theme_score": FactorConfig(
            source="llm_feature",
            path=str(packet_path),
            field="theme_score",
            default=0.0,
        )
    }

    aaoi = prepare_factor_frame(frame, factors, symbol="AAOI")
    lite = prepare_factor_frame(frame, factors, symbol="LITE")

    assert aaoi["theme_score"].tolist() == [0.9, 0.9]
    assert lite["theme_score"].tolist() == [0.0, 0.1]


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
