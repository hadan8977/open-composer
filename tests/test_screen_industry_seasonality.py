"""Tests for `scripts/screen_batches/h20260930_10_industry_seasonality.py`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402
import h20260930_10_industry_seasonality as ind  # noqa: E402


def _panel(symbols: tuple[str, ...], seed: int = 0) -> pd.DataFrame:
    index = pd.bdate_range("2019-01-01", "2022-12-30")
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.01, size=(len(index), len(symbols)))
    return pd.DataFrame(100.0 * np.cumprod(1.0 + rets, axis=0), index=index, columns=symbols)


def test_universe_is_the_frozen_23_etfs() -> None:
    assert len(ind.INDUSTRY_ETFS) == 23
    assert len(set(ind.INDUSTRY_ETFS)) == 23
    assert not set(ind.INDUSTRY_ETFS) & set(b2.SECTOR_ETFS)


def test_specs_match_manifest_ids_and_grid() -> None:
    manifest = json.loads(
        (
            ROOT
            / "reports/research/iterations/h20260930_10_industry_seasonality"
            / "candidate-manifest.json"
        ).read_text()
    )
    assert [s["id"] for s in ind.SPECS] == [c["candidate_id"] for c in manifest["candidates"]]
    assert [s["id"] for s in ind.SPECS] == [g[0] for g in ind.GRID]
    for spec in ind.SPECS:
        assert tuple(spec["universe"]) == ind.INDUSTRY_ETFS
        assert spec["freq"] == "D"


def test_sector_universe_reproduces_parent_rule_weights() -> None:
    close = _panel(b2.SECTOR_ETFS)
    parent = opt.make_sector_seasonality_fn()
    wrapper = opt.make_sector_seasonality_fn(universe=b2.SECTOR_ETFS, top_n=2, avg_years=1)
    for asof in ind.b2.month_end_signal_dates(close.index)[15:]:
        assert wrapper(close, asof) == parent(close, asof)
        assert parent(close, asof) == b2.w_front_run_sector_top2(close, asof)


def test_placebo_shifts_are_2_to_9_and_reproducible() -> None:
    assert ind.PLACEBO_SHIFTS == (2, 3, 4, 5, 6, 7, 8, 9)
    close = _panel(ind.INDUSTRY_ETFS)
    fn_a = ind.make_shift_placebo_fn(top_n=2, avg_years=1, seed=7)
    fn_b = ind.make_shift_placebo_fn(top_n=2, avg_years=1, seed=7)
    fn_c = ind.make_shift_placebo_fn(top_n=2, avg_years=1, seed=8)
    dates = b2.month_end_signal_dates(close.index)[15:]
    a = [fn_a(close, d) for d in dates]
    b = [fn_b(close, d) for d in reversed(dates)][::-1]
    c = [fn_c(close, d) for d in dates]
    assert a == b
    assert a != c
    drawn = set()
    for seed in range(1, 21):
        for d in dates:
            m, y = b2._holding_month_and_year(d)
            drawn.add(int(np.random.default_rng([seed, y, m]).choice(ind.PLACEBO_SHIFTS)))
    assert drawn == set(range(2, 10))


def test_placebo_and_rule_only_fire_on_month_end() -> None:
    close = _panel(ind.INDUSTRY_ETFS)
    ends = set(b2.month_end_signal_dates(close.index))
    placebo = ind.make_shift_placebo_fn(top_n=3, avg_years=1, seed=1)
    real = ind.SPECS[1]["fn"]
    other = [d for d in close.index[400:520] if d not in ends]
    assert other
    for d in other:
        assert placebo(close, d) == {}
        assert real(close, d) == {}
    fired = [d for d in sorted(ends) if d >= pd.Timestamp("2021-01-01")]
    assert all(len(placebo(close, d)) == 3 for d in fired)
    assert all(abs(sum(real(close, d).values()) - 1.0) < 1e-9 for d in fired)
