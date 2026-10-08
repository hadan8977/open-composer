#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-01: cost-aware engine, slow score x fast composite in one book (t20261007_01_cost_aware_engine).

Contract: ``reports/research/iterations/t20261007_01_cost_aware_engine/hypotheses.md``.  New code only; the v1.2
construction (``book_v12``, ``trading_rules``) and the production runner are untouched.

    --stage identity   new engine with the new features off against the old B0 paths, same process, same data
    --stage timing     wall time of B0 and of each variant type on a few decision dates
    --stage passes     the preregistered grid -> data/research/t0701/T_<variant>_o<k>.parquet
    --stage placebo    net-convention placebo (100 seeds) of the selected variant, ``--target fast|full``

Runs on Modal (``scripts/modal_run.py``); ``evaluate`` reads parquets only (separate script).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtri

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book import engine_v2 as ev  # noqa: E402
from scripts import book_v12_account as acct  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261007_01_cost_aware_engine"
OUT_DATA = ROOT / "data/research/t0701"
STORE_DIR = ROOT / "data/research/t0701_store"
PRED = ROOT / "data/research/book_v14/predictions.parquet"
OFFSETS = T25.OFFSETS
START_S0 = T25.START  # 2017-10-02
START_S2 = "2019-01-02"  # first v1.4 out-of-sample prediction
WARMUP_PLACEBO = "2023-11-01"
IDENTITY_TOL = 1e-9
SERIES_COLS = [
    "gross",
    "cost",
    "borrow",
    "turnover",
    "spy",
    "hedge_size",
    "vix_scale",
    "gross_exposure",
    "n_deferred",
    "net",
]
W_F = (0.25, 0.5, 1.0)
C_DEFER = (0.0, 0.5, 1.0)
KAPPAS = (0.05, 0.1, 0.2)
PHI_SLOW_HALF_LIFE_CAP = 252.0


# ---------------------------------------------------------------------------
# preregistered variants
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    vid: str
    slow: str  # M0 | m0m2 | m0m3
    mode: str  # I0 | I1 | I2 | I3
    param: float | None = None  # w_f | c | kappa
    fast: str = "fc_ew"
    placebo: str | None = None  # None | fast | full
    seed: int = 0
    start: str = START_S0
    flag: str = "in_u3000"
    fill: str = "close"
    drop: str | None = None

    @property
    def daily(self) -> bool:
        return self.mode == "I3"


def _tag(x: float) -> str:
    return f"{int(round(x * 100)):03d}"


def grid(include_f: bool = False) -> list[Spec]:
    out = [Spec("B0", "M0", "I0")]
    for slow, sname, start in (("M0", "S0", START_S0), ("m0m2", "S2", START_S2)):
        if sname == "S2":
            out.append(Spec("S2_I0", "m0m2", "I0", None, start=start))
        for w in W_F:
            out.append(Spec(f"{sname}_I1_w{_tag(w)}", slow, "I1", w, start=start))
        for c in C_DEFER:
            out.append(Spec(f"{sname}_I2_c{_tag(c)}", slow, "I2", c, start=start))
        for k in KAPPAS:
            out.append(Spec(f"{sname}_I3_k{_tag(k)}", slow, "I3", k, start=start))
    out.append(Spec("S3_I0", "m0m3", "I0", None, start=START_S2))
    if include_f:
        for k in KAPPAS:
            out.append(Spec(f"S0_I3F_k{_tag(k)}", "M0", "I3", k, fast="fcx", start=START_S0))
    return out


def spec_by_id(vid: str, include_f: bool = True) -> Spec:
    for s in grid(include_f):
        if s.vid == vid:
            return s
    raise KeyError(vid)


# ---------------------------------------------------------------------------
# fast store, placebo ranks
# ---------------------------------------------------------------------------
def rank_normal_np(x: np.ndarray) -> np.ndarray:
    """Vectorised ``optimize.rank_normal``: inverse normal of (average rank - 0.5) / n, NaN stays NaN."""
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    n = int(ok.sum())
    if n == 0:
        return out
    r = pd.Series(x[ok]).rank(method="average").to_numpy()
    out[ok] = ndtri((r - 0.5) / n)
    return out


