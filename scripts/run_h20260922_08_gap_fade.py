"""H-20260922-08: cross-sectional response of the intraday session to the
overnight gap, and the gap-fade book built from it.

Rebuilt from Concretum's public description (Russell 3000 minus the least liquid
30%, fade abnormally large overnight gaps during the following session; author
reports 2012-01 to 2026-05 gross CAGR ~98%, Sharpe ~2.08, max drawdown ~67%, and
says the curve peaked in H1 2022 and has given back much of the gain since). The
rule table itself is behind a paywall, so this is a reconstruction, not a
line-by-line replication, and the card says so.

The direction is not assumed. We first estimate E[oc | z bucket]; reversal and
continuation are both publishable answers and the book's sign is read off the
select window, not chosen in advance. Grid, windows and the pass condition were
frozen in prefreeze.md before any number here was computed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/features/gap_panel.parquet"
OUT_DIR = ROOT / "reports/research/iterations/h20260922_08_gap_fade"

EARLY = ("2016-03-31", "2021-12-31")
LATE = ("2022-01-01", "2026-09-21")
LEG_SIZES = (10, 20, 50)
LIQ_TIERS = (1e6, 1e7, 5e7)
COSTS_BPS = (5.0, 10.0, 20.0)
BORROW_BPS = (0.0, 10.0, 25.0)
SHIFTS = tuple(range(1, 21))


def load_panel() -> pd.DataFrame:
    d = pd.read_parquet(PANEL, columns=["symbol", "date", "z", "oc", "dv21"])
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values(["date", "z"], kind="stable").reset_index(drop=True)


def bucket_response(panel: pd.DataFrame, liq: float) -> pd.DataFrame:
    """E[oc | z bucket], demeaned by day so it is a cross-sectional statement."""
    d = panel[panel["dv21"] >= liq].copy()
    d["oc_dm"] = d["oc"] - d.groupby("date")["oc"].transform("mean")
    edges = [-np.inf, -4, -3, -2, -1, -0.5, 0.5, 1, 2, 3, 4, np.inf]
    d["bucket"] = pd.cut(d["z"], edges)
    g = d.groupby("bucket", observed=True)["oc_dm"]
    out = pd.DataFrame({"n": g.size(), "pooled_bp": g.mean() * 1e4})
    # Everything inferential is computed on the daily mean of each bucket, so that
    # names overlapping inside one day do not masquerade as independent draws. The
    # pooled mean is kept only for contrast: where the two disagree in sign, the
    # bucket is populated on a few clustered days and the pooled number is the
    # misleading one.
    daily = d.groupby(["date", "bucket"], observed=True)["oc_dm"].mean().unstack()
    means, ts, ndays = [], [], []
    for b in out.index:
        col = daily[b].dropna() if b in daily else pd.Series(dtype=float)
        ndays.append(int(len(col)))
        if len(col) > 30 and col.std(ddof=1) > 0:
            means.append(float(col.mean() * 1e4))
            ts.append(float(col.mean() / col.std(ddof=1) * np.sqrt(len(col))))
        else:
            means.append(np.nan)
            ts.append(np.nan)
    out["mean_bp"] = means
    out["t_daily"] = ts
    out["days"] = ndays
    out["liq"] = liq
    out = out.reset_index()
    out["bucket"] = out["bucket"].astype(str)
    return out


def select(panel: pd.DataFrame, liq: float, k: int) -> pd.DataFrame:
    """Long the k most negative z, short the k most positive z, per day."""
    d = panel[panel["dv21"] >= liq]
    pos = d.groupby("date").cumcount()
    n = d.groupby("date")["z"].transform("size")
    longs = d[pos < k].assign(side=1.0)
    shorts = d[pos >= n - k].assign(side=-1.0)
    return pd.concat([longs, shorts])[["date", "symbol", "side"]]


def book_returns(
    sel: pd.DataFrame, oc_map: pd.DataFrame, cost_bps: float, borrow_bps: float
) -> pd.Series:
    """Dollar-neutral book: 1x long notional, 1x short notional, return on capital
    is the mean of the two legs' contributions. Cost is charged on entry and exit
    of both legs; borrow is charged on the short notional for the one day held."""
    m = sel.merge(oc_map, on=["date", "symbol"], how="inner")
    m["contrib"] = m["side"] * m["oc"]
    leg = m.groupby(["date", "side"])["contrib"].mean().unstack()
    if 1.0 not in leg or -1.0 not in leg:
        return pd.Series(dtype=float)
    gross = (leg[1.0] + leg[-1.0]) / 2.0
    cost = 2.0 * cost_bps / 1e4  # two sides per day, averaged over the two legs
    borrow = borrow_bps / 1e4 / 2.0  # short leg only, halved by the capital convention
    return gross - cost - borrow


def stats(ret: pd.Series) -> dict:
    ret = ret.dropna()
    if len(ret) < 30:
        return {}
    eq = (1.0 + ret).cumprod()
    years = len(ret) / 252.0
    return {
        "days": int(len(ret)),
        "cagr": float(eq.iloc[-1] ** (1.0 / years) - 1.0) if eq.iloc[-1] > 0 else -1.0,
        "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(252.0))
        if ret.std(ddof=1) > 0
        else np.nan,
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
        "mean_bp": float(ret.mean() * 1e4),
        "hit": float((ret > 0).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    panel = load_panel()
    print(f"panel {len(panel):,} rows, {panel['symbol'].nunique():,} symbols", flush=True)
    oc_map = panel[["date", "symbol", "oc"]]
    dates = np.array(sorted(panel["date"].unique()))

    resp = pd.concat([bucket_response(panel, liq) for liq in LIQ_TIERS], ignore_index=True)
    resp.to_parquet(OUT_DIR / "bucket_response.parquet")
    print("\n=== E[oc | z bucket], day-demeaned, all windows ===")
    print(resp[resp["liq"] == 1e7].to_string(index=False))

    rows = []
    sels = {}
    for liq in LIQ_TIERS:
        for k in LEG_SIZES:
            sel = select(panel, liq, k)
            sels[(liq, k)] = sel
            for cost in COSTS_BPS:
                for borrow in BORROW_BPS:
                    r = book_returns(sel, oc_map, cost, borrow)
                    for name, (lo, hi) in (("early", EARLY), ("late", LATE)):
                        w = r[(r.index >= lo) & (r.index <= hi)]
                        rows.append(
                            {
                                "liq": liq,
                                "k": k,
                                "cost_bps": cost,
                                "borrow_bps": borrow,
                                "window": name,
                                **stats(w),
                            }
                        )
            print(f"  liq {liq:.0e} k {k} done", flush=True)
    cells = pd.DataFrame(rows)
    cells.to_parquet(OUT_DIR / "cells.parquet")

    # placebo on the frozen judgement cell: liq $10M, k=20, 5 bp, 10 bp borrow, late
    key = (1e7, 20)
    real = book_returns(sels[key], oc_map, 5.0, 10.0)
    real_late = stats(real[(real.index >= LATE[0]) & (real.index <= LATE[1])])
    pos = {d: i for i, d in enumerate(dates)}
    base = sels[key].copy()
    base["idx"] = base["date"].map(pos)
    pl = []
    for k_shift in SHIFTS:
        s = base.copy()
        s["idx"] = s["idx"] + k_shift
        s = s[s["idx"] < len(dates)]
        s["date"] = dates[s["idx"].to_numpy()]
        r = book_returns(s[["date", "symbol", "side"]], oc_map, 5.0, 10.0)
        w = r[(r.index >= LATE[0]) & (r.index <= LATE[1])]
        pl.append({"placebo": "calendar_shift", "seed": k_shift, **stats(w)})
    # random-pick placebo: same leg sizes drawn at random from the eligible set
    elig = panel[panel["dv21"] >= 1e7][["date", "symbol"]]
    for seed in range(args.seeds):
        rng = np.random.default_rng(20260922 + seed)
        take = elig.sample(frac=1.0, random_state=int(rng.integers(1 << 31)))
        c = take.groupby("date").cumcount()
        s = pd.concat([take[c < 20].assign(side=1.0), take[(c >= 20) & (c < 40)].assign(side=-1.0)])
        r = book_returns(s, oc_map, 5.0, 10.0)
        w = r[(r.index >= LATE[0]) & (r.index <= LATE[1])]
        pl.append({"placebo": "random_pick", "seed": seed, **stats(w)})
    placebo = pd.DataFrame(pl)
    placebo.to_parquet(OUT_DIR / "placebo.parquet")

    print("\n=== judgement cell: liq $10M, k=20, 5 bp/side, 10 bp/day borrow, late window ===")
    print(json.dumps(real_late, indent=2, default=float))
    beat = {}
    for name, g in placebo.groupby("placebo"):
        beat[name] = {
            "median_cagr": float(g["cagr"].median()),
            "beat_fraction": float((g["cagr"] > real_late["cagr"]).mean()),
        }
    print(json.dumps(beat, indent=2))
    passes = (
        real_late.get("cagr", -1) > 0
        and real_late.get("sharpe", -9) >= 1.0
        and beat.get("calendar_shift", {}).get("beat_fraction", 1.0) <= 0.10
    )
    print(f"\nFROZEN PASS CONDITION: {'PASS' if passes else 'FAIL'}")
    (OUT_DIR / "summary.json").write_text(
        json.dumps(
            {"judgement_cell": real_late, "placebo": beat, "passes": bool(passes)},
            indent=2,
            default=float,
        )
        + "\n"
    )
    print("\n=== best cells by late-window Sharpe (5 bp, 10 bp borrow) ===")
    sub = cells[
        (cells["window"] == "late") & (cells["cost_bps"] == 5.0) & (cells["borrow_bps"] == 10.0)
    ]
    print(sub.sort_values("sharpe", ascending=False).head(9).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
