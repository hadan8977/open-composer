"""Synthetic tests for scripts/run_h20261004_pm_midterm_odds_leadlag.py (T-20261004-53)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_h20261004_pm_midterm_odds_leadlag.py"
)
spec = importlib.util.spec_from_file_location("run_h20261004_pm_midterm_odds_leadlag", SCRIPT)
assert spec and spec.loader
rn = importlib.util.module_from_spec(spec)
sys.modules["run_h20261004_pm_midterm_odds_leadlag"] = rn
spec.loader.exec_module(rn)
bd = rn.bd


def test_transform_burn_in_range_and_direction() -> None:
    rng = np.random.default_rng(1)
    dp = pd.Series(np.r_[np.nan, rng.normal(0, 1, 120)])
    sig = rn.transform(dp)
    assert sig.iloc[:60].isna().all() and sig.iloc[60:].notna().all()
    assert sig.dropna().between(-1, 1).all()
    # a very large positive EMA is the top of its window: signal 1.0
    up = pd.Series(np.r_[np.nan, rng.normal(0, 0.1, 100), 50.0])
    assert rn.transform(up).iloc[-1] == 1.0
    down = pd.Series(np.r_[np.nan, rng.normal(0, 0.1, 100), -50.0])
    assert abs(rn.transform(down).iloc[-1] - (2 / 60 - 1)) < 1e-12


def test_delta_p_mean_of_two_markets_and_carry() -> None:
    idx = pd.date_range("2026-01-05", periods=4, freq="B")
    panel = pd.DataFrame(
        {"a": [0.10, 0.12, np.nan, 0.15], "b": [0.50, 0.50, 0.40, 0.40]}, index=idx
    )
    dp = rn.delta_p(panel)
    assert np.isnan(dp.iloc[0])
    assert abs(dp.iloc[1] - 1.0) < 1e-9  # (2 pp + 0 pp) / 2
    assert abs(dp.iloc[2] - (-5.0)) < 1e-9  # a carried (0 pp), b -10 pp
    assert abs(dp.iloc[3] - 1.5) < 1e-9  # (3 pp + 0) / 2


def test_lagged_signal_uses_previous_session() -> None:
    s = pd.Series([0.1, 0.2, 0.3])
    assert np.isnan(rn.lagged_position_signal(s).iloc[0])
    assert rn.lagged_position_signal(s).iloc[2] == 0.2


def test_nw_t_matches_plain_t_on_iid_and_is_lower_on_autocorrelated() -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(0.1, 1.0, 4000)
    plain = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert abs(rn.nw_t(x) - plain) / plain < 0.2
    ar = np.zeros(4000)
    for i in range(1, 4000):
        ar[i] = 0.7 * ar[i - 1] + rng.normal()
    ar += 0.05
    plain_ar = ar.mean() / (ar.std(ddof=0) / np.sqrt(len(ar)))
    assert rn.nw_t(ar) < plain_ar


def test_sharpe_annualization() -> None:
    x = np.array([0.001, 0.003, 0.002] * 20)
    expected = x.mean() / x.std(ddof=1) * np.sqrt(252)
    assert abs(rn.sharpe(x) - expected) < 1e-12
    assert np.isnan(rn.sharpe(np.array([0.01, 0.01, 0.01, 0.01])))


def test_dk_regression_recovers_beta_and_ols_nw_agrees() -> None:
    rng = np.random.default_rng(3)
    t, a = 400, 10
    x = rng.normal(0, 1, t)
    common = rng.normal(0, 1, t)  # cross-sectional dependence
    y = 0.13 * x[:, None] + common[:, None] + rng.normal(0, 0.5, (t, a))
    res = rn.dk_regression(y, x)
    assert abs(res["beta_bp_per_pp"] - 0.13) < 0.2
    assert res["n_obs"] == t * a and res["n_sessions"] == t
    # DK accounts for the common shock: its se exceeds a naive iid pooled se
    naive_se = np.sqrt(np.var(y - 0.13 * x[:, None]) / (t * a) / np.var(x))
    assert res["se"] > naive_se
    basket = rn._ols_nw(y.mean(axis=1), x)
    assert abs(basket["beta"] - res["beta_bp_per_pp"]) < 1e-9


def test_net_series_costs_entry_and_flips() -> None:
    ret = np.zeros((4, 2))
    dirs = np.array([1.0, -1.0])
    costs = np.array([2.0, 10.0])
    sig = np.array([1.0, 1.0, -1.0, -1.0])
    net = rn.net_series(sig, ret, dirs, costs)
    # entry: mean(2, 10) bp; flip from +1 to -1 is a unit change of 2 per asset
    assert abs(net[0] + 6e-4) < 1e-12 and net[1] == 0.0
    assert abs(net[2] + 12e-4) < 1e-12 and net[3] == 0.0
    gross = rn.net_series(sig, np.full((4, 2), 0.01), dirs, costs, gross=True)
    assert np.allclose(gross, [0.0, 0.0, 0.0, 0.0])  # +1% long and -1% short legs cancel


def test_circular_shift_test_deterministic_and_percentile_in_range() -> None:
    rng = np.random.default_rng(4)
    n, a = 200, 5
    sig = rng.uniform(-1, 1, n)
    ret = rng.normal(0, 0.01, (n, a))
    dirs, costs = np.ones(a), np.full(a, 2.0)
    r1 = rn.circular_shift_test(sig, ret, dirs, costs, n_shifts=200)
    r2 = rn.circular_shift_test(sig, ret, dirs, costs, n_shifts=200)
    assert r1 == r2
    assert 0.0 <= r1["percentile_of_real"] <= 100.0
    planted = ret + 0.01 * sig[:, None]
    r3 = rn.circular_shift_test(sig, planted, dirs, costs, n_shifts=200)
    assert r3["above_p95"] and r3["percentile_of_real"] > 95


def _stat(sharpe, t, above):
    return {"net": {"sharpe": sharpe, "nw_t": t}, "circular_shifts": {"above_p95": above}}


def test_verdict_labels() -> None:
    assert rn.verdict(_stat(0.8, 2.5, True))["verdict"] == "continue"
    assert rn.verdict(_stat(0.8, 2.5, False))["verdict"] == "inconclusive"
    assert rn.verdict(_stat(0.4, 3.0, True))["verdict"] == "inconclusive"
    assert rn.verdict(_stat(0.0, -1.0, False))["verdict"] == "stop_refuted"
    assert rn.verdict(_stat(-0.2, 3.0, True))["verdict"] == "stop_refuted"


def _synthetic(planted: float, seed: int = 5):
    sessions = pd.DatetimeIndex(bd.sessions_between(date(2025, 7, 14), date(2026, 10, 2)))
    rng = np.random.default_rng(seed)

    def walk(scale):
        return np.clip(0.4 + np.cumsum(rng.normal(0, scale, len(sessions))), 0.02, 0.98)

    rows = []
    for name, scale in [
        ("polymarket_house_r", 0.01),
        ("polymarket_senate_r", 0.01),
        ("kalshi_house_r", 0.01),
        ("kalshi_senate_r", 0.01),
        ("placebo_market", 0.01),
    ]:
        rows.append(pd.DataFrame({"series": name, "session": sessions, "price": walk(scale)}))
    daily = pd.concat(rows, ignore_index=True)
    sig = rn.build_signals(daily)["polymarket"]
    bars = {}
    dirs = dict(zip(bd.ASSETS, rn.direction_vector(bd.ASSETS), strict=True))
    for tk in bd.ASSETS:
        r = rng.normal(0, 0.004, len(sessions)) + planted * dirs[tk] * sig.fillna(0).to_numpy()
        bars[tk] = pd.Series(100 * np.cumprod(1 + r), index=sessions)
    return daily, bars


def test_run_end_to_end_planted_signal_continues_and_null_does_not() -> None:
    daily, bars = _synthetic(planted=0.004)
    res = rn.run(daily, bars)
    assert res["window"]["sessions"] == 248
    assert res["assets"]["n_kept"] == 27
    assert res["verdict"] == "continue", res["continue_rule"]
    assert res["research_pass"] is True
    assert res["placebos"]["sign_flip"]["gross"]["sharpe"] < 0  # mirrors the planted gross
    assert res["regressions"]["backtest_window"]["next_day_pooled_dk"]["t"] > 2
    daily0, bars0 = _synthetic(planted=0.0, seed=6)
    res0 = rn.run(daily0, bars0)
    assert res0["verdict"] != "continue"
    assert res0["research_pass"] is False and res0["paper_ready_pass"] is False


def test_outputs_are_written(tmp_path) -> None:
    daily, bars = _synthetic(planted=0.0, seed=7)
    res = rn.run(daily, bars)
    rn.write_report(res, tmp_path / "report.md")
    rn.write_decision_record(res, tmp_path / "decision-record.md")
    rn.write_ledger(res, tmp_path / "trial-ledger.jsonl")
    text = (tmp_path / "decision-record.md").read_text()
    for marker in ("Path", "Decision", "Reason", "Next iteration suggestion"):
        assert marker in text
    assert (tmp_path / "report.md").read_text().startswith("# Report")
    assert len((tmp_path / "trial-ledger.jsonl").read_text().splitlines()) == 3