def _mix(u: np.ndarray) -> np.ndarray:
    u = u.astype("uint64")
    with np.errstate(over="ignore"):
        u = (u ^ (u >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        u = (u ^ (u >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return u ^ (u >> np.uint64(31))


def hash_rank_assign(z: pd.Series, seed: int, t: pd.Timestamp, stream: int) -> pd.Series:
    """Net-convention placebo (standard section 3): each calendar quarter every symbol gets a random rank
    from a hash of (seed, stream, quarter, symbol); the real scores' sorted values are assigned by that rank
    at every date.  Names entering mid-quarter are inserted by their hash.  NaN stays NaN."""
    ok = z.notna().to_numpy()
    if not ok.any():
        return z
    names = z.index[ok]
    q = int(t.year) * 4 + (int(t.month) - 1) // 3
    base = pd.util.hash_array(names.to_numpy(dtype=object)).astype("uint64")
    key = _mix(
        base
        ^ _mix(np.full(len(base), (seed * 1_000_003 + stream * 7919 + q * 104729) & (2**63 - 1)))
    )
    order = np.argsort(key, kind="stable")
    vals = np.sort(z.to_numpy("float64")[ok])
    out = np.empty(len(vals))
    out[order] = vals
    res = z.copy()
    res[ok] = out
    return res


class FastStore:
    """``fc_ew.parquet`` (or ``fcx``): ``z(t, members)`` = rank-normal of the composite over the members."""

    def __init__(self, path: Path) -> None:
        import pyarrow.parquet as pq

        df = pq.read_table(str(path)).to_pandas(categories=["symbol"])
        col = [c for c in df.columns if c not in ("trade_date", "symbol")][0]
        d = df["trade_date"].to_numpy().astype("datetime64[ns]")
        order = np.argsort(d, kind="stable")
        self._dates = d[order]
        self._codes = df["symbol"].cat.codes.to_numpy()[order]
        self._cats = df["symbol"].cat.categories
        self._vals = df[col].to_numpy("float64")[order]
        self._cache: dict[tuple[int, int], pd.Series] = {}

    def z(self, t: pd.Timestamp, members: pd.Index) -> pd.Series:
        key = (int(t.value), len(members))
        hit = self._cache.get(key)
        if hit is not None and hit.index.equals(members):
            return hit
        d = np.datetime64(pd.Timestamp(t).to_datetime64(), "ns")
        lo = int(np.searchsorted(self._dates, d, "left"))
        hi = int(np.searchsorted(self._dates, d, "right"))
        s = pd.Series(self._vals[lo:hi], index=self._cats.take(self._codes[lo:hi]))
        s = s[~s.index.duplicated(keep="first")].reindex(members)
        out = pd.Series(rank_normal_np(s.to_numpy("float64")), index=members)
        if len(self._cache) > 16:
            self._cache.clear()
        self._cache[key] = out
        return out


def make_fast(path: Path | None = None) -> FastStore:
    return FastStore(path or STORE_DIR / "fc_ew.parquet")


def fast_z(
    fast: FastStore, t: pd.Timestamp, members: pd.Index, spec: Spec | None = None
) -> pd.Series:
    z = fast.z(t, members)
    if spec is not None and spec.placebo == "fast":
        z = hash_rank_assign(z, spec.seed, t, stream=1)
    return z


def dense_fast_z(
    ctx: T25.Context, fast: FastStore, t: pd.Timestamp, spec: Spec | None = None
) -> np.ndarray:
    px = ctx.px
    out = np.full(px.N, np.nan)
    th = ctx.themes.at(t)
    if th.empty:
        return out
    members = th.index[th[spec.flag if spec is not None else "in_u3000"].to_numpy(bool)]
    z = fast_z(fast, t, members, spec)
    idx = px.symbols.get_indexer(z.index)
    ok = idx >= 0
    out[idx[ok]] = z.to_numpy()[ok]
    return out


# ---------------------------------------------------------------------------
# slow sources
# ---------------------------------------------------------------------------
def slow_source(ctx: T25.Context, name: str, drop: str | None = None):
    if name == "M0":
        if drop is None:
            return acct.make_source(ctx, "M0_U3000")
        from scripts.run_book_v1_stage2 import AlphaSource

        return AlphaSource(ctx.themes, ctx.fic, "M0", "u3000", drop_theme=drop)
    from scripts.book_v14_ml_eval import PredictionSource

    return PredictionSource(PRED, name)


def set_fill(ctx: T25.Context, fill: str) -> None:
    """Spread snapshot of the cost function follows the fill price (close: MOC, open: MOO)."""
    from open_composer.research.equity_book.costfn import make_cost_fn

    if getattr(ctx, "_fill", "close") != fill:
        ctx.cost_fn = make_cost_fn(fill)
        ctx._fill = fill


# ---------------------------------------------------------------------------
# helpers shared with book_v13_trading_rules
# ---------------------------------------------------------------------------
def dense_eligible(ctx: T25.Context, di: acct.DecisionInputs) -> np.ndarray:
    px = ctx.px
    elig = np.zeros(px.N, dtype=bool)
    idx = px.symbols.get_indexer(di.eligible.index)
    ok = idx >= 0
    elig[idx[ok]] = di.eligible.to_numpy(bool)[ok]
    return elig


def dense_beta(ctx: T25.Context, di: acct.DecisionInputs) -> np.ndarray:
    px = ctx.px
    names = di.score.dropna().index
    idx = px.symbols.get_indexer(names)
    keep = idx >= 0
    b = np.ones(px.N)
    ev_ = di.beta.reindex(names).fillna(1.0).clip(-1.0, 4.0)
    b[idx[keep]] = ev_.to_numpy()[keep]
    return b


def decision_calendar(px: T25.Prices, start: str, offset: int, period: int) -> list[int]:
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    return T25.decision_positions(px.T, first, px.T - 3, period, offset)


def _score_for(di: acct.DecisionInputs, fast: FastStore | None, spec: Spec) -> pd.Series:
    """Score that feeds ``tranche_target`` for this spec (I0/I2: slow; I1: slow + w_f fast)."""
    score = di.score
    if spec.placebo == "full":
        score = hash_rank_assign(score, spec.seed, di.t, stream=2)
    if spec.mode == "I1":
        zf = fast_z(fast, di.t, score.index, spec)
        score = pd.Series(
            ev.combine_score(score.to_numpy("float64"), zf.to_numpy("float64"), spec.param),
            index=score.index,
        )
    return score


def _cost_days(
    ctx: T25.Context,
    p: int,
    di: acct.DecisionInputs,
    d_w: np.ndarray,
    d_h: np.ndarray,
) -> np.ndarray:
    px = ctx.px
    cost = np.zeros(len(d_h))
    for j in range(len(d_h)):
        if not (np.abs(d_w[j]).max() > 1e-12 or abs(d_h[j]) > 1e-12):
            continue
        t = px.dates[p + j]
        attrs = di.attrs if j == 0 else ctx.panel.at(t)
        cost[j] = T25.real_cost(ctx, t, px.symbols, d_w[j], d_h[j], attrs)
    return cost


# ---------------------------------------------------------------------------
# weekly passes (I0, I1, I2): one decision loop, one state per spec
# ---------------------------------------------------------------------------
def weekly_pass(
    ctx: T25.Context,
    specs: list[Spec],
    offset: int,
    fast: FastStore | None,
    *,
    start: str,
    limit: int | None = None,
    hook=None,
) -> dict[str, pd.DataFrame]:
    px = ctx.px
    keys = {(s.slow, s.flag, s.fill, s.drop) for s in specs}
    assert len(keys) == 1, keys
    slow, flag, fill, drop = keys.pop()
    set_fill(ctx, fill)
    src = slow_source(ctx, slow, drop)
    dec = decision_calendar(px, start, offset, T25.WEEK)
    st = {s.vid: {"w": np.zeros(px.N), "h": 0.0, "rows": []} for s in specs}
    tt_cache: dict[tuple, bv.TrancheTarget] = {}
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else px.T - 3 + 1
        length = nxt - p
        di = acct.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        b_ewma = dense_beta(ctx, di)
        ret, spy_r = px.returns(fill, p, length)
        tt_cache.clear()
        for s in specs:
            sc = _score_for(di, fast, s)
            key = (s.mode == "I1", s.param if s.mode == "I1" else None, s.placebo, s.seed)
            tt = tt_cache.get(key)
            if tt is None:
                di_s = di if sc is di.score else dataclasses.replace(di, score=sc)
                tt = acct.tranche_from_inputs(ctx, di_s)
                tt_cache[key] = tt
            state = st[s.vid]
            if s.mode == "I2":
                zf = np.vstack([dense_fast_z(ctx, fast, px.dates[p + d], s) for d in range(length)])
                exec_day = ev.defer_days(tt.w - state["w"], zf, s.param, ev.MAX_DEFER)
            else:
                exec_day = np.zeros(px.N, dtype="int64")
            blk = ev.deferred_block(state["w"], tt.w, exec_day, ret, spy_r, b_ewma, state["h"])
            cost_v = _cost_days(ctx, p, di, blk["d_w"], blk["d_h"])
            to_v = np.abs(blk["d_w"]).sum(axis=1)
            n = len(blk["pnl"])
            ndef = np.zeros(n)
            ndef[0] = float(((exec_day > 0) & (np.abs(tt.w - state["w"]) > 1e-12)).sum())
            bor = blk["short_notional"] * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0)
            state["rows"].append(
                pd.DataFrame(
                    {
                        "gross": blk["pnl"],
                        "cost": cost_v,
                        "borrow": bor,
                        "turnover": to_v,
                        "spy": spy_r,
                        "hedge_size": np.full(n, float(-np.nansum(tt.w * b_ewma))),
                        "vix_scale": np.full(n, tt.vscale),
                        "gross_exposure": np.full(n, float(np.abs(tt.w).sum())),
                        "n_deferred": ndef,
                    },
                    index=px.dates[p : p + n],
                )
            )
            state["w"], state["h"] = blk["w_end"], blk["h_end"]
    out = {}
    for s in specs:
        df = pd.concat(st[s.vid]["rows"])
        df["net"] = df["gross"] - df["cost"] - df["borrow"]
        out[s.vid] = df[SERIES_COLS]
    return out


# ---------------------------------------------------------------------------
# daily passes (I3): aim book, partial adjustment every session
# ---------------------------------------------------------------------------
def load_gp_params(path: Path | None = None) -> dict:
    """Half-lives and b_k from the stress window of P1 stage 0 (frozen rule of the contract)."""
    p = path or ROOT / "reports/research/iterations/t20261005_p1_s0_decay/results.json"
    r = json.loads(p.read_text())
    w = r["objects"]
    fast = w["FC_EW"]["windows"]["L12"]["stress"]
    slow = w["m0_composite"]["windows"]["L12"]["stress"]
    hl_fast = float(fast["h_exp"])
    hl_slow = min(float(slow["h_exp"]), PHI_SLOW_HALF_LIFE_CAP)
    return {
        "b": {"slow": float(slow["ic_mean"][1]), "fast": float(fast["ic_mean"][1])},
        "phi": {
            "slow": ev.phi_from_half_life(hl_slow),
            "fast": ev.phi_from_half_life(hl_fast),
        },
        "half_life": {"slow": hl_slow, "fast": hl_fast},
        "source": str(p.relative_to(ROOT)),
        "window": "stress 2017-10-02..2023-08-31, L12, lag 2 mean IC and h_exp",
    }


def daily_pass(
    ctx: T25.Context,
    specs: list[Spec],
    fasts: dict[str, FastStore],
    gp: dict,
    *,
    start: str,
    limit: int | None = None,
    hook=None,
) -> dict[str, pd.DataFrame]:
    px = ctx.px
    keys = {(s.slow, s.flag, s.fill, s.drop) for s in specs}
    assert len(keys) == 1, keys
    slow, flag, fill, drop = keys.pop()
    set_fill(ctx, fill)
    src = slow_source(ctx, slow, drop)
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    dec = list(range(first, px.T - 3 + 1))
    st = {s.vid: {"w": np.zeros(px.N), "h": 0.0, "rows": []} for s in specs}
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        di = acct.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        elig = dense_eligible(ctx, di)
        b_ewma = dense_beta(ctx, di)
        ret, spy_r = px.returns(fill, p, 1)
        for s in specs:
            zs = di.score
            if s.placebo == "full":
                zs = hash_rank_assign(zs, s.seed, di.t, stream=2)
            zf = fast_z(fasts[s.fast], di.t, zs.index, s)
            score = pd.Series(
                ev.gp_score(
                    zs.to_numpy("float64"), zf.to_numpy("float64"), gp["b"], gp["phi"], s.param
                ),
                index=zs.index,
            )
            di_s = dataclasses.replace(di, score=score)
            tt = acct.tranche_from_inputs(ctx, di_s)
            state = st[s.vid]
            x_new = ev.partial_adjust(state["w"], tt.w, s.param, elig, di.fill_ok)
            if hook is not None:
                hook(s, p, di, x_new)
            h_new = float(-np.nansum(x_new * b_ewma))
            blk = bv.hold_block(x_new, ret, spy_r, h0=h_new)
            d_w = x_new - state["w"]
            d_h = h_new - state["h"]
            cost = T25.real_cost(ctx, di.t, px.symbols, d_w, d_h, di.attrs)
            state["rows"].append(
                pd.DataFrame(
                    {
                        "gross": blk["pnl"],
                        "cost": [cost],
                        "borrow": blk["short_notional"] * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0),
                        "turnover": [float(np.abs(d_w).sum())],
                        "spy": spy_r,
                        "hedge_size": [h_new],
                        "vix_scale": [tt.vscale],
                        "gross_exposure": [float(np.abs(x_new).sum())],
                        "n_deferred": [0.0],
                    },
                    index=px.dates[p : p + 1],
                )
            )
            state["w"], state["h"] = blk["w_end"], blk["h_end"]
    out = {}
    for s in specs:
        df = pd.concat(st[s.vid]["rows"])
        df["net"] = df["gross"] - df["cost"] - df["borrow"]
        out[s.vid] = df[SERIES_COLS]
    return out


# ---------------------------------------------------------------------------
# io, tasks
# ---------------------------------------------------------------------------
def t_path(vid: str, o: int, base: Path = OUT_DATA) -> Path:
    return base / f"T_{vid}_o{o}.parquet"


def jdump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=1, default=float))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_list(include_f: bool = False) -> list[tuple[str, int, tuple[str, ...]]]:
    """(group, offset, vids).  Groups: g0 (S0 weekly), g2 (S2 weekly), g3 (m0m3 I0), d0 / d2 (daily I3)."""
    specs = grid(include_f)
    out: list[tuple[str, int, tuple[str, ...]]] = []
    wk0 = tuple(s.vid for s in specs if s.slow == "M0" and not s.daily)
    wk2 = tuple(s.vid for s in specs if s.slow == "m0m2" and not s.daily)
    wk3 = tuple(s.vid for s in specs if s.slow == "m0m3" and not s.daily)
    for o in OFFSETS:
        out += [("g0", o, wk0), ("g2", o, wk2), ("g3", o, wk3)]
    out.append(("d0", 0, tuple(s.vid for s in specs if s.slow == "M0" and s.daily)))
    out.append(("d2", 0, tuple(s.vid for s in specs if s.slow == "m0m2" and s.daily)))
    return out


