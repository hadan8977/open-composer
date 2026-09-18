"""Tests for the Rule 10b5-1 pre-scheduled-plan split (H-20260916-01 intel
brief, 2026-09-18): ``open_market_buy_count_nonplan_60d``,
``net_buy_usd_nonplan_60d``, ``buyers_nonplan_60d``,
``open_market_buy_count_plan_60d``, ``net_buy_usd_plan_60d``,
``open_market_buy_count_flag_unknown_60d`` and
``tenb5one_flag_coverage_60d``, plus
``scripts.collect_sec_insider_transactions.normalize_10b5_1_flag``.

Two independent things are exercised:

1. ``normalize_10b5_1_flag`` -- the raw ``AFF10B5ONE`` text -> nullable
   boolean mapping, with synthetic strings covering every encoding the
   intel brief measured on disk (``'0'``/``'1'``/``'true'``/``'false'``,
   plus the ``'y'``/``'n'``/``'yes'``/``'no'`` tokens the normalizer also
   accepts) and blank/unrecognized text.
2. The feature builder's plan/nonplan/unknown aggregates -- built the same
   way ``tests/test_insider_role_split.py`` builds the role split: small
   synthetic parsed-transaction frames run through the module's own
   pipeline (``attach_visible_index`` -> ``classify_transactions`` ->
   ``label_buy_routineness`` -> ``build_year``). No real ``data/`` archive
   is read or written.
"""

from __future__ import annotations

import importlib
from datetime import date

import pandas as pd
import pytest

build_insider_features = importlib.import_module("scripts.build_insider_features")
collect_sec_insider_transactions = importlib.import_module(
    "scripts.collect_sec_insider_transactions"
)


# --------------------------------------------------------------------------
# normalize_10b5_1_flag
# --------------------------------------------------------------------------


def test_normalizer_maps_every_observed_encoding() -> None:
    raw = pd.Series(
        [
            "0",
            "1",
            "true",
            "false",
            "TRUE",
            "FALSE",
            "Y",
            "y",
            "N",
            "n",
            "yes",
            "no",
            "",
            None,
            "  1  ",
            "  FALSE ",
            "maybe",
        ]
    )
    result = collect_sec_insider_transactions.normalize_10b5_1_flag(raw)
    expected = [
        False,
        True,
        True,
        False,
        True,
        False,
        True,
        True,
        False,
        False,
        True,
        False,
        pd.NA,
        pd.NA,
        True,
        False,
        pd.NA,
    ]
    assert result.dtype == "boolean"
    for actual_value, expected_value in zip(result.tolist(), expected, strict=True):
        if expected_value is pd.NA:
            assert actual_value is pd.NA
        else:
            assert actual_value is expected_value


def test_normalizer_all_blank_column_is_all_null() -> None:
    """Mirrors the pre-2023q2 case: the column is absent, so every value
    the caller passes in is already ``pd.NA``."""
    raw = pd.Series([pd.NA, pd.NA, pd.NA], dtype="string")
    result = collect_sec_insider_transactions.normalize_10b5_1_flag(raw)
    assert result.isna().all()


# --------------------------------------------------------------------------
# feature builder plan / nonplan / unknown split
# --------------------------------------------------------------------------


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
    is_10b5_1: bool | None,
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
        "is_director": False,
        "is_officer": False,
        "is_ten_percent_owner": False,
        "is_10b5_1": is_10b5_1,
    }


def _transactions_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["trans_date"] = pd.to_datetime(frame["trans_date"])
    frame["owner_cik"] = frame["owner_cik"].astype("Int64")
    for column in ("is_director", "is_officer", "is_ten_percent_owner"):
        frame[column] = frame[column].astype("boolean")
    frame["is_10b5_1"] = frame["is_10b5_1"].astype("boolean")
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


