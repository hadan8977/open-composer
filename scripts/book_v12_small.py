# ruff: noqa: E501
"""Book v1.2 small-capital construction, Stage A (T-20261005-37).

Contract: ``reports/research/iterations/t20261006_p1_v12_small/hypotheses.md`` plus
``amendment-A1.md``.  One pass over the sessions steps every account together (decision inputs are
computed once per day); each config writes ``data/research/book_v12_small/<config_id>.parquet``.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_small.py --stage identity --limit 300
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_small.py --stage run [--configs G_CAND]
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_small.py --stage evaluate

Rehedge (contract section 3): the SPY hedge of the concentrated, rounded book is
``-sum_i q_i * P_ref_i * beta_i`` (beta of the refresh-day decision input, missing 1.0, clipped to
[-1, 4], aligned like ``bv.tranche_target``).  This equals the original aggregate hedge times the
beta-exposure ratio of the contract, written without the ratio's near-zero denominator.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from scripts import book_v12_account as acc  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

OUT_DATA = ROOT / "data/research/book_v12_small"
OUT_REPORT = ROOT / "reports/research/iterations/t20261006_p1_v12_small"
A1_DIR = ROOT / "data/research/book_v12"
VARIANT = "M0_U3000"
IDENTITY_TOL = 1e-12
HURDLE = 1.25
MIN_LONG_NOTIONAL = 1.0  # Alpaca minimum fractional order
PRAND_BASE_SEED = 20261006
V2 = {
    "short_gross_ratio_min": 0.9,
    "rel_l1_max": 0.3,
    "net_dollar_abs_max": 0.05,
    "adv_frac_max": 0.01,
}
WIN = {"recent": ("2024-01-08", "2026-09-15"), "stress": ("2017-10-02", "2023-08-31")}


# ---------------------------------------------------------------------------
# pure construction functions (tested on toy arrays)
# ---------------------------------------------------------------------------
def _select_side(
    mag: np.ndarray,
    k: int,
    key: np.ndarray,
    held: np.ndarray | None,
    hurdle: float | None,
) -> np.ndarray:
    """Boolean mask of the kept names on one side.  ``mag`` > 0 marks the names on the side;
    ``key`` ranks them (larger first); ``held``/``hurdle`` switch on the R1B memory."""
    cand = np.flatnonzero(mag > 0)
    keep = np.zeros(len(mag), dtype=bool)
    if len(cand) <= k:
        keep[cand] = True
        return keep
    if held is None:
        order = cand[np.argsort(-key[cand], kind="stable")]
        keep[order[:k]] = True
        return keep
    cur = held & (mag > 0)
    n_cur = int(cur.sum())
    nonheld = cand[~cur[cand]]
    nh = nonheld[np.argsort(-mag[nonheld], kind="stable")]
    if n_cur < k:
        add = nh[: k - n_cur]
        cur[add] = True
        nh = nh[k - n_cur :]
    if hurdle is not None and len(nh):
        hd = np.flatnonzero(cur)
        hd = hd[np.argsort(mag[hd], kind="stable")]
        for i in range(min(len(hd), len(nh))):
            if mag[nh[i]] >= hurdle * mag[hd[i]]:
                cur[hd[i]] = False
                cur[nh[i]] = True
            else:
                break
    return cur


def concentrate(
    virt: np.ndarray,
    p_ref: np.ndarray,
    method: str,
    k: int | None,
    held: dict[int, np.ndarray] | None = None,
    hurdle: float | None = None,
    priority: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[int, np.ndarray] | None]:
    """Concentrated aggregate book (shares) and the updated R1B memory.

    ``virt`` is the aggregate of the tranche virtual shares; values are ``virt * p_ref``."""
    if method in ("R0", "orig"):
        return virt, held
    bad = ~(np.isfinite(p_ref) & (p_ref > 0))  # no price today: untradable, passed through
    if method == "R3":
        return np.where((virt < 0) & ~bad, 0.0, virt), held
    v = virt * np.where(bad, 0.0, p_ref)
    out = np.where(bad, virt, 0.0)
    new_held: dict[int, np.ndarray] | None = {} if method == "R1B" else None
    for sign in (1, -1):
        side = (v * sign) > 0
        mag = np.where(side, np.abs(v), 0.0)
        if k is None or int(side.sum()) <= k:
            keep = side
        else:
            if method == "PRAND":
                key = priority
            else:
                key = mag
            mem = (held or {}).get(sign, np.zeros(len(v), dtype=bool)) if method == "R1B" else None
            keep = _select_side(mag, k, key, mem, hurdle if method == "R1B" else None)
        if new_held is not None:
            new_held[sign] = keep.copy()
        if keep.sum() == 0:
            continue
        before = float(mag.sum())
        kept = float(mag[keep].sum())
        factor = 1.0 if (k is None or kept == before) else before / kept
        out[keep] = virt[keep] * factor
    return out, new_held


def round_orders(
    target: np.ndarray,
    qty: np.ndarray,
    p_ref: np.ndarray,
    min_long_notional: float = MIN_LONG_NOTIONAL,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fractional long / whole-share short rounding.  ``target`` is the (concentrated, scaled)
    virtual shares.  Returns ``(post_qty, order_qty, dropped)``."""
    pr = np.where(np.isfinite(p_ref), p_ref, 0.0)
    neg = target < 0
    tq = np.where(neg, bv.round_half_away_array(target), target)
    delta = tq - qty
    notional = np.abs(delta) * pr
    dropped = np.where(
        neg, (delta != 0) & (np.abs(delta) < 1.0), (delta != 0) & (notional < min_long_notional)
    )
    order = np.where(dropped, 0.0, delta)
    return qty + order, order, dropped


def rehedge_value(qty: np.ndarray, p_ref: np.ndarray, beta: np.ndarray) -> float:
    """SPY hedge value of a stock book: ``-sum q P beta`` (names without a price count 0)."""
    pr = np.where(np.isfinite(p_ref), p_ref, 0.0)
    return float(-(qty * pr * beta).sum())


