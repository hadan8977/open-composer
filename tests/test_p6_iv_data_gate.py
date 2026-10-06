"""Synthetic-data tests for scripts/p6_iv_data_gate.py (no network, no market data)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p6_iv_data_gate.py"
spec = importlib.util.spec_from_file_location("p6_iv_data_gate", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules["p6_iv_data_gate"] = gate
spec.loader.exec_module(gate)


def make_returns(n_days: int = 90, n_sym: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-10-01", periods=n_days)
    sigma = 0.02  # equal true vol: only estimation noise separates the two timing hypotheses
    ret = pd.DataFrame(rng.standard_normal((n_days, n_sym)) * sigma, index=idx)
    ret.columns = [f"S{i}" for i in range(n_sym)]
    return ret


def test_f2_identifies_same_day_published_hv() -> None:
    ret = make_returns()
    hv = ret.rolling(20, min_periods=20).std()  # row d reflects the close of d
    out = gate.f2_timing(hv, ret, hv.index[40:])
    assert out["as_of_rule"] == "same_day"
    assert out["best_median_same"] > 0.99
    assert out["best_w_same"] == 20
    assert out["best_median_prev"] < out["best_median_same"]


def test_f2_identifies_previous_session_hv() -> None:
    ret = make_returns()
    hv = ret.rolling(21, min_periods=21).std().shift(1)  # row d reflects the close of d-1
    out = gate.f2_timing(hv, ret, hv.index[40:])
    assert out["as_of_rule"] == "previous_session"
    assert out["best_w_prev"] == 21
    assert out["prev_minus_same"] >= 0.01
    assert out["best_median_prev"] > 0.99


def test_f2_needs_enough_symbols() -> None:
    ret = make_returns(n_sym=50)
    hv = ret.rolling(20, min_periods=20).std()
    out = gate.f2_timing(hv, ret, hv.index[40:])
    assert all(r["n_dates"] == 0 for r in out["table"])


def test_stale_share_counts_repeats_only_when_both_days_present() -> None:
    wide = pd.DataFrame(
        {"A": [1.0, 1.0, 2.0, 2.0], "B": [5.0, 6.0, np.nan, 6.0]},
        index=pd.bdate_range("2025-01-06", periods=4),
    )
    share, n = gate.stale_share(wide)
    assert n == 4  # A: 3 pairs, B: 1 pair (the NaN breaks two)
    assert abs(share - 2 / 4) < 1e-12  # A repeats twice; B 5->6 is not a repeat


def test_lag1_autocorr_separates_persistent_from_noise() -> None:
    rng = np.random.default_rng(1)
    n = 300
    ar = np.zeros(n)
    for i in range(1, n):
        ar[i] = 0.97 * ar[i - 1] + 0.1 * rng.standard_normal()
    wide = pd.DataFrame({"AR": ar, "WN": rng.standard_normal(n)})
    wide["SHORT"] = np.where(np.arange(n) < 20, rng.standard_normal(n), np.nan)
    med, n_sym = gate.lag1_autocorr_median(wide, min_pairs=100)
    assert n_sym == 2  # SHORT has too few pairs
    assert -0.2 < med < 0.9  # median of {~0.9+, ~0}
    only_ar, _ = gate.lag1_autocorr_median(wide[["AR"]], min_pairs=100)
    assert only_ar > 0.85


def test_coverage_counts_window_and_late_share() -> None:
    sessions = pd.bdate_range("2024-01-02", "2026-09-17")
    have = sessions[sessions >= pd.Timestamp("2024-10-01")]
    have = have.delete(range(0, len(have), 10))  # drop every tenth
    out = gate.coverage_stats(have, sessions)
    late = sessions[(sessions >= gate.LATE_START) & (sessions <= gate.WIN_END)]
    expected = len([d for d in have if gate.LATE_START <= d <= gate.WIN_END])
    assert out["late_sessions"] == len(late)
    assert out["late_days_with_data"] == expected
    assert abs(out["late_coverage"] - expected / len(late)) < 1e-12
    assert out["window_days_with_data"] == expected


def test_join_rate_and_never_matched() -> None:
    d1, d2 = pd.Timestamp("2025-03-03"), pd.Timestamp("2025-03-04")
    l12 = pd.DataFrame(
        {
            "date": [d1, d1, d1, d2, d2, d2],
            "symbol": ["A", "B", "C", "A", "B", "C"],
            "dollar_adv_21": [3.0, 2.0, 1.0, 3.0, 2.0, 1.0],
        }
    )
    vh = pd.DataFrame({"date": [d1, d2, d2], "symbol": ["A", "A", "B"]})
    rate = gate.join_rate_by_date(l12, vh)
    assert rate[d1] == 1 / 3 and rate[d2] == 2 / 3
    missing = gate.never_matched_top(l12, vh)
    assert [m["symbol"] for m in missing] == ["C"]


def test_holiday_rows_identical_share() -> None:
    sessions = pd.DatetimeIndex(["2025-12-23", "2025-12-24", "2025-12-26"])
    rows = []
    for day, scale in (("2025-12-24", 1.0), ("2025-12-25", 1.0), ("2025-12-26", 2.0)):
        for sym, base in (("A", 0.2), ("B", 0.3)):
            row = {"date": pd.Timestamp(day), "symbol": sym}
            row.update({c: base * scale for c in gate.VALUE_COLS})
            rows.append(row)
    vh = pd.DataFrame(rows)
    out = gate.holiday_identical_share(vh, sessions)
    assert out["holiday_dates_with_rows"] == 1
    assert out["rows_compared"] == 2 and out["identical_share"] == 1.0


def calendar(days: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(days, end)


def test_publication_delay_same_day_vs_previous_session() -> None:
    sessions = calendar("2026-09-01", "2026-09-17")
    cal = calendar("2026-09-01", "2026-10-30")
    # data date Wed 09-09 committed Thu 09-10 06:35 UTC
    commit = datetime(2026, 9, 10, 6, 35, tzinfo=UTC)
    commits = [(pd.Timestamp("2026-09-09"), commit)]
    # same_day: t = 09-09, deadline = 09-10 15:50 ET -> on time
    assert gate.publication_delays(commits, sessions, cal, "same_day") == [0]
    # previous_session: t = 09-08, deadline = 09-09 15:50 ET -> one session late
    assert gate.publication_delays(commits, sessions, cal, "previous_session") == [1]


def test_publication_shift_uses_p95_with_floor_of_one() -> None:
    assert gate.publication_shift([0] * 96 + [1] * 4) == (0, 0.96)
    shift, on_time = gate.publication_shift([0] * 90 + [1] * 5 + [3] * 5)
    assert shift == 3 and abs(on_time - 0.9) < 1e-12
    shift, _ = gate.publication_shift([1] * 10)
    assert shift == 1


def test_parse_dolt_log_keeps_only_volatility_history_updates() -> None:
    rows = [
        {"date": "2026-10-03 06:34:55.023", "message": "volatility_history 2026-10-02 update"},
        {"date": "2026-10-03 06:34:48.563", "message": "option_chain 2026-10-02 update"},
        {"date": "2026-10-02 06:34:59.796", "message": "volatility_history 2026-10-01 update"},
    ]
    out = gate.parse_dolt_log(rows)
    assert [d for d, _ in out] == [pd.Timestamp("2026-10-02"), pd.Timestamp("2026-10-01")]
    assert out[0][1] == datetime(2026, 10, 3, 6, 34, 55, 23000, tzinfo=UTC)
