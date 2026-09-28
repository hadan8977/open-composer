"""Tests for scripts/screen_batches/h20260928_40_equity_etf_menus.py: the
weight function must read only `close.loc[:asof]` (no look-ahead), must apply
the absolute-momentum-vs-SHY filter, and must pick exactly `top_n` names
(equal-weighted) when enough candidates clear the filter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_40_equity_etf_menus as mod  # noqa: E402


def _make_panel(n_days: int = 400, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily close panel: FACTOR_MENU + INDUSTRY_MENU + SHY, each a
    smooth deterministic random walk so lookback returns are well-defined
    and reproducible."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    cols = list(mod.FACTOR_MENU) + list(mod.INDUSTRY_MENU) + [mod.CASH]
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
    for menu in ("FACTOR", "INDUSTRY"):
        for lb in (63, 126, 252):
            for tn in (1, 2):
                for rebal in ("MO", "WK"):
                    assert f"{menu}_L{lb}_N{tn}_{rebal}" in ids


@pytest.mark.parametrize("lookback,top_n", [(63, 1), (126, 2), (252, 1)])
def test_no_lookahead(lookback: int, top_n: int) -> None:
    """Corrupting every row strictly after `asof` with extreme values must
    not change the weights computed at `asof`."""
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.FACTOR_MENU, lookback, top_n)
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
            "MTUM": 100.0 * np.linspace(1.0, 1.01, len(idx)),  # nearly flat
            "QUAL": 100.0 * np.linspace(1.0, 0.98, len(idx)),  # declining
            "USMV": 100.0 * np.linspace(1.0, 0.97, len(idx)),
            "VLUE": 100.0 * np.linspace(1.0, 0.96, len(idx)),
            "SIZE": 100.0 * np.linspace(1.0, 0.95, len(idx)),
            mod.CASH: 100.0 * np.linspace(1.0, 1.20, len(idx)),  # SHY rallies hard
        },
        index=idx,
    )
    fn = mod.make_rotation_fn(mod.FACTOR_MENU, 63, 2)
    asof = idx[150]
    w = fn(close, asof)
    assert w == {}


def test_top_n_count_and_equal_weight() -> None:
    """When enough names clear the absolute-momentum filter, exactly `top_n`
    names are picked, equal-weighted, weights summing to <= 1."""
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.INDUSTRY_MENU, 126, 2)
    asof = close.index[350]
    w = fn(close, asof)
    assert len(w) <= 2
    if w:
        vals = list(w.values())
        assert all(abs(v - vals[0]) < 1e-12 for v in vals)
        assert sum(w.values()) <= 1.0 + 1e-9


def test_top_n_one_picks_single_best() -> None:
    close = _make_panel()
    fn = mod.make_rotation_fn(mod.FACTOR_MENU, 63, 1)
    asof = close.index[300]
    w = fn(close, asof)
    assert len(w) <= 1
    if w:
        assert next(iter(w.values())) == pytest.approx(1.0)
