"""Checkpoint causal features and raw-minute geometry; no economics or network."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext

from build_finite_raw_diagnostic import BASE, NY, OUT, ROOT, feature_row, stamp, valid

from open_composer.market_sessions import previous_us_equity_session, us_equity_session_dates

TARGET = OUT / "diagnostic-completion"


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def binding(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(p, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(canon(obj) + "\n")
    tmp.replace(p)


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (180, 181))
    assert not json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())[
        "research_paused"
    ]
    implementation = BASE / "code/build_finite_raw_diagnostic.py"
    assert binding(implementation)["sha256"] == (
        "b934dd653aeddd9610c862fbf82767df26fc0b88fac130d8909a5fc9e4041465"
    )
    TARGET.mkdir(exist_ok=True)
    cases = TARGET / "cases"
    cases.mkdir(exist_ok=True)
    ledger = json.loads((OUT / "market/request-ledger.json").read_text())
    identities = json.loads((OUT / "identity-candidates.json").read_text())["records"]
    issue = {r["source_ticker_candidate"]: r["issue_key"] for r in identities}
    symbols = list(issue)
    days = list(us_equity_session_dates(date(2024, 1, 1), date(2024, 12, 31))[:40])
    config = {
        "input_ledger": binding(OUT / "market/request-ledger.json"),
        "original_feature_function": binding(implementation),
        "frozen_contract": binding(OUT / "state-and-ledger-contract.json"),
        "root_total_pool_authority": binding(OUT / "root-task-pool-continuation.json"),
        "symbols": symbols,
        "days": days,
        "Decimal_precision": 60,
        "original_math_seed_clock_hygiene_unchanged": True,
        "source_window_EMA_seed_not_episode_certificate": True,
        "no_orders_fills_strategy_returns_PnL_or_new_network": True,
    }
    if (TARGET / "config.json").exists():
        assert json.loads((TARGET / "config.json").read_text()) == json.loads(canon(config))
    else:
        save(TARGET / "config.json", config)
    totals = Counter()
    raw, raw_pointer, actions = defaultdict(dict), defaultdict(dict), []
    geometry_counts = Counter()
    with localcontext() as ctx:
        ctx.prec = 60
        for attempt in ledger["attempts"]:
            entity = ROOT / attempt["entity"]["path"]
            assert binding(entity) == attempt["entity"]
            kind = attempt["id"]
            if kind not in {"diagnostic_daily_raw", "diagnostic_alltype_actions"} and not (
                kind.startswith("raw_RTH_")
            ):
                continue
            payload = json.loads(entity.read_bytes(), parse_float=Decimal, parse_int=Decimal)
            if kind == "diagnostic_alltype_actions":
                for typ, records in payload["corporate_actions"].items():
                    if typ == "forward_splits":
                        actions.extend(records)
                continue
            if kind == "diagnostic_daily_raw":
                for symbol, records in payload["bars"].items():
                    for ordinal, row in enumerate(records):
                        day = stamp(row).date()
                        assert day not in raw[symbol], "duplicate_raw_daily_date"
                        raw[symbol][day] = row
                        raw_pointer[symbol][day] = {
                            "entity_sha256": attempt["entity"]["sha256"],
                            "pointer": f"/bars/{symbol}/{ordinal}",
                        }
                continue
            day = date.fromisoformat(kind.removeprefix("raw_RTH_"))
            assert day in days
            assert not any(
                a["symbol"] in raw
                and min(raw[a["symbol"]]) < date.fromisoformat(a["ex_date"]) <= days[-1]
                for a in actions
            ), "diagnostic_BREAK_requires_decision_split_basis"
            start = datetime.combine(day, datetime.strptime("09:30", "%H:%M").time(), NY)
            expected = [start + timedelta(minutes=i) for i in range(390)]
            for symbol in symbols:
                p = cases / f"{symbol}--{day}.json"
                if p.exists():
                    saved = json.loads(p.read_text())
                    assert saved["source_minute_entity"] == attempt["entity"]
                    assert saved["config_sha256"] == binding(TARGET / "config.json")["sha256"]
                    totals.update(saved["counts"])
                    geometry_counts.update(saved["geometry_counts"])
                    continue
                feature = feature_row(symbol, day, raw[symbol], actions)
                prior = previous_us_equity_session(day)
                prefix_dates = sorted(d for d in raw[symbol] if d <= prior)
                feature["current_fetched_at_provenance"] = "Bound raw daily request ledger"
                feature["raw_daily_prefix_endpoints"] = (
                    [raw_pointer[symbol][prefix_dates[0]], raw_pointer[symbol][prefix_dates[-1]]]
                    if prefix_dates
                    else []
                )
                feature["raw_daily_last20_pointers"] = [
                    raw_pointer[symbol][d] for d in prefix_dates[-20:]
                ]
                records = payload.get("bars", {}).get(symbol, [])
                mapped, duplicates, invalid, seen = {}, set(), [], set()
                for ordinal, row in enumerate(records):
                    when = stamp(row)
                    if when in seen:
                        duplicates.add(when)
                    seen.add(when)
                    if valid(row):
                        mapped[when] = (ordinal, row)
                    else:
                        invalid.append(ordinal)
                counts = Counter(cells=1, raw_minute_rows=len(records), invalid_rows=len(invalid))
                counts["numeric_price_gate_cells"] = int(bool(feature.get("numeric_price_gate")))
                missing = [t for t in expected if t not in mapped or t in duplicates]
                counts["missing_real_minutes"] = len(missing)
                counts["complete_real_session_cells"] = int(not missing)
                geom = Counter()
                events = []
                valid_prior_dates = [d for d in prefix_dates if valid(raw[symbol][d])]
                previous10_high = (
                    max(raw[symbol][d]["h"] for d in valid_prior_dates[-10:])
                    if len(valid_prior_dates) >= 10
                    else None
                )
                for close_minute in list(range(1, 15)) + list(range(15, 60, 5)) + [60, 75, 90]:
                    width = 1 if close_minute < 15 else (5 if close_minute < 60 else 15)
                    times = [
                        start + timedelta(minutes=i)
                        for i in range(close_minute - width, close_minute)
                    ]
                    event = {
                        "close_time": start + timedelta(minutes=close_minute),
                        "width_minutes": width,
                        "full_eligibility": None,
                        "actual_order_or_fill": False,
                    }
                    if any(t not in mapped or t in duplicates for t in times):
                        geom["missing_parent_events"] += 1
                        event["status"] = "missing_real_parent"
                        events.append(event)
                        continue
                    geom["complete_parent_events"] += 1
                    parents = [mapped[t] for t in times]
                    event["source_pointers"] = [
                        f"/bars/{symbol}/{ordinal}" for ordinal, _ in parents
                    ]
                    rows = [r for _, r in parents]
                    low, high, close = (
                        min(r["l"] for r in rows),
                        max(r["h"] for r in rows),
                        rows[-1]["c"],
                    )
                    event.update(low=low, high=high, close=close, status="complete_real_parent")
                    if feature.get("numeric_price_gate"):
                        pref = grid_up(high + Decimal("0.01"))
                        supports = [
                            (abs(low - feature[k]) / feature[k], priority, k)
                            for priority, k in enumerate(("EMA21", "EMA9"))
                            if abs(low - feature[k]) / feature[k]
                            <= Decimal("0.25") * feature["ADR20"]
                            and close >= feature[k]
                        ]
                        tight = pref >= 5 and 0 < (pref - low) / pref <= min(
                            Decimal("0.05"), Decimal("0.5") * feature["ADR20"]
                        )
                        pb = bool(supports) and tight
                        event.update(
                            EMA_PB_price_geometry=pb,
                            P_ref=pref,
                            S_tight=low,
                            chosen_support=min(supports)[2] if supports else None,
                            AVWAP=None,
                            EMA_fallback_legal=True,
                        )
                        baseline_active = event["close_time"] + timedelta(
                            minutes=1
                        ) < start + timedelta(minutes=90)
                        event["baseline_activation_before_cutoff"] = baseline_active
                        if pb:
                            geom["EMA_PB_price_geometry_candidates"] += 1
                            geom["baseline_activatable_EMA_PB_candidates"] += int(baseline_active)
                        if width == 5 and previous10_high is not None:
                            bp = grid_up(
                                max(high + Decimal("0.01"), previous10_high + Decimal("0.01"))
                            )
                            br = (
                                close > previous10_high + Decimal("0.01")
                                and bp >= 5
                                and 0
                                < (bp - low) / bp
                                <= min(Decimal("0.05"), Decimal("0.5") * feature["ADR20"])
                            )
                            event.update(
                                BREAK_price_geometry=br,
                                BREAK_P_ref=bp,
                                previous10high=previous10_high,
                            )
                            geom["BREAK_price_geometry_candidates"] += int(br)
                    events.append(event)
                saved = {
                    "symbol": symbol,
                    "day": day,
                    "issue_key": issue[symbol],
                    "config_sha256": binding(TARGET / "config.json")["sha256"],
                    "source_minute_entity": attempt["entity"],
                    "feature": feature,
                    "counts": dict(counts),
                    "geometry_counts": dict(geom),
                    "missing_minutes": missing,
                    "invalid_source_ordinals": invalid,
                    "duplicate_timestamps": sorted(duplicates),
                    "events": events,
                    "opportunity_qualification": (
                        "Conditional price geometry, not certified eligibility/rank/fill"
                    ),
                    "orders_fits_strategy_returns_PnL": False,
                }
                save(p, saved)
                totals.update(counts)
                geometry_counts.update(geom)
                save(
                    TARGET / "runtime-progress.json",
                    {
                        "complete_cells": totals["cells"],
                        "last_completed": [symbol, day],
                        "process_CPU_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime,
                        "counts": dict(totals),
                        "geometry_counts": dict(geometry_counts),
                    },
                )
        assert totals["cells"] == 1000
        save(
            TARGET / "result.json",
            {
                "counts": dict(totals),
                "geometry_counts": dict(geometry_counts),
                "complete_25x40_diagnostic": True,
                "full101_rank": None,
                "full_eligibility_and_firstepisode_seed": None,
                "economic_execution_admitted": False,
                "no_Rf_ETB_AVWAP_or_firstvisible_blanket_block": True,
            },
        )
    print(canon({"counts": dict(totals), "geometry_counts": dict(geometry_counts)}))


def grid_up(value):
    return (value / Decimal("0.01")).to_integral_value(rounding=ROUND_CEILING) * Decimal("0.01")


if __name__ == "__main__":
    main()
