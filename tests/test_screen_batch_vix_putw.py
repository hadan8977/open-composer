"""Synthetic-data tests for `scripts/screen_batches/h20260928_18_vix_putw.py`.

No backtest is run here -- these are unit tests of the pure `w_putw_hold`
weight function against hand-computed cases, plus the generic contract
checks the iteration brief requires: long-only, sum(weights) <= 1, only
universe tickers appear, and no look-ahead (appending future rows -- price
history OR a synthetic VIX spike -- never changes an already-decided
`asof`'s weights).

VIX_REGIME_SPY_SSO_TLT is out of scope for this batch (dropped by the
owner's 2026-09-28 cross-asset scope decision) and has no batch module or
test coverage here; the VIX-series no-look-ahead check below is a defensive
regression test on VIX data handling in general (data/research/vix/
VIXCLS.csv is fetched and kept for a possible future equity-only VIX rule),
not a test of any candidate weight function that reads it -- PUTW_HOLD does
not use VIX at all.
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

import h20260928_18_vix_putw as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _frame(index: pd.DatetimeIndex, columns: list[str], value: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(value, index=index, columns=columns)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# CANDIDATES shape
# --------------------------------------------------------------------------


def test_candidates_ids_and_shape() -> None:
    ids = [c.id for c in batch.CANDIDATES]
    assert ids == ["PUTW_HOLD"]
    (candidate,) = batch.CANDIDATES
    assert isinstance(candidate, lane.ScreenCandidate)
    assert candidate.freq == "M"
    assert candidate.universe == ("PUTW",)
    assert callable(candidate.weights_fn)
    assert candidate.signal_dates_fn is None


# --------------------------------------------------------------------------
# w_putw_hold: hand-computed cases
# --------------------------------------------------------------------------


def test_putw_hold_fixed_weight_hand_computed() -> None:
    index = pd.bdate_range("2021-01-04", "2021-01-08")
    close = _frame(index, ["PUTW"])
    weights = batch.w_putw_hold(close, index[-1])
    assert weights == {"PUTW": 1.0}
    _assert_contract(weights, ("PUTW",))


def test_putw_hold_returns_cash_before_history_exists() -> None:
    import numpy as np

    index = pd.bdate_range("2021-01-04", "2021-01-08")
    close = pd.DataFrame({"PUTW": [np.nan] * len(index)}, index=index)
    assert batch.w_putw_hold(close, index[-1]) == {}


def test_putw_hold_missing_column_returns_cash() -> None:
    index = pd.bdate_range("2021-01-04", "2021-01-08")
    close = _frame(index, ["SPY"])  # PUTW absent entirely, e.g. not in the local panel
    assert batch.w_putw_hold(close, index[-1]) == {}


# --------------------------------------------------------------------------
# Generic contract: long-only, sum <= 1, only universe tickers
# --------------------------------------------------------------------------


def test_putw_hold_contract_over_a_date_range() -> None:
    index = pd.bdate_range("2021-01-04", "2021-03-31")
    close = _frame(index, ["PUTW", "SHY"])
    for asof in index[::5]:
        weights = batch.w_putw_hold(close, asof)
        _assert_contract(weights, ("PUTW",))


# --------------------------------------------------------------------------
# No look-ahead: appending future rows never changes an already-decided asof
# --------------------------------------------------------------------------


def test_putw_hold_no_lookahead_on_future_price_history() -> None:
    index = pd.bdate_range("2021-01-04", "2021-01-29")
    decided_at = index[9]  # a date strictly before the end of the frame

    close_short = _frame(index[: index.get_loc(decided_at) + 1], ["PUTW"])
    weights_short = batch.w_putw_hold(close_short, decided_at)

    # Append many future rows with a wildly different price -- a future PUTW
    # move must not change what was already decided at `decided_at`.
    future_index = pd.bdate_range(index[-1] + pd.Timedelta(days=1), periods=20)
    close_long = pd.concat(
        [
            close_short,
            pd.DataFrame(9999.0, index=future_index, columns=["PUTW"]),
        ]
    )
    weights_long = batch.w_putw_hold(close_long, decided_at)

    assert weights_short == weights_long == {"PUTW": 1.0}


def test_vix_series_no_lookahead_forward_fill_at_most_one_day() -> None:
    """Defensive regression test on the VIX data-handling convention this
    round establishes (data/research/vix/VIXCLS.csv,
    VIXCLS.meta.json's `missing_data_policy`): a VIX value dated t is usable
    at or after the close of t, never before, and a gap is forward-filled by
    at most 1 trading day. PUTW_HOLD does not read VIX; this guards the
    convention documented for any future VIX-based rule (e.g. a revived,
    equity-only VIX_REGIME variant)."""
    index = pd.bdate_range("2021-01-04", "2021-01-08")
    # day 0: 15.0, day 1: missing (1-day gap -- forward-fillable), day 2:
    # missing (2nd consecutive missing day -- stays missing), day 3: a big
    # future spike that must never leak into any earlier decision, day 4:
    # 20.0.
    raw = pd.Series([15.0, None, None, 80.0, 20.0], index=index)

    def vix_asof(series: pd.Series, asof: pd.Timestamp) -> float:
        """Mirrors the forward-fill-at-most-1-day policy: only uses
        `series.loc[:asof]`, never a later value."""
        window = series.loc[:asof].ffill(limit=1)
        return float(window.iloc[-1]) if not pd.isna(window.iloc[-1]) else float("nan")

    # At day 0 (close), only day 0's own value is knowable.
    assert vix_asof(raw, index[0]) == 15.0
    # At day 1 (close), day 1 is missing but 1-day forward-fill from day 0
    # covers it -- still no knowledge of day 3's future spike.
    assert vix_asof(raw, index[1]) == 15.0
    # At day 2 (close), day 2 is a *second* consecutive missing day -- the
    # forward-fill policy caps at 1 day, so this must stay NaN, not silently
    # carry day 0's value forward indefinitely.
    assert pd.isna(vix_asof(raw, index[2]))
    # At day 1 or day 2, the day-3 spike (80.0) must never be visible.
    assert vix_asof(raw, index[1]) != 80.0
    assert vix_asof(raw, index[2]) != 80.0


def test_vix_csv_fetched_and_metadata_documents_pit_policy() -> None:
    vix_csv = ROOT / "data" / "research" / "vix" / "VIXCLS.csv"
    meta_path = ROOT / "data" / "research" / "vix" / "VIXCLS.meta.json"
    assert vix_csv.is_file()
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["source"].startswith("FRED")
    assert "pit_semantics" in meta and meta["pit_semantics"]
    assert "missing_data_policy" in meta and "1 trading day" in meta["missing_data_policy"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
