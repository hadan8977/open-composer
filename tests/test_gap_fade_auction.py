"""Unit tests for scripts/run_t20260930_11_gap_fade_auction.py pure logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import run_t20260930_11_gap_fade_auction as m


def _trade(t: str, x: str, p: float, c: list[str], s: float = 100.0) -> dict:
    return {"t": t, "x": x, "p": p, "s": s, "c": c, "z": "C"}


def test_official_open_prefers_q_over_o() -> None:
    trades = [
        _trade("2026-03-02T14:30:00.1Z", "Q", 10.10, ["O"]),
        _trade("2026-03-02T14:30:00.2Z", "Q", 10.00, ["Q"]),
    ]
    res = m.official_open(trades, "C")
    assert res is not None
    assert res["source"] == "Q_listing"
    assert res["p"] == 10.00


def test_official_open_falls_back_to_listing_o() -> None:
    trades = [
        _trade("2026-03-02T14:30:00.1Z", "P", 10.20, ["O"]),  # not the listing exchange
        _trade("2026-03-02T14:30:00.3Z", "Q", 10.10, ["O"]),
    ]
    res = m.official_open(trades, "C")
    assert res is not None
    assert res["source"] == "O_listing"
    assert res["p"] == 10.10


def test_official_open_q_from_other_exchange_is_tagged() -> None:
    trades = [_trade("2026-03-02T14:30:00.1Z", "P", 10.05, ["Q"])]
    res = m.official_open(trades, "C")
    assert res is not None
    assert res["source"] == "Q_other"


def test_official_close_prefers_m_over_6() -> None:
    trades = [
        _trade("2026-03-02T21:00:00.5Z", "N", 20.05, ["6"]),
        _trade("2026-03-02T21:00:00.6Z", "N", 20.00, ["M"]),
    ]
    res = m.official_close(trades, "A")
    assert res is not None
    assert res["source"] == "M_listing"
    assert res["p"] == 20.00


def test_official_close_falls_back_to_listing_6() -> None:
    trades = [
        _trade("2026-03-02T21:00:00.5Z", "N", 20.05, ["6"]),
        _trade("2026-03-02T21:00:00.7Z", "Q", 20.07, ["6"]),
    ]
    res = m.official_close(trades, "A")
    assert res is not None
    assert res["source"] == "6_listing"
    assert res["p"] == 20.05


def test_official_missing_when_no_codes() -> None:
    trades = [_trade("2026-03-02T14:31:00Z", "Q", 10.0, ["@"])]
    assert m.official_open(trades, "C") is None
    assert m.official_close(trades, "C") is None
    assert m.official_open([], "C") is None


def test_delta_sign_long_and_short() -> None:
    # official open is lower and official close is higher than the bars
    long = m.delta_components(1, o_bar=100.0, c_bar=101.0, o_off=99.0, c_off=102.0)
    assert long["r_bar"] == pytest.approx(0.01)
    assert long["r_off"] == pytest.approx(102.0 / 99.0 - 1.0)
    assert long["delta"] == pytest.approx(long["r_off"] - long["r_bar"])
    assert long["delta_open"] == pytest.approx(100.0 / 99.0 - 1.0)
    assert long["delta_close"] == pytest.approx(102.0 / 101.0 - 1.0)
    short = m.delta_components(-1, o_bar=100.0, c_bar=101.0, o_off=99.0, c_off=102.0)
    assert short["r_bar"] == pytest.approx(-0.01)
    assert short["delta"] == pytest.approx(-long["delta"])
    assert short["delta_open"] == pytest.approx(-long["delta_open"])
    assert short["delta_close"] == pytest.approx(-long["delta_close"])


def test_delta_parts_add_to_first_order() -> None:
    c = m.delta_components(1, 50.0, 51.0, 50.02, 51.03)
    assert c["delta"] == pytest.approx(c["delta_open"] + c["delta_close"], abs=1e-5)


def test_direction_and_tier() -> None:
    assert m.direction("long") == 1
    assert m.direction("short") == -1
    with pytest.raises(ValueError):
        m.direction("flat")
    assert m.tier_of(4.9e6) is None
    assert m.tier_of(5e6) == "T1"
    assert m.tier_of(20e6) == "T2"
    assert m.tier_of(99.9e6) == "T2"
    assert m.tier_of(100e6) == "T3"


def _picks(n_dates: int = 60) -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2024-02-01", periods=n_dates)
    rng = np.random.default_rng(1)
    for d in dates:
        for tier in ("T1", "T2", "T3"):
            for leg in ("long", "short"):
                for j in range(3):
                    rows.append(
                        {
                            "date": d,
                            "symbol": f"{tier}{leg[0]}{j}_{rng.integers(0, 99)}",
                            "leg": leg,
                            "tier": tier,
                        }
                    )
    return pd.DataFrame(rows)


def test_stratified_sample_counts_and_no_duplicates() -> None:
    picks = _picks()
    s = m.stratified_sample(picks, seed=m.SEED)
    counts = s.groupby(["tier", "leg"]).size()
    # 60 dates per cell: T1 needs 40 (one per date); T2/T3 need 80 > 60 dates, so 20
    # extra rows are filled from unused rows of the same cell
    assert counts[("T1", "long")] == 40
    assert counts[("T2", "long")] == 80
    assert counts[("T3", "short")] == 80
    assert s["sample_id"].is_unique
    assert not s.duplicated(["symbol", "date"]).any()


def test_stratified_sample_takes_whole_small_cell() -> None:
    picks = _picks(10)  # 30 rows per cell, fewer than any requested n
    s = m.stratified_sample(picks, seed=m.SEED)
    assert len(s) == len(picks)


def test_stratified_sample_is_reproducible_and_seed_sensitive() -> None:
    picks = _picks(200)
    a = m.stratified_sample(picks, seed=m.SEED)
    b = m.stratified_sample(picks.sample(frac=1.0, random_state=3), seed=m.SEED)
    assert list(a["sample_id"]) == list(b["sample_id"])
    c = m.stratified_sample(picks, seed=m.SEED + 1)
    assert list(a["sample_id"]) != list(c["sample_id"])
    assert len(a) == 400


def test_stratified_sample_dates_distinct_within_cell() -> None:
    picks = _picks(200)  # 200 dates >= 80, so one row per chosen date
    s = m.stratified_sample(picks, seed=m.SEED)
    for _key, g in s.groupby(["tier", "leg"]):
        assert g["date"].is_unique


def test_pooled_e_off_weights_and_legs() -> None:
    cells = {
        ("T2", "long"): (100.0, 10.0, 2.0),
        ("T3", "long"): (300.0, 20.0, -2.0),
        ("T2", "short"): (200.0, 0.0, 0.0),
        ("T3", "short"): (200.0, 4.0, 0.0),
    }
    long_leg = (100 * 12.0 + 300 * 18.0) / 400.0
    short_leg = (200 * 0.0 + 200 * 4.0) / 400.0
    assert m.pooled_e_off(cells) == pytest.approx((long_leg + short_leg) / 2.0)


def test_merge_top_k_matches_global_top_k() -> None:
    rng = np.random.default_rng(5)
    rows = []
    for d in pd.bdate_range("2024-03-01", periods=4):
        for i in range(60):
            for leg in ("long", "short"):
                rows.append(
                    {"date": d, "symbol": f"S{i:03d}", "leg": leg, "z": float(rng.normal())}
                )
    full = pd.DataFrame(rows)
    # emulate three chunks each keeping its own top-K, then merge
    parts = []
    for lo, hi in ((0, 20), (20, 40), (40, 60)):
        sym = [f"S{i:03d}" for i in range(lo, hi)]
        sub = full[full["symbol"].isin(sym)]
        keep = []
        for leg, asc in (("long", True), ("short", False)):
            x = sub[sub["leg"] == leg].sort_values(["date", "symbol"], kind="stable")
            x = x.assign(rank=x.groupby("date")["z"].rank(method="first", ascending=asc))
            keep.append(x[x["rank"] <= m.K_LEG].drop(columns="rank"))
        parts.append(pd.concat(keep))
    merged = m.merge_top_k(pd.concat(parts, ignore_index=True))
    direct = m.merge_top_k(full)
    key = ["date", "leg", "symbol"]
    assert merged[key].equals(direct[key])


def test_et_to_utc_handles_dst() -> None:
    assert m.et_to_utc("2026-01-15", 9, 30) == "2026-01-15T14:30:00Z"
    assert m.et_to_utc("2026-07-15", 9, 30) == "2026-07-15T13:30:00Z"
    assert m.et_to_utc("2026-07-15", 16, 0) == "2026-07-15T20:00:00Z"
