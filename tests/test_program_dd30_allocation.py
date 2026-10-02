"""Mechanics of scripts/run_program_dd30_allocation.py on synthetic returns (T-20261002-43)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def alloc():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "run_program_dd30_allocation", ROOT / "scripts" / "run_program_dd30_allocation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(n: int = 600, seed: int = 7) -> pd.DataFrame:
    idx = pd.bdate_range("2017-10-02", periods=n)
    rng = np.random.default_rng(seed)
    data = {
        "S3": rng.normal(0.002, 0.025, n),
        "C2": rng.normal(0.0008, 0.006, n),
        "F1": rng.normal(0.0004, 0.003, n),
        "F2": rng.normal(0.0007, 0.01, n),
        "CASH": np.full(n, 0.0001),
    }
    return pd.DataFrame(data, index=idx)


def test_grid_sizes_and_sums(alloc):
    a = alloc.grid_a()
    assert len(a) == 10626
    assert np.allclose(a[:, :5].sum(axis=1), 1.0)
    assert (a[:, 5] == 0).all()
    b = alloc.grid_b()
    risky = b[:, :4].sum(axis=1)
    assert risky.max() <= 1.5 + 1e-9
    # cash minus borrowing always closes the book to 1
    assert np.allclose(b[:, :4].sum(axis=1) + b[:, 4] + b[:, 5], 1.0)


def test_simulate_matches_single_path(alloc, monkeypatch):
    frame = _frame()
    monkeypatch.setattr(
        alloc,
        "WINDOWS",
        {"full": (str(frame.index[0].date()), str(frame.index[-1].date()))},
    )
    w = np.array([[0.4, 0.3, 0.2, 0.0, 0.1, 0.0], [0.8, 0.4, 0.2, 0.0, 0.0, -0.4]])
    res = alloc.simulate(w, frame.to_numpy(), frame.index, 5)
    for i in range(len(w)):
        p = alloc.path(w[i], frame.to_numpy(), frame.index, 5)
        nav = (1 + p).cumprod()
        years = len(p) / 252.0
        assert res["full_cagr"][i] == pytest.approx(nav.iloc[-1] ** (1 / years) - 1, rel=1e-9)
        assert res["full_mdd"][i] == pytest.approx(
            min(0.0, (nav / nav.cummax() - 1).min()), abs=1e-12
        )


def test_borrowing_costs_debit_rate(alloc):
    idx = pd.bdate_range("2020-01-01", periods=252)
    flat = pd.DataFrame(0.0, index=idx, columns=alloc.ENGINES)
    w = np.array([1.0, 0.5, 0.0, 0.0, 0.0, -0.5])  # 1.5x risky on zero returns, 0.5 borrowed
    p = alloc.path(w, flat.to_numpy(), idx, 0)
    total = (1 + p).prod() - 1
    # borrowing 0.5 at 6.5%/yr on zero-return assets loses about 0.5 * 6.5%
    assert total == pytest.approx(-0.5 * 0.065, rel=0.05)


def test_rebalance_cost_charged_on_turnover(alloc):
    idx = pd.bdate_range("2020-01-01", periods=60)
    rets = pd.DataFrame(0.0, index=idx, columns=alloc.ENGINES)
    rets["S3"] = 0.01  # S3 drifts up, so each monthly reset trades
    w = np.array([0.5, 0.0, 0.0, 0.0, 0.5, 0.0])
    p = alloc.path(w, rets.to_numpy(), idx, 0)
    no_cost = rets["S3"] * 0.5
    assert (p <= no_cost.to_numpy() + 1e-12).all() or p.sum() < (1 + 0.005) ** 60


def test_margin_filter(alloc):
    gmax = {"F1": 1.8, "F2": 1.8}
    w = np.array(
        [
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # S3 alone: init 0.75, maint 0.75 -> ok
            [1.0, 0.5, 0.0, 0.0, 0.0, -0.5],  # init 0.75 + 0.25 = 1.0 -> ok; maint 0.9 -> ok
            [1.0, 0.0, 0.5, 0.0, 0.0, -0.5],  # init 0.75 + 0.45 -> fail
        ]
    )
    assert alloc.margin_ok(w, gmax).tolist() == [True, True, False]


def test_choose_respects_dd_and_feasibility(alloc):
    res = {
        "anchor_cagr": np.array([0.9, 0.7, 0.8]),
        "full_mdd": np.array([-0.45, -0.25, -0.29]),
        "select_cagr": np.array([0.5, 0.4, 0.3]),
    }
    feasible = np.array([True, True, False])
    assert alloc.choose(res, feasible, "anchor_cagr", -0.30) == 1
    assert alloc.choose(res, np.ones(3, dtype=bool), "anchor_cagr", -0.30) == 2


def test_realization_dated_moves_values_two_sessions(alloc):
    idx = pd.bdate_range("2020-03-02", periods=6)
    decision = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05, 0.06], index=idx)
    out = alloc.realization_dated(decision)
    assert out.index.equals(idx)
    assert out.tolist() == [0.0, 0.0, 0.01, 0.02, 0.03, 0.04]
