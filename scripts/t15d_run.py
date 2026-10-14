# ruff: noqa: E501, E741
"""T-20261006-15-D runner: Reversal Trend 1h / 1m on the frozen main grid (amendment-2026-10-06-main-grid.md).

Stages (all resumable; heavy ones go through scripts/heavy_run.sh):

  series   build indicator/signal series per symbol: ETF (QQQ, SPY) and the top-50 stock cohort
  grid     16 main-grid points (2 baskets x 8 variants) + single-signal diagnostics, placebos
           -> data/features/t15_work/d_acc/*.npz
  deep     selected spec per basket: phase/latency, robustness grid, V4, DSR, tier -> results_d.json
"""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15d_engine as X  # noqa: E402

ACC_DIR = X.WORK / "d_acc"
SEEDS = 100
RECENT_START = pd.Timestamp("2024-01-08")
PERIODS = {"1h": dict(H=13, intraday=False), "1m": dict(H=90, intraday=True)}
DIRS = ("long", "longshort")
SIGS = ("primary_only", "primary_and_reclaim")
LONG_FLAGS = {"primary_only": ("f_bull",), "primary_and_reclaim": ("f_bull", "f_recl")}
SHORT_FLAGS = {"primary_only": ("f_bear",), "primary_and_reclaim": ("f_bear", "f_recs")}
INFO_SIGNALS = {
    "bull": (("f_bull",), ()),
    "recl": (("f_recl",), ()),
    "bear": ((), ("f_bear",)),
    "recs": ((), ("f_recs",)),
}


def etf_basket() -> dict:
    return dict(kind="etf", syms=["QQQ", "SPY"], N=2)


def stock_basket() -> dict:
    import t15d_extract_stock_minutes as XS

    return dict(kind="stock", syms=XS.stock_symbols(), N=50)


def baskets() -> dict[str, dict]:
    top50 = stock_basket()
    return {
        "QQQ_SPY": etf_basket(),
        "TOP50": {**top50, "topk": 50},
        # scale-curve supplement (not in the frozen 16 points; counted as robustness)
        "TOP10": {**top50, "N": 10, "topk": 10},
        "TOP25": {**top50, "N": 25, "topk": 25},
    }


def cfg_flags(dirn: str, sig: str):
    return LONG_FLAGS[sig], (SHORT_FLAGS[sig] if dirn == "longshort" else ())


