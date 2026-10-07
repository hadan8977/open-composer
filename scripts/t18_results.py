# ruff: noqa: E501
"""T-20261006-18: results.json, leaderboard.md, breakeven-costs.json from the analysis outputs, with the labels of
hypotheses.md section 5 (factors) and the lane hypotheses section 3 (ETF / calendar rules).

    uv run python scripts/t18_results.py
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

from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import t18_analyze as AN  # noqa: E402
from scripts import t18_engine as E  # noqa: E402
from scripts import t18_factors as F  # noqa: E402

OUT = AN.OUT
FIRST = {
    i["id"]: i
    for i in json.loads((ROOT / "reports/research/strategy-library/first-batch.json").read_text())[
        "items"
    ]
}
SHORT_SAMPLE = {"MomSeason06YrPlus", "MomOffSeason06YrPlus"}


def first_id(name: str) -> str:
    return "qc-standardized-unexpected-earnings" if name == "SUE" else f"osap-{name}"


def coverage(name: str) -> float:
    vals = []
    for y in (2024, 2025, 2026):
        df = pd.read_parquet(
            F.FACTOR_DIR / f"{y}.parquet", columns=["trade_date", "in_u3000", name]
        )
        df = df[df["in_u3000"].fillna(False).astype(bool)]
        vals.append(df.groupby("trade_date")[name].apply(lambda s: s.notna().mean()).mean())
    return float(np.mean(vals))


def v4(ex: pd.Series) -> dict:
    x = ex[(ex.index >= AN.DIAG[0]) & (ex.index <= AN.DIAG[1])]
    mv, qv = x.std() * 21**0.5, x.std() * 63**0.5
    w21, w63 = -x.rolling(21).sum().min(), -x.rolling(63).sum().min()
    return {
        "worst21_over_monthly_vol": float(w21 / mv),
        "worst63_over_quarterly_vol": float(w63 / qv),
        "veto": bool(w21 > 5 * mv or w63 > 4 * qv),
    }


def diag_t3(name: str, rf: pd.Series) -> dict | None:
    try:

        def bl(k: str) -> pd.Series:
            return pd.concat(
                [pd.read_parquet(E.SERIES / f"{k}{o}.parquet")["net"] for o in range(5)], axis=1
            ).mean(axis=1)

        base = bl("t3d__base__o")
        out = {}
        for v in ("w0.5", "w1.0", "w2.0", "merge"):
            s = bl(f"t3d__{name}__{v}__o")
            a = AN.win(s - rf.reindex(s.index).fillna(0.0), *AN.DIAG)
            b = AN.win(base - rf.reindex(base.index).fillna(0.0), *AN.DIAG)
            out[v] = {
                "sharpe": AN.sharpe(a.to_numpy()),
                "base": AN.sharpe(b.to_numpy()),
                "delta": AN.sharpe(a.to_numpy()) - AN.sharpe(b.to_numpy()),
            }
        return out
    except FileNotFoundError:
        return None


def main() -> None:
    raw = json.loads((OUT / "t3_analysis_raw.json").read_text())
    rf, _ = load_rf_spy()
    res: dict = {
        "base_recent_sharpe_excess_bil": raw["base_recent_sharpe"],
        "families": {k: v["_family"] for k, v in raw["families"].items()},
        "factors": {},
        "data_insufficient": {},
        "lane": None,
    }
    base = pd.concat(
        [pd.read_parquet(E.SERIES / f"t3__base__o{o}.parquet")["net"] for o in range(5)], axis=1
    ).mean(axis=1)
    res["base_recent_sharpe_net_no_rf"] = AN.sharpe(AN.win(base, *AN.RECENT).to_numpy())
    breakeven = {}
    for name in F.COMPUTED:
        f = raw["factors"][name]
        uni, proc = AN.main_spec(name)
        t1 = f["tier1"][f"{uni}_{proc}"]
        t1p = f["tier1"][f"P1000_{proc}"]
        t3 = f.get("tier3", {})
        d = {v: t3[v]["delta"] for v in ("w0.5", "w1.0", "w2.0", "merge") if v in t3}
        cov = coverage(name)
        th = f.get("tier2", {})
        maxcorr = {
            w: max(
                abs(v)
                for k, v in th.get(f"corr_themes_{w}", {}).items()
                if k != "M0" and np.isfinite(v)
            )
            for w in ("full", "recent")
        }
        plc = (f.get("placebo_gross") or {}).get("recent", {}).get("pct_below")
        main = AN.load(f"t1__{name}__{uni}__{proc}")
        ex = AN.ex_series(main["net"], rf)
        v4r = v4(ex)
        gross_ann = float(AN.win(main["gross"], *AN.RECENT).mean() * 252)
        turn = float(AN.win(main["turnover"], *AN.RECENT).mean() * 252)
        breakeven[name] = {
            "breakeven_cost_bps_per_side": gross_ann / turn * 1e4 if turn > 0 else None,
            "gross_return": gross_ann,
            "one_way_turnover": turn,
            **({} if turn > 0 else {"not_applicable_reason": "zero turnover"}),
        }
        # ---- rule: into the book
        c = {}
        if len(d) == 4:
            c["delta_w1_ge_0.10"] = d["w1.0"] >= 0.10
            c["two_of_four_ge_0.10_none_le_-0.10"] = (
                sum(v >= 0.10 for v in d.values()) >= 2 and min(d.values()) > -0.10
            )
            c["p_delta_pos_ge_0.75"] = t3["w1.0"]["p_pos"] >= 0.75
        c["oriented_ic_pos_and_gross_sharpe_pos_recent"] = (
            t1["ic_recent"].get("ic_mean", -1) > 0 and t1["gross_sharpe_recent"] > 0
        )
        c["max_theme_corr_lt_0.8_both_windows"] = bool(
            maxcorr["full"] < 0.8 and maxcorr["recent"] < 0.8
        )
        c["coverage_ge_0.5"] = cov >= 0.5
        c["gross_placebo_ge_0.80"] = plc is not None and plc >= 0.80
        pre = all(c.values()) and len(c) == 6 + 1 - 0 and name not in SHORT_SAMPLE
        dg = diag_t3(
            name, rf
        )  # run for IntMom as an extra although the rule only requires it when the recent conditions hold
        c["crash_diag_delta_w1_ge_-0.10"] = (dg["w1.0"]["delta"] >= -0.10) if dg else None
        into_book = bool(pre and dg and c["crash_diag_delta_w1_ge_-0.10"])
        # ---- rule: own paper sleeve (P1-style proxy)
        dsr = raw["families"]["tier1"].get(f"{name}|{uni}|{proc}", {}).get("dsr")
        sl = {
            "family_dsr_ge_0.70": dsr is not None and dsr >= 0.70,
            "gross_placebo_ge_0.90": plc is not None and plc >= 0.90,
            "ic_nw_t_ge_2": t1["ic_recent"].get("ic_nw_t", -9) >= 2.0,
            "cost2x_recent_excess_pos": t1["net_2xcost_excess_recent"] > 0,
            "v4_no_veto": not v4r["veto"],
            "tier2_alpha_t_ge_1": th.get("spanning_recent", {}).get("alpha_t", -9) >= 1.0,
        }
        sleeve = all(sl.values()) and name not in SHORT_SAMPLE
        # ---- rule: unfounded in the recent window
        unf = (
            name not in SHORT_SAMPLE
            and len(d) == 4
            and t1["net_recent"]["sharpe"] <= 0
            and t1p["net_recent"]["sharpe"] <= 0
            and (t1["ic_recent"].get("ic_mean", 1) <= 0 or t1["ic_recent"].get("ic_nw_t", 9) < 1)
            and (t1p["ic_recent"].get("ic_mean", 1) <= 0 or t1p["ic_recent"].get("ic_nw_t", 9) < 1)
            and all(v <= 0 for v in d.values())
        )
        label = (
            "进组合"
            if into_book
            else "独立上模拟盘"
            if sleeve
            else "不成立（近期窗口）"
            if unf
            else "未到深度"
        )
        T = t1["net_recent"]["n"] / 252
        sr = t1["net_recent"]["sharpe"]
        res["factors"][name] = {
            "first_batch_id": first_id(name),
            "label": label,
            "coverage_u3000_2024_26": cov,
            "tier1_main_spec": f"{uni}_{proc}",
            "tier1": f["tier1"],
            "standalone_power": {
                "se_sharpe_recent": float(np.sqrt((1 + 0.5 * sr**2) / T)),
                "mde80_sharpe_recent": float(2.487 * np.sqrt((1 + 0.5 * sr**2) / T)),
            },
            "ff5_alpha_recent": f.get("ff5_alpha_recent"),
            "ff5_alpha_full": f.get("ff5_alpha_full"),
            "tier2": th,
            "closest_theme": f.get("closest_theme"),
            "tier3_recent": t3,
            "tier3_crash_diag": dg,
            "placebo_gross": f.get("placebo_gross"),
            "family_dsr_tier1_main": raw["families"]["tier1"].get(f"{name}|{uni}|{proc}"),
            "rule_into_book": c,
            "rule_sleeve": sl,
            "rule_unfounded_met": bool(unf),
            "v4_main_spec": v4r,
            "breakeven": breakeven[name],
            "short_sample_caveat": name in SHORT_SAMPLE,
        }
    for name, v in F.DEFINITIONS.items():
        if v["status"] != "ok":
            res["data_insufficient"][name] = {
                "first_batch_id": first_id(name),
                "label": "数据不足",
                "missing": v["missing"],
            }
    lane_p = OUT / "lane-results.json"
    if lane_p.exists():
        res["lane"] = lane_labels(json.loads(lane_p.read_text()))
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    (OUT / "breakeven-costs.json").write_text(
        json.dumps(
            {
                "candidates": breakeven,
                "note": "recent window, tier-1 main spec: gross annual return / annual traded notional (sum |dw|), bp per traded notional",
            },
            indent=1,
            default=float,
        )
    )
    (OUT.parent / "t20261006_18_library_batch1_lane" / "lane-results.json").write_text(
        lane_p.read_text()
    ) if lane_p.exists() else None
    leaderboard(res)
    print({k: v["label"] for k, v in res["factors"].items()})


def lane_labels(L: dict) -> dict:
    by = {c["id"]: c for c in L["candidates"]}
    out = {}
    for gid, g in L["groups"].items():
        members = [
            c
            for cid, c in by.items()
            if cid.startswith(tuple(g["prefix"])) and not c.get("skipped")
        ]
        p = by.get(g["primary"])
        if p is None or p.get("skipped"):
            out[gid] = {
                "label": "数据不足",
                "primary": g["primary"],
                "note": "primary member skipped (symbol missing)",
            }
            continue
        jo = p["judged"]["anchor"]["offset"]
        n20 = p["per_window"]["anchor"]["offsets"][str(jo)]["net20"]["sharpe"]
        edge = p["diversifier"]["anchor"]["judged_edge"]
        dsr = p.get("dsr_anchor")
        plc = (p.get("circular_shift_placebo") or {}).get("pct_below_real")
        veto = (p.get("v4_stress") or {}).get("veto")
        sleeve = bool(
            edge >= 0.10
            and n20 > 0
            and dsr is not None
            and dsr >= 0.70
            and plc is not None
            and plc >= 0.90
            and veto is False
        )
        sr = p["judged"]["anchor"]["sharpe"]
        members_sr = {c["id"]: c["judged"]["anchor"]["sharpe"] for c in members}
        real_sr = {
            k: v for k, v in members_sr.items() if not k.startswith("PLACEBO") and "RAND" not in k
        }
        unf = bool(sr <= 0 and all(v <= 0.3 for v in real_sr.values()))
        passing_other = [
            k
            for k, c in ((c["id"], c) for c in members)
            if k != g["primary"]
            and not k.startswith("PLACEBO")
            and "RAND" not in k
            and c["diversifier"]["anchor"]["judged_edge"] >= 0.10
            and (c.get("dsr_anchor") or 0) >= 0.70
            and (c.get("circular_shift_placebo") or {}).get("pct_below_real", 0) >= 0.90
        ]
        T = 33 / 12
        out[gid] = {
            "label": "独立上模拟盘（P1代理）"
            if sleeve
            else "不成立（近期窗口）"
            if unf
            else "未到深度",
            "primary": g["primary"],
            "anchor_sharpe_net10": sr,
            "anchor_sharpe_net20": n20,
            "anchor_edge_vs_vol_matched_s3": edge,
            "dsr_anchor": dsr,
            "circular_shift_placebo_pct": plc,
            "v4_stress": p.get("v4_stress"),
            "members_anchor_sharpe": members_sr,
            "other_members_passing": passing_other,
            "power_mde80_sharpe": float(2.487 * np.sqrt((1 + 0.5 * max(sr, 0) ** 2) / T)),
        }
    return out


def leaderboard(res: dict) -> None:
    rows = [
        "# Library batch 1 leaderboard (T-20261006-18)",
        "",
        f"Base v1.2 M0_U3000, recent window 2024-01-08..2026-09-17, five-offset blend: Sharpe over BIL {res['base_recent_sharpe_excess_bil']:.2f}, net without BIL subtraction {res['base_recent_sharpe_net_no_rf']:.2f}.",
        "",
        "## Stock factors (19 computed + 6 data-insufficient)",
        "",
        "| first-batch id | label | IC recent (NW t) | net Sharpe U3000 / P1000 (recent) | FF5 alpha t (recent) | Delta Sharpe w0.5 / w1 / w2 / merge | MDE 80% | coverage |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in res["factors"].values():
        t = f["tier1"][f["tier1_main_spec"]]
        pm = f["tier1"][f"P1000_{f['tier1_main_spec'].split('_')[1]}"]
        d = f["tier3_recent"]
        ds = " / ".join(
            f"{d[v]['delta']:+.2f}" for v in ("w0.5", "w1.0", "w2.0", "merge") if v in d
        )
        ff = (f.get("ff5_alpha_recent") or {}).get("alpha_t")
        mde = d.get("w1.0", {}).get("mde_80")
        rows.append(
            f"| {f['first_batch_id']} | {f['label']} | {t['ic_recent'].get('ic_mean', float('nan')):+.3f} ({t['ic_recent'].get('ic_nw_t', float('nan')):.1f}) | {t['net_recent']['sharpe']:.2f} / {pm['net_recent']['sharpe']:.2f} | {ff if ff is None else round(ff, 1)} | {ds} | {mde if mde is None else round(mde, 2)} | {f['coverage_u3000_2024_26']:.0%} |"
        )
    for v in res["data_insufficient"].values():
        rows.append(f"| {v['first_batch_id']} | 数据不足 | - | - | - | - | - | {v['missing']} |")
    if res["lane"]:
        rows += [
            "",
            "## ETF and calendar rules (primary member)",
            "",
            "| first-batch id | label | primary | anchor Sharpe 10bp / 20bp | edge vs vol-matched S3 | DSR (63 trials) | circular-shift placebo | stress V4 veto |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for gid, v in res["lane"].items():
            if "anchor_sharpe_net10" not in v:
                rows.append(f"| {gid} | {v['label']} | {v['primary']} | - | - | - | - | - |")
                continue
            rows.append(
                f"| {gid} | {v['label']} | {v['primary']} | {v['anchor_sharpe_net10']:.2f} / {v['anchor_sharpe_net20']:.2f} | {v['anchor_edge_vs_vol_matched_s3']:+.2f} | {v['dsr_anchor'] if v['dsr_anchor'] is None else round(v['dsr_anchor'], 2)} | {v['circular_shift_placebo_pct']} | {(v['v4_stress'] or {}).get('veto')} |"
            )
    (OUT / "leaderboard.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
