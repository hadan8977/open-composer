from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import run_t20260929_35_overnight_persistence as m


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2024-01-02", periods=6)
    open_w = pd.DataFrame(
        {"A": [10.0, 11.0, 12.1, 12.1, 13.0, 13.0], "B": [20.0, 20.0, 21.0, 22.0, 22.0, 23.0]},
        index=dates,
    )
    close_w = pd.DataFrame(
        {"A": [10.5, 11.5, 12.0, 12.5, 12.8, 13.5], "B": [20.5, 20.8, 21.5, 22.5, 22.3, 23.5]},
        index=dates,
    )
    return open_w, close_w


def test_overnight_and_intraday_use_the_right_prices() -> None:
    open_w, close_w = _frames()
    on, id_ = m.overnight_intraday_returns(open_w, close_w)
    assert np.isnan(on.iloc[0]["A"])
    assert on.iloc[1]["A"] == pytest.approx(np.log(11.0 / 10.5))
    assert id_.iloc[1]["A"] == pytest.approx(np.log(11.5 / 11.0))


def test_next_night_return_is_close_t_to_open_t_plus_1() -> None:
    open_w, close_w = _frames()
    r = m.next_night_return(open_w, close_w)
    assert r.iloc[0]["A"] == pytest.approx(11.0 / 10.5 - 1.0)
    assert r.iloc[2]["B"] == pytest.approx(22.0 / 21.5 - 1.0)
    assert np.isnan(r.iloc[-1]["A"])
    idn = m.next_day_intraday_return(open_w, close_w)
    assert idn.iloc[0]["A"] == pytest.approx(11.5 / 11.0 - 1.0)


def test_signal_intraday_part_only_uses_t_minus_1() -> None:
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-02", periods=40)
    on = pd.DataFrame(rng.normal(0, 0.01, (40, 3)), index=dates, columns=list("ABC"))
    id_ = pd.DataFrame(rng.normal(0, 0.01, (40, 3)), index=dates, columns=list("ABC"))
    base = m.rolling_signals(on, id_)
    id_changed = id_.copy()
    id_changed.iloc[30] += 0.5  # the intraday return of t=30 is only known at the close of 30
    changed = m.rolling_signals(on, id_changed)
    # signal at t=30 must not see ID_30, signal at t=31 must
    pd.testing.assert_series_equal(base["TOW21"].iloc[30], changed["TOW21"].iloc[30])
    assert not np.allclose(base["TOW21"].iloc[31], changed["TOW21"].iloc[31])
    # ON_t of the same day is part of the signal (known at 09:30)
    on_changed = on.copy()
    on_changed.iloc[30] += 0.5
    assert not np.allclose(m.rolling_signals(on_changed, id_)["ON5"].iloc[30], base["ON5"].iloc[30])
    # ON_L is the mean of the last L values and needs 0.8 L observations
    assert base["ON5"].iloc[10]["A"] == pytest.approx(on["A"].iloc[6:11].mean())
    assert np.isnan(base["ON21"].iloc[10]["A"])  # only 11 observations, needs 17
    assert base["TOW21"].iloc[30]["B"] == pytest.approx(
        on["B"].iloc[10:31].mean() - id_["B"].iloc[9:30].mean()
    )


def test_decile_long_short_on_toy_data() -> None:
    signal = np.arange(100, dtype="float64")
    ret = np.where(signal >= 90, 0.010, np.where(signal < 10, -0.004, 0.001))
    out = m.decile_long_short(signal, ret)
    assert out is not None
    assert out["k"] == 10
    assert out["long"] == pytest.approx(0.010)
    assert out["short"] == pytest.approx(-0.004)
    assert out["ls"] == pytest.approx(0.014)
    assert m.decile_long_short(np.arange(40, dtype="float64"), np.zeros(40)) is None  # k=4 < 5


def test_friday_night_borrow_counts_three_days() -> None:
    dates = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"])
    days = m.days_to_next_session(dates)
    assert list(days[:3]) == [1.0, 3.0, 1.0]
    assert np.isnan(days[-1])
    # 5% annual borrow, Friday night (3 days) vs weekday night (1 day), day count 360
    assert m.borrow_cost_bp(0.05, 3.0) == pytest.approx(0.05 * 3 / 360 * 1e4)
    assert m.borrow_cost_bp(0.05, 3.0) == pytest.approx(3 * m.borrow_cost_bp(0.05, 1.0))


def test_borrow_rate_tiers() -> None:
    rate = m.borrow_rate_from_dv21(np.array([1e6, 6e6, 5e7, 5e8, np.nan]))
    assert rate[:4].tolist() == [0.05, 0.05, 0.02, 0.005]
    assert np.isnan(rate[4])


