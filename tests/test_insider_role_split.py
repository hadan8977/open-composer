"""Tests for the officer/director vs ten-percent-owner role split added to
``scripts/build_insider_features.py`` -- ``net_buy_usd_od_60d``,
``net_buy_shares_od_60d``, ``open_market_buy_count_od_60d``,
``buyers_od_60d``, ``net_buy_usd_tenpct_60d`` and
``open_market_buy_count_tenpct_od_excluded_60d``.

Motivation (see the module docstring's "Joint filings" section): RSG's
``net_buy_usd_60d`` was $1.38 billion, all of it one 10%-owner, which made
the unsplit column unable to distinguish officer/director buying from a
passive large holder's accumulation. These tests build a small synthetic
parsed-transaction frame and call the module's own pipeline functions
directly (``attach_visible_index`` -> ``classify_transactions`` ->
``label_buy_routineness`` -> ``build_year``), matching the import idiom in
``tests/test_build_hourly_bars.py``. No real ``data/`` table is read or
written.
"""

from __future__ import annotations

import importlib
from datetime import date

import pandas as pd
import pytest

build_insider_features = importlib.import_module("scripts.build_insider_features")


def _row(
    *,
    accession: str,
    symbol: str,
    owner_cik: int,
    owner_seq: int,
    filing_date: str,
    trans_date: str,
    shares: float,
    price: float,
    is_director: bool = False,
    is_officer: bool = False,
    is_ten_percent_owner: bool = False,
    trans_code: str = "P",
    acquired_disposed: str = "A",
) -> dict:
    return {
        "accession": accession,
        "issuer_symbol": symbol,
        "owner_cik": owner_cik,
        "owner_seq": owner_seq,
        "filing_date": filing_date,
        "trans_date": trans_date,
        "trans_code": trans_code,
        "acquired_disposed": acquired_disposed,
        "shares": shares,
        "price_per_share": price,
        "is_director": is_director,
        "is_officer": is_officer,
        "is_ten_percent_owner": is_ten_percent_owner,
    }


def _transactions_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["trans_date"] = pd.to_datetime(frame["trans_date"])
    frame["owner_cik"] = frame["owner_cik"].astype("Int64")
    for column in ("is_director", "is_officer", "is_ten_percent_owner"):
        frame[column] = frame[column].astype("boolean")
    return frame


def _build_year_frame(rows: list[dict]) -> pd.DataFrame:
    """Run the real builder pipeline on ``rows`` and return the 2024 table
    indexed by ``(symbol, trade_date)``, ascending by date within symbol."""
    module = build_insider_features
    transactions = _transactions_frame(rows)
    sessions, session_position = module.build_session_index(date(2024, 1, 1), date(2024, 2, 29))
    transactions = module.attach_visible_index(
        transactions, session_position, shift_days=0, seed=module.DEFAULT_PLACEBO_SEED
    )
    transactions = module.classify_transactions(transactions)
    transactions = pd.concat([transactions, module.label_buy_routineness(transactions)], axis=1)

    symbols = sorted(transactions["issuer_symbol"].unique())
    universe_panel = pd.DataFrame(
        {
            "month_end": [pd.Timestamp("2023-12-29")] * len(symbols),
            "symbol": symbols,
            "adv_rank": list(range(1, len(symbols) + 1)),
            "dollar_adv": [1_000_000.0] * len(symbols),
            "close": [10.0] * len(symbols),
        }
    )
    frame = module.build_year(
        2024,
        transactions=transactions,
        sessions=sessions,
        universe_panel=universe_panel,
        top_n=len(symbols) + 1,
    )
    return frame.set_index(["symbol", "trade_date"]).sort_index()


def _last_row(frame: pd.DataFrame, symbol: str) -> pd.Series:
    """The row for ``symbol``'s latest trade_date -- by then every synthetic
    filing in these tests is well inside its trailing 60-session window."""
    return frame.loc[symbol].iloc[-1]


