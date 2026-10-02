# ruff: noqa: E501
"""Book v1.2 Stage B: strategy-level placebo (t20261002_book_v12, hypotheses.md section 5).

At every rebalance date and offset the composite of the universe members with a finite score is
permuted (``rng = default_rng(seed * 100003 + offset * 1009 + p)``, ``p`` the calendar position of
the decision date); everything downstream is the R6 pipeline: industry demeaning, ETB restriction,
the missing-fill zeroing, the hedge of the permuted weights, the VIX scale, real costs, 25 bp borrow.
Warm-up from the first rebalance on or after 2023-11-01; the recent window 2024-01-08..2026-09-15
decides.  The per-seed arithmetic is vectorised; ``--check`` shows that without a permutation it
reproduces the saved T-25 R6 series.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_placebo.py --stage run
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_placebo.py --stage check
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book.costfn import (  # noqa: E402
    ETF_HALF_SPREAD_BP,
    MISSING_HALF_SPREAD_BP,
)
from open_composer.research.equity_book.costs import (  # noqa: E402
    FEES_BP_PER_SIDE,
    IMPACT_Y,
    half_spread_bp,
    impact_bp,
    load_model,
)
from open_composer.research.scorecard_v2 import annual_sharpe, placebo_percentile  # noqa: E402
from scripts import book_v12_account as acct  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

OUT_DATA = acct.OUT_DATA / "placebo"
OUT_REPORT = acct.OUT_REPORT
WARMUP_FROM = "2023-11-01"
RECENT = ("2024-01-08", "2026-09-15")
N_SEEDS = 100
VARIANTS = T25.VARIANTS
OFFSETS = T25.OFFSETS


@dataclass
class Static:
    p: int
    idx: np.ndarray  # global symbol index of the members with a finite score
    s: np.ndarray  # composite of those members
    codes: np.ndarray  # industry group code (missing industry is its own group)
    n_groups: int
    elig: np.ndarray
    beta: np.ndarray
    fill_ok: np.ndarray
    vscale: float
    q: np.ndarray  # (L, M) g_before * r : stock P&L per unit weight
    gb: np.ndarray  # (L, M) g_before
    g_end: np.ndarray  # (M,)
    spy_sb: np.ndarray  # (L,) s_before * spy_r
    spy_end: float
    hs_all: np.ndarray  # (N,) half-spread bp (stock model, missing -> 40 bp)
    adv_all: np.ndarray
    vol_all: np.ndarray
    n: int


def build_statics(
    ctx: T25.Context,
    variant: str,
    offset: int,
    start: str,
    limit: int | None = None,
) -> list[Static]:
    px = ctx.px
    flag = acct.variant_flag(variant)
    src = acct.make_source(ctx, variant)
    model = load_model()
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    last_label = px.T - 3
    dec = T25.decision_positions(px.T, first, last_label, T25.WEEK, offset)
    out: list[Static] = []
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        di = acct.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        names = di.score.dropna().index
        idx = px.symbols.get_indexer(names)
        assert (idx >= 0).all(), "a scored member is missing from the wide matrices"
        g = di.ind.reindex(names).fillna(-1)
        codes, uniq = pd.factorize(g.to_numpy())
        ret, spy_r = px.returns("close", p, length)
        r = np.where(np.isfinite(ret[:, idx]), ret[:, idx], 0.0)
        g_after = np.cumprod(1.0 + r, axis=0)
        g_before = np.vstack([np.ones((1, r.shape[1])), g_after[:-1]])
        s_after = np.cumprod(1.0 + spy_r)
        s_before = np.concatenate([[1.0], s_after[:-1]])
        a = di.attrs.reindex(px.symbols)
        price = a["close"].to_numpy("float64")
        adv = a["dollar_adv_21"].to_numpy("float64")
        vol = a["vol_21"].to_numpy("float64")
        with np.errstate(invalid="ignore", divide="ignore"):
            hs = half_spread_bp(price, adv, vol, np.full(len(price), di.t.year), "close", model)
        hs = np.where(np.isfinite(hs), hs, MISSING_HALF_SPREAD_BP)
        out.append(
            Static(
                p=p,
                idx=idx,
                s=di.score.loc[names].to_numpy("float64"),
                codes=codes.astype("int64"),
                n_groups=len(uniq),
                elig=di.eligible.reindex(names).fillna(False).to_numpy(bool),
                beta=di.beta.reindex(names).fillna(1.0).clip(-1.0, 4.0).to_numpy("float64"),
                fill_ok=di.fill_ok[idx],
                vscale=bv.vix_scale(di.vix),
                q=g_before * r,
                gb=g_before,
                g_end=g_after[-1],
                spy_sb=s_before * spy_r,
                spy_end=float(s_after[-1]),
                hs_all=hs,
                adv_all=adv,
                vol_all=vol,
                n=length,
            )
        )
    return out


def placebo_weights(
    s: np.ndarray,
    codes: np.ndarray,
    n_groups: int,
    elig: np.ndarray,
    fill_ok: np.ndarray,
    beta: np.ndarray,
    vscale: float,
) -> tuple[np.ndarray, float]:
    """R6 weights and hedge of one (permuted) composite on arrays: industry demeaning, ETB
    restriction, missing-fill zeroing, VIX scale, hedge (numpy form of ``book_v12.tranche_target``)."""
    cnt = np.bincount(codes, minlength=n_groups)
    mean = np.bincount(codes, weights=s, minlength=n_groups) / np.maximum(cnt, 1)
    dm = s - mean[codes]
    tot = float(np.abs(dm).sum())
    w = 2.0 * dm / tot if tot > 0 else dm * 0.0
    out = np.where((w >= 0) | elig, w, 0.0)
    neg = out < 0
    sn = -float(out[neg].sum())
    if sn > 0:
        out[neg] = out[neg] / sn
    out[~fill_ok] = 0.0
    w0 = out * vscale
    return w0, float(-np.nansum(w0 * beta))


def seed_pass(
    statics: list[Static], seed: int, offset: int, n_sym: int, *, permute: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One seed: daily ``gross``, ``cost``, ``borrow`` concatenated over the blocks."""
    w_state = np.zeros(n_sym)
    h_state = 0.0
    gross, cost, borrow = [], [], []
    for st in statics:
        if permute:
            rng = np.random.default_rng(seed * 100003 + offset * 1009 + st.p)
            s = st.s[rng.permutation(len(st.s))]
        else:
            s = st.s
        w0, h = placebo_weights(s, st.codes, st.n_groups, st.elig, st.fill_ok, st.beta, st.vscale)
        pnl = st.q @ w0 + h * st.spy_sb
        short = st.gb @ np.where(w0 < 0, -w0, 0.0)
        # trade cost on the change from the drifted previous book
        d = -w_state
        d[st.idx] += w0
        dh = h - h_state
        nz = np.flatnonzero(np.abs(d) > 1e-12)
        amt = np.abs(d[nz]) * bv.EQUITY
        imp = impact_bp(amt, st.adv_all[nz], st.vol_all[nz], IMPACT_Y)
        imp = np.where(np.isfinite(imp), imp, 0.0)
        c = float(np.sum(amt * st.hs_all[nz] / 1e4) + np.sum(amt * imp / 1e4))
        c += float(np.sum(amt) * FEES_BP_PER_SIDE / 1e4)
        if abs(dh) > 1e-12:
            a_h = abs(dh) * bv.EQUITY
            c += a_h * ETF_HALF_SPREAD_BP / 1e4 + a_h * FEES_BP_PER_SIDE / 1e4
        c /= bv.EQUITY
        n = len(pnl)
        cv = np.zeros(n)
        cv[0] = c
        gross.append(pnl)
        cost.append(cv)
        borrow.append(short * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0))
        w_state = np.zeros(n_sym)
        w_state[st.idx] = w0 * st.g_end
        h_state = h * st.spy_end
    return (
        np.concatenate(gross),
        np.concatenate(cost),
        np.concatenate(borrow),
        np.concatenate([np.full(st.n, st.p) + np.arange(st.n) for st in statics]),
    )