def dense_beta(beta: pd.Series, score_index: pd.Index, symbols: pd.Index) -> np.ndarray:
    """Per-name beta as ``bv.tranche_target`` builds it: 1.0 everywhere, the clipped EWMA beta on
    the names of the day's score (the target-weight index)."""
    out = np.ones(len(symbols))
    idx = symbols.get_indexer(score_index)
    keep = idx >= 0
    ev = beta.reindex(score_index).fillna(1.0).clip(-1.0, 4.0)
    out[idx[keep]] = ev.to_numpy()[keep]
    return out


# ---------------------------------------------------------------------------
# simulator
# ---------------------------------------------------------------------------
class SmallSim(acc.AccountSim):
    def __init__(
        self,
        form: str,
        ctx: T25.Context,
        etf: dict[str, np.ndarray],
        cf: np.ndarray,
        capital: float,
        method: str,
        k: int | None = None,
        hurdle: float | None = None,
        seed: int | None = None,
        long_fractional: bool = True,
        min_notional_whole: float | None = None,
        rehedge: bool = True,
    ):
        super().__init__(form, ctx, etf, cf)
        self.capital = float(capital)
        self.method = method
        self.k = k
        self.hurdle = hurdle if hurdle is not None else (HURDLE if method == "R1B" else None)
        self.long_fractional = bool(long_fractional) and method != "orig"
        self.rehedge = bool(rehedge) and method != "orig"
        self.mn_whole = (
            min_notional_whole
            if min_notional_whole is not None
            else (bv.MIN_NOTIONAL if method == "orig" else 0.0)
        )
        if self.long_fractional:
            self.qty = np.zeros(ctx.px.N)
        self.beta = np.ones(ctx.px.N)
        self.held: dict[int, np.ndarray] | None = {} if method == "R1B" else None
        self.priority = (
            np.random.default_rng(PRAND_BASE_SEED + int(seed or 0)).random(ctx.px.N)
            if method == "PRAND"
            else None
        )
        self._conc: np.ndarray | None = None

    def refresh(self, o, tt, p_ref, spy_ref, beta=None):  # type: ignore[override]
        k = (
            bv.f1_k_eff(tt.vscale, tt.h_unit)
            if self.form == "F1"
            else bv.f2_k2_eff(tt.vscale, tt.h_unit)
        )
        v = bv.virtual_shares(tt.w_unit, k, self.capital, p_ref)
        v[self.dead] = 0.0
        self.virt[o] = v
        self.virt_h[o] = tt.h_unit * k * (self.capital / bv.N_TRANCHES) / spy_ref
        if beta is not None:
            self.beta = beta
        self._conc = None

    def _concentrated(self, p_ref: np.ndarray) -> np.ndarray:
        if self._conc is None:
            virt_total = self.virt.sum(axis=0)
            self._conc, self.held = concentrate(
                virt_total, p_ref, self.method, self.k, self.held, self.hurdle, self.priority
            )
        return self._conc

    def _targets(self, scale: float, p_ref: np.ndarray, spy_ref: float):  # type: ignore[override]
        virt_total = self.virt.sum(axis=0)
        conc = self._concentrated(p_ref) if self.method != "orig" else virt_total
        tgt_spy = float(self.virt_h.sum()) * scale
        if self.form == "F2":
            tgt_spy += bv.F2_CORE * self.capital / spy_ref
        if self.method == "orig" or not self.long_fractional:
            post_q, ord_q, drop = bv.aggregate_targets(
                conc, p_ref, self.qty, min_notional=self.mn_whole, scale=scale
            )
        else:
            post_q, ord_q, drop = round_orders(conc * scale, self.qty, p_ref)
        if self.rehedge:
            h_val = rehedge_value(post_q, p_ref, self.beta)
            tgt_spy = h_val / spy_ref + (
                bv.F2_CORE * self.capital / spy_ref if self.form == "F2" else 0.0
            )
        post_spy, ord_spy, drop_spy = bv.aggregate_targets(
            np.array([tgt_spy]),
            np.array([spy_ref]),
            np.array([self.qty_spy]),
            min_notional=self.mn_whole,
            scale=1.0,
        )
        val = post_q * np.where(np.isfinite(p_ref), p_ref, 0.0)
        spy_val = float(post_spy[0]) * spy_ref
        long_f = (val[val > 0].sum() + max(spy_val, 0.0)) / self.capital
        short_f = (-val[val < 0].sum() + max(-spy_val, 0.0)) / self.capital
        return conc, post_q, ord_q, drop, post_spy, ord_spy, drop_spy, val, long_f, short_f, tgt_spy

    def step(self, p, attrs, p_ref, last_valid, delist_flagged, calendar_days) -> dict:  # type: ignore[override]
        px, ctx = self.px, self.ctx
        cap = self.capital
        t = px.dates[p]
        spy_ref = float(px.spy_c[p])
        spy_now, spy_next = float(px.spy_c[p + 1]), float(px.spy_c[p + 2])
        bil_ref = float(self.etf["BIL_c"][p])
        bil_now, bil_next = float(self.etf["BIL_c"][p + 1]), float(self.etf["BIL_c"][p + 2])
        pf_now, pf_next = self.cf[p + 1], self.cf[p + 2]
        scale, scale_event = 1.0, 0
        res = self._targets(scale, p_ref, spy_ref)
        long_f, short_f = res[8], res[9]
        if self.form == "F1" and long_f + short_f > bv.G_CAP + 1e-12:
            scale = bv.gross_scale(long_f, short_f)
            scale_event = 1
            res = self._targets(scale, p_ref, spy_ref)
            long_f, short_f = res[8], res[9]
        conc, post_q, ord_q, drop, post_spy, ord_spy, drop_spy, val, _, _, tgt_spy = res
        if self.form == "F1":
            x = bv.tbill_fraction(long_f, short_f)
            post_bil, ord_bil, drop_bil = bv.aggregate_targets(
                np.array([x * cap / bil_ref]),
                np.array([bil_ref]),
                np.array([self.qty_bil]),
                min_notional=self.mn_whole,
                scale=1.0,
            )
        else:
            post_bil, ord_bil, drop_bil = np.array([self.qty_bil]), np.array([0]), np.array([False])
        nz = np.flatnonzero(ord_q)
        sym = list(px.symbols[nz])
        amt = list(ord_q[nz] * p_ref[nz])
        if ord_spy[0] != 0:
            sym.append("SPY")
            amt.append(float(ord_spy[0]) * spy_ref)

        def cost_of(symbols: list[str], amounts: list[float]) -> tuple[float, np.ndarray]:
            if not symbols:
                return 0.0, np.array([])
            a = attrs.reindex(symbols)
            trades = pd.DataFrame(
                {
                    "symbol": symbols,
                    "dollar_trade": amounts,
                    "price": a["close"].to_numpy(),
                    "prior_close": a["close"].to_numpy(),
                    "dollar_adv_21": a["dollar_adv_21"].to_numpy(),
                    "vol_21": a["vol_21"].to_numpy(),
                    "trade_date": t,
                }
            )
            c = ctx.cost_fn(trades, None)
            return float(c["spread"] + c["impact"] + c["fees"]), a["dollar_adv_21"].to_numpy()

        cost_overlay, adv = cost_of(sym, amt)
        adv_max = adv_mean = float("nan")
        if len(nz):
            a_ = adv[: len(nz)]
            ratio = np.abs(ord_q[nz] * p_ref[nz]) / np.where(a_ > 0, a_, np.nan)
            ratio = ratio[np.isfinite(ratio)]
            if len(ratio):
                adv_max, adv_mean = float(ratio.max()), float(ratio.mean())
        cost_bil = cost_of(["BIL"], [float(ord_bil[0]) * bil_ref])[0] if ord_bil[0] != 0 else 0.0
        cost = cost_overlay + cost_bil
        n_orders = int((ord_q != 0).sum() + (ord_spy[0] != 0) + (ord_bil[0] != 0))
        n_dropped = int(drop.sum() + drop_spy.sum() + drop_bil.sum())
        pr0 = np.where(np.isfinite(p_ref), p_ref, 0.0)
        v_value = conc * scale * pr0
        tgt_spy_val = tgt_spy * spy_ref
        drift = float(
            (np.abs(val - v_value).sum() + abs(float(post_spy[0]) * spy_ref - tgt_spy_val))
            / cap
            / 2.0
        )
        # V2 feasibility against the concentrated target before rounding (stock names only)
        t_short, r_short = -v_value[v_value < 0].sum(), -val[val < 0].sum()
        t_abs = float(np.abs(v_value).sum())
        v2_short = float(r_short / t_short) if t_short > 0 else 1.0
        v2_l1 = float(np.abs(val - v_value).sum() / t_abs) if t_abs > 0 else 0.0
        v2_net = float((val.sum() - v_value.sum()) / cap)
        self.qty, self.qty_spy, self.qty_bil = post_q, int(post_spy[0]), int(post_bil[0])
        qf = self.qty.astype(float)
        long_mv = float(pf_now[self.qty > 0] @ qf[self.qty > 0])
        short_stock = float(-(pf_now[self.qty < 0] @ qf[self.qty < 0]))
        long_mv += max(self.qty_spy, 0) * spy_now + self.qty_bil * bil_now
        short_mv = short_stock + max(-self.qty_spy, 0) * spy_now
        eq_pre = cap + self.cum_net - cost
        cash = eq_pre - long_mv + short_mv
        interest = bv.debit_interest(cash, calendar_days)
        qty_all = np.concatenate([qf, [self.qty_spy, self.qty_bil]])
        pr_all = np.concatenate([pf_now, [spy_now, bil_now]])
        maint = bv.maintenance_requirement(qty_all, pr_all)
        init_req = bv.initial_margin_requirement(long_mv, short_mv)
        stock_pnl = float((pf_next - pf_now) @ qf)
        spy_pnl = self.qty_spy * (spy_next - spy_now)
        tbill_pnl = self.qty_bil * (bil_next - bil_now)
        delist_adj = 0.0
        gone = np.flatnonzero(delist_flagged & ~self.dead & (last_valid == p + 1))
        for j in gone:
            delist_adj += bv.delist_adjustment(float(self.qty[j]), float(pf_now[j]))
        if len(gone):
            self.dead[gone] = True
            self.qty[gone] = 0
            self.virt[:, gone] = 0.0
        net = stock_pnl + spy_pnl + tbill_pnl - cost - interest + delist_adj
        self.cum_net += net
        row = dict(
            stock_pnl=stock_pnl,
            spy_pnl=spy_pnl,
            tbill_pnl=tbill_pnl,
            cost=cost,
            borrow=0.0,
            interest=interest,
            delist_adj=delist_adj,
            net_pnl=net,
            equity=cap + self.cum_net,
            long_mv=long_mv,
            short_mv=short_mv,
            gross=long_mv + short_mv,
            init_excess=eq_pre - init_req,
            maint_excess=eq_pre - maint,
            n_orders=n_orders,
            n_dropped=n_dropped,
            rounding_drift=drift,
            scale_events=scale_event,
            cost_overlay=cost_overlay,
            cost_bil=cost_bil,
            cash=cash,
            short_mv_stock=short_stock,
            bil_ret=bil_next / bil_now - 1.0,
            spy_ret=spy_next / spy_now - 1.0,
            adv_frac_max=adv_max,
            adv_frac_mean=adv_mean,
            short_gross_ratio=v2_short,
            rel_l1=v2_l1,
            net_dollar_err=v2_net,
            n_long=int((self.qty > 0).sum()),
            n_short=int((self.qty < 0).sum()),
            turnover_value=float(np.abs(ord_q * pr0).sum() + abs(float(ord_spy[0])) * spy_ref),
        )
        self.rows.append(row | {"date": t})
        return row


