from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import run_h20260929_37_ls_short_unlocked as mod  # noqa: E402


def synthetic_panel(n: int = 400, seed: int = 0) -> mod.Panel:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    cols = sorted(
        {s for pair in mod.PAIRS for s in pair}
        | set(mod.SECTORS)
        | {"SPY", "SHY", "XLK", "SOXX"}
        | set(mod.CONSTITUENTS["XLK"])
        | set(mod.CONSTITUENTS["SOXX"])
    )
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, len(cols))), axis=0)),
        index=idx,
        columns=cols,
    )
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, (n, len(cols))))
    spread = pd.DataFrame(0.001, index=idx, columns=cols)
    dv21 = pd.DataFrame(1e8, index=idx, columns=cols)
    false = pd.DataFrame(False, index=idx, columns=cols)
    return mod.Panel(close, open_, spread, dv21, false.copy(), false.copy(), {})


def test_simulate_matches_salvage_simulate_for_signed_weights():
    p = synthetic_panel(120)
    cols = ["AAPL", "MSFT", "SHY"]
    w = np.zeros((len(p.close), 3))
    w[10:40, 0], w[10:40, 1] = 0.5, -0.5
    w[40:80, 0], w[40:80, 1] = -0.3, 0.6
    lo, lc = mod.salvage.legs(p.close[cols], p.open[cols])
    wdf = pd.DataFrame(w, index=p.close.index, columns=cols)
    ref, ref_turn = mod.salvage.simulate(wdf, lo, lc, np.ones(len(wdf)), 10.0)
    fracs = {"flat10": np.full(w.shape, 10.0 / 1e4)}
    sim = mod.simulate_signed(w, lo.to_numpy(), lc.to_numpy(), fracs, np.zeros(w.shape))
    np.testing.assert_allclose(sim["gross"] - sim["cost"]["flat10"], ref.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(sim["turn"], ref_turn.to_numpy(), atol=1e-12)


def test_borrow_charged_only_on_shorts_at_row_rate():
    w = np.zeros((6, 2))
    w[1:5, 0], w[1:5, 1] = 1.0, -0.5
    lo = np.zeros((6, 2))
    lc = np.zeros((6, 2))
    rate = np.full((6, 2), 0.02)
    fr = {k: np.zeros((6, 2)) for k in ("flat10", "flat20", "main", "stress")}
    sim = mod.simulate_signed(w, lo, lc, fr, rate)
    np.testing.assert_allclose(sim["borrow"][1:5], 0.5 * 0.02 / 252)
    assert sim["borrow"][0] == 0 and sim["borrow"][5] == 0
    s = mod.series_variants(sim, pd.RangeIndex(6))
    np.testing.assert_allclose(s["ret_10_before"] - s["ret_10_after"], sim["borrow"])


def test_borrow_rate_tiers_and_etf_override():
    dv = pd.DataFrame({"AAA": [1e8, 2e7, 1e6], "XLK": [1e6, 1e6, 1e6]})
    r = mod.borrow_rates(dv)
    assert list(r["AAA"]) == [mod.BORROW_HI, mod.BORROW_LO, mod.BORROW_LO]
    assert list(r["XLK"]) == [mod.BORROW_ETF] * 3


def test_pair_book_is_dollar_neutral_long_cheap_short_rich_and_flip_inverts():
    ctx = mod.make_ctx(synthetic_panel())
    z = np.full(len(mod.PAIRS), np.nan)
    z[0] = -1.5  # GOOG cheap vs GOOGL -> long GOOG, short GOOGL
    z[1] = 2.0  # FOX rich vs FOXA -> short FOX, long FOXA
    vec = mod.pair_book(ctx, z, 100, 0.0, False, None)
    ix = ctx.col_ix
    n = len(mod.PAIRS)
    assert vec.sum() == pytest.approx(0.0)
    assert vec[ix["GOOG"]] == pytest.approx(1 / n) and vec[ix["GOOGL"]] == pytest.approx(-1 / n)
    assert vec[ix["FOX"]] == pytest.approx(-1 / n) and vec[ix["FOXA"]] == pytest.approx(1 / n)
    mirror = mod.pair_book(ctx, z, 100, 0.0, True, None)
    np.testing.assert_allclose(mirror, -vec)


def test_pair_threshold_and_short_eligibility_skip_the_pair():
    p = synthetic_panel()
    p.dv21["MKC.V"] = 1e5  # illiquid class cannot be the short leg
    ctx = mod.make_ctx(p)
    z = np.full(len(mod.PAIRS), np.nan)
    z[8] = -2.0  # MKC cheap, MKC.V rich -> short MKC.V -> ineligible -> flat
    assert np.allclose(mod.pair_book(ctx, z, 100, 0.0, False, None), 0.0)
    z[8] = 2.0  # MKC rich -> short MKC (liquid), long MKC.V (allowed as long)
    vec = mod.pair_book(ctx, z, 100, 0.0, False, None)
    assert vec[ctx.col_ix["MKC.V"]] > 0 and vec[ctx.col_ix["MKC"]] < 0
    z[8] = 0.5
    assert np.allclose(mod.pair_book(ctx, z, 100, 1.0, False, None), 0.0)


def test_pair_random_sign_keeps_neutrality_and_uses_seeded_rng():
    ctx = mod.make_ctx(synthetic_panel())
    z = np.full(len(mod.PAIRS), 1.2)
    a = mod.pair_book(ctx, z, 100, 1.0, False, np.random.default_rng(3))
    b = mod.pair_book(ctx, z, 100, 1.0, False, np.random.default_rng(3))
    np.testing.assert_allclose(a, b)
    assert a.sum() == pytest.approx(0.0)


def test_event_book_long_laggards_short_etf_hold_and_no_overlap():
    p = synthetic_panel()
    ctx = mod.make_ctx(p)
    cand = mod.Cand("t", "B", dict(etf="XLK", k=3, hold=5))
    trig = np.zeros(ctx.n, dtype=bool)
    trig[50] = trig[52] = trig[70] = True  # 52 lands inside the 50 hold -> skipped
    w = mod.weights_B(ctx, cand, trig, 0)
    ie = ctx.col_ix["XLK"]
    assert np.all(w[51:56, ie] == -1.0) and np.all(w[:51] == 0) and np.all(w[56:71] == 0)
    assert np.all(w[71:76, ie] == -1.0)
    row = w[51]
    longs = np.flatnonzero(row > 0)
    assert len(longs) == 3 and row[longs].sum() == pytest.approx(1.0)
    rel = ctx.ret1[50] - ctx.ret1[50, ie]
    names = [ctx.col_ix[s] for s in mod.CONSTITUENTS["XLK"]]
    expect = sorted(names, key=lambda j: rel[j])[:3]
    assert sorted(longs) == sorted(expect)
    delayed = mod.weights_B(ctx, cand, trig, 2)
    assert np.all(delayed[53:58, ie] == -1.0) and np.all(delayed[:53] == 0)
    mirror = mod.weights_B(ctx, cand, trig, 0, flip=True)
    np.testing.assert_allclose(mirror, -w)


def test_calendar_book_windows_and_mirror():
    p = synthetic_panel(700)
    ctx = mod.make_ctx(p)
    cand = mod.Cand("t", "C", dict(kind="LS", k=3))
    w = mod.weights_C_calendar(ctx, cand)
    me = mod.month_end_positions(p.close.index)
    i = me[-6]
    assert i > 300
    b = w[i + 1]
    assert np.count_nonzero(b) == 6 and b.sum() == pytest.approx(0.0)
    np.testing.assert_allclose(w[i + 2], -b)
    np.testing.assert_allclose(w[i + 3], -b)
    assert np.allclose(w[i + 4], 0.0)
    prev_book = w[me[-7] + 1]  # ranking of the previous month-end
    np.testing.assert_allclose(w[i - 10], prev_book)
    np.testing.assert_allclose(w[i - 5], prev_book)
    assert np.allclose(w[i - 4], 0.0)
    mirror = mod.weights_C_calendar(ctx, cand, flip=True)
    np.testing.assert_allclose(mirror, -w)
    mn = mod.weights_C_calendar(ctx, mod.Cand("t", "C", dict(kind="MN", k=2)))
    row = mn[i + 1]
    assert row[ctx.col_ix["SPY"]] == pytest.approx(-1.0) and row.sum() == pytest.approx(0.0)


def test_tier_logic_boundaries():
    keep = mod.tier_from(1.2, 0.7, 0.05, 0.05, 0.0, 0.0, 0.5)
    assert keep["k1"] and keep["tier"] == "keep"
    strong = mod.tier_from(1.2, 0.7, 0.05, 0.05, 0.11, 0.12, 0.5)
    assert strong["k2"] and strong["tier"] == "keep_strong"
    k2_only = mod.tier_from(0.3, 0.2, -0.1, -0.1, 0.06, 0.05, None)
    assert k2_only["k2"] and not k2_only["k1"] and k2_only["tier"] == "keep"
    watch = mod.tier_from(1.3, 0.3, 0.05, 0.05, 0.0, 0.0, 0.5)
    assert watch["tier"] == "watch_recent" and any(
        "K1 stress" in f for f in watch["failed_conditions"]
    )
    placebo = mod.tier_from(1.2, 0.7, 0.05, 0.05, 0.0, 0.0, 1.25)
    assert placebo["tier"] == "reject_placebo"
    neg = mod.tier_from(-0.2, 0.1, -0.1, 0.0, -0.3, -0.2, 0.3)
    assert neg["tier"] == "reject" and neg["failed_conditions"]
    no_cagr = mod.tier_from(1.5, 0.9, 0.05, -0.01, 0.0, 0.0, None)
    assert not no_cagr["k1"] and no_cagr["tier"] == "watch_recent"


def test_candidate_list_is_the_preregistered_sixteen():
    assert len(mod.CANDIDATES) == 16
    assert len({c.id for c in mod.CANDIDATES}) == 16
    assert {c.direction for c in mod.CANDIDATES} == {"A", "B", "C"}
    assert all(("BRK.A", "BRK.B") != pair for pair in mod.PAIRS)
    assert mod.N_TRIALS == 22
