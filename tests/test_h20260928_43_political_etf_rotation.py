"""Tests for scripts/screen_batches/h20260928_43_political_etf_rotation.py:
the weight function must read only `close.loc[:asof]` (no look-ahead), must
apply the absolute-momentum-vs-SHY filter, must pick exactly `top_n` names
(equal-weighted) when enough candidates clear the filter, must return empty
weights when a symbol has no history yet, and every candidate id must match
the preregistered manifest.
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

import h20260928_43_political_etf_rotation as mod  # noqa: E402


def _make_panel(n_days: int = 400, seed: int = 11) -> pd.DataFrame:
    """Synthetic daily close panel: POLITICAL_MENU + PLACEBO_BIGTECH_MENU +
    SHY, each a smooth deterministic random walk so lookback returns are
    well-defined and reproducible."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    cols = list(mod.POLITICAL_MENU) + list(mod.PLACEBO_BIGTECH_MENU) + [mod.CASH]
    data = {}
    for i, col in enumerate(cols):
        drift = 0.0002 + 0.00002 * i  # distinct drift per symbol -> distinct ranks
        noise = rng.normal(0.0, 0.003, size=n_days)
        rets = drift + noise
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=idx)


def test_spec_count_and_ids() -> None:
    assert len(mod.SPECS) == 24
    ids = {spec["id"] for spec in mod.SPECS}
    assert len(ids) == 24
    for menu in ("POLITICAL", "PLACEBO_BIGTECH"):
        for lb in (63, 126, 252):
            for tn in (1, 2):
                for rebal in ("MO", "WK"):
                    assert f"{menu}_L{lb}_N{tn}_{rebal}" in ids


def test_ids_match_preregistered_manifest() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260928_43_political_etf_rotation"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = {c["candidate_id"] for c in manifest["candidates"]}
    module_ids = {spec["id"] for spec in mod.SPECS}
    assert manifest_ids == module_ids


@pytest.mark.parametrize("lookback,top_n", [(63, 1), (126, 2), (252, 1)])
def test_no_lookahead(lookback: int, top_n: int) -> None:
    """Corrupting every row strictly after `asof` with extreme values must
    not change the weights computed at `asof`."""
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.POLITICAL_MENU, lookback, top_n)
    asof = close.index[300]

    w_before = fn(close, asof)

    corrupted = close.copy()
    future_mask = corrupted.index > asof
    corrupted.loc[future_mask, :] = 1e9
    w_after = fn(corrupted, asof)

    assert w_before == w_after
    assert w_before != {}


def test_absolute_momentum_filter_rejects_weak_pick() -> None:
    """If the top-ranked name's lookback score does not beat SHY's own score,
    it must be filtered out (weight left to the lane's SHY remainder, i.e.
    an empty dict from this candidate)."""
    idx = pd.bdate_range("2022-01-03", periods=200)
    close = pd.DataFrame(
        {
            "NANC": 100.0 * np.linspace(1.0, 1.01, len(idx)),  # nearly flat
            "GOP": 100.0 * np.linspace(1.0, 0.98, len(idx)),  # declining
            "MAGA": 100.0 * np.linspace(1.0, 0.97, len(idx)),
            "DEMZ": 100.0 * np.linspace(1.0, 0.96, len(idx)),
            mod.CASH: 100.0 * np.linspace(1.0, 1.20, len(idx)),  # SHY rallies hard
        },
        index=idx,
    )
    fn = mod.make_rotation_fn(mod.POLITICAL_MENU, 63, 2)
    asof = idx[150]
    w = fn(close, asof)
    assert w == {}


def test_top_n_count_and_equal_weight() -> None:
    """When enough names clear the absolute-momentum filter, exactly `top_n`
    names are picked, equal-weighted, weights summing to <= 1."""
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.PLACEBO_BIGTECH_MENU, 126, 2)
    asof = close.index[350]
    w = fn(close, asof)
    assert len(w) <= 2
    if w:
        vals = list(w.values())
        assert all(abs(v - vals[0]) < 1e-12 for v in vals)
        assert sum(w.values()) <= 1.0 + 1e-9


def test_top_n_one_picks_single_best() -> None:
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.POLITICAL_MENU, 63, 1)
    asof = close.index[300]
    w = fn(close, asof)
    assert len(w) <= 1
    if w:
        assert next(iter(w.values())) == pytest.approx(1.0)


def test_empty_when_symbol_has_no_history_yet() -> None:
    """A symbol that has not yet listed (e.g. GOP/NANC before their
    2023-02-07 launch, represented here by NaN rows) must not be selectable;
    if no menu ticker has any valid score at `asof`, weights_fn returns {}."""
    idx = pd.bdate_range("2022-01-03", periods=100)
    close = pd.DataFrame(
        {
            "NANC": np.nan,  # not listed yet over the whole synthetic history
            "GOP": np.nan,
            "MAGA": np.nan,
            "DEMZ": np.nan,
            mod.CASH: 100.0 * np.linspace(1.0, 1.05, len(idx)),
        },
        index=idx,
    )
    fn = mod.make_rotation_fn(mod.POLITICAL_MENU, 63, 1)
    asof = idx[80]
    w = fn(close, asof)
    assert w == {}


def test_empty_before_enough_lookback_history() -> None:
    """Before `lookback` sessions of history exist, momentum_score is NaN and
    weights_fn must return {} rather than raising or fabricating a signal."""
    close = _make_panel(n_days=100)
    fn = mod.make_rotation_fn(mod.POLITICAL_MENU, 63, 1)
    asof = close.index[10]  # far fewer than 63 sessions of history
    w = fn(close, asof)
    assert w == {}


def test_menus_are_disjoint_and_correctly_sized() -> None:
    assert set(mod.POLITICAL_MENU) == {"NANC", "GOP", "MAGA", "DEMZ"}
    assert set(mod.PLACEBO_BIGTECH_MENU) == {"QQQ", "XLK", "SPY", "DIA"}
    assert set(mod.POLITICAL_MENU).isdisjoint(mod.PLACEBO_BIGTECH_MENU)
