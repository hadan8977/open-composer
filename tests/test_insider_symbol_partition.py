from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import build_insider_features as m


def test_partition_preserves_full_cohort_guard_and_owner_history():
    names = [f"S{i:03d}" for i in range(100)]
    universe = pd.DataFrame(
        {
            "symbol": names,
            "month_end": pd.Timestamp("2023-12-29"),
            "adv_rank": range(1, 101),
            "dollar_adv": 1_000_000.0,
            "close": 10.0,
        }
    )
    rows = []
    for symbol, owner, seq in [("S000", 1001, 0), ("S000", 1002, 1), ("S090", 2001, 0)]:
        rows.append(
            {
                "accession": symbol,
                "issuer_symbol": symbol,
                "owner_cik": owner,
                "owner_seq": seq,
                "filing_date": pd.Timestamp("2024-02-01"),
                "trans_date": pd.Timestamp("2024-01-31"),
                "trans_code": "P",
                "acquired_disposed": "A",
                "shares": 100.0,
                "price_per_share": 10.0,
                "is_director": True,
                "is_officer": False,
                "is_ten_percent_owner": False,
            }
        )
    frame = pd.DataFrame(rows)
    frame["owner_cik"] = frame.owner_cik.astype("Int64")
    sessions, positions = m.build_session_index(date(2024, 1, 1), date(2024, 2, 29))
    frame = m.attach_visible_index(frame, positions, shift_days=0, seed=m.DEFAULT_PLACEBO_SEED)
    frame = m.classify_transactions(frame)
    frame = pd.concat([frame, m.label_buy_routineness(frame)], axis=1)
    full = m.build_year(
        2024, transactions=frame, sessions=sessions, universe_panel=universe, top_n=100
    )
    assert not full.empty
    # A one-name output partition must retain the valid full 100-name population.
    part = m.build_year(
        2024,
        transactions=frame.loc[frame.issuer_symbol == "S000"],
        sessions=sessions,
        universe_panel=universe,
        top_n=100,
        output_symbols={"S000"},
    )
    expected = full.loc[full.symbol == "S000"].reset_index(drop=True)
    pd.testing.assert_frame_equal(part, expected, check_exact=True)
    assert part.buyers_od_60d.max() == 2


def test_normal_partitioned_writer_matches_full_history_and_empty_chunks(tmp_path, monkeypatch):
    parsed, tail = tmp_path / "parsed", tmp_path / "tail"
    parsed.mkdir()
    tail.mkdir()
    monkeypatch.setattr(m, "PARSED_ROOT", parsed)
    monkeypatch.setattr(m, "TAIL_PARSED_ROOT", tail)
    names = [f"S{i:03d}" for i in range(401)]
    universe = pd.DataFrame(
        {
            "symbol": names,
            "month_end": pd.Timestamp("2022-12-30"),
            "adv_rank": range(1, 402),
            "dollar_adv": 1e6,
            "close": 10.0,
        }
    )
    rows = []
    for year in (2019, 2020, 2021, 2022, 2023):
        for symbol, owner, seq in [("S180", 1, 0), ("S180", 2, 1), ("S380", 3, 0)]:
            rows.append(
                dict(
                    accession=f"{year}-{symbol}-{seq}",
                    document_type="4",
                    issuer_symbol=symbol,
                    reporting_owner_cik=str(owner),
                    owner_seq=seq,
                    filing_date=pd.Timestamp(f"{year}-01-10"),
                    trans_date=pd.Timestamp(f"{year}-01-09"),
                    trans_code="P",
                    acquired_disposed="A",
                    shares=100.0,
                    price_per_share=10.0,
                    is_director=True,
                    is_officer=False,
                    is_ten_percent_owner=False,
                    is_10b5_1=None,
                )
            )
    source = pd.DataFrame(rows)
    source.to_parquet(parsed / "fixture.parquet", index=False, row_group_size=2)
    # Preserve a duplicate source row, including tail file ordering.
    source.tail(1).to_parquet(tail / "fixture.parquet", index=False)
    sessions, pos = m.build_session_index(date(2016, 1, 1), date(2023, 2, 28))
    tx = m.load_transactions(symbols=set(names))
    tx = m.attach_visible_index(tx, pos, shift_days=0, seed=m.DEFAULT_PLACEBO_SEED)
    tx = m.classify_transactions(tx)
    tx = pd.concat([tx, m.label_buy_routineness(tx)], axis=1)
    expected = m.build_year(
        2023, transactions=tx, sessions=sessions, universe_panel=universe, top_n=1000
    )
    out = tmp_path / "out"
    out.mkdir()
    args = SimpleNamespace(
        start_year=2023,
        end_year=2023,
        force=False,
        top_n=1000,
        symbol_batch_size=180,
        placebo_seed=m.DEFAULT_PLACEBO_SEED,
    )
    m.build_partitioned_years(args, out, sessions, pos, universe)
    pd.testing.assert_frame_equal(pd.read_parquet(out / "2023.parquet"), expected, check_exact=True)
    assert expected.symbol.nunique() == 401
    before = (out / "2023.parquet").read_bytes()
    original = m.build_year
    calls = 0

    def failure(*a, **kw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected partition interruption")
        return original(*a, **kw)

    args.force = True
    monkeypatch.setattr(m, "build_year", failure)
    with pytest.raises(RuntimeError, match="partition interruption"):
        m.build_partitioned_years(args, out, sessions, pos, universe)
    assert (out / "2023.parquet").read_bytes() == before


def test_partition_flag_does_not_reseed_placebo_or_accept_negative_size():
    with pytest.raises(SystemExit):
        m.main(["--symbol-batch-size", "180", "--shift-filing-dates-days", "1"])
    with pytest.raises(SystemExit):
        m.main(["--symbol-batch-size", "-1"])