# ---------------------------------------------------------------------------
# config table
# ---------------------------------------------------------------------------
def config_table() -> dict[str, dict]:
    cfg: dict[str, dict] = {}
    for f in ("F1", "F2"):
        cfg[f"FULL_{f}"] = dict(form=f, parent=True, group="G_REF")
        cfg[f"ORIG_{f}"] = dict(
            form=f, method="orig", capital=1e6, long_fractional=False, group="G_REF"
        )
        cfg[f"I2_{f}"] = dict(
            form=f,
            method="R1",
            k=None,
            capital=1e6,
            long_fractional=False,
            min_notional_whole=100.0,
            rehedge=False,
            group="G_REF",
        )
    for f in ("F1", "F2"):
        for k in (50, 100, 200, 300, None):
            cfg[f"{f}_R1_K{'all' if k is None else k}"] = dict(
                form=f, method="R1", k=k, capital=50000.0, group="G_CAND", family="cand"
            )
        for k in (100, 200):
            cfg[f"{f}_R1B_K{k}"] = dict(
                form=f, method="R1B", k=k, capital=50000.0, group="G_CAND", family="cand"
            )
        cfg[f"{f}_R3"] = dict(
            form=f, method="R3", k=None, capital=50000.0, group="G_CAND", family="cand"
        )
        for c in (25000, 100000):
            for k in (50, 100, 200, 300, None):
                cfg[f"{f}_R1_K{'all' if k is None else k}_C{c}"] = dict(
                    form=f, method="R1", k=k, capital=float(c), group="G_TIER", family="tier"
                )
        for s in range(20):
            cfg[f"{f}_PRAND_K200_s{s}"] = dict(
                form=f,
                method="PRAND",
                k=200,
                seed=s,
                capital=50000.0,
                group="G_PLAC",
                family="placebo",
            )
    return cfg


