# ruff: noqa: E501
"""T-20261007-06 engines for G1 (stock noise band), G2 (end-of-day reversal) and G3 (ETF gap fill).

Conventions as in T-15 (hypotheses.md section 0): signal on the close of bar t, fill at the open of bar t+1,
flat at the close of the session (15:59 bar; the 5-minute G2 panel exits at the 15:55 close).
Every engine returns raw pieces so that net(m) = gross - (m * spread_part + fixed_part).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t0706_costs as C  # noqa: E402
import t0706_grid as G  # noqa: E402
import t15_engine as E  # noqa: E402

DATA_END = str(G.DATA_END.date())
SEEDS = 100


# ----------------------------------------------------------------------------- shared helpers
def master_index() -> pd.DatetimeIndex:
    d = pd.read_parquet(ROOT / "data/features/t15_minute/SPY.parquet", columns=["date"])[
        "date"
    ].unique()
    d = pd.DatetimeIndex(sorted(d))
    return d[(d >= pd.Timestamp("2016-01-04")) & (d <= G.DATA_END)]


def put(
    master: pd.DatetimeIndex, dates: pd.DatetimeIndex, x: np.ndarray, fill=np.nan
) -> np.ndarray:
    out = np.full((len(master),) + x.shape[1:], fill, dtype=float)
    idx = master.get_indexer(dates)
    ok = idx >= 0
    out[idx[ok]] = x[ok]
    return out


def sec_fee() -> float:
    return C.SEC_FEE_BP


# ----------------------------------------------------------------------------- G3
def g3_pieces(
    p: E.Panel, cm: C.CostModel, pct: float, entry: int, exit_: int, phase: int = 0
) -> dict:
    """One ETF: per-day gross return of a gap-fade round trip, spread part, fixed part, trigger, move r."""
    gap = p.day_open / p.prev_close - 1.0
    a = np.abs(gap)
    thr = pd.Series(a).rolling(250, min_periods=120).quantile(pct).shift(1).to_numpy()
    es, xs = entry + phase, exit_ + phase
    oe, ox = p.o[:, es], p.o[:, xs]
    r = ox / oe - 1.0
    trig = np.isfinite(gap) & np.isfinite(thr) & (a >= thr) & np.isfinite(r) & (p.first_slot == 0)
    snap_in = "0935" if entry == 5 else "0945"
    hs_in = cm.hs(p.symbol, snap_in, "etf")
    hs_out = cm.hs(p.symbol, "0945", "etf")
    sp = np.where(trig, (hs_in + hs_out) / 1e4, 0.0)
    fx = np.where(trig, (2 * C.ETF_SLIP_BP + C.SEC_FEE_BP) / 1e4, 0.0)
    return {"gap": gap, "r": np.where(trig, r, 0.0), "trig": trig, "sp": sp, "fx": fx}


def g3_series(
    panels: dict, master, cm, basket: list[str], pct, entry, exit_, phase=0, placebo_rng=None
) -> dict:
    n = len(basket)
    D = len(master)
    gross = np.zeros(D)
    sp = np.zeros(D)
    fx = np.zeros(D)
    trades = np.zeros(D)
    rmat = np.zeros((D, n))
    tmat = np.zeros((D, n), bool)
    for i, s in enumerate(basket):
        z = g3_pieces(panels[s], cm, pct, entry, exit_, phase)
        dr = -np.sign(z["gap"])
        g = np.where(z["trig"], dr * z["r"], 0.0)
        gross += put(master, panels[s].dates, g[:, None], 0.0)[:, 0] / n
        sp += put(master, panels[s].dates, z["sp"][:, None], 0.0)[:, 0] / n
        fx += put(master, panels[s].dates, z["fx"][:, None], 0.0)[:, 0] / n
        tt = put(master, panels[s].dates, z["trig"][:, None].astype(float), 0.0)[:, 0]
        trades += tt
        rmat[:, i] = put(master, panels[s].dates, z["r"][:, None], 0.0)[:, 0]
        tmat[:, i] = tt > 0
    out = {"gross": gross, "sp": sp, "fx": fx, "trades": trades, "n": n}
    if placebo_rng is not None:
        gp = np.zeros((SEEDS, D))
        for sd in range(SEEDS):
            sign = placebo_rng.choice([-1.0, 1.0], size=(D, n))
            gp[sd] = (np.where(tmat, sign * rmat, 0.0)).sum(axis=1) / n
        out["gross_placebo"] = gp
    return out


def net_of(piece: dict, m: float) -> np.ndarray:
    return piece["gross"] - (m * piece["sp"] + piece["fx"])


# ----------------------------------------------------------------------------- G2 (1-minute ETF14)
def etf_g2_arrays(p: E.Panel, phase: int = 0) -> dict:
    """Signals and the 15:30 -> 15:55 move for one ETF from 1-minute bars (slots: 09:30 = 0)."""
    s_end = 359 + phase  # close of the 15:29 bar = the 15:30 price
    c1500 = p.c[:, 329]
    c1530 = p.c[:, s_end]
    o_in = p.o[:, 360 + phase]
    c_out = p.c[:, 384 + phase]
    ok = (
        np.isfinite(o_in)
        & np.isfinite(c_out)
        & np.isfinite(c1530)
        & np.isfinite(p.prev_close)
        & (p.last_slot >= 389)
    )
    return {
        "pc_to_1500": c1500 / p.prev_close - 1.0,
        "pc_to_1530": c1530 / p.prev_close - 1.0,
        "open_to_1530": c1530 / p.day_open - 1.0,
        "r": c_out / o_in - 1.0,
        "ok": ok,
        "price": o_in * p.factor,
    }


def g2_leg_counts(n: int, grouping: str) -> int:
    frac = 0.10 if grouping in ("decile", "long_only") else 0.05
    return max(2, int(round(frac * n)))


def g2_day(
    sig: np.ndarray,
    r: np.ndarray,
    hs_sum: np.ndarray,
    valid: np.ndarray,
    grouping: str,
    perm_key: np.ndarray | None = None,
    slip_bp: float = C.STOCK_SLIP_BP,
):
    """One session: returns (gross, spread_part, fixed_part, n_trades). hs_sum[i] = (hs_in + hs_out) in bp.

    perm_key (placebo): random keys replacing the ranking, same order-statistic assignment."""
    idx = np.flatnonzero(valid)
    n = len(idx)
    if n < 6:
        return 0.0, 0.0, 0.0, 0
    k = g2_leg_counts(n, grouping)
    if 2 * k > n:
        return 0.0, 0.0, 0.0, 0
    score = sig[idx] if perm_key is None else perm_key[idx]
    order = np.argsort(score, kind="stable")
    longs = idx[order[:k]]
    shorts = idx[order[-k:]]
    if grouping == "long_only":
        w_l, w_s = 1.0 / k, 0.0
        shorts = shorts[:0]
    else:
        w_l, w_s = 0.5 / k, 0.5 / k
    gross = w_l * r[longs].sum() - w_s * (r[shorts].sum() if len(shorts) else 0.0)
    spart = (w_l * hs_sum[longs].sum() + w_s * (hs_sum[shorts].sum() if len(shorts) else 0.0)) / 1e4
    fixed = (w_l * len(longs) + w_s * len(shorts)) * (2 * slip_bp + C.SEC_FEE_BP) / 1e4
    return gross, spart, fixed, len(longs) + len(shorts)


# ----------------------------------------------------------------------------- G1
def g1_symbol_pieces(
    p: E.Panel, cm: C.CostModel, interval: int, mult: float, phase: int = 0, detail: bool = False
) -> dict:
    """One stock, one (interval, mult): per-day unlevered gross, spread part, fixed part, entries, lev."""
    sigma = E.noise_sigma(p, G.G1_FIXED["lookback"])
    paths = E.a_position_paths(p, sigma, interval, [mult], ["both"], phase=phase)
    P = paths[(mult, "both")]
    ms = E.check_slots(interval, phase)
    nd, nj = P.shape
    fills = p.o[:, ms + 1]
    last_close = p.day_close
    X = np.concatenate([fills, last_close[:, None]], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        seg = X[:, 1:] / X[:, :-1] - 1.0
    seg = np.where(np.isfinite(seg), seg, 0.0)
    gross = np.sum(P * seg, axis=1)
    prevP = np.concatenate([np.zeros((nd, 1)), P[:, :-1]], axis=1)
    dpos = np.abs(P - prevP)
    fill_slot = ms + 1
    snaps = np.where(fill_slot < 30, 0, np.where(fill_slot < 360, 1, 2))
    names = ["0945", "1200", "1545"]
    hs_j = np.array([cm.hs(p.symbol, names[s], "top20") for s in snaps])  # (nj,)
    hs_close = cm.hs(p.symbol, "1555", "top20")
    spart = (dpos * hs_j[None, :]).sum(axis=1) + np.abs(P[:, -1]) * hs_close
    sells = (P - prevP) < 0
    # fixed: slippage on every fill and the close-out, SEC fee on sells (reducing a long / opening a short) and on closing a long
    n_fills = dpos.sum(axis=1) + np.abs(P[:, -1])
    sell_notional = (np.where(sells, dpos, 0.0)).sum(axis=1) + np.where(
        P[:, -1] > 0, np.abs(P[:, -1]), 0.0
    )
    fixed = n_fills * C.STOCK_SLIP_BP + sell_notional * C.SEC_FEE_BP
    entries = np.sum((prevP == 0) & (P != 0), axis=1) + np.sum(
        (prevP != 0) & (P != 0) & (np.sign(P) != np.sign(prevP)), axis=1
    )
    ok = np.isfinite(last_close) & np.isfinite(p.day_open)
    out = {
        "gross": np.where(ok, gross, np.nan),
        "sp": spart / 1e4,
        "fx": fixed / 1e4,
        "entries": entries.astype(float),
        "lev": np.where(
            np.isfinite(p.sigma_ret14),
            np.minimum(G.G1_FIXED["vt_cap"], G.G1_FIXED["vt_target"] / p.sigma_ret14),
            1.0,
        ),
    }
    if detail:
        segg = np.abs(P) * seg
        start = (P != 0) & ((prevP == 0) | (np.sign(P) != np.sign(prevP)))
        tid = np.cumsum(start, axis=1) - 1
        out["absseg"] = segg
        out["tid"] = np.where(P != 0, tid, -1)
    return out


def load_stock_panel(symbol: str) -> E.Panel:
    d = pd.read_parquet(ROOT / "data/features/t0706_minute" / f"{symbol}.parquet")
    d = d[d["date"] <= G.DATA_END]
    return E.Panel(symbol, frame=d)


def slim(p: E.Panel, keep: tuple[str, ...]) -> E.Panel:
    """Drop the big minute matrices that a group does not need (box has 3.9 GB, cap 0.8 GB per job)."""
    for name in ("o", "h", "l", "c", "v", "vw"):
        if name not in keep:
            setattr(p, name, None)
        else:
            setattr(p, name, getattr(p, name).astype(np.float32))
    return p


def load_etf(symbol: str, keep: tuple[str, ...]) -> E.Panel:
    return slim(E.Panel(symbol, end=DATA_END), keep)
