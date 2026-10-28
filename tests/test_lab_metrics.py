import numpy as np
import pandas as pd
import pytest

from open_composer.lab import DSRConfig, dsr_summary
from open_composer.lab.metrics import session_returns
from open_composer.research.campaign_statistics import deflated_sharpe_probability
from open_composer.research.scorecard_v2 import dsr


def series():
    return pd.Series(
        np.sin(np.arange(80) * 0.7) * 0.008 + 0.0006,
        index=pd.bdate_range("2024-01-02", periods=80),
    )


def test_dsr_methods_reuse_their_distinct_native_definitions():
    returns = series()
    benchmark = pd.Series(0.0001, index=returns.index)
    scorecard = DSRConfig(
        method="scorecard_v2",
        benchmark=benchmark,
        benchmark_note="Synthetic cash",
        var_sr_annual=0.7,
        n_eff=3,
        assumptions="Fixture dispersion; iid source estimator, serial dependence unadjusted",
    )
    campaign = DSRConfig(
        method="campaign_statistics",
        benchmark=benchmark,
        benchmark_note="Synthetic cash",
        hac_lag=5,
        assumptions="All 8 started trials; native HAC lag 5, no independent-trial discount",
    )
    a = dsr_summary(returns, n_trials=8, config=scorecard)
    b = dsr_summary(returns, n_trials=8, config=campaign)
    excess = (returns - benchmark).to_numpy()
    assert a["dsr"] == pytest.approx(dsr(excess, var_sr_annual=0.7, n_eff=3)["dsr"])
    assert b["dsr"] == pytest.approx(deflated_sharpe_probability(excess, trial_count=8, hac_lag=5))
    assert a["dsr"] != pytest.approx(b["dsr"])
    assert a["parameters"]["n_eff"] == 3
    assert b["n_trials"] == 8


@pytest.mark.parametrize("method", ["scorecard_v2", "campaign_statistics"])
def test_missing_and_inapplicable_dsr_is_null_with_reason(method):
    returns = series()
    missing = dsr_summary(returns, n_trials=2, config=DSRConfig(method=method))
    assert missing["dsr"] is None
    assert "benchmark" in missing["reason"]
    benchmark = pd.Series(0.0, index=returns.index)
    invalid = dsr_summary(
        returns * 0,
        n_trials=1,
        config=DSRConfig(method=method, benchmark=benchmark, assumptions="Fixture", hac_lag=5),
    )
    assert invalid["dsr"] is None
    assert "variable" in invalid["reason"]


def test_missing_benchmark_dates_are_not_silently_zero_filled():
    returns = series()
    result = dsr_summary(
        returns,
        n_trials=3,
        config=DSRConfig(
            method="campaign_statistics",
            benchmark=returns.iloc[1:] * 0,
            hac_lag=5,
            assumptions="Fixture",
        ),
    )
    assert result["dsr"] is None
    assert "calendar differs" in result["reason"]


def test_bar_returns_compound_on_declared_local_session_date():
    dates = pd.to_datetime(["2024-01-02T23:59Z", "2024-01-03T00:01Z"])
    result = session_returns(pd.Series([0.1, -0.1], index=dates), timezone="America/New_York")
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(-0.01)
    with pytest.raises(ValueError, match="timezone"):
        session_returns(pd.Series([0.1], index=pd.to_datetime(["2024-01-02"])), timezone="UTC")
