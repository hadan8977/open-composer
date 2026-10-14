"""T-20261006-21: scorecard of all registered variants from the per-month daily shards.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/evaluate.py

Reads data/research/t21/daily/<variant>/x<cm>/<month>.parquet, writes
reports/research/iterations/t20261006_21_intraday_ml/results.json (variants block, selection, DSR) and
data/research/t21/series.parquet (daily gross/net series of every variant).
Metrics follow hypotheses.md and addendum-1.md (P1 tier of docs/evaluation-standard.zh.md).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from open_composer.research import scorecard_v2 as sc  # noqa: E402

OUT = ROOT / "data/research/t21"
PANEL = ROOT / "data/features/t21_panel"
ITER = ROOT / "reports/research/iterations/t20261006_21_intraday_ml"
RECENT_START = "2024-01-08"
DATA_END = "2026-10-05"  # contract: last complete session at freeze
CMS = ("0.5", "1.0", "2.0")


def trading_days() -> pd.DatetimeIndex:
    f = OUT / "days.json"
    if f.exists():
        return pd.DatetimeIndex(json.loads(f.read_text()))
    days = set()
    for p in sorted(PANEL.glob("*.parquet")):
        d = pd.read_parquet(p, columns=["d"])["d"].unique()
        days.update(pd.to_datetime(d))
    idx = pd.DatetimeIndex(sorted(days))
    f.write_text(json.dumps([str(x.date()) for x in idx]))
    return idx


def load_daily(variant: str, cm: str) -> pd.DataFrame:
    parts = sorted((OUT / "daily" / variant / f"x{cm}").glob("*.parquet"))
    if not parts:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df["d"] = pd.to_datetime(df["d"])
    return df.set_index("d").sort_index()


def variant_ids() -> list[dict]:
    g = json.loads((ITER / "variant-grid.json").read_text())
    return g["variants"]


def phases(last: pd.Timestamp) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    p = json.loads((ROOT / "data/research/equity_book/regimes/phases.json").read_text())[
        "phases_recent"
    ]
    return sc._phase_windows(p, pd.Timestamp(RECENT_START), last)


def stats(net: pd.Series) -> dict:
    return {
        "sharpe": sc.annual_sharpe(net),
        "mean_bp_day": float(net.mean() * 1e4),
        "sd_bp_day": float(net.std(ddof=1) * 1e4),
        "sessions": int(len(net)),
        "total_pct": float(net.sum() * 100),
    }


def main() -> int:
    days = trading_days()
    days = days[days <= DATA_END]
    last = days.max()
    rec = days[(days >= RECENT_START)]
    grid = variant_ids()
    ph = phases(last)
    series: dict[str, pd.DataFrame] = {}
    rows = {}
    for v in grid:
        vid = v["variant_id"]
        base = load_daily(vid, "1.0")
        if base.empty:
            continue
        r = {"spec": v}
        full = {}
        for cm in CMS:
            d = base if cm == "1.0" else load_daily(vid, cm)
            if d.empty:
                continue
            d = d.reindex(days).fillna(0.0)
            d["cost"] = d[["spread", "impact", "fees", "borrow", "hedge"]].sum(axis=1)
            d["net"] = d["gross"] - d["cost"]
            full[cm] = d
        b = full["1.0"]
        series[vid] = b[["gross", "net"]]
        br = b.loc[rec]
        r["recent"] = {
            "net": stats(br["net"]),
            "gross": stats(br["gross"]),
            "gross_pct_total": float(br["gross"].sum() * 100),
            "cost_pct_total": float(br["cost"].sum() * 100),
            "net_pct_total": float(br["net"].sum() * 100),
            "cost_share_of_gross": float(br["cost"].sum() / br["gross"].sum())
            if br["gross"].sum() > 0
            else None,
            "cost_components_pct": {
                c: float(br[c].sum() * 100) for c in ("spread", "impact", "fees", "borrow", "hedge")
            },
            "turnover_per_day": float(br["turnover"].mean()),
            "positions_per_day": float(br["n_pos"].mean()),
            "avg_gross_bp_per_position": float(
                br["pos_gross_bp"].sum() / max(br["n_pos"].sum(), 1)
            ),
            "avg_cost_bp_per_side_notional": float(
                br["cost"].sum() / max(br["turnover"].sum(), 1e-12) * 1e4
            ),
        }
        r["cost_tiers_net_sharpe"] = {cm: sc.annual_sharpe(full[cm].loc[rec, "net"]) for cm in full}
        r["phases"] = {
            pid: {
                "sessions": int(len(b.loc[a:z])),
                "net_sharpe": sc.annual_sharpe(b.loc[a:z, "net"]),
                "net_pct": float(b.loc[a:z, "net"].sum() * 100),
                "gross_pct": float(b.loc[a:z, "gross"].sum() * 100),
            }
            for pid, a, z in ph
        }
        rows[vid] = r
    if not rows:
        print("no daily shards yet")
        return 1
    # DSR over the registered trials found so far (all 75 when complete)
    panel = pd.DataFrame({v: s.loc[rec, "net"] for v, s in series.items()})
    n_trials = 75
    corr = panel.corr().to_numpy()
    iu = np.triu_indices_from(corr, k=1)
    mean_corr = float(np.nanmean(corr[iu])) if len(iu[0]) else 0.0
    shp = np.array([sc.annual_sharpe(panel[c]) for c in panel.columns])
    var_sr = float(np.nanvar(shp, ddof=1)) if len(shp) > 1 else 0.0
    n_eff = sc.n_eff_from_corr(n_trials, mean_corr)
    for vid, r in rows.items():
        s = panel[vid].dropna()
        r["dsr"] = sc.dsr(s.to_numpy(), var_sr_annual=var_sr, n_eff=n_eff) if s.std() > 0 else None
    out = {
        "iter_id": "t20261006_21_intraday_ml",
        "recent_window": [RECENT_START, str(last.date())],
        "sessions_recent": int(len(rec)),
        "variants_scored": len(rows),
        "n_trials_registered": n_trials,
        "mean_pairwise_corr": mean_corr,
        "n_eff": n_eff,
        "var_sr_annual": var_sr,
        "variants": rows,
    }
    (ITER / "results.partial.json").write_text(json.dumps(out, indent=1, default=float))
    pd.concat({k: v for k, v in series.items()}, names=["variant", "d"]).to_parquet(
        OUT / "series.parquet"
    )
    top = sorted(rows.items(), key=lambda kv: -(kv[1]["recent"]["net"]["sharpe"] or -9))[:10]
    for vid, r in top:
        print(
            f"{vid:28s} net {r['recent']['net']['sharpe']:6.2f} gross {r['recent']['gross']['sharpe']:6.2f} "
            f"x2 {r['cost_tiers_net_sharpe'].get('2.0', float('nan')):6.2f} cost/gross {r['recent']['cost_share_of_gross']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
