"""Tests for scripts/run_h20260930_03_tax_loss_year_end.py.

Covers: the YTD signal only uses closes on or before the 15 December signal
day, the entry/exit rules when the 15th/16th/31 January are not trading days,
ADV-tiered costs, decile / -30% selection, and the five continue conditions.

Run only this file: ``uv run pytest tests/test_h20260930_03_tax_loss_year_end.py -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260930_03_tax_loss_year_end as t  # noqa: E402


def _cal(*ranges: tuple[str, str]) -> pd.DatetimeIndex:
    parts = [pd.bdate_range(a, b) for a, b in ranges]
    out = parts[0]
    for p in parts[1:]:
        out = out.union(p)
    return out


def test_signal_day_rolls_back_and_entry_rolls_forward_when_15th_is_weekend():
    # 2018-12-15 is a Saturday: signal = Friday the 14th, entry = Monday the 17th.
    cal = _cal(("2018-12-03", "2019-02-08"))
    pos = t.window_positions(cal, 2018, "W2", "X31")
    assert cal[pos["signal"]] == pd.Timestamp("2018-12-14")
    assert cal[pos["entry"]] == pd.Timestamp("2018-12-17")


def test_entry_is_first_session_on_or_after_16th_when_15th_is_a_session():
    # 2020-12-15 is a Tuesday: signal that day, entry Wednesday the 16th.
    cal = _cal(("2020-12-01", "2021-02-05"))
    pos = t.window_positions(cal, 2020, "W2", "X15")
    assert cal[pos["signal"]] == pd.Timestamp("2020-12-15")
    assert cal[pos["entry"]] == pd.Timestamp("2020-12-16")


def test_exit_uses_previous_session_on_weekend_or_holiday():
    # 2026-01-31 is a Saturday -> exit Friday 2026-01-30; 2026-01-15 is a Thursday.
    cal = _cal(("2025-12-01", "2026-02-05"))
    p31 = t.window_positions(cal, 2025, "W2", "X31")
    p15 = t.window_positions(cal, 2025, "W2", "X15")
    assert cal[p31["exit"]] == pd.Timestamp("2026-01-30")
    assert cal[p15["exit"]] == pd.Timestamp("2026-01-15")
    # a holiday missing from the calendar rolls back too
    cal2 = cal.drop(pd.Timestamp("2026-01-15"))
    p15b = t.window_positions(cal2, 2025, "W2", "X15")
    assert cal2[p15b["exit"]] == pd.Timestamp("2026-01-14")


def test_baseline_is_last_close_of_prior_year_and_first_open_when_absent():
    cal = _cal(("2019-12-20", "2020-03-01"))
    pos, field = t.baseline_position(cal, 2020)
    assert cal[pos] == pd.Timestamp("2019-12-31") and field == "close"
    cal_first = _cal(("2016-01-04", "2016-03-01"))
    pos, field = t.baseline_position(cal_first, 2016)
    assert cal_first[pos] == pd.Timestamp("2016-01-04") and field == "open"


def _synthetic_panel(n_syms: int = 40, seed: int = 0):
    cal = _cal(
        ("2018-12-20", "2019-02-05"), ("2019-02-06", "2019-12-31"), ("2020-01-01", "2020-02-05")
    )
    rng = np.random.default_rng(seed)
    syms = [f"S{i:02d}" for i in range(n_syms)]
    steps = 1 + rng.normal(0, 0.01, size=(len(cal), n_syms))
    close = pd.DataFrame(50.0 * np.cumprod(steps, axis=0), index=cal, columns=syms)
    open_ = close.shift(1).fillna(close.iloc[0]) * 1.001
    volume = pd.DataFrame(
        rng.uniform(1e5, 1e6, size=(len(cal), n_syms)) * (np.arange(n_syms) + 1),
        index=cal,
        columns=syms,
    )
    return close, open_, volume


def _pool(close, open_, volume, year=2019):
    cal = close.index
    base_pos, base_field = t.baseline_position(cal, year)
    pos = t.window_positions(cal, year, "W2", "X31")
    return t.build_pool_frame(
        close,
        open_,
        volume,
        base_pos=base_pos,
        base_field=base_field,
        sig_pos=pos["signal"],
        entry_pos=pos["entry"],
        exit_pos=pos["exit"],
    ), (base_pos, pos)


def test_ytd_signal_uses_only_closes_on_or_before_signal_day():
    close, open_, volume = _synthetic_panel()
    (frame, _), (_, pos) = _pool(close, open_, volume)
    ytd_before = frame["ytd"].copy()
    # scramble every close and volume AFTER the signal day
    close2, open2, vol2 = close.copy(), open_.copy(), volume.copy()
    after = close.index > close.index[pos["signal"]]
    close2.loc[after] *= 3.7
    open2.loc[after] *= 3.7
    vol2.loc[after] *= 5.0
    (frame2, _), _ = _pool(close2, open2, vol2)
    common = ytd_before.index.intersection(frame2.index)
    assert len(common) > 20
    pd.testing.assert_series_equal(ytd_before[common], frame2.loc[common, "ytd"])
    # and the rank (ADV) is unchanged too
    pd.testing.assert_series_equal(
        frame.loc[common, "rank"], frame2.loc[common, "rank"], check_names=False
    )


def test_ytd_value_and_return_convention():
    close, open_, volume = _synthetic_panel(n_syms=5)
    cal = close.index
    (frame, counts), (base_pos, pos) = _pool(close, open_, volume)
    sym = "S03"
    expected_ytd = close[sym].iloc[pos["signal"]] / close[sym].loc["2018-12-31"] - 1
    assert frame.loc[sym, "ytd"] == pytest.approx(expected_ytd)
    expected_ret = close[sym].iloc[pos["exit"]] / open_[sym].iloc[pos["entry"]] - 1
    assert frame.loc[sym, "ret"] == pytest.approx(expected_ret)
    assert cal[pos["entry"]] > cal[pos["signal"]]
    assert counts["n_pool"] == 5


def test_split_like_symbol_excluded_from_pool():
    close, open_, volume = _synthetic_panel(n_syms=6)
    # unadjusted 2-for-1 forward split in the YTD window creates a fake -50% loser
    close.loc["2019-06-03":, "S02"] *= 0.5
    open_.loc["2019-06-03":, "S02"] *= 0.5
    (frame, counts), _ = _pool(close, open_, volume)
    assert "S02" not in frame.index
    assert counts["n_split_like_excluded"] == 1


def test_tier_costs_by_adv_rank():
    assert t.tier_bps_per_side(1) == 3.0
    assert t.tier_bps_per_side(500) == 3.0
    assert t.tier_bps_per_side(501) == 6.0
    assert t.tier_bps_per_side(1000) == 6.0
    assert t.tier_bps_per_side(1001) == 12.0
    assert t.tier_bps_per_side(1500) == 12.0


def _frame(n=100):
    rank = np.arange(1, n + 1, dtype=float)
    return pd.DataFrame(
        {
            "ytd": np.linspace(-0.5, 0.5, n),
            "rank": rank,
            "ret": np.linspace(0.05, -0.05, n),
            "tier_bp": [t.tier_bps_per_side(r) for r in rank],
        },
        index=[f"X{i}" for i in range(n)],
    )


def test_select_decile_and_loss30_and_pool_b():
    frame = _frame(1500)
    pool, basket = t.select_basket(frame, "D10_A")
    assert len(pool) == 1500 and 149 <= len(basket) <= 151
    assert basket["ytd"].max() <= np.quantile(frame["ytd"], 0.10) + 1e-12
    poolb, basketb = t.select_basket(frame, "D10_B")
    assert len(poolb) == 1000 and poolb["rank"].min() == 501
    _, b30 = t.select_basket(frame, "L30_A")
    assert (b30["ytd"] <= -0.30).all() and len(b30) > 0


def test_cost_deducted_round_trip_from_basket_and_excess_vs_pool():
    frame = _frame(1500)
    pool, basket = t.select_basket(frame, "D10_A")
    m = t.basket_metrics(pool, basket, iwm_ret=0.01)
    expected_cost = (2 * basket["tier_bp"] / 1e4).mean()
    assert m["cost"] == pytest.approx(expected_cost)
    assert m["basket_net"] == pytest.approx(m["basket_gross"] - expected_cost)
    assert m["excess_net"] == pytest.approx(m["basket_net"] - pool["ret"].mean())
    assert m["excess_net_vs_iwm"] == pytest.approx(m["basket_net"] - 0.01)


def test_conditions_pass_and_each_condition_can_fail():
    years = t.YEARS
    good = {y: 0.03 for y in years}
    good[years[0]] = 0.028
    good[years[1]] = 0.032
    ev = t.evaluate_conditions(good, 0.002, 0.003)
    assert ev["all_pass"]
    # c1: small mean
    low = {y: 0.01 + (0.001 if i % 2 else -0.001) for i, y in enumerate(years)}
    assert not t.evaluate_conditions(low, 0.0, 0.0)["conditions"]["c1_mean_net_excess_ge_1p5pct"][
        "pass"
    ]
    # c2: only 6 positive years but large mean carried by two years
    six = {y: (0.2 if i < 2 else (0.01 if i < 6 else -0.01)) for i, y in enumerate(years)}
    ev6 = t.evaluate_conditions(six, 0.0, 0.0)
    assert ev6["stats"]["n_positive"] == 6
    assert not ev6["conditions"]["c2_positive_years_ge_7"]["pass"]
    # c4: placebo sum above half of real mean
    ev4 = t.evaluate_conditions(good, 0.012, 0.010)
    assert not ev4["conditions"]["c4_placebo_sum_le_half_real_mean"]["pass"]
    # c5: Dec 2025 negative
    neg = dict(good)
    neg[2025] = -0.001
    ev5 = t.evaluate_conditions(neg, 0.0, 0.0)
    assert not ev5["conditions"]["c5_dec2024_and_dec2025_positive"]["pass"]
    # missing year -> nothing passes
    miss = dict(good)
    miss[2020] = None
    assert not t.evaluate_conditions(miss, 0.0, 0.0)["all_pass"]


def test_annual_stats_t_and_without_best():
    vals = [0.02, 0.01, -0.01, 0.03, 0.00, 0.02, 0.01, 0.04, -0.02, 0.02]
    st = t.annual_stats(vals)
    arr = np.array(vals)
    assert st["mean"] == pytest.approx(arr.mean())
    assert st["t_clustered"] == pytest.approx(arr.mean() / (arr.std(ddof=1) / np.sqrt(10)))
    assert st["n_positive"] == 7
    assert st["mean_without_best"] == pytest.approx(np.delete(arr, arr.argmax()).mean())
