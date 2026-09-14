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
    assert len(ALPHA191_COLUMNS) == 34  # 20 original + 14 Step 15 Track A US-17 additions
    assert len(result) == len(SYMBOLS) * N_DAYS


def test_skipped_ids_cover_the_rest_of_191(ohlcv: pd.DataFrame) -> None:
    skipped = alpha191_skipped_ids()
    assert len(skipped) == 191 - len(IMPLEMENTED_IDS) == 157
    ids = {row["id"] for row in skipped}
    assert "gtja030" in ids  # explicitly unfinished in the fetched source
    assert "gtja033" in ids  # needs turnover-rate data
    assert "gtja191" in ids  # never fetched this round
    assert "gtja001" not in ids
    assert "gtja039" not in ids  # Step 15 Track A: now implemented (DECAYLINEAR added)
    assert "gtja181" in ids  # Step 15 Track A: genuinely blocked, see alpha191.py docstring


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


def _make_ohlcv_vwap_long(seed: int = 23, n_days: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-03", periods=n_days)
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
def ohlcv_long() -> pd.DataFrame:
    """A longer (260 trading day) fixture for Step 15 Track A ids whose
    formulas need more warm-up than ``N_DAYS=90`` can provide (e.g.
    gtja184's 200-day correlation window) to produce any non-null output
    at all worth checking."""
    return _make_ohlcv_vwap_long()


def test_gtja046_matches_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    close = _wide(ohlcv, "close")
    expected = (
        close.rolling(3).mean()
        + close.rolling(6).mean()
        + close.rolling(12).mean()
        + close.rolling(24).mean()
    ) / (4.0 * close)
    _merge_check(result, expected, "gtja046")


def test_gtja161_matches_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    high = _wide(ohlcv, "high")
    low = _wide(ohlcv, "low")
    close = _wide(ohlcv, "close")
    delay1 = close.shift(1)
    true_range = np.maximum(np.maximum(high - low, (delay1 - high).abs()), (delay1 - low).abs())
    expected = true_range.rolling(12).mean()
    _merge_check(result, expected, "gtja161")


def test_gtja086_hits_all_three_branches_and_matches_reference() -> None:
    """Regression test for the branch-logic bug found in the fetched
    Daic115 reference (see module docstring): the -1 / 1 / close-diff
    branches must not be swapped. Handcrafted so all three branches fire
    for the same symbol across the series.
    """
    dates = pd.bdate_range("2024-01-02", periods=30)
    # Handcrafted (not random) close path: diff86_t = (close[t-20] -
    # 2*close[t-10] + close[t]) / 10. With close[0:10]=close[20:30]=100
    # flat, only close[10:20] varies, so diff86 at t=20,21,22 (i=0,1,2 of
    # the varying block) is driven entirely by close[10+i]:
    #   i=0: close[10]=90  -> diff86 = (100-2*90+100)/10 = 2.0   (>0.25, branch -1)
    #   i=1: close[11]=150 -> diff86 = (100-2*150+100)/10 = -10.0 (<0, branch 1)
    #   i=2: close[12]=99  -> diff86 = (100-2*99+100)/10 = 0.2    (in [0,0.25], close-diff branch)
    #   i=3..9: close[13:20]=100 -> diff86 = 0 (also the close-diff branch)
    seg_a = [100.0] * 10
    seg_b = [90.0, 150.0, 99.0] + [100.0] * 7
    seg_c = [100.0] * 10
    close_vals = np.array(seg_a + seg_b + seg_c)
    frame = pd.DataFrame(
        {
            "symbol": "ONLY",
            "trade_date": dates,
            "open": close_vals - 0.1,
            "high": close_vals + 0.5,
            "low": close_vals - 0.5,
            "close": close_vals,
            "volume": 100_000.0,
            "vwap": close_vals,
        }
    )
    result = compute_alpha191(frame)
    close = pd.Series(close_vals, index=dates)
    delay20 = close.shift(20)
    delay10 = close.shift(10)
    delay1 = close.shift(1)
    diff86 = (delay20 - delay10) / 10.0 - (delay10 - close) / 10.0
    expected = pd.Series(np.nan, index=dates)
    valid = diff86.notna() & delay1.notna()
    branch_neg1 = valid & (diff86 > 0.25)
    branch_pos1 = valid & (diff86 < 0) & ~branch_neg1
    branch_close_diff = valid & ~branch_neg1 & ~branch_pos1
    expected[branch_neg1] = -1.0
    expected[branch_pos1] = 1.0
    expected[branch_close_diff] = (-1.0 * (close - delay1))[branch_close_diff]
    # Sanity: this handcrafted series must actually exercise every branch,
    # else the test would pass vacuously.
    assert branch_neg1.sum() > 0
    assert branch_pos1.sum() > 0
    assert branch_close_diff.sum() > 0
    merged = result.merge(
        expected.rename("expected").reset_index().rename(columns={"index": "trade_date"}),
        on="trade_date",
    )
    pd.testing.assert_series_equal(
        merged["gtja086"], merged["expected"], check_names=False, rtol=1e-8
    )


def test_gtja123_masks_nan_instead_of_fabricating_zero(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha191(ohlcv)
    high = _wide(ohlcv, "high")
    low = _wide(ohlcv, "low")
    volume = _wide(ohlcv, "volume")
    corr_a = (
        ((high + low) / 2.0)
        .rolling(20)
        .sum()
        .rolling(9)
        .corr(volume.rolling(60).mean().rolling(20).sum())
    )
    corr_b = low.rolling(6).corr(volume)
    rank_a = corr_a.rank(axis=1, pct=True)
    rank_b = corr_b.rank(axis=1, pct=True)
    expected = (rank_a < rank_b).astype(float) * -1.0
    expected = expected.where(rank_a.notna() & rank_b.notna())
    _merge_check(result, expected, "gtja123")
    # Every row with a defined result must be exactly 0 or -1 (a boolean
    # cast), never some other fabricated value.
    merged = result.loc[result["gtja123"].notna(), "gtja123"]
    assert set(merged.unique().tolist()) <= {0.0, -1.0}


def test_gtja190_bounded_and_finite(ohlcv_long: pd.DataFrame) -> None:
    """gtja190 is the most construction-heavy new id (COUNT/SUMIF via
    validity-masked rolling sums, then a guarded LOG) -- check it produces
    real finite values on a long fixture and never an inf, matching the
    "no gtja017-repeat" project rule."""
    result = compute_alpha191(ohlcv_long)
    col = result["gtja190"]
    assert col.notna().sum() > 0  # not vacuously all-NaN
    finite = col[np.isfinite(col)]
    assert np.isinf(col.dropna()).sum() == 0
    assert (finite.abs() < 50).all()  # log of a bounded ratio; nowhere near gtja017's ~1e300


def test_step15_new_ids_never_produce_inf(ohlcv_long: pd.DataFrame) -> None:
    """Blanket regression test for the project rule (module docstring):
    none of the 14 Step 15 Track A ids may reproduce gtja017's numeric
    degeneracy (values DuckDB cannot cast to FLOAT)."""
    result = compute_alpha191(ohlcv_long)
    new_columns = [
        "gtja039",
        "gtja046",
        "gtja049",
        "gtja054",
        "gtja063",
        "gtja071",
        "gtja073",
        "gtja084",
        "gtja086",
        "gtja123",
        "gtja155",
        "gtja161",
        "gtja184",
        "gtja190",
    ]
    values = result[new_columns].to_numpy(dtype="float64")
    assert not np.isinf(values).any()
    finite = values[np.isfinite(values)]
    assert finite.size > 0
    # Nowhere near gtja017's observed ~1e68..1e307 blowup. Generous
    # headroom above gtja084/gtja155's legitimate dollar/share-volume
    # scale (rolling sums of raw `volume`, easily in the 1e6-1e7 range for
    # a liquid symbol) -- the point of this bound is to catch a genuine
    # exponent-style explosion, not to constrain ordinary volume units.
    assert np.nanmax(np.abs(finite)) < 1e9


def test_build_alpha191_features_empty_universe(tmp_path: Path) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    result = build_alpha191_features(str(daily_dir / "*.parquet"), [])
    assert list(result.columns) == ["symbol", "trade_date", *ALPHA191_COLUMNS]
    assert len(result) == 0
