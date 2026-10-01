from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import run_t20261001_02_dfc_cross_section as m


def _calendar(start: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


def test_position_labels_and_era_switch() -> None:
    cal = _calendar("2024-03-01", "2024-08-30")
    tau_idx = m.month_end_indices(cal)
    taus = [cal[i] for i in tau_idx]
    assert pd.Timestamp("2024-04-30") in taus and pd.Timestamp("2024-05-31") in taus
    frame = m.build_event_frame(cal, tau_idx)
    # April tau (pre-reform): b = tau-4, pre window = tau-9..tau-4, post = tau-3..tau+3
    t_apr = int(np.flatnonzero(cal == pd.Timestamp("2024-04-30"))[0])
    assert frame["pre"].iloc[t_apr - 9 : t_apr - 3].all()
    assert not frame["pre"].iloc[t_apr - 3]
    assert frame["post"].iloc[t_apr - 3 : t_apr + 4].all()
    assert frame["seg"].iloc[t_apr] == "pre"
    # May tau (reform in force): b = tau-3
    t_may = int(np.flatnonzero(cal == pd.Timestamp("2024-05-31"))[0])
    assert frame["pre"].iloc[t_may - 8 : t_may - 2].all()
    assert not frame["pre"].iloc[t_may - 2]
    assert frame["post"].iloc[t_may - 2 : t_may + 4].all()
    assert frame["seg"].iloc[t_may] == "post"
    assert frame["pos"].iloc[t_may] == 0
    assert frame["pos"].iloc[t_may - 4] == -4
    assert frame["pos"].iloc[t_may + 2] == 2
    assert frame["pos"].iloc[t_may + 6] == 6
    assert m.settle_offset(pd.Timestamp("2024-05-24")) == 4
    assert m.settle_offset(pd.Timestamp("2024-05-28")) == 3


def test_deciles_and_group_freezing() -> None:
    mom = np.arange(100, dtype=float)[::-1].copy()  # highest momentum first
    mom[7] = np.nan
    dec = m.assign_deciles(mom)
    assert np.isnan(dec[7])
    counts = pd.Series(dec[np.isfinite(dec)]).value_counts()
    assert counts.min() >= 9 and counts.max() <= 10
    assert dec[99] == 1 and dec[0] == 10  # lowest momentum -> D1
    form = np.array([100, 120, 140])
    assert m.formation_for_day(103, form) == -1
    assert m.formation_for_day(104, form) == 0
    assert m.formation_for_day(123, form) == 0  # frozen through tau_{f+1}+3
    assert m.formation_for_day(124, form) == 1


def test_m3_three_observations_per_month() -> None:
    cal = _calendar("2023-01-02", "2023-06-30")
    tau_idx = m.month_end_indices(cal)
    vals = pd.Series(0.0, index=cal)
    t = int(tau_idx[2])
    vals.iloc[t - 4] = 0.01
    vals.iloc[t - 3] = -0.02
    vals.iloc[t + 5 : t + 9] = [0.001, 0.002, 0.003, 0.004]
    obs = m.m3_observations(vals, cal, tau_idx)
    sub = obs[obs["tau"] == cal[t]].set_index("obs")["r"]
    assert len(obs) % 3 == 0
    assert sub["tm4"] == 0.01 and sub["tm3"] == -0.02
    assert abs(sub["ctrl"] - 0.0025) < 1e-12


def test_hac_diff_t_matches_brute_force() -> None:
    rng = np.random.default_rng(3)
    n = 120
    obs = pd.DataFrame(
        {
            "tau": np.repeat(pd.date_range("2019-01-31", periods=n // 3, freq="ME"), 3),
            "obs": np.tile(["tm4", "tm3", "ctrl"], n // 3),
            "r": rng.normal(0, 0.01, n),
        }
    )
    post = (obs["tau"] >= pd.Timestamp("2021-01-01")).to_numpy()
    est = m.m3_estimate(obs, post, lags=3)
    d4 = (obs["obs"] == "tm4").to_numpy(float)
    d3 = (obs["obs"] == "tm3").to_numpy(float)
    po = post.astype(float)
    x = np.column_stack([np.ones(n), d4, d3, po, d4 * po, d3 * po])
    y = obs["r"].to_numpy()
    beta = np.linalg.solve(x.T @ x, x.T @ y)
    e = y - x @ beta
    idx = np.arange(n)
    omega = np.clip(1.0 - np.abs(idx[:, None] - idx[None, :]) / 4.0, 0.0, None)
    xtx_inv = np.linalg.inv(x.T @ x)
    meat = x.T @ (omega * np.outer(e, e)) @ x
    cov = xtx_inv @ meat @ xtx_inv
    c = np.array([0, 0, 0, 0, 1, -1.0])
    assert abs(est["diff_bp"] - (c @ beta) * 1e4) < 1e-8
    assert abs(est["diff_t"] - (c @ beta) / np.sqrt(c @ cov @ c)) < 1e-9
    assert est["n_post_months"] + est["n_pre_months"] == n // 3


def test_missing_returns_dropped_not_zero() -> None:
    d = pd.Timestamp("2020-01-02")
    panel = pd.DataFrame(
        {
            "date": [d, d, d],
            "symbol": ["A", "B", "C"],
            "mom_decile": [1.0, 1.0, 1.0],
            "weight_dv": [1.0, 3.0, 6.0],
            "ret_cc_adj": [0.10, 0.20, np.nan],  # C delisted: missing
        }
    )
    ew = m.group_daily(panel, 1, "ew")
    dv = m.group_daily(panel, 1, "dv")
    assert abs(ew[d] - 0.15) < 1e-12
    assert abs(dv[d] - (0.1 * 1 + 0.2 * 3) / 4) < 1e-12


def test_trade_stats_costs_and_window() -> None:
    g = np.array([0.01, 0.03, -0.01, 0.02])
    s = m.trade_stats(g, 20.0)
    assert abs(s["gross_mean_bp"] - 125.0) < 1e-9
    assert abs(s["net10_mean_bp"] - 105.0) < 1e-9
    assert abs(s["net20_mean_bp"] - 85.0) < 1e-9
    entry = pd.Series(pd.to_datetime(["2023-09-01", "2023-10-02"]))
    exit_ = pd.Series(pd.to_datetime(["2023-09-12", "2023-10-11"]))
    ok = m.in_window(entry, exit_, "2023-09-18", "2025-12-31")
    assert ok.tolist() == [False, True]
