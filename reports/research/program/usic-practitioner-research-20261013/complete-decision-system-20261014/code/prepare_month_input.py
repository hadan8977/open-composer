"""Review-admitted raw-basis input preparation; no features, signals or P&L."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import resource
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from datetime import time as day_time
from pathlib import Path

import duckdb

from open_composer.market_sessions import (
    NEW_YORK,
    us_equity_session_close,
    us_equity_session_dates,
)

P = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
SYMBOLS = ["COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"]
PRICE_KEYS = ["o", "h", "l", "c", "vw"]


def binding(path):
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), sha256=digest, bytes=path.stat().st_size)


def main():
    start_cpu = time.process_time()
    review_path = P / "independent-plan-review.json"
    review = json.loads(review_path.read_text())
    admission = review.get("input_preparation_admission", {})
    if not (
        admission.get("accepted_for_execution") is True
        and review.get("author") == "7c7b1f3d-b962-4bbe-a2eb-87578888a8d5"
        and review.get("reviewer") != review.get("author")
        and admission.get("economic_execution_admitted") is False
        and admission["allocation"]["economic_coreseconds"] == 0
    ):
        raise SystemExit("No bound independent input-only admission; refusing prices")
    plan_binding = binding(P / "scientific-plan.json")
    rows = review.get("bindings", {})
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    assert any(
        isinstance(b, dict) and all(b.get(k) == plan_binding[k] for k in ("path", "sha256"))
        for b in rows
    )
    assert admission["symbols"] == SYMBOLS
    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == (
        "45ab956ac9d57541227daf201006b6523255ccff90e63f9967b1228ae1a85b5f"
    )
    resource.setrlimit(resource.RLIMIT_CPU, (150, 155))
    inventory = json.loads((P / "input-inventory.json").read_text())
    daily = defaultdict(lambda: defaultdict(dict))
    raw_examples = defaultdict(dict)
    input_bindings = []
    admitted_entities = admission["existing_raw_all_action_and_raw_witness_bindings"]
    assert {json.dumps(e["entity"], sort_keys=True) for e in inventory["entities"]} == {
        json.dumps(e, sort_keys=True) for e in admitted_entities
    }
    actions = []
    for b in admitted_entities:
        assert binding(ROOT / b["path"]) == b
        packet = json.loads((ROOT / b["path"]).read_text())
        for kind, records in packet.get("corporate_actions", {}).items():
            for r in records:
                actions.append(dict(kind=kind, row=r))
    for e in inventory["entities"]:
        if e["params"].get("timeframe") not in ("1Day", "1Min"):
            continue
        path = ROOT / e["entity"]["path"]
        assert binding(path) == e["entity"]
        input_bindings.append(e["entity"])
        data = json.loads(path.read_text())
        for symbol, records in data.get("bars", {}).items():
            if symbol not in SYMBOLS:
                continue
            if e["params"]["timeframe"] == "1Day":
                for r in records:
                    day = (
                        datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
                        .astimezone(NEW_YORK)
                        .date()
                    )
                    daily[e["params"]["adjustment"]][symbol][day] = r
            elif e["params"].get("adjustment") == "raw":
                for r in records:
                    raw_examples[symbol][datetime.fromisoformat(r["t"].replace("Z", "+00:00"))] = r
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='400MB'")
    out = P / "inputs/november2024"
    out.mkdir(parents=True, exist_ok=False)
    session_summary, raw_comparisons = [], []
    for symbol in SYMBOLS:
        admitted_shards = [b for b in admission["fixed_minute_entities"] if b["symbol"] == symbol]
        assert len(admitted_shards) == 1
        expected = {k: v for k, v in admitted_shards[0].items() if k != "symbol"}
        files = [ROOT / expected["path"]]
        assert binding(files[0]) == expected
        destination = out / (symbol + ".csv")
        with destination.open("w") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "symbol",
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "vwap",
                    "basis_known_from",
                    "research_price_factor",
                    "volume_factor",
                ],
            )
            writer.writeheader()
            for day in us_equity_session_dates(
                datetime(2024, 11, 1).date(), datetime(2024, 11, 30).date()
            ):
                earlier = [d for d in daily["raw"][symbol] if d < day and d in daily["all"][symbol]]
                assert earlier
                previous = max(earlier)
                raw, adjusted = daily["raw"][symbol][previous], daily["all"][symbol][previous]
                ratios = [
                    raw[k] / adjusted[k] for k in PRICE_KEYS if raw.get(k) and adjusted.get(k)
                ]
                price_factor = ratios[-1]
                spread = max(abs(r / price_factor - 1) for r in ratios)
                if spread > 1e-4:
                    session_summary.append(
                        dict(
                            symbol=symbol,
                            day=str(day),
                            status="nonuniform_prior_day_basis",
                            relative_ratio_spread=spread,
                        )
                    )
                    continue
                # Normalize volumes separately: dividend price adjustments must
                # never be mistaken for split share-volume transforms.
                volume_factor = raw["v"] / adjusted["v"]
                close = us_equity_session_close(day)
                assert close is not None
                session_open = datetime.combine(day, day_time(9, 30), tzinfo=NEW_YORK)
                session_close = datetime.combine(day, close, tzinfo=NEW_YORK)
                expected_minutes = set()
                cursor = session_open
                while cursor < session_close:
                    expected_minutes.add(cursor.astimezone(UTC))
                    cursor += timedelta(minutes=1)
                records = con.execute(
                    "SELECT timestamp, open, high, low, close, volume, vwap "
                    "FROM read_parquet(?) WHERE symbol=? AND "
                    "timestamp >= ? AND timestamp < ? "
                    "ORDER BY timestamp",
                    [[str(f) for f in files], symbol, session_open, session_close],
                ).fetchall()
                valid_count = 0
                timestamps = []
                frequencies = Counter(r[0] for r in records)
                duplicates = {t for t, n in frequencies.items() if n > 1}
                invalid = []
                for t, o, h, low, c, v, vw in records:
                    if t in duplicates:
                        continue
                    prices = [
                        o * price_factor,
                        h * price_factor,
                        low * price_factor,
                        c * price_factor,
                        vw * price_factor,
                    ]
                    if (
                        not all(math.isfinite(p) and p > 0 for p in prices)
                        or not low <= min(o, c) <= max(o, c) <= h
                        or not math.isfinite(v)
                        or v < 0
                    ):
                        invalid.append(t.isoformat())
                        continue
                    writer.writerow(
                        dict(
                            symbol=symbol,
                            timestamp=t.isoformat(),
                            open=prices[0],
                            high=prices[1],
                            low=prices[2],
                            close=prices[3],
                            volume=v * volume_factor,
                            vwap=prices[4],
                            basis_known_from=str(previous),
                            research_price_factor=price_factor,
                            volume_factor=volume_factor,
                        )
                    )
                    timestamps.append(t)
                    valid_count += 1
                    r = raw_examples[symbol].get(t)
                    if r:
                        error = max(
                            abs(p - r[k]) / r[k] for k, p in zip(PRICE_KEYS, prices, strict=True)
                        )
                        raw_comparisons.append(
                            dict(
                                symbol=symbol,
                                timestamp=t.isoformat(),
                                maximum_relative_price_error=error,
                                maximum_absolute_price_error=max(
                                    abs(p - r[k]) for k, p in zip(PRICE_KEYS, prices, strict=True)
                                ),
                                relative_volume_error=abs(v * volume_factor - r["v"])
                                / max(1, r["v"]),
                            )
                        )
                session_summary.append(
                    dict(
                        symbol=symbol,
                        day=str(day),
                        status="normalized_research_current_vintage",
                        rows=valid_count,
                        prior_basis_date=str(previous),
                        price_factor=price_factor,
                        volume_factor=volume_factor,
                        first=str(min(timestamps)) if timestamps else None,
                        last=str(max(timestamps)) if timestamps else None,
                        scheduled_open=session_open.isoformat(),
                        scheduled_close=session_close.isoformat(),
                        expected_minutes=len(expected_minutes),
                        missing_minutes=[
                            t.isoformat() for t in sorted(expected_minutes - set(timestamps))
                        ],
                        duplicate_minutes=[t.isoformat() for t in sorted(duplicates)],
                        invalid_minutes=invalid,
                        exact_raw_certified=False,
                    )
                )
        input_bindings += [binding(f) for f in files]
    report = dict(
        at_utc=datetime.now(UTC).isoformat(),
        admission=binding(review_path),
        scientific_plan=plan_binding,
        input_bindings=input_bindings,
        outputs=[binding(f) for f in sorted(out.glob("*.csv"))],
        sessions=session_summary,
        matched_raw_example_comparisons=raw_comparisons,
        actions=actions,
        normalization_is_conditional_not_exact_raw=True,
        source_basis=(
            "prior completed daily raw/all scalar, volume separately; "
            "no current-day price used to choose transform"
        ),
        local_producer_adjustment="all",
        current_vintage=True,
        historical_data_vintage_certified=False,
        PIT_identity_certified=False,
        features_or_signals_computed=False,
        economic_execution=False,
        new_market_requests=0,
        CPU=time.process_time() - start_cpu,
        max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        next_action=(
            "Independent accept actual basis/raw-example deviations; "
            "session grid and corporate-action coverage must be checked "
            "before any consumer replay"
        ),
    )
    (P / "input-preparation-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                normalized_sessions=len(session_summary),
                matched_raw_examples=len(raw_comparisons),
                CPU=report["CPU"],
            )
        )
    )


if __name__ == "__main__":
    main()
