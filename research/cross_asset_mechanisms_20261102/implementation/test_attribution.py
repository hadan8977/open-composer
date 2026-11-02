"""Checks for the new scientific clock and valid-history eligibility."""
import numpy as np
import pandas as pd

from attribution import allocation_rules


def test_prior_month_and_prior_valid_mean_exclude_current_information():
    dates = pd.to_datetime(["2023-01-31", "2023-02-01", "2023-02-28", "2023-03-31", "2023-04-28"])
    raw = pd.Series([.5, .5, .9, .1, .6], index=dates)
    monthly = pd.Series([True, False, True, True, True], index=dates)
    valid = pd.Series([False, False, True, True, True], index=dates)
    rules = allocation_rules(raw, valid, monthly)
    np.testing.assert_allclose(rules["L1"], [.5, .5, .5, .75, .25])
    np.testing.assert_allclose(rules["H1"], [.5, .5, .5, .75, .5])
    # A current/future volatility shock cannot change either intervention today.
    shocked = raw.copy()
    shocked.iloc[3:] = .72
    revised = allocation_rules(shocked, valid, monthly)
    assert revised["A4"].iloc[3] != rules["A4"].iloc[3]
    assert revised["L1"].iloc[3] == rules["L1"].iloc[3]
    assert revised["H1"].iloc[3] == rules["H1"].iloc[3]
    assert revised["H1"].iloc[4] == (.75 + .72) / 2


def test_open_effective_average_excludes_final_close_decision():
    dates = pd.to_datetime(["2023-01-31", "2023-02-01", "2023-02-02", "2023-02-28"])
    raw = pd.Series([.6, .6, .6, .75], index=dates)
    valid = pd.Series(True, index=dates)
    monthly = pd.Series([True, False, False, True], index=dates)
    close_rule = allocation_rules(raw, valid, monthly)["A4"]
    assert close_rule.loc["2023-02-01":].mean() == (.6 + .6 + .75) / 3
    assert close_rule.shift(1).loc["2023-02-01":].mean() == .6
