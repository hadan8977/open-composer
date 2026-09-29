"""Synthetic-data tests for `scripts/screen_batches/h20260929_10_vix_vrp_etp.py`.

No backtest is run here; importing the module DOES read the two local VIX/
VIX3M CSVs (`data/research/vix/VIXCLS.csv`, `data/research/vix/VXVCLS.csv`)
once at module scope (same pattern as `h20260928_18_vix_putw.py`'s VIX
loader), but every test below constructs its own synthetic `close` frame and
monkeypatches the module's cached VIX/VIX3M series so results never depend on
real market data.

Covers: candidate ids/shape match the preregistered manifest exactly;
long-only/sum(weights)<=1/universe-only contract; the 4-case sign logic
(short-vol vs not, full vs half size); signal-1-only and signal-2-only drop
the other signal; no look-ahead (future VIX/VIX3M/price rows never change an
already-decided `asof`'s weight); RAND placebo determinism and price-
independence; static 50/50 always returns exactly {SMH: 0.5, QQQ: 0.5}.
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

import h20260929_10_vix_vrp_etp as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _close_frame(index: pd.DatetimeIndex, prices: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(prices, index=index)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


def _patch_vix(monkeypatch: pytest.MonkeyPatch, index: pd.DatetimeIndex, vix: list[float]) -> None:
    monkeypatch.setattr(batch, "_VIX_FULL", pd.Series(vix, index=index))
    batch._ALIGN_CACHE.clear()


def _patch_vix_vix3m(
    monkeypatch: pytest.MonkeyPatch,
    index: pd.DatetimeIndex,
    vix: list[float],
    vix3m: list[float],
) -> None:
    monkeypatch.setattr(batch, "_VIX_FULL", pd.Series(vix, index=index))
    monkeypatch.setattr(batch, "_VIX3M_FULL", pd.Series(vix3m, index=index))
    batch._ALIGN_CACHE.clear()


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    batch._ALIGN_CACHE.clear()
    batch._RAND_RATE_CACHE.clear()
    yield
    batch._ALIGN_CACHE.clear()
    batch._RAND_RATE_CACHE.clear()


# --------------------------------------------------------------------------
# Candidate shape matches the preregistered manifest exactly
# --------------------------------------------------------------------------


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260929_10_vix_vrp_etp"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(c.id for c in batch.CANDIDATES)
    assert module_ids == manifest_ids
    assert len(module_ids) == 12


def test_candidates_are_screen_candidate_long_only() -> None:
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq in ("D", "M")
        assert callable(c.weights_fn)
        assert c.signal_dates_fn is None


# --------------------------------------------------------------------------
# 4-case sign logic: full short-vol, half short-vol, not-short-vol (cases 3/4)
# --------------------------------------------------------------------------


def test_full_short_vol_case_evrp_positive_contango(monkeypatch: pytest.MonkeyPatch) -> None:
    # SPY flat -> eRV ~ 0 -> eVRP = VIX - 0 = VIX > 0 whenever VIX > 0.
    index = pd.bdate_range("2024-01-01", periods=15)
    spy = [100.0] * 15
    close = _close_frame(index, {"SPY": spy})
    _patch_vix_vix3m(monkeypatch, index, vix=[20.0] * 15, vix3m=[25.0] * 15)  # VIX < VIX3M
    fn = batch._combo_weights_fn(10, non_short_vol_leg=None)
    w = fn(close, index[-1])
    assert w == {"SVXY": pytest.approx(0.20)}  # VIX/100 = 0.20


def test_half_short_vol_case_evrp_negative_contango(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sharp SPY swings -> large eRV -> eVRP = VIX - eRV < 0.
    index = pd.bdate_range("2024-01-01", periods=15)
    spy = [100.0 * (1.05 if i % 2 == 0 else 0.95) for i in range(15)]
    close = _close_frame(index, {"SPY": spy})
    _patch_vix_vix3m(monkeypatch, index, vix=[20.0] * 15, vix3m=[25.0] * 15)  # VIX < VIX3M
    fn = batch._combo_weights_fn(10, non_short_vol_leg=None)
    w = fn(close, index[-1])
    assert w == {"SVXY": pytest.approx(0.10)}  # 0.5 * VIX/100 = 0.10


def test_not_short_vol_case_backwardation_returns_spy_or_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.bdate_range("2024-01-01", periods=15)
    spy = [100.0 * (1.05 if i % 2 == 0 else 0.95) for i in range(15)]  # eVRP < 0
    close = _close_frame(index, {"SPY": spy})
    _patch_vix_vix3m(monkeypatch, index, vix=[30.0] * 15, vix3m=[20.0] * 15)  # VIX > VIX3M (case 3)
    fn_spy = batch._combo_weights_fn(10, non_short_vol_leg="SPY")
    fn_shy = batch._combo_weights_fn(10, non_short_vol_leg=None)
    assert fn_spy(close, index[-1]) == {"SPY": 1.0}
    assert fn_shy(close, index[-1]) == {}


def test_not_short_vol_case_conflicting_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.bdate_range("2024-01-01", periods=15)
    spy = [100.0] * 15  # eRV ~ 0 -> eVRP = VIX > 0
    close = _close_frame(index, {"SPY": spy})
    _patch_vix_vix3m(monkeypatch, index, vix=[30.0] * 15, vix3m=[20.0] * 15)  # VIX > VIX3M, case 4
    fn_shy = batch._combo_weights_fn(10, non_short_vol_leg=None)
    assert fn_shy(close, index[-1]) == {}


def test_weight_capped_at_one_for_extreme_vix(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.bdate_range("2024-01-01", periods=15)
    close = _close_frame(index, {"SPY": [100.0] * 15})
    _patch_vix_vix3m(monkeypatch, index, vix=[150.0] * 15, vix3m=[200.0] * 15)
    fn = batch._combo_weights_fn(10, non_short_vol_leg=None)
    w = fn(close, index[-1])
    assert w["SVXY"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Signal-1-only / signal-2-only drop the other signal
# --------------------------------------------------------------------------


def test_sig1_only_ignores_term_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.bdate_range("2024-01-01", periods=15)
    close = _close_frame(index, {"SPY": [100.0] * 15})  # eVRP = VIX > 0
    # backwardation (would be case 3/4 in the full combo) -- sig1-only should
    # still go short-vol since it only looks at eVRP.
    _patch_vix_vix3m(monkeypatch, index, vix=[20.0] * 15, vix3m=[10.0] * 15)
    fn = batch._sig1_only_weights_fn(10, non_short_vol_leg=None)
    w = fn(close, index[-1])
    assert w == {"SVXY": pytest.approx(0.20)}


def test_sig2_only_ignores_evrp(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.bdate_range("2024-01-01", periods=15)
    spy = [100.0 * (1.05 if i % 2 == 0 else 0.95) for i in range(15)]  # eVRP < 0
    close = _close_frame(index, {"SPY": spy})
    _patch_vix_vix3m(monkeypatch, index, vix=[20.0] * 15, vix3m=[30.0] * 15)  # VIX < VIX3M
    fn = batch._sig2_only_weights_fn(non_short_vol_leg=None)
    w = fn(close, index[-1])
    assert w == {"SVXY": pytest.approx(0.20)}  # short-vol regardless of eVRP sign


# --------------------------------------------------------------------------
# No look-ahead
# --------------------------------------------------------------------------


def test_no_lookahead_future_vix_rows_do_not_change_past_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.bdate_range("2024-01-01", periods=20)
    spy = [100.0 + i * 0.1 for i in range(20)]
    close = _close_frame(index, {"SPY": spy})
    vix_a = [20.0] * 20
    vix_b = list(vix_a)
    vix3m_a = [25.0] * 20
    vix3m_b = list(vix3m_a)
    decided_idx = 14
    # mutate rows strictly AFTER decided_idx with wildly different values
    for i in range(decided_idx + 1, 20):
        vix_b[i] = 999.0
        vix3m_b[i] = 1.0
    fn = batch._combo_weights_fn(10, non_short_vol_leg=None)

    _patch_vix_vix3m(monkeypatch, index, vix_a, vix3m_a)
    w_a = fn(close, index[decided_idx])
    _patch_vix_vix3m(monkeypatch, index, vix_b, vix3m_b)
    w_b = fn(close, index[decided_idx])
    assert w_a == w_b


def test_no_lookahead_future_price_rows_do_not_change_past_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.bdate_range("2024-01-01", periods=20)
    decided_idx = 14
    spy_a = [100.0 + i * 0.1 for i in range(20)]
    spy_b = list(spy_a)
    for i in range(decided_idx + 1, 20):
        spy_b[i] = 5.0  # wild future price change
    _patch_vix_vix3m(monkeypatch, index, [20.0] * 20, [25.0] * 20)
    fn = batch._combo_weights_fn(10, non_short_vol_leg=None)
    w_a = fn(_close_frame(index, {"SPY": spy_a}), index[decided_idx])
    w_b = fn(_close_frame(index, {"SPY": spy_b}), index[decided_idx])
    assert w_a == w_b


# --------------------------------------------------------------------------
# RAND placebo: deterministic, price-independent trigger, VIX-sized on trigger
# --------------------------------------------------------------------------


def test_rand_placebo_is_deterministic_and_price_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.bdate_range("2024-01-01", periods=30)
    _patch_vix_vix3m(monkeypatch, index, [20.0] * 30, [25.0] * 30)
    monkeypatch.setitem(batch._RAND_RATE_CACHE, "rate", 0.5)
    close_1 = _close_frame(index, {"SPY": [100.0] * 30})
    close_2 = _close_frame(index, {"SPY": [1.0, 500.0] * 15})
    w1 = [batch._rand_placebo_weights_fn(close_1, d) for d in index]
    w2 = [batch._rand_placebo_weights_fn(close_2, d) for d in index]
    assert w1 == w2
    fired = [bool(w) for w in w1]
    assert any(fired) and not all(fired)


def test_rand_placebo_zero_rate_never_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    _patch_vix_vix3m(monkeypatch, index, [20.0] * 10, [25.0] * 10)
    monkeypatch.setitem(batch._RAND_RATE_CACHE, "rate", 0.0)
    close = _close_frame(index, {"SPY": [100.0] * 10})
    assert all(batch._rand_placebo_weights_fn(close, d) == {} for d in index)


# --------------------------------------------------------------------------
# Static 50/50 SMH/QQQ
# --------------------------------------------------------------------------


def test_static5050_always_half_half() -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    close = _close_frame(index, {"SMH": [100.0] * 10, "QQQ": [400.0] * 10})
    fn = batch._static5050_weights_fn("SMH", "QQQ")
    for d in index:
        assert fn(close, d) == {"SMH": 0.5, "QQQ": 0.5}


def test_static5050_missing_column_returns_empty() -> None:
    index = pd.bdate_range("2024-01-01", periods=3)
    close = _close_frame(index, {"SMH": [100.0] * 3})
    fn = batch._static5050_weights_fn("SMH", "QQQ")
    assert fn(close, index[-1]) == {}


# --------------------------------------------------------------------------
# Contract sweep over every real candidate (synthetic panel with all symbols)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("candidate", batch.CANDIDATES, ids=lambda c: c.id)
def test_universe_only_and_long_only_over_full_history(
    candidate: lane.ScreenCandidate, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = pd.bdate_range("2024-01-01", "2024-06-30")
    rng = np.random.default_rng(0)
    spy = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, len(index)))
    smh = 200.0 * np.cumprod(1.0 + rng.normal(0, 0.015, len(index)))
    qqq = 400.0 * np.cumprod(1.0 + rng.normal(0, 0.012, len(index)))
    close = _close_frame(index, {"SPY": spy, "SMH": smh, "QQQ": qqq})
    vix = 15.0 + 10.0 * np.abs(rng.normal(0, 1, len(index)))
    vix3m = vix + rng.normal(0, 2, len(index))
    _patch_vix_vix3m(monkeypatch, index, list(vix), list(vix3m))
    if candidate.id == "VVRP_RAND_PLACEBO":
        monkeypatch.setitem(batch._RAND_RATE_CACHE, "rate", 0.2)
    for d in index:
        weights = candidate.weights_fn(close, d)
        _assert_contract(weights, candidate.universe)