def test_plan_flagged_buy_excluded_from_nonplan_included_in_plan() -> None:
    rows = [
        _row(
            accession="P1",
            symbol="PLAN1",
            owner_cik=111,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=5.0,
            is_10b5_1=True,
        )
    ]
    row = _last_row(_build_year_frame(rows), "PLAN1")
    assert row["open_market_buy_count_plan_60d"] == pytest.approx(1.0)
    assert row["net_buy_usd_plan_60d"] == pytest.approx(5000.0)
    assert row["open_market_buy_count_nonplan_60d"] == pytest.approx(0.0)
    assert row["net_buy_usd_nonplan_60d"] == pytest.approx(0.0)
    assert row["buyers_nonplan_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_flag_unknown_60d"] == pytest.approx(0.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(1.0)


def test_nonplan_flagged_buy_lands_in_nonplan_not_plan() -> None:
    rows = [
        _row(
            accession="N1",
            symbol="NONPLAN1",
            owner_cik=222,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=400.0,
            price=10.0,
            is_10b5_1=False,
        )
    ]
    row = _last_row(_build_year_frame(rows), "NONPLAN1")
    assert row["open_market_buy_count_nonplan_60d"] == pytest.approx(1.0)
    assert row["net_buy_usd_nonplan_60d"] == pytest.approx(4000.0)
    assert row["buyers_nonplan_60d"] == pytest.approx(1.0)
    assert row["open_market_buy_count_plan_60d"] == pytest.approx(0.0)
    assert row["net_buy_usd_plan_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_flag_unknown_60d"] == pytest.approx(0.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(1.0)


def test_null_flagged_buy_lands_only_in_unknown_counter() -> None:
    """Mirrors the pre-2023q2 case: ``is_10b5_1`` is null, not False --
    this buy must not be silently counted as nonplan."""
    rows = [
        _row(
            accession="U1",
            symbol="UNK1",
            owner_cik=333,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=300.0,
            price=10.0,
            is_10b5_1=None,
        )
    ]
    row = _last_row(_build_year_frame(rows), "UNK1")
    assert row["open_market_buy_count_flag_unknown_60d"] == pytest.approx(1.0)
    assert row["open_market_buy_count_nonplan_60d"] == pytest.approx(0.0)
    assert row["net_buy_usd_nonplan_60d"] == pytest.approx(0.0)
    assert row["buyers_nonplan_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_plan_60d"] == pytest.approx(0.0)
    assert row["net_buy_usd_plan_60d"] == pytest.approx(0.0)
    assert row["open_market_buy_count_60d"] == pytest.approx(1.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(0.0)


def test_coverage_zero_for_all_pre_2023_style_unknown_window() -> None:
    """A window with several buys, all null-flagged (the pre-2023q2
    shape): coverage must read 0.0, not NaN or something that looks like
    the filter was applied."""
    rows = [
        _row(
            accession=f"H{i}",
            symbol="PRE23",
            owner_cik=400 + i,
            owner_seq=0,
            filing_date="2024-01-1" + str(i),
            trans_date="2024-01-0" + str(i),
            shares=100.0,
            price=10.0,
            is_10b5_1=None,
        )
        for i in range(1, 4)
    ]
    row = _last_row(_build_year_frame(rows), "PRE23")
    assert row["open_market_buy_count_60d"] == pytest.approx(3.0)
    assert row["open_market_buy_count_flag_unknown_60d"] == pytest.approx(3.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(0.0)


def test_coverage_one_when_every_filing_carries_a_flag() -> None:
    rows = [
        _row(
            accession="C1",
            symbol="COVER1",
            owner_cik=501,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=100.0,
            price=10.0,
            is_10b5_1=False,
        ),
        _row(
            accession="C2",
            symbol="COVER1",
            owner_cik=502,
            owner_seq=0,
            filing_date="2024-01-11",
            trans_date="2024-01-09",
            shares=200.0,
            price=10.0,
            is_10b5_1=True,
        ),
    ]
    row = _last_row(_build_year_frame(rows), "COVER1")
    assert row["open_market_buy_count_60d"] == pytest.approx(2.0)
    assert row["open_market_buy_count_flag_unknown_60d"] == pytest.approx(0.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(1.0)


def test_coverage_default_when_window_has_no_buys_at_all() -> None:
    """No buys in the window at all: coverage is defined as 0.0 rather
    than NaN (a 0/0 fraction), so it never silently propagates NaN into a
    downstream screen."""
    rows = [
        _row(
            accession="S1",
            symbol="NOBUY1",
            owner_cik=601,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=100.0,
            price=10.0,
            is_10b5_1=False,
            trans_code="S",
            acquired_disposed="D",
        )
    ]
    row = _last_row(_build_year_frame(rows), "NOBUY1")
    assert row["open_market_buy_count_60d"] == pytest.approx(0.0)
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(0.0)


def test_joint_filing_still_dedupes_dollars_once_buyers_twice() -> None:
    """``owner_count=2``, rows with ``owner_seq`` 0 and 1, identical shares
    and price, both nonplan-flagged -- dollars count once (owner_seq == 0
    only), distinct owners count once per owner row, same joint-filing rule
    as the role split."""
    rows = [
        _row(
            accession="J1",
            symbol="JOINT2",
            owner_cik=701,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=20.0,
            is_10b5_1=False,
        ),
        _row(
            accession="J1",
            symbol="JOINT2",
            owner_cik=702,
            owner_seq=1,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=1000.0,
            price=20.0,
            is_10b5_1=False,
        ),
    ]
    row = _last_row(_build_year_frame(rows), "JOINT2")
    assert row["net_buy_usd_nonplan_60d"] == pytest.approx(20000.0)
    assert row["open_market_buy_count_nonplan_60d"] == pytest.approx(1.0)
    assert row["buyers_nonplan_60d"] == pytest.approx(2.0)


def test_nonplan_plus_plan_plus_unknown_equals_total_buy_count() -> None:
    rows = [
        _row(
            accession="M1",
            symbol="MIX2",
            owner_cik=801,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=100.0,
            price=10.0,
            is_10b5_1=False,
        ),
        _row(
            accession="M2",
            symbol="MIX2",
            owner_cik=802,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=200.0,
            price=10.0,
            is_10b5_1=True,
        ),
        _row(
            accession="M3",
            symbol="MIX2",
            owner_cik=803,
            owner_seq=0,
            filing_date="2024-01-10",
            trans_date="2024-01-08",
            shares=300.0,
            price=10.0,
            is_10b5_1=None,
        ),
    ]
    row = _last_row(_build_year_frame(rows), "MIX2")
    assert row["open_market_buy_count_60d"] == pytest.approx(3.0)
    assert row["open_market_buy_count_60d"] == pytest.approx(
        row["open_market_buy_count_nonplan_60d"]
        + row["open_market_buy_count_plan_60d"]
        + row["open_market_buy_count_flag_unknown_60d"]
    )
    assert row["tenb5one_flag_coverage_60d"] == pytest.approx(2.0 / 3.0)
