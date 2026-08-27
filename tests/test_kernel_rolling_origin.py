from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_composer.research.kernel.rolling_origin import (
    returns_from_ohlcv,
    rolling_origin_folds,
)

ROOT = Path(__file__).resolve().parents[1]


def _synthetic_returns(*, years: list[int], first_day: str = "01-01") -> pd.Series:
    parts = []
    for year in years:
        index = pd.bdate_range(f"{year}-{first_day}", f"{year}-12-31", tz="UTC")
        parts.append(pd.Series(0.001, index=index))
    return pd.concat(parts).sort_index()


def test_folds_never_train_on_future_data() -> None:
    returns = _synthetic_returns(years=[2020, 2021, 2022, 2023, 2024])
    folds, _stitched = rolling_origin_folds(returns, fold_count=3, embargo_bars=5)
    assert len(folds) == 3
    for fold in folds:
        train_end = pd.Timestamp(fold.train.train_end)
        test_start = pd.Timestamp(fold.train.test_start)
        assert train_end < test_start


def test_folds_respect_embargo_gap() -> None:
    returns = _synthetic_returns(years=[2020, 2021, 2022])
    embargo_bars = 5
    folds, _stitched = rolling_origin_folds(returns, fold_count=1, embargo_bars=embargo_bars)
    (fold,) = folds
    full_index = returns.sort_index().index
    test_start = pd.Timestamp(fold.train.test_start)
    train_end = pd.Timestamp(fold.train.train_end)
    gap_positions = full_index[(full_index > train_end) & (full_index < test_start)]
    assert len(gap_positions) == embargo_bars


def test_stitched_series_has_no_duplicates_and_is_sorted() -> None:
    returns = _synthetic_returns(years=[2020, 2021, 2022, 2023, 2024, 2025])
    _folds, stitched = rolling_origin_folds(returns, fold_count=4, embargo_bars=3)
    assert not stitched.index.has_duplicates
    assert stitched.index.is_monotonic_increasing


def test_stitched_series_covers_exactly_the_test_years() -> None:
    returns = _synthetic_returns(years=[2020, 2021, 2022, 2023])
    folds, stitched = rolling_origin_folds(returns, fold_count=2, embargo_bars=2)
    test_years = {pd.Timestamp(fold.train.test_start).year for fold in folds}
    assert test_years == {2022, 2023}
    assert set(stitched.index.year.unique()) == {2022, 2023}


def test_explicit_test_years_override_default_selection() -> None:
    returns = _synthetic_returns(years=[2018, 2019, 2020, 2021, 2022])
    folds, stitched = rolling_origin_folds(returns, embargo_bars=2, test_years=[2020, 2022])
    assert [fold.fold for fold in folds] == [1, 2]
    assert set(stitched.index.year.unique()) == {2020, 2022}


def test_rejects_non_chronological_explicit_years() -> None:
    returns = _synthetic_returns(years=[2020, 2021, 2022])
    with pytest.raises(ValueError, match="chronological order"):
        rolling_origin_folds(returns, test_years=[2022, 2020])


def test_rejects_insufficient_training_history_for_embargo() -> None:
    returns = _synthetic_returns(years=[2020, 2021])
    with pytest.raises(ValueError, match="not enough"):
        rolling_origin_folds(returns, test_years=[2020], embargo_bars=10_000)


def test_rejects_more_folds_than_available_years() -> None:
    returns = _synthetic_returns(years=[2020, 2021])
    with pytest.raises(ValueError, match="cannot build"):
        rolling_origin_folds(returns, fold_count=5)


def test_rejects_duplicate_timestamps_in_input() -> None:
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-01", "2020-01-02"], tz="UTC")
    returns = pd.Series([0.01, 0.02, 0.01], index=index)
    with pytest.raises(ValueError, match="duplicate"):
        rolling_origin_folds(returns, test_years=[2020])


def test_returns_from_ohlcv_computes_simple_returns_sorted_by_time() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": ["2020-01-03", "2020-01-01", "2020-01-02"],
            "open": [1.0, 1.0, 1.0],
            "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0],
            "close": [102.0, 100.0, 101.0],
            "volume": [10, 10, 10],
        }
    )
    returns = returns_from_ohlcv(frame)
    assert list(returns.index.sort_values()) == list(returns.index)
    assert returns.iloc[0] == pytest.approx(0.01)
    assert returns.iloc[1] == pytest.approx(1.0 / 101.0)


def test_end_to_end_stitched_oos_row_count_matches_real_qqq_window() -> None:
    frame = pd.read_csv(ROOT / "data" / "cache" / "qqq_daily_iex.csv")
    returns = returns_from_ohlcv(frame)
    folds, stitched = rolling_origin_folds(returns, fold_count=5)
    assert len(folds) == 5
    assert 1000 <= len(stitched) <= 1300
    for fold in folds:
        train_end = pd.Timestamp(fold.train.train_end)
        test_start = pd.Timestamp(fold.train.test_start)
        assert train_end < test_start
