import numpy as np
from hf_features import CausalJumpFilter, aggregate_day, current_har, prior_channels


def data():
    rng = np.random.default_rng(18)
    return np.arange(570, 961), rng.normal(0, 1e-4, (391, 5))


def test_overnight_is_separate_from_first15_and_hour():
    minutes, values = data()
    idx, sums, valid = aggregate_day(minutes, values, 26)
    np.testing.assert_allclose(idx[0], np.log1p(values[0]))
    np.testing.assert_allclose(sums[1], values[1:16].sum(0))
    previous = prior_channels(idx, sums, valid)
    har = current_har(idx, sums, valid, 4, previous)
    np.testing.assert_allclose(har["SUM"][5:10], values[1:61].sum(0) / 4)


def test_inv_eliminates_constant_simple_minute_offset_only():
    minutes, values = data()
    idx, sums, valid = aggregate_day(minutes, values, 26)
    other_idx, other_sum, other_valid = aggregate_day(minutes, values + 0.002, 26)
    a = current_har(idx, sums, valid, 6, prior_channels(idx, sums, valid))
    b = current_har(
        other_idx, other_sum, other_valid, 6, prior_channels(other_idx, other_sum, other_valid)
    )
    np.testing.assert_allclose(a["INV"], b["INV"], atol=1e-15, rtol=1e-12)
    assert not np.allclose(a["IDX"], b["IDX"])


def test_future_tail_or_target_changes_do_not_change_current_packet():
    minutes, values = data()
    idx, sums, valid = aggregate_day(minutes, values, 26)
    previous = prior_channels(idx, sums, valid)
    a = current_har(idx, sums, valid, 4, previous)
    values[61:] = 0.04  # First future target minute and every later return.
    other = aggregate_day(minutes[:101], values[:101], 26)  # Missing future tail.
    b = current_har(*other, 4, previous)
    for view in a:
        np.testing.assert_array_equal(a[view], b[view])


def test_missing_current_minute_is_not_filled_but_future_missing_does_not_reject():
    minutes, values = data()
    idx, sums, valid = aggregate_day(minutes, values, 26)
    previous = prior_channels(idx, sums, valid)
    mask = minutes != 610
    missing = aggregate_day(minutes[mask], values[mask], 26)
    assert current_har(*missing, 4, previous) is None
    mask = minutes != 650
    future_missing = aggregate_day(minutes[mask], values[mask], 26)
    assert current_har(*future_missing, 4, previous) is not None


def test_no_packet_activation_without_actual0930():
    minutes, values = data()
    assert aggregate_day(minutes[1:], values[1:], 26) is None


def test_conditional_short_cutoff_quarantines_later_rows():
    minutes, values = data()
    idx, sums, valid = aggregate_day(minutes, values, 14)
    assert valid[:15].all() and not valid[15:].any()
    previous = prior_channels(idx, sums, valid)
    np.testing.assert_allclose(previous["SUM"], values[:211].sum(0))


def test_jump_threshold_is_lagged_and_not_contaminated_by_own_return():
    a, b = CausalJumpFilter(), CausalJumpFilter()
    for value in [0.001, 0.002]:
        a.observe_completed(value, 1, None)
        b.observe_completed(value, 1, None)
    _, threshold1 = a.observe_completed(0.003, 3, np.ones(26))
    _, threshold2 = b.observe_completed(0.20, 3, np.ones(26))
    expected = 3.5 * np.sqrt(np.pi / 2 * 26 * 0.001 * 0.002) * (1 / 26) ** 0.49
    np.testing.assert_allclose(threshold1, expected)
    assert threshold1 == threshold2


def test_time_of_day_requires_52_prior_complete_days_and_is_frozen_value():
    a = CausalJumpFilter()
    for _ in range(51):
        a.full_days.append(np.arange(1, 27) * 0.001)
    assert a.day_tau() is None
    a.full_days.append(np.arange(1, 27) * 0.001)
    tau = a.day_tau()
    np.testing.assert_allclose(tau, np.arange(1, 27) ** 2 / np.mean(np.arange(1, 27) ** 2))
    a.full_days.append(np.ones(26) * 20)
    np.testing.assert_allclose(tau, np.arange(1, 27) ** 2 / np.mean(np.arange(1, 27) ** 2))
