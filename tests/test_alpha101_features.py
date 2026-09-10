"""Tests for open_composer.research.features.alpha101.

Spot-checks (plan section 3.2: "单元测试:任取 3 个公式...用 pandas 独立实现
对照") a handful of the 20 implemented formulas against a from-scratch
``pandas`` reference written directly against wide frames -- deliberately
not calling ``_panel_ops`` (already covered by its own tests), so this test
is validating the *wiring* in ``alpha101.py``, not re-validating the
operators.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.alpha101 import (
    ALPHA101_COLUMNS,
    IMPLEMENTED_IDS,
    alpha101_skipped_ids,
    build_alpha101_features,
    compute_alpha101,
)

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
N_DAYS = 90


def _make_ohlcv_vwap(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=N_DAYS)
    rows: list[dict[str, object]] = []
    for symbol, base, vol_base in [
        ("AAA", 80.0, 800_000),
        ("BBB", 30.0, 300_000),
        ("CCC", 150.0, 150_000),
        ("DDD", 55.0, 450_000),
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


def test_alpha003_matches_from_scratch_pandas_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    open_ = _wide(ohlcv, "open")
    volume = _wide(ohlcv, "volume")
    expected = -1 * open_.rank(axis=1, pct=True).rolling(10).corr(volume.rank(axis=1, pct=True))
    expected = expected.replace([np.inf, -np.inf], np.nan)
    expected_long = expected.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name="alpha003"
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged["alpha003"], merged["alpha003_ref"], check_names=False, rtol=1e-8
    )


def test_alpha006_matches_from_scratch_pandas_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    open_ = _wide(ohlcv, "open")
    volume = _wide(ohlcv, "volume")
    expected = (-1 * open_.rolling(10).corr(volume)).replace([np.inf, -np.inf], np.nan)
    expected_long = expected.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name="alpha006"
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged["alpha006"], merged["alpha006_ref"], check_names=False, rtol=1e-8
    )


def test_alpha012_matches_from_scratch_pandas_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    close = _wide(ohlcv, "close")
    volume = _wide(ohlcv, "volume")
    expected = np.sign(volume.diff(1)) * (-1 * close.diff(1))
    expected_long = expected.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name="alpha012"
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged["alpha012"], merged["alpha012_ref"], check_names=False, rtol=1e-8
    )


def test_alpha009_conditional_branch_matches_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    close = _wide(ohlcv, "close")
    delta_close = close.diff(1)
    cond = (delta_close.rolling(5).min() > 0) | (delta_close.rolling(5).max() < 0)
    expected = delta_close.where(cond, -1 * delta_close)
    expected_long = expected.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name="alpha009"
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged["alpha009"], merged["alpha009_ref"], check_names=False, rtol=1e-8
    )


def test_alpha020_matches_from_scratch_pandas_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    open_ = _wide(ohlcv, "open")
    high = _wide(ohlcv, "high")
    low = _wide(ohlcv, "low")
    close = _wide(ohlcv, "close")
    expected = (
        -1
        * (open_ - high.shift(1)).rank(axis=1, pct=True)
        * (open_ - close.shift(1)).rank(axis=1, pct=True)
        * (open_ - low.shift(1)).rank(axis=1, pct=True)
    )
    expected_long = expected.reset_index().melt(
        id_vars="trade_date", var_name="symbol", value_name="alpha020"
    )
    merged = result.merge(expected_long, on=["symbol", "trade_date"], suffixes=("", "_ref"))
    pd.testing.assert_series_equal(
        merged["alpha020"], merged["alpha020_ref"], check_names=False, rtol=1e-8
    )


def test_output_shape_and_columns(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha101(ohlcv)
    assert list(result.columns) == ["symbol", "trade_date", *ALPHA101_COLUMNS]
    assert len(ALPHA101_COLUMNS) == 20
    assert set(result["symbol"]) == set(SYMBOLS)
    assert len(result) == len(SYMBOLS) * N_DAYS


def test_skipped_ids_cover_the_rest_of_101(ohlcv: pd.DataFrame) -> None:
    skipped = alpha101_skipped_ids()
    assert len(skipped) == 101 - len(IMPLEMENTED_IDS) == 81
    assert {"alpha021", "alpha101"} <= {row["id"] for row in skipped}
    assert "alpha001" not in {row["id"] for row in skipped}


def test_build_alpha101_features_from_parquet_glob(tmp_path: Path, ohlcv: pd.DataFrame) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    archive = ohlcv.rename(columns={"trade_date": "timestamp"}).copy()
    archive["timestamp"] = pd.to_datetime(archive["timestamp"])
    archive.to_parquet(daily_dir / "2024.parquet", index=False)

    loaded = build_alpha101_features(
        str(daily_dir / "*.parquet"),
        SYMBOLS,
        memory_limit="256MB",
        temp_directory=str(tmp_path / "_duckdb_tmp"),
    )
    direct = compute_alpha101(ohlcv)
    pd.testing.assert_frame_equal(
        loaded.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        direct.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        check_exact=False,
        check_dtype=False,
        rtol=1e-6,
    )


def test_build_alpha101_features_empty_universe(tmp_path: Path) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    result = build_alpha101_features(str(daily_dir / "*.parquet"), [])
    assert list(result.columns) == ["symbol", "trade_date", *ALPHA101_COLUMNS]
    assert len(result) == 0
