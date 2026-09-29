"""T-20260929-32 unit tests: the cross-sectional selection, per-leg return
engine, leg combination, sign-flip placebo, split-like trigger filter, and
wide-matrix signal builder used by
``scripts/run_t20260929_32_gap_fade_ls.py``. These are the only new,
untested pure functions the task introduces -- the Abdi-Ranaldo spread and
its cost formula are imported unmodified from
``scripts/run_t20260928_30_smallcap_ml_book.py`` and already tested in
``tests/test_t20260928_30_smallcap_ml_book.py``; ``price_hygiene`` is
already tested in its own test module."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

mod = importlib.import_module("scripts.run_t20260929_32_gap_fade_ls")


def _panel() -> pd.DataFrame:
    """Two trading days, four symbols each: z spread from most negative to
    most positive so top/bottom-2 selection is unambiguous."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    rows = []
    for d in dates:
        for sym, z in (("AAAA", -2.0), ("BBBB", -1.0), ("CCCC", 1.0), ("DDDD", 2.0)):
            rows.append({"date": d, "symbol": sym, "z": z})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# select_side
# --------------------------------------------------------------------------


def test_select_side_bottom_k_is_most_negative_z():
    panel = _panel()
    mask = pd.Series(True, index=panel.index)
    sel = mod.select_side(panel, mask, k=2, most_negative=True)
    for _d, group in sel.groupby("date"):
        assert set(group["symbol"]) == {"AAAA", "BBBB"}


def test_select_side_top_k_is_most_positive_z():
    panel = _panel()
    mask = pd.Series(True, index=panel.index)
    sel = mod.select_side(panel, mask, k=2, most_negative=False)
    for _d, group in sel.groupby("date"):
        assert set(group["symbol"]) == {"CCCC", "DDDD"}


def test_select_side_respects_eligibility_mask():
    panel = _panel()
    # Exclude the two most positive-z names from eligibility; the short
    # selection (top-k by z) must fall back to the next-best eligible names.
    mask = ~panel["symbol"].isin(["CCCC", "DDDD"])
    sel = mod.select_side(panel, mask, k=2, most_negative=False)
    for _d, group in sel.groupby("date"):
        assert set(group["symbol"]) == {"AAAA", "BBBB"}


# --------------------------------------------------------------------------
# leg_return: cost charged twice (entry+exit), borrow only on shorts
# --------------------------------------------------------------------------


def _panel_idx(oc: dict[str, float], cost: float, borrow: float) -> pd.DataFrame:
    d = pd.Timestamp("2024-01-02")
    rows = [
        {
            "date": d,
            "symbol": sym,
            "oc": v,
            "cost_base": cost,
            "borrow_annual": borrow,
        }
        for sym, v in oc.items()
    ]
    return pd.DataFrame(rows)


def test_leg_return_long_side_no_borrow():
    sel = pd.DataFrame({"date": [pd.Timestamp("2024-01-02")] * 2, "symbol": ["AAAA", "BBBB"]})
    panel_idx = _panel_idx({"AAAA": 0.02, "BBBB": 0.04}, cost=0.0005, borrow=0.05)
    ret = mod.leg_return(sel, panel_idx, "cost_base", side=1, apply_borrow=False)
    # mean(oc) - 2*cost, no borrow even though borrow_annual is set on the rows
    expected = np.mean([0.02, 0.04]) - 2 * 0.0005
    assert np.isclose(ret.iloc[0], expected)


def test_leg_return_short_side_flips_sign_and_charges_borrow():
    sel = pd.DataFrame({"date": [pd.Timestamp("2024-01-02")] * 2, "symbol": ["AAAA", "BBBB"]})
    panel_idx = _panel_idx({"AAAA": 0.02, "BBBB": 0.04}, cost=0.0005, borrow=0.05)
    ret = mod.leg_return(sel, panel_idx, "cost_base", side=-1, apply_borrow=True)
    expected = np.mean([-0.02, -0.04]) - 2 * 0.0005 - 0.05 / mod.BORROW_DAYCOUNT
    assert np.isclose(ret.iloc[0], expected)


def test_leg_return_missing_borrow_defaults_to_zero():
    d = pd.Timestamp("2024-01-02")
    panel_idx = pd.DataFrame(
        [{"date": d, "symbol": "AAAA", "oc": 0.01, "cost_base": 0.0, "borrow_annual": np.nan}]
    )
    sel = pd.DataFrame({"date": [d], "symbol": ["AAAA"]})
    ret = mod.leg_return(sel, panel_idx, "cost_base", side=-1, apply_borrow=True)
    assert np.isclose(ret.iloc[0], -0.01)


# --------------------------------------------------------------------------
# combine_legs: dollar-neutral average, inner-joined on date
# --------------------------------------------------------------------------


def test_combine_legs_averages_on_shared_dates_only():
    idx_a = pd.to_datetime(["2024-01-02", "2024-01-03"])
    idx_b = pd.to_datetime(["2024-01-02", "2024-01-04"])
    a = pd.Series([0.02, 0.03], index=idx_a)
    b = pd.Series([-0.01, 0.05], index=idx_b)
    out = mod.combine_legs(a, b)
    assert list(out.index) == [pd.Timestamp("2024-01-02")]
    assert np.isclose(out.iloc[0], (0.02 + -0.01) / 2.0)


