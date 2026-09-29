"""Tests for scripts/screen_batches/h20260928_44_etf_pair_switch.py: the PAIR
weight function must read only `close.loc[:asof]` (no look-ahead), must apply
the absolute-momentum-vs-SHY filter (both legs weak -> empty dict), must pick
the stronger leg when it clears the filter, and the STATIC5050 control must
always return a fixed 0.5/0.5 book. Candidate ids must match the preregistered
manifest exactly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_44_etf_pair_switch as mod  # noqa: E402


def _make_panel(n_days: int = 400, seed: int = 11) -> pd.DataFrame:
    """Synthetic daily close panel: every ticker used across PAIRS plus SHY,
    each a smooth deterministic random walk so lookback returns are
    well-defined and reproducible, with distinct drift per symbol so ranks
    are unambiguous."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    tickers = sorted({t for pair in mod.PAIRS.values() for t in pair} | {mod.CASH})
    data = {}
    for i, col in enumerate(tickers):
        drift = 0.0002 + 0.00002 * i
        noise = rng.normal(0.0, 0.003, size=n_days)
        rets = drift + noise
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=idx)


def test_spec_count_and_ids() -> None:
    assert len(mod.SPECS) == 18
    ids = {spec["id"] for spec in mod.SPECS}
    assert len(ids) == 18
    for pair_name in mod.PAIRS:
        for lb in mod.LOOKBACKS:
            assert f"PAIR_{pair_name}_L{lb}_MO" in ids
        assert f"STATIC5050_{pair_name}_MO" in ids


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260928_44_etf_pair_switch"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(spec["id"] for spec in mod.SPECS)
    assert module_ids == manifest_ids
    assert len(module_ids) == 18


@pytest.mark.parametrize("lookback", [63, 126])
def test_pair_switch_no_lookahead(lookback: int) -> None:
    """Corrupting every row strictly after `asof` with extreme values must
    not change the weights computed at `asof`."""
    close = _make_panel()
    leg_a, leg_b = mod.PAIRS["QQQSPY"]
    fn = mod.make_pair_switch_fn(leg_a, leg_b, lookback)
    asof = close.index[300]

    w_before = fn(close, asof)

    corrupted = close.copy()
    future_mask = corrupted.index > asof
    corrupted.loc[future_mask, :] = 1e9
    w_after = fn(corrupted, asof)

    assert w_before == w_after
    assert w_before != {}


def test_static5050_no_lookahead() -> None:
    close = _make_panel()
    leg_a, leg_b = mod.PAIRS["SMHQQQ"]
    fn = mod.make_static5050_fn(leg_a, leg_b)
    asof = close.index[300]

    w_before = fn(close, asof)

    corrupted = close.copy()
    future_mask = corrupted.index > asof
    corrupted.loc[future_mask, :] = 1e9
    w_after = fn(corrupted, asof)

    assert w_before == w_after == {leg_a: 0.5, leg_b: 0.5}


def test_both_legs_weaker_than_shy_returns_empty() -> None:
    """If neither leg's lookback score beats SHY's own score, the pair
    candidate must return an empty dict (cash held via the lane's own
    remainder convention)."""
    idx = pd.bdate_range("2022-01-03", periods=200)
    close = pd.DataFrame(
        {
            "QQQ": 100.0 * np.linspace(1.0, 0.97, len(idx)),  # declining
            "SPY": 100.0 * np.linspace(1.0, 0.98, len(idx)),  # declining
            mod.CASH: 100.0 * np.linspace(1.0, 1.20, len(idx)),  # SHY rallies hard
        },
        index=idx,
    )
    fn = mod.make_pair_switch_fn("QQQ", "SPY", 63)
    asof = idx[150]
    w = fn(close, asof)
    assert w == {}


def test_strong_leg_is_selected() -> None:
    """When one leg clearly outpaces both the other leg and SHY, it must be
    the sole 100%-weighted pick."""
    idx = pd.bdate_range("2022-01-03", periods=200)
    close = pd.DataFrame(
        {
            "QQQ": 100.0 * np.linspace(1.0, 1.40, len(idx)),  # strong rally
            "SPY": 100.0 * np.linspace(1.0, 1.02, len(idx)),  # nearly flat
            mod.CASH: 100.0 * np.linspace(1.0, 1.05, len(idx)),  # modest SHY gain
        },
        index=idx,
    )
    fn = mod.make_pair_switch_fn("QQQ", "SPY", 63)
    asof = idx[150]
    w = fn(close, asof)
    assert w == {"QQQ": pytest.approx(1.0)}


def test_static5050_always_fixed_regardless_of_trend() -> None:
    """The static placebo must never rank or filter -- same 0.5/0.5 book
    whether the pair is rallying or both legs are collapsing vs cash."""
    idx = pd.bdate_range("2022-01-03", periods=200)
    close = pd.DataFrame(
        {
            "QQQ": 100.0 * np.linspace(1.0, 0.90, len(idx)),
            "SPY": 100.0 * np.linspace(1.0, 0.95, len(idx)),
            mod.CASH: 100.0 * np.linspace(1.0, 1.30, len(idx)),
        },
        index=idx,
    )
    fn = mod.make_static5050_fn("QQQ", "SPY")
    asof = idx[150]
    w = fn(close, asof)
    assert w == {"QQQ": 0.5, "SPY": 0.5}


def test_pair_weights_sum_to_one_or_empty() -> None:
    close = _make_panel()
    for _pair_name, (a, b) in mod.PAIRS.items():
        for lb in mod.LOOKBACKS:
            fn = mod.make_pair_switch_fn(a, b, lb)
            asof = close.index[350]
            w = fn(close, asof)
            assert set(w) <= {a, b}
            assert sum(w.values()) <= 1.0 + 1e-9
            if w:
                assert next(iter(w.values())) == pytest.approx(1.0)
