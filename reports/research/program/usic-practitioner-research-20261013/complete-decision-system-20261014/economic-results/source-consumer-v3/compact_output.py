"""Keep daily continuous NAV and exact minute-summary metrics without large spill.

Native policy/orders/controller consume every event unchanged. Signal/order/fill
records remain complete; negative policy reasons retain count and clock ranges.
"""

import gzip
from collections import Counter

import msgspec


def flush(strategy, folder, key, counters):
    with gzip.open(folder / (key + "-audit.jsonl.gz"), "wb", compresslevel=1) as f:
        for row in strategy.audit:
            counters[row["action"]] += 1
            f.write(msgspec.json.encode(row) + b"\n")
    strategy.audit.clear()
    daily = [row for row in strategy.snapshots if row["daily_close"]]
    with gzip.open(folder / (key + "-NAV.jsonl.gz"), "wb", compresslevel=1) as f:
        for row in daily:
            f.write(msgspec.json.encode(row) + b"\n")
    nav = [r["equity"] for r in strategy.snapshots]
    peak = None
    maxdd = 0
    for value in nav:
        peak = max(value, peak) if peak is not None else value
        maxdd = max(maxdd, 1 - value / peak)
    # Boundary-aware drawdown can be combined exactly with prior monthly peak.
    running_min = float("inf")
    frontier = []
    for row in strategy.snapshots:
        value = row["equity"]
        if value < running_min:
            running_min = value
            frontier.append(dict(at_ns=row["at_ns"], equity=value))
    summary = dict(
        end_minute_NAV_count=len(nav),
        daily_NAV_count=len(daily),
        first=strategy.snapshots[0] if nav else None,
        last=strategy.snapshots[-1] if nav else None,
        maximum=max(nav) if nav else None,
        minimum=min(nav) if nav else None,
        internal_end_minute_max_drawdown=maxdd,
        prefix_min_frontier=frontier,
        price_quotes_not_persisted_as_new_bars=True,
        all_native_orders_and_financial_decisions_unchanged=True,
        intraday_measure="scheduled end-minute marks, not continuously time-weighted quote extrema",
    )
    (folder / (key + "-minute-summary.json")).write_bytes(msgspec.json.encode(summary))
    strategy.snapshots.clear()
    aggregates = {}
    with gzip.open(folder / (key + "-policy.jsonl.gz"), "wb", compresslevel=1) as f:
        for symbol, state in strategy.policy.states.items():
            for row in state.audit:
                reason = row.get("reason", "execution_report")
                counters["policy:" + reason] += 1
                if "reason" not in row:
                    f.write(msgspec.json.encode(dict(symbol=symbol, **row)) + b"\n")
                    continue
                group = (symbol, row["at"][:10], reason, row.get("state", ""))
                item = aggregates.setdefault(
                    group,
                    dict(
                        symbol=symbol,
                        day=row["at"][:10],
                        reason=reason,
                        state=row.get("state", ""),
                        count=0,
                        first_at=row["at"],
                        last_at=row["at"],
                    ),
                )
                item["count"] += 1
                item["last_at"] = row["at"]
            state.audit.clear()
        for item in aggregates.values():
            f.write(msgspec.json.encode(item) + b"\n")
    (folder / (key + "-policy-counts.json")).write_bytes(
        msgspec.json.encode(
            dict(Counter({k: v for k, v in counters.items() if k.startswith("policy:")}))
        )
    )