# ----------------------------------------------------------------------------- accumulation
class Acc:
    """Daily series and trade-level stats of one (basket, config), accumulated symbol by symbol."""

    def __init__(self, N: int, D: int, seeds: int = SEEDS):
        self.N, self.D, self.seeds = N, D, seeds
        self.g = np.zeros(D)
        self.cv = np.zeros(D)
        self.cf = np.zeros(D)
        self.ent = np.zeros(D)
        self.pl_g = np.zeros((seeds, D))
        self.rd_g = np.zeros((seeds, D))
        self.rd_c = np.zeros((seeds, D))
        self.rd_sum = np.zeros(seeds)
        self.rd_n = np.zeros(seeds)
        self.tr_day: list[np.ndarray] = []
        self.tr_g: list[np.ndarray] = []
        self.tr_c: list[np.ndarray] = []
        self.tr_side: list[np.ndarray] = []

    # real trades
    def add_real(self, tr: dict, co: dict, rng: np.random.Generator, placebo: bool = True):
        k = len(tr["side"])
        if k == 0:
            return
        D, N = self.D, self.N
        side = tr["side"].astype(float)
        self.g += np.bincount(tr["m_day"], weights=side[tr["m_tid"]] * tr["m_val"], minlength=D) / N
        self.cv += np.bincount(tr["day_e"], weights=co["var_e"], minlength=D) + np.bincount(
            tr["day_x"], weights=co["var_x"], minlength=D
        )
        self.cf += np.bincount(tr["day_e"], weights=co["fix_e"], minlength=D) + np.bincount(
            tr["day_x"], weights=co["fix_x"], minlength=D
        )
        self.ent += np.bincount(tr["day_e"], minlength=D)
        gbp = side * (tr["px"] - tr["pe"]) / tr["pe"] * 1e4
        cbp = co["var_e"] + co["fix_e"] + co["var_x"] + co["fix_x"]
        self.tr_day.append(tr["day_e"].copy())
        self.tr_g.append(gbp)
        self.tr_c.append(cbp)
        self.tr_side.append(tr["side"].copy())
        if placebo:
            recent = tr["day_e"] >= RECENT_IDX0
            if not recent.any():
                return
            sign = rng.choice([-1.0, 1.0], size=(self.seeds, k))
            w = tr["m_val"] / N
            mt = tr["m_tid"]
            m_ok = recent[mt]
            for s in range(self.seeds):
                self.pl_g[s] += np.bincount(
                    tr["m_day"][m_ok], weights=(sign[s][mt] * w)[m_ok], minlength=D
                )

    # same-slot random-day placebo
    def add_random_day(self, S: dict, tr: dict, co: dict, cfg: dict, rbs: dict, rng, bad):
        recent = tr["day_e"] >= RECENT_IDX0
        k = int(recent.sum())
        if k == 0:
            return
        idx = np.flatnonzero(recent)
        side = tr["side"][idx].astype(float)
        slot_e = tr["slot_e"][idx]
        cost_bp = (co["var_e"] + co["fix_e"] + co["var_x"] + co["fix_x"])[idx]
        seeds, D, N = self.seeds, self.D, self.N
        e_new = np.full((seeds, k), -1, np.int64)
        for sl in np.unique(slot_e):
            rows = rbs.get(int(sl))
            if rows is None or len(rows) == 0:
                continue
            m = slot_e == sl
            e_new[:, m] = rows[rng.integers(0, len(rows), size=(seeds, int(m.sum())))]
        valid = e_new >= 0
        o, c, day = S["o"], S["c"], S["day"]
        n = len(o)
        H = cfg["H"]
        if cfg["intraday"]:
            lrd = X.last_row_of_day(day)
            en = np.where(valid, e_new, 0)
            lastrow = lrd[en]
            x = en + H
            atc = x > lastrow
            px = np.where(atc, c[lastrow], o[np.minimum(x, n - 1)])
            pe = o[en]
            ret = (px - pe) / pe
            ok = valid & np.isfinite(ret) & (np.abs(ret) <= 0.3)
            ret = np.where(ok, ret, 0.0)
            dnew = day[en]
            flat = (np.arange(seeds)[:, None] * D + dnew).ravel()
            gw = (side[None, :] * ret).ravel()
            self.rd_g += np.bincount(flat, weights=gw, minlength=seeds * D).reshape(seeds, D) / N
            cw = (np.where(ok, cost_bp[None, :], 0.0) / 1e4 / N).ravel()
            self.rd_c += np.bincount(flat, weights=cw, minlength=seeds * D).reshape(seeds, D)
            self.rd_sum += (np.where(ok, side[None, :] * ret, 0.0) * 1e4).sum(axis=1)
            self.rd_n += ok.sum(axis=1)
        else:
            for s in range(seeds):
                ok_rows = valid[s]
                if not ok_rows.any():
                    continue
                er = e_new[s][ok_rows]
                sd = side[ok_rows].astype(int)
                ctr = cost_bp[ok_rows]
                tr2 = X.simulate(
                    S,
                    (),
                    (),
                    H,
                    False,
                    bad_by_day=bad,
                    entry_rows=er,
                    entry_sides=sd,
                    no_block=True,
                )
                if len(tr2["side"]) == 0:
                    continue
                kp = tr2["keep"]
                s2 = tr2["side"].astype(float)
                self.rd_g[s] += (
                    np.bincount(tr2["m_day"], weights=s2[tr2["m_tid"]] * tr2["m_val"], minlength=D)
                    / N
                )
                self.rd_c[s] += (
                    np.bincount(tr2["day_e"], weights=ctr[kp] / 2.0, minlength=D)
                    + np.bincount(tr2["day_x"], weights=ctr[kp] / 2.0, minlength=D)
                ) / (1e4 * N)
                self.rd_sum[s] += float((s2 * (tr2["px"] - tr2["pe"]) / tr2["pe"]).sum() * 1e4)
                self.rd_n[s] += len(kp)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        cat = lambda L, dt: np.concatenate(L) if L else np.zeros(0, dt)  # noqa: E731
        np.savez_compressed(
            path,
            N=self.N,
            g=self.g,
            cv=self.cv,
            cf=self.cf,
            ent=self.ent,
            pl_g=self.pl_g,
            rd_g=self.rd_g,
            rd_c=self.rd_c,
            rd_sum=self.rd_sum,
            rd_n=self.rd_n,
            tr_day=cat(self.tr_day, np.int32),
            tr_g=cat(self.tr_g, float),
            tr_c=cat(self.tr_c, float),
            tr_side=cat(self.tr_side, np.int8),
        )

    @staticmethod
    def load(path: Path) -> dict:
        z = np.load(path)
        return {k: z[k] for k in z.files}


