# ruff: noqa: E501, E741
"""Synthetic tests for scripts/p1_stage0_decay.py (T-20261005-01).  No market data is read."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import costs
from open_composer.research.equity_book import signals as sg
from open_composer.research.equity_book.evaluate import newey_west_t

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load("p1_stage0_decay_mod", "scripts/p1_stage0_decay.py")


# --------------------------------------------------------------------------- small helpers


def _toy_grid(T=120, N=60, seed=1):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0, 0.02, (T, N))
    C = 20.0 * np.exp(np.cumsum(ret, axis=0))
    O = C * (1.0 + rng.normal(0, 0.003, (T, N)))
    spy_c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, T)))
    spy_o = spy_c * (1.0 + rng.normal(0, 0.002, T))
    ind = (np.arange(N) % 4).astype(np.int16)
    ctx = SimpleNamespace(
        C=C,
        O=O,
        spy_c=spy_c,
        spy_o=spy_o,
        beta=np.ones((T, N)),
        T=T,
        N=N,
        ind=np.tile(ind, (T, 1)),
        se=np.ones((T, N), dtype=bool),
        i0=0,
        i1=T - 3,
    )
    return ctx


def _toy_rows(ctx):
    di = np.repeat(np.arange(ctx.T), ctx.N).astype(np.int64)
    si = np.tile(np.arange(ctx.N), ctx.T).astype(np.int64)
    ind = ctx.ind[di, si].astype(np.int64)
    return di, si, ind


def _toy_pathctx(ctx, e, hs=None, impk=None):
    T, N = ctx.T, ctx.N
    ok = np.ones((T, N), dtype=bool)
    ok[-1] = False
    nT = ctx.i1 - ctx.i0 + 1
    return SimpleNamespace(
        hs={"close": np.zeros((T, N)) if hs is None else hs},
        e={"close": e},
        ok={"close": ok},
        impk=np.zeros((T, N)) if impk is None else impk,
        i0=ctx.i0,
        i1=ctx.i1,
        nT=nT,
        N=N,
        dates=pd.bdate_range("2020-01-01", periods=T)[ctx.i0 : ctx.i1 + 1],
        wmasks={"recent": np.ones(nT, dtype=bool)},
    )


# (a) lag alignment -----------------------------------------------------------------------


def test_lag_alignment_and_no_lookahead():
    ctx = _toy_grid()
    di, si, ind = _toy_rows(ctx)
    E = m.lag_targets(ctx, di, si, ind)
    cfgm = SimpleNamespace(min_names=10)
    T, N = ctx.T, ctx.N
    e_dense = np.zeros((T, N))
    e_dense[di, si] = np.where(np.isfinite(E[:, 1]), E[:, 1], 0.0)
    P = _toy_pathctx(ctx, e_dense)

    def run(col):
        S = np.full((T, N), np.nan)
        S[di, si] = E[:, col]
        ws = m.wstar_from_dense(S, ctx, cfgm)
        arr = m.run_path(ws, P, "close", "kappa", 1.0)
        return S, arr

    # IC of a score equal to e(t, 2) is 1 at lag 2, ~0 at lag 1 (rank IC, per date)
    S2, arr2 = run(1)
    t = 40
    sl = slice(t * N, (t + 1) * N)
    zx, fx = m.zrank(E[sl, 1:2])
    ze, fe = m.zrank(E[sl][:, :3])
    ic = m.rank_ic(zx, fx, ze, fe, 10)[0]
    assert ic[1] == pytest.approx(1.0, abs=1e-12)
    assert abs(ic[0]) < 0.4 and abs(ic[2]) < 0.4
    # the MOC portfolio built from e(t,2) earns it (strongly positive); built from e(t,1) it does not
    S1, arr1 = run(0)
    g2 = np.nanmean(arr2["gross"])
    g1 = np.nanmean(arr1["gross"])
    assert g2 > 0.02
    assert abs(g1) < 0.15 * g2


# (b) kappa recursion and turnover on a hand-computed example ----------------------------------


def test_kappa_recursion_and_turnover_hand_example():
    ctx = SimpleNamespace(T=6, N=2, i0=0, i1=2)
    e = np.zeros((6, 2))
    P = _toy_pathctx(ctx, e)
    ws = m.WStar(
        [np.array([0, 1])] * 3,
        [np.array([1.0, -1.0]), np.array([-1.0, 1.0]), np.array([1.0, -1.0])],
        np.array([True, True, True]),
    )
    arr = m.run_path(ws, P, "close", "kappa", 0.5)
    # w0=[.5,-.5], w1=[-.25,.25], w2=[.375,-.375]
    assert arr["to"].tolist() == pytest.approx([1.0, 1.5, 1.25])
    assert arr["expo"].tolist() == pytest.approx([1.0, 0.5, 0.75])
    # full rebalance every 2 sessions, offset 0: trades on days 0 and 2 only
    arr = m.run_path(ws, P, "close", "reb", 2, 0)
    assert arr["to"].tolist() == pytest.approx([2.0, 0.0, 0.0])


# (c) per-name cost -----------------------------------------------------------------------------


def test_cost_per_name_and_missing_inputs():
    ctx = SimpleNamespace(T=4, N=1, i0=0, i1=1)
    model = costs.load_model()
    hs_val = float(costs.half_spread_bp(20.0, 1e7, 0.02, 2024, "close", model))
    imp = float(costs.impact_bp(1e6 * 1.0, 1e7, 0.02))
    hs = np.full((4, 1), hs_val)
    P = _toy_pathctx(ctx, np.zeros((4, 1)), hs=hs, impk=np.full((4, 1), imp))
    ws = m.WStar([np.array([0])] * 2, [np.array([1.0]), np.array([1.0])], np.array([True, True]))
    arr = m.run_path(ws, P, "close", "kappa", 1.0)
    assert arr["tc"][0] == pytest.approx((hs_val + imp + 0.5) / 1e4)
    assert arr["tc"][1] == 0.0
    # square-root law: a 0.25 trade costs 0.25 x (hs + impact_bp(0.25 x $1M) + fee)
    arr = m.run_path(ws, P, "close", "kappa", 0.25)
    imp_q = float(costs.impact_bp(0.25e6, 1e7, 0.02))
    assert arr["tc"][0] == pytest.approx(0.25 * (hs_val + 0.5) / 1e4 + 0.25 * imp_q / 1e4)
    # missing cost inputs: 40 bp half spread and no impact
    grid = m.cost_grid(
        np.array([[np.nan]]), np.array([[1e7]]), np.array([[0.02]]), np.array([[2024]]), "close"
    )
    assert grid[0, 0] == 40.0
    P2 = _toy_pathctx(ctx, np.zeros((4, 1)), hs=np.full((4, 1), 40.0))
    arr = m.run_path(ws, P2, "close", "kappa", 1.0)
    assert arr["tc"][0] == pytest.approx((40.0 + 0.5) / 1e4)


# (d) half lives --------------------------------------------------------------------------------


def test_half_lives_on_exponential_curve():
    lam, a = 0.1, 0.01
    means = np.zeros(m.NTGT)
    means[0] = 0.02
    j = np.arange(2, 23)
    means[1:22] = a * np.exp(-lam * (j - 2))
    assert m.half_life_exp(means) == pytest.approx(math.log(2) / lam, abs=1e-6)
    cum = np.cumsum(means[1:22])
    expect = int(np.flatnonzero(cum >= 0.5 * cum[-1])[0]) + 1
    assert m.half_life_np(means) == expect
    neg = means.copy()
    neg[1:22] = -means[1:22]
    assert math.isnan(m.half_life_np(neg)) and math.isnan(m.half_life_exp(neg))


# (e) walk-forward weights ----------------------------------------------------------------------


def test_walk_forward_ir_uses_only_ic_up_to_t_minus_2():
    rng = np.random.default_rng(3)
    x = rng.normal(0.01, 0.03, (400, 5))
    t = 300
    base = m.rolling_ir(x, 63, 50)[t]
    y = x.copy()
    y[t - 1] += 5.0
    y[t] += 5.0
    assert np.allclose(m.rolling_ir(y, 63, 50)[t], base, rtol=1e-9, atol=0)
    y = x.copy()
    y[t - 2] += 5.0
    assert not np.allclose(m.rolling_ir(y, 63, 50)[t], base)
    y = x.copy()
    y[t - 65] += 5.0  # just outside the 63 most recent rows s <= t-2
    assert np.allclose(m.rolling_ir(y, 63, 50)[t], base, rtol=1e-9, atol=0)
    # too few finite observations -> weight 0
    z = x.copy()
    z[: t - 20, 2] = np.nan
    assert m.rolling_ir(z, 63, 50)[t][2] == 0.0
    # value check against a direct computation
    win = x[t - 64 : t - 1, 0]
    assert len(win) == 63
    assert base[0] == pytest.approx(win.mean() / win.std(ddof=1))


# (f) Benjamini-Hochberg ------------------------------------------------------------------------


def test_bh_q_values():
    q = m.bh_qvalues([0.01, 0.04, 0.03, 0.005])
    assert q.tolist() == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_nw_t_matches_repo_estimator():
    rng = np.random.default_rng(5)
    x = rng.normal(0.1, 1.0, 300)
    x[1:] += 0.4 * x[:-1]
    assert m.nw_stats(x, 10)["t"] == pytest.approx(newey_west_t(x, 10))
    st = m.nw_stats(x, 10)
    assert st["se_nw"] >= st["se_iid"] * 0.5


# ------------------------------------------------------------------------------ end to end


def _write_synthetic(root: Path):
    """Two calendar years of 80 names; returns (data dir, cfg kwargs)."""
    rng = np.random.default_rng(11)
    eb = root / "eb"
    for d in ("signals", "prices", "panel", "risk", "regimes"):
        (eb / d).mkdir(parents=True)
    db = root / "daily_broad"
    db.mkdir()
    dates = pd.bdate_range("2020-09-01", "2021-03-31")
    T, N = len(dates), 80
    syms = [f"S{i:03d}" for i in range(N)] + ["XTRA"]
    ret = rng.normal(0.0003, 0.02, (T, N + 1))
    close = 20.0 * np.exp(np.cumsum(ret, axis=0))
    open_ = close * (1.0 + rng.normal(0, 0.004, close.shape))
    close[100:, 7] = np.nan  # a name that stops trading
    open_[100:, 7] = np.nan
    close[50, 9] = np.nan  # one missing session
    open_[50, 9] = np.nan
    spy_c = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, T)))
    spy_o = spy_c * (1.0 + rng.normal(0, 0.002, T))
    etf = pd.DataFrame(
        {
            "trade_date": dates,
            "symbol": "SPY",
            "open": spy_o,
            "close": spy_c,
            "volume": 1.0,
        }
    )
    etf.to_parquet(eb / "etf_daily.parquet")
    adv_rank = np.tile(rng.permutation(N) + 1, (T, 1))  # 1..N, fixed per name
    ind_code = (np.arange(N) % 6).astype("int16")
    ind_code[:3] = -1
    slow = sorted({n for v in sg.THEME_SIGNALS.values() for n in v})
    lib = ["a101_alpha016", "a101_alpha002", "g191_gtja190", "g191_gtja001", "rev_21_ind", "on252"]
    themes = list(sg.THEME_SIGNALS)
    for y in (2020, 2021):
        sel = np.flatnonzero(dates.year == y)
        recs = []
        for ti in sel:
            d = {
                "trade_date": np.repeat(dates[ti], N),
                "symbol": syms[:N],
                "ind_code": ind_code,
                "m0_n_themes": rng.choice([0, 1, 2], N, p=[0.05, 0.5, 0.45]).astype("int8"),
            }
            fut = (
                np.log(close[min(ti + 2, T - 1), :N] / close[min(ti + 1, T - 1), :N])
                if ti + 2 < T
                else 0
            )
            for n in lib + slow + ["m0_composite"] + [f"theme_{t}" for t in themes]:
                v = rng.normal(size=N) + (0.5 * np.nan_to_num(fut) / 0.02 if n == lib[0] else 0.0)
                d[n] = v.astype("float32")
                if n in lib + slow:
                    cov = rng.random(N) > 0.1
                    d[n + "_cov"] = cov
            recs.append(pd.DataFrame(d))
        df = pd.concat(recs, ignore_index=True)
        # a few non-finite values inside covered cells
        df.loc[df.sample(30, random_state=1).index, "a101_alpha002"] = np.nan
        df.to_parquet(eb / "signals" / f"{y}.parquet")
        # prices (timestamp[us] like the real files)
        pr = pd.DataFrame(
            {
                "trade_date": np.repeat(dates[sel].values, N + 1).astype("datetime64[us]"),
                "symbol": np.tile(syms, len(sel)),
                "open": open_[sel].ravel(),
                "close": close[sel].ravel(),
            }
        ).dropna(subset=["close"])
        pr.to_parquet(eb / "prices" / f"{y}.parquet")
        pn = pd.DataFrame(
            {
                "trade_date": np.repeat(dates[sel].values, N).astype("datetime64[us]"),
                "symbol": np.tile(syms[:N], len(sel)),
                "open": open_[sel][:, :N].ravel(),
                "close": close[sel][:, :N].ravel(),
                "dollar_adv_21": (1e8 / adv_rank[sel]).ravel(),
                "adv_rank": adv_rank[sel].ravel().astype("int64"),
                "vol_21": 0.02,
                "beta_252_spy": rng.normal(1.0, 0.3, len(sel) * N),
            }
        )
        pn.loc[pn.sample(40, random_state=2).index, "beta_252_spy"] = np.nan
        pn.to_parquet(eb / "panel" / f"{y}.parquet")
        rs = pd.DataFrame(
            {
                "trade_date": np.repeat(dates[sel].values, N).astype("datetime64[us]"),
                "symbol": np.tile(syms[:N], len(sel)),
                "resid": rng.normal(0, 0.01, len(sel) * N).astype("float32"),
            }
        )
        rs.to_parquet(eb / "risk" / f"residuals_{y}.parquet")
        vv = pd.DataFrame(
            {
                "symbol": np.tile(syms[:N], len(sel)),
                "trade_date": np.repeat(dates[sel].values, N).astype("datetime64[us]"),
                "dollar_adv_21_over_63": rng.lognormal(0, 0.3, len(sel) * N).astype("float32"),
            }
        )
        vv.to_parquet(db / f"{y}.parquet")
    return eb, db, dates, lib, slow, themes


def _make_reference(eb: Path, dates, lib, slow, themes, start, end):
    """Original regimes code, pointed at the synthetic data, as the identity reference."""
    reg = _load("regimes_ref_mod", "scripts/analyze_equity_book_regimes.py")
    reg.DATA = eb
    open_, _ = reg.load_etf()
    sessions = open_["SPY"].dropna().index
    names = lib + slow
    th = {t: list(v) for t, v in sg.THEME_SIGNALS.items()}
    cols = ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
    cols += names + [f"{n}_cov" for n in names] + [f"theme_{t}" for t in th]
    parts = []
    for y in (2020, 2021):
        sig = pd.read_parquet(eb / f"signals/{y}.parquet", columns=cols)
        sig = sig[(sig["trade_date"] >= start) & (sig["trade_date"] <= end)]
        ret = reg.year_returns(y, sessions, open_["SPY"])
        df = sig.merge(ret, on=["trade_date", "symbol"], how="inner")
        df = df[np.isfinite(df["e"])]
        f, _ = reg.ls_returns(df, names, th)
        parts.append(f)
    F = pd.concat(parts).sort_index()
    F.to_parquet(eb / "regimes" / "signal_ls_daily.parquet")


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("p1s0")
    eb, db, dates, lib, slow, themes = _write_synthetic(root)
    start, end = str(dates[30].date()), str(dates[-3].date())
    _make_reference(eb, dates, lib, slow, themes, start, end)
    it = root / "iter"
    it.mkdir()
    cfg = m.Cfg(
        data=eb,
        daily_broad=db,
        regimes_ref=eb / "regimes" / "signal_ls_daily.parquet",
        iter_dir=it,
        cache=root / "cache",
        cal_start="2019-01-01",
        start=start,
        end=end,
        last_data=str(dates[-1].date()),
        windows={
            "recent": ("2021-01-04", end),
            "stress": (start, "2020-12-31"),
            "owner_B": ("2021-03-01", end),
        },
        sign_window=(start, "2020-12-31"),
        cut=(20, 40, 80),
        min_names=8,
        expected_lib=len(lib),
        reb_periods=(2, 3),
        n_seeds=2,
        wf={"FC_WF252": (40, 25), "FC_WF63": (15, 10)},
        identity_cols=("m0_composite", "rev_21_ind", "a101_alpha016"),
        procs=1,
        schema_year=2021,
        dsr_window=("2021-01-04", end),
        blend_vol_window=15,
    )
    for st in m.STAGES:
        m.run_stage(cfg, st)
    return cfg


def test_identity_against_regimes_code(pipeline):
    ident = json.loads((pipeline.iter_dir / "identity.json").read_text())
    assert ident["passed"]
    for nm in pipeline.identity_cols:
        assert ident[nm]["max_abs_diff"] <= 1e-9
        assert ident[nm]["nan_pattern_mismatch_days"] == 0
        assert ident[nm]["n_compared_days"] > 100


def test_results_structure_and_acceptance_fields(pipeline):
    R = json.loads((pipeline.iter_dir / "results.json").read_text())
    assert R["mechanical_status"] in ("measured_promotions", "measured_no_promotion")
    assert len(R["objects"]) == 6 + 7 + 3 + 10
    keys = {
        "ic_mean",
        "ic_t",
        "ic_on1",
        "ic_id1",
        "cic_2_6",
        "cic_2_6_t",
        "cic_2_22",
        "cic_1_22",
        "h_np",
        "h_exp",
        "F_MOC",
        "F_MOO",
        "persistence",
        "ic_sd_cic_2_6",
        "mde_cic_2_6",
        "n_days",
    }
    for o in R["objects"].values():
        assert set(o["windows"]["L12"]) == {"recent", "stress", "owner_B"}
        for w in o["windows"]["L12"].values():
            assert keys <= set(w)
            assert len(w["ic_mean"]) == 22 and len(w["ic_t"]) == 22
            assert set(w["persistence"]) == {"1", "5", "21"}
    full = set(m.OBJ_B + m.OBJ_C + ["m0_composite"])
    for name in full:
        assert set(R["objects"][name]["windows"]) == {"L12", "L1", "L2", "L3"}
    # speed: 7 configurations per object on L12 with the 7 metrics, kappa_star and MOO
    for name in R["speed"]:
        sp = R["speed"][name]["L12"]
        assert len(sp["configs"]) == 7
        for cfgm in sp["configs"].values():
            for w in ("recent", "stress", "owner_B"):
                assert {
                    "gross",
                    "net",
                    "net_2x",
                    "turnover",
                    "avg_gross",
                    "cost_bp_yr",
                    "corr_m0",
                } <= set(cfgm["metrics"][w])
        if sp["kappa_star"] is not None:
            assert "k1" in sp["moo"] and sp["kappa_star"] in sp["moo"]
    # composites
    for c in m.OBJ_C:
        e = R["composites"][c]
        assert e["first_valid_date"] is not None
        if e["kappa_star"] is not None:
            assert len(e["placebo"]["recent_net_sharpe"]) == 2
            assert set(e["blend_with_m0"]) == {"recent", "stress"}
            assert "dsr_21" in e and "dsr_193" in e
    led = json.loads((pipeline.iter_dir / "trial-ledger.json").read_text())
    assert len(led) == 70
    assert {"candidate", "speed", "recent_net_sharpe", "stress_net_sharpe"} <= set(led[0])
    pr = R["promotion"]
    assert len(pr["singles"]) == 7 and len(pr["composites"]) == 3
    dc = R["data_checks"]
    assert dc["n_library_columns"] == 6 and dc["max_trade_date_ok"]
    assert "stress_sign_flip" in pr
    md = (pipeline.iter_dir / "report.md").read_text().splitlines()
    assert 0 < len(md) <= 150


def test_signs_fixed_before_recent_window_and_stress_only(pipeline):
    signs = json.loads((pipeline.cache / "signs.json").read_text())
    ev = [json.loads(line) for line in (pipeline.cache / "events.jsonl").read_text().splitlines()]
    first_recent = next(e["utc"] for e in ev if e["event"] == "recent_window_first_touch")
    assert signs["fixed_at"] < first_recent
    assert signs["ON5"]["sign"] in (-1, 1) and signs["ID5"]["sign"] in (-1, 1)
    assert signs["window"] == list(pipeline.sign_window)


def test_new_signals_definitions_on_synthetic_data(pipeline):
    """REV5 / ON5 / ID5 / RREV5 built in the build stage equal a direct recomputation."""
    ctx = m.Ctx(pipeline)
    y = 2021
    rows = ctx.rows(y)
    B = np.load(pipeline.cache / f"B_{y}.npy")
    di, si = rows["di"], rows["si"]
    k = len(di) // 2
    d, s = int(di[k]), int(si[k])
    C, O = np.asarray(ctx.C), np.asarray(ctx.O)
    if np.isfinite(C[d, s]) and np.isfinite(C[d - 5, s]):
        assert B[k, 0] == pytest.approx(-(C[d, s] / C[d - 5, s] - 1.0), rel=1e-5)
    on = [O[d - i, s] / C[d - i - 1, s] - 1.0 for i in range(5)]
    idv = [C[d - i, s] / O[d - i, s] - 1.0 for i in range(5)]
    if np.isfinite(on).sum() >= 4:
        assert B[k, 4] == pytest.approx(np.nanmean(on), rel=1e-4, abs=1e-7)
    if np.isfinite(idv).sum() >= 4:
        assert B[k, 5] == pytest.approx(np.nanmean(idv), rel=1e-4, abs=1e-7)
    # no row after the last usable date is read
    assert pipeline.last_data >= max(ctx.meta["max_trade_date_read"].values())


# --------------------------------------------------------------------------- extra checks


def test_rank_ic_matches_spearman_and_missing_rule():
    from scipy.stats import spearmanr

    rng = np.random.default_rng(8)
    n = 200
    x = rng.normal(size=(n, 1))
    e = 0.3 * x + rng.normal(size=(n, 1))
    zx, fx = m.zrank(x)
    ze, fe = m.zrank(e)
    ic = m.rank_ic(zx, fx, ze, fe, 50)[0, 0]
    assert ic == pytest.approx(spearmanr(x[:, 0], e[:, 0]).statistic, abs=1e-12)
    # a missing score is neutral (0) and the day needs >= 50 pairs
    x2 = x.copy()
    x2[:40] = np.nan
    zx, fx = m.zrank(x2)
    ic2 = m.rank_ic(zx, fx, ze, fe, 50)[0, 0]
    rk = pd.Series(x2[:, 0]).rank().to_numpy()
    zs = np.where(np.isfinite(rk), rk - (np.isfinite(rk).sum() + 1) / 2, 0.0)
    zr = pd.Series(e[:, 0]).rank().to_numpy()
    zr = zr - (n + 1) / 2
    assert ic2 == pytest.approx((zs * zr).sum() / np.sqrt((zs**2).sum() * (zr**2).sum()))
    x3 = x.copy()
    x3[:160] = np.nan
    zx, fx = m.zrank(x3)
    assert math.isnan(m.rank_ic(zx, fx, ze, fe, 50)[0, 0])


def test_lag_targets_match_direct_computation():
    ctx = _toy_grid(T=60, N=40, seed=4)
    ctx.beta[:] = np.random.default_rng(2).normal(1.0, 0.4, ctx.beta.shape)
    ctx.beta[10, 3] = np.nan
    ctx.beta[10, 5] = 9.0  # clipped to 3
    di, si, ind = _toy_rows(ctx)
    E = m.lag_targets(ctx, di, si, ind)
    t = 10
    rows = np.flatnonzero(di == t)
    b = np.clip(np.where(np.isfinite(ctx.beta[t]), ctx.beta[t], 1.0), -0.5, 3.0)

    def hedged(j):
        r = ctx.C[t + j] / ctx.C[t + j - 1] - 1.0
        rs = ctx.spy_c[t + j] / ctx.spy_c[t + j - 1] - 1.0
        return r - b * rs

    for j in (1, 2, 7, 22):
        v = hedged(j)
        grp = ind[rows]
        exp = v - pd.Series(v).groupby(grp).transform("mean").to_numpy()
        assert E[rows, j - 1] == pytest.approx(exp, abs=1e-12)
    ov = ctx.O[t + 1] / ctx.C[t] - 1.0 - b * (ctx.spy_o[t + 1] / ctx.spy_c[t] - 1.0)
    idr = ctx.C[t + 1] / ctx.O[t + 1] - 1.0 - b * (ctx.spy_c[t + 1] / ctx.spy_o[t + 1] - 1.0)
    for col, v in ((22, ov), (23, idr)):
        exp = v - pd.Series(v).groupby(ind[rows]).transform("mean").to_numpy()
        assert E[rows, col] == pytest.approx(exp, abs=1e-12)
    # lags beyond the last session are missing
    last = np.flatnonzero(di == ctx.T - 3)
    assert np.isnan(E[last, 2:LAGS_CONST]).all()


LAGS_CONST = 22


def test_persistence_matches_spearman_on_common_names():
    from scipy.stats import spearmanr

    rng = np.random.default_rng(9)
    N, T = 120, 8
    cfgm = SimpleNamespace(cut=(40, 80, 120), min_names=20)
    ctxm = SimpleNamespace(T=T)
    acc = m.ICAcc(cfgm, ctxm, 1, ["L12"])
    base = rng.normal(size=N)
    di, si, X, adv = [], [], [], []
    for t in range(T):
        keep = np.sort(rng.choice(N, 100, replace=False))
        v = 0.7 * base[keep] + rng.normal(size=len(keep))
        di += [t] * len(keep)
        si += keep.tolist()
        X.append(v[:, None])
        adv += (keep + 1).tolist()
    di, si, adv = np.array(di), np.array(si), np.array(adv, dtype=float)
    X = np.vstack(X).astype("float32")
    E = np.full((len(di), m.NTGT), np.nan)
    acc.add_year(di, si, adv, X, E)
    t, L = 6, 5
    cur = {
        s: v
        for s, v, d, a in zip(si[di == t], X[di == t, 0], di[di == t], adv[di == t], strict=True)
        if a <= 80
    }
    prev = {s: v for s, v in zip(si[di == t - L], X[di == t - L, 0], strict=True)}
    common = sorted(set(cur) & set(prev))
    exp = spearmanr([cur[s] for s in common], [prev[s] for s in common]).statistic
    assert acc.pers["L12"][t, 0, 1] == pytest.approx(exp, abs=1e-6)