def resolve_configs(arg: str | None, table: dict[str, dict]) -> list[str]:
    if not arg:
        return list(table)
    out: list[str] = []
    for tok in arg.split(","):
        tok = tok.strip()
        if tok.startswith("G_"):
            out += [c for c, v in table.items() if v["group"] == tok]
        elif tok in table:
            out.append(tok)
        else:
            raise SystemExit(f"unknown config {tok}")
    return list(dict.fromkeys(out))


def beta_dense(di: acc.DecisionInputs, symbols: pd.Index) -> np.ndarray:
    from open_composer.research.equity_book.book_v12 import target_weights

    return dense_beta(di.beta, target_weights(di.score, di.ind).index, symbols)


def run_pass(
    config_ids: list[str], limit: int | None, timing: bool, force: bool
) -> dict[str, pd.DataFrame]:
    table = config_table()
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    todo = [
        c
        for c in config_ids
        if force or limit is not None or not (OUT_DATA / f"{c}.parquet").exists()
    ]
    if not todo:
        print("all configs exist, nothing to do", flush=True)
        return {}
    ctx = T25.Context()
    px = ctx.px
    flag = acc.variant_flag(VARIANT)
    sources = [acc.make_source(ctx, VARIANT) for _ in acc.OFFSETS]
    etf = acc.etf_series(px)
    last_valid, delist_flagged = bv.delist_flags(px.C)
    cf = np.nan_to_num(pd.DataFrame(px.C).ffill().to_numpy(), nan=0.0)
    sims: dict[str, acc.AccountSim] = {}
    for c in todo:
        s = dict(table[c])
        form = s.pop("form")
        s.pop("group", None)
        s.pop("family", None)
        if s.pop("parent", False):
            sims[c] = acc.AccountSim(form, ctx, etf, cf)
        else:
            sims[c] = SmallSim(form, ctx, etf, cf, **s)
    first = int(px.dates.searchsorted(pd.Timestamp(acc.START)))
    last_label = px.T - 3
    cal = px.dates
    n_done = 0
    t_di = t_sim = 0.0
    t0 = time.time()
    for p in range(first, last_label + 1):
        if limit is not None and n_done >= limit:
            break
        o = p % T25.WEEK
        ta = time.time()
        di = acc.decision_inputs(ctx, sources[o], flag, p)
        if di is None:
            continue
        tt = acc.tranche_from_inputs(ctx, di)
        beta = beta_dense(di, px.symbols)
        p_ref = px.C[p]
        spy_ref = float(px.spy_c[p])
        cdays = int((cal[p + 2] - cal[p + 1]).days)
        tb = time.time()
        for sim in sims.values():
            if isinstance(sim, SmallSim):
                sim.refresh(o, tt, p_ref, spy_ref, beta)
            else:
                sim.refresh(o, tt, p_ref, spy_ref)
            sim.step(p, di.attrs, p_ref, last_valid, delist_flagged, cdays)
            if not isinstance(sim, SmallSim):
                sim.part_notional.clear()
                sim.part_adv.clear()
        t_di += tb - ta
        t_sim += time.time() - tb
        n_done += 1
        if timing or n_done % 100 == 0:
            print(
                f"session {n_done} p={p} decision_inputs {t_di / n_done:.2f}s/sess sims {t_sim / n_done:.2f}s/sess total {(time.time() - t0) / n_done:.2f}s/sess configs={len(sims)}",
                flush=True,
            )
    frames = {c: sim.frame() for c, sim in sims.items()}
    if limit is None:
        for c, df in frames.items():
            df.to_parquet(OUT_DATA / f"{c}.parquet")
    n = max(n_done, 1)
    print(
        f"done sessions={n_done} configs={len(sims)} decision_inputs {t_di / n:.3f}s/sess sims {t_sim / n:.3f}s/sess total {(time.time() - t0) / n:.3f}s/sess; extrapolated 2240 sessions: {(time.time() - t0) / n * 2240 / 3600:.2f} h",
        flush=True,
    )
    return frames


# ---------------------------------------------------------------------------
# identity (I1, I2, I3)
# ---------------------------------------------------------------------------
NUM_COLS = list(acc.DAILY_COLS) + [
    "cost_overlay",
    "cost_bil",
    "cash",
    "short_mv_stock",
    "bil_ret",
    "spy_ret",
]


def max_col_diff(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, float]:
    if not a.index.equals(b.index):
        return {c: float("nan") for c in NUM_COLS}
    return {
        c: float((a[c].astype(float) - b[c].astype(float)).abs().max())
        for c in NUM_COLS
        if c in a and c in b
    }


