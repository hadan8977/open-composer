"""Preserve both full-year relevant-event boundaries across execution chunks."""

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd


def module():
    spec = importlib.util.spec_from_file_location(
        "fundamental_empty", Path(__file__).parents[1] / "scripts/build_sec_xbrl_fundamentals.py"
    )
    f = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f)
    return f


def test_null_only_last_chunk_is_not_a_membership_filter(tmp_path, monkeypatch):
    f = module()
    price_root, out = tmp_path / "prices", tmp_path / "out"
    price_root.mkdir()
    out.mkdir()
    monkeypatch.setattr(f, "DAILY_BROAD_ROOT", price_root)
    monkeypatch.setattr(f, "DAILY_ROOT", out)
    dates = pd.date_range("2026-01-02", periods=2)
    pos = dict(zip(dates, (0, 1), strict=True))
    mapping = {f"S{i:03d}": i for i in range(201)}
    prices = pd.DataFrame(
        [(s, d) for s in mapping for d in dates] + [("S200", dates[0])],
        columns=["symbol", "trade_date"],
    )
    prices.to_parquet(price_root / "2026.parquet", index=False)
    events = pd.DataFrame([{"cik": 0, "event_idx": 0, "last_report_idx": 0, "total_assets": 100.0}])
    expected = f.merge_daily_prices(prices, events, mapping, pos)
    work = tmp_path / "work"
    work.mkdir()
    with duckdb.connect() as con:
        con.execute("SET threads=1")
        coverage = f.write_bounded_daily_year(con, 2026, events, mapping, pos, work)
    actual = pd.read_parquet(out / "2026.parquet")
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    assert len(actual) == 403 and actual.symbol.nunique() == 201
    unmatched = actual.loc[actual.symbol.eq("S200")]
    assert len(unmatched) == 3 and unmatched.cik.eq(200).all()
    assert unmatched[list(f.RAW_COLUMNS)].isna().all().all()
    assert coverage == f._year_coverage(expected)


def test_events_outside_valid_year_mapping_leave_old_output_unchanged(tmp_path, monkeypatch):
    f = module()
    price_root, out = tmp_path / "prices", tmp_path / "out"
    price_root.mkdir()
    out.mkdir()
    monkeypatch.setattr(f, "DAILY_BROAD_ROOT", price_root)
    monkeypatch.setattr(f, "DAILY_ROOT", out)
    dates = pd.date_range("2026-01-02", periods=2)
    pos = dict(zip(dates, (0, 1), strict=True))
    mapping = {"NO_EVENTS": 1, "OUTSIDE_CALENDAR": 2, "NO_PRICE": 3}
    prices = pd.DataFrame(
        [
            ("NO_EVENTS", dates[0]),
            ("NO_EVENTS", dates[0]),
            ("OUTSIDE_CALENDAR", pd.Timestamp("1999-01-01")),
            ("UNMAPPED", dates[0]),
        ],
        columns=["symbol", "trade_date"],
    )
    prices.to_parquet(price_root / "2026.parquet", index=False)
    events = pd.DataFrame(
        [{"cik": i, "event_idx": 0, "last_report_idx": 0, "total_assets": 100.0} for i in (2, 3, 4)]
    )
    assert not events.empty
    assert f.merge_daily_prices(prices, events, mapping, pos).empty
    old = out / "2026.parquet"
    old.write_bytes(b"previous accepted output")
    work = tmp_path / "work"
    work.mkdir()
    with duckdb.connect() as con:
        con.execute("SET threads=1")
        assert f.write_bounded_daily_year(con, 2026, events, mapping, pos, work) is None
    assert old.read_bytes() == b"previous accepted output"
