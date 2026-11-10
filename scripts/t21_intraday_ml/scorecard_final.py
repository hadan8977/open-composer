"""T-20261006-21: final scorecard (P1 tier, addendum-1) from evaluate.py output, placebos and phases.

    uv run python scripts/t21_intraday_ml/scorecard_final.py

Reads results.partial.json + data/research/t21/series.parquet + data/research/t21/placebo/*.json,
writes reports/research/iterations/t20261006_21_intraday_ml/results.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from open_composer.research import scorecard_v2 as sc  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261006_21_intraday_ml"
OUT = ROOT / "data/research/t21"
RECENT = ("2024-01-08", "2026-10-05")


def median_spec(top3: list[dict]) -> dict:
    ns = sorted(s["universe_top_n"] for s in top3)
    ks = sorted(s["k"] for s in top3)
    hs = [s["horizon_min"] for s in top3]
    ms = [s["model"] for s in top3]
    h = max(set(hs), key=lambda x: (hs.count(x), -top3[hs.index(x)].get("rank", 0)))
    m = max(set(ms), key=lambda x: ms.count(x))
    return {"model": m, "universe_top_n": ns[1], "horizon_min": h, "k": ks[1]}


def main() -> int:
    res = json.loads((ITER / "results.partial.json").read_text())
    V = res["variants"]
    series = pd.read_parquet(OUT / "series.parquet")
    models = sorted(
        (v for v in V.values() if v["spec"]["family"] == "model"),
        key=lambda v: (
            -(v["recent"]["net"]["sharpe"] if np.isfinite(v["recent"]["net"]["sharpe"]) else -99)
        ),
    )
    out: dict = {"selection": {}}
    per_h = {}
    for h in (15, 30, 60):
        mh = [v for v in models if v["spec"]["horizon_min"] == h]
        per_h[h] = {
            "best": mh[0]["spec"]["variant_id"],
            "best_net_sharpe": mh[0]["recent"]["net"]["sharpe"],
            "best_cost_share_of_gross": mh[0]["recent"]["cost_share_of_gross"],
        }
    out["best_per_horizon"] = per_h
    top3 = [dict(v["spec"], rank=i) for i, v in enumerate(models[:3])]
    msp = median_spec(top3)
    sel_id = f"{msp['model']}_N{msp['universe_top_n']}_H{msp['horizon_min']}_K{msp['k']}"
    out["selection"] = {
        "rule": "addendum-1 A3: median spec of the three model variants with the highest recent net Sharpe",
        "top3": [m["variant_id"] if "variant_id" in m else m for m in top3],
        "selected": sel_id,
    }
    days = pd.DatetimeIndex(sorted(series.index.get_level_values("d").unique()))
    rec = days[(days >= RECENT[0]) & (days <= RECENT[1])]
    var_sr, n_eff = res["var_sr_annual"], res["n_eff"]
    cards = {}
    plc_dir = OUT / "placebo"
    ph = json.loads((ROOT / "data/research/equity_book/regimes/phases.json").read_text())[
        "phases_recent"
    ]
    phase_wins = sc._phase_windows(ph, pd.Timestamp(RECENT[0]), pd.Timestamp(RECENT[1]))
    state = pd.read_parquet(ROOT / "data/research/equity_book/regimes/market_state.parquet")
    for vid in {sel_id, models[0]["spec"]["variant_id"]}:
        if vid not in V:
            continue
        net = series.loc[vid, "net"].reindex(rec).fillna(0.0)
        gross = series.loc[vid, "gross"].reindex(rec).fillna(0.0)
        card = {
            "variant": vid,
            "net_sharpe": sc.annual_sharpe(net),
            "gross_sharpe": sc.annual_sharpe(gross),
        }
        card["dsr"] = V[vid].get("dsr")
        pf = plc_dir / f"{vid}.json"
        if pf.exists():
            p = json.loads(pf.read_text())
            pn, pg = list(p["net"].values()), list(p["gross"].values())
            card["placebo"] = {
                "seeds": len(pn),
                "net_mean": float(np.nanmean(pn)),
                "gross_mean": float(np.nanmean(pg)),
                "net_pct": sc.placebo_percentile(card["net_sharpe"], pn),
                "gross_pct": sc.placebo_percentile(card["gross_sharpe"], pg),
            }
        t2 = V[vid]["cost_tiers_net_sharpe"].get("2.0")
        rb = {
            "a_cost2x": bool(
                t2 is not None
                and np.isfinite(t2)
                and card["net_sharpe"] > 0
                and t2 >= 0.5 * card["net_sharpe"]
            )
        }
        # b: days with the same ex-ante state as the latest day
        try:
            st = state["state"] if "state" in state.columns else state.iloc[:, 0]
            st.index = pd.to_datetime(st.index).normalize()
            cur = st.iloc[-1]
            same = [d for d in rec if d in st.index and st.shift(1).get(d) == cur]
            rb["b_current_state_sharpe"] = (
                sc.annual_sharpe(net.reindex(same)) if len(same) >= sc.MIN_WINDOW_SESSIONS else None
            )
        except Exception as e:  # noqa: BLE001
            rb["b_current_state_sharpe"] = f"unavailable: {e}"
        tot = float(net.sum())
        shares = {}
        for pid, a, z in phase_wins:
            shares[pid] = float(net.loc[a:z].sum())
        rb["c_phase_net_pct"] = {k: v * 100 for k, v in shares.items()}
        rb["c_pass"] = bool(tot > 0 and all((tot - s) >= 0.5 * tot for s in shares.values()))
        rb["d_minute_shift"] = (
            "not computed (needs 1-minute re-aggregation, only for a candidate that passes the other P1 conditions)"
        )
        main_sr = card["net_sharpe"]
        z63 = (
            sc.sharpe_z(sc.annual_sharpe(net.iloc[-63:]), 63, main_sr, len(net))
            if np.isfinite(main_sr)
            else None
        )
        rb["e_z63"] = z63
        rb["e_pass"] = bool(z63 is not None and z63 >= -2.0)
        rb["f_gross_placebo_pct"] = card.get("placebo", {}).get("gross_pct")
        card["robustness"] = rb
        score = sum(
            [
                rb["a_cost2x"],
                isinstance(rb["b_current_state_sharpe"], float)
                and rb["b_current_state_sharpe"] > 0,
                rb["c_pass"],
                rb["e_pass"],
                rb["f_gross_placebo_pct"] is not None and rb["f_gross_placebo_pct"] >= 0.95,
            ]
        )
        card["robustness_score_of_5_computed"] = score
        card["P1"] = {
            "net_sharpe_gt_1_reference": bool(main_sr > 1.0),
            "dsr_ge_0.7": bool(card["dsr"] and card["dsr"]["dsr"] >= 0.7),
            "net_placebo_pct_ge_0.9": bool(
                card.get("placebo", {}).get("net_pct", 0) and card["placebo"]["net_pct"] >= 0.9
            ),
            "robustness_ge_3": score >= 3,
            "V4_done": False,
        }
        card["P1"]["pass"] = bool(
            all(v for k, v in card["P1"].items() if k != "net_sharpe_gt_1_reference")
        )
        cards[vid] = card
    out["cards"] = cards
    # model vs best baseline, same pool and horizon
    cmp_rows = {}
    for vid in {sel_id, models[0]["spec"]["variant_id"]}:
        if vid not in V:
            continue
        s = V[vid]["spec"]
        base = [
            b
            for b in V.values()
            if b["spec"]["family"] == "baseline"
            and b["spec"]["universe_top_n"] == s["universe_top_n"]
            and b["spec"]["horizon_min"] in (s["horizon_min"], 25)
        ]
        best = max(base, key=lambda b: b["recent"]["net"]["sharpe"])
        bid = best["spec"]["variant_id"]
        d = series.loc[vid, "net"].reindex(rec).fillna(0) - series.loc[bid, "net"].reindex(
            rec
        ).fillna(0)
        cmp_rows[vid] = {
            "best_baseline": bid,
            "baseline_net_sharpe": best["recent"]["net"]["sharpe"],
            "diff_nw_t": sc.newey_west_t_diff(
                series.loc[vid, "net"].reindex(rec).fillna(0),
                series.loc[bid, "net"].reindex(rec).fillna(0),
            ),
        }
    out["model_vs_baseline"] = cmp_rows
    out["trials"] = {
        "n_registered": res["n_trials_registered"],
        "n_scored": res["variants_scored"],
        "n_eff": n_eff,
        "var_sr_annual": var_sr,
        "mean_pairwise_corr": res["mean_pairwise_corr"],
    }
    out["window"] = {"recent": list(RECENT), "sessions": int(len(rec))}
    out["variants"] = V
    (ITER / "results.json").write_text(json.dumps(out, indent=1, default=float))
    print(
        json.dumps(
            {k: out[k] for k in ("best_per_horizon", "selection", "model_vs_baseline", "trials")},
            indent=1,
            default=float,
        )[:3000]
    )
    for vid, c in cards.items():
        print(vid, "net", round(c["net_sharpe"], 2), "P1", c["P1"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