def score_series(df: pd.DataFrame, form: str, capital: float) -> tuple[pd.Series, pd.Series]:
    r = df["net_pnl"] / capital
    bench = df["bil_ret"] if form == "F1" else df["spy_ret"]
    return r, bench


def window_stats(df: pd.DataFrame, form: str, capital: float, window: str) -> dict:
    from scripts import book_v12_score as sco

    r, bench = score_series(df, form, capital)
    if window != "full":
        a, b = WIN[window]
        r, bench = sco.win(r, a, b), sco.win(bench, a, b)
    return sco.stats(r, r - bench)


def run_identity(limit: int | None) -> dict:
    frames = run_pass(
        ["FULL_F1", "FULL_F2", "ORIG_F1", "ORIG_F2", "I2_F1", "I2_F2"], limit, False, True
    )
    out: dict = {"tolerance": IDENTITY_TOL, "limit_sessions": limit, "I1": {}, "I2": {}, "I3": {}}
    ok1 = ok2 = True
    for f in ("F1", "F2"):
        d1 = max_col_diff(frames[f"FULL_{f}"], frames[f"ORIG_{f}"])
        d2 = max_col_diff(frames[f"ORIG_{f}"], frames[f"I2_{f}"])
        w1, w2 = max(d1.values()), max(d2.values())
        out["I1"][f] = {
            "max_abs_diff_by_column": d1,
            "worst": w1,
            "pass": bool(math.isfinite(w1) and w1 <= IDENTITY_TOL),
        }
        out["I2"][f] = {
            "max_abs_diff_by_column": d2,
            "worst": w2,
            "pass": bool(math.isfinite(w2) and w2 <= IDENTITY_TOL),
        }
        ok1 &= out["I1"][f]["pass"]
        ok2 &= out["I2"][f]["pass"]
    summ = json.loads(
        (ROOT / "reports/research/iterations/t20261002_book_v12/account-summary.json").read_text()
    )
    ok3 = True
    for f in ("F1", "F2"):
        d = pd.read_parquet(A1_DIR / f"A1_{VARIANT}_{f}.parquet")
        got = window_stats(d, f, bv.EQUITY, "recent")["sharpe_excess"]
        ref = summ["variants"][VARIANT][f]["windows"]["recent"]["sharpe_excess"]
        out["I3"][f] = {
            "computed": got,
            "account_summary": ref,
            "abs_diff": abs(got - ref),
            "pass": bool(abs(got - ref) <= 1e-9),
        }
        ok3 &= out["I3"][f]["pass"]
    out["I1_pass"], out["I2_pass"], out["I3_pass"] = bool(ok1), bool(ok2), bool(ok3)
    out["pass"] = bool(ok1 and ok2 and ok3)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)
    (OUT_REPORT / "identity.json").write_text(json.dumps(out, indent=1, default=float))
    return out


# ---------------------------------------------------------------------------
# evaluation (stage evaluate)
# ---------------------------------------------------------------------------
K_ORDER = (50, 100, 200, 300, None)
K_RANK = {50: 0, 100: 1, 200: 2, 300: 3, None: 4}


