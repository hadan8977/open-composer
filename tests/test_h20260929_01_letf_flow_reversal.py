"""Synthetic-data tests for `scripts/screen_batches/h20260929_01_letf_flow_
reversal.py`. No backtest is run here and no real market data is read
(importing the module and constructing `CANDIDATES` never hits duckdb --
only calling a `LETF_*_RAND` weights_fn would, and this file never does).

Covers: candidate ids match the preregistered manifest exactly; long-only/
sum(weights)<=1/universe-only contract; trigger direction (a down day fires,
an up day of the same magnitude does not); the fixed-hold state machine
(hold length, no stacking on a retrigger, reset between independent sweeps);
no look-ahead (appending/mutating future rows never changes an already-
decided `asof`'s weight); and the RAND placebo's determinism (same inputs ->
same trigger days, independent of real price data).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260929_01_letf_flow_reversal as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _close_frame(index: pd.DatetimeIndex, prices: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(prices, index=index)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# (c) CANDIDATES shape matches the preregistered manifest exactly
# --------------------------------------------------------------------------


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260929_01_letf_flow_reversal"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(c.id for c in batch.CANDIDATES)
    assert module_ids == manifest_ids
    assert len(module_ids) == 15


def test_candidates_are_screen_candidate_d_freq_long_only_single_symbol() -> None:
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq == "D"
        assert len(c.universe) == 1
        assert callable(c.weights_fn)
        assert c.signal_dates_fn is None


# --------------------------------------------------------------------------
# Trigger direction: a down day fires, an up day of the same magnitude does not
# --------------------------------------------------------------------------


def test_letf_trigger_fires_on_down_day_not_up_day() -> None:
    index = pd.bdate_range("2024-01-01", periods=5)
    down_fn = batch._make_letf_trigger("SPY", 2)
    down_close = _close_frame(index[:2], {"SPY": [100.0, 97.5]})  # -2.5%
    up_close = _close_frame(index[:2], {"SPY": [100.0, 102.5]})  # +2.5%
    assert down_fn(down_close, index[1])
    assert not down_fn(up_close, index[1])


def test_letf_trigger_respects_exact_threshold_boundary() -> None:
    index = pd.bdate_range("2024-01-01", periods=2)
    fn = batch._make_letf_trigger("SPY", 2)
    exactly_2pct = _close_frame(index, {"SPY": [100.0, 98.0]})
    assert fn(exactly_2pct, index[1])  # <=, boundary included
    just_under = _close_frame(index, {"SPY": [100.0, 98.5]})
    assert not fn(just_under, index[1])


def test_letf_trigger_missing_column_returns_false() -> None:
    index = pd.bdate_range("2024-01-01", periods=2)
    fn = batch._make_letf_trigger("SPY", 2)
    close = _close_frame(index, {"QQQ": [100.0, 90.0]})
    assert not fn(close, index[1])


# --------------------------------------------------------------------------
# Stateful hold: length, no stacking on retrigger, reset between sweeps
# --------------------------------------------------------------------------


def test_event_hold_weights_fn_holds_for_fixed_hold_then_returns_cash() -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    # trigger only on day 1 (index[1]); flat afterward.
    prices = [100.0, 97.0, 97.0, 97.0, 97.0, 97.0, 97.0, 97.0, 97.0, 97.0]
    close = _close_frame(index, {"SPY": prices})
    fn = batch._make_event_hold_weights_fn("SPY", batch._make_letf_trigger("SPY", 2), fixed_hold=3)
    weights_by_day = [fn(close, d) for d in index]
    # trigger fires at index[1]; holds (returns SPY) for hold=3 more calls
    # (index[1] itself, then index[2], index[3]), then cash from index[4].
    assert weights_by_day[1] == {"SPY": 1.0}
    assert weights_by_day[2] == {"SPY": 1.0}
    assert weights_by_day[3] == {"SPY": 1.0}
    assert weights_by_day[4] == {}
    assert weights_by_day[5] == {}


def test_event_hold_weights_fn_ignores_retrigger_while_active() -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    # down day at index[1] AND index[2] (retrigger while still holding).
    prices = [100.0, 97.0, 93.0, 93.0, 93.0, 93.0, 93.0, 93.0, 93.0, 93.0]
    close = _close_frame(index, {"SPY": prices})
    fn = batch._make_event_hold_weights_fn("SPY", batch._make_letf_trigger("SPY", 2), fixed_hold=3)
    weights_by_day = [fn(close, d) for d in index]
    # First trigger at index[1] holds for 3 calls (index[1..3]); the
    # retrigger at index[2] (still active) is ignored -- no extension, so
    # cash resumes at index[4], not later.
    assert weights_by_day[1] == {"SPY": 1.0}
    assert weights_by_day[2] == {"SPY": 1.0}
    assert weights_by_day[3] == {"SPY": 1.0}
    assert weights_by_day[4] == {}


def test_event_hold_weights_fn_resets_on_new_sweep() -> None:
    index = pd.bdate_range("2024-01-01", periods=5)
    prices = [100.0, 97.0, 97.0, 97.0, 97.0]
    close = _close_frame(index, {"SPY": prices})
    fn = batch._make_event_hold_weights_fn("SPY", batch._make_letf_trigger("SPY", 2), fixed_hold=3)
    first_sweep = [fn(close, d) for d in index]
    assert first_sweep[1] == {"SPY": 1.0}
    assert first_sweep[4] == {}
    # A second full sweep from index[0] again must reproduce the identical
    # result, not continue mid-hold from wherever the first sweep ended.
    second_sweep = [fn(close, d) for d in index]
    assert second_sweep == first_sweep


# --------------------------------------------------------------------------
# No look-ahead: mutating rows strictly after `asof` never changes the
# already-decided weight at `asof`.
# --------------------------------------------------------------------------


def test_no_lookahead_on_future_price_history() -> None:
    index = pd.bdate_range("2024-01-01", periods=6)
    prices_a = [100.0, 97.0, 97.0, 97.0, 200.0, 5.0]  # wild future values
    prices_b = [100.0, 97.0, 97.0, 97.0, 1.0, 999.0]
    close_a = _close_frame(index, {"SPY": prices_a})
    close_b = _close_frame(index, {"SPY": prices_b})
    fn_a = batch._make_event_hold_weights_fn(
        "SPY", batch._make_letf_trigger("SPY", 2), fixed_hold=3
    )
    fn_b = batch._make_event_hold_weights_fn(
        "SPY", batch._make_letf_trigger("SPY", 2), fixed_hold=3
    )
    decided_at = index[3]
    for d in index[: index.get_loc(decided_at) + 1]:
        w_a = fn_a(close_a, d)
        w_b = fn_b(close_b, d)
        assert w_a == w_b  # identical up to and including `decided_at`


# --------------------------------------------------------------------------
# RAND placebo: deterministic, price-independent, contract-respecting
# --------------------------------------------------------------------------


def test_rand_trigger_is_deterministic_and_price_independent() -> None:
    index = pd.bdate_range("2024-01-01", periods=30)
    close_1 = _close_frame(index, {"SPY": [100.0] * 30})
    close_2 = _close_frame(index, {"SPY": [1.0, 500.0] * 15})  # wildly different prices
    fn = batch._make_rand_trigger("SPY")
    # Force a known, deterministic trigger rate so the test does not depend
    # on real data (importing/constructing the trigger fn never reads data;
    # only calling it does, so seed the cache directly).
    batch._RAND_RATE_CACHE["SPY"] = 0.5
    triggers_1 = [fn(close_1, d) for d in index]
    triggers_2 = [fn(close_2, d) for d in index]
    assert triggers_1 == triggers_2  # price-independent
    assert any(triggers_1) and not all(triggers_1)  # a real mix, not degenerate
    del batch._RAND_RATE_CACHE["SPY"]


def test_rand_trigger_zero_rate_never_fires() -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    close = _close_frame(index, {"SPY": [100.0] * 10})
    fn = batch._make_rand_trigger("SPY")
    batch._RAND_RATE_CACHE["SPY"] = 0.0
    assert not any(fn(close, d) for d in index)
    del batch._RAND_RATE_CACHE["SPY"]


@pytest.mark.parametrize("candidate", batch.CANDIDATES, ids=lambda c: c.id)
def test_universe_only_and_long_only_over_full_history(
    candidate: lane.ScreenCandidate, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = pd.bdate_range("2024-01-01", "2024-06-30")
    sym = candidate.universe[0]
    # deterministic synthetic path with some sharp drops, so triggers fire
    prices = [100.0]
    for i in range(1, len(index)):
        prices.append(prices[-1] * (0.95 if i % 17 == 0 else 1.001))
    close = _close_frame(index, {sym: prices})
    if candidate.id.endswith("_RAND"):
        monkeypatch.setitem(batch._RAND_RATE_CACHE, sym, 0.1)
    for d in index:
        weights = candidate.weights_fn(close, d)
        _assert_contract(weights, candidate.universe)
