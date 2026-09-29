"""Synthetic-data tests for `scripts/screen_batches/h20260929_01_dip_rejudge.
py`. No backtest is run here and no real market data is read: importing the
module and constructing `CANDIDATES` never hits duckdb; `_dip_indicators`
only loads data lazily on first call, and every test here injects synthetic
OHLC frames directly into `_OHLC_CACHE` instead of hitting real data.

Covers: candidate ids match the preregistered manifest exactly; long-only/
sum(weights)<=1/universe-only contract; D2's fixed 1-day hold; D4's entry/
exit direction (rule fires when the entry condition is met, exits when the
exit condition is met); no look-ahead (mutating rows strictly after `asof`
never changes an already-decided weight); reset between independent sweeps.
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

import h20260929_01_dip_rejudge as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


def _seed_ohlc(symbol: str, index: pd.DatetimeIndex, close: list[float]) -> None:
    """Synthetic OHLC with high == low == open == close (a degenerate but
    valid panel: IBS is then 0.5 everywhere unless a test overrides high/low
    directly), injected into `_OHLC_CACHE` so no real data is read."""
    frame = pd.DataFrame({"open": close, "high": close, "low": close, "close": close}, index=index)
    batch._OHLC_CACHE[symbol] = frame
    batch._DIP_IND_CACHE.pop(symbol, None)


def _close_frame(index: pd.DatetimeIndex, prices: dict[str, list[float]]) -> pd.DataFrame:
    """The harness's own close-only panel argument to `weights_fn` -- not
    the same object as the module's separately-loaded OHLC cache."""
    return pd.DataFrame(prices, index=index)


@pytest.fixture(autouse=True)
def _clear_caches():
    yield
    batch._OHLC_CACHE.clear()
    batch._DIP_IND_CACHE.clear()


# --------------------------------------------------------------------------
# (c) CANDIDATES shape matches the preregistered manifest exactly
# --------------------------------------------------------------------------


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260929_01_dip_rejudge"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(c.id for c in batch.CANDIDATES)
    assert module_ids == manifest_ids
    assert len(module_ids) == 12


def test_candidates_are_screen_candidate_d_freq_long_only_single_symbol() -> None:
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq == "D"
        assert len(c.universe) == 1
        assert callable(c.weights_fn)
        assert c.signal_dates_fn is None


# --------------------------------------------------------------------------
# D2: raw IBS < 0.20, fixed 1-session hold
# --------------------------------------------------------------------------


def test_d2_entry_on_low_ibs_then_fixed_one_day_hold() -> None:
    index = pd.bdate_range("2024-01-01", periods=8)
    # IBS = (close - low) / (high - low). Day 3: close near the low -> low IBS.
    high = [110.0] * 8
    low = [90.0] * 8
    close = [100.0, 100.0, 100.0, 91.0, 100.0, 100.0, 100.0, 100.0]  # IBS[3] = 1/20 = 0.05
    ohlc = pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=index)
    batch._OHLC_CACHE["SPY"] = ohlc
    batch._DIP_IND_CACHE.pop("SPY", None)

    fn = batch._make_dip_weights_fn("SPY", "D2")
    harness_close = _close_frame(index, {"SPY": close})
    weights_by_day = [fn(harness_close, d) for d in index]
    assert weights_by_day[3] == {"SPY": 1.0}  # entry decided at day 3's close
    assert weights_by_day[4] == {}  # fixed_hold=1 -> flat starting day 4's decision


def test_d2_no_entry_when_ibs_high() -> None:
    index = pd.bdate_range("2024-01-01", periods=5)
    high = [110.0] * 5
    low = [90.0] * 5
    close = [109.0] * 5  # IBS = 19/20 = 0.95, never < 0.20
    ohlc = pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=index)
    batch._OHLC_CACHE["SPY"] = ohlc
    batch._DIP_IND_CACHE.pop("SPY", None)

    fn = batch._make_dip_weights_fn("SPY", "D2")
    harness_close = _close_frame(index, {"SPY": close})
    for d in index:
        assert fn(harness_close, d) == {}


# --------------------------------------------------------------------------
# D4: close > SMA200 & RSI(2) <= 5 entry; close > SMA5 exit -- direction only
# (full SMA200/RSI2 warmup is long; this checks the entry/exit SERIES
# construction directly rather than requiring 200+ days of synthetic data).
# --------------------------------------------------------------------------


