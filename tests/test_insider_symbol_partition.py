from datetime import date

import pandas as pd

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
