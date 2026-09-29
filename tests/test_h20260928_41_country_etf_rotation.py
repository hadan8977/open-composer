"""Synthetic-data tests for `scripts/screen_batches/h20260928_41_country_etf_
rotation.py`. No real market data is read (constructing `SPECS` only calls
`h20260928_40_equity_etf_menus.make_rotation_fn`, which builds a closure --
it does not touch data until called with a synthetic `close` frame here).

Covers: candidate ids/count match the preregistered manifest (8); the reused
`make_rotation_fn` mechanism (top-N by lookback momentum, absolute-momentum
filter vs SHY, equal-weight survivors, long-only/sum<=1/universe-only
contract); rule direction (the higher-lookback-return ticker is picked, and
nothing is picked when every candidate trails SHY); no look-ahead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_41_country_etf_rotation as batch  # noqa: E402


def _close_frame(index: pd.DatetimeIndex, prices: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(prices, index=index)


def test_specs_count_and_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260928_41_country_etf_rotation"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(spec["id"] for spec in batch.SPECS)
    assert module_ids == manifest_ids
    assert len(module_ids) == 8


def test_specs_cover_expected_grid() -> None:
    ids = {spec["id"] for spec in batch.SPECS}
    expected = {
        f"COUNTRY_L{lb}_N{tn}_{rb}" for lb in (63, 252) for tn in (1, 2) for rb in ("MO", "WK")
    }
    assert ids == expected


def test_specs_universe_is_country_menu_and_freq_is_monthly_or_weekly() -> None:
    for spec in batch.SPECS:
        assert tuple(spec["universe"]) == batch.COUNTRY_MENU
        assert spec["freq"] in ("M", "W")
        assert callable(spec["fn"])


def test_rotation_picks_higher_momentum_ticker_and_respects_absolute_filter() -> None:
    index = pd.bdate_range("2024-01-01", periods=80)
    # EWJ trends up strongly, EWG trends down, SHY (cash) flat -> EWJ should
    # be picked over EWG at top_n=1, and it must beat SHY's own (~0) score.
    ewj = [100.0 * (1.01**i) for i in range(80)]
    ewg = [100.0 * (0.995**i) for i in range(80)]
    shy = [100.0] * 80
    prices = {"EWJ": ewj, "EWG": ewg, "SHY": shy}
    for sym in batch.COUNTRY_MENU:
        if sym not in prices:
            prices[sym] = [float("nan")] * 80
    close = _close_frame(index, prices)
    fn = batch.t40.make_rotation_fn(batch.COUNTRY_MENU, 63, 1)
    asof = index[70]
    weights = fn(close, asof)
    assert weights == {"EWJ": 1.0}


def test_rotation_returns_empty_when_nothing_beats_cash() -> None:
    index = pd.bdate_range("2024-01-01", periods=80)
    # Every country ETF trends down; SHY (cash) is flat, so nothing should
    # clear the absolute-momentum filter.
    down = [100.0 * (0.995**i) for i in range(80)]
    prices = {sym: list(down) for sym in batch.COUNTRY_MENU}
    prices["SHY"] = [100.0] * 80
    close = _close_frame(index, prices)
    fn = batch.t40.make_rotation_fn(batch.COUNTRY_MENU, 63, 1)
    weights = fn(close, index[70])
    assert weights == {}


def test_no_lookahead_on_future_price_history() -> None:
    index = pd.bdate_range("2024-01-01", periods=80)
    base_ewj = [100.0 * (1.01**i) for i in range(80)]
    prices_a = {sym: list(base_ewj) for sym in batch.COUNTRY_MENU}
    prices_a["SHY"] = [100.0] * 80
    prices_b = {k: list(v) for k, v in prices_a.items()}
    decided_at = index[70]
    decided_pos = index.get_loc(decided_at)
    # Mutate every symbol's price strictly after `decided_at`.
    for sym in prices_b:
        for i in range(decided_pos + 1, 80):
            prices_b[sym][i] = prices_b[sym][i] * 3.0 + 17.0
    close_a = _close_frame(index, prices_a)
    close_b = _close_frame(index, prices_b)
    fn = batch.t40.make_rotation_fn(batch.COUNTRY_MENU, 63, 1)
    assert fn(close_a, decided_at) == fn(close_b, decided_at)