@pytest.mark.parametrize(
    ("mean_bp", "t_nw", "beat", "t_min", "expected"),
    [
        (7.99, 5.0, 1.0, 2.0, "closed"),
        (8.0, 5.0, 1.0, 2.0, "marginal"),
        (15.99, 5.0, 1.0, 2.0, "marginal"),
        (16.0, 2.0, 0.90, 2.0, "pass"),
        (16.0, 1.99, 0.90, 2.0, "closed"),
        (16.0, 2.0, 0.89, 2.0, "closed"),
        (20.0, 2.49, 1.0, 2.5, "closed"),
        (20.0, 2.5, 1.0, 2.5, "pass"),
        (12.0, 2.0, 0.95, 2.0, "marginal"),
        (float("nan"), 3.0, 1.0, 2.0, "closed"),
    ],
)
def test_tier_rule_boundaries(
    mean_bp: float, t_nw: float, beat: float, t_min: float, expected: str
) -> None:
    assert m.tier_from_stats(mean_bp, t_nw, beat, t_min) == expected


def test_stress_class() -> None:
    assert m.stress_class_from_stats(8.0, 2.0) == "robust"
    assert m.stress_class_from_stats(7.9, 5.0) == "recent_only"
    assert m.stress_class_from_stats(20.0, 1.9) == "recent_only"


def test_series_stats_and_newey_west() -> None:
    x = np.array([0.0010, 0.0020, -0.0005, 0.0015, 0.0012, 0.0008, 0.0011, 0.0004])
    s = m.series_stats(x)
    assert s["n"] == 8
    assert s["mean_bp"] == pytest.approx(x.mean() * 1e4)
    assert s["sharpe"] == pytest.approx(x.mean() / x.std(ddof=1) * np.sqrt(252))
    assert np.isfinite(s["t_nw5"])
    assert m.series_stats(np.array([]))["n"] == 0


def test_cell_ids_are_the_twenty_registered_candidates() -> None:
    ids = m.cell_ids()
    assert len(ids) == 20 and len(set(ids)) == 20
    assert m.DECISION_CELL in ids and m.SECONDARY_CELL in ids


def test_cell_series_ls_lo_and_costs() -> None:
    n_names = 100
    dates = pd.DatetimeIndex(["2024-01-04", "2024-01-05"])
    sig = np.arange(n_names, dtype="float64")
    rows = []
    for d in dates:
        for j in range(n_names):
            rows.append(
                {
                    "date": d,
                    "symbol": f"S{j:03d}",
                    "p1500": True,
                    "on21": sig[j],
                    "r": 0.010 if j >= 90 else (-0.004 if j < 10 else 0.001),
                    "idn": -0.001,
                    "spread21": 0.001,
                    "borrow_rate": 0.05,
                    "dtc_cross_sectional_pct": 0.5,
                }
            )
    panel = pd.DataFrame(rows)
    starts = np.array([0, n_names])
    ends = np.array([n_names, 2 * n_names])
    days = m.days_to_next_session(dates)
    ls = m.run_cell_series(
        panel, "p1500", "on21", "LS", dates, np.array([3.0, np.nan]), starts, ends
    )
    assert ls["gross"].iloc[0] == pytest.approx(0.014)
    # continuous 1x: 2 legs x 2 sides x (0.5 x 10 bp + 2 bp) = 28 bp
    assert ls["cont1_bp"].iloc[0] == pytest.approx(28.0)
    # borrow: 5% x 3 days / 360 = 4.1667 bp on the Friday night
    assert ls["borrow_bp"].iloc[0] == pytest.approx(0.05 * 3 / 360 * 1e4)
    nets = m.net_series(ls, "LS")
    assert nets["auction_1x"].iloc[0] == pytest.approx(0.014 - 8e-4 - ls["borrow_bp"].iloc[0] / 1e4)
    assert nets["auction_2x"].iloc[0] == pytest.approx(
        0.014 - 16e-4 - ls["borrow_bp"].iloc[0] / 1e4
    )
    assert nets["frozen_20"].iloc[0] == pytest.approx(0.014 - 80e-4 - ls["borrow_bp"].iloc[0] / 1e4)
    assert ls["idn_ls"].iloc[0] == pytest.approx(0.0)
    assert ls["gross_etb"].iloc[0] == pytest.approx(0.014)
    lo = m.run_cell_series(panel, "p1500", "on21", "LO", dates, days, starts, ends)
    assert lo["gross"].iloc[0] == pytest.approx(0.010 * 10 / 20 + 0.001 * 10 / 20)
    pool_mean = panel["r"].iloc[:n_names].mean()
    assert lo["excess"].iloc[0] == pytest.approx(lo["gross"].iloc[0] - pool_mean)
    # LO pays one leg: 2 sides x 2 bp on auction 1x
    assert m.net_series(lo, "LO")["auction_1x"].iloc[0] == pytest.approx(lo["gross"].iloc[0] - 4e-4)


def test_placebo_reproducible_and_centered() -> None:
    rng = np.random.default_rng(3)
    valid = {i: rng.normal(0, 0.02, 300) for i in range(50)}
    a = m.placebo_series(valid, 50, seed=7)
    b = m.placebo_series(valid, 50, seed=7)
    c = m.placebo_series(valid, 50, seed=8)
    np.testing.assert_array_equal(a, b)
    assert not np.allclose(a, c)
    assert abs(np.nanmean(a)) < 0.01
