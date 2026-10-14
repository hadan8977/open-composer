"""Bounded actual source/clock/causal-price diagnostics; no orders or P&L."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from open_composer.market_sessions import previous_us_equity_session, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"
DERIVED = OUT / "derived"
NY = ZoneInfo("America/New_York")
resource.setrlimit(resource.RLIMIT_CPU, (45, 46))


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(name, obj):
    p = DERIVED / name
    assert not p.exists(), "preserve_derived_attempt"
    p.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def stamp(row):
    return datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(NY)


def valid(row):
    return (
        all(row[k].is_finite() and row[k] > 0 for k in ("o", "h", "l", "c", "vw"))
        and (row["l"] <= min(row["o"], row["c"]) <= max(row["o"], row["c"]) <= row["h"])
        and row["v"] >= 0
        and not (row["v"] == 0 and row["n"] == 0)
    )


def main():
    assert os.sched_getaffinity(0) == {0}
    assert not DERIVED.exists()
    DERIVED.mkdir()
    ledger = json.loads((OUT / "market/request-ledger.json").read_text())
    assert ledger["finished_at"] and ledger["requests_used"] == 47
    assert ledger["incomplete_response_reserved_bytes"] == 0
    assert all(a["http_status"] == 200 and a["entity_complete"] for a in ledger["attempts"])
    identities = json.loads((OUT / "identity-candidates.json").read_text())["records"]
    symbols = sorted(r["source_ticker_candidate"] for r in identities)
    issue_by_symbol = {r["source_ticker_candidate"]: r["issue_key"] for r in identities}
    raw, adjusted = defaultdict(dict), defaultdict(dict)
    days = us_equity_session_dates(date(2024, 1, 1), date(2024, 12, 31))[:40]
    assert [
        date.fromisoformat(a["id"].removeprefix("raw_RTH_"))
        for a in ledger["attempts"]
        if a["id"].startswith("raw_RTH_")
    ] == list(days)
    action_rows, count_rows = [], []
    clocks, clock_counts = [], Counter()
    all_counts = Counter()
    features = {}
    with localcontext() as ctx, (DERIVED / "source-record-pointers.jsonl").open("w") as stream:
        ctx.prec = 60
        # Daily and actions precede minute objects in the fixed request inventory.
        for attempt in ledger["attempts"]:
            entity = ROOT / attempt["entity"]["path"]
            assert bind(entity) == attempt["entity"]
            payload = json.loads(entity.read_bytes(), parse_float=Decimal, parse_int=Decimal)
            kind = attempt["id"]
            if "corporate_actions" in payload:
                for action_type, records in payload["corporate_actions"].items():
                    for ordinal, record in enumerate(records):
                        pointer = f"/corporate_actions/{action_type}/{ordinal}"
                        item = {
                            "type": action_type,
                            "record": record,
                            "entity": attempt["entity"],
                            "pointer": pointer,
                            "historical_first_visible": None,
                            "current_fetched_at": attempt["current_fetched_at"],
                            "actual_spendable_at": None,
                            "market_value": None,
                        }
                        links = []
                        for field, symbol in record.items():
                            if field == "symbol" or field.endswith("_symbol"):
                                if symbol in issue_by_symbol:
                                    cfield = (
                                        "cusip"
                                        if field == "symbol"
                                        else field.replace("_symbol", "_cusip")
                                    )
                                    expected = issue_by_symbol[symbol].split("|")[0]
                                    links.append(
                                        {
                                            "symbol": symbol,
                                            "role_field": field,
                                            "expected_issue_cusip": expected,
                                            "source_cusip": record.get(cfield),
                                            "CUSIP_match": record.get(cfield) == expected,
                                        }
                                    )
                        item["issue_links"] = links
                        item["quarantined_identity_mismatch"] = any(
                            not r["CUSIP_match"] for r in links
                        )
                        action_rows.append(item)
                        all_counts["actions"] += 1
                        stream.write(
                            canon(
                                {
                                    "entity_sha256": attempt["entity"]["sha256"],
                                    "pointer": pointer,
                                    "record_sha256": hashlib.sha256(
                                        canon(record).encode()
                                    ).hexdigest(),
                                }
                            )
                            + "\n"
                        )
                continue
            by_symbol = payload.get("bars", {})
            day = (
                date.fromisoformat(kind.removeprefix("raw_RTH_"))
                if kind.startswith("raw_RTH_")
                else None
            )
            if day is not None:
                splits = [
                    a["record"]
                    for a in action_rows
                    if a["type"] == "forward_splits" and not a["quarantined_identity_mismatch"]
                ]
                for symbol in symbols:
                    if (symbol, day) not in features:
                        features[symbol, day] = feature_row(symbol, day, raw[symbol], splits)
            for symbol in symbols if day else sorted(by_symbol):
                bars = by_symbol.get(symbol, [])
                good_by_time, duplicates = {}, set()
                for ordinal, row in enumerate(bars):
                    pointer = f"/bars/{symbol}/{ordinal}"
                    stream.write(
                        canon(
                            {
                                "entity_sha256": attempt["entity"]["sha256"],
                                "pointer": pointer,
                                "record_sha256": hashlib.sha256(canon(row).encode()).hexdigest(),
                                "symbol": symbol,
                                "t": row["t"],
                            }
                        )
                        + "\n"
                    )
                    all_counts[kind.split("_2024-")[0]] += 1
                    when = stamp(row)
                    if day is None:
                        if kind == "diagnostic_daily_raw":
                            raw[symbol][when.date()] = row
                        if kind == "diagnostic_daily_all":
                            adjusted[symbol][when.date()] = row
                    else:
                        if when in good_by_time:
                            duplicates.add(when)
                        if valid(row):
                            good_by_time[when] = row
                if day is None:
                    continue
                start = datetime.combine(day, datetime.strptime("09:30", "%H:%M").time(), NY)
                expected = [start + timedelta(minutes=i) for i in range(390)]
                missing = [t for t in expected if t not in good_by_time or t in duplicates]
                geom = Counter()
                for close_minute in list(range(1, 15)) + list(range(15, 60, 5)) + [60, 75, 90]:
                    width = 1 if close_minute < 15 else (5 if close_minute < 60 else 15)
                    parent = [
                        None
                        if start + timedelta(minutes=i) in duplicates
                        else good_by_time.get(start + timedelta(minutes=i))
                        for i in range(close_minute - width, close_minute)
                    ]
                    if any(r is None for r in parent):
                        geom["missing_parent_events"] += 1
                        continue
                    geom["complete_parent_events"] += 1
                    f = features[symbol, day]
                    if not f.get("numeric_price_gate"):
                        continue
                    low, high, close = (
                        min(r["l"] for r in parent),
                        max(r["h"] for r in parent),
                        parent[-1]["c"],
                    )
                    pref = ((high + Decimal("0.01")) / Decimal("0.01")).to_integral_value(
                        rounding=ROUND_CEILING
                    ) * Decimal("0.01")
                    support = any(
                        abs(low - f[k]) / f[k] <= Decimal("0.25") * f["ADR20"] and close >= f[k]
                        for k in ("EMA21", "EMA9")
                    )
                    if (
                        support
                        and pref >= 5
                        and 0
                        < (pref - low) / pref
                        <= min(Decimal("0.05"), Decimal("0.5") * f["ADR20"])
                    ):
                        geom["EMA_PB_price_geometry_candidates"] += 1
                clocks.append(
                    {
                        "symbol": symbol,
                        "day": day,
                        "raw_records": len(bars),
                        "invalid_rows": sum(not valid(r) for r in bars),
                        "duplicate_timestamps": len(duplicates),
                        "missing_minutes": [t.isoformat() for t in missing],
                        "counts": dict(geom),
                        "orders_fills_PnL": False,
                        "full_eligibility": None,
                    }
                )
                clock_counts.update(geom)
        # These are source/price summaries, never realized strategy return comparisons.
        for symbol in symbols:
            r, a = raw[symbol], adjusted[symbol]
            expected = us_equity_session_dates(date(2023, 7, 1), date(2025, 12, 31))
            paired = sorted(set(r) & set(a))
            ratios = [r[d]["c"] / a[d]["c"] for d in paired if a[d]["c"] > 0]
            count_rows.append(
                {
                    "symbol": symbol,
                    "issue_key": issue_by_symbol[symbol],
                    "raw_rows": len(r),
                    "all_rows": len(a),
                    "raw_first": min(r) if r else None,
                    "raw_last": max(r) if r else None,
                    "expected_sessions": len(expected),
                    "missing_sessions": [d for d in expected if d not in r],
                    "invalid_raw": sum(not valid(v) for v in r.values()),
                    "paired": len(paired),
                    "raw_all_close_ratio_min": min(ratios) if ratios else None,
                    "raw_all_close_ratio_max": max(ratios) if ratios else None,
                    "all_adjusted_not_raw_cash": True,
                    "no_source_first_last_as_life_interval": True,
                }
            )
    save("causal-price-feature-candidates.json", list(features.values()))
    save(
        "continuous-raw-clock.json",
        {
            "records": clocks,
            "totals": dict(clock_counts),
            "source_grid_complete_is_not_actualfill": True,
        },
    )
    save("daily-coverage-and-basis.json", count_rows)
    save(
        "all-actions-and-held-rights.json",
        {
            "records": action_rows,
            "retain_mismatches_unknown_and_outofcohort_childrights": True,
            "dividend_payable_is_not_spendable": True,
            "acquirer_not_cancelled": True,
        },
    )
    save(
        "actual-diagnostic-summary.json",
        {
            "record_counts": dict(all_counts),
            "clock_counts": dict(clock_counts),
            "features": len(features),
            "numeric_price_gate_days": sum(
                bool(f.get("numeric_price_gate")) for f in features.values()
            ),
            "strict_input_ready": False,
            "full_cohort_rank": None,
            "economic_trials": 0,
            "fit_orders_PnL": 0,
        },
    )
    print(
        canon(
            {
                "record_counts": dict(all_counts),
                "clocks": dict(clock_counts),
                "features": len(features),
            }
        )
    )


def feature_row(symbol, day, raw, splits):
    prior = previous_us_equity_session(day)
    prefix = {d: r for d, r in raw.items() if d <= prior}
    result = {
        "symbol": symbol,
        "decision_day": day,
        "prior_completed_day": prior,
        "visibility_proxy": "prior completed session close, current-vintage source",
        "historical_first_visible": None,
        "episode_interval_certified": False,
        "first_episode_EMA_seed_certified": False,
        "full_eligibility": None,
        "trigger_splitlike_eligibility_certified": False,
        "full_rank": None,
        "AVWAP": None,
        "EMA_fallback_legal": True,
    }
    if not prefix:
        result["missing_reason"] = "no_actual_prior_prefix"
        return result
    calendar = us_equity_session_dates(min(prefix), prior)

    def factor(observed):
        f = Decimal(1)
        for action in splits:
            if (
                action["symbol"] == symbol
                and observed < date.fromisoformat(action["ex_date"]) <= day
            ):
                f *= action["new_rate"] / action["old_rate"]
        return f

    normalized = {d: r["c"] / factor(d) for d, r in prefix.items() if valid(r)}
    prices = pd.DataFrame(
        {symbol: [float(normalized.get(d, Decimal("NaN"))) for d in calendar]},
        index=pd.DatetimeIndex(calendar),
    )
    opens = pd.DataFrame(
        {
            symbol: [
                float(prefix[d]["o"] / factor(d)) if d in normalized else float("nan")
                for d in calendar
            ]
        },
        index=prices.index,
    )
    cleaned, _, hygiene = sanitize_price_matrices(prices, opens)
    suffix = []
    for d, v in zip(calendar, cleaned[symbol], strict=True):
        suffix = [] if pd.isna(v) else suffix + [d]
    result.update(
        contiguous_clean_sessions=len(suffix),
        hygiene_asof_prefix_only=hygiene.manifest(),
        numeric_price_gate=False,
    )
    if len(suffix) < 63:
        result["missing_reason"] = "insufficient_consecutive_actual_prefix"
        return result
    tail = [prefix[d] for d in suffix[-20:]]
    result["ADR20"] = sum(r["h"] / r["l"] - 1 for r in tail) / 20
    result["ADV20"] = sum(r["c"] * r["v"] for r in tail) / 20
    result["momentum21"] = normalized[suffix[-1]] / normalized[suffix[-22]] - 1
    for n in (9, 21, 50):
        alpha = Decimal(2) / Decimal(n + 1)
        history = []
        value = normalized[suffix[0]]
        for d in suffix:
            value = value if not history else alpha * normalized[d] + (1 - alpha) * value
            history.append(value)
        result[f"EMA{n}"] = value
        if n == 21:
            result["rising_EMA21_lag5"] = history[-1] > history[-6]
    result["numeric_price_gate"] = bool(
        result["ADV20"] >= 50000000
        and result["momentum21"] > 0
        and result["EMA9"] > result["EMA21"] > result["EMA50"]
        and result["rising_EMA21_lag5"]
    )
    result["qualification"] = (
        "source-window numeric candidate; not lifeepisode seed/type or fullrank certificate"
    )
    return result


if __name__ == "__main__":
    main()