_CTX: T25.Context | None = None
_FAST: dict[str, FastStore] = {}


def get_ctx() -> T25.Context:
    global _CTX
    if _CTX is None:
        _CTX = T25.Context()
    return _CTX


def get_fast(key: str) -> FastStore:
    if key not in _FAST:
        _FAST[key] = make_fast(STORE_DIR / f"{key}.parquet" if key != "fc_ew" else None)
    return _FAST[key]


def run_task(
    group: str, o: int, vids: tuple[str, ...], limit: int | None = None
) -> dict[str, pd.DataFrame]:
    ctx = get_ctx()
    specs = [spec_by_id(v) for v in vids]
    if not specs:
        return {}
    start = specs[0].start
    if group.startswith("d"):
        fasts = {s.fast: get_fast(s.fast) for s in specs}
        return daily_pass(ctx, specs, fasts, load_gp_params(), start=start, limit=limit)
    need_fast = any(s.mode in ("I1", "I2") for s in specs)
    return weekly_pass(
        ctx, specs, o, get_fast("fc_ew") if need_fast else None, start=start, limit=limit
    )


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------
def max_diff(a: pd.DataFrame, b: pd.DataFrame, cols: tuple[str, ...]) -> dict:
    if not a.index.equals(b.index):
        return {"index_equal": False, "rows_a": len(a), "rows_b": len(b)}
    return {"index_equal": True, **{c: float((a[c] - b[c]).abs().max()) for c in cols}}


