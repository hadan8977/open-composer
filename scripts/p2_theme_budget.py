# ruff: noqa: E501
"""T-20261005-32 / P2 stage 1: semiconductor theme risk budget on the ETF sleeves.

Contract: `reports/research/iterations/t20261005_p2_s1_theme_budget/hypotheses.md`
(+ amendment-A1.md: the same decision rule is also written for object S3).
Brief: `reports/research/control/briefs/T-20261005-32.md`.

    scripts/run_capped.sh --mem 1.0G -- uv run python scripts/p2_theme_budget.py --stage build
    scripts/run_capped.sh --mem 1.0G -- uv run python scripts/p2_theme_budget.py --stage run
    scripts/run_capped.sh --mem 1.0G -- uv run python scripts/p2_theme_budget.py --stage report

Report-only measurement; nothing here changes a frozen engine. The sleeve engines are
imported unchanged (`salvage.simulate`, `salvage.vol_scale`, `tranche.effective_weights`,
`tranche.simulate_effective`); only the theme-risk-share machinery, the cap/hedge
overlays and the evaluation are new.

Assumptions the contract leaves open (written here, not tuned on results):
  * SHY and BIL are zero-risk cash for TRS, but SHY counts as a 1x long in the margin test.
  * Margin positions are netted per ticker across sleeves and overlays.
  * A negative hedge size h (net short theme, only possible for placebo themes) puts a long
    theme leg and a short SPY leg; only long legs consume cash, short proceeds earn nothing.
  * "dsr" in the result keys is the same-volatility Sharpe change (delta SR) against ORIG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260927_01_sleeve_combination as combo  # noqa: E402
import run_h20260928_01_s3_rebalance_tranching as tranche  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

ITER_ID = "t20261005_p2_s1_theme_budget"
OUT = ROOT / "reports/research/iterations" / ITER_ID
CACHE = OUT / "cache"
C2_FILE = (
    ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.sip-repaired-20261002.parquet"
)

CASH, RF = base.CASH, base.RF  # SHY, BIL
MKT, THEME = "SPY", "SMH"
WINDOW = 126
LEVELS = [0.40, 0.30, 0.20, 0.10]
S3_OFFSETS = [0, 4, 8, 12, 16]
ALL_OFFSETS = list(range(21))
W_S3, W_C2 = 0.642, 0.358
DEBIT_RATE = 0.065
SHORT_BORROW_2X = 0.01
BOOT_DRAWS, BOOT_BLOCK, BOOT_SEED = 2000, 21, 20261005
PLACEBO_THEMES = ["XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
EXTRA_SYMBOLS = [
    "SPY",
    "SMH",
    "SOXX",
    "SOXS",
    "SSO",
    "UPRO",
    "BIL",
    "SHY",
    "XLK",
    *PLACEBO_THEMES,
]
SUB = {"TQQQ": "UPRO", "SOXL": "UPRO", "TECL": "UPRO", "USD": "SSO"}
NO_MOVE = {"SPY", "UPRO", "SSO"}  # substitutes themselves; moving them changes nothing
LEV3 = {"TQQQ", "SOXL", "TECL", "UPRO", "SOXS"}
LEV2 = {"USD", "SSO"}
WINDOWS = {
    "recent": ("2024-01-08", None),
    "stress": ("2017-10-02", "2023-08-31"),
    "full": ("2017-10-02", None),
}
REPLAY_BOXES = {
    "R1": ("2024-06-01", "2024-07-31", "2024-08-31"),
    "R2": ("2025-01-01", "2025-03-31", "2025-04-30"),
    "R3": ("2026-06-01", "2026-07-31", "2026-08-31"),
}
COST_PRIMARY, COST_2X = 10.0, 20.0


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------------------
# Risk statistics (pure numpy; unit-tested on synthetic data)
# --------------------------------------------------------------------------------------
class RiskStats:
    """Rolling covariance of daily returns over the `window` sessions ending at each row
    (inclusive). Columns with a NaN in the window are invalid for that row."""

    def __init__(self, ret: pd.DataFrame, window: int = WINDOW):
        self.cols = list(ret.columns)
        self.ci = {c: i for i, c in enumerate(self.cols)}
        arr = ret.to_numpy(dtype=float)
        self.T, self.K = arr.shape
        self.window = window
        self.cov = np.zeros((self.T, self.K, self.K))
        self.valid = np.zeros((self.T, self.K), dtype=bool)
        for t in range(window - 1, self.T):
            x = arr[t - window + 1 : t + 1]
            ok = np.isfinite(x).all(axis=0)
            self.valid[t] = ok
            idx = np.flatnonzero(ok)
            if len(idx) >= 2:
                self.cov[t][np.ix_(idx, idx)] = np.cov(x[:, idx], rowvar=False, ddof=1)


class ThemeView:
    """Theme factor f = r_theme - beta r_mkt (orthogonal to the market on the window)."""

    def __init__(self, rs: RiskStats, theme: str, mkt: str = MKT):
        self.rs, self.theme, self.mkt = rs, theme, mkt
        self.i_th, self.i_m = rs.ci[theme], rs.ci[mkt]
        s = rs.cov
        self.vs = s[:, self.i_m, self.i_m]
        cts = s[:, self.i_th, self.i_m]
        ctt = s[:, self.i_th, self.i_th]
        with np.errstate(divide="ignore", invalid="ignore"):
            self.beta = np.where(self.vs > 0, cts / self.vs, np.nan)
        self.vf = ctt - 2.0 * self.beta * cts + self.beta**2 * self.vs
        self.cf = s[:, :, self.i_th] - self.beta[:, None] * s[:, :, self.i_m]
        t_ok = np.arange(rs.T) >= rs.window - 1
        self.ok = (
            t_ok
            & rs.valid[:, self.i_th]
            & rs.valid[:, self.i_m]
            & np.isfinite(self.beta)
            & (self.vs > 0)
            & (self.vf > 1e-18)
        )

    def parts(self, w: np.ndarray, t: int) -> dict[str, np.ndarray] | None:
        """Risk decomposition of risky weight vector(s) `w` (M x K or K) on the window
        ending at row t. None if the window is incomplete for the theme, the market or any
        held column."""
        w2 = np.atleast_2d(np.asarray(w, dtype=float))
        if t < 0 or not self.ok[t]:
            return None
        if np.any(w2[:, ~self.rs.valid[t]] != 0.0):
            return None
        s = self.rs.cov[t]
        vp = np.einsum("mk,kl,ml->m", w2, s, w2)
        cpf = w2 @ self.cf[t]
        cps = w2 @ s[:, self.i_m]
        vf, vs = self.vf[t], self.vs[t]
        b_th = cpf / vf
        b_m = cps / vs
        v_e = vp - b_m**2 * vs - b_th**2 * vf
        with np.errstate(divide="ignore", invalid="ignore"):
            trs = np.where(vp > 1e-18, cpf**2 / (vf * vp), 0.0)
        return {"trs": trs, "b_th": b_th, "b_m": b_m, "v_e": v_e, "vp": vp}

    def asset_loadings(self, t: int) -> np.ndarray:
        return self.cf[t] / self.vf[t]

    def daily_trs(self, wk: np.ndarray) -> np.ndarray:
        """Ex-ante TRS for each session t: weights of t, window ending t-1."""
        n = len(wk)
        out = np.full(n, np.nan)
        if n < 2:
            return out
        w = wk[1:]
        s = self.rs.cov[:-1]
        sw = np.matmul(s, w[:, :, None])[:, :, 0]
        vp = (w * sw).sum(axis=1)
        cpf = (w * self.cf[:-1]).sum(axis=1)
        vf = self.vf[:-1]
        bad = ((w != 0.0) & ~self.rs.valid[:-1]).any(axis=1) | ~self.ok[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            trs = np.where(vp > 1e-18, cpf**2 / (vf * vp), 0.0)
        trs[bad] = np.nan
        out[1:] = trs
        return out


def cap_row(
    view: ThemeView,
    t: int,
    w_k: np.ndarray,
    c: float,
    sub_k: dict[int, int],
    cash_k: set[int],
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Selection-level cap. `w_k` is the risky target weight vector in K space (cash zero).
    Returns (new weights, s, info). s = 0 when TRS <= c or TRS is undefined."""
    p = view.parts(w_k, t)
    if p is None:
        return w_k, 0.0, {"valid": False, "trs": float("nan"), "bound": False, "flag": False}
    trs = float(p["trs"][0])
    info = {"valid": True, "trs": trs, "bound": False, "flag": False}
    if trs <= c:
        return w_k, 0.0, info
    sgn = np.sign(p["b_th"][0])
    b_i = view.asset_loadings(t)
    moved = [
        i
        for i in np.flatnonzero(w_k > 0)
        if i not in cash_k and sub_k.get(i, i) != i and b_i[i] != 0 and np.sign(b_i[i]) == sgn
    ]
    info["bound"] = True
    grid = np.arange(101) / 100.0
    wmat = np.tile(w_k, (len(grid), 1))
    for i in moved:
        wmat[:, i] = w_k[i] * (1.0 - grid)
        wmat[:, sub_k[i]] += w_k[i] * grid
    pm = view.parts(wmat, t)
    if pm is None:  # a substitute column has no valid window
        info["flag"] = True
        return w_k, 0.0, info
    ok = np.flatnonzero(pm["trs"] <= c)
    if len(ok) == 0:
        info["flag"] = True
        j = len(grid) - 1
    else:
        j = int(ok[0])
    info["trs_after"] = float(pm["trs"][j])
    return wmat[j], float(grid[j]), info


