"""Exact layout/file metadata for the frozen101; no price scan or cohort selection."""

import hashlib
import json
import os
import resource
from collections import Counter

from build_finite_raw_diagnostic import OUT, ROOT


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
    path = ROOT / "data/sip/minute/_LAYOUT.json"
    layout = json.loads(path.read_text())
    rows = json.loads((OUT / "full-cohort-route/identity-candidates.json").read_text())["records"]
    result, counts = [], Counter()
    for row in rows:
        s = row["source_ticker_candidate"]
        shards = sorted(k for k, v in layout["shard_symbols"].items() if s in v)
        files = []
        for year in (2024, 2025):
            for month in range(1, 13):
                for shard in shards:
                    p = ROOT / f"data/sip/minute/{year}/{month:02d}/shard-{shard}.parquet"
                    present = p.exists()
                    files.append(
                        {
                            "path": str(p.relative_to(ROOT)),
                            "exists": present,
                            "bytes": p.stat().st_size if present else None,
                        }
                    )
        counts["roster_issues"] += 1
        counts["with_locator"] += int(bool(shards))
        counts["without_locator"] += int(not shards)
        counts["existing_file_refs_not_unique_bytes"] += sum(f["exists"] for f in files)
        result.append(
            {
                "issue_key": row["issue_key"],
                "symbol_candidate": s,
                "shards": shards,
                "exact_file_metadata": files,
                "actual_symbol_continuity_verified": False,
                "source_adjustment": "all",
                "raw_basis_from_locator": False,
                "first_episode_EMA_seed": None,
                "no_resample_no_removed_member": True,
            }
        )
    target = OUT / "full-cohort-route/cache-route-inventory.json"
    assert not target.exists()
    obj = {
        "layout": {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mixed_layout_note": layout.get("note"),
        },
        "counts": dict(counts),
        "records": result,
        "no_price_row_reads": True,
        "directory_presence_not_per_symbol_continuity": True,
        "source_firstrow_not_episode_birth": True,
        "not_all_market_absence_claim": True,
        "new_HTTP_market_requests": 0,
    }
    target.write_text(json.dumps(obj, indent=2) + "\n")
    print(json.dumps(dict(counts)))


if __name__ == "__main__":
    main()