def run_identity(limit: int | None, offsets: tuple[int, ...]) -> dict:
    """New engine with S0/I0 (and w_f = 0, c = None) against the old B0 loops of the same process."""
    from scripts import book_v13_trading_rules as v13
    from scripts.book_v14_ml_eval import strategy_pass_with_source

    ctx = get_ctx()
    cols = ("gross", "cost", "borrow", "turnover", "net")
    res: dict = {"tolerance": IDENTITY_TOL, "limit": limit, "cases": {}, "pass": True}
    worst = 0.0
    for o in offsets:
        t0 = time.time()
        new = weekly_pass(ctx, [Spec("B0", "M0", "I0")], o, None, start=START_S0, limit=limit)["B0"]
        sec_new = time.time() - t0
        t0 = time.time()
        old = v13.rules_pass(ctx, "M0_U3000", o, ("B0",), limit=limit)["B0"]
        sec_old = time.time() - t0
        z = weekly_pass(
            ctx,
            [Spec("Z1", "M0", "I1", 0.0), Spec("Z2", "M0", "I2", None)],
            o,
            make_fast(),
            start=START_S0,
            limit=limit,
        )
        d_old = max_diff(new, old, cols)
        d_z1 = max_diff(new, z["Z1"], cols)
        d_z2 = max_diff(new, z["Z2"], cols)
        case: dict = {
            "new_vs_old_b0": d_old,
            "new_vs_i1_w0": d_z1,
            "new_vs_i2_off": d_z2,
            "seconds_new_b0": round(sec_new, 1),
            "seconds_old_b0": round(sec_old, 1),
            "rows": len(new),
        }
        saved = pd.read_parquet(T25.RAW / f"R6_M0_U3000_o{o}.parquet")
        sub = saved.loc[new.index] if limit is not None else saved
        case["new_vs_saved_r6_report_only"] = max_diff(new, sub, cols)
        vals = [
            v
            for dd in (d_old, d_z1, d_z2)
            for k, v in dd.items()
            if k != "index_equal" and isinstance(v, float)
        ]
        ok = all(dd.get("index_equal") for dd in (d_old, d_z1, d_z2)) and max(vals) <= IDENTITY_TOL
        case["pass"] = bool(ok)
        worst = max(worst, max(vals))
        res["pass"] = bool(res["pass"] and ok)
        res["cases"][f"B0_o{o}"] = case
        print("identity B0 offset", o, case["new_vs_old_b0"], flush=True)
    # S2 / I0 against the v1.4 loop of the same process (offset 0 only)
    o = offsets[0]
    new2 = weekly_pass(
        ctx, [Spec("S2_I0", "m0m2", "I0", start=START_S2)], o, None, start=START_S2, limit=limit
    )["S2_I0"]
    from scripts.book_v14_ml_eval import PredictionSource

    old2 = strategy_pass_with_source(
        ctx, PredictionSource(PRED, "m0m2"), "in_u3000", o, START_S2, limit
    )
    d2 = max_diff(new2, old2, cols)
    vals2 = [v for k, v in d2.items() if k != "index_equal" and isinstance(v, float)]
    ok2 = bool(d2.get("index_equal") and max(vals2) <= IDENTITY_TOL)
    res["cases"][f"S2_I0_o{o}"] = {"new_vs_old_v14_loop": d2, "pass": ok2}
    res["pass"] = bool(res["pass"] and ok2)
    res["max_abs_diff"] = max([worst, *vals2])
    return res