def h1_size(parts: dict[str, np.ndarray], vs: float, vf: float, c: float) -> float:
    """Closed-form hedge size h with TRS(w - h f) = c; 0 when TRS <= c."""
    trs = float(parts["trs"][0])
    if trs <= c:
        return 0.0
    b_th = float(parts["b_th"][0])
    b_m = float(parts["b_m"][0])
    v_e = float(parts["v_e"][0])
    q = c / (1.0 - c) * (b_m**2 * vs + v_e) / vf
    q = max(q, 0.0)
    if abs(b_th) <= np.sqrt(q):
        return 0.0
    return b_th - np.sign(b_th) * np.sqrt(q)


def h2_solve(
    bth_s: float, bm_s: float, bth_u: float, bm_u: float, h: float
) -> tuple[float, float] | None:
    """n SOXS + u UPRO with n*bth_s + u*bth_u = -h and n*bm_s + u*bm_u = 0. None if singular
    or negative."""
    a = np.array([[bth_s, bth_u], [bm_s, bm_u]], dtype=float)
    if abs(np.linalg.det(a)) < 1e-14:
        return None
    n, u = np.linalg.solve(a, np.array([-h, 0.0]))
    if n < 0 or u < 0:
        return None
    return float(n), float(u)


def margin_ok(pos: np.ndarray, lev2: np.ndarray, lev3: np.ndarray) -> bool:
    """Alpaca margin test on net positions (NAV = 1)."""
    long = np.clip(pos, 0.0, None)
    short = np.clip(-pos, 0.0, None)
    lev1 = ~(lev2 | lev3)
    initial = 0.5 * (long.sum() + short.sum())
    maint = (
        0.30 * long[lev1].sum()
        + 0.50 * long[lev2].sum()
        + 0.75 * long[lev3].sum()
        + 0.30 * short.sum()
    )
    return bool(initial <= 1.0 + 1e-12 and maint <= 0.9 + 1e-12)


def bisect_lambda(feasible, tol: float = 1e-4) -> float:
    """Largest lambda in [0, 1] with feasible(lambda) true (feasible assumed monotone)."""
    if feasible(1.0):
        return 1.0
    if not feasible(0.0):
        return 0.0
    lo, hi = 0.0, 1.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    return lo


# --------------------------------------------------------------------------------------
# Evaluation helpers
# --------------------------------------------------------------------------------------
def sharpe(x: np.ndarray) -> float:
    sd = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    return float(np.mean(x) / sd * np.sqrt(252.0)) if sd > 0 else float("nan")


def samevol_k(r_cfg: np.ndarray, r_orig: np.ndarray) -> float:
    sc = float(np.std(r_cfg, ddof=1))
    return float(np.std(r_orig, ddof=1) / sc) if sc > 0 else float("nan")


def samevol_excess(r: np.ndarray, rf: np.ndarray, k: float) -> np.ndarray:
    return k * (r - rf) - max(k - 1.0, 0.0) * (DEBIT_RATE / 252.0 - rf)


def es975(x: np.ndarray) -> float:
    q = np.quantile(x, 0.025)
    return float(x[x <= q].mean())


def max_drawdown(r: np.ndarray) -> float:
    eq = np.cumprod(1.0 + r)
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def window_mask(index: pd.DatetimeIndex, w: tuple[str, str | None]) -> np.ndarray:
    m = index >= pd.Timestamp(w[0])
    if w[1] is not None:
        m = m & (index <= pd.Timestamp(w[1]))
    return np.asarray(m)


def window_stats(
    r_cfg: np.ndarray, r_orig: np.ndarray, rf: np.ndarray, mask: np.ndarray
) -> dict[str, float]:
    rc, ro, f = r_cfg[mask], r_orig[mask], rf[mask]
    k = samevol_k(rc, ro)
    xs = samevol_excess(rc, f, k)
    n = len(rc)
    ann_ret = float(np.prod(1.0 + rc) ** (252.0 / n) - 1.0) if n else float("nan")
    return {
        "sr_raw": sharpe(rc - f),
        "sr_samevol": sharpe(xs),
        "dsr": sharpe(xs) - sharpe(ro - f),
        "k": k,
        "rho": float(np.corrcoef(rc, ro)[0, 1]) if np.std(rc) > 0 and np.std(ro) > 0 else 1.0,
        "ann_ret": ann_ret,
        "ann_vol": float(np.std(rc, ddof=1) * np.sqrt(252.0)),
        "maxdd_raw": max_drawdown(rc),
        "maxdd_samevol": max_drawdown(xs + f),
        "es975_samevol": es975(xs),
    }


