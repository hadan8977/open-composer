"""Mechanical first-batch selection (rule: selection-rule.md, written before this ran).

    python3 reports/research/strategy-library/select_first_batch.py

Reads catalog.json + the read-only direction registry snapshot, writes first-batch.json.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAT = json.load(open(HERE / "catalog.json"))
DIRS = {r["id"]: r for r in json.load(open(HERE / "_directions_latest.json"))}

TARGET = 50
RETEST_CAP = 14
ORIGIN_CAP = 24
FAMILY_CAP = 3
BUCKET_MIN = {"intraday": 8, "event": 8, "daily": 6, "weekly_monthly": 12}
IN_PROGRESS = {"passed", "testing", "queued", "triaged", "harvested"}
DENIED = {"refuted", "evidence_too_weak", "parked", "partial"}
CX = {"S": 0, "M": 1, "L": 2}


def bucket(r: dict) -> str:
    f = r["frequency"]
    return "weekly_monthly" if f in ("weekly", "monthly") else f


def specific_statuses(r: dict) -> list[str]:
    if r["prior_scope"] != "specific":
        return []
    return [DIRS[i]["status"] for i in r["prior_ids"] if i in DIRS]


def tested_statuses(r: dict) -> list[str]:
    """statuses that count as 'tested locally but not at depth' (rule section 1/3)"""
    if r["prior_scope"] != "specific" or not r.get("prior_locally_tested"):
        return []
    return [s for s in specific_statuses(r) if s in DENIED]


def eligibility(r: dict) -> tuple[bool, list[str], str]:
    """returns (eligible, failed conditions, retest flag)"""
    fails = []
    if r["alpaca_tradable"] != "yes":
        fails.append("E1")
    if not r["adapter_1d"]:
        fails.append("E2")
    if r["entry_type"] != "strategy" or r["asset_class"] not in ("us_equity", "etf", "options", "crypto"):
        fails.append("E3")
    sts = specific_statuses(r)
    if any(s in IN_PROGRESS for s in sts) or any(s == "not_executable" for s in sts) or r.get("in_equity_book"):
        fails.append("E4")
    if r["prior_depth_ok"] == "yes":
        fails.append("E5")
    retest = "yes" if tested_statuses(r) else "no"
    return (not fails), fails, retest


def tier(r: dict) -> int:
    if r["origin_list"] == "osap":
        p, q = r.get("osap_predictability", ""), r.get("osap_rep_quality", "")
        if p == "1_clear" and q == "1_good":
            return 1
        if p in ("1_clear", "2_likely") and q in ("1_good", "2_fair"):
            return 2
        return 3
    if r["origin_list"] == "qc":
        return 3 if "Premium" in r["original_paper"] else 2
    return 3


def recency(r: dict) -> int:
    if r["origin_list"] == "osap":
        return r.get("osap_year", 0)
    ys = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-3]\d)\b", r["original_paper"])]
    return max(ys) if ys else 2010


def sort_key(r: dict):
    never = 0 if (r["prior_scope"] in ("none", "generic_only", "family_level") or not r.get("prior_locally_tested")) else 1
    return (tier(r), never, -recency(r), CX[r["complexity"]], r["id"])


# ---------------------------------------------------------------- templates / costs
CAL = {"turn_of_month", "pre_holiday_effect", "calendar_seasonality_index", "lunar_cycle_timing", "macro_announcement_drift",
       "oil_predicts_equity_timing", "vix_timing", "gold_timing", "january_effect"}
ROT = {"etf_momentum_rotation", "factor_style_etf_rotation", "country_etf_momentum", "country_etf_mean_reversion", "country_etf_value",
       "cross_asset_etf_trend", "low_risk_beta", "size_price"}


def template(r: dict) -> str:
    f, eng, a = r["family_key"], r["engine"], r["asset_class"]
    if a == "crypto":
        return "scripts/screen_batches/h20260929_33_crypto_trend.py (crypto spot long-only; new signal function)"
    if a == "options":
        return "no lane template: option-chain replay on data/options + data/dolthub_options (new harness; registry dir:options_premium_selling_real_chain_batch is the closest queued task)"
    if r["frequency"] == "intraday":
        return "no lane template: minute-bar harness needed (reuse data/features/minute_panel and scripts/build_intraday_daily_features.py for loading; new signal/exit code)"
    if eng == "lane":
        if f == "option_expiration_week":
            return "scripts/screen_batches/h20260928_42_opex_week.py"
        if f in CAL:
            return "scripts/screen_batches/h20260929_02_pre_holiday_etf.py (calendar rule with signal_dates_fn)"
        if f == "etf_pair_relative_strength":
            return "scripts/screen_batches/h20260928_44_etf_pair_switch.py"
        if f in ROT:
            return "scripts/screen_batches/h20260928_41_country_etf_rotation.py (rotation_cell)"
        if f in ("short_term_reversal", "short_term_etf_dip_reversion"):
            return "scripts/screen_batches/h20260929_01_dip_rejudge.py"
        if "levered" in f or "volatility" in f or "vix" in f:
            return "scripts/screen_batches/h20260929_10_vix_vrp_etp.py"
        return "scripts/screen_batches/h20260928_04_batch1.py (published long-only rule batch)"
    if eng == "book":
        col = "feature column exists in data/features/osap_price" if r.get("feature_column_exists") else "new signal column"
        return f"equity-book signal table (docs/equity-book-design.zh.md section 4; scripts/build_book_v1_alpha.py): {col}, run through the stock long/short book engine, not scripts/screen_lane.py"
    return "no lane template: new code needed (daily stock-pair/stat-arb harness on data/sip/daily)"


def cost_basis(r: dict) -> str:
    eng = r["engine"]
    if r["asset_class"] == "crypto":
        return "TBD (not frozen): Alpaca crypto maker/taker fee 15-25 bp per side at the lowest volume tier (docs snapshot 2026-10-06) plus spread; report 25 bp and 50 bp per side, excess over BIL"
    if r["asset_class"] == "options":
        return "TBD (not frozen): fill at recorded bid/ask, 2x-spread stress, per-contract fees; no frozen options cost contract exists yet"
    if r["frequency"] == "intraday":
        return "TBD (not frozen): intraday cost contract is set before the 11-02 start (docs/plan-v2-2026-10-05.zh.md 3.1: measured per-slot half-spreads, passive fills); the screen reports break-even bp per side and 1/2/5 bp rows only"
    if eng == "lane":
        return "10 bp per side primary, 20 bp stress, next-session-open fill, excess over BIL (docs/evaluation-standard.zh.md; scripts/run_h20260918_05_recent_menu.py COST_BPS_PRIMARY/STRESS; config/evaluation-standard-v2.json excess_over=BIL, recent window from 2024-01-08)"
    if eng == "book":
        return "docs/equity-book-design.zh.md section 7: NBBO-fitted half-spread (open-segment coefficients), 0.5 bp per side fees, easy-to-borrow short only with 25 bp/yr borrow (stress 100 bp/yr), plus fixed 10 bp and 20 bp reference columns; excess over BIL; V3 doubles costs"
    return "TBD: no stock stat-arb cost contract frozen; use the section 7 half-spread model and report 5 bp per side as the plan-v2 reference"


def adapter(r: dict) -> str:
    parts = []
    if r.get("adapter_note"):
        parts.append(r["adapter_note"])
    if r["data_local"] == "yes":
        parts.append("no data adapter: " + r["data_local_detail"][:120])
    elif r["data_local_detail"]:
        parts.append(r["data_local_detail"][:200])
    if r["engine"] == "book" and not r.get("feature_column_exists"):
        parts.append("compute the signal column from the listed inputs and register it in the book signal table")
    if r["engine"] == "new":
        parts.append("new harness code: " + {"intraday": "minute-bar signal and exit loop", "daily": "daily pair/residual loop", "event": "event-window loop", "monthly": "monthly loop", "weekly": "weekly loop"}.get(r["frequency"], "strategy loop"))
    return "; ".join(parts)


def main() -> None:
    pool, excluded = [], Counter()
    for r in CAT:
        ok, fails, retest = eligibility(r)
        r["_retest"] = retest
        if ok:
            pool.append(r)
        else:
            for f in fails:
                excluded[f] += 1
    pool.sort(key=sort_key)
    chosen: list[dict] = []
    fam_n, org_n, retests = Counter(), Counter(), 0

    def can_add(r: dict) -> bool:
        if r in chosen:
            return False
        if fam_n[r["family_key"]] >= FAMILY_CAP or org_n[r["origin_list"]] >= ORIGIN_CAP:
            return False
        if r["_retest"] == "yes" and retests >= RETEST_CAP:
            return False
        return len(chosen) < TARGET

    def add(r: dict, why: str) -> None:
        nonlocal retests
        chosen.append(r)
        r["_why"] = why
        fam_n[r["family_key"]] += 1
        org_n[r["origin_list"]] += 1
        if r["_retest"] == "yes":
            retests += 1

    shortfall = {}
    for b, need in BUCKET_MIN.items():
        got = 0
        for r in pool:
            if got >= need:
                break
            if bucket(r) == b and can_add(r):
                add(r, f"bucket:{b}")
                got += 1
        if got < need:
            shortfall[b] = need - got
    for r in pool:
        if len(chosen) >= TARGET:
            break
        if can_add(r):
            add(r, "global_rank")

    out = []
    for n, r in enumerate(chosen, 1):
        met = ["E1", "E2", "E3", "E4", "E5", "E6", "E7"] + [f"bucket={bucket(r)}", f"fill={r['_why']}", f"tier={tier(r)}"]
        sts = specific_statuses(r)
        item = {
            "rank": n, "id": r["id"], "name": r["name"], "family_key": r["family_key"], "origin_list": r["origin_list"],
            "asset_class": r["asset_class"], "frequency": r["frequency"], "direction": r["direction"], "engine": r["engine"],
            "rules_met": met, "evidence_tier": tier(r), "recency_year": recency(r), "complexity": r["complexity"],
            "prior_scope": r["prior_scope"], "prior_local": r["prior_local"], "retest": r["_retest"] == "yes",
            "data_adapter": adapter(r), "template": template(r), "cost_basis": cost_basis(r),
            "source": r["source"],
        }
        if r["_retest"] == "yes":
            ids = [i for i in r["prior_ids"] if i in DIRS and DIRS[i]["status"] in DENIED]
            item["retest_reason"] = (DIRS[ids[0]].get("verdict") or DIRS[ids[0]].get("claim") or "")[:200] if ids else ""
            item["retest_of"] = ids
        out.append(item)
    meta = {
        "rule_file": "reports/research/strategy-library/selection-rule.md", "pool_size": len(pool), "n_selected": len(out),
        "excluded_counts_by_condition (a row can fail several)": dict(excluded), "bucket_shortfall": shortfall,
        "retests_selected": retests, "retest_cap": RETEST_CAP, "family_cap": FAMILY_CAP, "origin_cap": ORIGIN_CAP,
    }
    json.dump({"meta": meta, "items": out}, open(HERE / "first-batch.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, indent=1))
    print(Counter(i["frequency"] for i in out), Counter(i["asset_class"] for i in out), Counter(i["origin_list"] for i in out))


if __name__ == "__main__":
    main()