def run_timing(n_dec: int) -> dict:
    ctx = get_ctx()
    fast = make_fast()
    gp = load_gp_params()
    out: dict = {"n_decisions": n_dec, "gp": gp, "seconds": {}}
    for name, specs in (
        ("I0", [Spec("B0", "M0", "I0")]),
        ("I1", [Spec("a", "M0", "I1", 0.5)]),
        ("I2", [Spec("b", "M0", "I2", 0.5)]),
    ):
        t0 = time.time()
        weekly_pass(ctx, specs, 0, fast, start="2024-01-08", limit=n_dec)
        out["seconds"][name] = round(time.time() - t0, 2)
    t0 = time.time()
    daily_pass(
        ctx,
        [Spec("c", "M0", "I3", 0.1, start="2024-01-08")],
        {"fc_ew": fast},
        gp,
        start="2024-01-08",
        limit=n_dec * 5,
    )
    out["seconds"]["I3_daily_5x"] = round(time.time() - t0, 2)
    return out


def run_passes(group_filter: set[str] | None, limit: int | None, include_f: bool) -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    for group, o, vids in task_list(include_f):
        if group_filter and group not in group_filter:
            continue
        todo = [v for v in vids if not t_path(v, o).exists()]
        if not todo and limit is None:
            print(group, o, "checkpoints exist, skip", flush=True)
            continue
        t0 = time.time()
        out = run_task(group, o, tuple(todo or vids), limit)
        for vid, df in out.items():
            dst = t_path(vid, o) if limit is None else OUT_DATA / f"debug_{vid}_o{o}.parquet"
            df.to_parquet(dst)
        print(group, "offset", o, "done", list(out), f"{time.time() - t0:.0f}s", flush=True)