MASTER = X.master()
D = len(MASTER)
RECENT_IDX0 = int(np.searchsorted(MASTER.values, RECENT_START.to_datetime64()))


def rows_by_slot(S: dict, allow: np.ndarray | None, bad: np.ndarray) -> dict[int, np.ndarray]:
    day = S["day"]
    elig = (day >= RECENT_IDX0) & ~bad[day]
    if allow is not None:
        elig &= allow[day]
    rows = np.flatnonzero(elig)
    if len(rows) == 0:
        return {}
    sl = S["slot"][rows].astype(int)
    order = np.argsort(sl, kind="stable")
    rows, sl = rows[order], sl[order]
    u, st = np.unique(sl, return_index=True)
    en = np.r_[st[1:], len(sl)]
    return {int(a): rows[b:c] for a, b, c in zip(u, st, en, strict=True)}


def seed_for(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode()) ^ 20261006


def symbol_context(sym: str, b: dict, S: dict, universe):
    if b["kind"] == "etf":
        return X.etf_ctx(sym, S), None
    ctx, pool = X.stock_ctx(sym, S, universe, b.get("topk", 50))
    return ctx, pool


def config_key(period, dirn, sig, H, exit_rule, delay=0, phase=0, extra=""):
    return f"{period}_{dirn}_{sig}_H{H}_{exit_rule}_d{delay}_p{phase}{extra}"


# ----------------------------------------------------------------------------- grid stage
def main_cfgs() -> dict[str, tuple]:
    cfgs = {}
    for dirn in DIRS:
        for sig in SIGS:
            cfgs[f"main|{dirn}|{sig}"] = cfg_flags(dirn, sig)
    for k, fl in INFO_SIGNALS.items():
        cfgs[f"info|{k}"] = fl
    return cfgs


def acc_path(bname: str, period: str, name: str) -> Path:
    return ACC_DIR / f"{bname}_{period}_{name.replace('|', '_')}.npz"


