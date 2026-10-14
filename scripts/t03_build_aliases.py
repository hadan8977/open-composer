# ruff: noqa: E501
#!/usr/bin/env python3
"""T-20261007-03: alias table (normalised company name -> cik) from sic_map + SEC former names."""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|ltd|limited|llc|lp|l p|plc|holdings?|"
    r"the|de|nv|sa|ag|se|new|common stock|class [a-z])\b"
)


def norm(name: str) -> str:
    s = name.lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    prev = None
    while prev != s:
        prev = s
        s = SUFFIX.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip()
    return s


def main() -> int:
    sic = pd.read_parquet(ROOT / "data/features/sic_map/sic_map.parquet")
    ciks = sorted(set(sic["cik"].astype(int)))
    z = zipfile.ZipFile(ROOT / "data/raw/sec_submissions/submissions.zip")
    rows = []
    for c in ciks:
        try:
            d = json.loads(z.read(f"CIK{c:010d}.json"))
        except KeyError:
            continue
        names = {d.get("name", "")}
        names |= {f["name"] for f in d.get("formerNames", [])}
        for n in names:
            if n and norm(n):
                rows.append({"cik": c, "alias": norm(n), "raw": n, "current": n == d.get("name")})
    # entity_name from sic_map too
    for _, r in sic.drop_duplicates("cik").iterrows():
        if isinstance(r["entity_name"], str) and norm(r["entity_name"]):
            rows.append(
                {
                    "cik": int(r["cik"]),
                    "alias": norm(r["entity_name"]),
                    "raw": r["entity_name"],
                    "current": True,
                }
            )
    out = pd.DataFrame(rows).drop_duplicates(["cik", "alias"])
    out.to_parquet(ROOT / "data/features/economic_links/aliases.parquet", index=False)
    print(
        len(out),
        out["cik"].nunique(),
        "alias dup keys:",
        out.groupby("alias")["cik"].nunique().gt(1).sum(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
