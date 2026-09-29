from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260929_51_small_cap_short_drift as mod  # noqa: E402
import screen_lane as lane  # noqa: E402


def synthetic_panel(n: int = 400, seed: int = 3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-02", periods=n)
    spy_r = rng.normal(0.0004, 0.01, n)
    iwm_r = 1.5 * spy_r + rng.normal(0.0, 0.004, n)
    shy_r = np.full(n, 0.0001)
    close = pd.DataFrame(
        {
            "SPY": 100 * np.cumprod(1 + spy_r),
            "IWM": 50 * np.cumprod(1 + iwm_r),
            "SHY": 80 * np.cumprod(1 + shy_r),
        },
        index=idx,
    )
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, (n, 3)))
    return close, open_


def test_lane_weights_frame_cannot_hold_shorts() -> None:
    """Documents why a separate runner exists: the batch lane discards every
    non-positive weight, so a hedged short would silently become a long SPY book."""
    close, _ = synthetic_panel()
    cand = lane.ScreenCandidate(
        id="X",
        name="x",
        source_card="n/a",
        universe=("IWM", "SPY"),
        freq="M",
        weights_fn=lambda c, d: {"IWM": -1.0, "SPY": 1.0},
    )
    frame, _ = lane.weights_frame(close, cand, 0)
    assert (frame["IWM"] == 0.0).all()
    assert frame["SPY"].iloc[-1] == 1.0  # the long leg survives alone, the short leg is gone


def test_signed_weights_simulate_to_minus_iwm_plus_spy_less_costs() -> None:
    close, open_ = synthetic_panel()
    leg_open, leg_close = mod.salvage.legs(close, open_)
    idx = close.index
    w = pd.DataFrame(0.0, index=idx, columns=["IWM", "SHY", "SPY"])
    w.loc[idx[1:], "IWM"] = -1.0
    w.loc[idx[1:], "SPY"] = 1.0
    gross, after, turn = mod.simulate_overlay(w, leg_open, leg_close, 10.0, 0.005)
    expected_gross = (
        -(leg_open["IWM"] + leg_close["IWM"]) + (leg_open["SPY"] + leg_close["SPY"])
    ).copy()
    # day 1: opening trade turns over |-1| + |1| = 2 -> 2 * 10bp; open leg has no prior position
    expected_gross.iloc[0] = 0.0
    expected_gross.iloc[1] = -leg_close["IWM"].iloc[1] + leg_close["SPY"].iloc[1] - 2 * 10 / 1e4
    pd.testing.assert_series_equal(gross, expected_gross, check_names=False, atol=1e-12)
    assert turn.iloc[1] == pytest.approx(2.0)
    assert turn.iloc[2:].sum() == 0.0
    fee = after.iloc[5] - gross.iloc[5]
    assert fee == pytest.approx(-1.0 * 0.005 / 252.0)  # only the short leg pays borrow
    assert after.iloc[0] == gross.iloc[0]  # nothing held yet, nothing borrowed


def test_trailing_beta_recovers_known_beta() -> None:
    close, _ = synthetic_panel()
    beta = mod.trailing_beta(close, "IWM", close.index[-1], 252)
    assert beta == pytest.approx(1.5, abs=0.15)
    assert np.isnan(mod.trailing_beta(close, "IWM", close.index[100], 252))


def test_weights_have_next_open_timing_and_mirror_is_negated() -> None:
    close, _ = synthetic_panel()
    short = mod.SpreadCandidate("A", "IWM", "M", 63)
    mirror = mod.SpreadCandidate("B", "IWM", "M", 63, mirror=True)
    w_s, dates = mod.weights_frame(close, short, 0)
    w_m, _ = mod.weights_frame(close, mirror, 0)
    first = next(d for d in dates if np.isfinite(mod.trailing_beta(close, "IWM", d, 63)))
    i = close.index.get_loc(first)
    assert (w_s.iloc[: i + 1].abs().sum(axis=1) == 0).all()  # nothing on the signal close
    assert w_s["IWM"].iloc[i + 1] == -1.0 and w_s["SPY"].iloc[i + 1] > 0
    np.testing.assert_allclose(w_m.to_numpy(), -w_s.to_numpy())


def test_unhedged_short_and_borrow_cost() -> None:
    close, _ = synthetic_panel()
    cand = mod.SpreadCandidate("N", "IWM", "M", None)
    w, _ = mod.weights_frame(close, cand, 0)
    assert (w["SPY"] == 0).all() and w["IWM"].min() == -1.0
    cost = mod.borrow_cost(w, 0.15)
    assert cost.max() == pytest.approx(0.15 / 252.0)
