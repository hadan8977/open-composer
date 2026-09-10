"""Tests for open_composer.research.features._panel_ops."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features import _panel_ops as ops

DATES = pd.bdate_range("2024-01-02", periods=15)
COLUMNS = ["AAA", "BBB", "CCC"]


@pytest.fixture
def wide() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(rng.normal(size=(15, 3)), index=DATES, columns=COLUMNS)


def test_rank_is_cross_sectional_per_row(wide: pd.DataFrame) -> None:
    result = ops.rank(wide)
    for date in DATES:
        row = wide.loc[date]
        expected = row.rank(pct=True)
        pd.testing.assert_series_equal(result.loc[date], expected, check_names=False)


def test_delta_and_delay(wide: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(ops.delta(wide, 2), wide.diff(2))
    pd.testing.assert_frame_equal(ops.delay(wide, 3), wide.shift(3))


def test_ts_sum_sma_stddev_are_native_rolling(wide: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(ops.ts_sum(wide, 4), wide.rolling(4).sum())
    pd.testing.assert_frame_equal(ops.sma(wide, 4), wide.rolling(4).mean())
    pd.testing.assert_frame_equal(ops.stddev(wide, 4), wide.rolling(4).std())


def test_correlation_and_covariance_are_elementwise_per_column(wide: pd.DataFrame) -> None:
    other = wide.iloc[::-1].reset_index(drop=True).set_axis(wide.index)
    corr = ops.correlation(wide, other, 5)
    cov = ops.covariance(wide, other, 5)
    for column in COLUMNS:
        expected_corr = wide[column].rolling(5).corr(other[column])
        expected_cov = wide[column].rolling(5).cov(other[column])
        pd.testing.assert_series_equal(corr[column], expected_corr, check_names=False)
        pd.testing.assert_series_equal(cov[column], expected_cov, check_names=False)


def test_ts_min_max_rank(wide: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(ops.ts_min(wide, 5), wide.rolling(5).min())
    pd.testing.assert_frame_equal(ops.ts_max(wide, 5), wide.rolling(5).max())
    pd.testing.assert_frame_equal(ops.ts_rank(wide, 5), wide.rolling(5).rank(pct=True))


def test_ts_argmax_argmin_match_a_naive_per_column_python_loop(wide: pd.DataFrame) -> None:
    window = 4
    argmax = ops.ts_argmax(wide, window)
    argmin = ops.ts_argmin(wide, window)
    values = wide.to_numpy()
    n_rows = values.shape[0]
    for col_idx in range(len(COLUMNS)):
        for row_idx in range(n_rows):
            if row_idx < window - 1:
                assert np.isnan(argmax.iloc[row_idx, col_idx])
                assert np.isnan(argmin.iloc[row_idx, col_idx])
                continue
            win = values[row_idx - window + 1 : row_idx + 1, col_idx]
            assert argmax.iloc[row_idx, col_idx] == float(np.argmax(win))
            assert argmin.iloc[row_idx, col_idx] == float(np.argmin(win))
    assert list(argmax.columns) == COLUMNS
    assert list(argmax.index) == list(wide.index)


def test_sign_and_safe_log(wide: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(ops.sign(wide), np.sign(wide))
    positive = wide.abs() + 1.0
    log_result = ops.safe_log(positive)
    pd.testing.assert_frame_equal(log_result, np.log(positive))
    with_zero = positive.copy()
    with_zero.iloc[0, 0] = 0.0
    with_zero.iloc[1, 1] = -3.0
    guarded = ops.safe_log(with_zero)
    assert np.isnan(guarded.iloc[0, 0])
    assert np.isnan(guarded.iloc[1, 1])


def test_recursive_ewm_matches_manual_recursion(wide: pd.DataFrame) -> None:
    n, m = 7, 2
    result = ops.recursive_ewm(wide, n, m)
    alpha = m / n
    column = wide["AAA"].to_numpy()
    manual = np.empty_like(column)
    manual[0] = column[0]
    for i in range(1, len(column)):
        manual[i] = alpha * column[i] + (1 - alpha) * manual[i - 1]
    np.testing.assert_allclose(result["AAA"].to_numpy(), manual, rtol=1e-10)


def test_replace_inf_with_nan(wide: pd.DataFrame) -> None:
    dirty = wide.copy()
    dirty.iloc[0, 0] = np.inf
    dirty.iloc[1, 1] = -np.inf
    cleaned = ops.replace_inf_with_nan(dirty)
    assert np.isnan(cleaned.iloc[0, 0])
    assert np.isnan(cleaned.iloc[1, 1])
    assert cleaned.iloc[2, 2] == pytest.approx(dirty.iloc[2, 2])
