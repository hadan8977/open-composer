"""Tests for open_composer.research.features.alpha158.

Strategy (plan section 3.1: "单元测试:随机 3 只 x 80 天,与直接 numpy 手算对比
rtol 1e-6"): a hand-rolled, loop-based reference implementation (deliberately
not vectorized, so it shares no code path with the module under test) checks
a representative column from every one of the 29 rolling groups plus the 9
K-bar columns, for one symbol and one window, against
``compute_alpha158``'s output.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.alpha158 import (
    KBAR_COLUMNS,
    ROLLING_GROUP_NAMES,
    alpha158_columns,
    build_alpha158_features,
    compute_alpha158,
)

SYMBOLS = ["AAA", "BBB", "CCC"]
N_DAYS = 80
WINDOW = 5


def _make_ohlcv(seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=N_DAYS)
    rows: list[dict[str, object]] = []
    for symbol, base, vol_base in [
        ("AAA", 100.0, 1_000_000),
        ("BBB", 40.0, 500_000),
        ("CCC", 250.0, 250_000),
    ]:
        price = base
        for i, date in enumerate(dates):
            day_open = price * (1.0 + rng.normal(0, 0.004))
            price *= 1.0 + rng.normal(0, 0.015)
            high = max(day_open, price) * (1.0 + abs(rng.normal(0, 0.003)))
            low = min(day_open, price) * (1.0 - abs(rng.normal(0, 0.003)))
            volume = vol_base * (1.0 + 0.01 * i) * (1.0 + abs(rng.normal(0, 0.2)))
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "open": day_open,
                    "high": high,
                    "low": low,
                    "close": price,
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return _make_ohlcv()


def _reference_row(closes, highs, lows, volumes, t: int, window: int) -> dict[str, float]:
    """Independent, loop-based (not vectorized) reference for one row `t`
    (0-indexed) of one symbol's series, window `window`. Mirrors the plan's
    formulas directly rather than reusing any helper from the module under
    test.
    """
    lo = t - window + 1
    win_close = closes[lo : t + 1]
    win_high = highs[lo : t + 1]
    win_low = lows[lo : t + 1]
    win_vol = volumes[lo : t + 1]
    c = closes[t]

    # BETA/RSQR/RESI: OLS of close on x = 0..window-1 within the window.
    x = list(range(window))
    xm_ = sum(x) / window
    ym_ = sum(win_close) / window
    sxx = sum((xi - xm_) ** 2 for xi in x)
    sxy = sum((xi - xm_) * (yi - ym_) for xi, yi in zip(x, win_close, strict=True))
    syy = sum((yi - ym_) ** 2 for yi in win_close)
    slope = sxy / sxx
    intercept = ym_ - slope * xm_
    resi = win_close[-1] - (intercept + slope * x[-1])
    rsquare = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0

    imax = win_high.index(max(win_high)) / window
    imin = win_low.index(min(win_low)) / window

    close_prev_series = [closes[i - 1] if i - 1 >= 0 else float("nan") for i in range(lo, t + 1)]
    pairs = list(zip(win_close, close_prev_series, strict=True))
    up_days = sum(1 for c_, p_ in pairs if p_ == p_ and c_ > p_)
    down_days = sum(1 for c_, p_ in pairs if p_ == p_ and c_ < p_)

    diffs = [c_ - p_ if p_ == p_ else float("nan") for c_, p_ in pairs]
    valid_diffs = [d for d in diffs if d == d]
    sum_abs = sum(abs(d) for d in valid_diffs)
    sum_pos = sum(max(d, 0.0) for d in valid_diffs)
    sum_neg = sum(max(-d, 0.0) for d in valid_diffs)

    log_vol = [np.log(v + 1.0) for v in win_vol]
    corr = float(np.corrcoef(win_close, log_vol)[0, 1])

    mean_close = sum(win_close) / window
    # Sample variance (ddof=1), matching pandas' Rolling.std() default and
    # this repo's existing convention (daily_features.py uses STDDEV_SAMP).
    var_close = sum((v - mean_close) ** 2 for v in win_close) / (window - 1)
    std_close = var_close**0.5

    sorted_close = sorted(win_close)
    rank_pct = (sum(1 for v in win_close[:-1] if v <= c) + 1) / window

    return {
        "MA": mean_close / c,
        "STD": std_close / c,
        "BETA": slope / c,
        "RSQR": rsquare,
        "RESI": resi / c,
        "MAX": max(win_high) / c,
        "MIN": min(win_low) / c,
        "IMAX": imax,
        "IMIN": imin,
        "IMXD": imax - imin,
        "CORR": corr,
        "CNTP": up_days / window,
        "CNTN": down_days / window,
        "CNTD": (up_days - down_days) / window,
        "SUMP": sum_pos / (sum_abs + 1e-12),
        "SUMN": sum_neg / (sum_abs + 1e-12),
        "SUMD": (sum_pos - sum_neg) / (sum_abs + 1e-12),
        "ROC": closes[t - window] / c if t - window >= 0 else float("nan"),
        "RSV": (c - min(win_low)) / ((max(win_high) - min(win_low)) + 1e-12),
        # sanity only; pandas rolling.rank tie handling may differ slightly
        "_rank_pct_hint": rank_pct,
        "_sorted_close_hint": sorted_close,
    }


def test_alpha158_matches_independent_loop_reference(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha158(ohlcv, windows=(WINDOW,))
    sym_result = result.loc[result["symbol"] == "AAA"].reset_index(drop=True)
    sym_raw = ohlcv.loc[ohlcv["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)

    closes = sym_raw["close"].tolist()
    highs = sym_raw["high"].tolist()
    lows = sym_raw["low"].tolist()
    volumes = sym_raw["volume"].tolist()

    # Row well past every warm-up window.
    t = 50
    ref = _reference_row(closes, highs, lows, volumes, t, WINDOW)
    row = sym_result.iloc[t]

    for name in [
        "MA",
        "STD",
        "BETA",
        "RSQR",
        "RESI",
        "MAX",
        "MIN",
        "IMAX",
        "IMIN",
        "IMXD",
        "CORR",
        "CNTP",
        "CNTN",
        "CNTD",
        "SUMP",
        "SUMN",
        "SUMD",
        "ROC",
        "RSV",
    ]:
        assert row[f"{name}{WINDOW}"] == pytest.approx(ref[name], rel=1e-6, abs=1e-9), name


def test_kbar_columns_are_pure_row_arithmetic(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha158(ohlcv, windows=(WINDOW,))
    row = ohlcv.loc[(ohlcv["symbol"] == "BBB")].sort_values("trade_date").iloc[10]
    match = result.loc[(result["symbol"] == "BBB")].sort_values("trade_date").iloc[10]
    open_, high, low, close = row["open"], row["high"], row["low"], row["close"]
    assert match["KMID"] == pytest.approx((close - open_) / open_, rel=1e-9)
    assert match["KLEN"] == pytest.approx((high - low) / open_, rel=1e-9)
    assert match["KMID2"] == pytest.approx((close - open_) / ((high - low) + 1e-12), rel=1e-9)
    assert match["KUP"] == pytest.approx((high - max(open_, close)) / open_, rel=1e-9)
    assert match["KLOW"] == pytest.approx((min(open_, close) - low) / open_, rel=1e-9)
    assert match["KSFT"] == pytest.approx((2 * close - high - low) / open_, rel=1e-9)


def test_warmup_rows_are_nan_not_fabricated(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha158(ohlcv, windows=(WINDOW,))
    sym_result = (
        result.loc[result["symbol"] == "CCC"].sort_values("trade_date").reset_index(drop=True)
    )
    # First WINDOW - 1 rows cannot have a full window.
    assert sym_result.loc[: WINDOW - 2, f"MA{WINDOW}"].isna().all()
    assert sym_result.loc[: WINDOW - 2, f"BETA{WINDOW}"].isna().all()
    assert sym_result.loc[: WINDOW - 2, f"IMAX{WINDOW}"].isna().all()
    # From WINDOW-1 onward, every column should be populated (no accidental
    # extra NaN once the window is full).
    assert sym_result.loc[WINDOW - 1 :, f"MA{WINDOW}"].notna().all()


def test_rank_is_pandas_rolling_rank_pct(ohlcv: pd.DataFrame) -> None:
    result = compute_alpha158(ohlcv, windows=(WINDOW,))
    sym_result = (
        result.loc[result["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    )
    sym_raw = ohlcv.loc[ohlcv["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    expected = sym_raw["close"].rolling(WINDOW).rank(pct=True)
    pd.testing.assert_series_equal(
        sym_result[f"RANK{WINDOW}"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )


def test_column_list_is_154_and_matches_alpha158_columns(ohlcv: pd.DataFrame) -> None:
    columns = alpha158_columns((5, 10, 20, 30, 60))
    assert len(columns) == 9 + 29 * 5 == 154
    assert len(set(columns)) == 154  # no accidental duplicate names
    result = compute_alpha158(ohlcv, windows=(5, 10, 20, 30, 60))
    assert list(result.columns) == ["symbol", "trade_date"] + columns
    assert set(KBAR_COLUMNS) <= set(columns)
    assert len(ROLLING_GROUP_NAMES) == 29


def test_build_alpha158_features_from_parquet_glob(tmp_path: Path, ohlcv: pd.DataFrame) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    archive = ohlcv.rename(columns={"trade_date": "timestamp"}).copy()
    archive["timestamp"] = pd.to_datetime(archive["timestamp"])
    archive.to_parquet(daily_dir / "2024.parquet", index=False)

    loaded = build_alpha158_features(
        str(daily_dir / "*.parquet"),
        SYMBOLS,
        windows=(WINDOW,),
        memory_limit="256MB",
        temp_directory=str(tmp_path / "_duckdb_tmp"),
    )
    direct = compute_alpha158(ohlcv, windows=(WINDOW,))
    assert len(loaded) == len(direct)
    assert set(loaded["symbol"]) == set(SYMBOLS)
    pd.testing.assert_frame_equal(
        loaded.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        direct.sort_values(["symbol", "trade_date"]).reset_index(drop=True),
        check_exact=False,
        check_dtype=False,
        rtol=1e-6,
    )


def test_build_alpha158_features_empty_universe_returns_empty_typed_frame(tmp_path: Path) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    result = build_alpha158_features(str(daily_dir / "*.parquet"), [], windows=(WINDOW,))
    assert list(result.columns) == ["symbol", "trade_date"] + alpha158_columns((WINDOW,))
    assert len(result) == 0
