"""Tests for scripts/build_news_hf_reaction.py.

Synthetic bars and news only -- no network, no real archive data. Covers the
four things the paper's construction lives or dies on: window alignment
(which 15-minute bucket a timestamp falls in), overnight handling (weekend/
after-hours/pre-9:45 news routed to the next session's overnight interval),
point-in-time cutoff (a stock-day's row is fully determined by that day's own
close), and aggregation (compounding news vs non-news interval returns, and
the news+non-news = overall identity).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

builder = importlib.import_module("scripts.build_news_hf_reaction")

ET = "America/New_York"


def _et(day: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{day} {hhmm}:00", tz=ET).tz_convert("UTC")


# --------------------------------------------------------------------- bucket math


@pytest.mark.parametrize(
    "minute_of_day,expected",
    [
        (585, 0),  # 09:45:00 exactly -> first intraday interval [9:45,10:00)
        (599, 0),  # 09:59
        (600, 1),  # 10:00:00 -> second interval [10:00,10:15)
        (958, 24),  # 15:58
        (959, 24),  # 15:59, last minute of the last bucket
    ],
)
def test_bucket_for_minute_of_day_half_open_boundaries(minute_of_day, expected):
    assert builder.bucket_for_minute_of_day(minute_of_day) == expected


@pytest.mark.parametrize(
    "minute_of_day,expected",
    [
        (570, -1),  # 09:30 open -> contributes to the 9:45 anchor
        (585, -1),  # 09:45:00 exactly -> still the 9:45 anchor (last <= 9:45)
        (586, 0),  # 09:46 -> first intraday bucket
        (959, 24),  # 15:59 -> last bucket (session close anchor)
    ],
)
def test_price_bucket_for_minute_of_day(minute_of_day, expected):
    assert builder.price_bucket_for_minute_of_day(minute_of_day) == expected


def test_bucket_count_matches_paper_m_26():
    assert builder.BUCKET_COUNT == 26
    assert builder.N_INTRADAY_BUCKETS == 25


# --------------------------------------------------------------------- calendar


def test_session_calendar_anchors_are_945_and_1600_et():
    cal = builder.session_calendar(
        pd.Timestamp("2024-01-02").date(), pd.Timestamp("2024-01-03").date()
    )
    assert list(cal["trade_date"].dt.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03"]
    assert cal.loc[0, "anchor_945_utc"] == _et("2024-01-02", "09:45")
    assert cal.loc[0, "anchor_1600_utc"] == _et("2024-01-02", "16:00")


def test_session_calendar_skips_weekend_and_holiday():
    # 2024-01-01 is New Year's Day, 2024-01-06/07 is a weekend.
    cal = builder.session_calendar(
        pd.Timestamp("2023-12-29").date(), pd.Timestamp("2024-01-08").date()
    )
    dates = set(cal["trade_date"].dt.strftime("%Y-%m-%d"))
    assert "2024-01-01" not in dates
    assert "2024-01-06" not in dates and "2024-01-07" not in dates
    assert "2023-12-29" in dates and "2024-01-02" in dates


# --------------------------------------------------------------------- news attribution


@pytest.fixture
def small_calendar() -> pd.DataFrame:
    # Fri 2024-01-05, Mon 2024-01-08, Tue 2024-01-09.
    return builder.session_calendar(
        pd.Timestamp("2024-01-05").date(), pd.Timestamp("2024-01-09").date()
    )


def test_regular_hours_news_attributes_to_same_session_intraday(small_calendar):
    visible_at = pd.Series([_et("2024-01-08", "10:05")])  # bucket 1, see docstring example
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-08")
    assert bucket[0] == 1


def test_news_exactly_at_945_is_intraday_bucket_zero(small_calendar):
    visible_at = pd.Series([_et("2024-01-08", "09:45")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-08")
    assert bucket[0] == 0


def test_news_one_minute_before_945_is_overnight_same_session(small_calendar):
    visible_at = pd.Series([_et("2024-01-08", "09:44")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-08")
    assert bucket[0] == builder.OVERNIGHT_BUCKET


def test_news_at_1600_is_overnight_next_session(small_calendar):
    visible_at = pd.Series([_et("2024-01-08", "16:00")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-09")
    assert bucket[0] == builder.OVERNIGHT_BUCKET


def test_friday_afterhours_news_routes_to_monday_overnight(small_calendar):
    visible_at = pd.Series([_et("2024-01-05", "18:00")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-08")
    assert bucket[0] == builder.OVERNIGHT_BUCKET


def test_saturday_weekend_news_routes_to_monday_overnight(small_calendar):
    visible_at = pd.Series([_et("2024-01-06", "12:00")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.Timestamp(trade_date[0]) == pd.Timestamp("2024-01-08")
    assert bucket[0] == builder.OVERNIGHT_BUCKET


def test_news_past_calendar_lookahead_is_dropped(small_calendar):
    # After the calendar's last 9:45 anchor: no session is far enough
    # forward, must not silently attribute anywhere.
    visible_at = pd.Series([_et("2024-01-09", "17:00")])
    trade_date, bucket = builder.attribute_news(visible_at, small_calendar)
    assert pd.isna(trade_date[0])
    assert bucket[0] == -99


def test_attribute_news_point_in_time_cutoff_never_looks_back_a_session(small_calendar):
    # Every attributed (trade_date, bucket) for news visible during session
    # 2024-01-08 or its immediately preceding overnight must be
    # trade_date == 2024-01-08, i.e. knowable by 2024-01-08's own close --
    # never a later session.
    times = [
        _et("2024-01-05", "16:01"),  # just after Friday close
        _et("2024-01-06", "09:00"),  # Saturday
        _et("2024-01-08", "09:44"),  # just before Monday's 9:45
        _et("2024-01-08", "09:45"),
        _et("2024-01-08", "15:59"),
    ]
    trade_date, _ = builder.attribute_news(pd.Series(times), small_calendar)
    assert set(pd.Timestamp(d) for d in trade_date) == {pd.Timestamp("2024-01-08")}


# --------------------------------------------------------------------- explode / fanout


def test_explode_news_events_drops_zero_and_over_fanout_articles(small_calendar):
    news = pd.DataFrame(
        {
            "id": ["a1", "a2", "a3"],
            "visible_at": [
                _et("2024-01-08", "10:05"),
                _et("2024-01-08", "10:06"),
                _et("2024-01-08", "10:07"),
            ],
            "symbols": [
                ["ZZZ"],
                [],
                [f"S{i}" for i in range(builder.MAX_SYMBOL_FANOUT + 1)],
            ],
        }
    )
    events = builder.explode_news_events(news, small_calendar)
    assert list(events["article_id"]) == ["a1"]
    assert list(events["symbol"]) == ["ZZZ"]


def test_explode_news_events_explodes_multi_symbol_article(small_calendar):
    news = pd.DataFrame(
        {
            "id": ["a1"],
            "visible_at": [_et("2024-01-08", "10:05")],
            "symbols": [["ZZZ", "YYY"]],
        }
    )
    events = builder.explode_news_events(news, small_calendar)
    assert set(events["symbol"]) == {"ZZZ", "YYY"}
    assert (events["trade_date"] == pd.Timestamp("2024-01-08")).all()
    assert (events["bucket"] == 1).all()


# --------------------------------------------------------------------- price anchors


def _write_minute_shard(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _bar(day: str, hhmm: str, symbol: str, close: float) -> dict:
    ts = pd.Timestamp(f"{day} {hhmm}:00", tz=ET).tz_convert("UTC")
    return {"symbol": symbol, "timestamp": ts, "close": close}


@pytest.fixture
def synthetic_shard(tmp_path: Path) -> Path:
    rows = [
        _bar("2024-01-02", "08:00", "ZZZ", 999.0),  # pre-market, must be excluded
        _bar("2024-01-02", "09:30", "ZZZ", 100.0),
        _bar("2024-01-02", "09:45", "ZZZ", 100.0),
        _bar("2024-01-02", "10:00", "ZZZ", 101.0),
        _bar("2024-01-02", "10:15", "ZZZ", 110.0),
        _bar("2024-01-02", "15:59", "ZZZ", 110.0),
        _bar("2024-01-03", "09:30", "ZZZ", 112.0),
        _bar("2024-01-03", "09:45", "ZZZ", 112.0),
        _bar("2024-01-03", "15:59", "ZZZ", 115.0),
    ]
    path = tmp_path / "shard-0000.parquet"
    _write_minute_shard(path, rows)
    return path


def test_anchor_prices_from_minute_bars_excludes_premarket_and_buckets_last_trade(
    synthetic_shard: Path,
):
    prices = builder.anchor_prices_from_minute_bars([str(synthetic_shard)], ["ZZZ"])
    day1 = prices[prices["trade_date"] == pd.Timestamp("2024-01-02")]
    got = dict(zip(day1["price_bucket"], day1["close"], strict=True))
    assert 999.0 not in got.values()  # pre-market bar never entered a bucket
    assert got[-1] == pytest.approx(100.0)  # 9:45 anchor
    assert got[0] == pytest.approx(101.0)  # 10:00 anchor
    assert got[1] == pytest.approx(110.0)  # 10:15 anchor
    assert got[24] == pytest.approx(110.0)  # 15:59 -> last (close) bucket


def test_anchor_prices_from_minute_bars_respects_symbol_filter(synthetic_shard: Path):
    prices = builder.anchor_prices_from_minute_bars([str(synthetic_shard)], ["SOMETHING_ELSE"])
    assert prices.empty


def test_session_anchor_table_forward_fills_gaps():
    bucket_prices = pd.DataFrame(
        {
            "symbol": ["ZZZ", "ZZZ", "ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")] * 3,
            "price_bucket": [-1, 0, 24],
            "close": [100.0, 101.0, 110.0],
        }
    )
    wide = builder.session_anchor_table(bucket_prices)
    row = wide.iloc[0]
    assert row[-1] == pytest.approx(100.0)
    assert row[0] == pytest.approx(101.0)
    # bucket 1..23 have no observation -> forward-filled from bucket 0 (101)
    assert row[5] == pytest.approx(101.0)
    assert row[24] == pytest.approx(110.0)


def test_interval_returns_table_overnight_uses_prior_session_close_and_first_session_is_null():
    anchors = pd.DataFrame(
        {
            "symbol": ["ZZZ", "ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            -1: [100.0, 112.0],
            **{k: [110.0, 115.0] for k in range(0, 25)},
        }
    )
    rets = builder.interval_returns_table(anchors)
    day1_overnight = rets[
        (rets["trade_date"] == pd.Timestamp("2024-01-02"))
        & (rets["bucket"] == builder.OVERNIGHT_BUCKET)
    ]
    day2_overnight = rets[
        (rets["trade_date"] == pd.Timestamp("2024-01-03"))
        & (rets["bucket"] == builder.OVERNIGHT_BUCKET)
    ]
    assert pd.isna(day1_overnight["ret"].iloc[0])  # no prior session loaded
    assert day2_overnight["ret"].iloc[0] == pytest.approx(112.0 / 110.0 - 1.0)

    day1_bucket0 = rets[(rets["trade_date"] == pd.Timestamp("2024-01-02")) & (rets["bucket"] == 0)]
    assert day1_bucket0["ret"].iloc[0] == pytest.approx(110.0 / 100.0 - 1.0)


# --------------------------------------------------------------------- aggregation


def test_aggregate_news_return_compounds_only_flagged_buckets_and_matches_overall_identity():
    interval_returns = pd.DataFrame(
        {
            "symbol": ["ZZZ"] * 3,
            "trade_date": [pd.Timestamp("2024-01-02")] * 3,
            "bucket": [-1, 0, 1],
            "ret": [0.01, 0.02, -0.01],
        }
    )
    news_events = pd.DataFrame(
        {
            "article_id": ["a1"],
            "symbol": ["ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")],
            "bucket": [0],
            "visible_at": [_et("2024-01-02", "10:05")],
        }
    )
    agg = builder.aggregate_news_return(interval_returns, news_events)
    row = agg.iloc[0]
    assert row["news_return"] == pytest.approx(0.02)
    expected_nonnews = (1.01) * (0.99) - 1.0
    assert row["non_news_return"] == pytest.approx(expected_nonnews)
    expected_overall = (1.0 + row["news_return"]) * (1.0 + row["non_news_return"]) - 1.0
    assert row["overall_return"] == pytest.approx(expected_overall)
    # and the identity must equal compounding the three raw interval returns
    # directly, i.e. the news/non-news split is a true partition.
    direct_overall = 1.01 * 1.02 * 0.99 - 1.0
    assert row["overall_return"] == pytest.approx(direct_overall)
    assert row["n_windows"] == 1


def test_aggregate_news_return_multiple_news_buckets_compound_together():
    interval_returns = pd.DataFrame(
        {
            "symbol": ["ZZZ"] * 3,
            "trade_date": [pd.Timestamp("2024-01-02")] * 3,
            "bucket": [-1, 0, 1],
            "ret": [0.01, 0.02, 0.03],
        }
    )
    news_events = pd.DataFrame(
        {
            "article_id": ["a1", "a2"],
            "symbol": ["ZZZ", "ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")] * 2,
            "bucket": [0, 1],
            "visible_at": [_et("2024-01-02", "10:05"), _et("2024-01-02", "10:20")],
        }
    )
    agg = builder.aggregate_news_return(interval_returns, news_events)
    row = agg.iloc[0]
    assert row["news_return"] == pytest.approx(1.02 * 1.03 - 1.0)
    assert row["n_windows"] == 2


def test_aggregate_news_return_drops_stock_days_with_no_news_bucket():
    interval_returns = pd.DataFrame(
        {
            "symbol": ["ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")],
            "bucket": [0],
            "ret": [0.02],
        }
    )
    news_events = pd.DataFrame(
        columns=["article_id", "symbol", "trade_date", "bucket", "visible_at"]
    )
    agg = builder.aggregate_news_return(interval_returns, news_events)
    assert agg.empty


def test_attach_news_counts_uses_article_count_and_latest_visible_at():
    agg = pd.DataFrame(
        {
            "symbol": ["ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")],
            "news_return": [0.02],
            "non_news_return": [0.0],
            "overall_return": [0.02],
            "n_windows": [1],
        }
    )
    early = _et("2024-01-02", "10:05")
    late = _et("2024-01-02", "10:20")
    news_events = pd.DataFrame(
        {
            "article_id": ["a1", "a2"],
            "symbol": ["ZZZ", "ZZZ"],
            "trade_date": [pd.Timestamp("2024-01-02")] * 2,
            "bucket": [0, 0],
            "visible_at": [early, late],
        }
    )
    out = builder.attach_news_counts(agg, news_events)
    row = out.iloc[0]
    assert row["n_news"] == 2
    assert row["visible_at"] == late
    assert list(out.columns) == list(builder.OUTPUT_COLUMNS)


# --------------------------------------------------------------------- end to end


def test_process_month_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sip_root = tmp_path / "sip" / "minute"
    news_root = tmp_path / "news_packets"
    monkeypatch.setattr(builder, "SIP_MINUTE_ROOT", sip_root)
    monkeypatch.setattr(builder, "NEWS_PACKETS_ROOT", news_root)

    rows = [
        _bar("2024-01-02", "09:30", "ZZZ", 100.0),
        _bar("2024-01-02", "09:45", "ZZZ", 100.0),
        _bar("2024-01-02", "10:00", "ZZZ", 101.0),
        _bar("2024-01-02", "10:15", "ZZZ", 110.0),
        _bar("2024-01-02", "15:59", "ZZZ", 110.0),
        _bar("2024-01-03", "09:30", "ZZZ", 112.0),
        _bar("2024-01-03", "09:45", "ZZZ", 112.0),
        _bar("2024-01-03", "15:59", "ZZZ", 115.0),
    ]
    _write_minute_shard(sip_root / "2024" / "01" / "shard-0000.parquet", rows)

    news_root.mkdir(parents=True)
    news = pd.DataFrame(
        {
            "id": ["a1", "a2", "a3", "a4"],
            "visible_at": [
                _et("2024-01-02", "10:05"),  # -> 2024-01-02, bucket 1 (intraday)
                _et("2024-01-02", "17:00"),  # after-hours -> 2024-01-03 overnight
                _et("2024-01-02", "10:06"),  # zero symbols, dropped
                _et("2024-01-02", "10:07"),  # over fanout, dropped
            ],
            "symbols": [
                ["ZZZ"],
                ["ZZZ"],
                [],
                [f"S{i}" for i in range(builder.MAX_SYMBOL_FANOUT + 1)],
            ],
        }
    )
    news.to_parquet(news_root / "2024.parquet", index=False)

    out = builder.process_month(2024, 1)
    assert list(out.columns) == list(builder.OUTPUT_COLUMNS)
    assert set(out["trade_date"]) == {pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")}

    day1 = out[out["trade_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert day1["news_return"] == pytest.approx(110.0 / 101.0 - 1.0)
    assert day1["n_news"] == 1
    assert day1["n_windows"] == 1

    day2 = out[out["trade_date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert day2["news_return"] == pytest.approx(112.0 / 110.0 - 1.0)
    assert day2["n_news"] == 1
    assert day2["n_windows"] == 1
    assert day2["visible_at"] == _et("2024-01-02", "17:00")


def test_run_build_checkpoints_and_is_resumable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sip_root = tmp_path / "sip" / "minute"
    news_root = tmp_path / "news_packets"
    out_root = tmp_path / "out"
    monkeypatch.setattr(builder, "SIP_MINUTE_ROOT", sip_root)
    monkeypatch.setattr(builder, "NEWS_PACKETS_ROOT", news_root)
    monkeypatch.setattr(builder, "OUT_ROOT", out_root)

    rows = [
        _bar("2024-01-02", "09:30", "ZZZ", 100.0),
        _bar("2024-01-02", "09:45", "ZZZ", 100.0),
        _bar("2024-01-02", "10:15", "ZZZ", 110.0),
        _bar("2024-01-02", "15:59", "ZZZ", 110.0),
    ]
    _write_minute_shard(sip_root / "2024" / "01" / "shard-0000.parquet", rows)
    news_root.mkdir(parents=True)
    news = pd.DataFrame(
        {
            "id": ["a1"],
            "visible_at": [_et("2024-01-02", "10:05")],
            "symbols": [["ZZZ"]],
        }
    )
    news.to_parquet(news_root / "2024.parquet", index=False)

    builder.run_build(2024, 1, 2024, 1)
    ckpt = builder.checkpoint_path(2024, 1)
    assert ckpt.exists()
    year_file = out_root / "2024.parquet"
    assert year_file.exists()
    first_mtime = ckpt.stat().st_mtime_ns

    # Re-running without --force must not touch the checkpoint (skip, not
    # recompute) -- the whole point of the per-month checkpoint.
    builder.run_build(2024, 1, 2024, 1)
    assert ckpt.stat().st_mtime_ns == first_mtime

    frame = pd.read_parquet(year_file)
    assert len(frame) == 1
    assert frame.iloc[0]["symbol"] == "ZZZ"


def test_month_bounds_handles_december_rollover():
    start, end = builder.month_bounds(2024, 12)
    assert start.isoformat() == "2024-12-01"
    assert end.isoformat() == "2024-12-31"
