"""Tests for open_composer.research.features.universe."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_composer.research.features.universe import (
    build_pit_universe_panel,
    exclude_funds_and_etfs,
    load_universe_panel,
    universe_union_symbols,
    write_universe_by_year,
)


def _write_daily_fixture(root: Path) -> None:
    """Three symbols, ~2 months of business days. AAA is the most liquid
    throughout; BBB overtakes it in February; CHEAP never clears the
    close > 5 filter; PENNY only exists in January (delisted-style gap, to
    confirm month-end ranking does not require every symbol on every date).
    """
    dates = pd.bdate_range("2020-01-01", "2020-02-29")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        rows.append(
            {"symbol": "AAA", "timestamp": date, "close": 100.0 + i * 0.1, "volume": 1_000_000}
        )
        # BBB starts cheap/illiquid and overtakes AAA's dollar ADV by late Feb
        # (needs a steep ramp: AAA's fixed 1M shares/day at ~$100-104/share is
        # a ~$100-104M/day dollar-ADV bar to clear).
        bbb_volume = 200_000 + i * 80_000
        rows.append(
            {"symbol": "BBB", "timestamp": date, "close": 50.0 + i * 0.05, "volume": bbb_volume}
        )
        rows.append({"symbol": "CHEAP", "timestamp": date, "close": 2.0, "volume": 5_000_000})
        if date < pd.Timestamp("2020-02-01"):
            rows.append({"symbol": "PENNY", "timestamp": date, "close": 20.0, "volume": 900_000})
    frame = pd.DataFrame(rows)
    year_dir = root / "2020"
    year_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(year_dir / "shard-0000.parquet", index=False)


@pytest.fixture
def daily_glob(tmp_path: Path) -> str:
    _write_daily_fixture(tmp_path)
    return str(tmp_path / "*" / "*.parquet")


def test_universe_panel_ranks_by_trailing_dollar_adv_at_each_month_end(daily_glob: str) -> None:
    panel = build_pit_universe_panel(
        daily_glob, adv_lookback_days=10, top_n=2, min_close=5.0, memory_limit="512MB"
    )
    months = sorted(panel["month_end"].dt.to_period("M").unique())
    assert len(months) == 2  # January and February month-ends

    # CHEAP (close=2.0) never appears despite the highest raw dollar volume.
    assert "CHEAP" not in set(panel["symbol"])

    jan_end = panel.loc[panel["month_end"].dt.month == 1]
    feb_end = panel.loc[panel["month_end"].dt.month == 2]
    # January: AAA (~100/share) beats BBB (~50/share) and PENNY on dollar ADV.
    assert set(jan_end["symbol"]) == {"AAA", "BBB"}
    assert jan_end.sort_values("adv_rank")["symbol"].tolist()[0] == "AAA"
    # February: BBB's ramping volume overtakes AAA by month end.
    assert set(feb_end["symbol"]) == {"AAA", "BBB"}
    assert feb_end.sort_values("adv_rank")["symbol"].tolist()[0] == "BBB"


def test_universe_panel_excludes_symbols_never_meeting_the_close_floor(daily_glob: str) -> None:
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    assert "CHEAP" not in set(panel["symbol"])


def test_universe_panel_is_pit_month_membership_does_not_require_full_history(
    daily_glob: str,
) -> None:
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    # PENNY existed only in January and must not leak into the February cohort.
    feb_symbols = set(panel.loc[panel["month_end"].dt.month == 2, "symbol"])
    assert "PENNY" not in feb_symbols


def test_exclude_funds_and_etfs_drops_only_flagged_symbols(daily_glob: str) -> None:
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    metadata = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "is_probable_fund_or_etf": [True, False],
        }
    )
    filtered = exclude_funds_and_etfs(panel, metadata)
    assert "AAA" not in set(filtered["symbol"])
    assert "BBB" in set(filtered["symbol"])


def test_exclude_funds_and_etfs_keeps_symbols_absent_from_metadata(daily_glob: str) -> None:
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    metadata = pd.DataFrame({"symbol": ["BBB"], "is_probable_fund_or_etf": [False]})
    filtered = exclude_funds_and_etfs(panel, metadata)
    # AAA is absent from metadata entirely -- must be kept, not dropped.
    assert "AAA" in set(filtered["symbol"])


def test_write_and_load_universe_by_year_round_trips(tmp_path: Path, daily_glob: str) -> None:
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    out_dir = tmp_path / "universe_out"
    written = write_universe_by_year(panel, out_dir)
    assert set(written) == {2020}
    assert written[2020].exists()

    reloaded = load_universe_panel(out_dir)
    assert set(reloaded.columns) == {"month_end", "symbol", "adv_rank", "dollar_adv", "close"}
    assert len(reloaded) == len(panel)

    union = universe_union_symbols(out_dir)
    # PENNY (close=20 > min_close) legitimately clears the price floor and
    # the generous top_n=10 cutoff for January before it disappears from the
    # fixture -- the full-history union correctly retains it.
    assert union == {"AAA", "BBB", "PENNY"}


def test_load_universe_panel_raises_when_nothing_written(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_universe_panel(tmp_path / "does_not_exist")
