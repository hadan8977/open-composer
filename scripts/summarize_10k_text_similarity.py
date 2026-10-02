#!/usr/bin/env python3
"""Acceptance numbers for the 10-K text-similarity data (T-20261002-03).

Reads ``10k_filings.parquet``, ``10k_pairs.parquet``, ``_manifest.json`` and
``_progress.json`` from the data directory and writes ``summary.json`` and
``report.md``. Computes no returns and no IC.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "features" / "text_similarity"
OUT = ROOT / "reports" / "research" / "program" / "text-similarity-2026-10-02"
QS = [0.05, 0.25, 0.5, 0.75, 0.95]


def quantiles(s: pd.Series) -> dict[str, float | int]:
    s = s.dropna()
    out: dict[str, float | int] = {"n": int(len(s))}
    for q in QS:
        out[f"p{int(q * 100):02d}"] = float(s.quantile(q)) if len(s) else float("nan")
    return out


def summarize(data: Path, extra_snippets: list[Path]) -> dict:
    filings = pd.read_parquet(data / "10k_filings.parquet")
    pairs = pd.read_parquet(data / "10k_pairs.parquet")
    manifest = json.loads((data / "_manifest.json").read_text())
    progress = json.loads((data / "_progress.json").read_text())
    all_ciks = json.loads((data / "ciks.json").read_text())
    index = pd.read_parquet(data / "filings_index.parquet", columns=["cik"])
    n_ciks_with_filings = int(index["cik"].nunique())
    n_fetch_fail = int((filings["fetch_status"] != "ok").sum())
    fetched = filings[filings["fetch_status"] == "ok"]
    n_parse_fail = int((fetched["parse_status"] != "ok").sum())
    post = filings[(filings["filing_date"] >= "2016-01-01") & (filings["fetch_status"] == "ok")]
    vis = pairs.dropna(subset=["visible_day"])
    early = vis[vis["visible_day"] < vis["filing_date"] - pd.Timedelta(days=1)]
    late_null = pairs[pairs["visible_day"].isna() & (pairs["filing_date"] >= "2016-01-01")]
    snippets = []
    for path in extra_snippets:
        if path.exists():
            snippets.extend(json.loads(path.read_text()))
    n_done = len(progress.get("completed_ciks", []))
    pairs_per_year = pairs.groupby(pairs["filing_date"].dt.year).size()
    summary = {
        "status_note": "pending lead review; data step only, no returns or IC computed",
        "ciks_in_universe": len(all_ciks),
        "ciks_with_10k_in_index": n_ciks_with_filings,
        "ciks_completed": n_done,
        "filings_in_index": int(len(index)),
        "filings_processed": int(len(filings)),
        "pairs": int(len(pairs)),
        "pairs_over_filings": float(len(pairs) / len(filings)) if len(filings) else float("nan"),
        "fetch_fail_rate": n_fetch_fail / len(filings) if len(filings) else float("nan"),
        "parse_fail_rate": n_parse_fail / len(fetched) if len(fetched) else float("nan"),
        "fetch_status_counts": manifest["fetch_status_counts"],
        "parse_status_counts": manifest["parse_status_counts"],
        "filings_2016_plus": int(len(post)),
        "rf_found_2016_plus": float(post["rf_found"].mean()),
        "mda_found_2016_plus": float(post["mda_found"].mean()),
        "pairs_by_year": {int(k): int(v) for k, v in pairs_per_year.items()},
        "cos": {c: quantiles(pairs[f"cos_{c}"]) for c in ("full", "rf", "mda")},
        "jac": {c: quantiles(pairs[f"jac_{c}"]) for c in ("full", "rf", "mda")},
        "gap_days": {
            **quantiles(pairs["gap_days"]),
            "min": float(pairs["gap_days"].min()),
            "max": float(pairs["gap_days"].max()),
        },
        "visible_day_earlier_than_filing_minus_1d": int(len(early)),
        "pairs_visible_day_null_2016_plus": int(len(late_null)),
        "requests": manifest.get("requests"),
        "elapsed_seconds": manifest.get("elapsed_seconds"),
        "git_hash": manifest.get("git_hash"),
        "snippets": snippets,
    }
    crit = {
        "fetch_fail_rate<=0.03": summary["fetch_fail_rate"] <= 0.03,
        "parse_fail_rate<=0.03": summary["parse_fail_rate"] <= 0.03,
        "mda_found_2016_plus>=0.90": summary["mda_found_2016_plus"] >= 0.90,
        "rf_found_2016_plus>=0.80": summary["rf_found_2016_plus"] >= 0.80,
        "pairs_over_filings>=0.70": summary["pairs_over_filings"] >= 0.70,
        "cos_full_median_in_[0.80,0.999]": 0.80 <= summary["cos"]["full"]["p50"] <= 0.999,
        "no_early_visible_day": len(early) == 0,
    }
    summary["criteria_on_processed_subset"] = crit
    summary["complete"] = n_done >= n_ciks_with_filings
    return summary


def render(s: dict) -> str:
    def q(d: dict) -> str:
        return (
            " / ".join(f"{d[k]:.4f}" for k in ("p05", "p25", "p50", "p75", "p95"))
            + f" (n={d['n']})"
        )

    lines = [
        "# 10-K text similarity data (T-20261002-03)",
        "",
        f"Status: {'complete' if s['complete'] else 'PARTIAL'}; pending lead review. "
        "Data step only: no returns, IC or group performance computed.",
        "",
        f"- CIKs in universe {s['ciks_in_universe']}, with a 10-K in the index "
        f"{s['ciks_with_10k_in_index']}, completed {s['ciks_completed']}.",
        f"- Filings in index {s['filings_in_index']}, processed {s['filings_processed']}, "
        f"pairs {s['pairs']} ({s['pairs_over_filings']:.3f} of processed filings).",
        f"- fetch fail rate {s['fetch_fail_rate']:.4f} {s['fetch_status_counts']}; "
        f"parse fail rate {s['parse_fail_rate']:.4f} {s['parse_status_counts']}.",
        f"- Filed 2016+ ({s['filings_2016_plus']} filings): "
        f"rf_found {s['rf_found_2016_plus']:.3f}, "
        f"mda_found {s['mda_found_2016_plus']:.3f}.",
        f"- Pairs by year: {s['pairs_by_year']}.",
        f"- Requests {s['requests']}, elapsed {s['elapsed_seconds']:.0f} s, "
        f"code {s['git_hash'][:10]}.",
        "",
        "## Quantiles (5/25/50/75/95)",
        "",
    ]
    for kind in ("cos", "jac"):
        for sec in ("full", "rf", "mda"):
            lines.append(f"- {kind}_{sec}: {q(s[kind][sec])}")
    g = s["gap_days"]
    lines += [
        f"- gap_days: {q(g)}, min {g['min']:.0f}, max {g['max']:.0f}",
        "",
        "## Mechanical criteria on the processed subset",
        "",
    ]
    lines += [
        f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in s["criteria_on_processed_subset"].items()
    ]
    lines += [
        f"- visible_day earlier than filing_date-1d: "
        f"{s['visible_day_earlier_than_filing_minus_1d']} pairs; "
        f"null visible_day among 2016+ pairs: {s['pairs_visible_day_null_2016_plus']}",
        "",
        "## Section-boundary spot checks (first / last 200 characters)",
        "",
    ]
    for sn in s["snippets"]:
        lines.append(f"### cik {sn['cik']} {sn['accession']}")
        for key in ("rf", "mda"):
            lines.append(f"- {key} start: {sn[key][0]}")
            lines.append(f"- {key} end: {sn[key][1]}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DATA))
    parser.add_argument("--out-dir", default=str(OUT))
    parser.add_argument("--snippets", nargs="*", default=[])
    args = parser.parse_args()
    summary = summarize(Path(args.data_dir), [Path(p) for p in args.snippets])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    (out / "report.md").write_text(render(summary))
    print(json.dumps(summary["criteria_on_processed_subset"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
