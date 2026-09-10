"""Tests for open_composer.research.features.osap_price."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.osap_price import (
    OSAP_PRICE_COLUMNS,
    TREND_MA_WINDOWS,
    add_momvol_cross_sectional,
    build_osap_price_features,
)

SYMBOLS = ["AAA", "BBB"]
MARKET = "SPY"
N_DAYS = 900  # > 756 so lrreversal/momseason_2_5 are populated for the later rows


def _make_ohlcv(seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-02", periods=N_DAYS)
    rows: list[dict[str, object]] = []
    for symbol, base, vol_base in [
        ("AAA", 70.0, 400_000),
        ("BBB", 25.0, 250_000),
        (MARKET, 300.0, 3_000_000),
    ]:
        price = base
        for date in dates:
            price *= 1.0 + rng.normal(0.0003, 0.013)
            volume = vol_base * (1.0 + abs(rng.normal(0, 0.2)))
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": date,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def parquet_path(tmp_path: Path) -> Path:
    frame = _make_ohlcv()
    path = tmp_path / "2020.parquet"
    frame.to_parquet(path, index=False)
    return path


@pytest.fixture
def raw_frame(parquet_path: Path) -> pd.DataFrame:
    return pd.read_parquet(parquet_path)


def test_column_list_matches_declared_manifest(parquet_path: Path) -> None:
    per_symbol = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    final = add_momvol_cross_sectional(per_symbol)
    assert list(final.columns) == ["symbol", "trade_date", *OSAP_PRICE_COLUMNS]
    assert len(OSAP_PRICE_COLUMNS) == 25  # 24 per-symbol + momvol
    assert len({f"trend_ma{w}" for w in TREND_MA_WINDOWS} & set(final.columns)) == 7


def test_mom6m_mom12m_streversal_lrreversal_match_direct_pandas(
    parquet_path: Path, raw_frame: pd.DataFrame
) -> None:
    result = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    sym = (
        raw_frame.loc[raw_frame["symbol"] == "AAA"].sort_values("timestamp").reset_index(drop=True)
    )
    close = sym["close"]
    ret_21 = close / close.shift(21) - 1.0
    ret_126 = close / close.shift(126) - 1.0
    ret_252 = close / close.shift(252) - 1.0
    ret_756 = close / close.shift(756) - 1.0
    expected_mom6m = (ret_126 - ret_21).to_numpy()
    expected_mom12m = (ret_252 - ret_21).to_numpy()
    expected_streversal = (-ret_21).to_numpy()
    expected_lrreversal = (-(ret_756 - ret_252)).to_numpy()

    sym_result = (
        result.loc[result["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    )
    np.testing.assert_allclose(
        sym_result["mom6m"].to_numpy(), expected_mom6m, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(
        sym_result["mom12m"].to_numpy(), expected_mom12m, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(
        sym_result["streversal"].to_numpy(), expected_streversal, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(
        sym_result["lrreversal"].to_numpy(), expected_lrreversal, rtol=1e-6, equal_nan=True
    )


def test_maxret_realizedvol_logprice_trendma_match_direct_pandas(
    parquet_path: Path, raw_frame: pd.DataFrame
) -> None:
    result = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    sym = (
        raw_frame.loc[raw_frame["symbol"] == "BBB"].sort_values("timestamp").reset_index(drop=True)
    )
    close = sym["close"]
    ret_1 = close / close.shift(1) - 1.0
    expected_maxret = ret_1.rolling(21).max().to_numpy()
    expected_vol21 = ret_1.rolling(21).std().to_numpy()
    expected_vol63 = ret_1.rolling(63).std().to_numpy()
    expected_log_price = np.log(close.to_numpy())
    expected_trend_ma20 = (close.rolling(20).mean() / close).to_numpy()

    sym_result = (
        result.loc[result["symbol"] == "BBB"].sort_values("trade_date").reset_index(drop=True)
    )
    np.testing.assert_allclose(
        sym_result["maxret"].to_numpy(), expected_maxret, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(
        sym_result["realizedvol_21"].to_numpy(), expected_vol21, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(
        sym_result["realizedvol_63"].to_numpy(), expected_vol63, rtol=1e-6, equal_nan=True
    )
    np.testing.assert_allclose(sym_result["log_price"].to_numpy(), expected_log_price, rtol=1e-9)
    np.testing.assert_allclose(
        sym_result["trend_ma20"].to_numpy(), expected_trend_ma20, rtol=1e-6, equal_nan=True
    )


def test_idiovol_spy_63_matches_daily_features_closed_form(
    parquet_path: Path, raw_frame: pd.DataFrame
) -> None:
    """Same construction as daily_features.py's idio_vol_63 -- recomputed
    independently here (this module has no import-time dependency on that
    one) via the textbook closed form for one-regressor OLS residual
    variance: Var(resid) = Var(y) * (1 - corr(x,y)^2).
    """
    result = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    aaa = (
        raw_frame.loc[raw_frame["symbol"] == "AAA"].sort_values("timestamp").reset_index(drop=True)
    )
    spy = (
        raw_frame.loc[raw_frame["symbol"] == MARKET].sort_values("timestamp").reset_index(drop=True)
    )
    ret_aaa = aaa["close"] / aaa["close"].shift(1) - 1.0
    ret_spy = spy["close"] / spy["close"].shift(1) - 1.0
    expected = (
        ret_aaa.rolling(63).std() * np.sqrt(1 - ret_aaa.rolling(63).corr(ret_spy) ** 2)
    ).to_numpy()

    sym_result = (
        result.loc[result["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    )
    np.testing.assert_allclose(
        sym_result["idiovol_spy_63"].to_numpy(), expected, rtol=1e-6, equal_nan=True
    )


def _ols_r2(y: np.ndarray, x_columns: list[np.ndarray]) -> float:
    x = np.column_stack([np.ones_like(y), *x_columns])
    coeffs, *_ = np.linalg.lstsq(x, y, rcond=None)
    predicted = x @ coeffs
    ss_res = np.sum((y - predicted) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return 1.0 - ss_res / ss_tot


def test_pricedelay_rsq_matches_numpy_lstsq_over_one_window(
    parquet_path: Path, raw_frame: pd.DataFrame
) -> None:
    """The closed-form partial-R^2 identity used in the SQL query is
    cross-checked against an independent numpy least-squares solve over
    one concrete 252-day window (row 500 of AAA), rather than trusting the
    algebra alone.
    """
    result = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    aaa = (
        raw_frame.loc[raw_frame["symbol"] == "AAA"].sort_values("timestamp").reset_index(drop=True)
    )
    spy = (
        raw_frame.loc[raw_frame["symbol"] == MARKET].sort_values("timestamp").reset_index(drop=True)
    )
    ret_aaa = (aaa["close"] / aaa["close"].shift(1) - 1.0).to_numpy()
    ret_spy = (spy["close"] / spy["close"].shift(1) - 1.0).to_numpy()

    row = 500
    window = slice(row - 251, row + 1)
    y = ret_aaa[window]
    x1 = ret_spy[window]
    x2 = np.concatenate([[np.nan], ret_spy[window][:-1]])  # lag-1 within the window
    # Drop the first observation (no lag available) for a clean, equal-length fit.
    y_fit, x1_fit, x2_fit = y[1:], x1[1:], x2[1:]
    r2_restricted = _ols_r2(y_fit, [x1_fit])
    r2_full = _ols_r2(y_fit, [x1_fit, x2_fit])
    expected = r2_full - r2_restricted

    sym_result = (
        result.loc[result["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    )
    actual = sym_result["pricedelay_rsq"].iloc[row]
    assert actual == pytest.approx(expected, rel=1e-2, abs=1e-3)


def test_coskew_252_matches_numpy_lstsq_partial_slope_over_one_window(
    parquet_path: Path, raw_frame: pd.DataFrame
) -> None:
    result = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    aaa = (
        raw_frame.loc[raw_frame["symbol"] == "AAA"].sort_values("timestamp").reset_index(drop=True)
    )
    spy = (
        raw_frame.loc[raw_frame["symbol"] == MARKET].sort_values("timestamp").reset_index(drop=True)
    )
    ret_aaa = (aaa["close"] / aaa["close"].shift(1) - 1.0).to_numpy()
    ret_spy = (spy["close"] / spy["close"].shift(1) - 1.0).to_numpy()

    row = 500
    window = slice(row - 251, row + 1)
    y = ret_aaa[window]
    x1 = ret_spy[window]
    x2 = x1**2
    x = np.column_stack([np.ones_like(y), x1, x2])
    coeffs, *_ = np.linalg.lstsq(x, y, rcond=None)
    expected_b2 = coeffs[2]

    sym_result = (
        result.loc[result["symbol"] == "AAA"].sort_values("trade_date").reset_index(drop=True)
    )
    actual = sym_result["coskew_252"].iloc[row]
    assert actual == pytest.approx(expected_b2, rel=1e-2, abs=1e-3)


def test_add_momvol_cross_sectional_uses_whole_universe_percentile(parquet_path: Path) -> None:
    per_symbol = build_osap_price_features(
        [str(parquet_path)],
        SYMBOLS,
        memory_limit="512MB",
        temp_directory=str(parquet_path.parent / "tmp"),
    )
    final = add_momvol_cross_sectional(per_symbol)
    one_date = final["trade_date"].iloc[-1]
    day_rows = final.loc[final["trade_date"] == one_date].set_index("symbol")
    assert len(day_rows) == len(SYMBOLS)
    # momvol = momentum_252_21 * cross-sectional percentile rank of dolvol_63;
    # with exactly 2 symbols, pandas' pct rank is {0.5, 1.0}.
    higher_dolvol_symbol = day_rows["dolvol_63"].idxmax()
    lower_dolvol_symbol = day_rows["dolvol_63"].idxmin()
    assert day_rows.loc[higher_dolvol_symbol, "momvol"] == pytest.approx(
        day_rows.loc[higher_dolvol_symbol, "mom12m"] * 1.0
    )
    assert day_rows.loc[lower_dolvol_symbol, "momvol"] == pytest.approx(
        day_rows.loc[lower_dolvol_symbol, "mom12m"] * 0.5
    )


def test_empty_universe_returns_empty_typed_frame(tmp_path: Path) -> None:
    empty_glob = str(tmp_path / "*.parquet")
    result = build_osap_price_features(empty_glob, [])
    assert "symbol" in result.columns and "trade_date" in result.columns
    assert len(result) == 0