def replay_stats(
    r_cfg: np.ndarray,
    r_orig: np.ndarray,
    rf: np.ndarray,
    index: pd.DatetimeIndex,
    k_recent: float,
    replays: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    sv = samevol_excess(r_cfg, rf, k_recent) + rf
    out = {}
    for name, rp in replays.items():
        m = np.asarray((index > pd.Timestamp(rp["peak"])) & (index <= pd.Timestamp(rp["trough"])))
        seg = sv[m]
        out[name] = {
            "ret_samevol": float(np.prod(1.0 + seg) - 1.0),
            "maxdd": max_drawdown(seg),
        }
    return out


def stationary_indices(t: int, draws: int, mean_block: int, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / mean_block
    idx = np.empty((draws, t), dtype=np.int64)
    idx[:, 0] = rng.integers(0, t, draws)
    new = rng.random((draws, t)) < p
    starts = rng.integers(0, t, (draws, t))
    for j in range(1, t):
        idx[:, j] = np.where(new[:, j], starts[:, j], (idx[:, j - 1] + 1) % t)
    return idx


# --------------------------------------------------------------------------------------
# Context: panel, legs, risk statistics, sleeves
# --------------------------------------------------------------------------------------
class Inst:
    """One sleeve instance (ORIG weights and engine parameters)."""

    def __init__(self, name, w2, cols2, sig, target, boost, boost_target, index):
        self.name, self.cols2, self.sig = name, cols2, sig
        self.w2 = w2  # n x len(cols2), padded with zero substitute columns
        self.target, self.boost, self.boost_target = target, boost, boost_target
        pos = {d: i for i, d in enumerate(index)}
        n = len(index)
        self.starts = sorted({pos[d] + 1 for d in sig if pos[d] + 1 < n})
        self.eff0: np.ndarray | None = None


class Ctx:
    pass


def load_context(last_session: str) -> Ctx:
    c = Ctx()
    base.WARMUP_START = tranche.PANEL_START
    base.HOLD_END = last_session
    mod = screen_batch.load_batch_module("h20260928_20_recent_opt")
    cands = screen_batch.candidates_from_module(mod)
    c2 = next(x for x in cands if x.id == "C2")
    symbols = sorted(set(salvage.symbols()) | set(c2.universe) | set(EXTRA_SYMBOLS))
    close, open_ = base.load_panel(symbols)
    c.symbols = list(close.columns)
    c.index = close.index
    c.close = close
    lo, lc = salvage.legs(close, open_)
    # overlay legs share the underlying legs
    for th in [THEME, *PLACEBO_THEMES]:
        lo[f"OVT_{th}"] = lo[th]
        lc[f"OVT_{th}"] = lc[th]
    for name, src in (("OVM", MKT), ("OVS", "SOXS"), ("OVU", "UPRO")):
        lo[name] = lo[src]
        lc[name] = lc[src]
    c.lo, c.lc = lo, lc
    c.rf = (close[RF] / close[RF].shift(1) - 1.0).fillna(0.0).to_numpy()
    ret = close.pct_change(fill_method=None)
    c.rs = RiskStats(ret)
    c.views = {th: ThemeView(c.rs, th) for th in [THEME]}
    c.ci = c.rs.ci
    c.K = c.rs.K
    c.cash_k = {c.ci[CASH], c.ci[RF]}
    c.shy_k = c.ci[CASH]
    c.sub_k = {}
    for col, i in c.ci.items():
        if col in NO_MOVE or col in (CASH, RF):
            c.sub_k[i] = i
        else:
            c.sub_k[i] = c.ci[SUB.get(col, MKT)]
    c.lev2 = np.array([col in LEV2 for col in c.rs.cols])
    c.lev3 = np.array([col in LEV3 for col in c.rs.cols])
    c.boost = salvage.boost_window(salvage.dip_signal(close), tranche.S3_BOOST_HOLD)
    c.insts: dict[str, Inst] = {}
    n = len(c.index)
    one = np.ones(n)

    def mk(name, weights, sig, target, boost, bt):
        cols = list(weights.columns)
        extra = [x for x in (MKT, "SSO", "UPRO") if x not in cols]
        w = weights.copy()
        for x in extra:
            w[x] = 0.0
        inst = Inst(name, w.to_numpy(dtype=float), list(w.columns), sig, target, boost, bt, c.index)
        inst.kidx = np.array([c.ci[x] for x in inst.cols2])
        inst.shy_pos = inst.cols2.index(CASH)
        inst.eff0 = eff_of(c, inst, inst.w2)
        return inst

    c.mk = mk
    c.one = one
    for o in ALL_OFFSETS:
        w, sig = tranche.s3_weights(close, o)
        c.insts[f"S3_{o}"] = mk(
            f"S3_{o}", w, sig, tranche.S3_TARGET, c.boost, tranche.S3_BOOST_TARGET
        )
    wc, sigc = lane.weights_frame(close, c2, 0)
    c.insts["C2"] = mk("C2", wc, sigc, None, None, None)
    w1, sig1 = salvage.sleeve_weights(close, "s1")
    c.insts["S1"] = mk("S1", w1, sig1, None, None, None)
    w2_, sig2 = salvage.sleeve_weights(close, "s2")
    c.insts["S2"] = mk("S2", w2_, sig2, combo.S2_TARGET, None, None)
    return c


def eff_of(c: Ctx, inst: Inst, w2: np.ndarray) -> np.ndarray:
    wdf = pd.DataFrame(w2, index=c.index, columns=inst.cols2)
    gross, _ = salvage.simulate(wdf, c.lo, c.lc, c.one, 0.0)
    scale = salvage.vol_scale(c.index, inst.sig, gross, inst.target, inst.boost, inst.boost_target)
    return tranche.effective_weights(wdf, scale)


def sim(c: Ctx, eff: np.ndarray, cols: list[str], cost: float) -> tuple[np.ndarray, np.ndarray]:
    r, t = tranche.simulate_effective(eff, cols, c.lo, c.lc, cost)
    return r.to_numpy(), t.to_numpy()


def to_kspace(c: Ctx, eff: np.ndarray, cols: list[str]) -> np.ndarray:
    wk = np.zeros((len(eff), c.K))
    for j, col in enumerate(cols):
        if col.startswith("OVT_"):
            name = col[4:]
        else:
            name = {"OVM": MKT, "OVS": "SOXS", "OVU": "UPRO"}.get(col, col)
        wk[:, c.ci[name]] += eff[:, j]
    return wk


def risky_k(c: Ctx, wk: np.ndarray) -> np.ndarray:
    out = wk.copy()
    out[..., list(c.cash_k)] = 0.0
    return out


def finish(
    c: Ctx,
    eff: np.ndarray,
    cols: list[str],
    extra: dict[str, np.ndarray] | None = None,
    shy_red: np.ndarray | None = None,
    debit: np.ndarray | None = None,
) -> dict[str, Any]:
    e2 = eff.copy()
    if shy_red is not None:
        e2[:, cols.index(CASH)] -= shy_red
    cols2 = list(cols)
    if extra:
        e2 = np.hstack([e2, np.column_stack(list(extra.values()))])
        cols2 += list(extra.keys())
    r10, turn = sim(c, e2, cols2, COST_PRIMARY)
    r20, _ = sim(c, e2, cols2, COST_2X)
    dch = (debit * DEBIT_RATE / 252.0) if debit is not None else np.zeros(len(eff))
    short = np.clip(-e2, 0.0, None).sum(axis=1)
    return {
        "r10": r10 - dch,
        "r20": r20 - dch - short * SHORT_BORROW_2X / 252.0,
        "turn": turn,
        "debit_charge": dch,
        "eff2": e2,
        "cols2": cols2,
    }


# --------------------------------------------------------------------------------------
# Variants: ORIG, CAP, hedge overlays
# --------------------------------------------------------------------------------------
def orig_variant(c: Ctx, inst: Inst) -> dict[str, Any]:
    v = finish(c, inst.eff0, inst.cols2)
    v["events"] = []
    return v


def cap_variant(c: Ctx, inst: Inst, view: ThemeView, level: float) -> dict[str, Any]:
    w = inst.w2.copy()
    n = len(w)
    events = []
    st_list = inst.starts
    for j, st in enumerate(st_list):
        en = st_list[j + 1] if j + 1 < len(st_list) else n
        wk = np.zeros(c.K)
        wk[inst.kidx] = w[st]
        wk = risky_k(c, wk)
        new, s, info = cap_row(view, st - 1, wk, level, c.sub_k, c.cash_k)
        if s > 0.0 or info["bound"]:
            row = w[st].copy()
            risky_pos = [p for p, col in enumerate(inst.cols2) if col not in (CASH, RF)]
            row[risky_pos] = new[inst.kidx[risky_pos]]
            w[st:en] = row
        events.append(
            {
                "date": str(c.index[st - 1].date()),
                "valid": info["valid"],
                "trs": info["trs"],
                "bound": bool(info["bound"]),
                "val": float(s),
                "flag": bool(info["flag"]),
            }
        )
    eff = eff_of(c, inst, w)
    v = finish(c, eff, inst.cols2)
    v["events"] = events
    return v


def update_sessions(eff: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    d = np.abs(np.diff(eff, axis=0)).max(axis=1)
    return np.flatnonzero(d > tol) + 1


def hedge_raw(c: Ctx, inst: Inst, view: ThemeView, level: float, mode: str) -> dict[str, Any]:
    """Raw (lambda = 1) hedge schedule on the sleeve's ORIG effective weights.
    mode "h1": theme short + SPY long.  mode "h2": SOXS + UPRO (cash account)."""
    eff = inst.eff0
    n = len(eff)
    hs, bt = np.zeros(n), np.zeros(n)
    ns, us = np.zeros(n), np.zeros(n)
    E = update_sessions(eff)
    events = []
    iS, iU = c.ci["SOXS"], c.ci["UPRO"]
    for j, e in enumerate(E):
        en = E[j + 1] if j + 1 < len(E) else n
        t = int(e) - 1
        wk = np.zeros(c.K)
        wk[inst.kidx] = eff[e]
        wk = risky_k(c, wk)
        p = view.parts(wk, t)
        ev = {
            "e": int(e),
            "date": str(c.index[e].date()),
            "valid": p is not None,
            "trs": float("nan"),
            "bound": False,
            "val": 0.0,
            "lam": None,
            "ach": None,
            "fits": None,
            "neg": False,
        }
        if p is not None:
            ev["trs"] = float(p["trs"][0])
            h = h1_size(p, view.vs[t], view.vf[t], level)
            if h != 0.0:
                ev["bound"] = True
                ev["val"] = float(h)
                ev["t"] = t
                if mode == "h1":
                    hs[e:en] = h
                    bt[e:en] = view.beta[t]
                else:
                    ld = view.asset_loadings(t)
                    s = view.rs.cov[t]
                    sol = h2_solve(
                        ld[iS],
                        s[iS, view.i_m] / view.vs[t],
                        ld[iU],
                        s[iU, view.i_m] / view.vs[t],
                        h,
                    )
                    if sol is None:
                        ev["neg"] = True
                    else:
                        nn, uu = sol
                        shy = float(eff[e, inst.shy_pos])
                        need = nn + uu
                        ev["fits"] = bool(need <= shy + 1e-12)
                        if need > shy and need > 0:
                            nn, uu = nn * shy / need, uu * shy / need
                        ns[e:en], us[e:en] = nn, uu
                        wk2 = wk.copy()
                        wk2[iS] += nn
                        wk2[iU] += uu
                        ev["ach"] = float(view.parts(wk2, t)["trs"][0])
        events.append(ev)
    return {"h": hs, "beta": bt, "n": ns, "u": us, "events": events, "E": E}


def account_lambdas(
    c: Ctx,
    view: ThemeView,
    members: list[tuple[Inst, dict[str, Any], float]],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Common lambda path for an account made of sleeves (inst, raw hedge, account weight)."""
    n = c.rs.T
    ev_set: set[int] = set()
    for _, raw, _ in members:
        ev_set.update(int(e) for e in raw["E"])
    E = sorted(ev_set)
    lam_t = np.ones(n)
    recs = []
    i_th, i_m = view.i_th, c.ci[MKT]
    for j, e in enumerate(E):
        en = E[j + 1] if j + 1 < len(E) else n
        base_pos = []
        for inst, raw, a in members:
            pos = np.zeros(c.K)
            pos[inst.kidx] = inst.eff0[e]
            base_pos.append((pos, -raw["h"][e], raw["h"][e] * raw["beta"][e], a))
        active = any(abs(o_t) > 0 for _, o_t, _, _ in base_pos)
        if not active:
            continue

        def feasible(lam: float, base_pos=base_pos) -> bool:
            tot = np.zeros(c.K)
            for pos, o_t, o_m, a in base_pos:
                p2 = pos.copy()
                lt, lm = lam * o_t, lam * o_m
                need = max(-lt, 0.0) + max(lm, 0.0)
                p2[c.shy_k] -= min(p2[c.shy_k], need)
                p2[i_th] += lt
                p2[i_m] += lm
                tot += a * p2
            return margin_ok(tot, c.lev2, c.lev3)

        lam = bisect_lambda(feasible)
        lam_t[e:en] = lam
        recs.append({"e": e, "lam": float(lam), "feasible_unscaled": bool(lam >= 1.0 - 1e-9)})
    return lam_t, recs


def h1_variant(
    c: Ctx,
    inst: Inst,
    view: ThemeView,
    raw: dict[str, Any],
    lam_t: np.ndarray,
    level: float,
) -> dict[str, Any]:
    eff = inst.eff0
    o_t = -lam_t * raw["h"]
    o_m = lam_t * raw["h"] * raw["beta"]
    need = np.clip(-o_t, 0.0, None) + np.clip(o_m, 0.0, None)
    shy = eff[:, inst.shy_pos]
    red = np.minimum(shy, need)
    debit = need - red
    extra = {f"OVT_{view.theme}": o_t, "OVM": o_m}
    v = finish(c, eff, inst.cols2, extra, red, debit)
    events = []
    for ev in raw["events"]:
        ev = dict(ev)
        if ev["bound"]:
            e = ev["e"]
            lam = float(lam_t[e])
            ev["lam"] = lam
            wk = risky_k(c, to_kspace(c, eff[e : e + 1], inst.cols2))[0]
            wk[view.i_th] -= lam * ev["val"]
            wk[c.ci[MKT]] += lam * ev["val"] * view.beta[ev["t"]]
            p = view.parts(wk, ev["t"])
            ev["ach"] = float(p["trs"][0]) if p is not None else None
            ev["val"] = lam * ev["val"]
        events.append(ev)
    v["events"] = events
    return v


def h2_variant(c: Ctx, inst: Inst, view: ThemeView, raw: dict[str, Any]) -> dict[str, Any]:
    eff = inst.eff0
    red = raw["n"] + raw["u"]
    v = finish(c, eff, inst.cols2, {"OVS": raw["n"], "OVU": raw["u"]}, red, None)
    v["events"] = raw["events"]
    return v


def attach_wk(c: Ctx, v: dict[str, Any]) -> None:
    v["wk"] = to_kspace(c, v["eff2"], v["cols2"])


# --------------------------------------------------------------------------------------
# Objects (linear combinations of sleeve variants)
# --------------------------------------------------------------------------------------
def combine(parts: list[tuple[float, dict[str, Any]]], with_wk: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("r10", "r20", "turn", "debit_charge"):
        out[key] = sum(w * v[key] for w, v in parts)
    out["events"] = [ev for _, v in parts for ev in v.get("events", [])]
    if with_wk:
        out["wk"] = sum(w * v["wk"] for w, v in parts)
    return out


def objects_for(
    s3_vars: list[dict[str, Any]] | None,
    c2_var: dict[str, Any] | None,
    with_wk: bool,
) -> dict[str, dict[str, Any]]:
    objs: dict[str, dict[str, Any]] = {}
    if s3_vars is not None:
        objs["S3"] = combine([(1.0 / len(s3_vars), v) for v in s3_vars], with_wk)
    if c2_var is not None:
        objs["C2"] = combine([(1.0, c2_var)], with_wk)
    if s3_vars is not None and c2_var is not None:
        objs["O1"] = combine([(W_S3, objs["S3"]), (W_C2, objs["C2"])], with_wk)
    return objs


# --------------------------------------------------------------------------------------
# Evaluation of objects and configurations
# --------------------------------------------------------------------------------------
def kdaily(c: Ctx) -> tuple[np.ndarray, np.ndarray]:
    return (
        c.lo[c.rs.cols].to_numpy(dtype=float),
        c.lc[c.rs.cols].to_numpy(dtype=float),
    )


def eval_series(
    c: Ctx,
    cfg: dict[str, Any],
    orig: dict[str, Any],
    replays: dict[str, Any],
    masks: dict[str, np.ndarray],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for w, m in masks.items():
        out[w] = window_stats(cfg["r10"], orig["r10"], c.rf, m)
    k_rec = out["recent"]["k"]
    out["replay"] = replay_stats(cfg["r10"], orig["r10"], c.rf, c.index, k_rec, replays)
    out["cost2x"] = {
        "dsr_recent": window_stats(cfg["r20"], orig["r20"], c.rf, masks["recent"])["dsr"]
    }
    return out


def replay_mean_change(ev: dict[str, Any], ev_orig: dict[str, Any]) -> float:
    return float(
        np.mean(
            [
                ev["replay"][r]["ret_samevol"] - ev_orig["replay"][r]["ret_samevol"]
                for r in ev["replay"]
            ]
        )
    )


def es_rel(ev: dict[str, Any], ev_orig: dict[str, Any]) -> float:
    return abs(ev["stress"]["es975_samevol"]) / abs(ev_orig["stress"]["es975_samevol"])


def event_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [e for e in events if e.get("valid")]
    bound = [e for e in valid if e.get("bound")]
    lam = [e["lam"] for e in bound if e.get("lam") is not None]
    ach = [e["ach"] for e in bound if e.get("ach") is not None]
    fits = [e["fits"] for e in bound if e.get("fits") is not None]
    flagged = [e["date"] for e in valid if e.get("flag")]
    return {
        "n_updates": len(events),
        "n_valid": len(valid),
        "n_skipped_no_window": len(events) - len(valid),
        "bind_rate": len(bound) / len(valid) if valid else float("nan"),
        "mean_s_or_h": float(np.mean([e["val"] for e in valid])) if valid else float("nan"),
        "flagged_dates": flagged,
        "feasibility_rate": (
            float(np.mean([x >= 1.0 - 1e-9 for x in lam]))
            if lam
            else (float(np.mean(fits)) if fits else None)
        ),
        "lambda_mean": float(np.mean(lam)) if lam else None,
        "achieved_trs_mean": float(np.mean(ach)) if ach else None,
        "h2_negative_solves": int(sum(1 for e in bound if e.get("neg"))),
    }


def theme_block(
    c: Ctx,
    view: ThemeView,
    obj: dict[str, Any],
    orig: dict[str, Any],
    orig_trs: np.ndarray,
    level: float | None,
    masks: dict[str, np.ndarray],
) -> dict[str, Any]:
    trs = view.daily_trs(obj["wk"])
    ok = np.isfinite(trs) & np.isfinite(orig_trs)
    rec = masks["recent"] & ok
    years = masks["recent"].sum() / 252.0
    out = event_stats(obj["events"])
    out.update(
        {
            "trs_mean_before": float(orig_trs[ok].mean()),
            "trs_mean_after": float(trs[ok].mean()),
            "trs_mean_before_recent": float(orig_trs[rec].mean()),
            "trs_mean_after_recent": float(trs[rec].mean()),
            "share_days_over_c_plus_005": (
                float((trs[ok] > level + 0.05).mean()) if level is not None else None
            ),
            "share_days_over_c_plus_005_recent": (
                float((trs[rec] > level + 0.05).mean()) if level is not None else None
            ),
            "turnover_added_per_yr": float(
                (obj["turn"][masks["recent"]].sum() - orig["turn"][masks["recent"]].sum()) / years
            ),
            "debit_cost_bp_yr": float(obj["debit_charge"][masks["recent"]].sum() / years * 1e4),
        }
    )
    out["cost_added_bp_yr"] = out["turnover_added_per_yr"] * COST_PRIMARY
    return out


def theme_pnl_share(c: Ctx, view: ThemeView, wk: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    lo_k, lc_k = kdaily(c)
    prev = np.vstack([np.zeros((1, c.K)), wk[:-1]])
    gross = np.nansum(prev * lo_k, axis=1) + np.nansum(wk * lc_k, axis=1)
    w = risky_k(c, wk)
    n = len(wk)
    b_th, b_m = np.full(n, np.nan), np.full(n, np.nan)
    ft = np.full(n, np.nan)
    rth, rm = c.R[:, view.i_th], c.R[:, view.i_m]
    for t in range(1, n):
        if not view.ok[t - 1]:
            continue
        if np.any((w[t] != 0.0) & ~c.rs.valid[t - 1]):
            continue
        b_th[t] = float(w[t] @ view.cf[t - 1] / view.vf[t - 1])
        b_m[t] = float(w[t] @ c.rs.cov[t - 1][:, view.i_m] / view.vs[t - 1])
        ft[t] = rth[t] - view.beta[t - 1] * rm[t]
    m = mask & np.isfinite(b_th) & np.isfinite(ft) & np.isfinite(rm)
    g = float(gross[mask].sum())
    return {
        "theme_pnl": float((b_th[m] * ft[m]).sum()),
        "market_pnl": float((b_m[m] * rm[m]).sum()),
        "gross_pnl": g,
        "theme_share": float((b_th[m] * ft[m]).sum() / g) if g else float("nan"),
        "market_share": float((b_m[m] * rm[m]).sum() / g) if g else float("nan"),
        "n_days": int(m.sum()),
    }


def decision_rule(
    grid: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """grid[version][tag] = {dsr_recent, replay_mean_change, es_stress_rel}. Frozen rule
    (hypotheses.md section 5)."""
    out: dict[str, Any] = {}
    selected: dict[str, float | None] = {}
    for v, byc in grid.items():
        sel = None
        out[v] = {}
        for c in LEVELS:  # loosest -> tightest
            row = byc[f"{int(round(c * 100))}"]
            cost_ok = bool(row["dsr_recent"] >= -0.10)
            benefit = bool(row["replay_mean_change"] >= 0.010 or row["es_stress_rel"] <= 0.95)
            looser = [byc[f"{int(round(x * 100))}"]["dsr_recent"] >= -0.10 for x in LEVELS if x > c]
            monotone = bool(cost_ok and all(looser))
            out[v][f"{int(round(c * 100))}"] = {
                "cost_ok": cost_ok,
                "benefit": benefit,
                "monotone": monotone,
                "dsr_recent": row["dsr_recent"],
                "replay_mean_change": row["replay_mean_change"],
                "es_stress_rel": row["es_stress_rel"],
            }
            if cost_ok and benefit and monotone:
                sel = c  # tightest wins (levels iterate loose -> tight)
        selected[v] = sel
        out[v]["selected"] = sel
    pilot, alts = None, []
    for v in ("CAP", "H2F", "H1F"):
        if selected.get(v) is not None:
            pilot = {"version": v, "c": selected[v]}
            break
    if pilot is not None and pilot["version"] == "CAP":
        for v in ("H2F", "H1F"):
            if selected.get(v) is not None and selected[v] < pilot["c"]:
                alts.append({"version": v, "c": selected[v]})
    if pilot is not None:
        status = "pilot_limit_selected"
    elif any(out[v]["40"]["cost_ok"] for v in ("CAP", "H2F", "H1F")):
        status = "cost_ok_no_benefit_monitor_only"
    else:
        status = "no_level_within_cost"
    return {"decision": out, "pilot_limit": pilot, "alternatives": alts, "status": status}


def sector_median(vals: list[float]) -> float:
    return float(np.median(vals))


# --------------------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------------------
def code_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def stage_build() -> int:
    import os

    import duckdb

    os.chdir(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='300MB'")
    last = con.execute(
        "SELECT max(timestamp::DATE) FROM read_parquet('data/sip/daily/2026/*.parquet')"
        " WHERE symbol='SPY'"
    ).fetchone()[0]
    con.close()
    last_session = str(last)
    log(f"build: last SPY session {last_session}")
    c = load_context(last_session)
    log(f"panel {c.index[0].date()}..{c.index[-1].date()} symbols={len(c.symbols)}")
    ident: dict[str, Any] = {}
    boost = c.boost
    # (i) S3 offsets: new ORIG path vs tranche engine
    d1 = {}
    for o in S3_OFFSETS:
        eff_ref, cols_ref = tranche.offset_effective(c.close, c.lo, c.lc, o, boost)
        ref, _ = tranche.simulate_effective(eff_ref, cols_ref, c.lo, c.lc, COST_PRIMARY)
        new = orig_variant(c, c.insts[f"S3_{o}"])["r10"]
        d1[str(o)] = float(np.max(np.abs(new - ref.to_numpy())))
    ident["i_s3_offsets_vs_tranche_max_abs_diff"] = d1
    # (ii) S3 o0, (iv) S1, S2 vs combo.sleeve_returns
    sr = combo.sleeve_returns(c.close, c.lo, c.lc, COST_PRIMARY)
    ident["ii_s3_o0_vs_combo_max_abs_diff"] = float(
        np.max(np.abs(orig_variant(c, c.insts["S3_0"])["r10"] - sr["s3"].to_numpy()))
    )
    ident["iv_s1_vs_combo_max_abs_diff"] = float(
        np.max(np.abs(orig_variant(c, c.insts["S1"])["r10"] - sr["s1"].to_numpy()))
    )
    ident["iv_s2_vs_combo_max_abs_diff"] = float(
        np.max(np.abs(orig_variant(c, c.insts["S2"])["r10"] - sr["s2"].to_numpy()))
    )
    # (iii) C2 vs stored repaired file
    stored = pd.read_parquet(C2_FILE)
    if "d" in stored.columns:
        stored.index = stored["d"]
    stored.index = pd.to_datetime(stored.index)
    c2 = pd.Series(orig_variant(c, c.insts["C2"])["r10"], index=c.index)
    common = c2.index.intersection(stored.index)
    common = common[common <= pd.Timestamp("2026-09-17")]
    diff = float(
        np.max(np.abs(c2.loc[common].to_numpy() - stored.loc[common, "C2__o00__net10"].to_numpy()))
    )
    ident["iii_c2_vs_stored_max_abs_diff"] = diff
    ident["iii_overlap"] = {
        "start": str(common[0].date()),
        "end": str(common[-1].date()),
        "n": int(len(common)),
    }
    tol_ok = (
        all(v <= 1e-12 for v in d1.values())
        and ident["ii_s3_o0_vs_combo_max_abs_diff"] <= 1e-12
        and ident["iv_s1_vs_combo_max_abs_diff"] <= 1e-12
        and ident["iv_s2_vs_combo_max_abs_diff"] <= 1e-12
        and diff <= 1e-10
    )
    ident["pass"] = bool(tol_ok)
    log(f"identity: {json.dumps(ident)}")
    build: dict[str, Any] = {
        "last_session": last_session,
        "symbols": c.symbols,
        "panel_first_session": str(c.index[0].date()),
        "identity": ident,
        "code_sha256": code_sha(),
    }
    if not tol_ok:
        build["mechanical_status"] = "identity_failed"
        build["frozen_at_utc"] = datetime.now(UTC).isoformat()
        (OUT / "build.json").write_text(json.dumps(build, indent=2) + "\n")
        log("identity failed; stopping")
        return 3
    smh = c.close[THEME]
    replays = {}
    for name, (a, b, end) in REPLAY_BOXES.items():
        seg = smh.loc[(smh.index >= a) & (smh.index <= b)]
        peak = seg.idxmax()
        after = smh.loc[(smh.index > peak) & (smh.index <= end)]
        trough = after.idxmin()
        replays[name] = {
            "peak": str(peak.date()),
            "trough": str(trough.date()),
            "smh_peak_close": float(smh.loc[peak]),
            "smh_trough_close": float(smh.loc[trough]),
            "smh_ret_peak_to_trough": float(smh.loc[trough] / smh.loc[peak] - 1.0),
        }
    build["replays"] = replays
    build["frozen_at_utc"] = datetime.now(UTC).isoformat()
    (OUT / "build.json").write_text(json.dumps(build, indent=2) + "\n")
    log(
        f"build.json written; replays {json.dumps({k: [v['peak'], v['trough']] for k, v in replays.items()})}"
    )
    return 0


def tag(c: float) -> str:
    return f"{int(round(c * 100))}"


def make_variant(
    c: Ctx,
    view: ThemeView,
    version: str,
    level: float,
    k: str,
    raws: dict[str, dict[str, Any]],
    lam_t: np.ndarray | None,
) -> dict[str, Any]:
    inst = c.insts[k]
    if version == "CAP":
        v = cap_variant(c, inst, view, level)
    elif version == "H2F":
        v = h2_variant(c, inst, view, raws[k])
    else:
        v = h1_variant(c, inst, view, raws[k], lam_t, level)
    attach_wk(c, v)
    return v


def stage_run() -> int:
    import os

    os.chdir(ROOT)
    t0 = time.time()
    bpath = OUT / "build.json"
    if not bpath.exists():
        raise SystemExit("build.json missing; run --stage build first")
    build = json.loads(bpath.read_text())
    if not build.get("identity", {}).get("pass"):
        raise SystemExit("identity did not pass; refusing to run")
    log(f"run start (build frozen_at_utc {build['frozen_at_utc']})")
    c = load_context(build["last_session"])
    c.R = c.close.pct_change(fill_method=None).to_numpy(dtype=float)
    replays = build["replays"]
    masks = {w: window_mask(c.index, win) for w, win in WINDOWS.items()}
    view = c.views[THEME]
    CACHE.mkdir(parents=True, exist_ok=True)

    # ---- ORIG ------------------------------------------------------------------------
    orig_v = {k: orig_variant(c, c.insts[k]) for k in c.insts}
    for k in ["S3_0", "S3_4", "S3_8", "S3_12", "S3_16", "C2", "S1", "S2"]:
        attach_wk(c, orig_v[k])
    s3_orig = [orig_v[f"S3_{o}"] for o in S3_OFFSETS]
    orig_objs = objects_for(s3_orig, orig_v["C2"], True)
    orig_objs["S1"] = combine([(1.0, orig_v["S1"])], True)
    orig_objs["S2"] = combine([(1.0, orig_v["S2"])], True)
    orig_trs = {k: view.daily_trs(v["wk"]) for k, v in orig_objs.items()}
    log("ORIG built")

    configs: dict[str, dict[str, Any]] = {k: {} for k in ("O1", "S3", "C2", "S1", "S2")}
    series_store: dict[str, np.ndarray] = {}
    for k, v in orig_objs.items():
        ev = eval_series(c, v, v, replays, masks)
        configs[k]["ORIG"] = ev
        configs[k]["ORIG"]["theme"] = {
            "trs_mean_recent": float(np.nanmean(orig_trs[k][masks["recent"]])),
            "trs_mean_full": float(np.nanmean(orig_trs[k])),
        }
        series_store[f"{k}__ORIG__r10"] = v["r10"]
        series_store[f"{k}__ORIG__r20"] = v["r20"]
    orig_o1_by_offset = {
        o: W_S3 * orig_v[f"S3_{o}"]["r10"] + W_C2 * orig_v["C2"]["r10"] for o in ALL_OFFSETS
    }
    # recent-window O1 series for bootstrap
    rec = masks["recent"]
    n_rec = int(rec.sum())
    rng = np.random.default_rng(BOOT_SEED)
    boot_idx = stationary_indices(n_rec, BOOT_DRAWS, BOOT_BLOCK, rng)
    x0_rec = orig_objs["O1"]["r10"][rec] - c.rf[rec]
    sr0_b = np.array([sharpe(x0_rec[i]) for i in boot_idx])

    bootstrap: dict[str, Any] = {}
    per_offset: dict[str, Any] = {}
    s3_21: dict[str, Any] = {}
    grid_o1: dict[str, dict[str, dict[str, Any]]] = {}
    grid_s3: dict[str, dict[str, dict[str, Any]]] = {}
    versions = ["CAP", "H2F", "H1F", "H1U"]

    def do_boot(cfg_id: str, o1: dict[str, Any]) -> None:
        k = window_stats(o1["r10"], orig_objs["O1"]["r10"], c.rf, rec)["k"]
        xs = samevol_excess(o1["r10"][rec], c.rf[rec], k)
        srs = np.array([sharpe(xs[i]) for i in boot_idx])
        d = srs - sr0_b
        bootstrap[cfg_id] = {
            "p10": float(np.nanpercentile(d, 10)),
            "p90": float(np.nanpercentile(d, 90)),
            "p2_5": float(np.nanpercentile(d, 2.5)),
            "p97_5": float(np.nanpercentile(d, 97.5)),
        }

    s3_keys = [f"S3_{o}" for o in S3_OFFSETS]
    for version in versions:
        grid_o1[version], grid_s3[version] = {}, {}
        for lv in LEVELS:
            cfg_id = f"{version}_{tag(lv)}"
            raws = {}
            if version in ("H1F", "H1U"):
                raws = {k: hedge_raw(c, c.insts[k], view, lv, "h1") for k in [*s3_keys, "C2"]}
            elif version == "H2F":
                raws = {k: hedge_raw(c, c.insts[k], view, lv, "h2") for k in [*s3_keys, "C2"]}

            if version == "H1F":
                members_s3 = [(c.insts[k], raws[k], 1.0 / 5.0) for k in s3_keys]
                lam_s3, rec_s3 = account_lambdas(c, view, members_s3)
                lam_c2, rec_c2 = account_lambdas(c, view, [(c.insts["C2"], raws["C2"], 1.0)])
                lam_pl, rec_pl = account_lambdas(
                    c,
                    view,
                    [
                        *[(c.insts[k], raws[k], W_S3 / 5.0) for k in s3_keys],
                        (c.insts["C2"], raws["C2"], W_C2),
                    ],
                )
                s3_alone = [make_variant(c, view, version, lv, k, raws, lam_s3) for k in s3_keys]
                c2_alone = make_variant(c, view, version, lv, "C2", raws, lam_c2)
                s3_pilot = [make_variant(c, view, version, lv, k, raws, lam_pl) for k in s3_keys]
                c2_pilot = make_variant(c, view, version, lv, "C2", raws, lam_pl)
                objs = {
                    "S3": objects_for(s3_alone, None, True)["S3"],
                    "C2": objects_for(None, c2_alone, True)["C2"],
                    "O1": objects_for(s3_pilot, c2_pilot, True)["O1"],
                }
                s3_for_offsets, c2_for_offsets = s3_pilot, c2_pilot
            else:
                lam1 = np.ones(c.rs.T)
                s3_list = [make_variant(c, view, version, lv, k, raws, lam1) for k in s3_keys]
                c2_v = make_variant(c, view, version, lv, "C2", raws, lam1)
                objs = objects_for(s3_list, c2_v, True)
                s3_for_offsets, c2_for_offsets = s3_list, c2_v
                if version == "CAP":
                    for k_, key in (("S1", "S1"), ("S2", "S2")):
                        vv = cap_variant(c, c.insts[key], view, lv)
                        attach_wk(c, vv)
                        objs[k_] = combine([(1.0, vv)], True)
            for name, obj in objs.items():
                ev = eval_series(c, obj, orig_objs[name], replays, masks)
                ev["theme"] = theme_block(c, view, obj, orig_objs[name], orig_trs[name], lv, masks)
                configs[name][cfg_id] = ev
                series_store[f"{name}__{cfg_id}__r10"] = obj["r10"]
                series_store[f"{name}__{cfg_id}__r20"] = obj["r20"]
            if version == "H1F":
                configs["O1"][cfg_id]["theme"]["account_lambda_records"] = {
                    "pilot_n": len(rec_pl),
                    "s3_alone_n": len(rec_s3),
                    "c2_alone_n": len(rec_c2),
                }
                configs["S3"][cfg_id]["theme"]["lambda_mean_account"] = (
                    float(np.mean([r["lam"] for r in rec_s3])) if rec_s3 else None
                )
                configs["C2"][cfg_id]["theme"]["lambda_mean_account"] = (
                    float(np.mean([r["lam"] for r in rec_c2])) if rec_c2 else None
                )
            # decision grids
            for name, g in (("O1", grid_o1), ("S3", grid_s3)):
                e = configs[name][cfg_id]
                e0 = configs[name]["ORIG"]
                g[version][tag(lv)] = {
                    "dsr_recent": e["recent"]["dsr"],
                    "replay_mean_change": replay_mean_change(e, e0),
                    "es_stress_rel": es_rel(e, e0),
                }
            do_boot(cfg_id, objs["O1"])
            # per-offset (5) pilot dsr
            po = {}
            for j, o in enumerate(S3_OFFSETS):
                o1 = W_S3 * s3_for_offsets[j]["r10"] + W_C2 * c2_for_offsets["r10"]
                po[str(o)] = window_stats(o1, orig_o1_by_offset[o], c.rf, rec)["dsr"]
            per_offset[cfg_id] = po
            if version == "CAP":
                d21 = {}
                for o in ALL_OFFSETS:
                    if o in S3_OFFSETS:
                        s3o = s3_for_offsets[S3_OFFSETS.index(o)]["r10"]
                    else:
                        s3o = cap_variant(c, c.insts[f"S3_{o}"], view, lv)["r10"]
                    o1 = W_S3 * s3o + W_C2 * c2_for_offsets["r10"]
                    d21[str(o)] = window_stats(o1, orig_o1_by_offset[o], c.rf, rec)["dsr"]
                s3_21[tag(lv)] = {
                    "by_offset": d21,
                    "min": float(min(d21.values())),
                    "median": float(np.median(list(d21.values()))),
                    "max": float(max(d21.values())),
                }
            log(f"{cfg_id} done (O1 dsr_recent {configs['O1'][cfg_id]['recent']['dsr']:+.3f})")

    # ---- theme P&L share (Q4) -------------------------------------------------------
    pnl = {k: theme_pnl_share(c, view, orig_objs[k]["wk"], masks["recent"]) for k in orig_objs}
    log("theme pnl share done")

    # ---- placebos --------------------------------------------------------------------
    placebos: dict[str, Any] = {}
    for j in PLACEBO_THEMES:
        vj = ThemeView(c.rs, j)
        placebos[j] = {k: {} for k in ("O1", "S3", "C2")}
        for version in ("CAP", "H1U"):
            for obj_name in placebos[j]:
                placebos[j][obj_name][version] = {}
            for lv in LEVELS:
                raws = {}
                if version == "H1U":
                    raws = {k: hedge_raw(c, c.insts[k], vj, lv, "h1") for k in [*s3_keys, "C2"]}
                lam1 = np.ones(c.rs.T)

                s3_list = [make_variant(c, vj, version, lv, k, raws, lam1) for k in s3_keys]
                c2_v = make_variant(c, vj, version, lv, "C2", raws, lam1)
                objs = objects_for(s3_list, c2_v, False)
                for name, obj in objs.items():
                    ev = eval_series(c, obj, orig_objs[name], replays, masks)
                    es = event_stats(obj["events"])
                    placebos[j][name][version][tag(lv)] = {
                        "bind_rate": es["bind_rate"],
                        "dsr_recent": ev["recent"]["dsr"],
                        "es_stress_rel": es_rel(ev, configs[name]["ORIG"]),
                        "replay_mean_change": replay_mean_change(ev, configs[name]["ORIG"]),
                    }
        log(f"placebo {j} done")
    semis_specific: dict[str, Any] = {}
    for name in ("O1", "S3", "C2"):
        semis_specific[name] = {}
        for version, sem_prefix in (("CAP", "CAP"), ("H1U", "H1U")):
            semis_specific[name][version] = {}
            for lv in LEVELS:
                sem = configs[name][f"{sem_prefix}_{tag(lv)}"]["recent"]["dsr"]
                med = sector_median(
                    [placebos[j][name][version][tag(lv)]["dsr_recent"] for j in PLACEBO_THEMES]
                )
                semis_specific[name][version][tag(lv)] = float(sem - med)

    # ---- decision --------------------------------------------------------------------
    dec_o1 = decision_rule({v: grid_o1[v] for v in ("CAP", "H2F", "H1F")})
    dec_s3 = decision_rule({v: grid_s3[v] for v in ("CAP", "H2F", "H1F")})

    results = {
        "meta": {
            "last_session": build["last_session"],
            "symbols": c.symbols,
            "runtime_s": round(time.time() - t0, 1),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
            "code_sha256": code_sha(),
            "windows": {k: list(v) for k, v in WINDOWS.items()},
            "dsr_means": "same-volatility Sharpe change versus ORIG (delta SR)",
            "pilot_weights": {"S3": W_S3, "C2": W_C2},
        },
        "identity": build["identity"],
        "replays": replays,
        "configs": configs,
        "bootstrap": bootstrap,
        "per_offset": per_offset,
        "per_offset_basis": "O1 recent delta SR with a single S3 offset",
        "s3_21_offsets_cap": s3_21,
        "theme_pnl_share": pnl,
        "placebos": placebos,
        "semis_specific": semis_specific,
        "decision": dec_o1["decision"],
        "pilot_limit": dec_o1["pilot_limit"],
        "pilot_limit_alternatives": dec_o1["alternatives"],
        "mechanical_status": dec_o1["status"],
        "decision_s3": dec_s3["decision"],
        "pilot_limit_s3": dec_s3["pilot_limit"],
        "pilot_limit_alternatives_s3": dec_s3["alternatives"],
        "mechanical_status_s3": dec_s3["status"],
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=float) + "\n")
    pd.DataFrame(series_store, index=c.index).to_parquet(CACHE / "series.parquet")
    log(
        f"run done: status {results['mechanical_status']} pilot_limit {results['pilot_limit']}; s3 {results['mechanical_status_s3']}"
    )
    return 0


def fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float) and not np.isfinite(x):
        return "n/a"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def stage_report() -> int:
    res = json.loads((OUT / "results.json").read_text())
    cf = res["configs"]
    lines: list[str] = []
    A = lines.append
    A("# P2 阶段 1 半导体主题风险预算：测量结果（T-20261005-32）")
    A("")
    A(
        f"最后会话 {res['meta']['last_session']}；运行 {res['meta']['runtime_s']} 秒，峰值内存 {res['meta']['peak_rss_mb']} MB。"
        " 数字全部来自 results.json；dsr = 同波动夏普变化（对 ORIG）。"
    )
    A("")
    A("## 1. O1 试点判定网格（近期窗口，主成本）")
    A("")
    A(
        "| 配置 | ΔSR近期 | 自助80% | ΔSR压力 | 压力ES比 | R1/R2/R3变化 | 触发率 | TRS前/后 | 可行率/λ | 新增成本bp/yr | 债务bp/yr | cost_ok | 好处 | 单调 |"
    )
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in ("CAP", "H2F", "H1F", "H1U"):
        for lv in LEVELS:
            cid = f"{v}_{tag(lv)}"
            e = cf["O1"][cid]
            e0 = cf["O1"]["ORIG"]
            b = res["bootstrap"][cid]
            rc = [
                e["replay"][r]["ret_samevol"] - e0["replay"][r]["ret_samevol"]
                for r in ("R1", "R2", "R3")
            ]
            th = e["theme"]
            d = res["decision"].get(v, {}).get(tag(lv), {})
            A(
                f"| {cid} | {fmt(e['recent']['dsr'])} | [{fmt(b['p10'])}, {fmt(b['p90'])}] | {fmt(e['stress']['dsr'])}"
                f" | {fmt(abs(e['stress']['es975_samevol']) / abs(e0['stress']['es975_samevol']))}"
                f" | {fmt(rc[0], 4)}/{fmt(rc[1], 4)}/{fmt(rc[2], 4)} | {fmt(th['bind_rate'])}"
                f" | {fmt(th['trs_mean_before'])}/{fmt(th['trs_mean_after'])}"
                f" | {fmt(th['feasibility_rate'])}/{fmt(th['lambda_mean'])} | {fmt(th['cost_added_bp_yr'], 1)}"
                f" | {fmt(th['debit_cost_bp_yr'], 1)} | {d.get('cost_ok', '-')} | {d.get('benefit', '-')} | {d.get('monotone', '-')} |"
            )
    A("")
    A("## 2. S3 单独与 C2 单独（近期/压力夏普 原始 / 同波动，k）")
    A("")
    A(
        "| 对象 | 配置 | 近期SR原始 | 近期SR同波动 | 近期k | 压力SR原始 | 压力SR同波动 | 压力k | ΔSR近期 | ΔSR压力 |"
    )
    A("|---|---|---|---|---|---|---|---|---|---|")
    for obj in ("S3", "C2"):
        for cid in ["ORIG"] + [
            f"{v}_{tag(lv)}" for v in ("CAP", "H2F", "H1F", "H1U") for lv in LEVELS
        ]:
            e = cf[obj][cid]
            A(
                f"| {obj} | {cid} | {fmt(e['recent']['sr_raw'], 2)} | {fmt(e['recent']['sr_samevol'], 2)} | {fmt(e['recent']['k'], 2)}"
                f" | {fmt(e['stress']['sr_raw'], 2)} | {fmt(e['stress']['sr_samevol'], 2)} | {fmt(e['stress']['k'], 2)}"
                f" | {fmt(e['recent']['dsr'])} | {fmt(e['stress']['dsr'])} |"
            )
    A("")
    A("## 3. 近期窗口主题盈亏份额（ORIG）")
    A("")
    A("| 对象 | 主题盈亏份额 | 市场盈亏份额 | 毛盈亏合计 |")
    A("|---|---|---|---|")
    for k, p in res["theme_pnl_share"].items():
        A(
            f"| {k} | {fmt(p['theme_share'])} | {fmt(p['market_share'])} | {fmt(p['gross_pnl'], 4)} |"
        )
    A("")
    A("## 4. 安慰剂（8 个行业 SPDR 作主题）与半导体特有依赖")
    A("")
    A(
        "| 对象 | 版本 | 档 | 半导体ΔSR | 行业ΔSR中位数 | 半导体特有依赖 | 行业触发率中位数 | 行业压力ES比中位数 | 行业回放变化中位数 |"
    )
    A("|---|---|---|---|---|---|---|---|---|")
    for name in ("O1", "S3", "C2"):
        for v in ("CAP", "H1U"):
            for lv in LEVELS:
                t = tag(lv)
                rows = [res["placebos"][j][name][v][t] for j in res["placebos"]]
                A(
                    f"| {name} | {v} | {t} | {fmt(cf[name][f'{v}_{t}']['recent']['dsr'])}"
                    f" | {fmt(float(np.median([r['dsr_recent'] for r in rows])))}"
                    f" | {fmt(res['semis_specific'][name][v][t])}"
                    f" | {fmt(float(np.median([r['bind_rate'] for r in rows])))}"
                    f" | {fmt(float(np.median([r['es_stress_rel'] for r in rows])))}"
                    f" | {fmt(float(np.median([r['replay_mean_change'] for r in rows])), 4)} |"
                )
    A("")
    A("## 5. S1、S2 的 CAP 结果（偏移 0）")
    A("")
    A("| 对象 | 配置 | ΔSR近期 | ΔSR压力 | 触发率 | TRS前/后 |")
    A("|---|---|---|---|---|---|")
    for obj in ("S1", "S2"):
        for lv in LEVELS:
            cid = f"CAP_{tag(lv)}"
            e = cf[obj][cid]
            A(
                f"| {obj} | {cid} | {fmt(e['recent']['dsr'])} | {fmt(e['stress']['dsr'])} | {fmt(e['theme']['bind_rate'])}"
                f" | {fmt(e['theme']['trs_mean_before'])}/{fmt(e['theme']['trs_mean_after'])} |"
            )
    A("")
    A("## 6. CAP 在 O1 上的 21 个 S3 偏移分布（近期ΔSR）")
    A("")
    A("| 档 | 最小 | 中位数 | 最大 |")
    A("|---|---|---|---|")
    for t, d in res["s3_21_offsets_cap"].items():
        A(f"| {t} | {fmt(d['min'])} | {fmt(d['median'])} | {fmt(d['max'])} |")
    A("")
    A("## 7. 恒等检查与数据")
    A("")
    ident = res["identity"]
    A(
        f"- (i) S3 偏移 0/4/8/12/16 对 tranche 引擎最大绝对差：{json.dumps(ident['i_s3_offsets_vs_tranche_max_abs_diff'])}"
    )
    A(f"- (ii) S3 偏移 0 对 combo：{ident['ii_s3_o0_vs_combo_max_abs_diff']:.3e}")
    A(
        f"- (iii) C2 对修复档 C2__o00__net10：{ident['iii_c2_vs_stored_max_abs_diff']:.3e}，重叠 {ident['iii_overlap']['start']}..{ident['iii_overlap']['end']}（{ident['iii_overlap']['n']} 个会话）"
    )
    A(
        f"- (iv) S1 {ident['iv_s1_vs_combo_max_abs_diff']:.3e}，S2 {ident['iv_s2_vs_combo_max_abs_diff']:.3e}"
    )
    for r, rp in res["replays"].items():
        A(
            f"- 回放 {r}：峰 {rp['peak']}，谷 {rp['trough']}，SMH 峰谷收益 {fmt(rp['smh_ret_peak_to_trough'], 4)}"
        )
    A("")
    A(
        f"mechanical_status = {res['mechanical_status']}；pilot_limit = {json.dumps(res['pilot_limit'])}；"
        f"pilot_limit_alternatives = {json.dumps(res['pilot_limit_alternatives'])}"
    )
    A(
        f"mechanical_status_s3 = {res['mechanical_status_s3']}；pilot_limit_s3 = {json.dumps(res['pilot_limit_s3'])}；"
        f"pilot_limit_alternatives_s3 = {json.dumps(res['pilot_limit_alternatives_s3'])}"
    )
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    ledger = []
    for v in ("CAP", "H1F", "H2F"):
        for lv in LEVELS:
            d = res["decision"][v][tag(lv)]
            ledger.append(
                {
                    "candidate_id": f"P2S1_{v}_{tag(lv)}",
                    "version": v,
                    "level": lv,
                    "dsr_recent": d["dsr_recent"],
                    "cost_ok": d["cost_ok"],
                    "benefit": d["benefit"],
                    "monotone": d["monotone"],
                }
            )
    (OUT / "trial-ledger.json").write_text(json.dumps(ledger, indent=1) + "\n")
    log(f"report written ({len(lines)} lines), ledger rows {len(ledger)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["build", "run", "report"], required=True)
    args = ap.parse_args(argv)
    return {"build": stage_build, "run": stage_run, "report": stage_report}[args.stage]()


if __name__ == "__main__":
    raise SystemExit(main())
