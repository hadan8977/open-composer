from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "run_h20260930_01_rebalancing", ROOT / "scripts" / "run_h20260930_01_rebalancing.py"
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["run_h20260930_01_rebalancing"] = mod
_spec.loader.exec_module(mod)


def test_weight_drift_matches_formula():
    rs = np.array([0.0, 0.10, 0.0])
    ri = np.array([0.0, 0.0, 0.0])
    dev, sig = mod.simulate_portfolio(rs, ri, delta=0.05, month_end=None)
    expected_w = 0.6 * 1.1 / (0.6 * 1.1 + 0.4)
    assert abs(dev[1] - (expected_w - 0.6)) < 1e-12
    # the paper's example: a 10 percent outperformance moves the weight about 2.3 points
    assert 0.02 < dev[1] < 0.025
    assert sig[1] == 0.0  # |dev| 0.0226 < delta 0.05: no reset, no signal


def test_threshold_resets_only_when_breached():
    rs = np.array([0.0, 0.10, 0.0, 0.0])
    ri = np.zeros(4)
    # delta 1%: breached on day 1 (dev ~2.26%), reset to 0.6, day 2 dev = 0
    dev, sig = mod.simulate_portfolio(rs, ri, delta=0.01, month_end=None)
    assert sig[1] == dev[1] and dev[1] > 0.01
    assert abs(dev[2]) < 1e-12 and sig[2] == 0.0
    # delta 5%: no breach, weight keeps drifting, signal zero
    dev5, sig5 = mod.simulate_portfolio(rs, ri, delta=0.05, month_end=None)
    assert sig5[1] == 0.0
    assert abs(dev5[2] - dev5[1]) < 1e-12  # no returns on day 2 keeps weight
    assert dev5[1] == dev[1]


def test_threshold_signal_is_mean_of_25_deltas():
    assert len(mod.DELTAS) == 25 and mod.DELTAS[0] == 0.001 and mod.DELTAS[-1] == 0.025
    rs = np.array([0.0, 0.10, 0.0])
    ri = np.zeros(3)
    thr = mod.threshold_signal(rs, ri)
    dev1 = 0.6 * 1.1 / (0.6 * 1.1 + 0.4) - 0.6
    n_breached = sum(1 for d in mod.DELTAS if dev1 > d)
    assert n_breached == 22  # deltas 0.1%..2.2% are below 2.26%
    assert abs(thr[1] - dev1 * n_breached / 25) < 1e-12


def test_month_position_and_calendar_mod():
    idx = pd.bdate_range("2024-01-02", "2024-03-29")
    month_end, k = mod.month_position(idx)
    jan = idx[idx.month == 1]
    assert month_end[list(idx).index(jan[-1])]
    assert k[list(idx).index(jan[-1])] == 1
    assert k[list(idx).index(jan[-5])] == 5
    assert k[list(idx).index(jan[0])] == len(jan)
    # equity outperforms bonds every day in January -> overweight -> CalMod -1 on k=2..5,
    # +1 on the last session (inverse of the k=5 modified value)
    rs = np.where(idx.month == 1, 0.004, 0.0)
    ri = np.zeros(len(idx))
    dev_c, cal = mod.calendar_signals(rs, ri, idx)
    pos = {d: i for i, d in enumerate(idx)}
    for d in jan[-5:-1]:
        assert cal[pos[d]] == -1.0
    assert cal[pos[jan[-1]]] == 1.0
    assert cal[pos[jan[0]]] == 0.0
    # calendar portfolio is reset at month end: first February session deviation small
    feb0 = idx[idx.month == 2][0]
    assert abs(dev_c[pos[feb0]]) < 1e-9


def test_incomplete_last_month_has_no_calendar_signal():
    idx = pd.bdate_range("2024-01-02", "2024-02-14")
    _, k = mod.month_position(idx)
    assert (k[idx.month == 2] == 0).all()
    assert (k[idx.month == 1] > 0).all()


def test_hc3_slope_recovers_coefficient_and_sign():
    rng = np.random.default_rng(1)
    x = rng.normal(size=4000)
    y = -0.5 * x + rng.normal(size=4000)
    b, se, t = mod.hc3_slope(x, y)
    assert abs(b + 0.5) < 0.05 and t < -20 and se > 0
    assert np.isnan(mod.hc3_slope(np.zeros(100), np.ones(100))[0])


def test_hc3_matches_matrix_formula():
    rng = np.random.default_rng(2)
    x = rng.normal(size=300)
    y = 0.3 * x + rng.standard_t(4, size=300)
    X = np.column_stack([np.ones(300), x])
    beta = np.linalg.solve(X.T @ X, X.T @ y)
    e = y - X @ beta
    xtx_inv = np.linalg.inv(X.T @ X)
    h = np.einsum("ij,jk,ik->i", X, xtx_inv, X)
    cov = xtx_inv @ (X.T * (e**2 / (1 - h) ** 2)) @ X @ xtx_inv
    b, se, _ = mod.hc3_slope(x, y)
    assert abs(b - beta[1]) < 1e-10 and abs(se - cov[1, 1] ** 0.5) < 1e-10


def test_w_formula_and_next_day_segments():
    idx = pd.bdate_range("2024-01-02", periods=6)
    close = pd.DataFrame({"SPY": [100, 101, 102, 101, 103, 104.0], "IEF": [100.0] * 6}, index=idx)
    sig = mod.build_signals(close)
    thr = sig["THR"].to_numpy()
    cal = sig["CALMOD"].to_numpy()
    assert np.allclose(sig["W"].to_numpy(), 0.6 * (-thr / 0.012) + 0.4 * cal)
    open_ = pd.Series([100, 100.5, 101, 102, 101, 103.0], index=idx)
    seg = mod.next_day_segments(open_, close["SPY"])
    assert abs(seg["ON"].iloc[0] - (100.5 / 100 - 1)) < 1e-12
    assert abs(seg["ID"].iloc[0] - (101 / 100.5 - 1)) < 1e-12
    assert abs(seg["CC"].iloc[0] - 0.01) < 1e-12
    assert np.isnan(seg["CC"].iloc[-1])


def test_gate_logic_mechanical():
    def row(leg, seg, sig, win, coef, t):
        return dict(leg=leg, segment=seg, signal=sig, window=win, coef=coef, hc3_t=t)

    rows = [
        row("SPY", "ID", "THR", "full", -0.02, -3.0),
        row("SPY", "ID", "THR", "anchor", -0.03, -2.1),
        row("SPY", "ON", "THR", "full", -0.01, -1.0),
    ]
    g = {x["id"]: x["passed"] for x in mod.regression_gates(rows)}
    assert g["G1"] and g["G2"] and g["G3"] and not g["G_overnight"]
    rows[1] = row("SPY", "ID", "THR", "anchor", -0.03, -1.9)
    g = {x["id"]: x["passed"] for x in mod.regression_gates(rows)}
    assert g["G2"] and not g["G3"]
    rows[0] = row("SPY", "ID", "THR", "full", 0.02, 3.0)
    rows[1] = row("SPY", "ID", "THR", "anchor", 0.03, 3.0)
    g = {x["id"]: x["passed"] for x in mod.regression_gates(rows)}
    assert not g["G1"] and not g["G2"] and not g["G3"]
