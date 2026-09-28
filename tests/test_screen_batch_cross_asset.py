"""H-20260928-02 cross-asset sleeve candidates: synthetic-data unit tests, no
network, no market panel. Checks long-only, sum(weights) <= 1, no look-ahead
(future rows never change a past `asof` decision), and a hand-computed D2
inverse-volatility case."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "screen_batches"))

import h20260928_02_cross_asset as batch  # noqa: E402


def _assert_long_only_sum_le_1(weights: dict[str, float]) -> None:
    assert all(v > 0 for v in weights.values()), weights
    assert sum(weights.values()) <= 1.0 + 1e-9, weights


# --- D1 Defense First: flat history, a single jump exactly on `asof` so all
# four (1/3/6/12-month) lookbacks read the same pre-jump reference price and
# the mean score equals the jump return exactly. -----------------------------


def _d1_frame() -> tuple[pd.DataFrame, pd.Timestamp]:
    index = pd.bdate_range("2016-01-04", periods=280)
    asof = index[-1]
    jumps = {"TLT": 0.10, "DBC": 0.05, "GLD": 0.02, "UUP": -0.03, "BIL": 0.0, "SPY": 0.0}
    data = {}
    for sym, jump in jumps.items():
        prices = np.full(len(index), 100.0)
        prices[-1] = 100.0 * (1.0 + jump)
        data[sym] = prices
    return pd.DataFrame(data, index=index), asof


def test_d1_rank_weights_and_hurdle_fallback() -> None:
    close, asof = _d1_frame()
    weights = batch.d1_weights_fn(close, asof)
    # TLT (score +0.10, rank 1) -> 0.40; DBC (+0.05, rank 2) -> 0.30;
    # GLD (+0.02, rank 3, still >= BIL's 0.0 hurdle) -> 0.20; UUP (-0.03,
    # below the 0.0 hurdle) redirected to SPY -> 0.10.
    expected = {"TLT": 0.40, "DBC": 0.30, "GLD": 0.20, "SPY": 0.10}
    assert weights.keys() == expected.keys()
    for sym, value in expected.items():
        assert weights[sym] == pytest.approx(value, abs=1e-9)
    _assert_long_only_sum_le_1(weights)


def test_d1_no_lookahead() -> None:
    close, asof = _d1_frame()
    baseline = batch.d1_weights_fn(close, asof)
    extra_index = pd.bdate_range(asof + pd.Timedelta(days=1), periods=10)
    crash = pd.DataFrame(
        {sym: np.full(10, 1.0) for sym in close.columns}, index=extra_index
    )  # a wildly different future (near-zero prices) must not change the past
    extended = pd.concat([close, crash])
    perturbed = batch.d1_weights_fn(extended, asof)
    assert perturbed == baseline


def test_d1_warmup_returns_empty() -> None:
    close, _asof = _d1_frame()
    too_early = close.index[5]  # far short of the 12-month lookback
    assert batch.d1_weights_fn(close, too_early) == {}


# --- D2 absolute momentum / inverse-63-session-vol: flat history, then a
# 63-day alternating two-point return window ending at `asof` for TLT/DBC
# (hand-computed std ratio exactly 2:1 by construction, see below), GLD/UUP
# held flat (ineligible, tied with SHY's 0% hurdle). -------------------------


def _two_point_series(base: float, up: float, down: float, n_up: int, n_down: int) -> np.ndarray:
    """`n_up` days of `+up` return followed by `n_down` days of `-down`
    return, applied multiplicatively from `base`. For a two-point sample
    {a, b} with counts (n1, n2), the ddof=1 sample std is
    sqrt(n1*n2/(n*(n-1))) * |a - b| -- a factor shared by any two candidates
    using the same (n_up, n_down) split, so std_TLT / std_DBC = |a-b|_TLT /
    |a-b|_DBC exactly, independent of that shared factor."""
    rets = np.concatenate([np.full(n_up, up), np.full(n_down, -down)])
    prices = base * np.cumprod(1.0 + rets)
    return np.concatenate([[base], prices])


def _d2_frame() -> tuple[pd.DataFrame, pd.Timestamp]:
    flat_len = 280  # > 12 months of trading days, all flat at 100.0
    index = pd.bdate_range("2016-01-04", periods=flat_len + 63)
    asof = index[-1]
    flat = np.full(flat_len, 100.0)

    # TLT: 32 days of +0.02 then 31 days of -0.02 (|a-b| = 0.04).
    tlt_tail = _two_point_series(100.0, 0.02, 0.02, 32, 31)[1:]
    # DBC: 32 days of +0.01 then 31 days of -0.01 (|a-b| = 0.02, half of TLT's
    # -> std_TLT = 2 * std_DBC exactly, by the shared-factor argument above).
    dbc_tail = _two_point_series(100.0, 0.01, 0.01, 32, 31)[1:]
    assert len(tlt_tail) == 63 and len(dbc_tail) == 63

    data = {
        "TLT": np.concatenate([flat, tlt_tail]),
        "DBC": np.concatenate([flat, dbc_tail]),
        "GLD": np.full(flat_len + 63, 100.0),  # flat: 12mo return 0, tied with SHY
        "UUP": np.full(flat_len + 63, 100.0),  # flat: 12mo return 0, tied with SHY
        "SHY": np.full(flat_len + 63, 100.0),  # flat: 0% hurdle
    }
    return pd.DataFrame(data, index=index), asof


def test_d2_hand_computed_inverse_vol_weights() -> None:
    close, asof = _d2_frame()

    tlt_12m = batch.calendar_return(close, "TLT", asof, 12)
    dbc_12m = batch.calendar_return(close, "DBC", asof, 12)
    gld_12m = batch.calendar_return(close, "GLD", asof, 12)
    uup_12m = batch.calendar_return(close, "UUP", asof, 12)
    shy_12m = batch.calendar_return(close, "SHY", asof, 12)
    # TLT and DBC's tails are net positive (32 up-days at the larger
    # magnitude outweigh 31 down-days), GLD/UUP are exactly flat (tied, not
    # strictly greater than SHY's 0%).
    assert tlt_12m > 0.0
    assert dbc_12m > 0.0
    assert gld_12m == pytest.approx(0.0, abs=1e-12)
    assert uup_12m == pytest.approx(0.0, abs=1e-12)
    assert shy_12m == pytest.approx(0.0, abs=1e-12)

    weights = batch.d2_weights_fn(close, asof)
    assert set(weights) == {"TLT", "DBC"}  # GLD/UUP excluded: tied with SHY, not eligible
    # std_TLT = 2 * std_DBC by construction -> weight_TLT : weight_DBC = 1 : 2.
    assert weights["TLT"] == pytest.approx(1.0 / 3.0, abs=1e-6)
    assert weights["DBC"] == pytest.approx(2.0 / 3.0, abs=1e-6)
    _assert_long_only_sum_le_1(weights)


def test_d2_no_lookahead() -> None:
    close, asof = _d2_frame()
    baseline = batch.d2_weights_fn(close, asof)
    extra_index = pd.bdate_range(asof + pd.Timedelta(days=1), periods=10)
    crash = pd.DataFrame({sym: np.full(10, 1.0) for sym in close.columns}, index=extra_index)
    extended = pd.concat([close, crash])
    perturbed = batch.d2_weights_fn(extended, asof)
    assert perturbed == baseline


def test_d2_all_ineligible_returns_empty() -> None:
    close, asof = _d2_frame()
    # Force every defensive asset flat (tied with SHY) -> nothing eligible.
    flat_close = close.copy()
    flat_close["TLT"] = 100.0
    flat_close["DBC"] = 100.0
    assert batch.d2_weights_fn(flat_close, asof) == {}


def test_d2_warmup_returns_empty() -> None:
    close, _asof = _d2_frame()
    too_early = close.index[5]
    assert batch.d2_weights_fn(close, too_early) == {}


# --- trailing_vol / calendar_return: basic shape and no-lookahead sanity. ---


def test_trailing_vol_insufficient_history_is_nan() -> None:
    close, _asof = _d2_frame()
    early = close.index[10]
    assert np.isnan(batch.trailing_vol(close, "TLT", early, 63))


def test_calendar_return_missing_symbol_is_nan() -> None:
    close, asof = _d1_frame()
    assert np.isnan(batch.calendar_return(close, "NOPE", asof, 12))


def test_candidates_export_expected_ids_and_universe() -> None:
    ids = [c.id for c in batch.CANDIDATES]
    assert ids == ["D1", "D2"]
    by_id = {c.id: c for c in batch.CANDIDATES}
    assert by_id["D1"].freq == "M"
    assert by_id["D2"].freq == "M"
    assert set(by_id["D1"].universe) == {"TLT", "GLD", "DBC", "UUP", "SPY"}
    assert set(by_id["D2"].universe) == {"TLT", "GLD", "DBC", "UUP"}
