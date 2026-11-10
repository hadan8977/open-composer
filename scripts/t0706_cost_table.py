# ruff: noqa: E501
"""T-20261007-06: aggregate the NBBO quote sample into cost_table_raw.json (per-symbol and per-bucket
median half spreads by snapshot time). Run after scripts/t0706_quote_sample.py has finished."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/t0706_quotes"


def main() -> int:
    parts = [pd.read_parquet(p) for p in sorted((OUT / "result").glob("*.parquet"))]
    d = pd.concat(parts, ignore_index=True)
    ok = d[np.isfinite(d["hs_bp"]) & (d["hs_bp"] > 0) & (d["hs_bp"] < 500)]
    uniq = ok.drop_duplicates(["day", "symbol", "t"])
    per_symbol = {}
    for (s, t), g in uniq.groupby(["symbol", "t"]):
        per_symbol.setdefault(s, {})[t] = {
            "med": round(float(g["hs_bp"].median()), 4),
            "n": int(len(g)),
        }
    bucket = {}
    for (b, t), g in ok.groupby(["bucket", "t"]):
        bucket.setdefault(b, {})[t] = {
            "med": round(float(g["hs_bp"].median()), 4),
            "n": int(len(g)),
            "mean": round(float(g["hs_bp"].mean()), 4),
        }
    top = bucket.get("top20", {})
    base = top.get("1200", {}).get("med", float("nan")) + 0.5
    summary = {
        "base_cost_bps": round(base, 3),
        "stress_cost_bps": round(2 * base, 3),
        "note": "base = top-20 12:00 median half spread + 0.5 bp slippage, per side; stress = x2",
    }
    sample = {
        "days": int(d["day"].nunique()),
        "symbols": int(d["symbol"].nunique()),
        "rows_valid": int(len(ok)),
        "rows_total": int(len(d)),
    }
    (OUT / "cost_table_raw.json").write_text(
        json.dumps(
            {"sample": sample, "summary": summary, "per_symbol": per_symbol, "bucket": bucket},
            indent=1,
        )
    )
    print(
        json.dumps(
            {
                "sample": sample,
                "summary": summary,
                "bucket": {b: {t: v["med"] for t, v in x.items()} for b, x in bucket.items()},
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
