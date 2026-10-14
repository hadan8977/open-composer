"""Unit tests for the group C opening-range-breakout simulator (T-20261006-15)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import t15_c_orb as C  # noqa: E402


def _path(n_bars=78, price=100.0):
    o = np.full((1, n_bars), price)
    return o.copy(), o.copy(), o.copy(), o.copy(), np.ones((1, n_bars), bool)


def test_long_stop_fills_at_stop_price_and_bar_close():
    op, hi, lo, cl, v = _path()
    # entry bar 1 at 100; bar 5 trades down through 99 (stop) and closes at 98.5
    lo[0, 5] = 98.0
    cl[0, 5] = 98.5
    op[0, 5] = 99.5
    e = np.array([1])
    stop = np.array([99.0])
    g, hit = C.sim(op, hi, lo, cl, v, e, np.array([1.0]), stop, "stop_price", np.array([101.0]))
    assert hit[0] and abs(g[0] - (99.0 / 100.0 - 1.0)) < 1e-12
    g2, _ = C.sim(
        op, hi, lo, cl, v, e, np.array([1.0]), stop, "trigger_bar_close", np.array([101.0])
    )
    assert abs(g2[0] - (98.5 / 100.0 - 1.0)) < 1e-12


def test_gap_through_stop_fills_at_open_and_short_mirrors():
    op, hi, lo, cl, v = _path()
    op[0, 7], lo[0, 7], hi[0, 7] = 97.0, 96.5, 97.5  # gap below a long stop of 99
    e = np.array([1])
    g, hit = C.sim(
        op, hi, lo, cl, v, e, np.array([1.0]), np.array([99.0]), "stop_price", np.array([97.0])
    )
    assert hit[0] and abs(g[0] - (97.0 / 100.0 - 1.0)) < 1e-12
    # short with stop 101, bar gaps up to 103
    op, hi, lo, cl, v = _path()
    op[0, 9], hi[0, 9], lo[0, 9] = 103.0, 103.5, 102.5
    g, hit = C.sim(
        op, hi, lo, cl, v, e, np.array([-1.0]), np.array([101.0]), "stop_price", np.array([103.0])
    )
    assert hit[0] and abs(g[0] - (-(103.0 / 100.0 - 1.0))) < 1e-12


def test_no_hit_exits_at_eod_and_filled_bars_never_trigger():
    op, hi, lo, cl, v = _path()
    lo[0, 20] = 50.0
    v[0, 20] = False  # a filled bar must not trigger a stop
    g, hit = C.sim(
        op,
        hi,
        lo,
        cl,
        v,
        np.array([1]),
        np.array([1.0]),
        np.array([99.0]),
        "stop_price",
        np.array([102.0]),
    )
    assert not hit[0] and abs(g[0] - 0.02) < 1e-12


def test_stop_levels():
    d = np.array([1.0, -1.0])
    entry = np.array([100.0, 100.0])
    atr = np.array([2.0, 2.0])
    hi, lo = np.array([101.0, 101.0]), np.array([99.0, 99.0])
    assert np.allclose(C.stop_level("opposite", d, entry, atr, hi, lo), [99.0, 101.0])
    assert np.allclose(C.stop_level("atr10", d, entry, atr, hi, lo), [99.8, 100.2])
    assert np.allclose(C.stop_level("atr5", d, entry, atr, hi, lo), [99.9, 100.1])


def test_split_events_flag_ratio_but_not_ordinary_gap():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    c = pd.DataFrame({"A": [100.0, 51.0, 51.0], "B": [100.0, 100.0, 100.0]}, index=idx)
    o = pd.DataFrame({"A": [100.0, 50.5, 51.0], "B": [100.0, 112.0, 100.0]}, index=idx)
    ev = C.split_events(o, c)
    assert bool(ev.loc[idx[1], "A"]) and not bool(ev["B"].any())


def test_canonical_daily_rejects_conflicting_keys_and_counts_partition_leaks():
    idx = pd.to_datetime(["2024-01-02", "2024-01-02", "2024-02-01"])
    frame = pd.DataFrame({"d": idx, "symbol": ["A", "A", "A"], "c": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="Conflicting"):
        C.canonical_daily(frame, "2024-01")
    exact = frame.iloc[[0, 0]].copy()
    clean, outside = C.canonical_daily(exact, "2024-01")
    assert len(clean) == 1 and outside == 0


def test_causal_features_do_not_rewrite_history_after_future_break():
    idx = pd.date_range("2024-01-02", periods=35, freq="B")
    cols = ["A"]
    base = {k: pd.DataFrame(100.0, index=idx, columns=cols) for k in ("o", "h", "l", "c")}
    base["h"] += 1.0
    base["l"] -= 1.0
    for k in ("vol", "rv5", "rv15", "rv30"):
        base[k] = pd.DataFrame(2_000_000.0, index=idx, columns=cols)
    changed = {k: v.copy() for k, v in base.items()}
    changed["c"].iloc[-1, 0] = 1_000.0
    f0, _, _ = C.causal_features(base)
    f1, _, _ = C.causal_features(changed)
    for k in ("pc", "atr", "avgvol", "adv21", "vol21", "rel5"):
        assert np.allclose(f0[k].iloc[:-1].to_numpy(), f1[k].iloc[:-1].to_numpy(), equal_nan=True)