def run_placebo(vid: str, target: str, seeds: range, limit: int | None) -> None:
    """Candidate ``vid`` with the fast composite (``fast``) or the whole driving score (``full``) replaced
    by the hash-rank placebo; seed 0 = real run, ``B0w`` = reference; everything from ``WARMUP_PLACEBO``."""
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    base = spec_by_id(vid)
    ctx = get_ctx()
    fast = get_fast(base.fast)
    specs = [
        dataclasses.replace(
            base,
            vid=f"{vid}__{target}{s:03d}",
            placebo=None if s == 0 else target,
            seed=s,
            start=WARMUP_PLACEBO,
        )
        for s in seeds
    ]
    ref = Spec("B0w", "M0", "I0", start=WARMUP_PLACEBO)
    for o in OFFSETS:
        b0 = weekly_pass(ctx, [ref], o, None, start=WARMUP_PLACEBO, limit=limit)
        b0["B0w"].to_parquet(OUT_DATA / f"P_B0w_o{o}.parquet")
        if base.daily:
            if o == 0:
                outs = daily_pass(
                    ctx,
                    specs,
                    {base.fast: fast},
                    load_gp_params(),
                    start=WARMUP_PLACEBO,
                    limit=limit,
                )
            else:
                continue
        else:
            outs = weekly_pass(ctx, specs, o, fast, start=WARMUP_PLACEBO, limit=limit)
        for k, df in outs.items():
            df.to_parquet(OUT_DATA / f"P_{k}_o{o}.parquet")
        print("placebo", vid, target, "offset", o, "done", flush=True)