def test_d4_signals_series_construction_matches_formula() -> None:
    index = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(0)
    close = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, len(index))), index=index)
    close = close.clip(lower=1.0)
    ohlc = pd.DataFrame({"open": close, "high": close, "low": close, "close": close}, index=index)
    batch._OHLC_CACHE["SPY"] = ohlc
    batch._DIP_IND_CACHE.pop("SPY", None)

    entry, exit_, max_hold, fixed_hold = batch._dip_signals("SPY", "D4")
    ind = batch._dip_indicators("SPY")
    expected_entry = (ind.close > ind.sma200) & (ind.rsi2 <= 5)
    expected_exit = ind.close > ind.sma5
    pd.testing.assert_series_equal(entry, expected_entry.fillna(False), check_names=False)
    pd.testing.assert_series_equal(exit_, expected_exit.fillna(False), check_names=False)
    assert max_hold is None
    assert fixed_hold is None


def test_d6_is_d4_entry_and_low_ibs() -> None:
    index = pd.bdate_range("2024-01-01", periods=250)
    rng = np.random.default_rng(1)
    close = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, len(index))), index=index)
    close = close.clip(lower=1.0)
    high = close + 2.0
    low = close - 2.0
    ohlc = pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=index)
    batch._OHLC_CACHE["QQQ"] = ohlc
    batch._DIP_IND_CACHE.pop("QQQ", None)

    d4_entry, _, _, _ = batch._dip_signals("QQQ", "D4")
    d6_entry, d6_exit, _, _ = batch._dip_signals("QQQ", "D6")
    ind = batch._dip_indicators("QQQ")
    assert (d6_entry & ~(d4_entry & (ind.ibs < 0.20))).sum() == 0
    assert (~d6_entry & (d4_entry & (ind.ibs < 0.20))).sum() == 0
    pd.testing.assert_series_equal(d6_exit, (ind.close > ind.sma5).fillna(False), check_names=False)


# --------------------------------------------------------------------------
# No look-ahead & sweep reset (using the fixed-hold D2 rule, cheap to seed)
# --------------------------------------------------------------------------


def test_no_lookahead_on_future_ohlc() -> None:
    index = pd.bdate_range("2024-01-01", periods=8)
    close_a = [100.0, 100.0, 100.0, 91.0, 100.0, 5.0, 200.0, 1.0]
    close_b = [100.0, 100.0, 100.0, 91.0, 100.0, 999.0, 1.0, 500.0]
    _seed_ohlc("SPY", index, close_a)
    fn_a = batch._make_dip_weights_fn("SPY", "D2")
    harness_a = _close_frame(index, {"SPY": close_a})
    decided_at = index[4]
    results_a = [fn_a(harness_a, d) for d in index[: index.get_loc(decided_at) + 1]]

    _seed_ohlc("SPY", index, close_b)
    fn_b = batch._make_dip_weights_fn("SPY", "D2")
    harness_b = _close_frame(index, {"SPY": close_b})
    results_b = [fn_b(harness_b, d) for d in index[: index.get_loc(decided_at) + 1]]
    assert results_a == results_b


def test_resets_on_new_sweep() -> None:
    index = pd.bdate_range("2024-01-01", periods=6)
    close = [100.0, 100.0, 100.0, 91.0, 100.0, 100.0]
    _seed_ohlc("SPY", index, close)
    fn = batch._make_dip_weights_fn("SPY", "D2")
    harness = _close_frame(index, {"SPY": close})
    first_sweep = [fn(harness, d) for d in index]
    second_sweep = [fn(harness, d) for d in index]
    assert first_sweep == second_sweep


@pytest.mark.parametrize("candidate", batch.CANDIDATES, ids=lambda c: c.id)
def test_universe_only_and_long_only_over_synthetic_history(
    candidate: lane.ScreenCandidate,
) -> None:
    index = pd.bdate_range("2024-01-01", "2024-12-31")
    sym = candidate.universe[0]
    rng = np.random.default_rng(hash(candidate.id) % (2**32))
    close = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, len(index))), index=index)
    close = close.clip(lower=1.0)
    high = close + 2.0
    low = close - 2.0
    _seed_ohlc(sym, index, close.tolist())
    batch._OHLC_CACHE[sym]["high"] = high.to_numpy()
    batch._OHLC_CACHE[sym]["low"] = low.to_numpy()
    batch._DIP_IND_CACHE.pop(sym, None)

    harness_close = _close_frame(index, {sym: close.tolist()})
    for d in index:
        weights = candidate.weights_fn(harness_close, d)
        _assert_contract(weights, candidate.universe)