def stationary_bootstrap_diff(
    a: np.ndarray, b: np.ndarray, *, draws: int = 2000, mean_block: int = 10, seed: int = 20261006
) -> dict:
    """90% interval of Sharpe(a) - Sharpe(b), paired Politis-Romano bootstrap (annualized)."""
    n = len(a)
    rng = np.random.default_rng(seed)
    pr = 1.0 / mean_block
    idx = np.empty((draws, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, draws)
    new = rng.random((draws, n)) < pr
    start = rng.integers(0, n, (draws, n))
    for j in range(1, n):
        idx[:, j] = np.where(new[:, j], start[:, j], (idx[:, j - 1] + 1) % n)
    sa, sb = a[idx], b[idx]
    sh = lambda x: x.mean(axis=1) / x.std(axis=1, ddof=1) * math.sqrt(252)  # noqa: E731
    d = sh(sa) - sh(sb)
    return {
        "lo90": float(np.quantile(d, 0.05)),
        "hi90": float(np.quantile(d, 0.95)),
        "draws": draws,
    }


def te_ratio(e: pd.Series, e_f: pd.Series) -> float:
    j = e.index.intersection(e_f.index)
    e, e_f = e.loc[j], e_f.loc[j]
    sd, sd_f = float(e.std(ddof=1)), float(e_f.std(ddof=1))
    return float((e * sd_f / sd - e_f).std(ddof=1) * math.sqrt(252) / (sd_f * math.sqrt(252)))


def v2_block(d: pd.DataFrame) -> dict:
    rec = d.loc[WIN["recent"][0] : WIN["recent"][1]]
    ok = (
        (rec["short_gross_ratio"] >= V2["short_gross_ratio_min"])
        & (rec["rel_l1"] <= V2["rel_l1_max"])
        & (rec["net_dollar_err"].abs() <= V2["net_dollar_abs_max"])
        & ~(rec["adv_frac_max"] > V2["adv_frac_max"])
    )
    means = {
        "short_gross_ratio": float(rec["short_gross_ratio"].mean()),
        "rel_l1": float(rec["rel_l1"].mean()),
        "net_dollar_abs": float(rec["net_dollar_err"].abs().mean()),
        "net_dollar_err": float(rec["net_dollar_err"].mean()),
        "adv_frac_max": float(rec["adv_frac_max"].mean()),
    }
    means_ok = (
        means["short_gross_ratio"] >= V2["short_gross_ratio_min"]
        and means["rel_l1"] <= V2["rel_l1_max"]
        and means["net_dollar_abs"] <= V2["net_dollar_abs_max"]
        and means["adv_frac_max"] <= V2["adv_frac_max"]
    )
    share = float(ok.mean())
    return {
        "share_sessions_pass": share,
        "means": means,
        "means_within": bool(means_ok),
        "v2_pass": bool(share >= 0.90 and means_ok),
    }


def config_metrics(d: pd.DataFrame, form: str, capital: float, full: pd.DataFrame | None) -> dict:
    from scripts import book_v12_score as sco

    out: dict = {"windows": {}}
    r, bench = score_series(d, form, capital)
    for w in ("recent", "stress", "full"):
        st = window_stats(d, form, capital, w)
        out["windows"][w] = {
            "n": st.get("n"),
            "ann_return": st.get("ann_return"),
            "ann_vol": st.get("ann_vol"),
            "sharpe": st.get("sharpe_excess"),
            "max_dd": st.get("max_dd"),
        }
    rec = d.loc[WIN["recent"][0] : WIN["recent"][1]]
    years = len(rec) / 252.0
    r2 = (d["net_pnl"] - d["cost"]) / capital
    r_b25 = (d["net_pnl"] - d["short_mv_stock"] * 25.0 / 1e4 / 252.0) / capital
    rw, bw = sco.win(r, *WIN["recent"]), sco.win(bench, *WIN["recent"])
    out["implementation"] = {
        "names_long_mean_recent": float(rec["n_long"].mean()),
        "names_short_mean_recent": float(rec["n_short"].mean()),
        "orders_per_day_mean_recent": float(rec["n_orders"].mean()),
        "orders_per_day_p95_recent": float(rec["n_orders"].quantile(0.95)),
        "annual_turnover_recent": float(rec["turnover_value"].sum() / capital / years),
        "cost_bp_per_year_recent": float(rec["cost"].sum() / capital / years * 1e4),
        "ann_excess_recent_2x_cost": float((sco.win(r2, *WIN["recent"]) - bw).mean() * 252),
        "ann_excess_recent_1x_cost": float((rw - bw).mean() * 252),
        "sharpe_recent_borrow_25bp": float(
            sco.stats(sco.win(r_b25, *WIN["recent"]), sco.win(r_b25, *WIN["recent"]) - bw)[
                "sharpe_excess"
            ]
        ),
        "min_init_excess_frac_all": float(d["init_excess"].min() / capital),
        "min_maint_excess_frac_all": float(d["maint_excess"].min() / capital),
        "min_init_excess_frac_recent": float(rec["init_excess"].min() / capital),
        "min_maint_excess_frac_recent": float(rec["maint_excess"].min() / capital),
        "max_gross_frac_all": float(d["gross"].max() / capital),
        "margin_violation_sessions_all": int(
            ((d["init_excess"] < 0) | (d["maint_excess"] < 0)).sum()
        ),
    }
    out["v2"] = v2_block(d)
    if full is not None:
        rf, bf = score_series(full, form, bv.EQUITY)
        e, e_f = r - bench, rf - bf
        out["te_ratio"] = {
            "full": te_ratio(e, e_f),
            "recent": te_ratio(sco.win(e, *WIN["recent"]), sco.win(e_f, *WIN["recent"])),
        }
        out["retention"] = {
            w: (
                out["windows"][w]["sharpe"] / fw
                if (fw := window_stats(full, form, bv.EQUITY, w).get("sharpe_excess"))
                else None
            )
            for w in ("recent", "stress", "full")
        }
        j = sco.win(e, *WIN["recent"]).index.intersection(sco.win(e_f, *WIN["recent"]).index)
        out["sharpe_diff_vs_full_recent_bootstrap"] = stationary_bootstrap_diff(
            e.loc[j].to_numpy(), e_f.loc[j].to_numpy()
        )
    return out


def percentile_among(x: float, ref: list[float]) -> float:
    ref_a = np.asarray(ref)
    return float(((ref_a < x).sum() + 0.5 * (ref_a == x).sum()) / len(ref_a))


def decide_form(form: str, res: dict, capital_tiers=(25000.0, 50000.0, 100000.0)) -> dict:
    """Contract section 9 for one form; every intermediate is written out."""

    def cid(method: str, k, cap: float) -> str:
        ks = "all" if k is None else str(k)
        if cap == 50000.0:
            return f"{form}_R3" if method == "R3" else f"{form}_{method}_K{ks}"
        return f"{form}_R1_K{ks}_C{int(cap)}"

    def sharpe(c: str, w: str = "recent") -> float:
        return res["configs"][c]["windows"][w]["sharpe"]

    tiers: dict = {}
    for cap in capital_tiers:
        t: dict = {"capital": cap, "v2_by_k": {}}
        feasible = []
        for k in K_ORDER:
            c = cid("R1", k, cap)
            if c in res["configs"]:
                ok = res["configs"][c]["v2"]["v2_pass"]
                t["v2_by_k"]["all" if k is None else str(k)] = ok
                if ok:
                    feasible.append(k)
        if not feasible:
            t["K_star"] = None
            t["status"] = "infeasible"
            tiers[str(int(cap))] = t
            continue
        kstar = max(feasible, key=lambda k: K_RANK[k])
        t["K_star"] = "all" if kstar is None else kstar
        x = cid("R1", kstar, cap)
        t["R1B_vs_R1"] = None
        if cap == 50000.0 and kstar in (100, 200):
            b = cid("R1B", kstar, cap)
            t["R1B_vs_R1"] = {"R1B_sharpe_recent": sharpe(b), "R1_sharpe_recent": sharpe(x)}
            if sharpe(b) >= sharpe(x):
                x = b
        t["X"] = x
        deploy = None
        if cap == 50000.0:
            r3 = cid("R3", None, cap)
            ret3 = res["configs"][r3]["retention"]["recent"]
            gap = sharpe(x) - sharpe(r3)
            t["R3_rule"] = {
                "R3_retention_recent": ret3,
                "X_minus_R3_sharpe_recent": gap,
                "X_stress_sharpe": sharpe(x, "stress"),
                "R3_stress_sharpe": sharpe(r3, "stress"),
                "R3_v2_pass_info": res["configs"][r3]["v2"]["v2_pass"],
            }
            if ret3 >= 0.80 and (gap < 0.10 or sharpe(x, "stress") <= sharpe(r3, "stress")):
                deploy = r3
        if deploy is None and res["configs"][x]["retention"]["recent"] >= 0.80:
            deploy = x
        t["deploy"] = deploy
        if deploy is None:
            t["status"] = "not_deployable"
            tiers[str(int(cap))] = t
            continue
        m = res["configs"][deploy]
        c1 = m["retention"]["recent"] >= 0.80
        c2 = m["te_ratio"]["full"] <= 0.25
        c3 = m["retention"]["stress"] >= 0.60
        c4 = m["implementation"]["ann_excess_recent_2x_cost"] > 0
        t["class_inputs"] = {
            "retention_recent": m["retention"]["recent"],
            "te_ratio_full": m["te_ratio"]["full"],
            "retention_stress": m["retention"]["stress"],
            "ann_excess_recent_2x_cost": m["implementation"]["ann_excess_recent_2x_cost"],
        }
        if c1 and c2 and c3 and c4:
            t["status"] = "same_strategy"
        elif c1 and c4:
            dsr_v = res["dsr_family"]["dsr"].get(deploy)
            placebo_pct = None
            need_placebo = "_R1" in deploy
            if need_placebo:
                pl = res["placebo"][form]["recent_sharpes"]
                placebo_pct = percentile_among(sharpe(deploy), pl)
            ok_dsr = dsr_v is not None and dsr_v >= 0.70
            ok_pl = (not need_placebo) or (placebo_pct is not None and placebo_pct >= 0.80)
            t["related_inputs"] = {"dsr": dsr_v, "placebo_percentile_of_deploy": placebo_pct}
            t["status"] = "related_pending_stage_b" if (ok_dsr and ok_pl) else "not_deployable"
        else:
            t["status"] = "not_deployable"
        tiers[str(int(cap))] = t
    first = next(
        (
            int(cap)
            for cap in capital_tiers
            if tiers[str(int(cap))]["status"] in ("same_strategy", "related_pending_stage_b")
        ),
        None,
    )
    t50 = tiers["50000"]["status"]
    status = {
        "same_strategy": "deployable_same",
        "related_pending_stage_b": "deployable_related_pending_stage_b",
    }.get(t50, "not_deployable_at_50k")
    return {"mechanical_status": status, "min_capital_tier": first, "tiers": tiers}


def evaluate_partial(table: dict[str, dict]) -> None:
    """Per-config metrics of the parquets that exist (no decision); writes results.partial.json."""
    have = [c for c in table if (OUT_DATA / f"{c}.parquet").exists()]
    data = {c: pd.read_parquet(OUT_DATA / f"{c}.parquet") for c in have}
    res: dict = {
        "have": have,
        "missing": [c for c in table if c not in have],
        "configs": {},
        "identity_full": {},
    }
    for f in ("F1", "F2"):
        if all(f"{x}_{f}" in data for x in ("FULL", "ORIG", "I2")):
            res["identity_full"][f] = {
                "I1_worst": max(max_col_diff(data[f"FULL_{f}"], data[f"ORIG_{f}"]).values()),
                "I2_worst": max(max_col_diff(data[f"ORIG_{f}"], data[f"I2_{f}"]).values()),
            }
    for c in have:
        spec = table[c]
        f = spec["form"]
        is_ref = c.startswith(("FULL_", "ORIG_", "I2_"))
        full = None if is_ref or f"FULL_{f}" not in data else data[f"FULL_{f}"]
        m = config_metrics(data[c], f, bv.EQUITY if is_ref else spec["capital"], full)
        m["spec"] = {k: v for k, v in spec.items() if k != "parent"}
        res["configs"][c] = m
    (OUT_REPORT / "results.partial.json").write_text(json.dumps(res, indent=1, default=float))
    print("partial results for", len(have), "configs; missing", len(res["missing"]), flush=True)


def evaluate(partial: bool = False) -> None:
    from open_composer.research import scorecard_v2 as sc

    table = config_table()
    missing = [c for c in table if not (OUT_DATA / f"{c}.parquet").exists()]
    if missing and partial:
        return evaluate_partial(table)
    if missing:
        raise SystemExit(f"missing config parquets: {missing}")
    data = {c: pd.read_parquet(OUT_DATA / f"{c}.parquet") for c in table}
    ident = json.loads((OUT_REPORT / "identity.json").read_text())
    full_ident: dict = {"I1": {}, "I2": {}}
    for f in ("F1", "F2"):
        full_ident["I1"][f] = max(max_col_diff(data[f"FULL_{f}"], data[f"ORIG_{f}"]).values())
        full_ident["I2"][f] = max(max_col_diff(data[f"ORIG_{f}"], data[f"I2_{f}"]).values())
    id_ok = (
        ident["pass"]
        and all(v <= IDENTITY_TOL for v in full_ident["I1"].values())
        and all(v <= IDENTITY_TOL for v in full_ident["I2"].values())
    )
    full_ident["pass"] = bool(id_ok)
    (OUT_REPORT / "identity-full.json").write_text(
        json.dumps({"quick": ident["pass"], **full_ident}, indent=1, default=float)
    )
    drift: dict = {}
    for f in ("F1", "F2"):
        a1d = pd.read_parquet(A1_DIR / f"A1_{VARIANT}_{f}.parquet")
        fr = data[f"FULL_{f}"]
        j = fr.index.intersection(a1d.index)
        cols = [c for c in NUM_COLS if c in fr and c in a1d]
        drift[f] = {
            "max_abs_diff_by_column": {
                c: float((fr.loc[j, c] - a1d.loc[j, c]).abs().max()) for c in cols
            },
            "rows_fresh": len(fr),
            "rows_a1": len(a1d),
            "sharpe_recent_fresh": window_stats(fr, f, bv.EQUITY, "recent")["sharpe_excess"],
            "sharpe_recent_a1": window_stats(a1d, f, bv.EQUITY, "recent")["sharpe_excess"],
            "sharpe_full_fresh": window_stats(fr, f, bv.EQUITY, "full")["sharpe_excess"],
            "sharpe_full_a1": window_stats(a1d, f, bv.EQUITY, "full")["sharpe_excess"],
        }
    res: dict = {
        "identity": {"quick": ident, "full": full_ident},
        "full_vs_a1_drift": drift,
        "configs": {},
    }
    for c, spec in table.items():
        f = spec["form"]
        if c.startswith(("FULL_", "ORIG_", "I2_")):
            cap = bv.EQUITY
        else:
            cap = spec["capital"]
        m = config_metrics(
            data[c],
            f,
            cap,
            data[f"FULL_{f}"] if not c.startswith(("FULL_", "ORIG_", "I2_")) else None,
        )
        m["spec"] = {k: v for k, v in spec.items() if k not in ("parent",)}
        res["configs"][c] = m
    res["placebo"] = {}
    for f in ("F1", "F2"):
        sh = [
            res["configs"][f"{f}_PRAND_K200_s{s}"]["windows"]["recent"]["sharpe"] for s in range(20)
        ]
        r1 = res["configs"][f"{f}_R1_K200"]["windows"]["recent"]["sharpe"]
        res["placebo"][f] = {
            "recent_sharpes": sh,
            "R1_K200_recent_sharpe": r1,
            "R1_K200_percentile": percentile_among(r1, sh),
            "placebo_mean": float(np.mean(sh)),
            "placebo_max": float(np.max(sh)),
        }
    fam = [c for c, v in table.items() if v.get("family") in ("cand", "tier")]
    ex = {}
    for c in fam:
        f, cap = table[c]["form"], table[c]["capital"]
        r, b = score_series(data[c], f, cap)
        e = r - b
        ex[c] = e.loc[WIN["recent"][0] : WIN["recent"][1]]
    ex_df = pd.DataFrame(ex).dropna()
    cm = ex_df.corr().to_numpy()
    n = len(fam)
    mean_corr = float((cm.sum() - n) / (n * (n - 1)))
    sr = np.array([ex_df[c].mean() / ex_df[c].std(ddof=1) * math.sqrt(252) for c in fam])
    var_sr = float(sr.var(ddof=1))
    n_eff = sc.n_eff_from_corr(n, mean_corr)
    res["dsr_family"] = {
        "n_series": n,
        "mean_pairwise_corr": mean_corr,
        "var_sr_annual": var_sr,
        "n_eff": n_eff,
        "expected_max_null": sc.expected_max_null(var_sr, n_eff),
        "dsr": {
            c: float(sc.dsr(ex_df[c].to_numpy(), var_sr_annual=var_sr, n_eff=n_eff)["dsr"])
            for c in fam
        },
    }
    res["decision"] = {f: decide_form(f, res) for f in ("F1", "F2")}
    if not id_ok:
        for f in ("F1", "F2"):
            res["decision"][f]["mechanical_status_if_identity_ok"] = res["decision"][f][
                "mechanical_status"
            ]
            res["decision"][f]["mechanical_status"] = "identity_failed"
    (OUT_REPORT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    ledger = [
        {
            "series_id": c,
            "family": table[c]["family"],
            "form": table[c]["form"],
            "method": table[c]["method"],
            "k": table[c].get("k"),
            "capital": table[c]["capital"],
            "hurdle": HURDLE if table[c]["method"] == "R1B" else None,
        }
        for c in fam
    ]
    (OUT_REPORT / "trial-ledger.json").write_text(
        json.dumps({"n_series": len(ledger), "series": ledger}, indent=1, default=float)
    )
    write_report(res)


def write_report(res: dict) -> None:
    L = ["# v1.2 small-capital Stage A (T-20261005-37)\n", "数字全部来自 results.json。\n"]
    L.append(f"identity 全长通过: {res['identity']['full']['pass']}\n")
    for f in ("F1", "F2"):
        d = res["decision"][f]
        L.append(f"\n## {f}: {d['mechanical_status']}，最低资金档 {d['min_capital_tier']}\n")
        for cap, t in d["tiers"].items():
            L.append(f"- ${cap}: K*={t.get('K_star')}，部署={t.get('deploy')}，状态={t['status']}")
    L.append("\n## 候选（$50,000，近期）\n")
    L.append(
        "| config | sharpe | retention | te_full | stress_ret | V2 share | V2 pass | orders/d | 2x-cost excess |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c, m in res["configs"].items():
        if m["spec"].get("family") == "cand":
            L.append(
                f"| {c} | {m['windows']['recent']['sharpe']:.3f} | {m['retention']['recent']:.3f} | {m['te_ratio']['full']:.3f} | {m['retention']['stress']:.3f} | {m['v2']['share_sessions_pass']:.3f} | {m['v2']['v2_pass']} | {m['implementation']['orders_per_day_mean_recent']:.1f} | {m['implementation']['ann_excess_recent_2x_cost']:.4f} |"
            )
    L.append("\n## 安慰剂和 DSR\n")
    for f in ("F1", "F2"):
        p = res["placebo"][f]
        L.append(
            f"- {f}: R1 K200 近期夏普 {p['R1_K200_recent_sharpe']:.3f}，分位 {p['R1_K200_percentile']:.2f}，安慰剂均值 {p['placebo_mean']:.3f}"
        )
    fam = res["dsr_family"]
    L.append(
        f"- DSR 族: n={fam['n_series']}，平均相关 {fam['mean_pairwise_corr']:.3f}，n_eff {fam['n_eff']:.2f}，var_sr {fam['var_sr_annual']:.4f}"
    )
    (OUT_REPORT / "report.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["identity", "run", "evaluate"], required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--configs",
        default=None,
        help="comma list of config ids or groups G_REF,G_CAND,G_TIER,G_PLAC",
    )
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--partial",
        action="store_true",
        help="evaluate: per-config metrics of existing parquets only",
    )
    a = ap.parse_args()
    if a.stage == "identity":
        res = run_identity(a.limit)
        print(json.dumps({k: res[k] for k in ("I1_pass", "I2_pass", "I3_pass", "pass")}))
        if not res["pass"]:
            sys.exit(3)
        return
    if a.stage == "run":
        ids = resolve_configs(a.configs, config_table())
        run_pass(ids, a.limit, a.timing, a.force)
        return
    evaluate(a.partial)


if __name__ == "__main__":
    main()
