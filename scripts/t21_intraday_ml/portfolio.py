"""T-20261006-21: portfolio construction, cost accounting and daily P&L for one variant.

``simulate(df, h, ...)``: df has one row per (symbol, d, t) with a score ``pred`` (bp for models, any scale
for baselines), the realised stock return ``ret`` over [open t+1, close t+m], the SPY return ``spy`` over the
same bars and the cost inputs ``px_prev, adv21, vol21, beta``.  Rows must already be restricted to the
variant's pool (pool_rank <= N).  Returns a per-day DataFrame of gross, cost components and turnover.

Rules (hypotheses.md section 5): long the top 10 %, short the bottom 10 % by ``pred`` at every rebalance
(t = 11 + offset + j*m), weight 1/n_side per name, optional spread filter |pred| > k * one-side cost,
SPY hedge of sum(w*beta), flat at the exit of the last period of the day.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from open_composer.research.equity_book.costs import (
    FEES_BP_PER_SIDE,
    IMPACT_Y,
    half_spread_bp,
    impact_bp,
    load_model,
)

T_MIN, T_MAX = 11, 76
SEC_FEE_BP = 0.2
ETF_HALF_SPREAD_BP = 1.0
MISSING_HALF_SPREAD_BP = 40.0
BORROW_BP_YEAR = 25.0
NOTIONAL_PER_NAME = 5000.0
MODEL = load_model()
DAILY_COLS = [
    "d",
    "gross",
    "spread",
    "impact",
    "fees",
    "borrow",
    "hedge",
    "turnover",
    "n_pos",
    "pos_gross_bp",
]


def _hs(df: pd.DataFrame, t_trade: np.ndarray) -> np.ndarray:
    """Half spread (bp): close snapshot for trades at or after 15:00 ET, mid snapshot before."""
    yr = df["d"].dt.year.to_numpy()
    args = (
        df["px_prev"].to_numpy("float64"),
        df["adv21"].to_numpy("float64"),
        df["vol21"].to_numpy("float64"),
        yr,
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        mid = half_spread_bp(*args, "mid", MODEL)
        close = half_spread_bp(*args, "close", MODEL)
    hs = np.where(570 + 5 * t_trade >= 900, close, mid)
    return np.where(np.isfinite(hs), hs, MISSING_HALF_SPREAD_BP)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=DAILY_COLS)


def simulate(
    df: pd.DataFrame,
    h: int,
    *,
    k: float = 0.0,
    cmult: float = 1.0,
    offset: int = 0,
    notional: float = NOTIONAL_PER_NAME,
    frac: float = 0.10,
    first_t: int = T_MIN,
) -> pd.DataFrame:
    m = h // 5
    ok = np.isfinite(df["pred"]) & np.isfinite(df["ret"]) & np.isfinite(df["spy"])
    df = df[ok]
    t = df["t"].to_numpy().astype(int)
    sel = (t >= first_t + offset) & (t + m <= T_MAX) & ((t - first_t - offset) % m == 0)
    df = df[sel].copy()
    if df.empty:
        return _empty()
    df["t"] = df["t"].astype(int)
    df["j"] = (df["t"] - first_t - offset) // m
    g = df.groupby(["d", "j"])["pred"]
    df["n"] = g.transform("size")
    df["rk"] = g.rank(method="first", ascending=False)
    df["nside"] = np.ceil(frac * df["n"]).astype(int).clip(lower=1)
    side = np.where(
        df["rk"] <= df["nside"], 1.0, np.where(df["rk"] > df["n"] - df["nside"], -1.0, 0.0)
    )
    df["side"] = side
    df = df[df["side"] != 0].copy()
    if df.empty:
        return _empty()
    df["t_trade"] = df["t"] + 1
    df["hs"] = _hs(df, df["t_trade"].to_numpy())
    if k > 0:
        imp0 = np.nan_to_num(
            impact_bp(
                np.full(len(df), notional),
                df["adv21"].to_numpy("float64"),
                df["vol21"].to_numpy("float64"),
                IMPACT_Y,
            )
        )
        # the k filter always uses the x1 one-side cost, so the cost tiers re-price the same trades
        c1 = df["hs"].to_numpy() + FEES_BP_PER_SIDE + imp0
        df = df[np.abs(df["pred"].to_numpy()) > k * c1].copy()
        if df.empty:
            return _empty()
    df["w"] = df["side"] / df["nside"]
    df["beta_i"] = df["beta"].where(np.isfinite(df["beta"]), 1.0)
    df["pnl"] = df["w"] * df["ret"]
    df["wb"] = df["w"] * df["beta_i"]
    per = (
        df.groupby(["d", "j"])
        .agg(pnl=("pnl", "sum"), H=("wb", "sum"), spy=("spy", "first"))
        .reset_index()
    )
    per["gross"] = per["pnl"] - per["H"] * per["spy"]
    # trades: selected rows at j plus ghost exits at j+1 (w = 0)
    cols = ["d", "symbol", "j", "w", "px_prev", "adv21", "vol21", "t_trade", "nside"]
    s1 = df[cols].copy()
    s1["symbol"] = s1["symbol"].astype(str)
    ghost = s1.copy()
    ghost["j"] += 1
    ghost["w"] = 0.0
    ghost["t_trade"] += m
    allr = pd.concat([s1, ghost], ignore_index=True)
    allr = allr.groupby(["d", "symbol", "j"], as_index=False).agg(
        w=("w", "sum"),
        px_prev=("px_prev", "first"),
        adv21=("adv21", "first"),
        vol21=("vol21", "first"),
        t_trade=("t_trade", "min"),
        nside=("nside", "max"),
    )
    allr = allr.sort_values(["d", "symbol", "j"])
    allr["w_prev"] = allr.groupby(["d", "symbol"])["w"].shift(1).fillna(0.0)
    allr["dw"] = allr["w"] - allr["w_prev"]
    allr["adw"] = allr["dw"].abs()
    allr = allr[allr["adw"] > 0].copy()
    hs_all = _hs(allr, allr["t_trade"].to_numpy())
    ntl = allr["adw"].to_numpy() * allr["nside"].to_numpy() * notional
    imp = np.nan_to_num(
        impact_bp(
            ntl, allr["adv21"].to_numpy("float64"), allr["vol21"].to_numpy("float64"), IMPACT_Y
        )
    )
    sell = allr["dw"].to_numpy() < 0
    allr["spread"] = cmult * hs_all * allr["adw"] / 1e4
    allr["impact"] = cmult * imp * allr["adw"] / 1e4
    allr["fees"] = (cmult * FEES_BP_PER_SIDE + np.where(sell, SEC_FEE_BP, 0.0)) * allr["adw"] / 1e4
    shorts = df[df["w"] < 0]
    borrow = (
        (-shorts["w"]).groupby(shorts["d"]).sum() * BORROW_BP_YEAR / 1e4 * (h / (390.0 * 252.0))
    )
    hd = per[["d", "j", "H"]].sort_values(["d", "j"])
    last = hd.groupby("d", as_index=False).agg(j=("j", "max"))
    last["j"] += 1
    last["H"] = 0.0
    hd = pd.concat([hd, last], ignore_index=True).sort_values(["d", "j"])
    hd["dH"] = hd["H"] - hd.groupby("d")["H"].shift(1).fillna(0.0)
    hd["hedge"] = (
        (cmult * (ETF_HALF_SPREAD_BP + FEES_BP_PER_SIDE) + np.where(hd["dH"] > 0, SEC_FEE_BP, 0.0))
        * hd["dH"].abs()
        / 1e4
    )
    pos = (df["side"] * (df["ret"] - df["beta_i"] * df["spy"])).groupby(df["d"]).sum() * 1e4
    daily = pd.DataFrame(
        {
            "gross": per.groupby("d")["gross"].sum(),
            "spread": allr.groupby("d")["spread"].sum(),
            "impact": allr.groupby("d")["impact"].sum(),
            "fees": allr.groupby("d")["fees"].sum(),
            "turnover": allr.groupby("d")["adw"].sum(),
            "borrow": borrow,
            "hedge": hd.groupby("d")["hedge"].sum(),
            "n_pos": df.groupby("d").size(),
            "pos_gross_bp": pos,
        }
    ).fillna(0.0)
    daily.index.name = "d"
    return daily.reset_index()[DAILY_COLS]


def with_net(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["cost"] = d[["spread", "impact", "fees", "borrow", "hedge"]].sum(axis=1)
    d["net"] = d["gross"] - d["cost"]
    return d


def annual_sharpe(r: pd.Series | np.ndarray) -> float:
    a = np.asarray(r, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 2 or not a.std(ddof=1) > 0:
        return float("nan")
    return float(a.mean() / a.std(ddof=1) * math.sqrt(252))
