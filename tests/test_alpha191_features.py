"""Tests for open_composer.research.features.alpha191.

Spot-checks (plan section 3.2) a handful of the 20 implemented GTJA
formulas against a from-scratch ``pandas`` reference on wide frames,
independent of ``_panel_ops`` -- validating the wiring in ``alpha191.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.alpha191 import (
    ALPHA191_COLUMNS,
    IMPLEMENTED_IDS,
    alpha191_skipped_ids,
    build_alpha191_features,
    compute_alpha191,
)

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
N_DAYS = 90


def _make_ohlcv_vwap(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=N_DAYS)
    rows: list[dict[str, object]] = []
    for symbol, base, vol_base in [
        ("AAA", 60.0, 600_000),
        ("BBB", 25.0, 250_000),
        ("CCC", 180.0, 120_000),
        ("DDD", 45.0, 400_000),
    ]:
        price = base
        for date in dates:
            day_open = price * (1.0 + rng.normal(0, 0.004))
            price *= 1.0 + rng.normal(0, 0.014)
            high = max(day_open, price) * (1.0 + abs(rng.normal(0, 0.003)))
            low = min(day_open, price) * (1.0 - abs(rng.normal(0, 0.003)))
            volume = vol_base * (1.0 + abs(rng.normal(0, 0.25)))
            vwap = (high + low + price) / 3.0 * (1.0 + rng.normal(0, 0.001))
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "open": day_open,
                    "high": high,
                    "low": low,
                    "close": price,
                    "volume": volume,
                    "vwap": vwap,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return _make_ohlcv_vwap()


def _wide(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    return frame.pivot(index="trade_date", columns="symbol", values=field)


def _merge_check(result: pd.DataFrame, expected_wide: pd.DataFrame, column: str) -> None:
    expected_long = expected_wide.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name=column
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged[column], merged[f"{column}_ref"], check_names=False, rtol=1e-8
    )


def test_gtja014_and_015_are_simple_delay_arithmetic(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    close = _wide(ohlcv, "close")
    open_ = _wide(ohlcv, "open")
    _merge_check(result, close - close.shift(5), "gtja014")
    _merge_check(result, open_ / close.shift(1) - 1, "gtja015")


def test_gtja018_and_020_use_close_not_vwap(ohlcv: pd.DataFrame) -> None:
    """Regression test for the deliberate correction documented in the
    module docstring: the fetched reference defaults these to vwap, but
    the quoted original formula text uses close.
    """
    result = compute_alpha191(ohlcv)
    close = _wide(ohlcv, "close")
    _merge_check(result, close / close.shift(5), "gtja018")
    delay6 = close.shift(6)
    _merge_check(result, (close - delay6) / delay6 * 100, "gtja020")


def test_gtja013_is_pure_row_arithmetic(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    high = _wide(ohlcv, "high")
    low = _wide(ohlcv, "low")
    vwap = _wide(ohlcv, "vwap")
    _merge_check(result, (high * low) ** 0.5 - vwap, "gtja013")


def test_gtja006_matches_from_scratch_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    open_ = _wide(ohlcv, "open")
    high = _wide(ohlcv, "high")
    val = open_ * 0.85 + high * 0.15
    expected = -1 * np.sign(val.diff(4)).rank(axis=1, pct=True)
    _merge_check(result, expected, "gtja006")


def test_gtja003_conditional_sum_matches_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    close = _wide(ohlcv, "close")
    high = _wide(ohlcv, "high")
    low = _wide(ohlcv, "low")
    delay1 = close.shift(1)
    up = close > delay1
    down = close < delay1
    term = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    term[up] = (close - np.minimum(low, delay1))[up]
    term[down] = (close - np.maximum(high, delay1))[down]
    term[delay1.isna()] = np.nan
    expected = term.rolling(6).sum()
    _merge_check(result, expected, "gtja003")


def test_output_shape_and_columns(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    assert list(result.columns) == ["symbol", "trade_date", *ALPHA191_COLUMNS]
    assert len(ALPHA191_COLUMNS) == 20
    assert len(result) == len(SYMBOLS) * N_DAYS


def test_skipped_ids_cover_the_rest_of_191(ohlcv: pd.DataFrame) -> None:
    skipped = alpha191_skipped_ids()
    assert len(skipped) == 191 - len(IMPLEMENTED_IDS) == 171
    ids = {row["id"] for row in skipped}
    assert "gtja030" in ids  # explicitly unfinished in the fetched source
    assert "gtja033" in ids  # needs turnover-rate data
    assert "gtja191" in ids  # never fetched this round
    assert "gtja001" not in ids


def test_build_alpha191_features_from_parquet_glob(tmp_path: Path, ohlcv: pd.DataFrame) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    archive = ohlcv.rename(columns={"trade_date": "timestamp"}).copy()
    archive["timestamp"] = pd.to_datetime(archive["timestamp"])
    archive.to_parquet(daily_dir / "2024.parquet", index=False)

    loaded = build_alpha191_features(
        str(daily_dir / "*.parquet"),
        SYMBOLS,
        memory_limit="256MB",
        temp_directory=str(tmp_path / "_duckdb_tmp"),
    )
    direct = compute_alpha191(ohlcv)
    pd.testing.assert_frame_equal(
        loaded.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        direct.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        check_exact=False,
        check_dtype=False,
        rtol=1e-6,
    )


def test_build_alpha191_features_empty_universe(tmp_path: Path) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    result = build_alpha191_features(str(daily_dir / "*.parquet"), [])
    assert list(result.columns) == ["symbol", "trade_date", *ALPHA191_COLUMNS]
    assert len(result) == 0
