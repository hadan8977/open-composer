"""Preserve actual raw components after capped full diagnostic failures."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

from build_finite_raw_diagnostic import OUT, ROOT, feature_row, stamp, valid

from open_composer.market_sessions import us_equity_session_dates


def main():
    assert os.sched_getaffinity(0) == {0}
    target = OUT / "bounded-components"
    assert not target.exists()
    target.mkdir()

    def save(name, value):
        (target / name).write_text(json.dumps(value, indent=2, default=str) + "\n")

    ledger = json.loads((OUT / "market/request-ledger.json").read_text())
    ids = json.loads((OUT / "identity-candidates.json").read_text())["records"]
    symbols = [r["source_ticker_candidate"] for r in ids]
    issues = {r["source_ticker_candidate"]: r["issue_key"] for r in ids}
    raw, adjusted, actions = defaultdict(dict), defaultdict(dict), []
    row_counts = Counter()
    with localcontext() as ctx:
        ctx.prec = 60
        for attempt in ledger["attempts"]:
            kind = attempt["id"]
            if kind.startswith("raw_RTH_"):
                continue
            payload = json.loads(
                (ROOT / attempt["entity"]["path"]).read_bytes(),
                parse_float=Decimal,
                parse_int=Decimal,
            )
            for typ, rows in payload.get("corporate_actions", {}).items():
                for ordinal, record in enumerate(rows):
                    links = []
                    for field, symbol in record.items():
                        if (field == "symbol" or field.endswith("_symbol")) and symbol in issues:
                            cf = (
                                "cusip" if field == "symbol" else field.replace("_symbol", "_cusip")
                            )
                            expected = issues[symbol].split("|")[0]
                            links.append(
                                {
                                    "symbol": symbol,
                                    "role_field": field,
                                    "expected_cusip": expected,
                                    "source_cusip": record.get(cf),
                                    "CUSIP_match": expected == record.get(cf),
                                }
                            )
                    actions.append(
                        {
                            "type": typ,
                            "record": record,
                            "entity": attempt["entity"],
                            "pointer": f"/corporate_actions/{typ}/{ordinal}",
                            "issue_links": links,
                            "quarantined_identity_mismatch": any(
                                not x["CUSIP_match"] for x in links
                            ),
                            "historical_first_visible": None,
                            "current_fetched_at": attempt["current_fetched_at"],
                            "actual_spendable_at": None,
                            "market_value": None,
                        }
                    )
                    row_counts["actions"] += 1
            for symbol, rows in payload.get("bars", {}).items():
                row_counts[kind] += len(rows)
                destination = raw if kind == "diagnostic_daily_raw" else adjusted
                if kind in {"diagnostic_daily_raw", "diagnostic_daily_all"}:
                    for record in rows:
                        destination[symbol][stamp(record).date()] = record
        splits = [
            a["record"]
            for a in actions
            if a["type"] == "forward_splits" and not a["quarantined_identity_mismatch"]
        ]
        # Fixed hash-first three, first diagnostic date. No price/performance selection.
        features = [feature_row(s, date(2024, 1, 2), raw[s], splits) for s in symbols[:3]]
        save(
            "fixed-first-three-price-features.json",
            {
                "selection": "first three frozen issue hashes, earliest fixed diagnostic session",
                "records": features,
                "full_1000_feature_diagnostic": None,
                "other_997_features": "N/A: two capped builds terminated before serialization",
                "no_orders_fills_strategy_returns_or_PnL": True,
            },
        )
        save(
            "all-actions-and-held-rights.json",
            {
                "records": actions,
                "retain_all_unknown_outofcohort_childrights": True,
                "payable_is_not_spendable": True,
                "acquirer_not_cancelled": True,
            },
        )
        sessions = us_equity_session_dates(date(2023, 7, 1), date(2025, 12, 31))
        coverage = []
        for s in symbols:
            r, a = raw[s], adjusted[s]
            ratios = [r[d]["c"] / a[d]["c"] for d in sorted(r.keys() & a.keys()) if a[d]["c"] > 0]
            coverage.append(
                {
                    "symbol": s,
                    "issue_key": issues[s],
                    "raw_rows": len(r),
                    "all_rows": len(a),
                    "raw_first": min(r) if r else None,
                    "raw_last": max(r) if r else None,
                    "expected_sessions": len(sessions),
                    "missing_sessions": [d for d in sessions if d not in r],
                    "invalid_raw": sum(not valid(x) for x in r.values()),
                    "raw_all_ratio_min": min(ratios) if ratios else None,
                    "raw_all_ratio_max": max(ratios) if ratios else None,
                    "episode_interval_certified": False,
                }
            )
        save("daily-coverage-and-basis.json", coverage)
    clocks = []
    for attempt in ledger["attempts"]:
        if not attempt["id"].startswith("raw_RTH_"):
            continue
        day = attempt["id"].removeprefix("raw_RTH_")
        payload = json.loads((ROOT / attempt["entity"]["path"]).read_bytes())
        start = datetime.fromisoformat(day + "T14:30:00").replace(tzinfo=UTC)
        expected = {
            (start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z") for i in range(390)
        }
        for s in symbols:
            rows = payload.get("bars", {}).get(s, [])
            times = [r["t"] for r in rows]
            row_counts["minute_raw"] += len(rows)
            clocks.append(
                {
                    "symbol": s,
                    "day": day,
                    "raw_rows": len(rows),
                    "unique_source_timestamps": len(set(times)),
                    "missing_source_timestamps": sorted(expected - set(times)),
                    "duplicate_timestamps": len(times) - len(set(times)),
                    "valid_OHLC_parent_geometry_and_execution": None,
                    "qualification": "source timestamp coverage only; no fill certificate",
                }
            )
    save("source-timestamp-coverage.json", clocks)
    save(
        "actual-component-summary.json",
        {
            "record_counts": dict(row_counts),
            "timestamp_grid_cells": len(clocks),
            "full_timestamp_grid_cells": sum(not r["missing_source_timestamps"] for r in clocks),
            "completed_feature_cases": len(features),
            "full_1000_feature_diagnostic": None,
            "price_geometry_candidates": None,
            "full_cohort_rank": None,
            "strict_input_ready": False,
            "economic_execution_admitted": False,
            "strategy_returns_PnL_fits_orders": 0,
        },
    )
    print(json.dumps(dict(row_counts), sort_keys=True))


if __name__ == "__main__":
    main()
