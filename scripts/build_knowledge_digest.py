"""Build the deterministic part of the knowledge digest (Step 18, plan B round 0).

Reads the experiment ledger and the harness source cards and writes compact,
citable entries (<= 300 chars each) that the research loop can read cheaply:

    reports/research/knowledge/digest/experiments.jsonl
    reports/research/knowledge/digest/literature.jsonl
    reports/research/knowledge/digest/index.json

Decision records are digested separately (LLM summarization) into
``decisions.jsonl``; this script never touches that file.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = ROOT / "reports" / "research" / "knowledge" / "digest"
LEDGER = ROOT / "reports" / "research" / "ledger" / "experiments.jsonl"
SOURCE_CARD_DIRS = [ROOT / "reports" / "harness" / "source_cards"]

TIER_RULES = [
    (
        1,
        r"insider|form 4|form-4|10b5|options?\b|implied vol|put[- ]call|skew|analyst|"
        r"earnings call|conference call|news|sentiment|headline|reddit|social|attention|"
        r"13f|short interest|days[- ]to[- ]cover",
    ),
    (
        3,
        r"\brsi\b|\bmacd\b|bollinger|\bema\b|\bsma\b crossover|stochastic|"
        r"technical indicator|reversal trend|pine",
    ),
    (
        2,
        r"momentum|reversal|volatility|overnight|intraday|liquidity|kyle|volume|adv\b|beta|residual|"
        r"factor|alpha158|alpha101|alpha191|gtja|osap|ohlcv|price[- ]volume",
    ),
]


def _tier(text: str) -> int | None:
    low = text.lower()
    for tier, pattern in TIER_RULES:
        if re.search(pattern, low):
            return tier
    return None


def _pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _clip(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_experiments() -> list[dict]:
    rows = [
        json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    out: list[dict] = []
    for r in rows:
        m = r.get("metrics") or {}
        g = r.get("gate_results") or {}
        applicable = [k for k in g if k not in set(r.get("gates_not_applicable") or [])]
        passed = sum(1 for k in applicable if g.get(k))
        feature_set = str(r.get("feature_set") or "")
        text_for_tier = " ".join(
            [str(r.get("experiment_id")), feature_set, str(r.get("mechanism") or "")]
        )
        tier = _tier(text_for_tier) or 2
        is_ml = bool(r.get("is_ml"))
        layer = (
            "timing"
            if (r.get("trend_gate") and not is_ml and "gate_on" in str(r.get("experiment_id")))
            else "selection"
        )
        dsr = m.get("dsr_probability")
        dsr_text = "n/a" if dsr is None else f"{float(dsr):.3f}"
        kind = "ML" if is_ml else "Rule"
        claim = (
            f"{kind} cell {r.get('experiment_id')} ({r.get('model_kind')}): "
            f"recent CAGR {_pct(m.get('cagr_recent_net'))}, "
            f"vol-matched SPY excess {_pct(m.get('cagr_excess_vol_matched_spy'))}, "
            f"MDD {_pct(m.get('max_drawdown_recent'))}, DSR p={dsr_text}; "
            f"gates {passed}/{len(applicable)}; all_pass={bool(r.get('all_gates_pass'))}"
        )
        if is_ml and m.get("rule_baseline_cagr_recent_net") is not None:
            claim += f"; rule twin CAGR {_pct(m.get('rule_baseline_cagr_recent_net'))}"
        out.append(
            {
                "id": f"exp:{r.get('experiment_id')}",
                "kind": "experiment",
                "family": r.get("family"),
                "claim": _clip(claim),
                "evidence": {
                    k: m.get(k)
                    for k in (
                        "cagr_recent_net",
                        "cagr_excess_vol_matched_spy",
                        "max_drawdown_recent",
                        "sharpe_excess_bil_recent",
                        "hit_rate_weekly",
                        "dsr_probability",
                        "ml_placebo_rank_ic_abs",
                        "rule_baseline_cagr_recent_net",
                        "recent_window_start",
                        "recent_window_end",
                    )
                    if k in m
                },
                "gates_passed": passed,
                "gates_applicable": len(applicable),
                "status": "gate_pass" if r.get("all_gates_pass") else "gate_fail",
                "layer": layer,
                "tier": tier,
                "is_ml": is_ml,
                "dsr_trial_count": r.get("dsr_trial_count"),
                "config": {
                    k: r.get(k)
                    for k in (
                        "model_kind",
                        "universe_top_n",
                        "train_window_months",
                        "refit_frequency",
                        "mechanism",
                        "cell",
                        "hyperparameters",
                    )
                    if r.get(k) is not None
                },
                "source": f"reports/research/ledger/experiments.jsonl#{r.get('experiment_id')}",
                "updated": str(r.get("recorded_at") or "")[:10] or None,
            }
        )
    return out


def build_literature() -> list[dict]:
    today = datetime.now(UTC).date().isoformat()
    latest: dict[str, dict] = {}
    for directory in SOURCE_CARD_DIRS:
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = str(card.get("claim_id") or "").strip()
                if not cid:
                    continue
                stamp = str(card.get("verified_at") or card.get("accessed_at") or "")
                prev = latest.get(cid)
                if prev is None or stamp >= str(prev.get("_stamp") or ""):
                    card["_stamp"] = stamp
                    card["_path"] = path.relative_to(ROOT).as_posix()
                    latest[cid] = card
    out: list[dict] = []
    for cid, card in sorted(latest.items()):
        verification = str(card.get("verification_status") or "unverified")
        expires = str(card.get("expires_at") or "")[:10]
        status = verification
        if expires and expires < today:
            status = f"{verification}_expired"
        claim = str(card.get("claim") or "")
        out.append(
            {
                "id": f"lit:{cid}",
                "kind": "literature",
                "claim": _clip(claim),
                "evidence": {
                    "source_type": card.get("source_type"),
                    "applies_to": _clip(str(card.get("applies_to") or ""), 160),
                    "impact_on_spec": _clip(str(card.get("impact_on_spec") or ""), 200),
                    "limitations": _clip(str(card.get("limitations") or ""), 200),
                },
                "status": status,
                "tier": _tier(claim + " " + str(card.get("applies_to") or "")),
                "verification_method": card.get("verification_method"),
                "iteration_id": card.get("iteration_id"),
                "source": card.get("source_url"),
                "card_path": card["_path"],
                "updated": str(card.get("_stamp") or "")[:10] or None,
                "expires_at": expires or None,
            }
        )
    return out


def main() -> None:
    DIGEST.mkdir(parents=True, exist_ok=True)
    experiments = build_experiments()
    literature = build_literature()
    (DIGEST / "experiments.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in experiments), encoding="utf-8"
    )
    (DIGEST / "literature.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in literature), encoding="utf-8"
    )
    decisions_path = DIGEST / "decisions.jsonl"
    n_dec = (
        sum(1 for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if decisions_path.is_file()
        else 0
    )
    index = {
        "generated_at": datetime.now(UTC).isoformat(),
        "schema": (
            "digest.v1 (id, kind, claim<=300 chars, evidence, status, tier, layer, source, updated)"
        ),
        "counts": {
            "experiments": len(experiments),
            "literature": len(literature),
            "decisions": n_dec,
            "experiments_by_status": dict(Counter(e["status"] for e in experiments)),
            "experiments_by_tier": dict(Counter(str(e["tier"]) for e in experiments)),
            "literature_by_status": dict(Counter(e["status"] for e in literature)),
            "literature_by_tier": dict(Counter(str(e["tier"]) for e in literature)),
        },
        "files": ["experiments.jsonl", "literature.jsonl", "decisions.jsonl"],
        "bytes": {p.name: p.stat().st_size for p in DIGEST.glob("*.jsonl")},
    }
    (DIGEST / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(index["counts"], ensure_ascii=False, indent=1))
    print("bytes", index["bytes"])


if __name__ == "__main__":
    main()
