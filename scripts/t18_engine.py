# ruff: noqa: E501
"""T-20261006-18 engine: single-factor books (tier 1), overlap with the nine themes (tier 2) and
factor added to the v1.2 composite (tier 3).  Every book is the T-25 R6 / book v1.2 strategy-level rule
(``book_v12.tranche_target``: industry-demeaned rank-normal weights long 1 / short 1, easy-to-borrow
shorts, EWMA SPY beta hedge, VIX > 20.60 halving, fill at the close of t+1, fitted real costs, 25 bp
borrow), differing only in the score source and the decision calendar.

    flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_engine.py tier1
    ... tier2 | tier3 | identity
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book import optimize as op  # noqa: E402
from open_composer.research.equity_book import signals as sg  # noqa: E402
from scripts import book_v12_account as A  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402
from scripts import t18_factors as F  # noqa: E402

OUTD = ROOT / "data/research/t18_library"
SERIES = OUTD / "series"
START = "2017-10-02"
RECENT = ("2024-01-08", "2026-09-17")
DIAG = ("2017-10-02", "2023-08-31")
RECENT_START_TIER3 = (
    "2023-12-01"  # burn-in before the recent window; books are rebuilt at every decision
)
THEMES = sg.THEMES
ACCOUNTING = {k for k, v in F.DEFINITIONS.items() if v["kind"] == "acct"}
W_GRID = (0.5, 1.0, 2.0)


class FactorStore:
    def __init__(self) -> None:
        self._year: int | None = None
        self._df: pd.DataFrame | None = None
        self._dates: np.ndarray | None = None

    def at(self, t: pd.Timestamp) -> pd.DataFrame:
        if self._year != t.year:
            df = pd.read_parquet(F.FACTOR_DIR / f"{t.year}.parquet")
            self._df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(
                drop=True
            )
            self._dates = self._df["trade_date"].to_numpy()
            self._year = t.year
        d = np.datetime64(t.to_datetime64())
        lo, hi = np.searchsorted(self._dates, d, "left"), np.searchsorted(self._dates, d, "right")
        return self._df.iloc[lo:hi].set_index("symbol")


def month_end_positions(px: T25.Prices, start: str, end_pos: int) -> list[int]:
    s = pd.Series(np.arange(px.T), index=px.dates)
    last = s.groupby([px.dates.year, px.dates.month]).max().to_numpy()
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    return [int(p) for p in last if first <= p <= end_pos]


def weekly_positions(px: T25.Prices, start: str, end_pos: int, offset: int) -> list[int]:
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    return T25.decision_positions(px.T, first, end_pos, T25.WEEK, offset)


def run_book(
    ctx: T25.Context, src, flag: str, dec: list[int], *, no_industry: bool = False, ic_hook=None
) -> pd.DataFrame:
    """Strategy-level k = 1 book at the given decision positions (copy of ``book_v12_account.strategy_pass``)."""
    px = ctx.px
    last_label = px.T - 3
    w_state, h_state = np.zeros(px.N), 0.0
    rows: list[pd.DataFrame] = []
    for i, p in enumerate(dec):
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        nxt = min(nxt, last_label + 1)
        length = nxt - p
        if length <= 0:
            break
        di = A.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        if no_industry:
            di.ind = pd.Series(0, index=di.score.index)
        if ic_hook is not None:
            ic_hook(p, di)
        tt = A.tranche_from_inputs(ctx, di)
        ret, spy_r = px.returns("close", p, length)
        blk = bv.hold_block(tt.w, ret, spy_r, h0=tt.h)
        d_w = tt.w - w_state
        d_h = tt.h - h_state
        turnover = float(np.abs(d_w).sum())
        cost = T25.real_cost(ctx, di.t, px.symbols, d_w, d_h, di.attrs)
        n = len(blk["pnl"])
        cost_v = np.zeros(n)
        cost_v[0] = cost
        to_v = np.zeros(n)
        to_v[0] = turnover
        bor = blk["short_notional"] * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0)
        rows.append(
            pd.DataFrame(
                {
                    "gross": blk["pnl"],
                    "cost": cost_v,
                    "borrow": bor,
                    "turnover": to_v,
                    "spy": spy_r,
                    "hedge_size": np.full(n, tt.h),
                    "vix_scale": np.full(n, tt.vscale),
                    "blk": p,
                    "n_names": int((np.abs(tt.w) > 0).sum()),
                },
                index=px.dates[p : p + n],
            )
        )
        w_state, h_state = blk["w_end"], blk["h_end"]
    df = pd.concat(rows)
    df["net"] = df["gross"] - df["cost"] - df["borrow"]
    return df


# ---------------------------------------------------------------------------
# score sources
# ---------------------------------------------------------------------------
def _codes(ctx: T25.Context, t: pd.Timestamp, members: pd.Index) -> np.ndarray:
    return ctx.sig.at(t)["ind_code"].reindex(members).fillna(-1).to_numpy("int64")


def single_src(ctx: T25.Context, fs: FactorStore, name: str, demean: bool):
    def src(t, state, members):
        f = fs.at(t)
        raw = f[name].reindex(members).to_numpy("float64")
        sc, cov = sg.process_signal(raw, _codes(ctx, t, members), demean)
        return pd.Series(np.where(cov, sc, np.nan), index=members)

    return src


def theme_src(ctx: T25.Context, theme: str):
    def src(t, state, members):
        return ctx.themes.at(t).reindex(members)[theme].astype("float64")

    return src


def composite_src(
    ctx: T25.Context,
    fs: FactorStore,
    name: str | None,
    mode: str,
    w: float = 0.0,
    merge_theme: str | None = None,
):
    """M0 (``name`` None), M0 + tenth category of weight ``w`` (mode ``add``) or the factor merged into a theme."""
    demean = name in ACCOUNTING

    def src(t, state, members):
        th = ctx.themes.at(t).reindex(members)
        mat = th[list(THEMES)].to_numpy("float64")
        if name is None:
            comp = mat.mean(axis=1)
        else:
            raw = fs.at(t)[name].reindex(members).to_numpy("float64")
            sc, cov = sg.process_signal(raw, _codes(ctx, t, members), demean)
            if mode == "add":
                sd_t = np.nanmean(np.nanstd(mat, axis=0))
                sd_f = float(np.std(sc[cov])) if cov.sum() > 2 else 0.0
                f_sc = sc * (sd_t / sd_f) if sd_f > 0 else np.zeros_like(sc)
                comp = mat.mean(axis=1) + (w / 9.0) * f_sc
            else:
                j = THEMES.index(merge_theme)
                n_j = len(sg.THEME_SIGNALS[merge_theme])
                m2 = mat.copy()
                m2[:, j] = (n_j * mat[:, j] + sc) / (n_j + 1)
                comp = m2.mean(axis=1)
        return op.rank_normal(pd.Series(comp, index=members))

    return src


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30:
        return float("nan")
    ra, rb = rankdata(a[ok]), rankdata(b[ok])
    return float(np.corrcoef(ra, rb)[0, 1])


def window_stats(net: pd.Series, rf: pd.Series, a: str, b: str) -> dict[str, float]:
    sub = net[(net.index >= a) & (net.index <= b)].dropna()
    if len(sub) < 20:
        return {"n": int(len(sub))}
    ex = sub - rf.reindex(sub.index).fillna(0.0)
    sd = float(ex.std(ddof=1))
    from open_composer.research.equity_book.evaluate import max_drawdown, newey_west_t

    return {
        "n": int(len(sub)),
        "sharpe": float(ex.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
        "ann_excess": float(ex.mean() * 252),
        "vol": float(sd * np.sqrt(252)),
        "nw_t": newey_west_t(ex.to_numpy(), 5),
        "max_dd": max_drawdown(sub.to_numpy()),
    }


def ic_stats(ic: pd.Series, a: str, b: str) -> dict[str, float]:
    s = ic[(ic.index >= a) & (ic.index <= b)].dropna()
    if len(s) < 6:
        return {"n": int(len(s))}
    from open_composer.research.equity_book.evaluate import newey_west_t

    return {
        "n": int(len(s)),
        "ic_mean": float(s.mean()),
        "ic_t": float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))),
        "ic_nw_t": newey_west_t(s.to_numpy(), 2),
        "ic_pos": float((s > 0).mean()),
    }


# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
IND_DIR = (
    OUTD / "ind"
)  # slim copy of signals/<year>.parquet (trade_date, symbol, ind_code) for Modal


def make_ctx() -> T25.Context:
    ctx = T25.Context()
    if (
        IND_DIR.exists()
    ):  # same three columns, same values, far smaller than the full signals tables
        ctx.sig = T25.YearStore(
            str(IND_DIR / "{year}.parquet"), ["trade_date", "symbol", "ind_code"]
        )
    return ctx


def save_series(name: str, df: pd.DataFrame) -> None:
    SERIES.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SERIES / f"{name}.parquet")


def have(name: str) -> bool:
    return (SERIES / f"{name}.parquet").exists()


def tier1(names: list[str] | None = None) -> None:
    """Single-factor books: factor x {U3000, P1000} x {raw, industry-demeaned}; monthly, month-end decisions."""
    ctx = make_ctx()
    fs = FactorStore()
    px = ctx.px
    dec = month_end_positions(px, START, px.T - 24)
    todo = names or F.COMPUTED
    for name in todo:
        for uni in ("U3000", "P1000"):
            for proc in ("raw", "dm"):
                key = f"t1__{name}__{uni}__{proc}"
                if have(key):
                    continue
                t0 = time.time()
                flag = "in_u3000" if uni == "U3000" else "in_p1000"
                src = single_src(ctx, fs, name, demean=(proc == "dm"))
                ics: dict[pd.Timestamp, float] = {}

                def hook(p, di, ics=ics):
                    s = di.score.dropna()
                    idx = px.symbols.get_indexer(s.index)
                    ok = idx >= 0
                    with np.errstate(invalid="ignore", divide="ignore"):
                        fwd = (
                            px.C[p + 22, idx[ok]] / px.C[p + 1, idx[ok]] - 1.0
                            if p + 22 < px.T
                            else np.full(ok.sum(), np.nan)
                        )
                    ics[px.dates[p]] = spearman(s.to_numpy()[ok], fwd)

                df = run_book(ctx, src, flag, dec, no_industry=(proc == "raw"), ic_hook=hook)
                df["ic"] = pd.Series(ics).reindex(df.index)
                save_series(key, df)
                print(key, f"{time.time() - t0:.0f}s", flush=True)


def tier2_themes() -> None:
    ctx = make_ctx()
    px = ctx.px
    dec = month_end_positions(px, START, px.T - 24)
    for th in (*THEMES, "M0"):
        key = f"t2__theme__{th}"
        if have(key):
            continue
        src = composite_src(ctx, None, None, "add") if th == "M0" else theme_src(ctx, th)
        df = run_book(ctx, src, "in_u3000", dec)
        save_series(key, df)
        print(key, flush=True)


def identity() -> None:
    """Base M0_U3000 weekly book rebuilt from 2023-12 must equal the saved R6 series from 2024-01-08."""
    ctx = make_ctx()
    px = ctx.px
    out = {}
    for o in (0, 3):
        dec = weekly_positions(px, RECENT_START_TIER3, px.T - 3, o)
        df = run_book(ctx, composite_src(ctx, None, None, "add"), "in_u3000", dec)
        saved = pd.read_parquet(T25.RAW / f"R6_M0_U3000_o{o}.parquet")
        a = df.loc[df.index >= RECENT[0], "net"]
        b = saved["net"].reindex(a.index)
        out[f"o{o}"] = {"n": int(len(a)), "max_abs_diff_net": float((a - b).abs().max())}
        print(o, out[f"o{o}"], flush=True)
    (OUTD / "identity.json").write_text(json.dumps(out, indent=1))


def tier3(
    names: list[str] | None = None, merge_map: dict[str, str] | None = None, diag: bool = False
) -> None:
    """``diag``: crash diagnostic window (2017-10..2023-09), series prefix ``t3d``."""
    ctx = make_ctx()
    fs = FactorStore()
    px = ctx.px
    pre = "t3d" if diag else "t3"
    start = START if diag else RECENT_START_TIER3
    end = int(px.dates.searchsorted(pd.Timestamp("2023-09-15"))) if diag else px.T - 3
    decs = {o: weekly_positions(px, start, end, o) for o in range(5)}
    for o in range(5):
        key = f"{pre}__base__o{o}"
        if not have(key):
            save_series(
                key, run_book(ctx, composite_src(ctx, None, None, "add"), "in_u3000", decs[o])
            )
            print(key, flush=True)
    for name in names or F.COMPUTED:
        variants = [(f"w{w}", dict(mode="add", w=w)) for w in W_GRID]
        if merge_map and name in merge_map:
            variants.append(("merge", dict(mode="merge", merge_theme=merge_map[name])))
        for vname, kw in variants:
            for o in range(5):
                key = f"{pre}__{name}__{vname}__o{o}"
                if have(key):
                    continue
                t0 = time.time()
                df = run_book(ctx, composite_src(ctx, fs, name, **kw), "in_u3000", decs[o])
                save_series(key, df)
                print(key, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if "--shard" in args:  # --shard i --nshards n: every n-th factor of the preregistered order
        i = args.index("--shard")
        k = int(args[i + 1])
        n = int(args[args.index("--nshards") + 1])
        args = F.COMPUTED[k::n]
    if stage == "tier1":
        tier1(args or None)
    elif stage == "tier2":
        tier2_themes()
    elif stage == "identity":
        identity()
    elif stage == "tier3diag":
        mm = json.loads((OUTD / "merge_map.json").read_text())
        tier3(args or None, mm, diag=True)
    elif stage == "tier3":
        mm = (
            json.loads((OUTD / "merge_map.json").read_text())
            if (OUTD / "merge_map.json").exists()
            else None
        )
        tier3(args or None, mm)
    else:
        raise SystemExit(f"unknown stage {stage}")
