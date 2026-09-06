"""Tests for open_composer.research.features.labels."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_composer.research.features.labels import build_labels

SYMBOLS = ["AAA", "BBB", "CCC"]


def _write_fixture(root: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=15)
    # Deterministic prices: AAA always beats the pack, CCC always trails.
    rows = []
    for i, date in enumerate(dates):
        rows.append({"symbol": "AAA", "timestamp": date, "close": 100.0 * (1.02**i)})
        rows.append({"symbol": "BBB", "timestamp": date, "close": 100.0 * (1.00**i)})
        rows.append({"symbol": "CCC", "timestamp": date, "close": 100.0 * (0.98**i)})
    frame = pd.DataFrame(rows)
    year_dir = root / "2020"
    year_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(year_dir / "shard-0000.parquet", index=False)


@pytest.fixture
def daily_glob(tmp_path: Path) -> str:
    _write_fixture(tmp_path)
    return str(tmp_path / "*" / "*.parquet")


def test_output_columns_for_requested_horizons(daily_glob: str) -> None:
    result = build_labels(daily_glob, SYMBOLS, horizons=(3, 5), memory_limit="512MB")
    assert set(result.columns) == {
        "symbol",
        "trade_date",
        "label_excess_3",
        "label_rank_3",
        "label_excess_5",
        "label_rank_5",
    }


def test_trailing_horizon_days_are_null_not_fabricated(daily_glob: str) -> None:
    result = build_labels(daily_glob, SYMBOLS, horizons=(3,), memory_limit="512MB")
    aaa = result.loc[result["symbol"] == "AAA"].sort_values("trade_date")
    # Last 3 trading days cannot see 3 days into the future.
    assert aaa["label_excess_3"].iloc[-3:].isna().all()
    assert aaa["label_excess_3"].iloc[:-3].notna().all()


def test_rank_is_null_wherever_excess_is_null(daily_glob: str) -> None:
    result = build_labels(daily_glob, SYMBOLS, horizons=(3,), memory_limit="512MB")
    null_excess = result["label_excess_3"].isna()
    assert result.loc[null_excess, "label_rank_3"].isna().all()
    assert result.loc[~null_excess, "label_rank_3"].notna().all()


def test_best_performer_gets_rank_one_and_worst_gets_zero(daily_glob: str) -> None:
    result = build_labels(daily_glob, SYMBOLS, horizons=(3,), memory_limit="512MB")
    defined = result.dropna(subset=["label_excess_3"])
    for _trade_date, group in defined.groupby("trade_date"):
        aaa_rank = group.loc[group["symbol"] == "AAA", "label_rank_3"].iloc[0]
        ccc_rank = group.loc[group["symbol"] == "CCC", "label_rank_3"].iloc[0]
        # AAA compounds at +2%/day, CCC at -2%/day -- AAA's forward return is
        # always the best of the three, CCC always the worst.
        assert aaa_rank == pytest.approx(1.0)
        assert ccc_rank == pytest.approx(0.0)


def test_excess_return_is_forward_return_minus_same_day_median(daily_glob: str) -> None:
    result = build_labels(daily_glob, SYMBOLS, horizons=(3,), memory_limit="512MB")
    defined = result.dropna(subset=["label_excess_3"])
    for _trade_date, group in defined.groupby("trade_date"):
        # BBB's own close never moves, so its raw forward return is exactly
        # 0.0 every day; the cross-sectional median of {+, 0, -} is BBB's own
        # forward return here (AAA up, CCC down, BBB flat -- middle value),
        # so BBB's excess label should be ~0.
        bbb_excess = group.loc[group["symbol"] == "BBB", "label_excess_3"].iloc[0]
        assert bbb_excess == pytest.approx(0.0, abs=1e-9)


def test_empty_universe_returns_empty_frame_with_correct_columns(daily_glob: str) -> None:
    result = build_labels(daily_glob, [], horizons=(5, 10, 21))
    assert len(result) == 0
    assert "label_excess_21" in result.columns