# ---------------------------------------------------------------------------
def run_check() -> dict:
    ctx = T25.Context()
    res: dict = {"cases": {}, "pass": True}
    for variant, o in (("M0_U3000", 0), ("M1_P1000", 3)):
        st = build_statics(ctx, variant, o, T25.START, limit=60)
        g, c, b, pos = seed_pass(st, 0, o, ctx.px.N, permute=False)
        saved = pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet")
        sv = saved.iloc[: len(g)]
        d = {
            "gross": float(np.abs(g - sv["gross"].to_numpy()).max()),
            "cost": float(np.abs(c - sv["cost"].to_numpy()).max()),
            "borrow": float(np.abs(b - sv["borrow"].to_numpy()).max()),
            "net": float(np.abs((g - c - b) - sv["net"].to_numpy()).max()),
        }
        ok = max(d.values()) <= 1e-9
        res["cases"][f"{variant}_o{o}"] = {"max_abs_diff": d, "rows": len(g), "pass": ok}
        res["pass"] = res["pass"] and ok
        print(variant, o, d, flush=True)
    return res


def run_placebo() -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    ctx = T25.Context()
    px = ctx.px
    dates = px.dates
    for variant in VARIANTS:
        for o in OFFSETS:
            f = OUT_DATA / f"{variant}_o{o}.npz"
            if f.exists():
                continue
            t0 = time.time()
            st = build_statics(ctx, variant, o, WARMUP_FROM)
            t1 = time.time()
            n_days = sum(s.n for s in st)
            gross = np.empty((N_SEEDS, n_days))
            net = np.empty((N_SEEDS, n_days))
            pos = None
            for seed in range(N_SEEDS):
                g, c, b, pos = seed_pass(st, seed, o, px.N)
                gross[seed], net[seed] = g, g - c - b
            np.savez_compressed(f, gross=gross, net=net, pos=pos)
            print(
                variant,
                o,
                f"static {t1 - t0:.0f}s seeds {time.time() - t1:.0f}s",
                flush=True,
            )
    # blend and score
    lo, hi = pd.Timestamp(RECENT[0]), pd.Timestamp(RECENT[1])
    out: dict = {"seeds": N_SEEDS, "recent": RECENT, "variants": {}}
    for variant in VARIANTS:
        common = None
        parts = []
        for o in OFFSETS:
            z = np.load(OUT_DATA / f"{variant}_o{o}.npz")
            parts.append((z["pos"], z["net"], z["gross"]))
            common = set(z["pos"]) if common is None else common & set(z["pos"])
        keep = np.array(sorted(common))
        keep = keep[(dates[keep] >= lo) & (dates[keep] <= hi)]
        net_b = np.zeros((N_SEEDS, len(keep)))
        gross_b = np.zeros((N_SEEDS, len(keep)))
        for pos, n_arr, g_arr in parts:
            sel = np.isin(pos, keep)
            net_b += n_arr[:, sel] / len(OFFSETS)
            gross_b += g_arr[:, sel] / len(OFFSETS)
        sr_net = [annual_sharpe(r) for r in net_b]
        sr_gross = [annual_sharpe(r) for r in gross_b]
        saved = [pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet") for o in OFFSETS]
        idx = saved[0].index
        for s in saved[1:]:
            idx = idx.intersection(s.index)
        bl = sum(s.loc[idx, ["gross", "net"]] for s in saved) / len(saved)
        bl = bl.loc[RECENT[0] : RECENT[1]]
        obs_net, obs_gross = annual_sharpe(bl["net"]), annual_sharpe(bl["gross"])
        out["variants"][variant] = {
            "sessions": int(len(keep)),
            "observed_net_sharpe": obs_net,
            "observed_gross_sharpe": obs_gross,
            "placebo_net_sharpes": sr_net,
            "placebo_gross_sharpes": sr_gross,
            "net_percentile": placebo_percentile(obs_net, sr_net),
            "gross_percentile": placebo_percentile(obs_gross, sr_gross),
            "placebo_net_mean": float(np.mean(sr_net)),
            "placebo_net_p95": float(np.quantile(sr_net, 0.95)),
            "placebo_net_max": float(np.max(sr_net)),
            "placebo_gross_mean": float(np.mean(sr_gross)),
            "placebo_gross_p95": float(np.quantile(sr_gross, 0.95)),
            "placebo_gross_max": float(np.max(sr_gross)),
        }
        print(
            variant,
            "obs net",
            round(obs_net, 3),
            "pct",
            out["variants"][variant]["net_percentile"],
            "gross pct",
            out["variants"][variant]["gross_percentile"],
            flush=True,
        )
    (OUT_REPORT / "placebo.json").write_text(json.dumps(out, indent=1, default=float))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["check", "run"], required=True)
    a = ap.parse_args()
    if a.stage == "check":
        res = run_check()
        OUT_DATA.mkdir(parents=True, exist_ok=True)
        (OUT_DATA / "check.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({"pass": res["pass"]}))
        if not res["pass"]:
            sys.exit(3)
    else:
        run_placebo()


if __name__ == "__main__":
    main()
