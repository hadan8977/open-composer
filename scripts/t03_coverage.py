# ruff: noqa: E501
"""T-20261007-03: coverage report of the link table + stratified 50-row audit sample."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "features" / "economic_links"


def main() -> int:
    idx = pd.read_parquet(ROOT / "data/features/text_similarity/filings_index.parquet")
    idx["year"] = pd.to_datetime(idx["filing_date"]).dt.year
    snips = {}
    for f in sorted((D / "_snippets").glob("part_main_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                snips[r["accession"]] = r
    links = pd.read_parquet(D / "links.parquet")
    links["year"] = pd.to_datetime(links["filing_date"]).dt.year
    sn = pd.DataFrame(
        [
            {"accession": a, "status": r["status"], "has_snip": bool(r["snippets"])}
            for a, r in snips.items()
        ]
    )
    idx = idx.merge(sn, on="accession", how="left")
    comp = links[links["customer_type"] == "company"]
    rows = []
    for y, g in idx.groupby("year"):
        L = links[links["year"] == y]
        C = comp[comp["year"] == y]
        rows.append(
            {
                "year": int(y),
                "filings_indexed": len(g),
                "filings_fetched": int(g["status"].notna().sum()),
                "fetch_ok": int((g["status"] == "ok").sum()),
                "with_snippets": int(g["has_snip"].fillna(False).sum()),
                "llm_extracted_filings": int(L["accession"].nunique()),
                "suppliers_with_named_customer": int(C["supplier_cik"].nunique()),
                "link_rows_company": len(C),
                "link_rows_government": int((L["customer_type"] == "government").sum()),
                "link_rows_anonymous": int((L["customer_type"] == "anonymous").sum()),
                "link_rows_group": int((L["customer_type"] == "group").sum()),
                "company_matched": int(C["customer_cik"].notna().sum()),
                "match_rate": float(C["customer_cik"].notna().mean()) if len(C) else None,
                "with_pct": int(C["pct"].notna().sum()),
            }
        )
    cov = pd.DataFrame(rows)
    # quote faithfulness: the quote is a fragment of the supplier's snippets
    ok = tot = 0
    for _, r in comp.iterrows():
        q = (r["quote"] or "").strip()
        s = snips.get(r["accession"])
        if not q or not s:
            continue
        tot += 1
        flat = " ".join(s["snippets"])
        ok += q[:80] in flat
    out = {
        "by_year": rows,
        "quote_in_source_rate": ok / tot if tot else None,
        "quote_checked": tot,
        "match_methods": comp["match_method"].value_counts().to_dict(),
    }
    (D / "coverage.json").write_text(json.dumps(out, indent=1))
    print(cov.to_string(index=False))
    print({k: v for k, v in out.items() if k != "by_year"})
    # audit sample: 50 company rows, 35 matched + 15 unmatched
    m = comp[comp["customer_cik"].notna()].sample(
        min(35, int(comp["customer_cik"].notna().sum())), random_state=20261007
    )
    u = comp[comp["customer_cik"].isna()].sample(
        min(15, int(comp["customer_cik"].isna().sum())), random_state=20261007
    )
    aud = []
    for _, r in pd.concat([m, u]).iterrows():
        s = snips.get(r["accession"], {"snippets": []})
        aud.append(
            {
                "accession": r["accession"],
                "supplier_cik": int(r["supplier_cik"]),
                "customer_name": r["customer_name"],
                "pct": r["pct"],
                "fiscal_year": r["fiscal_year"],
                "customer_cik": None if pd.isna(r["customer_cik"]) else int(r["customer_cik"]),
                "customer_symbols": r["customer_symbols"],
                "match_method": r["match_method"],
                "quote": r["quote"],
                "source_snippet": " // ".join(s["snippets"])[:1500],
            }
        )
    (D / "audit_sample.json").write_text(json.dumps(aud, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
