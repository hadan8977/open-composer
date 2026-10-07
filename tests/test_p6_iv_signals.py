"""Synthetic tests for scripts/p6_iv_signals.py (T-20261005-45).  No market data is read."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "p6_iv_signals_mod", ROOT / "scripts/p6_iv_signals.py"
)
m = importlib.util.module_from_spec(spec)
sys.modules["p6_iv_signals_mod"] = m
spec.loader.exec_module(m)


def test_bh_q_known_vector():
    q = m.bh_q([0.01, 0.04, 0.03, 0.005])
    assert np.allclose(q, [0.02, 0.04, 0.04, 0.02])
    assert np.allclose(m.bh_q([0.9, 0.9]), [0.9, 0.9])


def test_rv21_alternating_returns():
    s = 0.01
    rets = np.array([s * (-1) ** k for k in range(21)])
    C = 100.0 * np.exp(np.concatenate([[0.0], np.cumsum(rets)]))[:, None]
    out = m.rv21(C, np.array([21]), np.array([0]))
    assert out[0] == pytest.approx(math.sqrt(252.0) * np.std(rets, ddof=1))


def test_rv21_constant_volatility_and_min_obs():
    # constant daily log return: zero sample std
    C = (100.0 * np.exp(0.002 * np.arange(30)))[:, None]
    assert m.rv21(C, np.array([25]), np.array([0]))[0] == pytest.approx(0.0, abs=1e-12)
    C2 = C.copy()
    C2[8:20, 0] = np.nan  # fewer than 18 finite returns among the last 21
    assert np.isnan(m.rv21(C2, np.array([25]), np.array([0]))[0])


def test_signal_block_formulas():
    rng = np.random.default_rng(0)
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (60, 1)), axis=0))
    d, s = np.array([40]), np.array([0])
    sig = m.signal_block(C, d, s, [0.4], [0.3], [0.2], [0.25])
    rv = m.rv21(C, d, s)[0]
    r3 = math.log(C[40, 0] / C[37, 0])
    assert sig["IVRV"][0] == pytest.approx(0.4 - rv)
    assert sig["DIV21"][0] == pytest.approx(0.2)
    assert sig["DIV5"][0] == pytest.approx(0.1)
    assert sig["IVZ3"][0] == pytest.approx(r3 / (0.4 * math.sqrt(3 / 252)))
    assert sig["HVZ3"][0] == pytest.approx(r3 / (rv * math.sqrt(3 / 252)))
    assert sig["IVRV_V"][0] == pytest.approx(0.15)


def _planted(T=120, n=400, rho=0.1, seed=3):
    """Signal and 24 target columns where the target of lag 2 carries correlation ~rho."""
    rng = np.random.default_rng(seed)
    di = np.repeat(np.arange(T), n)
    sig = rng.normal(size=T * n)
    E = rng.normal(size=(T * n, m.NTGT))
    E[:, 1] = rho * sig + math.sqrt(1 - rho**2) * rng.normal(size=T * n)
    return di, sig, E.astype("float32")


def test_planted_ic_recovered():
    di, sig, E = _planted(rho=0.1)
    T = int(di.max()) + 1
    dmask = np.ones(T, bool)
    ic, npair = m.ic_dates(di, np.column_stack([sig, -sig]), E, T, dmask)
    assert np.nanmean(ic[:, 0, 1]) == pytest.approx(0.1, abs=0.01)
    assert np.nanmean(ic[:, 1, 1]) == pytest.approx(-0.1, abs=0.01)
    assert abs(np.nanmean(ic[:, 0, 2])) < 0.01
    assert npair[5, 0, 1] == 400
    st = m.decision_stats(ic[:, 0, :], 2, 2, 10, dmask)
    assert st["cic"] == pytest.approx(0.1, abs=0.01)
    assert st["t"] > 10
    assert st["mde"] == pytest.approx(2.8 * st["se"])


def test_min_names_rule():
    di, sig, E = _planted(T=10, n=150)
    ic, _ = m.ic_dates(di, sig[:, None], E, 10, np.ones(10, bool))
    assert np.isnan(ic).all()


def test_residual_scores_remove_m0_exposure():
    rng = np.random.default_rng(1)
    T, n = 20, 300
    di = np.repeat(np.arange(T), n)
    m0 = rng.normal(size=T * n)
    th = rng.normal(size=(T * n, 9))
    sig = 0.8 * m0 + 0.2 * rng.normal(size=T * n)
    res = m.residual_scores(di, sig[:, None], m0, th, np.ones(T, bool))
    z0, _ = m.rank_normal(m0[:n, None])
    assert abs(np.corrcoef(z0[:, 0], res[:n, 0])[0, 1]) < 0.05


def test_measure_requires_signs(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CACHE", tmp_path)
    with pytest.raises(SystemExit):
        m.stage_measure()
    with pytest.raises(SystemExit):
        m.load_signs()


def test_earnings_flag_window_and_censoring():
    T = 50
    key = np.array([3 * T + 10])  # symbol 3 has a filing in session 10
    di = np.array([9, 10, 0, 40])
    si = np.array([3, 3, 3, 3])
    flag = m.earnings_flag(key, di, si, T, lastk=T - 1)
    assert list(flag) == [1, 0, 1, -1]
    assert m.earnings_flag(key, np.array([0]), np.array([4]), T, T - 1)[0] == 0
