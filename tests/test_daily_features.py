"""Tests for open_composer.research.features.daily_features.

Strategy: cross-validate the DuckDB pipeline against an independent pandas
computation of the same quantities (pct_change/rolling/groupby-median)
rather than hand-deriving expected floats -- two independent
implementations agreeing is stronger evidence than either one alone, and
catches transcription slips a hand-derived fixture would not.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.daily_features import (
    build_daily_features,
    join_intraday_rolling_features,
)

SYMBOLS = ["AAA", "BBB", "CCC"]
MARKET = "SPY"
WINDOW_KW = dict(
    return_windows=(1, 3, 5, 10),
    vol_windows=(3, 5),
    beta_window=10,
    idio_vol_window=5,
    max_return_window=5,
    adv_windows=(5, 10),
    amihud_window=5,
    high_window=10,
    momentum_long_window=10,
    momentum_skip_window=3,
    memory_limit="512MB",
)


def _write_fixture(root: Path, n_days: int = 40, seed: int = 11) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for symbol, base, vol_base in [
        ("AAA", 100.0, 1_000_000),
        ("BBB", 50.0, 400_000),
        ("CCC", 75.0, 700_000),
        (MARKET, 300.0, 2_000_000),
    ]:
        price = base
        for i, date in enumerate(dates):
            price *= 1.0 + rng.normal(0, 0.012)
            volume = vol_base * (1 + 0.01 * i)
            rows.append({"symbol": symbol, "timestamp": date, "close": price, "volume": volume})
    frame = pd.DataFrame(rows)
    year_dir = root / "2020"
    year_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(year_dir / "shard-0000.parquet", index=False)
    return frame


@pytest.fixture
def fixture_frame_and_glob(tmp_path: Path) -> tuple[pd.DataFrame, str]:
    raw = _write_fixture(tmp_path)
    return raw, str(tmp_path / "*" / "*.parquet")


def _independent_pandas_returns(raw: pd.DataFrame) -> pd.DataFrame:
    """Reference implementation of the return columns via plain pandas,
    used to cross-check the DuckDB query's return/vol arithmetic.
    """
    wide = raw.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    out = {}
    for window in (1, 3, 5, 10):
        out[f"ret_{window}"] = wide.pct_change(window)
    return out, wide


def test_returns_match_independent_pandas_pct_change(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    raw, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    expected, _ = _independent_pandas_returns(raw)

    for symbol in SYMBOLS:
        got = result.loc[result["symbol"] == symbol].set_index("trade_date")
        for window in (1, 3, 5, 10):
            exp_series = expected[f"ret_{window}"][symbol]
            exp_series.index = pd.to_datetime(exp_series.index)
            aligned_expected = exp_series.reindex(got.index)
            pd.testing.assert_series_equal(
                got[f"ret_{window}"],
                aligned_expected,
                check_names=False,
                rtol=1e-9,
            )


def test_warm_up_period_is_null_not_fabricated(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    first_two = result.groupby("symbol").head(2)
    assert first_two["ret_10"].isna().all()
    assert first_two["vol_5"].isna().all()
    assert first_two["beta_10_spy"].isna().all()


def test_vol_matches_independent_rolling_stddev(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    raw, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    wide_close = raw.pivot(index="timestamp", columns="symbol", values="close").sort_index()
    ret_1 = wide_close.pct_change(1)
    expected_vol_5 = ret_1.rolling(5).std(ddof=1)

    for symbol in SYMBOLS:
        got = result.loc[result["symbol"] == symbol].set_index("trade_date")["vol_5"]
        exp = expected_vol_5[symbol]
        exp.index = pd.to_datetime(exp.index)
        pd.testing.assert_series_equal(got, exp.reindex(got.index), check_names=False, rtol=1e-8)


def test_market_relative_return_subtracts_same_day_cross_sectional_median(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    non_null = result.dropna(subset=["ret_1"])
    for _trade_date, group in non_null.groupby("trade_date"):
        expected_median = group["ret_1"].median()
        reconstructed = group["ret_1"] - expected_median
        pd.testing.assert_series_equal(
            group["ret_1_rel"].reset_index(drop=True),
            reconstructed.reset_index(drop=True),
            check_names=False,
            rtol=1e-9,
        )


def test_momentum_is_long_return_minus_skip_return(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    non_null = result.dropna(subset=["ret_10", "ret_3"])
    pd.testing.assert_series_equal(
        non_null["momentum_10_3"].reset_index(drop=True),
        (non_null["ret_10"] - non_null["ret_3"]).reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_amihud_is_positive_and_finite_where_defined(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    defined = result["amihud_5"].dropna()
    assert (defined >= 0).all()
    assert np.isfinite(defined).all()


def test_dist_from_high_is_never_positive(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    defined = result["dist_from_10d_high"].dropna()
    assert (defined <= 1e-12).all()


def test_market_symbol_itself_is_excluded_from_the_output(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, SYMBOLS, market_symbol=MARKET, **WINDOW_KW)
    assert MARKET not in set(result["symbol"])


def test_empty_universe_returns_empty_frame(
    fixture_frame_and_glob: tuple[pd.DataFrame, str],
) -> None:
    _, glob = fixture_frame_and_glob
    result = build_daily_features(glob, [], market_symbol=MARKET, **WINDOW_KW)
    assert len(result) == 0


def test_join_intraday_rolling_features_computes_trailing_means() -> None:
    daily = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "ret_1": [0.01, 0.02, 0.03],
        }
    )
    intraday = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "overnight_return": [0.001, 0.002, 0.003],
            "intraday_return": [0.01, -0.01, 0.02],
            "intraday_realized_vol": [0.001, 0.0015, 0.002],
            "intraday_amplitude": [0.02, 0.03, 0.01],
            "open_30min_volume_share": [0.2, 0.3, 0.1],
            "close_30min_volume_share": [0.2, 0.1, 0.3],
            "vwap_deviation": [0.001, -0.002, 0.0015],
            "intraday_skew": [0.1, -0.2, 0.3],
            "trade_count": [100, 150, 120],
            "amihud_intraday": [1e-9, 2e-9, 1.5e-9],
        }
    )
    merged = join_intraday_rolling_features(daily, intraday, rolling_windows=(2,))
    assert "overnight_return_2d_mean" in merged.columns
    # Row 2 (2024-01-03): mean of days 1-2's overnight_return = mean(0.001, 0.002).
    row = merged.loc[merged["trade_date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert row["overnight_return_2d_mean"] == pytest.approx((0.001 + 0.002) / 2)
    # Row 1 (2024-01-02, min_periods=1): mean of just itself.
    row0 = merged.loc[merged["trade_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert row0["overnight_return_2d_mean"] == pytest.approx(0.001)


def test_join_intraday_rolling_features_left_join_keeps_daily_only_rows() -> None:
    daily = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "ret_1": [0.01, 0.02],
        }
    )
    intraday = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "trade_date": pd.to_datetime(["2024-01-02"]),
            "overnight_return": [0.001],
            "intraday_return": [0.01],
            "intraday_realized_vol": [0.001],
            "intraday_amplitude": [0.02],
            "open_30min_volume_share": [0.2],
            "close_30min_volume_share": [0.2],
            "vwap_deviation": [0.001],
            "intraday_skew": [0.1],
            "trade_count": [100],
            "amihud_intraday": [1e-9],
        }
    )
    merged = join_intraday_rolling_features(daily, intraday, rolling_windows=(2,))
    assert len(merged) == 2
    bbb_row = merged.loc[merged["symbol"] == "BBB"].iloc[0]
    assert pd.isna(bbb_row["overnight_return_2d_mean"])
