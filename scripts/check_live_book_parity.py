"""Book-level parity of the v1.2 targets: live equity-book root against the frozen research data.

T-20261001-22 lead review (2026-10-04).  The row-level parity of ``check_live_parity.py`` fails with
every difference attributed (restated symbols re-based by the vendor, the snapshot's own intra-year
fallback-mcap look-ahead, late SEC filings).  What the paper book needs to know is whether those
differences move the traded weights.  For each decision date this builds the M0 (primary variant)
F1/F2 targets from both roots with ``build_v12_bundle`` (nothing is written) and compares the stock
weights.

Decision rule (written before the first run): STOP the paper start if any date/form has a weight
correlation below 0.90 or a target-gross difference above 10 %; CLEAN if every correlation is at
least 0.97; otherwise PROCEED with a recorded caveat.  The snapshot's own one-week change (D against
D - 5 sessions) is reported as the scale of ordinary book turnover.

Usage: ``scripts/run_capped.sh --mem 1.8G -- uv run python scripts/check_live_book_parity.py``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.book_paper import v12_targets as v12  # noqa: E402

SNAPSHOT = ROOT / "data/research/equity_book"
LIVE = ROOT / "data/live/equity_book"
RESTATED = ROOT / "data/features/_t02_stage/vendor_revision_symbols.txt"
OUT = ROOT / "reports/research/program/data-refresh-2026-10-01/live-book-parity.json"
DATES = ("2026-06-30", "2026-07-31", "2026-08-21", "2026-09-01", "2026-09-17")
STOP_CORR, CLEAN_CORR, STOP_GROSS = 0.90, 0.97, 0.10


def compare(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    names = sorted(set(a) | set(b))
    x = np.array([a.get(s, 0.0) for s in names])
    y = np.array([b.get(s, 0.0) for s in names])
    ga, gb = float(np.abs(x).sum()), float(np.abs(y).sum())
    d = np.abs(x - y)
    return {
        "n_a": len(a),
        "n_b": len(b),
        "n_common": len(set(a) & set(b)),
        "corr": float(np.corrcoef(x, y)[0, 1]) if len(names) > 1 else float("nan"),
        "one_way": float(0.5 * d.sum()),
        "rel_distance": float(d.sum() / (ga + gb)) if ga + gb > 0 else 0.0,
        "gross_a": ga,
        "gross_b": gb,
        "gross_rel_diff": abs(ga - gb) / gb if gb > 0 else float("nan"),
    }


def fallback_names(day: pd.Timestamp) -> set[str]:
    df = pd.read_parquet(
        SNAPSHOT / f"panel/{day.year}.parquet",
        columns=["trade_date", "symbol", "mcap_source"],
        filters=[("trade_date", "==", day)],
    )
    return set(df.loc[df["mcap_source"].astype(str).str.startswith("adv_fallback"), "symbol"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dates", nargs="*", default=list(DATES))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    t0 = time.time()
    variant = v12.primary_variant()
    days = [pd.Timestamp(d) for d in args.dates]
    restated = set(RESTATED.read_text().split()) if RESTATED.exists() else set()
    ctx = {
        name: v12.V12Context.open(
            root, first_date=min(days) - pd.Timedelta(days=14), last_date=max(days)
        )
        for name, root in (("snapshot", SNAPSHOT), ("live", LIVE))
    }
    rows = []
    for day in days:
        books = {
            name: v12.build_v12_bundle(day, variant=variant, context=c, logged_at_utc="check")
            for name, c in ctx.items()
        }
        p = int(ctx["snapshot"].px.dates.get_loc(day))
        week_ago = ctx["snapshot"].px.dates[p - 5]
        prev = v12.build_v12_bundle(
            week_ago, variant=variant, context=ctx["snapshot"], logged_at_utc="check"
        )
        fb = fallback_names(day)
        for account in sorted(books["live"].targets):
            live = books["live"].targets[account].stock_weights
            snap = books["snapshot"].targets[account].stock_weights
            cmp = compare(live, snap)
            names = set(live) | set(snap)
            diff = {s: abs(live.get(s, 0.0) - snap.get(s, 0.0)) for s in names}
            total = sum(diff.values()) or 1.0
            top = sorted(diff.items(), key=lambda kv: -kv[1])[:10]
            rows.append(
                {
                    "decision_date": day.date().isoformat(),
                    "account": account,
                    "form": books["live"].targets[account].form,
                    **{k: round(v, 6) for k, v in cmp.items()},
                    "share_of_diff_restated": round(
                        sum(v for s, v in diff.items() if s in restated) / total, 4
                    ),
                    "share_of_diff_fallback_mcap": round(
                        sum(v for s, v in diff.items() if s in fb and s not in restated) / total, 4
                    ),
                    "top_diff": [
                        {
                            "symbol": s,
                            "live": round(live.get(s, 0.0), 6),
                            "snapshot": round(snap.get(s, 0.0), 6),
                            "restated": s in restated,
                            "fallback_mcap": s in fb,
                        }
                        for s, _ in top
                    ],
                    "snapshot_week_change": {
                        k: round(v, 6)
                        for k, v in compare(snap, prev.targets[account].stock_weights).items()
                        if k in ("corr", "one_way", "rel_distance")
                    },
                }
            )
            print(
                f"{day.date()} {account}: corr {cmp['corr']:.4f} one-way {cmp['one_way']:.4f} "
                f"gross {cmp['gross_a']:.3f}/{cmp['gross_b']:.3f}",
                flush=True,
            )
    worst = min(r["corr"] for r in rows)
    gross_worst = max(r["gross_rel_diff"] for r in rows)
    if worst < STOP_CORR or gross_worst > STOP_GROSS:
        verdict = "stop"
    elif worst >= CLEAN_CORR:
        verdict = "clean"
    else:
        verdict = "proceed_with_caveat"
    out = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "variant": variant,
        "rule": {
            "stop_if_corr_below": STOP_CORR,
            "stop_if_gross_rel_diff_above": STOP_GROSS,
            "clean_if_all_corr_at_least": CLEAN_CORR,
        },
        "verdict": verdict,
        "min_corr": round(worst, 6),
        "max_gross_rel_diff": round(gross_worst, 6),
        "n_restated_symbols": len(restated),
        "rows": rows,
        "seconds": round(time.time() - t0, 1),
    }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"verdict {verdict}: min corr {worst:.4f}, max gross diff {gross_worst:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
