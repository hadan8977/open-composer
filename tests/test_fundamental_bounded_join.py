import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def test_issuer_chunks_preserve_visibility_aliases_and_duplicate_price_rows():
    path = Path(__file__).parents[1] / "scripts/build_sec_xbrl_fundamentals.py"
    spec = importlib.util.spec_from_file_location("fundamental_bounded_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dates = pd.date_range("2026-01-01", periods=5)
    positions = dict(zip(dates, range(5), strict=True))
    events = pd.DataFrame(
        [
            {"cik": 11, "event_idx": 1, "last_report_idx": 1, "total_assets": 100.0},
            {"cik": 11, "event_idx": 3, "last_report_idx": 3, "total_assets": 150.0},
            {"cik": 22, "event_idx": 0, "last_report_idx": 0, "total_assets": 200.0},
        ]
    )
    mapping = {"A": 11, "A_ALIAS": 11, "B": 22}
    price = pd.DataFrame(
        [
            ("A", dates[0]),
            ("A", dates[2]),
            ("A", dates[4]),
            ("A_ALIAS", dates[2]),
            ("B", dates[2]),
            ("B", dates[2]),
            ("UNMAPPED", dates[4]),
        ],
        columns=["symbol", "trade_date"],
    )
    full = module.merge_daily_prices(price, events, mapping, positions)
    chunks = pd.concat(
        [
            module.merge_daily_prices(price[price.symbol.isin(names)], events, mapping, positions)
            for names in (["A", "A_ALIAS"], ["B"])
        ]
    ).sort_values(["trade_date", "symbol"], ignore_index=True)
    pd.testing.assert_frame_equal(full, chunks)
    assert len(full) == 6
    assert np.isnan(full.iloc[0].total_assets)
    assert full.loc[full.symbol.eq("A"), "total_assets"].iloc[1:].tolist() == [100.0, 150.0]
    assert full.loc[full.symbol.eq("A_ALIAS"), "days_since_report"].tolist() == [1.0]
    assert full.loc[full.symbol.eq("B"), "days_since_report"].tolist() == [2.0, 2.0]


def test_bounded_writer_matches_full_join_and_keeps_old_file_on_failure(tmp_path, monkeypatch):
    import duckdb

    spec = importlib.util.spec_from_file_location(
        "fund_writer", Path(__file__).parents[1] / "scripts/build_sec_xbrl_fundamentals.py"
    )
    f = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f)
    prices, outputs = tmp_path / "prices", tmp_path / "out"
    prices.mkdir()
    outputs.mkdir()
    monkeypatch.setattr(f, "DAILY_BROAD_ROOT", prices)
    monkeypatch.setattr(f, "DAILY_ROOT", outputs)
    dates = pd.date_range("2026-01-02", periods=4)
    pos = dict(zip(dates, range(4), strict=True))
    mapping = {f"S{i:03}": i // 2 for i in range(402)}
    price = pd.DataFrame(
        [(s, d) for s in [*mapping, "UNMAPPED", "S000"] for d in dates],
        columns=["symbol", "trade_date"],
    )
    price.to_parquet(prices / "2026.parquet", index=False)
    events = pd.DataFrame(
        [
            {"cik": i, "event_idx": t, "last_report_idx": t, "total_assets": float(i + t)}
            for i in range(201)
            for t in (1, 3)
        ]
    )
    full = f.merge_daily_prices(price, events, mapping, pos)
    work = tmp_path / "work"
    work.mkdir()
    with duckdb.connect() as con:
        con.execute("SET threads=1")
        result = f.write_bounded_daily_year(con, 2026, events, mapping, pos, work)
    pd.testing.assert_frame_equal(pd.read_parquet(outputs / "2026.parquet"), full)
    assert result == f._year_coverage(full)
    before = (outputs / "2026.parquet").read_bytes()
    failed = tmp_path / "failed"
    failed.mkdir()
    original = f.merge_daily_prices
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected interrupted join")
        return original(*args)

    monkeypatch.setattr(f, "merge_daily_prices", fail_second)
    with duckdb.connect() as con, pytest.raises(RuntimeError, match="interrupted"):
        f.write_bounded_daily_year(con, 2026, events, mapping, pos, failed)
    assert (outputs / "2026.parquet").read_bytes() == before


def test_bounded_events_preserve_source_sequence_across_batches(tmp_path, monkeypatch):
    import duckdb

    spec = importlib.util.spec_from_file_location(
        "fund_events", Path(__file__).parents[1] / "scripts/build_sec_xbrl_fundamentals.py"
    )
    f = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f)
    facts = pd.DataFrame(
        [(i, j) for j in (3, 1, 1, 2) for i in range(402)], columns=["cik", "sequence"]
    )
    path = tmp_path / "facts.parquet"
    facts.to_parquet(path, index=False)
    monkeypatch.setattr(f, "FACTS_PATH", path)
    seen = {}

    def compute(cik, group):
        seen[cik] = list(group.sequence)
        return pd.DataFrame()

    monkeypatch.setattr(f, "compute_cik_table", compute)
    with duckdb.connect() as con:
        con.execute("SET threads=1")
        assert f.bounded_events(con, {}).empty
    assert seen == {i: [3, 1, 1, 2] for i in range(402)}
