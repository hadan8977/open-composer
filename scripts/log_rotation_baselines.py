"""Append the daily equal-weight-menu baselines for the H-20260918-05 sleeves.

Card H-20260918-05 records that two of the three sleeves have a weak random-pick
placebo result (20% and 25% of seeds reach their holdout Sharpe), so the forward
question is specifically whether the momentum ranking beats simply holding the
same menu equal-weighted. That comparison is only possible if the baseline is
recorded from day one, so this script runs nightly next to the paper cycle and
appends one row per menu per session to reports/paper/rotation_baselines.jsonl.

It never touches the broker and never reads .env.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "reports" / "paper" / "rotation_baselines.jsonl"

MENUS: dict[str, list[str]] = {
    "us_etf_sector_rotation_252_top2_weekly": [
        "XLK",
        "XLV",
        "XLF",
        "XLE",
        "XLI",
        "XLY",
        "XLP",
        "XLU",
        "XLB",
        "XLRE",
        "XLC",
    ],
    "us_etf_growth_rotation_blend_top2_monthly": ["SPMO", "QQQ", "SMH", "XLK", "GLD", "TLT"],
    "us_etf_levered_rotation_63_top2_monthly": ["TQQQ", "SOXL", "UPRO", "USD", "TECL"],
}
REFERENCES = ["SPMO", "SPY", "SHY"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=6, help="trailing sessions to load")
    args = parser.parse_args(argv)

    import duckdb

    symbols = sorted({s for menu in MENUS.values() for s in menu} | set(REFERENCES))
    in_list = ",".join(f"'{s}'" for s in symbols)
    year = datetime.now(UTC).year
    globs = ",".join(f"'data/sip/daily/{y}/*.parquet'" for y in (year - 1, year))
    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'")
    con.execute("SET threads=2")
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, close
        FROM read_parquet([{globs}], union_by_name=true)
        WHERE symbol IN ({in_list})
              AND (volume > 0 OR trade_count > 0)
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    if frame.empty:
        raise SystemExit("no rows loaded from the daily archive")

    pivot = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    rets = pivot.pct_change(fill_method=None)
    tail = rets.tail(max(1, args.sessions))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()
    if OUT_PATH.is_file():
        for line in OUT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            seen.add((str(row.get("session")), str(row.get("strategy"))))

    written = 0
    with OUT_PATH.open("a", encoding="utf-8") as handle:
        for session, row in tail.iterrows():
            session_key = str(session.date() if hasattr(session, "date") else session)
            for strategy, menu in MENUS.items():
                if (session_key, strategy) in seen:
                    continue
                present = [s for s in menu if s in row.index and row[s] == row[s]]
                if not present:
                    continue
                payload = {
                    "session": session_key,
                    "strategy": strategy,
                    "baseline": "equal_weight_menu_buy_and_hold",
                    "menu": menu,
                    "menu_symbols_priced": present,
                    "equal_weight_return": float(row[present].mean()),
                    "reference_returns": {
                        ref: (
                            float(row[ref]) if ref in row.index and row[ref] == row[ref] else None
                        )
                        for ref in REFERENCES
                    },
                    "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "note": "baseline only -- no broker interaction, no positions implied",
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                written += 1
    print(f"appended {written} baseline rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