def test_officer_buy_lands_in_od_not_tenpct() -> None:
    rows = [
        _row(
            accession="A1",
            symbol="OD1",
            owner_cik=111,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=5.0,
            is_officer=True,
        )
    ]
    row = _last_row(_build_year_frame(rows), "OD1")
    assert row["net_buy_usd_od_60d"] == pytest.approx(5000.0)
    assert row["net_buy_shares_od_60d"] == pytest.approx(1000.0)
    assert row["open_market_buy_count_od_60d"] == pytest.approx(1.0)
    assert row["buyers_od_60d"] == pytest.approx(1.0)
    assert row["net_buy_usd_tenpct_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_tenpct_od_excluded_60d"] == pytest.approx(0.0)


def test_pure_ten_percent_owner_buy_lands_in_tenpct_not_od() -> None:
    rows = [
        _row(
            accession="A2",
            symbol="TP1",
            owner_cik=222,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=400.0,
            price=10.0,
            is_ten_percent_owner=True,
        )
    ]
    row = _last_row(_build_year_frame(rows), "TP1")
    assert row["net_buy_usd_tenpct_60d"] == pytest.approx(4000.0)
    assert row["open_market_buy_count_tenpct_od_excluded_60d"] == pytest.approx(1.0)
    assert row["net_buy_usd_od_60d"] == pytest.approx(0.0)
    assert row["net_buy_shares_od_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_od_60d"] == pytest.approx(0.0)
    assert row["buyers_od_60d"] == pytest.approx(0.0)


def test_ten_percent_owner_who_is_also_director_counts_as_od_only() -> None:
    rows = [
        _row(
            accession="A3",
            symbol="BOTH1",
            owner_cik=333,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=300.0,
            price=10.0,
            is_director=True,
            is_ten_percent_owner=True,
        )
    ]
    row = _last_row(_build_year_frame(rows), "BOTH1")
    assert row["net_buy_usd_od_60d"] == pytest.approx(3000.0)
    assert row["open_market_buy_count_od_60d"] == pytest.approx(1.0)
    assert row["buyers_od_60d"] == pytest.approx(1.0)
    assert row["net_buy_usd_tenpct_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_tenpct_od_excluded_60d"] == pytest.approx(0.0)


def test_joint_filing_counts_dollars_once_and_buyers_twice_in_od() -> None:
    """``owner_count=2``, rows with ``owner_seq`` 0 and 1, identical shares
    and price -- the joint-filing rule: dollars count once (owner_seq == 0
    only), distinct owners count once per owner row."""
    rows = [
        _row(
            accession="J1",
            symbol="JOINT1",
            owner_cik=444,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=20.0,
            is_officer=True,
        ),
        _row(
            accession="J1",
            symbol="JOINT1",
            owner_cik=555,
            owner_seq=1,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=20.0,
            is_officer=True,
        ),
    ]
    row = _last_row(_build_year_frame(rows), "JOINT1")
    assert row["net_buy_usd_od_60d"] == pytest.approx(20000.0)
    assert row["net_buy_shares_od_60d"] == pytest.approx(1000.0)
    assert row["open_market_buy_count_od_60d"] == pytest.approx(1.0)
    assert row["buyers_od_60d"] == pytest.approx(2.0)


def test_net_buy_usd_60d_still_equals_unsplit_total_across_roles() -> None:
    rows = [
        _row(
            accession="M1",
            symbol="MIX1",
            owner_cik=666,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=2000.0,
            price=10.0,
            is_officer=True,
        ),
        _row(
            accession="M2",
            symbol="MIX1",
            owner_cik=777,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=500.0,
            price=10.0,
            is_ten_percent_owner=True,
        ),
    ]
    row = _last_row(_build_year_frame(rows), "MIX1")
    assert row["net_buy_usd_60d"] == pytest.approx(25000.0)
    assert row["net_buy_usd_od_60d"] == pytest.approx(20000.0)
    assert row["net_buy_usd_tenpct_60d"] == pytest.approx(5000.0)
    assert row["net_buy_usd_60d"] == pytest.approx(
        row["net_buy_usd_od_60d"] + row["net_buy_usd_tenpct_60d"]
    )
