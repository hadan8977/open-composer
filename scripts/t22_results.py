# ruff: noqa: E501
"""Assemble results.json and breakeven-costs.json of T-20261006-22 from the Modal result directories.

    uv run python scripts/t22_results.py
Inputs: data/research/t22_results (phase 1), data/research/t22_results2 (phase 2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research import scorecard_v2 as scv  # noqa: E402
from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from open_composer.research.gate_additions import breakeven_cost_bps  # noqa: E402

P1 = ROOT / "data/research/t22_results"
P2 = ROOT / "data/research/t22_results2"
P3 = ROOT / "data/research/t22_results3"
IT = ROOT / "reports/research/iterations/t20261006_22_st_reversal"


def js(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def cell_row(d: dict) -> dict:
    m = d["net_1x"]
    return {
        "recent_net_sharpe": m.get("sharpe"),
        "recent_net_sharpe_0.5x_cost": d["net_0.5x"].get("sharpe"),
        "recent_net_sharpe_2x_cost": d["net_2.0x"].get("sharpe"),
        "recent_gross_sharpe": d["gross"]["sharpe"],
        "recent_gross_ann_excess_return": d["gross"]["ann_return"],
        "recent_net_ann_excess_return": m.get("ann_excess_return"),
        "vol": m.get("vol"),
        "max_drawdown": m.get("max_dd"),
        "nw_t": m.get("nw_t"),
        "turnover_annual_traded_over_equity": m.get("turnover"),
        "cost_share_of_gross": m.get("cost_share"),
        "costs_annual": d["costs_ann"],
        "beta_spy": m.get("beta_spy"),
        "avg_long_exposure": d["exposure"]["avg_long"],
        "avg_short_exposure": d["exposure"]["avg_short"],
        "avg_names_long": d["exposure"]["avg_n_long"],
        "avg_names_short": d["exposure"]["avg_n_short"],
        "capacity": d["capacity"],
        "engine_info": d.get("info"),
    }


def per_period_gross(
    daily: pd.DataFrame, rf: pd.Series, periods: dict[str, tuple[str, str]]
) -> dict:
    out = {}
    for k, (a, b) in periods.items():
        s = daily.loc[a:b]
        g = s["gross"] - rf.reindex(s.index).fillna(0.0)
        n = s["net"] - rf.reindex(s.index).fillna(0.0)
        sd = g.std(ddof=1)
        sdn = n.std(ddof=1)
        out[k] = {
            "n": len(s),
            "gross_sharpe": float(g.mean() / sd * np.sqrt(252)) if sd > 0 else None,
            "net_sharpe": float(n.mean() / sdn * np.sqrt(252)) if sdn > 0 else None,
        }
    return out


def main() -> None:
    rf, _ = load_rf_spy()
    sel = js(P1 / "selected.json")
    out: dict = {
        "iter_id": "t20261006_22_st_reversal",
        "contract": "reports/research/iterations/t20261006_22_st_reversal/contract.md (sections 0-15 frozen 2026-10-06T23:23Z, section 16 addendum 2 before any result)",
        "windows": {
            "recent": "2024-01-08..2026-09-15",
            "stress_diagnostic": "2017-10-02..2023-08-31",
            "forward_holdout_not_read": "2026-09-16..2026-09-30",
        },
        "trial_accounting": {
            "registered_cells": 30,
            "main_grid_cells_dsr_family": 24,
            "robustness_cells": 4,
            "model_cells": 2,
            "withdrawn_cells_in_global_ledger_from_23:22Z_version": 15,
            "extra_diagnostics_not_trials": [
                "reproduction anchor ind L1 H1 U1000 (2017-2026)",
                "borrow stress cells (2: 100 bp, shorts adv_rank<=1000) counted among the 4+1 robustness runs below",
            ],
        },
        "engine": {
            "run_book": "open_composer.research.equity_book.backtest",
            "cost_fn": "costfn.make_cost_fn (cost_model_v1, open snapshot)",
            "equity_usd": 300000,
            "names_per_side": 100,
            "side_gross": 0.5,
            "borrow_bp_per_year": 25,
        },
    }
    cells = {}
    for f in sorted((P1 / "A").glob("R_U*.json")):
        d = js(f)
        cid = d["cell_id"]
        row = cell_row(d)
        b = js(P1 / "B" / f.name)
        if b:
            row["stress"] = {
                "net_sharpe": b["net_1x"].get("sharpe"),
                "gross_sharpe": b["gross"]["sharpe"],
                "net_sharpe_2x": b["net_2.0x"].get("sharpe"),
                "turnover": b["net_1x"].get("turnover"),
                "max_drawdown": b["net_1x"].get("max_dd"),
            }
            sd = pd.read_parquet(P1 / "B" / f"{cid}.parquet")
            row["stress_21d_63d_worst_loss"] = {
                "21": float((1 + sd["net"]).rolling(21).apply(np.prod, raw=True).min() - 1),
                "63": float((1 + sd["net"]).rolling(63).apply(np.prod, raw=True).min() - 1),
            }
        cells[cid] = row
    out["main_grid_24"] = cells
    book_corr = js(P1 / "book_corr.json") or {}
    for k, v in book_corr.items():
        cells[k]["corr_with_existing_stock_book_v12_M0_U3000_F1"] = v["corr_with_v12_m0_u3000_f1"]
    out["selection"] = sel
    rob = {}
    for f in sorted((P1 / "robust").glob("ROB_*.json")):
        rob[f.stem] = cell_row(js(f))
    out["robustness_on_selected_spec"] = rob
    ml = {}
    for m in ("ridge", "lgbm"):
        for w in ("recent", "stress"):
            d = js(P2 / "ml" / f"{m}_ml_{w}.json")
            if d:
                ml[f"{m}_{w}"] = (
                    cell_row(d)
                    if w == "recent"
                    else {
                        "net_sharpe": d["net_1x"].get("sharpe"),
                        "gross_sharpe": d["gross"]["sharpe"],
                        "turnover": d["net_1x"].get("turnover"),
                    }
                )
    out["model_second_stage"] = ml
    expl = {}
    for f in sorted((P3 / "ml").glob("E*_ml_recent.json")):
        name = f.name.replace("_ml_recent.json", "")
        d = js(f)
        s = js(P3 / "ml" / f"{name}_ml_stress.json")
        expl[name] = cell_row(d)
        if s:
            expl[name]["stress"] = {
                "net_sharpe": s["net_1x"].get("sharpe"),
                "gross_sharpe": s["gross"]["sharpe"],
                "turnover": s["net_1x"].get("turnover"),
            }
    out["exploratory_cells_post_hoc_contract_section_17"] = expl
    if sel and (P2 / "ml" / "lgbm_ml_recent.parquet").exists():
        win = ("2024-01-08", "2026-09-15")

        def ex(path):
            s = pd.read_parquet(path)["net"].loc[win[0] : win[1]]
            return s - rf.reindex(s.index).fillna(0.0)

        rule = ex(P1 / "A" / f"{sel['cell_id']}.parquet")
        card = js(P1 / "scorecard.json")
        fam = card["family"] if card else None
        contrib = {}
        for m in ("ridge", "lgbm"):
            mm = ex(P2 / "ml" / f"{m}_ml_recent.parquet")
            j = pd.concat([mm, rule], axis=1, join="inner").dropna()
            row = {
                "net_sharpe_model": scv.annual_sharpe(mm),
                "net_sharpe_selected_rule": scv.annual_sharpe(rule),
                "nw_t_of_net_difference_model_minus_rule": scv.newey_west_t_diff(
                    j.iloc[:, 0], j.iloc[:, 1]
                ),
                "corr_model_vs_rule_net": float(j.corr().iloc[0, 1]),
            }
            if fam:
                n_eff = scv.n_eff_from_corr(26, fam["mean_pairwise_corr"])
                row["dsr_model_n26"] = scv.dsr(
                    mm.to_numpy(), var_sr_annual=fam["var_sr_annual"], n_eff=n_eff
                )
            contrib[m] = row
        out["ml_contribution_standard_section_7"] = contrib
    anchor = P2 / "anchor" / "R_U1000_ind_L1_none_H1_open.parquet"
    if anchor.exists():
        out["reproduction_anchor_ind_L1_H1_U1000"] = per_period_gross(
            pd.read_parquet(anchor),
            rf,
            {
                "2017-10..2018-12": ("2017-10-02", "2018-12-31"),
                "2019-01..2023-08": ("2019-01-02", "2023-08-31"),
                "2024-01..2026-09-15 (recent)": ("2024-01-08", "2026-09-15"),
                "2017-10..2023-08": ("2017-10-02", "2023-08-31"),
            },
        )
    pl = js(P2 / "placebo.json")
    if pl and sel:
        real = cells[sel["cell_id"]]
        net_arr, gross_arr = (
            np.array(list(pl["net"].values())),
            np.array(list(pl["gross"].values())),
        )
        out["placebo"] = {
            "n_seeds": len(net_arr),
            "net_placebo_mean": float(net_arr.mean()),
            "net_placebo_max": float(net_arr.max()),
            "gross_placebo_mean": float(gross_arr.mean()),
            "gross_placebo_max": float(gross_arr.max()),
            "real_net": real["recent_net_sharpe"],
            "real_gross": real["recent_gross_sharpe"],
            "net_percentile": float((net_arr < real["recent_net_sharpe"]).mean()),
            "gross_percentile": float((gross_arr < real["recent_gross_sharpe"]).mean()),
        }
    out["whole_share_v2"] = js(P1 / "whole_share.json")
    out["attribution_by_liquidity_tier"] = js(P1 / "attribution.json")
    out["identity_and_no_lookahead_checks"] = js(P1 / "checks.json")
    out["power"] = js(IT / "power.json")
    sc = js(P1 / "scorecard.json") or js(P2 / "scorecard.json")
    if sc:
        out["scorecard_v2"] = {
            "family": sc["family"],
            "selected_variant": sc["variants"].get(sel["cell_id"]) if sel else None,
        }
    (IT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    # break-even cost per side for every manifest candidate (representative = best recent net Sharpe in the family)
    man = js(IT / "candidate-manifest.json")
    be = {}
    for cand in man["candidates"]:
        cid = cand["candidate_id"]
        if cid.startswith("MAIN_"):
            fam = cid[5:]
            rows = {
                k: v for k, v in cells.items() if f"_{fam.split('_')[1]}_{fam.split('_')[0]}_" in k
            }
            if not rows:
                continue
            k = max(rows, key=lambda x: rows[x]["recent_net_sharpe"])
            r = rows[k]
        elif cid.startswith("ROBUST_"):
            key = {
                "lowturn": "ROB_lowturn_open_b25",
                "nonews": "ROB_nonews_open_b25",
                "vixscale": "ROB_vixscale_open_b25",
                "exec_close": "ROB_none_close_b25",
            }[cid[7:]]
            hit = [v for k2, v in rob.items() if k2.startswith(key)]
            r = hit[0] if hit else None
            k = key
        else:
            kk = f"{cid[6:]}_recent"
            r = ml.get(kk)
            k = kk
        if not r:
            be[cid] = {
                "breakeven_cost_bps_per_side": None,
                "not_applicable_reason": "cell not run in this iteration at the time of writing",
            }
            continue
        g, t = r["recent_gross_ann_excess_return"], r["turnover_annual_traded_over_equity"]
        be[cid] = {
            "representative_cell": k,
            "gross_return": g,
            "one_way_turnover": t,
            "breakeven_cost_bps_per_side": breakeven_cost_bps(g, t),
            "note": "gross annual excess return divided by annual traded notional over equity (both sides summed, so the cost is per traded dollar)",
        }
    (IT / "breakeven-costs.json").write_text(
        json.dumps({"iter_id": "t20261006_22_st_reversal", "candidates": be}, indent=1)
    )
    print("results.json and breakeven-costs.json written")


if __name__ == "__main__":
    main()
