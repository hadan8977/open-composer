from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import run_t20260929_35_overnight_persistence as t35
from scripts import run_t20260930_14_overnight_12m as t14


def test_pool_b_rank_band_includes_both_ends() -> None:
    rank = np.array([1, 1500, 1501, 2000, 3000, 3001, np.nan])
    got = t14.pool_b_mask(rank)
    assert got.tolist() == [False, False, True, True, True, False, False]


def test_sample_days_reproducible_and_without_replacement() -> None:
    eligible = pd.bdate_range("2024-01-08", "2026-09-29")
    a = t14.sample_days(eligible)
    b = t14.sample_days(list(eligible))
    assert a == b
    assert len(a) == 20 and len(set(a)) == 20
    assert a == sorted(a)
    assert set(a) <= {str(d.date()) for d in eligible}
    days = sorted(str(d.date()) for d in eligible)
    rng = np.random.default_rng(20260930)
    expect = sorted(days[i] for i in rng.choice(len(days), size=20, replace=False))
    assert a == expect
    assert t14.sample_days(eligible, seed=1) != a


def test_on252_signal_matches_t35_rolling_signals() -> None:
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=300)
    on = pd.DataFrame(rng.normal(0, 0.01, (300, 4)), index=idx, columns=list("ABCD"))
    on.iloc[:80, 0] = np.nan
    id_ = pd.DataFrame(rng.normal(0, 0.01, (300, 4)), index=idx, columns=list("ABCD"))
    pd.testing.assert_frame_equal(t14.on252_signal(on), t35.rolling_signals(on, id_)["ON252"])


def test_adjustment_factor_and_official_return() -> None:
    f_t = t14.adj_factor(50.0, 100.0)  # 2-for-1 split adjusted price 50 vs raw 100
    f_n = t14.adj_factor(51.0, 102.0)
    assert f_t == 0.5 and f_n == 0.5
    # raw open 102.0 vs raw close 100.0 -> +2 percent on the adjusted basis too
    assert abs(t14.official_return(102.0, 100.0, f_n, f_t) - 0.02) < 1e-12
    # split night: raw prices halve; the factor ratio restores the true return
    f_split_next = t14.adj_factor(50.0, 50.0)  # next day is post split, factor 1
    f_split_t = t14.adj_factor(25.0, 50.0)  # local adjusted 25 vs raw 50 pre split
    assert abs(t14.official_return(25.5, 50.0, f_split_next, f_split_t) - 0.02) < 1e-12
    assert np.isnan(t14.adj_factor(np.nan, 10.0))
    assert np.isnan(t14.official_return(np.nan, 1.0, 1.0, 1.0))


def test_delta_pairing_and_day_then_day_mean() -> None:
    r_off = np.array([0.0110, 0.0050, 0.0000, np.nan])
    r_day = np.array([0.0100, 0.0060, 0.0010, 0.0200])
    delta = t14.pair_delta(r_off, r_day)
    np.testing.assert_allclose(delta[:3], [0.0010, -0.0010, -0.0010])
    assert np.isnan(delta[3])
    days = np.array(["d1", "d1", "d2", "d2"])
    mean, n_days = t14.day_then_day_mean(delta, days)
    # d1 mean = 0.0, d2 mean over finite = -0.0010 -> -0.0005
    assert n_days == 2 and abs(mean - (-0.0005)) < 1e-12


def test_delta_ls_by_day_uses_long_minus_short_and_drops_incomplete_days() -> None:
    delta = np.array([0.0002, 0.0004, -0.0002, 0.0001, 0.0009])
    days = np.array(["d1", "d1", "d1", "d2", "d2"])
    leg = np.array(["long", "long", "short", "long", "long"])
    mean, n = t14.delta_ls_by_day(delta, days, leg)
    # d1: mean(long)=0.0003 minus short(-0.0002) = 0.0005; d2 has no short leg -> dropped
    assert n == 1 and abs(mean - 0.0005) < 1e-12


def test_gate_a_boundaries() -> None:
    assert t14.gate_a(5.0, 2.0, 3.0, 2.0)  # t = 2.0 passes (>=)
    assert not t14.gate_a(5.0, 1.999, 3.0, 2.5)
    assert not t14.gate_a(5.0, 3.0, 3.0, 1.99)
    assert not t14.gate_a(0.0, 3.0, 3.0, 3.0)  # mean must be > 0
    assert not t14.gate_a(5.0, 3.0, -0.1, 3.0)
    assert not t14.gate_a(float("nan"), 3.0, 3.0, 3.0)


def test_gate_b_boundaries() -> None:
    assert t14.gate_b(-4.0, -4.0, 0.10)  # delta = -4 bp and missing 10 percent pass
    assert not t14.gate_b(-4.01, 0.0, 0.05)
    assert not t14.gate_b(0.0, -4.01, 0.05)
    assert not t14.gate_b(0.0, 0.0, 0.1001)
    assert t14.gate_b(-1.0, -2.0, 20 / 200)
    assert not t14.gate_b(float("nan"), 0.0, 0.0)
