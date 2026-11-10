"""T-20261006-15 group C analysis: portfolios, selection, placebos, DSR, phases, V4.

Reads data/features/t15_c/trades/*.parquet (written by t15_c_orb.py), the A/B results for the DSR
inputs and the QQQ noise-band daily series. Writes results_c.json and trial-ledger-c.jsonl in the
iteration directory. Frozen rules: amendment-2026-10-06-main-grid.md, hypotheses.md section C.
"""

from __future__ import annotations

import json
import math
import os
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import t15_c_orb as C5  # noqa: E402
import t15_engine as E  # noqa: E402
import t15_stats as T  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261006_15_intraday_rules"
OUT = Path(os.environ.get("T15C_OUT", ITER))
WORK = C5.WORK
DEPTHS = (100, 300, 600)
KS = (20, 50, 100)
MAIN_K = (20, 50)
MAIN_STOPS = ("atr10", "opposite", "atr5")
SEEDS = 100
FEES = C5.FEES_BP
MULTS = (0.5, 1.0, 2.0, 4.0)
PAPER_SPEC = {"R": 5, "K": 20, "stop": "atr10", "sem": "stop_price"}
V4_START, V4_END = "2017-10-02", "2023-08-31"


def _r(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _alpha(y: np.ndarray, x: np.ndarray) -> dict:
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = np.asarray(y, dtype=float)[ok], np.asarray(x, dtype=float)[ok]
    if len(y) < 30:
        return {
            "annual_alpha": None,
            "alpha_t_nw5": None,
            "beta_spy": None,
            "sessions": int(len(y)),
        }
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    score = X * resid[:, None]
    S = score.T @ score / len(y)
    for lag in range(1, min(5, len(y) - 1) + 1):
        gamma = score[lag:].T @ score[:-lag] / len(y)
        S += (1.0 - lag / 6.0) * (gamma + gamma.T)
    Q = X.T @ X / len(y)
    cov = np.linalg.pinv(Q) @ S @ np.linalg.pinv(Q) / len(y)
    return {
        "annual_alpha": _r(beta[0] * 252),
        "alpha_t_nw5": _r(beta[0] / math.sqrt(max(float(cov[0, 0]), 1e-30))),
        "beta_spy": _r(beta[1]),
        "sessions": int(len(y)),
    }


class Trades:
    def __init__(self):
        files = sorted((WORK / "trades").glob("*.parquet"))
        self.df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        d = pd.to_datetime(self.df["d"])
        daily = sorted((WORK / "daily").glob("*.parquet"))
        cal = pd.concat([pd.read_parquet(f, columns=["d"]) for f in daily])["d"].unique()
        cal = pd.DatetimeIndex(np.sort(cal))
        cal = cal[cal >= pd.Timestamp("2017-09-01")]
        self.dates = cal
        self.D = len(cal)
        self.day = cal.get_indexer(d)
        assert (self.day >= 0).all()
        df = self.df
        self.pool = df["pool"].to_numpy()
        self.ho = df["hs_open"].to_numpy(float)
        self.hc = df["hs_close"].to_numpy(float)
        self.pc = df["pc"].to_numpy(float)
        self.atr = df["atr"].to_numpy(float)
        self.masks = E.window_masks(cal)
        self._order = {}
        daily_rows = []
        for f in daily:
            x = pd.read_parquet(f, columns=["d", "symbol", "c"])
            daily_rows.append(x[x["d"].dt.strftime("%Y-%m") == f.stem])
        all_daily = pd.concat(daily_rows, ignore_index=True)
        spy = all_daily[all_daily["symbol"] == "SPY"].sort_values("d")
        self.spy = (
            spy.set_index("d")["c"].pct_change(fill_method=None).reindex(self.dates).to_numpy(float)
        )

    def col(self, name):
        return self.df[name].to_numpy(float)

    def order(self, R, depth):
        """Eligible rows sorted by (day, -relative volume) with the rank inside the day."""
        key = (R, depth)
        if key not in self._order:
            ok = self.df[f"ok{R}"].to_numpy() == 1
            idx = np.flatnonzero(ok & (self.pool <= depth))
            rel = self.df[f"rel{R}"].to_numpy(float)[idx]
            o = np.lexsort((-rel, self.day[idx]))
            idx = idx[o]
            if len(idx) == 0:
                self._order[key] = (idx, np.empty(0, dtype=int))
                return self._order[key]
            ds = self.day[idx]
            start = np.r_[True, ds[1:] != ds[:-1]]
            pos = np.arange(len(idx))
            first = np.maximum.accumulate(np.where(start, pos, 0))
            self._order[key] = (idx, pos - first)
        return self._order[key]

    def rows(self, R, depth, K):
        idx, rank = self.order(R, depth)
        return idx[rank < K]

    def cost(self, rows, stopped, mult, fees=FEES):
        hs_exit = np.where(stopped, 0.5 * (self.ho[rows] + self.hc[rows]), self.hc[rows])
        # Frozen cost multiples stress the spread component; commissions remain fixed.
        return (mult * (self.ho[rows] + hs_exit) + 2.0 * fees) / 1e4

    def daily(self, rows, vals, K):
        return np.bincount(self.day[rows], weights=vals, minlength=self.D) / K

    def counts(self, rows):
        return np.bincount(self.day[rows], minlength=self.D).astype(float)

    def series(self, R, depth, K, stop, sem, mult=1.0, delay=0):
        rows = self.rows(R, depth, K)
        if delay:
            g = self.col(f"gd{delay}_{stop}")[rows]
            st = self.col(f"gds{delay}_{stop}")[rows] > 0
            good = np.isfinite(g)
            rows, g, st = rows[good], g[good], st[good]
        else:
            g = self.col(f"g{R}_{stop}_{sem}")[rows]
            st = self.col(f"gs{R}_{stop}")[rows] > 0
            good = np.isfinite(g)
            rows, g, st = rows[good], g[good], st[good]
        c = self.cost(rows, st, mult)
        gross = self.daily(rows, g, K)
        cost = self.daily(rows, c, K)
        return gross, cost, self.counts(rows), (rows, g, st)


def metrics(tr: Trades, R, depth, K, stop, sem):
    rec = tr.masks["recent"]
    gross, cost1, cnt, (rows, g, st) = tr.series(R, depth, K, stop, sem, 1.0)
    nets = {}
    for mu in MULTS:
        _, cmu, _, _ = tr.series(R, depth, K, stop, sem, mu)
        nets[mu] = gross - cmu
    n1 = nets[1.0]
    rr = rec[tr.day[rows]]
    gb = float(np.mean(g[rr]) * 1e4) if rr.any() else float("nan")
    cb = float(np.mean(tr.cost(rows, st, 1.0)[rr]) * 1e4) if rr.any() else float("nan")
    d = {
        "gross_bp_per_trade": _r(gb),
        "cost_bp_per_trade": _r(cb),
        "cost_share_of_gross": _r(cb / gb) if gb > 0 else None,
        "trades_per_day": _r(np.mean(cnt[rec])),
        "stopped_share": _r(np.mean(st[rr])) if rr.any() else None,
        "gross_bp_day": _r(np.mean(gross[rec]) * 1e4),
        "net_bp_day": _r(np.mean(n1[rec]) * 1e4),
        "sr_net_recent": {f"x{m}": _r(T.sr_rows(nets[m][None, :], rec)[0]) for m in MULTS},
        "sr_gross_recent": _r(T.sr_rows(gross[None, :], rec)[0]),
        "sr_net_2017_2023": _r(T.sr_rows(n1[None, :], tr.masks["diag_2016_2023"])[0]),
        "phase_sr_net": {
            f"P{i:02d}": _r(T.sr_rows(n1[None, :], tr.masks[f"P{i:02d}"])[0]) for i in range(1, 12)
        },
        "t_newey_west": _r(T.nw(n1[rec])["t_newey_west"]),
        "ann_net_ret": _r(np.mean(n1[rec]) * 252),
        "alpha_vs_spy": _alpha(n1[rec], tr.spy[rec]),
    }
    return d, nets, gross


def cross_sectional_ic(tr: Trades, depth: int, K: int) -> dict:
    rows = tr.rows(5, depth, K)
    if len(rows) == 0:
        return {}
    days = tr.day[rows]
    fwd = tr.col("fwd5")[rows]
    direction = tr.col("dir5")[rows]
    rel = tr.col("rel5")[rows]
    recent = tr.masks["recent"][days]
    rows = rows[recent]
    days = days[recent]
    fwd = fwd[recent]
    direction = direction[recent]
    rel = rel[recent]
    vals = {"direction_vs_forward_return": [], "relvolume_vs_forward_return": []}
    for day in np.unique(days):
        m = (days == day) & np.isfinite(fwd)
        if m.sum() < 3:
            continue
        y = pd.Series(fwd[m]).rank(method="average").to_numpy()
        for name, x in (
            ("direction_vs_forward_return", direction[m]),
            ("relvolume_vs_forward_return", rel[m]),
        ):
            if np.nanstd(x) > 0 and np.nanstd(y) > 0:
                vals[name].append(float(np.corrcoef(pd.Series(x).rank(method="average"), y)[0, 1]))
    out = {}
    for name, values in vals.items():
        a = np.asarray(values, dtype=float)
        out[name] = {
            "mean_rank_ic": _r(np.nanmean(a)) if len(a) else None,
            "nw_t": _r(T.nw(a)["t_newey_west"]) if len(a) >= 3 else None,
            "days": int(len(a)),
            "interpretation": (
                "daily cross-sectional rank IC; direction is binary, relvolume is ranking"
            ),
        }
    return out


def v4_check(net: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    m = (dates >= pd.Timestamp(V4_START)) & (dates <= pd.Timestamp(V4_END))
    x = np.nan_to_num(net[m], nan=0.0)
    out = {"sessions": int(m.sum())}
    if len(x) < 70:
        out["note"] = "window not covered"
        return out
    sd = x.std(ddof=1)
    for w, name, veto, warn in ((21, "21d", 5.0, 4.0), (63, "63d", 4.0, 3.0)):
        c = np.convolve(x, np.ones(w), mode="valid")
        worst = float(c.min())
        vol = sd * math.sqrt(w)
        ratio = -worst / vol if vol > 0 else float("nan")
        out[name] = {
            "worst_sum": _r(worst),
            "vol_over_window": _r(vol),
            "loss_over_vol": _r(ratio),
            "veto": bool(ratio > veto),
            "warn": bool(ratio > warn),
        }
    out["sr_net_in_window"] = _r(T.sr_rows(net[None, :], m)[0])
    return out


# ---------------------------------------------------------------------------- placebos
def placebos(tr: Trades, depth, K, stop, rng):
    """Random direction per entry (spec): same exits, sizes, costs. Also the mirror-simulated
    version (own stops) and random selection of K among the eligible names (supplementary)."""
    rec = tr.masks["recent"]
    rows = tr.rows(5, depth, K)
    rows = rows[rec[tr.day[rows]]]
    g = tr.col(f"g5_{stop}_stop_price")[rows]
    m = tr.col(f"m5_{stop}_stop_price")[rows]
    dirn = tr.col("dir5")[rows]
    u = g * dirn
    st = tr.col(f"gs5_{stop}")[rows] > 0
    stm = tr.col(f"ms5_{stop}")[rows] > 0
    c_real = tr.cost(rows, st, 1.0)
    c_mir = tr.cost(rows, stm, 1.0)
    n = len(rows)
    out = {}
    g1 = np.full((SEEDS, tr.D), np.nan)
    n1 = np.full((SEEDS, tr.D), np.nan)
    g2 = np.full((SEEDS, tr.D), np.nan)
    n2 = np.full((SEEDS, tr.D), np.nan)
    sgn = rng.choice([-1.0, 1.0], size=(SEEDS, n))
    coin = rng.random((SEEDS, n)) < 0.5
    for s in range(SEEDS):
        gp = sgn[s] * u
        g1[s, rec] = tr.daily(rows, gp, K)[rec]
        n1[s, rec] = tr.daily(rows, gp - c_real, K)[rec]
        gm = np.where(coin[s], g, m)
        cm = np.where(coin[s], c_real, c_mir)
        g2[s, rec] = tr.daily(rows, gm, K)[rec]
        n2[s, rec] = tr.daily(rows, gm - cm, K)[rec]
    out["dir_same_exit"] = (n1, g1)
    out["dir_mirror_sim"] = (n2, g2)
    # random selection among eligible names (same pool, same K, real direction and exits)
    idx, _ = tr.order(5, depth)
    idx = idx[rec[tr.day[idx]]]
    ge = tr.col(f"g5_{stop}_stop_price")[idx]
    ste = tr.col(f"gs5_{stop}")[idx] > 0
    ce = tr.cost(idx, ste, 1.0)
    dd = tr.day[idx]
    start = np.r_[True, dd[1:] != dd[:-1]]
    pos = np.arange(len(idx))
    first = np.maximum.accumulate(np.where(start, pos, 0))
    g3 = np.full((SEEDS, tr.D), np.nan)
    n3 = np.full((SEEDS, tr.D), np.nan)
    for s in range(SEEDS):
        key = rng.random(len(idx))
        o = np.lexsort((key, dd))  # dd already sorted by day: lexsort keeps days grouped
        rank = np.empty(len(idx), int)
        rank[o] = pos - first
        sel = rank < K
        gs = np.bincount(dd[sel], weights=ge[sel], minlength=tr.D) / K
        cs = np.bincount(dd[sel], weights=ce[sel], minlength=tr.D) / K
        g3[s, rec] = gs[rec]
        n3[s, rec] = (gs - cs)[rec]
    out["random_selection"] = (n3, g3)
    return out


def eval_candidate(tr, depth, K, stop, nets, gross, dsr_args, rng, extra_name):
    rec = tr.masks["recent"]
    n1, n2 = nets[1.0], nets[2.0]
    pl = placebos(tr, depth, K, stop, rng)
    sr_net = T.sr_rows(n1[None, :], rec)[0]
    sr_gross = T.sr_rows(gross[None, :], rec)[0]
    pct = {}
    for name, (npl, gpl) in pl.items():
        pct[name] = {
            "net_pct": _r(T.placebo_pct(sr_net, T.sr_rows(npl, rec))),
            "gross_pct": _r(T.placebo_pct(sr_gross, T.sr_rows(gpl, rec))),
            "placebo_net_sr_median": _r(np.nanmedian(T.sr_rows(npl, rec))),
            "placebo_gross_sr_median": _r(np.nanmedian(T.sr_rows(gpl, rec))),
        }
    prim = pct["dir_same_exit"]
    rob = T.robustness(n1, n2, tr.dates, tr.masks, prim["gross_pct"])
    # d item: fill delayed by 1 and 2 five-minute bars (1-minute phase shifts are not representable)
    ph = {"delay_0": _r(sr_net)}
    for dl in C5.DELAYS:
        gd, cd, _, _ = tr.series(5, depth, K, stop, "stop_price", 1.0, delay=dl)
        ph[f"delay_{dl}"] = _r(T.sr_rows((gd - cd)[None, :], rec)[0])
    d_ok = sum(1 for v in ph.values() if v is not None and v > 0) >= 2
    rob["d_offsets"] = bool(d_ok)
    rob["score"] = (
        int(rob["a_cost2x_ratio"])
        + int(rob["b_up_state_sharpe_gt0"])
        + int(rob["c_ok"])
        + int(d_ok)
        + int(rob["e_ok"])
        + int(rob["f_ok"])
    )
    dsr = T.dsr_of(n1[rec], *dsr_args["primary"])
    dsr_strict = T.dsr_of(n1[rec], *dsr_args["strict"])
    out = {
        "sr_net_recent": _r(sr_net),
        "sr_gross_recent": _r(sr_gross),
        "placebo": pct,
        "d_check_delay_recent_sr": ph,
        "robustness": rob,
        "dsr": _r(dsr["dsr"]),
        "dsr_strict_independent_N": _r(dsr_strict["dsr"]),
        "sr0_annual_null": _r(dsr["sr0_annual"]),
        "psr0": _r(dsr["psr0"]),
        "V3_cost2x_recent_ann_net_gt0": bool(np.mean(n2[rec]) * 252 > 0),
        "V4_2017_10_to_2023_08": v4_check(n1, tr.dates),
    }
    out["tier"] = T.tier_p1(dsr["dsr"], prim["net_pct"], rob["score"])
    return out


# ---------------------------------------------------------------------------- reproduction
def reproduction(tr: Trades):
    """Paper spec (5 min, K=20, 10% ATR stop, stop price fills), commission only."""
    out = {}
    depth = 600
    K = PAPER_SPEC["K"]
    rows = tr.rows(5, depth, K)
    g = tr.col("g5_atr10_stop_price")[rows]
    comm = 0.0035 / tr.pc[rows] * 2.0  # $0.0035/share per side, round trip, fraction of notional
    gross = tr.daily(rows, g, K)
    net_eq = tr.daily(rows, g - comm, K)
    x = tr.pc[rows] / tr.atr[rows]
    # paper sizing: 1% risk / (10% ATR) -> weights proportional to P/ATR, total gross capped at 4x
    day = tr.day[rows]
    tot = np.bincount(day, weights=x, minlength=tr.D)
    scale = np.minimum(1.0, 4.0 / np.where(tot > 0, tot * 0.1, np.inf))
    w = 0.1 * x * scale[day]
    net_pp = np.bincount(day, weights=w * (g - comm), minlength=tr.D)
    gross_pp = np.bincount(day, weights=w * g, minlength=tr.D)
    wins = {
        "2017-10_2022-12": (tr.dates >= "2017-10-02") & (tr.dates <= "2022-12-30"),
        "2023_2023-08": (tr.dates >= "2023-01-03") & (tr.dates <= "2023-08-31"),
        "2017-10_2023-08": (tr.dates >= "2017-10-02") & (tr.dates <= "2023-08-31"),
        "recent_2024-01-08_end": tr.masks["recent"],
    }
    for name, msk in wins.items():
        out[name] = {
            "equal_weight_1/K_sr_gross": _r(T.sr_rows(gross[None, :], msk)[0]),
            "equal_weight_1/K_sr_commission_only": _r(T.sr_rows(net_eq[None, :], msk)[0]),
            "paper_sizing_cap4x_sr_gross": _r(T.sr_rows(gross_pp[None, :], msk)[0]),
            "paper_sizing_cap4x_sr_commission_only": _r(T.sr_rows(net_pp[None, :], msk)[0]),
            "paper_sizing_cap4x_ann_ret_commission_only": _r(np.mean(net_pp[msk]) * 252),
            "gross_bp_per_trade": _r(np.mean(g[msk[day]]) * 1e4),
        }
    atr_dist = 0.1 * tr.atr[rows]
    entry_proxy = tr.pc[rows]
    r_mult = g / (atr_dist / entry_proxy)
    out["mean_R_per_trade_all"] = _r(np.mean(r_mult))
    out["paper_reported"] = {"sharpe_2016_2023": 2.81, "R_per_trade": 0.08}
    return out


# ---------------------------------------------------------------------------- main
def qqq_noiseband_corr(tr: Trades, net_c: np.ndarray) -> dict:
    z = np.load(ROOT / "data/features/t15_work/ab_QQQ.npz")
    dates = pd.DatetimeIndex(z["dates"])
    lev = np.where(np.isfinite(z["lev"]), z["lev"], 1.0)
    net = lev * (z["G_k30_m1.0_ph0"] - z["C_k30_m1.0_ph0"])
    s = pd.Series(net, index=dates)
    c = pd.Series(net_c, index=tr.dates)
    both = pd.concat([s.rename("qqq_nb"), c.rename("orb")], axis=1, join="inner").dropna()
    rec = both[both.index >= E.RECENT_START]
    return {
        "series": "QQQ noise band k30 M1 vt1 net x1 (ab_QQQ.npz)",
        "recent_days": int(len(rec)),
        "corr_recent_pearson": _r(rec["qqq_nb"].corr(rec["orb"])),
        "corr_recent_spearman": _r(rec["qqq_nb"].corr(rec["orb"], method="spearman")),
        "corr_all_overlap": _r(both["qqq_nb"].corr(both["orb"])),
        "overlap_days": int(len(both)),
    }


def main() -> int:
    tr = Trades()
    rec = tr.masks["recent"]
    n_rec = int(rec.sum())
    rng = np.random.default_rng(20261006)
    res = {
        "generated_for": "amendment-2026-10-06-main-grid (group C)",
        "calendar": [str(tr.dates[0].date()), str(tr.dates[-1].date())],
        "recent_sessions": n_rec,
        "min_detectable_annual_sharpe_5pct_80pwr": _r((1.6449 + 0.8416) / math.sqrt(n_rec / 252.0)),
        "main_points": {},
        "robustness_versions": {},
    }
    # ---- all 162 versions: metrics + series
    versions = {}
    series_all = {}
    for depth, R, K, stop, sem in product(DEPTHS, C5.RANGES, KS, MAIN_STOPS, C5.SEMS):
        d, nets, gross = metrics(tr, R, depth, K, stop, sem)
        key = f"pool{depth}_R{R}_K{K}_{stop}_{sem}"
        main = R == 5 and K in MAIN_K and sem == "stop_price"
        d["main_grid"] = main
        versions[key] = d
        series_all[key] = (nets, gross)
    main_keys = [k for k, v in versions.items() if v["main_grid"]]
    assert len(main_keys) == 18
    res["main_points"] = {k: versions[k] for k in main_keys}
    res["robustness_versions"] = {k: v for k, v in versions.items() if not v["main_grid"]}
    # ---- DSR inputs (amendment: N = main points + robustness points; variance from main grid)
    srs_main = np.array([versions[k]["sr_net_recent"]["x1.0"] for k in main_keys], float)
    var_sr = float(np.nanvar(srs_main, ddof=1))
    X = np.stack([series_all[k][0][1.0][rec] for k in series_all])
    X = X[np.std(X, axis=1) > 0]
    rho = float(np.mean(np.corrcoef(X)[np.triu_indices(len(X), 1)]))
    nC = 1 + (len(series_all) - 1) * (1 - rho)
    ab = json.loads((ITER / "results_ab_main.json").read_text())["dsr_inputs"]
    n_total = ab["A"]["n_eff"] + ab["B"]["n_eff"] + nC + 16
    n_strict = 98 + 144  # all counted main points + C robustness versions, treated as independent
    dsr_args = {"primary": (var_sr, n_total), "strict": (var_sr, float(n_strict))}
    res["dsr_inputs"] = {
        "C_versions": len(series_all),
        "C_var_sr_main_points": var_sr,
        "C_mean_pairwise_corr_all_versions": rho,
        "C_n_eff": nC,
        "n_eff_A": ab["A"]["n_eff"],
        "n_eff_B": ab["B"]["n_eff"],
        "D_main_points_counted_independent": 16,
        "n_eff_total_primary": n_total,
        "n_independent_strict": n_strict,
        "note": "A/B inputs from results_ab_main.json dsr_inputs; D not yet run.",
    }
    # ---- selection per depth and candidate evaluation
    res["selected"] = {}
    for depth in DEPTHS:
        pts = [(K, s) for K in MAIN_K for s in MAIN_STOPS]
        sr = {
            p: versions[f"pool{depth}_R5_K{p[0]}_{p[1]}_stop_price"]["sr_net_recent"]["x1.0"]
            for p in pts
        }
        order = sorted(pts, key=lambda p: -(sr[p] if sr[p] is not None else -9))
        sel = order[1]
        K, stop = sel
        key = f"pool{depth}_R5_K{K}_{stop}_stop_price"
        nets, gross = series_all[key]
        ev = eval_candidate(tr, depth, K, stop, nets, gross, dsr_args, rng, key)
        ev["cross_sectional_ic"] = cross_sectional_ic(tr, depth, K)
        res["selected"][f"pool{depth}"] = {
            "selected_spec": {"K": K, "stop": stop, "R": 5, "sem": "stop_price"},
            "top3": [list(p) for p in order[:3]],
            "key": key,
            "metrics": versions[key],
            **ev,
        }
        # paper spec of the frozen manifest at this depth, for reference
        pk = f"pool{depth}_R5_K20_atr10_stop_price"
        if pk != key:
            nets_p, gross_p = series_all[pk]
            res["selected"][f"pool{depth}"]["paper_spec_reference"] = {
                "key": pk,
                "sr_net_recent": versions[pk]["sr_net_recent"]["x1.0"],
                "sr_gross_recent": versions[pk]["sr_gross_recent"],
            }
    # best (highest-depth-median) overall for QQQ correlation: use the selected spec of each depth
    res["qqq_noiseband_corr"] = {
        f"pool{dp}": qqq_noiseband_corr(tr, series_all[res["selected"][f"pool{dp}"]["key"]][0][1.0])
        for dp in DEPTHS
    }
    res["reproduction"] = reproduction(tr)
    ba = json.loads(Path(WORK / "base_notes.json").read_text())
    res["hygiene"] = {k: v for k, v in ba.items() if k != "split_event_list"}
    res["hygiene"]["split_event_examples"] = ba.get("split_event_list", [])[:25]
    (OUT / "results_c.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    # ---- trial ledger (one line per computed point)
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%MZ")
    lines = []
    for k in main_keys:
        v = versions[k]
        lines.append(
            {
                "ts": ts,
                "group": "C",
                "kind": "main_grid_point",
                "points": 1,
                "id": k,
                "sr_net_recent_x1": v["sr_net_recent"]["x1.0"],
                "gross_bp_per_trade": v["gross_bp_per_trade"],
            }
        )
    lines.append(
        {
            "ts": ts,
            "group": "C",
            "kind": "robustness_full_grid",
            "versions": len(series_all) - 18,
            "detail": "R x K x pool x stop x semantics (162 versions) minus the 18 main points",
        }
    )
    lines.append(
        {
            "ts": ts,
            "group": "C",
            "kind": "d_item_delay_variants_not_counted",
            "detail": "selected specs only, fill delayed by 1 and 2 five-minute bars",
        }
    )
    with open(OUT / "trial-ledger-c.jsonl", "w") as fh:
        for ln in lines:
            fh.write(json.dumps(ln) + "\n")
    print("wrote results_c.json,", len(lines), "ledger lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