# --------------------------------------------------------------------------
# placebo_sign_flip: deterministic per seed, only flips the sign, same
# eligibility-relevant columns untouched
# --------------------------------------------------------------------------


def test_placebo_sign_flip_only_changes_z_magnitude_sign_and_is_deterministic():
    panel = _panel()
    flipped_a = mod.placebo_sign_flip(panel, seed=0)
    flipped_b = mod.placebo_sign_flip(panel, seed=0)
    pd.testing.assert_frame_equal(flipped_a, flipped_b)
    # same day must carry the same sign for both symbols (day-level flip)
    for _d, group in flipped_a.groupby("date"):
        signs = np.sign(group["z"].to_numpy()) / np.sign(panel.loc[group.index, "z"].to_numpy())
        assert len(set(signs)) == 1
    # magnitudes preserved
    assert np.allclose(flipped_a["z"].abs().to_numpy(), panel["z"].abs().to_numpy())


def test_placebo_sign_flip_different_seeds_can_differ():
    panel = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-02", periods=10, freq="D"),
            "symbol": ["AAAA"] * 10,
            "z": [1.0] * 10,
        }
    )
    seeds_signs = [
        tuple(np.sign(mod.placebo_sign_flip(panel, seed=s)["z"]).tolist()) for s in range(5)
    ]
    assert len(set(seeds_signs)) > 1


# --------------------------------------------------------------------------
# is_split_like_ratio: catches 2x/3x/etc trigger-day gap ratios that
# price_hygiene's 10x jump threshold does not
# --------------------------------------------------------------------------


def test_is_split_like_ratio_flags_common_split_multiples():
    ratios = np.array([2.0, 0.5, 3.0, 1.0 / 3.0, 1.02, 1.5, 1.2])
    flags = mod.is_split_like_ratio(ratios)
    # 2.0, 0.5, 3.0, 1/3, 1.5 (3:2 split) are split-like candidates;
    # 1.02 (a normal day) and 1.2 (not in the candidate list) are not.
    assert list(flags) == [True, True, True, True, False, True, False]


def test_is_split_like_ratio_respects_tolerance():
    ratios = np.array([2.0, 2.0 * np.exp(0.02), 2.0 * np.exp(0.10)])
    flags = mod.is_split_like_ratio(ratios, tol=0.03)
    # exact match and within-tolerance match both True, well-outside False.
    assert list(flags) == [True, True, False]


def test_is_split_like_ratio_handles_nan_and_nonpositive():
    ratios = np.array([np.nan, 0.0, -2.0, 2.0])
    flags = mod.is_split_like_ratio(ratios)
    assert list(flags) == [False, False, False, True]


# --------------------------------------------------------------------------
# build_signal_panel: wide -> long, history/liquidity eligibility, and the
# split-like filter actually removes the trigger row (not neighbouring rows)
# --------------------------------------------------------------------------


def _wide_matrices(
    n_days: int = 70, price0: float = 20.0
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """One symbol, ``n_days`` sessions of flat $20 price and steady $1M/day
    dollar volume -- enough history (>=60) and liquidity (dv21 >= $1M) for
    every day from day 61 onward to be eligible once sigma21 is nonzero, so
    a tiny amount of daily noise is added to avoid a zero-variance sigma21."""
    idx = pd.date_range("2024-01-02", periods=n_days, freq="B")
    rng = np.random.default_rng(0)
    noise = 1.0 + rng.normal(0.0, 0.01, size=n_days)
    close = pd.Series(price0 * np.cumprod(noise), index=idx)
    open_ = close.shift(1).fillna(close.iloc[0]) * (1.0 + rng.normal(0.0, 0.002, size=n_days))
    volume = pd.Series(50_000.0, index=idx)  # $1M/day at price ~20
    close_w = pd.DataFrame({"AAAA": close})
    open_w = pd.DataFrame({"AAAA": open_})
    volume_w = pd.DataFrame({"AAAA": volume})
    return close_w, open_w, volume_w


def test_build_signal_panel_requires_60_days_history():
    close_w, open_w, volume_w = _wide_matrices(n_days=70)
    panel = mod.build_signal_panel(close_w, open_w, volume_w, filter_split_like=False)
    # history counts prior sessions strictly before today, so the earliest
    # possible eligible row is at position 60 (0-indexed) -- well before
    # that, nothing should appear.
    first_eligible = panel["date"].min()
    assert first_eligible >= close_w.index[60]


def test_build_signal_panel_split_filter_drops_only_the_trigger_row():
    close_w, open_w, volume_w = _wide_matrices(n_days=70)
    # Engineer a clean 2x gap on one specific day (comfortably after the
    # 60-day warmup) without touching any other day.
    trigger_pos = 65
    open_w = open_w.copy()
    open_w.iloc[trigger_pos, 0] = close_w.iloc[trigger_pos - 1, 0] * 2.0

    panel_unfiltered = mod.build_signal_panel(close_w, open_w, volume_w, filter_split_like=False)
    panel_filtered = mod.build_signal_panel(close_w, open_w, volume_w, filter_split_like=True)

    trigger_date = close_w.index[trigger_pos]
    assert (panel_unfiltered["date"] == trigger_date).any()
    assert not (panel_filtered["date"] == trigger_date).any()
    # every other eligible date is unaffected
    other_unfiltered = set(panel_unfiltered.loc[panel_unfiltered["date"] != trigger_date, "date"])
    other_filtered = set(panel_filtered["date"])
    assert other_unfiltered == other_filtered
