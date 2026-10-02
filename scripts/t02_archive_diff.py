"""Row-level difference between the pre-swap and the repaired SIP daily archive.

T-20261002-02. For every symbol that ``_restatements.jsonl`` lists as restated this
writes (a) the (symbol, date) rows present on one side only and (b) the classified
return events (date_set / bar_correction / factor_revision / unexplained) using the
T-01 verifier's own classifier, so the vendor-revision symbol list and the origin of
the verifier's "1100 missing / 1475 added" rows are on file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_sip_repair as v  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=Path("data/sip/daily"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    restated = {r["symbol"] for r in v.read_restatements(args.after / "_restatements.jsonl")}
    names = sorted({p.name for p in args.after.glob("*/shard-*.parquet")})
    empty = pd.DataFrame(columns=v.COLUMNS)
    one_sided: list[dict] = []
    events: list[dict] = []
    for position, name in enumerate(names):
        bg = dict(tuple(v.load_shard(args.before, name).groupby("symbol")))
        ag = dict(tuple(v.load_shard(args.after, name).groupby("symbol")))
        for symbol in sorted(set(bg) | set(ag)):
            if symbol not in restated:
                continue
            b = bg.get(symbol, empty)
            a = ag.get(symbol, empty)
            stats = v.compare_symbol_precision(b, a)
            b_dates = set(b["timestamp"])
            a_dates = set(a["timestamp"])
            for ts in sorted(b_dates - a_dates):
                one_sided.append({"symbol": symbol, "date": str(ts)[:10], "side": "only_old"})
            for ts in sorted(a_dates - b_dates):
                one_sided.append({"symbol": symbol, "date": str(ts)[:10], "side": "only_new"})
            for event in stats["events"]:
                events.append({"symbol": symbol, **event})
        if position % 40 == 0:
            print(f"shard {position}/{len(names)}", flush=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(one_sided, columns=["symbol", "date", "side"]).to_parquet(
        args.out_dir / "archive_diff_one_sided.parquet"
    )
    pd.DataFrame(events).to_parquet(args.out_dir / "archive_diff_events.parquet")
    print(json.dumps({"one_sided_rows": len(one_sided), "events": len(events)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
