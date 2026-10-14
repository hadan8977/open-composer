"""Accounting checks on artificial values; never an economic result."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

PATH = Path(__file__).with_name("evaluate_application.py")
SPEC = importlib.util.spec_from_file_location("application", PATH)
application = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(application)


def test_dividends_receivable_cash_budget_and_no_terminal_trade():
    prices = pd.Series(
        [100.0, 98.0, 98.0], index=pd.to_datetime(["2024-09-10", "2024-09-11", "2024-09-12"])
    )
    quotes = {"2024-09-10": {"valid_quote": True, "quote": {"ap": 100.0}, "quote_age_seconds": 1}}
    dividends = [{"ex_date": "2024-09-11", "payable_date": "2024-09-12", "amount": 2.0}]
    ledger, summary = application.cash_account(prices, quotes, 20, dividends)
    assert summary["shares"] == 199
    assert summary["initial_cash"] >= 0
    assert ledger.loc["2024-09-11", "cash"] == ledger.loc["2024-09-10", "cash"]
    assert ledger.loc["2024-09-11", "dividend_receivable"] == 398
    assert ledger.loc["2024-09-12", "cash"] - ledger.loc["2024-09-11", "cash"] == 398
    assert ledger.equity.nunique() == 1
    assert summary["terminal_liquidation_included"] is False
    assert summary["dividend_reinvestment"] is False


def test_missing_quote_does_not_use_ohlc_as_execution():
    account, summary = application.cash_account(pd.Series([99.0]), {}, 20, [])
    assert account is None and summary["exact_entry"] is None


def test_drifting_weights_preserve_two_leg_account_value():
    index = pd.date_range("2025-01-01", periods=3)
    a = pd.Series([1, 2, 1], index=index)
    b = pd.Series([1, 1, 1], index=index)
    drifting = application.returns_from_wealth(0.8 * a + 0.2 * b)
    assert np.isclose((1 + drifting).prod(), 1)
    constant_weight = pd.Series([0, 0.8, -0.4], index=index)
    assert not np.isclose((1 + constant_weight).prod(), 1)


def test_stationary_bootstrap_is_bound_and_reproducible():
    a = application.stationary_indexes(90, 10, 4201)
    assert np.array_equal(a, application.stationary_indexes(90, 10, 4201))
    assert a.shape == (10, 90) and a.min() >= 0 and a.max() < 90
