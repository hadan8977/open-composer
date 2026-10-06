"""Append the P-1 depth audit (audit.json) and the three external negative
results to reports/research/harvest/directions.jsonl. Append-only: the last row
per id wins in the registry, so each revision row is a full copy of the latest
row plus ``depth_audit``; no existing line is touched. Idempotent: skips ids
whose latest row already carries a depth_audit dated today."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FILE = ROOT / "reports/research/harvest/directions.jsonl"
AUDIT = Path(__file__).resolve().parent / "audit.json"
AUDIT_REL = "reports/research/program/power-reaudit-2026-10-08/audit.json"
TODAY = "2026-10-06"
SNAP = "reports/research/intel/sources/power-reaudit-2026-10-08"
REPO = "https://github.com/henryzhangpku/autonomous-quant-researcher"
FETCHED = "2026-10-06T17:07Z"
BASE = "https://raw.githubusercontent.com/henryzhangpku/autonomous-quant-researcher/HEAD"
README_SNAP = (
    "reports/research/intel/sources/vibe-wave-2026-10-04/"
    "henryzhangpku__autonomous-quant-researcher.md"
)
FOUND = ["T-20261005-35", "I-20261004-08"]

LABELS = {"未到深度": "under_depth"}


def mde_text(m) -> str:
    if not isinstance(m, dict):
        return str(m)
    if m["type"] == "sharpe":
        return (
            f"Sharpe T={m['years']}y SE={m['se']} MDE80={m['mde_80']} vs target "
            f"{m['target']} ({m['target_basis']}); one-sided 95% upper bound "
            f"{m['upper95_one_sided']}"
        )
    if m["type"] == "sharpe_edge":
        w = "; ".join(f"T={x['years']}y rho={x['rho']} MDE80={x['mde_80']}" for x in m["windows"])
        return f"Sharpe-difference vs bar {m['bar']}: {w}"
    claimed = f" vs claimed {m['claimed']}" if "claimed" in m else ""
    return f"{m['unit']}: SE={m['se']} MDE80={m['mde_80']}{claimed}"


def obs_text(m, fallback) -> str:
    if not isinstance(m, dict):
        return "see original_verdict"
    if m["type"] == "sharpe":
        return f"pooled Sharpe {m['observed_pooled']} over {m['years']}y"
    if m["type"] == "sharpe_edge":
        return "; ".join(f"edge {x['observed_edge']}" for x in m["windows"])
    return f"{m['observed']} (t {m['t']})"


def ext_rows() -> list[dict]:
    def row(id_, name, cat, fam, aliases, claim, verdict, snaps, ext, reopen, notes):
        return {
            "id": id_,
            "name": name,
            "category": cat,
            "family_key": fam,
            "status": "evidence_too_weak",
            "updated": TODAY,
            "aliases": aliases,
            "sources": [
                {
                    "url": REPO,
                    "kind": "repo",
                    "title": "henryzhangpku/autonomous-quant-researcher (1 star, MIT, one author)",
                    "accessed_at": TODAY,
                },
            ],
            "claim": claim,
            "verdict": verdict,
            "evidence": snaps,
            "reopen_if": reopen,
            "external_negative_evidence": ext,
            "notes": notes,
            "found_by": FOUND,
        }

    note = (
        "External negative evidence (I-20261004-08 section 6 item 6), registered by "
        "T-20261005-35. Not our own test: status evidence_too_weak means no local run "
        "and a one-author self-reported source; it is kept so that the same ground is "
        "not reopened without reading it. Author-reported, no third-party replication, "
        "code not audited."
    )
    return [
        row(
            "dir:ext_neg_single_rule_etf_grid_bars_rules",
            "Preregistered single-rule grid on 8 US ETFs: 232 cells, 4 discovery passers, "
            "0 promotions (author-reported)",
            "etf_rule",
            "single_rule_etf_grid",
            ["bars-rules", "single rule grid ETF", "ret_20d rule", "preregistered rule grid"],
            "A grid of single-condition daily rules on SPY QQQ IWM DIA XLF XLE XLK SMH "
            "contains a rule that survives validation.",
            "external, author-reported 2026-08-13: 232 preregistered cells, 1,240 sessions x 8 "
            "ETFs (2021-08-31..2026-08-10), discovery 2021-08-31..2024-08-15; 4 discovery "
            "passers, all ret_20d long-after-decline and long-after-advance (the long side, not "
            "the rule); validation 2024-08-16..2025-08-13: +18.87 bps/trade but -12.22 "
            "bps/session (Sharpe -0.86); all failed 4 gates; holdout never opened. The "
            "per-trade number is a clustering artifact (the condition fires on all 8 symbols the "
            "same day).",
            [f"{SNAP}/bars-rules_FINDINGS.md", README_SNAP],
            [
                {
                    "url": f"{BASE}/research/missions/bars-rules/FINDINGS.md",
                    "snapshot_path": f"{SNAP}/bars-rules_FINDINGS.md",
                    "fetched_at": FETCHED,
                    "author_reported_result": "232 cells, 4 discovery passers, 0 promotions; "
                    "validation Sharpe -0.86 for the leader; passers are one feature in both "
                    "directions (long beta)",
                    "caveats": "one discovery regime with strong long drift; single-condition "
                    "rules only; 5 bps assumed not measured; daily close decision only; "
                    "self-reported, no third-party replication",
                }
            ],
            "before any single-rule ETF grid is reopened: the discovery window must contain "
            "both market directions and the rule must be tested against its mirrored condition "
            "(the author's own check); a rule that passes in both directions is the long side.",
            note,
        ),
        row(
            "dir:ext_neg_tradingview_ta_premises_fib_channel_ribbon",
            "Premises under popular TradingView trend scripts (Fibonacci, regression channel, "
            "MA ribbon, support recency): all failed validation (author-reported)",
            "other",
            "tradingview_ta_premises",
            [
                "Fibonacci retracement",
                "regression channel",
                "moving average ribbon",
                "support recency",
                "TradingView trend script premises",
            ],
            "Fibonacci retracement levels, regression-channel position, MA ribbons and "
            "support-zone recency carry tradable information on daily US stocks and ETFs.",
            "external, author-reported 2026-08-23: 12 tickers (SPY QQQ IWM NVDA AAPL MSFT AMZN "
            "GOOGL META TSLA AVGO IBIT), 2019-04-01..2026-08-19, 21,019 rows, 5 bps/trade, "
            "rules frozen before data staged; validation bps/session net: Fibonacci -30.10, "
            "regression channel -22.32 (+16.26 and all nine gates in discovery), MA ribbon "
            "-7.14, support recency -11.08, always-long baseline -3.11; every premise worse than "
            "being long; holdout deliberately unopened.",
            [f"{SNAP}/ta-premises_RESULTS.md", README_SNAP],
            [
                {
                    "url": f"{BASE}/research/missions/ta-premises/RESULTS.md",
                    "snapshot_path": f"{SNAP}/ta-premises_RESULTS.md",
                    "fetched_at": FETCHED,
                    "author_reported_result": "no premise supported; the regression channel "
                    "passed 9/9 discovery gates (+16.26 bps) then lost -22.32 bps in validation",
                    "caveats": "daily close decision, next-open-to-close payoff; one "
                    "universe; author corrected one reported figure (profile persistence "
                    "r -0.055 -> +0.179) in the same file; self-reported, no third-party "
                    "replication",
                }
            ],
            "a preregistered test on the unread holdout (2025-02-26..2026-08-19) by the "
            "original author, or our own preregistered test with a different decision/payoff "
            "contract; do not reopen on the same daily next-open-to-close contract.",
            note,
        ),
        row(
            "dir:ext_neg_overnight_spx_put_credit_premium",
            "Overnight SPX put-credit vertical premium: 40 trials, no candidate passed "
            "discovery (author-reported)",
            "options",
            "overnight_spx_put_credit",
            ["overnight SPX", "overnight put credit spread", "ES overnight options premium"],
            "There is an overnight premium in SPX put-credit verticals that clears realistic "
            "costs.",
            "external, author-reported 2026-08-13: 482 stitched ES overnight sessions "
            "2024-09-03..2026-08-12, 40 scientific trials, 9 admission failures, local "
            "Qwen2.5-Coder-7B proposer; no candidate passed discovery, validation sealed. The "
            "premium is real but thin and time-localized (control net +0.004..+0.014 of width at "
            "00:00 ET) and dies at the doubled-cost gate (needs >= +0.05 width; best observed "
            "about +0.014); high-net conditioned trials won in both directions and are read as a "
            "pricing-model artifact. A later holdout on the structure vanished (+4.4%/+6.7% of "
            "width per session to +0.15%) but the author calls it UNDERPOWERED (7 weeks, 30 "
            "trades), not proof of absence.",
            [f"{SNAP}/overnight-spx_FINDINGS.md", README_SNAP],
            [
                {
                    "url": f"{BASE}/research/missions/overnight-spx/FINDINGS.md",
                    "snapshot_path": f"{SNAP}/overnight-spx_FINDINGS.md",
                    "fetched_at": FETCHED,
                    "author_reported_result": "no candidate passed discovery; premium inside "
                    "execution noise at modeled overnight SPX spread costs",
                    "caveats": "ES proxies SPX, basis not modeled; Black-Scholes marks with "
                    "vrp_mult 1.10 and no overnight quote tape; history from 2024-09 only (no "
                    "bear year); conditions fire on about 25 of 287 sessions, below the 60-trade "
                    "floor; the author's own holdout rejection is labelled underpowered; "
                    "self-reported, no third-party replication",
                }
            ],
            "a real overnight option-quote capture (not Black-Scholes marks) over a window that "
            "includes a volatility shock, with measured spreads; the 2024-09+ ES-proxy sample "
            "alone cannot settle it.",
            note,
        ),
    ]


def main() -> None:
    latest: dict[str, dict] = {}
    for line in FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["id"]] = r
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    out: list[str] = []
    for e in audit["entries"]:
        base = latest[e["id"]]
        da = base.get("depth_audit")
        if da and da.get("audited_at") == TODAY:
            continue
        if e["p1_not_applicable"]:
            label = "p1_not_applicable"
        elif e["p1_met"]:
            label = "p1_met"
        else:
            label = "under_depth"
        row = dict(base)
        row["updated"] = TODAY
        row["depth_audit"] = {
            "audited_at": TODAY,
            "label": label,
            "p1": e["p1_conditions"],
            "original_verdict": e["original_verdict"],
            "min_detectable_effect": mde_text(e["min_detectable_effect"]),
            "observed": obs_text(e["min_detectable_effect"], e["observed"]),
            "missing_depth_points": e["missing_depth_points"],
            "audit_file": AUDIT_REL,
            "new_label": e["new_label"],
            "gap_class": e["gap_class"],
            "what_is_missing_specifically": e["what_is_missing_specifically"],
            "reopen_candidate_pending_lead_review": e["reopen_candidate_pending_lead_review"],
        }
        out.append(json.dumps(row, ensure_ascii=False))
    for r in ext_rows():
        if r["id"] not in latest:
            out.append(json.dumps(r, ensure_ascii=False))
    text = FILE.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    FILE.write_text(text + "".join(x + "\n" for x in out), encoding="utf-8")
    print(f"appended {len(out)} rows")


if __name__ == "__main__":
    main()
