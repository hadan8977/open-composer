from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_composer.adapters.data.sip_parquet import clear_sip_index_cache
from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates

REAL_DAILY = Path(__file__).resolve().parents[1] / "data" / "sip" / "daily"

requires_real_daily = pytest.mark.skipif(
    not REAL_DAILY.is_dir(),
    reason="local SIP daily archive (data/sip/daily) is not present",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_sip_index_cache()
    yield
    clear_sip_index_cache()


@requires_real_daily
def test_index_is_naive_not_tz_aware() -> None:
    returns = daily_returns_on_naive_dates("QQQ", start="2026-06-01", end="2026-06-30")
    assert returns.index.tz is None


@requires_real_daily
def test_index_matches_plain_date_string_convention() -> None:
    # This is the exact reindex this function exists to make safe: a plain
    # "YYYY-MM-DD"-derived DatetimeIndex, like router_common's dataset.dates,
    # must find every row rather than reindexing to all-NaN.
    returns = daily_returns_on_naive_dates("QQQ", start="2026-06-01", end="2026-06-30")
    plain_dates = [timestamp.date().isoformat() for timestamp in returns.index]
    reindexed = returns.reindex(pd.DatetimeIndex(plain_dates))
    assert not reindexed.isna().any()


@requires_real_daily
def test_returns_are_simple_close_to_close_pct_change() -> None:
    returns = daily_returns_on_naive_dates("QQQ", start="2026-06-01", end="2026-06-10")
    assert (returns.abs() < 0.5).all()  # sanity: no absurd single-day move
    assert len(returns) > 0