def diag_specs(base: Spec) -> list[Spec]:
    """Diagnostics of the selected point (reported, never used to select): P1000 universe, MOO fill,
    each slow theme dropped (M0 route), no fast signal."""
    from scripts.run_book_v1_stage2 import THEMES

    out = [
        dataclasses.replace(base, vid=f"{base.vid}__p1000", flag="in_p1000"),
        dataclasses.replace(base, vid=f"{base.vid}__moo", fill="open"),
        Spec(f"{base.vid}__nofast", base.slow, "I0", start=base.start),
    ]
    if base.slow == "M0":
        out += [dataclasses.replace(base, vid=f"{base.vid}__drop_{t}", drop=t) for t in THEMES]
    return out


def run_diag(vid: str, limit: int | None) -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    base = spec_by_id(vid)
    ctx = get_ctx()
    gp = load_gp_params()
    for s in diag_specs(base):
        t0 = time.time()
        if s.daily:
            fasts = {s.fast: get_fast(s.fast)}
            outs = {0: daily_pass(ctx, [s], fasts, gp, start=s.start, limit=limit)}
        else:
            need_fast = s.mode in ("I1", "I2")
            outs = {
                o: weekly_pass(
                    ctx, [s], o, get_fast(s.fast) if need_fast else None, start=s.start, limit=limit
                )
                for o in OFFSETS
            }
        for o, d in outs.items():
            d[s.vid].to_parquet(OUT_DATA / f"D_{s.vid}_o{o}.parquet")
        print("diag", s.vid, f"{time.time() - t0:.0f}s", flush=True)


ACCOUNT_SCALE = (
    0.5  # F1 overlay scale k = 0.5 * vix scale (vix scale is already inside the weights)
)
MIN_ORDER = 100.0


