"""H-20260923-09: what do we actually own in S3-vt40+boost?

S3 is live as a five-name levered-ETF rotation (top 2 of TQQQ/SOXL/UPRO/USD/TECL
by 63-day momentum, monthly, absolute momentum against cash), and with the
H-20260922-02 volatility target plus the H-20260922-05 dip boost it reaches
116.3% anchor CAGR. But H-20260918-05 already recorded that its ranking edge is
weak: 25% of random-pick seeds beat it. If the menu rotation contributes little,
then the object we own is "volatility-targeted levered index exposure", and the
next round should attack the exposure rule rather than the menu.

This decomposes the book into the layers that could be producing the return --
levered beta, the absolute-momentum filter, the menu breadth, the ranking, the
volatility target, the dip boost -- by running each variant through the same
simulator, the same frozen windows and the same cost assumption. Nothing here is
a new strategy proposal and no gate is re-searched; the frozen S3 cell is
reproduced as the control.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as sal  # noqa: E402

ITER_ID = "h20260923_09_s3_attribution"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
MENU = base.MENUS["A4_levered"]
CASH = base.CASH
TARGET = sal.S3_FROZEN_TARGET
BOOST_TARGET, BOOST_HOLD = 0.60, 10


def monthly_dates(close: pd.DataFrame) -> list[pd.Timestamp]:
    return list(close.index[base.rebalance_flags(close.index, "monthly")])


def picks_for(
    close: pd.DataFrame, variant: str, rng: np.random.Generator | None = None
) -> dict[pd.Timestamp, list[str]]:
    """Every variant uses the same signal dates, the same 63-day momentum score
    and the same absolute-momentum filter against cash. Only the breadth and the
    ranking change, so any difference is attributable to those two things."""
    score = base.momentum_score(close, "63")
    cash_score = score[CASH]
    menu = [s for s in MENU if s in close.columns]
    out: dict[pd.Timestamp, list[str]] = {}
    for d in monthly_dates(close):
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        cs = cash_score.loc[d]
        if variant == "A_tqqq_hold":
            out[d] = ["TQQQ"]
            continue
        if variant == "B_tqqq_absmom":
            chosen = ["TQQQ"] if "TQQQ" in row.index else []
        elif variant == "C_menu_equalweight":
            chosen = list(row.index)
        elif variant == "D_s3_rotation":
            chosen = list(row.sort_values(ascending=False).index[:2])
        elif variant == "E_s3_random":
            assert rng is not None
            chosen = list(rng.choice(list(row.index), size=min(2, len(row)), replace=False))
        else:
            raise ValueError(variant)
        if pd.notna(cs):
            chosen = [s for s in chosen if row.get(s, -np.inf) > cs]
        out[d] = chosen
    return out


def run(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    variant: str,
    overlay: str,
    boost: np.ndarray,
    rng: np.random.Generator | None = None,
) -> tuple[pd.Series, pd.Series]:
    cols = sorted({*MENU, CASH} & set(close.columns) | {CASH})
    sig = monthly_dates(close)
    w = base.weights_from_selection(close.index, sig, picks_for(close, variant, rng), cols)
    gross, _ = sal.simulate(w, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    if overlay == "none":
        scale = np.ones(len(close.index))
    elif overlay == "vt40":
        scale = sal.vol_scale(close.index, sig, gross, TARGET)
    elif overlay == "vt40_boost":
        scale = sal.vol_scale(close.index, sig, gross, TARGET, boost, BOOST_TARGET)
    else:
        raise ValueError(overlay)
    return sal.simulate(w, leg_open, leg_close, scale, base.COST_BPS_PRIMARY)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    close, open_ = base.load_panel(sal.symbols())
    leg_open, leg_close = sal.legs(close, open_)
    rf = close[base.RF].pct_change().fillna(0.0)
    boost = sal.boost_window(sal.dip_signal(close), BOOST_HOLD)
    print(f"{len(close)} sessions, dip boost on {int(boost.sum())} of them", flush=True)

    rows = []
    for variant in ("A_tqqq_hold", "B_tqqq_absmom", "C_menu_equalweight", "D_s3_rotation"):
        for overlay in ("none", "vt40", "vt40_boost"):
            ret, turn = run(close, leg_open, leg_close, variant, overlay, boost)
            wm = base.window_metrics(ret, rf, turn)
            rows.append(
                {
                    "variant": variant,
                    "overlay": overlay,
                    "anchor_cagr": wm["anchor"].cagr,
                    "anchor_max_dd": wm["anchor"].max_dd,
                    "anchor_sharpe": wm["anchor"].sharpe,
                    "holdout_sharpe": wm["holdout"].sharpe,
                    "turnover_yr": wm["anchor"].turnover_yr,
                }
            )
            print(f"  {variant:20s} {overlay:11s} done", flush=True)

    # E: random 2 of 5, the selection placebo, under the full frozen overlay
    rand = []
    for seed in range(args.seeds):
        rng = np.random.default_rng(20260923 + seed)
        ret, turn = run(close, leg_open, leg_close, "E_s3_random", "vt40_boost", boost, rng)
        wm = base.window_metrics(ret, rf, turn)
        rand.append(
            {
                "seed": seed,
                "anchor_cagr": wm["anchor"].cagr,
                "anchor_sharpe": wm["anchor"].sharpe,
                "holdout_sharpe": wm["holdout"].sharpe,
            }
        )
    rnd = pd.DataFrame(rand)
    table = pd.DataFrame(rows)
    table.to_parquet(OUT_DIR / "attribution.parquet")
    rnd.to_parquet(OUT_DIR / "random_selection.parquet")

    pd.set_option("display.width", 200)
    print("\n=== attribution (anchor window, 10 bp/side) ===")
    print(table.round(4).to_string(index=False))
    real = table[(table.variant == "D_s3_rotation") & (table.overlay == "vt40_boost")].iloc[0]
    print("\n=== random 2-of-5 selection under the same frozen overlay ===")
    print(
        f"real S3 anchor cagr {real.anchor_cagr:.4f} sharpe {real.anchor_sharpe:.3f} "
        f"holdout {real.holdout_sharpe:.3f}"
    )
    print(
        f"random median cagr {rnd.anchor_cagr.median():.4f}  "
        f"beat fraction {float((rnd.anchor_cagr > real.anchor_cagr).mean()):.2f}  "
        f"holdout-sharpe beat fraction "
        f"{float((rnd.holdout_sharpe > real.holdout_sharpe).mean()):.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
