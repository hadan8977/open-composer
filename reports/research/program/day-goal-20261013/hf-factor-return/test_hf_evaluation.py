import numpy as np
from hf_diagnostics import run_fractional
from hf_evaluate import continuous_metrics, descriptive_dsr, hac_ratio, paired_inference


def test_hac_uses_sum_loss_sum_window_count_not_daily_unweighted_mean():
    actual = hac_ratio([1, 9], [1, 3])
    assert actual["loss_control_minus_treatment"] == 2.5
    assert actual["windows"] == 4


def test_all_and_cts_comparisons_each_use_one_common_realized_target(tmp_path, monkeypatch):
    import hf_evaluate

    monkeypatch.setattr(hf_evaluate, "OUT", tmp_path)
    n = 60
    pred = np.column_stack((np.full(n, 0.05), np.zeros(n)))
    rows = [dict(date=f"2004-01-{i // 3 + 1:02d}") for i in range(n)]
    contrast = [dict(contrast_id="test", treatment_id="CTS_TRAIN", control_id="ALL_TRAIN")]
    result = paired_inference(
        pred, np.full(n, 0.1), np.zeros(n), rows, ["CTS_TRAIN", "ALL_TRAIN"], contrast
    )
    np.testing.assert_allclose(
        result["All_primary"]["paired"][0]["loss_control_minus_treatment"], 0.0075
    )
    np.testing.assert_allclose(
        result["Cts_descriptive"]["paired"][0]["loss_control_minus_treatment"], -0.0025
    )


def test_internal_unknown_is_not_dropped_from_terminal_or_physical_excess():
    dates = ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07"]
    result = continuous_metrics([20000, 20010, None, 20100], dates)
    assert result["terminal_NAV"] is None and not result["continuous_NAV_ready"]
    full = continuous_metrics([20000, 20010, 20020, 20100], dates, [20000, None, None, None])
    assert full["continuous_NAV_ready"] and full["primary_physical_Sharpe_ex_BIL"] is None


def test_descriptive_dsr_does_not_remove_effective_multiple_testing():
    rng = np.random.default_rng(18)
    nav = np.r_[1.0, np.cumprod(1 + rng.normal(0.0003, 0.01, 400))]
    small = descriptive_dsr(nav, 20)
    full = descriptive_dsr(nav, 4400)
    assert full["probability"] < small["probability"] and not full["promotion_evidence"]


def test_fractional_delayed_reference_is_not_executed_at_nominal_time():
    dates = ["2016-01-04", "2016-01-05", "2016-01-06"]
    days = [dict(date=d, regular15_windows=7) for d in dates[:2]]
    bars = {dates[1]: {k: dict(open=10.0, close=10.0, first_price_age_minutes=0) for k in range(7)}}
    bars[dates[1]][4]["first_price_age_minutes"] = 2
    result = run_fractional(
        days,
        bars,
        {d: 10.0 for d in dates},
        {(dates[1], 630): 0.01},
        [],
        dates,
        0.002,
        "SPositive",
        False,
        0,
    )
    attempt = result["events"][result["events"]["minute"] == 630]
    assert len(attempt) == 1 and attempt["status"][0] == 0 and attempt["q_after"][0] == 0