def run_account_diag(
    vid: str, limit: int | None, capitals: tuple[float, ...] = (300_000.0, 1_000_000.0)
) -> None:
    """Simplified whole-share rendering of a daily-book candidate's own target weights (no margin, no
    delisting, no T-bill leg): shares = round_half_away(0.5 * x * capital / P_ref), an order below $100 is
    dropped.  Reports the three V2 metrics of ``book_v12_small`` per session, the dropped-order share and
    the number of orders."""
    base = spec_by_id(vid)
    assert base.daily, "account diagnostic is written for the daily book"
    ctx = get_ctx()
    px = ctx.px
    qty = {c: np.zeros(px.N, dtype="int64") for c in capitals}
    rows: dict[float, list[dict]] = {c: [] for c in capitals}

    def hook(s: Spec, p: int, di: acct.DecisionInputs, x_new: np.ndarray) -> None:
        pref = px.C[p]
        adv = di.attrs.reindex(px.symbols)["dollar_adv_21"].to_numpy("float64")
        okp = np.isfinite(pref) & (pref > 0)
        for c in capitals:
            tgt = np.where(okp, ACCOUNT_SCALE * x_new * c, 0.0)
            with np.errstate(invalid="ignore", divide="ignore"):
                post = bv.round_half_away_array(np.where(okp, tgt / pref, 0.0))
            delta = post - qty[c]
            notional = np.abs(delta) * np.where(okp, pref, 0.0)
            dropped = (delta != 0) & (notional < MIN_ORDER)
            order = np.where(dropped, 0, delta)
            qty[c] = qty[c] + order
            val = qty[c] * np.where(okp, pref, 0.0)
            t_short, r_short = -tgt[tgt < 0].sum(), -val[val < 0].sum()
            t_abs = float(np.abs(tgt).sum())
            with np.errstate(invalid="ignore", divide="ignore"):
                ratio = np.abs(order) * np.where(okp, pref, 0.0) / adv
            ratio = ratio[np.isfinite(ratio) & (order != 0)]
            rows[c].append(
                {
                    "date": di.t,
                    "short_gross_ratio": float(r_short / t_short) if t_short > 0 else 1.0,
                    "rel_l1": float(np.abs(val - tgt).sum() / t_abs) if t_abs > 0 else 0.0,
                    "net_dollar_err": float((val.sum() - tgt.sum()) / c),
                    "adv_frac_max": float(ratio.max()) if len(ratio) else 0.0,
                    "n_orders": int((order != 0).sum()),
                    "n_dropped": int(dropped.sum()),
                    "n_wanted": int((delta != 0).sum()),
                    "turnover_value": float(np.abs(order * np.where(okp, pref, 0.0)).sum()),
                }
            )

    daily_pass(
        ctx,
        [base],
        {base.fast: get_fast(base.fast)},
        load_gp_params(),
        start=base.start,
        limit=limit,
        hook=hook,
    )
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    for c in capitals:
        pd.DataFrame(rows[c]).to_parquet(OUT_DATA / f"A_{vid}_{int(c)}.parquet")
        print("account diag", vid, int(c), len(rows[c]), flush=True)


def main() -> None:
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["identity", "timing", "passes", "placebo", "diag", "account"],
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offsets", default="0,3")
    ap.add_argument("--groups", default=None, help="comma list of g0,g2,g3,d0,d2")
    ap.add_argument("--include-f", action="store_true")
    ap.add_argument("--vid", default=None)
    ap.add_argument("--target", default="fast", choices=["fast", "full"])
    ap.add_argument("--seeds", default="0:101", help="a:b, seed 0 = real run")
    ap.add_argument("--out", default=None, help="iteration-folder json for identity/timing")
    ns = ap.parse_args()
    if ns.stage == "identity":
        res = run_identity(ns.limit, tuple(int(x) for x in ns.offsets.split(",")))
        ITER.mkdir(parents=True, exist_ok=True)
        jdump(ITER / (ns.out or "identity.json"), res)
        print("identity pass:", res["pass"], "worst", res.get("max_abs_diff"))
    elif ns.stage == "timing":
        res = run_timing(ns.limit or 20)
        ITER.mkdir(parents=True, exist_ok=True)
        jdump(ITER / (ns.out or "timing.json"), res)
        print(json.dumps(res["seconds"]))
    elif ns.stage == "passes":
        run_passes(set(ns.groups.split(",")) if ns.groups else None, ns.limit, ns.include_f)
    elif ns.stage == "diag":
        run_diag(ns.vid, ns.limit)
    elif ns.stage == "account":
        run_account_diag(ns.vid, ns.limit)
    else:
        a, b = (int(x) for x in ns.seeds.split(":"))
        run_placebo(ns.vid, ns.target, range(a, b), ns.limit)


if __name__ == "__main__":
    main()
