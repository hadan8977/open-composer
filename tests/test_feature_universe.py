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
    """Five symbols, ~2 months of business days. AAA is the most liquid
    throughout; BBB overtakes it in February; CHEAP never clears the
    close > 5 filter; PENNY only exists in January (delisted-style gap, to
    confirm month-end ranking does not require every symbol on every date);
    GONE stops trading mid-February (acquisition-style delisting, the case
    that produced malformed one-row mid-month cohorts before 2026-09-16).

    The range runs a few sessions into March so that January and February are
    *finished* months: the builder deliberately emits no cohort for the
    archive's trailing, still-running month (here March).
    """
    dates = pd.bdate_range("2020-01-01", "2020-03-04")
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
        if date <= pd.Timestamp("2020-02-13"):
            rows.append({"symbol": "GONE", "timestamp": date, "close": 30.0, "volume": 800_000})
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
    # January and February month-ends; March is still running, so no cohort.
    assert [str(month) for month in months] == ["2020-01", "2020-02"]

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


def test_universe_panel_stamps_one_shared_month_end_per_calendar_month(
    daily_glob: str,
) -> None:
    """Regression test for the 2026-09-16 malformed-cohort defect: GONE's last
    February bar is 2020-02-13, but its row must still carry February's shared
    cohort date (the month's last session in the archive), not 2020-02-13 --
    otherwise ``universe_as_of_calendar_month`` resolves the weeks after
    2020-02-13 to a one-row cohort.
    """
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    per_month = panel.groupby(panel["month_end"].dt.to_period("M"))["month_end"].nunique()
    assert (per_month == 1).all(), panel["month_end"].drop_duplicates().tolist()

    february = panel.loc[panel["month_end"].dt.month == 2]
    # Last business day of the fixture's February date range.
    assert set(february["month_end"]) == {pd.Timestamp("2020-02-28")}
    # GONE is still admitted to (and ranked inside) the February cohort, on its
    # own last-traded ADV/close -- it is only the cohort *date* that is shared.
    assert "GONE" in set(february["symbol"])
    assert february.loc[february["symbol"] == "GONE", "close"].tolist() == [30.0]

    # No cohort is degenerate: every month carries the full cross-section.
    sizes = panel.groupby("month_end").size()
    assert sizes.min() >= 3


def test_universe_panel_omits_the_archives_still_running_final_month(daily_glob: str) -> None:
    """The fixture archive ends 2020-03-04. A March cohort dated 2020-03-04
    would make the universe change membership mid-month, which is the same
    defect class as the mid-month delisting rows -- so March is skipped until
    April data proves the month is over.
    """
    panel = build_pit_universe_panel(daily_glob, adv_lookback_days=10, top_n=10, min_close=5.0)
    assert panel["month_end"].max() == pd.Timestamp("2020-02-28")


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
    assert union == {"AAA", "BBB", "PENNY", "GONE"}


def test_load_universe_panel_raises_when_nothing_written(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_universe_panel(tmp_path / "does_not_exist")


def test_universe_panel_floor_mode_admits_everything_above_the_dollar_adv_floor(
    daily_glob: str,
) -> None:
    capped = build_pit_universe_panel(
        daily_glob, adv_lookback_days=10, top_n=2, min_close=5.0, memory_limit="512MB"
    )
    floor = build_pit_universe_panel(
        daily_glob,
        adv_lookback_days=10,
        top_n=None,
        min_close=5.0,
        min_dollar_adv=1.0,
        memory_limit="512MB",
    )
    # No rank cap: the floor-mode panel is a superset of the capped one ...
    capped_keys = set(zip(capped["month_end"], capped["symbol"], strict=True))
    floor_keys = set(zip(floor["month_end"], floor["symbol"], strict=True))
    assert capped_keys <= floor_keys
    assert len(floor_keys) > len(capped_keys)
    # ... and adv_rank is the rank over the whole month-end cross-section in
    # both modes, so the floor-mode panel can be sliced back to the capped one.
    merged = floor.merge(capped, on=["month_end", "symbol"], suffixes=("_floor", "_cap"))
    assert (merged["adv_rank_floor"] == merged["adv_rank_cap"]).all()
    assert set(floor.loc[floor["adv_rank"] <= 2, "symbol"]) == set(capped["symbol"])
    # a floor high enough to exclude BBB in January leaves AAA alone that month
    strict = build_pit_universe_panel(
        daily_glob,
        adv_lookback_days=10,
        top_n=None,
        min_close=5.0,
        min_dollar_adv=90_000_000.0,
        memory_limit="512MB",
    )
    january = strict.loc[strict["month_end"].dt.month == 1]
    assert set(january["symbol"]) == {"AAA"}


def test_universe_panel_requires_a_rank_cap_or_a_floor(daily_glob: str) -> None:
    with pytest.raises(ValueError):
        build_pit_universe_panel(daily_glob, top_n=None, min_dollar_adv=None)


def test_universe_panel_accepts_a_list_of_globs_for_a_delisted_root(tmp_path: Path) -> None:
    survivors = tmp_path / "sip"
    delisted = tmp_path / "sip-delisted"
    _write_daily_fixture(survivors)
    # A very liquid name that only exists in the delisted root (acquired in
    # February) must rank alongside survivors in January.
    dates = pd.bdate_range("2020-01-01", "2020-02-10")
    frame = pd.DataFrame(
        {
            "symbol": "TWTR",
            "timestamp": dates,
            "close": 40.0,
            "volume": 10_000_000,
            "trade_count": 1.0,
        }
    )
    (delisted / "2020").mkdir(parents=True)
    frame.to_parquet(delisted / "2020" / "batch-0000.parquet", index=False)
    panel = build_pit_universe_panel(
        [str(survivors / "*" / "*.parquet"), str(delisted / "*" / "*.parquet")],
        adv_lookback_days=10,
        top_n=2,
        min_close=5.0,
        memory_limit="512MB",
    )
    january = panel.loc[panel["month_end"].dt.month == 1].sort_values("adv_rank")
    assert january["symbol"].tolist()[0] == "TWTR"
    # Same semantics as GONE above: the acquired name is still ranked in the
    # cohort of the month it stopped trading, stamped with the shared cohort
    # date, and disappears from the next month's cohort.
    february = panel.loc[panel["month_end"].dt.month == 2]
    assert set(february["month_end"]) == {pd.Timestamp("2020-02-28")}
    assert "TWTR" in set(february["symbol"])
    assert january["month_end"].nunique() == 1
