# ruff: noqa: E501
"""Book v1.2 Stage A: identity (A0) and the account layer (A1) of t20261002_book_v12.

Contract: ``reports/research/iterations/t20261002_book_v12/hypotheses.md`` (frozen 05:31 UTC).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_account.py --stage identity
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v12_account.py --stage account

Daily series go to ``data/research/book_v12/`` (outside the hash-guarded research snapshot).
Label convention of T-25: the row of label date t earns the return from close(t+1) to close(t+2);
a decision at close(t) fills at close(t+1).  In label time the "execution price" of label t is
``Pf[t] = close[t+1]``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

OUT_DATA = ROOT / "data/research/book_v12"
OUT_REPORT = ROOT / "reports/research/iterations/t20261002_book_v12"
VARIANTS = T25.VARIANTS
OFFSETS = T25.OFFSETS
START = T25.START
IDENTITY_CASES = (("M0_U3000", 0), ("M1_P1000", 3))
IDENTITY_TOL = 1e-12
ETF_COST_SYMBOLS = ("SPY", "BIL")


# ---------------------------------------------------------------------------
# decision inputs (everything the pure rules need at one decision date)
# ---------------------------------------------------------------------------
@dataclass
class DecisionInputs:
    p: int
    t: pd.Timestamp
    score: pd.Series
    ind: pd.Series
    eligible: pd.Series
    fill_ok: np.ndarray
    beta: pd.Series
    vix: float
    attrs: pd.DataFrame


def decision_inputs(ctx: T25.Context, src, flag: str, p: int) -> DecisionInputs | None:
    """Static inputs of the T-25 R6 rule at decision position ``p`` (None: no theme row)."""
    from open_composer.research.equity_book.borrow import short_eligible

    px = ctx.px
    t = px.dates[p]
    th = ctx.themes.at(t)
    if th.empty:
        return None
    members = th.index[th[flag].to_numpy(bool)]
    state_obj = type("S", (), {"pos": p})()
    score = src(t, state_obj, members)
    ind = ctx.sig.at(t)["ind_code"]
    names = score.dropna().index
    idx = px.symbols.get_indexer(names)
    attrs = ctx.panel.at(t)
    a = attrs.reindex(names)
    se = short_eligible(
        pd.DataFrame(
            {
                "adv_rank": a["adv_rank"],
                "price": a["close"],
                "reverse_split_252": px.rs_recent(p)[idx.clip(min=0)] & (idx >= 0),
            },
            index=names,
        )
    )
    be, _ = ctx.ewma.at(t)
    return DecisionInputs(
        p=p,
        t=t,
        score=score,
        ind=ind,
        eligible=se,
        fill_ok=np.isfinite(px.C[p + 1]),
        beta=be,
        vix=float(px.vix[p]),
        attrs=attrs,
    )


def make_source(ctx: T25.Context, variant: str):
    from scripts.run_book_v1_stage2 import AlphaSource

    method, universe = variant.split("_")
    return AlphaSource(ctx.themes, ctx.fic, method, universe.lower())


def variant_flag(variant: str) -> str:
    return "in_u3000" if variant.split("_")[1].lower() == "u3000" else "in_p1000"


def tranche_from_inputs(ctx: T25.Context, di: DecisionInputs) -> bv.TrancheTarget:
    return bv.tranche_target(
        di.score, di.ind, di.eligible, ctx.px.symbols, di.fill_ok, di.beta, di.vix
    )


# ---------------------------------------------------------------------------
# strategy-level pass (A0): T-25 R6 through the module's rules
# ---------------------------------------------------------------------------
def strategy_pass(
    ctx: T25.Context, variant: str, offset: int, limit: int | None = None
) -> pd.DataFrame:
    px = ctx.px
    flag = variant_flag(variant)
    src = make_source(ctx, variant)
    first = int(px.dates.searchsorted(pd.Timestamp(START)))
    last_label = px.T - 3
    dec = T25.decision_positions(px.T, first, last_label, T25.WEEK, offset)
    w_state, h_state = np.zeros(px.N), 0.0
    rows: list[pd.DataFrame] = []
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        di = decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        tt = tranche_from_inputs(ctx, di)
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
                },
                index=px.dates[p : p + n],
            )
        )
        w_state, h_state = blk["w_end"], blk["h_end"]
    df = pd.concat(rows)
    df["net"] = df["gross"] - df["cost"] - df["borrow"]
    return df


def run_identity(limit: int | None = None) -> dict:
    ctx = T25.Context()
    out: dict = {"tolerance": IDENTITY_TOL, "cases": {}, "pass": True, "max_abs_diff": 0.0}
    for variant, o in IDENTITY_CASES:
        saved = pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet")
        mine = strategy_pass(ctx, variant, o, limit=limit)
        if limit is not None:
            saved = saved.loc[mine.index]
        diffs: dict[str, float] = {}
        for col in ("gross", "cost", "borrow", "net"):
            joined_index_equal = bool(mine.index.equals(saved.index))
            d = (mine[col] - saved[col]).abs().max() if joined_index_equal else float("nan")
            diffs[col] = float(d)
        extra = {
            c: float((mine[c] - saved[c]).abs().max())
            for c in ("turnover", "spy", "hedge_size", "vix_scale")
        }
        worst = max(diffs.values())
        ok = bool(math.isfinite(worst) and worst <= IDENTITY_TOL)
        out["cases"][f"{variant}_o{o}"] = {
            "rows_mine": len(mine),
            "rows_saved": len(saved),
            "index_equal": bool(mine.index.equals(saved.index)),
            "max_abs_diff": diffs,
            "max_abs_diff_other_columns": extra,
            "worst": worst,
            "pass": ok,
        }
        out["max_abs_diff"] = max(out["max_abs_diff"], worst if math.isfinite(worst) else 1e99)
        out["pass"] = out["pass"] and ok
        print(variant, o, "worst", worst, flush=True)
    out["limit"] = limit
    return out


# ---------------------------------------------------------------------------
# account layer (A1)
# ---------------------------------------------------------------------------
DAILY_COLS = (
    "stock_pnl",
    "spy_pnl",
    "tbill_pnl",
    "cost",
    "borrow",
    "interest",
    "delist_adj",
    "net_pnl",
    "equity",
    "long_mv",
    "short_mv",
    "gross",
    "init_excess",
    "maint_excess",
    "n_orders",
    "n_dropped",
    "rounding_drift",
    "scale_events",
)


class AccountSim:
    """One account form (F1 or F2) of one variant, stepped by the daily loop.

    Sizing basis is the fixed ``E = $1M``; the actual equity (``E + cumulative net P&L``) only
    enters the margin check and the cash balance.  Prices are carried forward (``Cf``) when a close
    is missing; a name flagged as delisted is written off once (-30% long, 0 short) and dropped."""

    def __init__(self, form: str, ctx: T25.Context, etf: dict[str, np.ndarray], cf: np.ndarray):
        self.form = form
        self.px = ctx.px
        self.ctx = ctx
        n = ctx.px.N
        self.virt = np.zeros((bv.N_TRANCHES, n))  # tranche virtual stock shares
        self.virt_h = np.zeros(bv.N_TRANCHES)  # tranche virtual SPY shares (overlay hedge)
        self.qty = np.zeros(n, dtype="int64")
        self.qty_spy = 0
        self.qty_bil = 0
        self.cum_net = 0.0
        self.dead = np.zeros(n, dtype=bool)
        self.etf = etf
        self.cf = cf
        self.rows: list[dict] = []
        self.part_notional: list[np.ndarray] = []
        self.part_adv: list[np.ndarray] = []

    def refresh(self, o: int, tt: bv.TrancheTarget, p_ref: np.ndarray, spy_ref: float) -> None:
        if self.form == "F1":
            k = bv.f1_k_eff(tt.vscale, tt.h_unit)
        else:
            k = bv.f2_k2_eff(tt.vscale, tt.h_unit)
        v = bv.virtual_shares(tt.w_unit, k, bv.EQUITY, p_ref)
        v[self.dead] = 0.0
        self.virt[o] = v
        self.virt_h[o] = tt.h_unit * k * (bv.EQUITY / bv.N_TRANCHES) / spy_ref

    def _targets(self, scale: float, p_ref: np.ndarray, spy_ref: float):
        virt_total = self.virt.sum(axis=0)
        tgt_spy = float(self.virt_h.sum()) * scale
        if self.form == "F2":
            tgt_spy += bv.F2_CORE * bv.EQUITY / spy_ref
        post_q, ord_q, drop = bv.aggregate_targets(virt_total, p_ref, self.qty, scale=scale)
        post_spy, ord_spy, drop_spy = bv.aggregate_targets(
            np.array([tgt_spy]), np.array([spy_ref]), np.array([self.qty_spy]), scale=1.0
        )
        val = post_q * np.where(np.isfinite(p_ref), p_ref, 0.0)
        spy_val = float(post_spy[0]) * spy_ref
        long_f = (val[val > 0].sum() + max(spy_val, 0.0)) / bv.EQUITY
        short_f = (-val[val < 0].sum() + max(-spy_val, 0.0)) / bv.EQUITY
        return virt_total, post_q, ord_q, drop, post_spy, ord_spy, drop_spy, val, long_f, short_f

    def step(
        self,
        p: int,
        attrs: pd.DataFrame,
        p_ref: np.ndarray,
        last_valid: np.ndarray,
        delist_flagged: np.ndarray,
        calendar_days: int,
    ) -> dict:
        """Trade at the execution close (close of D+1), earn to the next close."""
        px, ctx = self.px, self.ctx
        t = px.dates[p]
        spy_ref = float(px.spy_c[p])
        spy_now, spy_next = float(px.spy_c[p + 1]), float(px.spy_c[p + 2])
        bil_ref = float(self.etf["BIL_c"][p])
        bil_now, bil_next = float(self.etf["BIL_c"][p + 1]), float(self.etf["BIL_c"][p + 2])
        pf_now, pf_next = self.cf[p + 1], self.cf[p + 2]
        # --- stock + SPY targets (netted, whole shares, $100 drop); F1 gross cap on the day
        scale, scale_event = 1.0, 0
        res = self._targets(scale, p_ref, spy_ref)
        long_f, short_f = res[8], res[9]
        if self.form == "F1" and long_f + short_f > bv.G_CAP + 1e-12:
            scale = bv.gross_scale(long_f, short_f)
            scale_event = 1
            res = self._targets(scale, p_ref, spy_ref)
            long_f, short_f = res[8], res[9]
        virt_total, post_q, ord_q, drop, post_spy, ord_spy, drop_spy, val, _, _ = res
        # --- T-bill leg (F1): fraction of equity from the post-trade L and S at P_ref
        if self.form == "F1":
            x = bv.tbill_fraction(long_f, short_f)
            post_bil, ord_bil, drop_bil = bv.aggregate_targets(
                np.array([x * bv.EQUITY / bil_ref]),
                np.array([bil_ref]),
                np.array([self.qty_bil]),
                scale=1.0,
            )
        else:
            post_bil, ord_bil, drop_bil = np.array([self.qty_bil]), np.array([0]), np.array([False])
        # --- cost on the netted dollar trades (attributes at D, as T-25 real_cost)
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
        if len(nz):
            self.part_notional.append(np.abs(ord_q[nz] * p_ref[nz]))
            self.part_adv.append(adv[: len(nz)])
        cost_bil = cost_of(["BIL"], [float(ord_bil[0]) * bil_ref])[0] if ord_bil[0] != 0 else 0.0
        cost = cost_overlay + cost_bil
        n_orders = int((ord_q != 0).sum() + (ord_spy[0] != 0) + (ord_bil[0] != 0))
        n_dropped = int(drop.sum() + drop_spy.sum() + drop_bil.sum())
        # rounding drift (engine definition): half the summed |whole-share - virtual| value / E
        v_value = virt_total * scale * np.where(np.isfinite(p_ref), p_ref, 0.0)
        tgt_spy_val = (
            float(self.virt_h.sum()) * scale
            + (bv.F2_CORE * bv.EQUITY / spy_ref if self.form == "F2" else 0.0)
        ) * spy_ref
        drift = float(
            (np.abs(val - v_value).sum() + abs(float(post_spy[0]) * spy_ref - tgt_spy_val))
            / bv.EQUITY
            / 2.0
        )
        self.qty, self.qty_spy, self.qty_bil = post_q, int(post_spy[0]), int(post_bil[0])
        # --- positions marked at the execution close (last price carried forward)
        qf = self.qty.astype(float)
        long_mv = float(pf_now[self.qty > 0] @ qf[self.qty > 0])
        short_stock = float(-(pf_now[self.qty < 0] @ qf[self.qty < 0]))
        long_mv += max(self.qty_spy, 0) * spy_now + self.qty_bil * bil_now
        short_mv = short_stock + max(-self.qty_spy, 0) * spy_now
        # --- equity, cash, interest of the post-trade book
        eq_pre = bv.EQUITY + self.cum_net - cost
        cash = eq_pre - long_mv + short_mv
        interest = bv.debit_interest(cash, calendar_days)
        # --- margin at this close
        qty_all = np.concatenate([qf, [self.qty_spy, self.qty_bil]])
        pr_all = np.concatenate([pf_now, [spy_now, bil_now]])
        maint = bv.maintenance_requirement(qty_all, pr_all)
        init_req = bv.initial_margin_requirement(long_mv, short_mv)
        # --- earn over the period
        stock_pnl = float((pf_next - pf_now) @ qf)
        spy_pnl = self.qty_spy * (spy_next - spy_now)
        tbill_pnl = self.qty_bil * (bil_next - bil_now)
        # --- delisting: a flagged name whose last close is session p+1 ends this period
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
            equity=bv.EQUITY + self.cum_net,
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
        )
        self.rows.append(row | {"date": t})
        return row

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows).set_index("date")


def etf_series(px: T25.Prices) -> dict[str, np.ndarray]:
    etf = pd.read_parquet(T25.EB / "etf_daily.parquet", columns=["trade_date", "symbol", "close"])
    bil = etf[etf["symbol"] == "BIL"].set_index("trade_date")["close"].sort_index()
    return {"BIL_c": bil.reindex(px.dates).to_numpy("float64")}


def run_account(variant: str, limit: int | None = None) -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    f1p = OUT_DATA / f"A1_{variant}_F1.parquet"
    f2p = OUT_DATA / f"A1_{variant}_F2.parquet"
    if f1p.exists() and f2p.exists() and limit is None:
        print(variant, "exists, skip", flush=True)
        return
    ctx = T25.Context()
    px = ctx.px
    flag = variant_flag(variant)
    sources = [make_source(ctx, variant) for _ in OFFSETS]
    etf = etf_series(px)
    last_valid, delist_flagged = bv.delist_flags(px.C)
    cf = np.nan_to_num(pd.DataFrame(px.C).ffill().to_numpy(), nan=0.0)
    sims = {"F1": AccountSim("F1", ctx, etf, cf), "F2": AccountSim("F2", ctx, etf, cf)}
    first = int(px.dates.searchsorted(pd.Timestamp(START)))
    last_label = px.T - 3
    cal = px.dates
    n_done = 0
    for p in range(first, last_label + 1):
        if limit is not None and n_done >= limit:
            break
        o = p % T25.WEEK
        di = decision_inputs(ctx, sources[o], flag, p)
        if di is None:
            continue
        tt = tranche_from_inputs(ctx, di)
        p_ref = px.C[p]
        spy_ref = float(px.spy_c[p])
        cdays = int((cal[p + 2] - cal[p + 1]).days)
        for sim in sims.values():
            sim.refresh(o, tt, p_ref, spy_ref)
            sim.step(p, di.attrs, p_ref, last_valid, delist_flagged, cdays)
        n_done += 1
        if n_done % 200 == 0:
            print(variant, p, n_done, flush=True)
    for name, sim in sims.items():
        df = sim.frame()
        if limit is None:
            df.to_parquet(OUT_DATA / f"A1_{variant}_{name}.parquet")
            np.savez_compressed(
                OUT_DATA / f"A1_{variant}_{name}_participation.npz",
                notional=np.concatenate(sim.part_notional) if sim.part_notional else np.array([]),
                adv=np.concatenate(sim.part_adv) if sim.part_adv else np.array([]),
            )
        else:
            df.to_parquet(OUT_DATA / f"debug_{variant}_{name}.parquet")
            print(df.tail(2).T)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["identity", "account"], required=True)
    ap.add_argument("--variant", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.stage == "identity":
        res = run_identity(a.limit)
        if a.limit is None:
            OUT_REPORT.mkdir(parents=True, exist_ok=True)
            (OUT_REPORT / "identity.json").write_text(json.dumps(res, indent=1, default=float))
        print(json.dumps({k: res[k] for k in ("max_abs_diff", "pass")}))
        if not res["pass"]:
            sys.exit(3)
        return
    for v in [a.variant] if a.variant else list(VARIANTS):
        run_account(v, a.limit)


if __name__ == "__main__":
    main()
