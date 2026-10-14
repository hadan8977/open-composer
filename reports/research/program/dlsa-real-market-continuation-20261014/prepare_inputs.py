"""Task-local, bounded intake. No network, factor fit, policy or P&L execution."""

import csv
import hashlib
import json
import resource
import time
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from open_composer.research.features.price_hygiene import sanitize_price_matrices

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BRIDGE = ROOT / "reports/research/program/day-goal-20261013/real-market-input-bridge"


def now():
    return datetime.now(UTC).isoformat()


def write(name, value):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def bind(p):
    return {
        "path": str(p.relative_to(ROOT)),
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }


def main():
    start = time.monotonic()
    contract = json.loads((OUT / "input-contract.json").read_text())
    selection = contract["cohort"]
    membership = ROOT / selection["source"]
    rows = list(csv.DictReader(membership.open()))
    as_of = selection["as_of_date"]
    eligible = {
        r["ticker"]
        for r in rows
        if r["start_date"] <= as_of and (not r["end_date"] or r["end_date"] >= as_of)
    }
    symbols = sorted(
        eligible, key=lambda s: hashlib.sha256((selection["hash_prefix"] + s).encode()).hexdigest()
    )[: selection["count"]]
    assert symbols == selection["symbols"], "frozen cohort changed"
    layout = json.loads((ROOT / "data/sip/daily/_LAYOUT.json").read_text())
    mapping = {s: k for k, values in layout["shard_symbols"].items() for s in values}
    manifest = json.loads((ROOT / "data/sip-delisted/broad/_manifest.json").read_text())
    paths = set()
    for year in range(contract["first_year"], contract["last_year"] + 1):
        paths.update(
            ROOT / f"data/sip/daily/{year}/shard-{mapping[s]}.parquet"
            for s in symbols
            if s in mapping
        )
    for k, batch in manifest["batches"].items():
        if set(batch["symbols"]) & set(symbols):
            paths.add(ROOT / f"data/sip-delisted/broad/daily/batch-{k}.parquet")
    # A few old S&P-removal batches, explicitly part of the local archive.
    paths.update((ROOT / "data/sip-delisted/daily").glob("batch-*.parquet"))
    assert len(paths) <= contract["max_local_value_files"]
    frames, receipts = [], []
    for p in sorted(paths):
        if not p.is_file():
            receipts.append({"path": str(p.relative_to(ROOT)), "status": "absent"})
            continue
        before = p.stat()
        f = pq.ParquetFile(p)
        columns = [
            c
            for c in [
                "symbol",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "trade_count",
            ]
            if c in f.schema_arrow.names
        ]
        table = pq.read_table(
            p, columns=columns, filters=[("symbol", "in", symbols)], use_threads=False
        )
        df = table.to_pandas()
        after = p.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        h = (
            hashlib.sha256(table.serialize().to_pybytes()).hexdigest()
            if hasattr(table, "serialize")
            else hashlib.sha256(
                pd.util.hash_pandas_object(df, index=False).values.tobytes()
            ).hexdigest()
        )
        receipts.append(
            {
                "path": str(p.relative_to(ROOT)),
                "bytes": after.st_size,
                "mtime_ns": after.st_mtime_ns,
                "selected_rows": len(df),
                "selected_record_sha256": h,
                "binding_scope": "exact selected values; not full-file hash",
                "source_kind": "sip_active"
                if "data/sip/daily" in str(p)
                else "existing_delisted_backfill",
            }
        )
        if len(df):
            df["source_file"] = str(p.relative_to(ROOT))
            df["source_rank"] = 0 if "data/sip/daily" in str(p) else 1
            frames.append(df)
    bars = pd.concat(frames, ignore_index=True)
    bars["session"] = (
        pd.to_datetime(bars["timestamp"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    bars = bars[(bars.session >= contract["start_date"]) & (bars.session <= contract["end_date"])]
    # Preserve conflicts. No stitching price vintages together within a ticker.
    duplicate = (
        bars.groupby(["symbol", "session"])
        .agg(versions=("close", "nunique"), records=("close", "size"))
        .reset_index()
    )
    conflict = duplicate[duplicate.versions > 1]
    conflict.to_json(OUT / "inputs/version-conflicts.json", orient="records", indent=2)
    bars = bars.sort_values(["symbol", "session", "source_rank", "source_file"])
    bars = bars.drop_duplicates(["symbol", "session"], keep="first")
    bars["ghost"] = (bars.volume == 0) & (bars.trade_count.fillna(0) == 0)
    bars.to_parquet(OUT / "inputs/selected-bars.parquet", index=False)
    valid = bars[~bars.ghost]
    # Use exchange sessions, not the observed union (which could hide missing days).
    from open_composer.market_sessions import us_equity_session_dates

    dates = [
        d.isoformat()
        for d in us_equity_session_dates(
            date.fromisoformat(contract["start_date"]), date.fromisoformat(contract["end_date"])
        )
    ]
    close = valid.pivot(index="session", columns="symbol", values="close").reindex(
        index=dates, columns=symbols
    )
    opens = valid.pivot(index="session", columns="symbol", values="open").reindex(
        index=dates, columns=symbols
    )
    # Each decision sees only its prefix. Never erase earlier admitted observations
    # using a break found later in the full panel. A break is not a terminal payout.
    clean = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    trigger = pd.DataFrame(False, index=close.index, columns=close.columns)
    break_rows = []
    for i, d in enumerate(close.index):
        a, _, report = sanitize_price_matrices(close.iloc[: i + 1], opens.iloc[: i + 1])
        clean.loc[d] = a.iloc[-1]
        for event in report.breaks:
            row = event.as_dict()
            if row["first_session_after"] == d:
                trigger.loc[d, row["symbol"]] = True
                break_rows.append(row)
    adjusted_return = (clean.div(clean.shift(1)) - 1).mask(trigger)
    # Sanitizer blanking does not give the holder a free exit. Missing/terminal
    # labels remain unknown. The full economic runner may not fill these with 0.
    features = pd.concat(
        {
            "adjusted_proxy_r1": adjusted_return,
            "adjusted_proxy_r5": (1 + adjusted_return).rolling(5).apply(np.prod, raw=True) - 1,
            "adjusted_proxy_vol5": adjusted_return.rolling(5).std(ddof=0),
        },
        axis=1,
    )
    features.to_parquet(OUT / "inputs/price-feature-candidates.parquet")
    clean.to_parquet(OUT / "inputs/causal-adjusted-close.parquet")
    trigger.to_parquet(OUT / "inputs/split-like-trigger-mask.parquet")
    write("inputs/hygiene-breaks.json", break_rows)
    write("inputs/local-read-receipt.json", receipts)
    write(
        "inputs/historical-cohort.json",
        {
            "membership_source": bind(membership),
            "as_of": as_of,
            "symbols": symbols,
            "selection": selection,
            "retrospective_membership_revision_limit": True,
            "security_identity_not_established_by_membership_or_CIK": True,
            "past_and_future_member_rows_retained": [r for r in rows if r["ticker"] in symbols],
        },
    )
    # Actual, source-qualified raw action/terminal/return/feature connections.
    raw = [
        json.loads(s)
        for s in (BRIDGE / "acquisition/daily-return-inputs.jsonl").read_text().splitlines()
        if s.strip()
    ]
    px = [
        json.loads(s)
        for s in (BRIDGE / "acquisition/price3-candidates.jsonl").read_text().splitlines()
        if s.strip()
    ]
    actions = json.loads((BRIDGE / "acquisition/normalized-actions.json").read_text())
    entitlements = json.loads((BRIDGE / "held-asset-action-ledger.json").read_text())["entries"]
    write(
        "inputs/actual-connected-raw-sample.json",
        {
            "basis": "accepted existing sources",
            "daily_return_rows": raw,
            "price3_feature_rows": px,
            "actions": actions,
            "unit_terminal_and_action_entitlements": entitlements,
            "limitations": [
                "current-vintage; historical first visibility unknown",
                "entitlements are not cash settlement or broker fills",
                "forensic examples are not the policy cohort",
            ],
        },
    )
    coverage = []
    for s in symbols:
        x = bars[bars.symbol == s]
        coverage.append(
            {
                "symbol": s,
                "rows": len(x),
                "first": x.session.min(),
                "last": x.session.max(),
                "ghost_rows": int(x.ghost.sum()),
                "finite_adjusted_return_candidates": int(adjusted_return[s].count()),
                "identity_status": "dated_shareclass_evidence_pending",
                "terminal_claim_status": "must_resolve_if_exposed; never_future_drop",
            }
        )
    write(
        "inputs/coverage.json",
        {
            "as_of_utc": now(),
            "cohort_size": len(symbols),
            "calendar_sessions": len(dates),
            "observed_rows": len(bars),
            "non_ghost_rows": len(valid),
            "conflicting_source_dates": len(conflict),
            "local_value_files_read": len(receipts),
            "per_symbol": coverage,
            "adjustment_basis": "Alpaca all: splits, cash dividends, spin-offs; not delisting cash",
            "actual_connected_raw_rows": len(raw),
            "actual_connected_feature_rows": len(px),
            "actual_action_rows": len(actions),
            "actual_entitlement_rows": len(entitlements),
            "economic_input_accepted": False,
            "new_model_fits": 0,
            "new_optimizer_updates": 0,
        },
    )
    write(
        "inputs/preparation-resource-receipt.json",
        {
            "at_utc": now(),
            "wall_seconds": time.monotonic() - start,
            "cpu_seconds": time.process_time(),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "market_requests": 0,
            "source_downloads": 0,
            "fits": 0,
            "updates": 0,
        },
    )


if __name__ == "__main__":
    (OUT / "inputs").mkdir(exist_ok=True)
    main()