def run_unit(bname: str, period: str, universe=None, force=False, tag="") -> None:
    b = baskets()[bname]
    pc = PERIODS[period]
    cfgs = main_cfgs()
    if not force and all(acc_path(bname + tag, period, n).exists() for n in cfgs):
        print(bname, period, "done already", flush=True)
        return
    if universe is None:
        universe = pd.read_parquet(X.UNIVERSE)
    accs = {n: Acc(b["N"], D) for n in cfgs}
    rngs = {n: np.random.default_rng(seed_for(bname, period, n)) for n in cfgs}
    for i, sym in enumerate(b["syms"]):
        S = X.build_series(sym, b["kind"], period, 0)
        if S is None:
            continue
        ctx, pool = symbol_context(sym, b, S, universe)
        if pool is not None and not pool[RECENT_IDX0:].any():
            continue
        bad = X.bad_by_day(S)
        rbs = rows_by_slot(S, pool, bad)
        for n, (lf, sf) in cfgs.items():
            tr = X.simulate(S, lf, sf, pc["H"], pc["intraday"], allow_day=pool, bad_by_day=bad)
            co = X.trade_costs(tr, ctx)
            accs[n].add_real(tr, co, rngs[n])
            accs[n].add_random_day(S, tr, co, pc, rbs, rngs[n], bad)
        del S
        if (i + 1) % 10 == 0:
            print(f"  {bname} {period}: {i + 1}/{len(b['syms'])} symbols", flush=True)
    for n, a in accs.items():
        a.save(acc_path(bname + tag, period, n))
    print(bname, period, "saved", len(accs), "accumulators", flush=True)


def build_all_series(which: str) -> None:
    bk = baskets()
    names = ["QQQ_SPY"] if which == "etf" else ["TOP50"]
    for bname in names:
        b = bk[bname]
        for sym in b["syms"]:
            for period, ph in (("1m", 0), ("1h", 0), ("1h", 1), ("1h", 2)):
                if (X.SIG_DIR / f"{sym}_{period}_ph{ph}.npz").exists():
                    continue
                S = X.build_series(sym, b["kind"], period, ph)
                print(sym, period, ph, None if S is None else len(S["o"]), flush=True)
                del S


# ----------------------------------------------------------------------------- deep stage
def series_sum(
    bname: str,
    period: str,
    dirn: str,
    sig: str,
    H: int,
    exit_rule: str = "time_stop",
    delay: int = 0,
    phase: int = 0,
    alt_open: bool = False,
    universe=None,
) -> dict:
    """Daily gross/cost/entries of one config summed over the basket's symbols (no placebos)."""
    b = baskets()[bname]
    pc = PERIODS[period]
    lf, sf = cfg_flags(dirn, sig)
    if universe is None:
        universe = pd.read_parquet(X.UNIVERSE)
    g = np.zeros(D)
    cv = np.zeros(D)
    cf = np.zeros(D)
    ent = np.zeros(D)
    for sym in b["syms"]:
        S = X.build_series(sym, b["kind"], period, phase if period == "1h" else 0)
        if S is None:
            continue
        ctx, pool = symbol_context(sym, b, S, universe)
        if pool is not None and not pool[RECENT_IDX0:].any():
            continue
        if alt_open:
            ctx["snap_override"] = "open"
        bad = X.bad_by_day(S)
        tr = X.simulate(
            S,
            lf,
            sf,
            H,
            pc["intraday"],
            allow_day=pool,
            bad_by_day=bad,
            exit_rule=exit_rule,
            delay=delay,
        )
        if len(tr["side"]) == 0:
            continue
        co = X.trade_costs(tr, ctx)
        side = tr["side"].astype(float)
        N = b["N"]
        g += np.bincount(tr["m_day"], weights=side[tr["m_tid"]] * tr["m_val"], minlength=D) / N
        cv += np.bincount(tr["day_e"], weights=co["var_e"], minlength=D) + np.bincount(
            tr["day_x"], weights=co["var_x"], minlength=D
        )
        cf += np.bincount(tr["day_e"], weights=co["fix_e"], minlength=D) + np.bincount(
            tr["day_x"], weights=co["fix_x"], minlength=D
        )
        ent += np.bincount(tr["day_e"], minlength=D)
        del S
    return {"N": b["N"], "g": g, "cv": cv, "cf": cf, "ent": ent}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "series":
        build_all_series(sys.argv[2])
    elif cmd == "grid":
        for bname in sys.argv[2].split(","):
            for period in ("1h", "1m"):
                run_unit(bname, period)
    else:
        raise SystemExit(f"unknown command {cmd}")
