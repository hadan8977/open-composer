"""Actual raw/action/clock components only: no orders, P&L, fits or cohort selection."""

from __future__ import annotations

import hashlib
import json
import resource
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

from open_composer.market_calendar import (
    expected_us_equity_rth_bar_starts,
    previous_us_equity_session,
    us_equity_session_dates,
)
from open_composer.research.features.price_hygiene import sanitize_price_matrices

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "acquisition"
DERIVED = OUT / "derived"
NY = ZoneInfo("America/New_York")
PRICE_FIELDS = ("o", "h", "l", "c", "vw")
START_CPU = time.process_time()
resource.setrlimit(resource.RLIMIT_CPU, (80, 81))


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def bound(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=encode, allow_nan=False) + "\n")


def dec(value):
    return Decimal(str(value))


def local_day(t):
    return pd.Timestamp(t).tz_convert(NY).date()


def valid(row):
    prices = [dec(row[k]) for k in PRICE_FIELDS]
    return (
        all(x.is_finite() and x > 0 for x in prices)
        and dec(row["l"]) <= min(dec(row["o"]), dec(row["c"]))
        and dec(row["h"]) >= max(dec(row["o"]), dec(row["c"]))
        and dec(row["v"]) >= 0
    )


def split_factor(symbol, observed_day, basis_day, splits):
    result = Decimal(1)
    for action in splits:
        effective = date.fromisoformat(action["ex_date"])
        if action["symbol"] == symbol and observed_day < effective <= basis_day:
            result *= dec(action["new_rate"]) / dec(action["old_rate"])
    return result


def main():
    assert ROOT == Path.cwd()
    assert not DERIVED.exists(), "Do not overwrite an input package or silently repeat a job"
    DERIVED.mkdir()
    ledger = json.loads((OUT / "request-ledger.json").read_text())
    assert ledger["requests_used"] == 13 and ledger["incomplete_response_reserved_bytes"] == 0
    packets, locators, canonical_records = {}, {}, []
    for attempt in ledger["attempts"]:
        entity = attempt["entity"]
        assert bound(ROOT / entity["path"]) == entity
        payload = json.loads((ROOT / entity["path"]).read_bytes(), parse_float=Decimal)
        packets[attempt["id"]] = payload
        groups = []
        if "bars" in payload:
            groups = [(f"/bars/{symbol}", symbol, rows) for symbol, rows in payload["bars"].items()]
        elif "quotes" in payload:
            groups = [("/quotes", payload["symbol"], payload["quotes"])]
        elif "corporate_actions" in payload:
            groups = [
                (f"/corporate_actions/{kind}", None, rows)
                for kind, rows in payload["corporate_actions"].items()
            ]
        for pointer, symbol, rows in groups:
            for ordinal, row in enumerate(rows):
                item = {
                    "request_ordinal": attempt["ordinal"],
                    "request_id": attempt["id"],
                    "entity": entity,
                    "json_pointer": f"{pointer}/{ordinal}",
                    "symbol": symbol,
                    "source_object_sha256_decimal_as_text": hashlib.sha256(
                        canonical(row).encode()
                    ).hexdigest(),
                    "source_object": row,
                    "current_fetched_at": attempt["current_fetched_at"],
                    "historical_first_visible": None,
                }
                canonical_records.append(item)
                if symbol and "t" in row:
                    locators[(attempt["id"], symbol, row["t"])] = {
                        k: item[k]
                        for k in (
                            "request_ordinal",
                            "entity",
                            "json_pointer",
                            "source_object_sha256_decimal_as_text",
                        )
                    }
    (DERIVED / "source-records.jsonl").write_text(
        "".join(canonical(x) + "\n" for x in canonical_records)
    )
    raw = packets["public_case_daily_raw"]["bars"]
    adjusted = packets["public_case_daily_all"]["bars"]
    actions = packets["public_case_actions"]["corporate_actions"]
    splits = actions.get("forward_splits", [])
    coverage, raw_all = {}, []
    for symbol, rows in raw.items():
        dates = [local_day(r["t"]) for r in rows]
        expected = us_equity_session_dates(dates[0], dates[-1])
        covered = set(dates)
        coverage[symbol] = {
            "raw_records": len(rows),
            "all_records": len(adjusted[symbol]),
            "first": str(dates[0]),
            "last": str(dates[-1]),
            "duplicate_dates": len(dates) - len(covered),
            "invalid_OHLCV_rows": sum(not valid(r) for r in rows),
            "zero_volume_zero_trades": sum(dec(r["v"]) == 0 and r["n"] == 0 for r in rows),
            "expected_sessions_between_observed_endpoints": len(expected),
            "missing_sessions": sorted(str(x) for x in set(expected) - covered),
            "noncalendar_dates": sorted(str(x) for x in covered - set(expected)),
            "coverage_before_first_observed": (
                "unknown; no IPO/episode start inferred from first bar"
            ),
        }
        by_t = {r["t"]: r for r in adjusted[symbol]}
        max_diff = {k: Decimal(0) for k in PRICE_FIELDS}
        different_prices = differing_volume = 0
        for r in rows:
            a = by_t[r["t"]]
            factor = split_factor(symbol, local_day(r["t"]), date(2026, 10, 13), splits)
            different_prices += any(dec(r[k]) != dec(a[k]) for k in PRICE_FIELDS)
            differing_volume += dec(a["v"]) != dec(r["v"]) * factor
            for key in PRICE_FIELDS:
                max_diff[key] = max(max_diff[key], abs(dec(a[key]) - dec(r[key]) / factor))
        raw_all.append(
            {
                "symbol": symbol,
                "same_timestamp_keys": {r["t"] for r in rows} == set(by_t),
                "different_price_rows": different_prices,
                "all_minus_raw_div_known_split_max_abs": max_diff,
                "volume_not_equal_raw_times_known_split": differing_volume,
                "claim": (
                    "Observed split-compatible precision residuals only; all"
                    " not certified total wealth/cash"
                ),
            }
        )

    action_ledger = []
    for kind, rows in actions.items():
        for row in rows:
            asset = (
                row.get("symbol")
                or row.get("source_symbol")
                or row.get("acquirer_symbol")
                or row.get("new_symbol")
            )
            action_ledger.append(
                {
                    "action_type": kind,
                    "source_action": row,
                    "related_held_asset": asset,
                    "economic_effective_date": row.get("ex_date") or row.get("effective_date"),
                    "process_date_is_not_effective_date": True,
                    "actual_spendable_at": None,
                    "actual_share_or_cash_receipt": None,
                    "separate_new_asset": row.get("new_symbol") if kind == "spin_offs" else None,
                    "held_asset_policy": (
                        "Keep share basis and all rights. Acquirer does not canc"
                        "el continuing held shares. Unknown receipt/valuation ne"
                        "ver becomes zero."
                    ),
                }
            )
    save(
        DERIVED / "lifecycle-and-rights.json",
        {
            "actions": action_ledger,
            "GME_2025_warrant": {
                "action_id": "83d8ed5e-8d5a-4021-bf03-552c2b537dfe",
                "right": "1 GME.WS per10 source GME shares",
                "ex_date": "2025-10-03",
                "record_date": "2025-10-03",
                "payable_date": "2025-10-07",
                "process_date": "2025-10-07",
                "market_value": None,
                "actual_receipt": None,
                "source_all_equals_raw_at_2025_10_02_and_03": True,
                "cross_event_wealth_or_NAV_ready": False,
                "reason": (
                    "Stock price alone omits distinct warrant asset; no new-"
                    "asset price/receipt in accepted13objects"
                ),
            },
            "identifiers": (
                "CUSIPs anchor specific source actions only; not continu"
                "ous historical shareclass validity"
            ),
            "historical_first_visible": None,
        },
    )

    probe = json.loads(
        (
            ROOT / "reports/research/program/martin-luk-usic-20261013/local-case-input-probe.json"
        ).read_text()
    )
    old_cases = {
        (r["symbol"], r["probe_date"]): r
        for r in probe["cases"]
        if r["status"] == "actual_records_present"
    }
    clocks, features, grids, differences, minute_case_lookup = [], [], [], [], {}
    for request_id, payload in packets.items():
        if "bars" not in payload or "daily" in request_id:
            continue
        symbol, rows = next(iter(payload["bars"].items()))
        day = local_day(rows[0]["t"])
        by_ns = {pd.Timestamp(r["t"]).value: r for r in rows}
        expected = sorted(t.value for t in expected_us_equity_rth_bar_starts(day, 1))
        rth = [by_ns[t] for t in expected if t in by_ns]
        minute_case_lookup[(symbol, str(day))] = rows
        clock = {
            "request_id": request_id,
            "symbol": symbol,
            "day": str(day),
            "rows": len(rows),
            "rth_rows": len(rth),
            "rth_expected": len(expected),
            "rth_missing": [
                pd.Timestamp(t, tz="UTC").isoformat() for t in expected if t not in by_ns
            ],
            "premarket_rows": sum(
                pd.Timestamp(r["t"]).tz_convert(NY).time()
                < datetime.strptime("09:30", "%H:%M").time()
                for r in rows
            ),
            "duplicate_timestamps": len(rows) - len(by_ns),
            "bad_rows_retained": sum(not valid(r) for r in rows),
            "first_source_bar": rows[0],
            "last_source_bar": rows[-1],
        }
        daily_r = next(r for r in raw[symbol] if local_day(r["t"]) == day)
        clock["daily_vs_RTH_minute"] = {
            "daily_source": daily_r,
            "RTH_first_open": rth[0]["o"],
            "RTH_last_close": rth[-1]["c"],
            "RTH_high": max(dec(r["h"]) for r in rth),
            "RTH_low": min(dec(r["l"]) for r in rth),
            "RTH_volume": sum(dec(r["v"]) for r in rth),
            "claim": (
                "Comparative aggregates do not certify provider daily pu"
                "blication time, auction filters or historicalfirstseen"
            ),
        }
        if (symbol, str(day)) in old_cases:
            old = old_cases[(symbol, str(day))]
            old_path = ROOT / old["path"]
            prior_binding = next(x for x in probe["input_bindings"] if x["path"] == old["path"])
            assert bound(old_path)["sha256"] == prior_binding["sha256"]
            start = pd.Timestamp(datetime.combine(day, datetime.min.time(), NY)).tz_convert("UTC")
            end = start + pd.Timedelta(days=1)
            table = pq.read_table(
                old_path,
                filters=[
                    ("symbol", "=", symbol),
                    ("timestamp", ">=", start.to_pydatetime()),
                    ("timestamp", "<", end.to_pydatetime()),
                ],
            )
            cache = {pd.Timestamp(r["timestamp"]).value: r for r in table.to_pylist()}
            factor = split_factor(symbol, day, date(2026, 10, 13), splits)
            matches = unexplained = 0
            for stamp in sorted(set(cache) | set(by_ns)):
                a, r = cache.get(stamp), by_ns.get(stamp)
                if a is None or r is None:
                    differences.append(
                        {
                            "symbol": symbol,
                            "day": str(day),
                            "t_ns": stamp,
                            "kind": "missing_clock_in_one_vintage",
                            "cached": {k: str(v) for k, v in a.items()} if a else None,
                            "raw": r,
                        }
                    )
                    unexplained += 1
                    continue
                field_diff = {
                    k: dec(a[long]) / 1 - dec(r[k]) / factor
                    for k, long in zip(
                        PRICE_FIELDS, ("open", "high", "low", "close", "vwap"), strict=True
                    )
                }
                volume_diff = dec(a["volume"]) - dec(r["v"]) * factor
                n_diff = dec(a["trade_count"]) - dec(r["n"])
                explained = (
                    all(abs(x) <= Decimal("0.005000001") for x in field_diff.values())
                    and volume_diff == 0
                    and n_diff == 0
                )
                matches += explained
                if not explained:
                    unexplained += 1
                    differences.append(
                        {
                            "symbol": symbol,
                            "day": str(day),
                            "t_ns": stamp,
                            "kind": "unexplained_vintage_or_rounding_delta",
                            "cached": {k: str(v) for k, v in a.items()},
                            "raw": r,
                            "known_split_factor": factor,
                            "price_delta": field_diff,
                            "volume_delta": volume_diff,
                            "trade_count_delta": n_diff,
                        }
                    )
            clock["cached_all_raw_reconciliation"] = {
                "file": prior_binding,
                "cache_rows": len(cache),
                "raw_rows": len(by_ns),
                "split_compatible_rows": matches,
                "unexplained_rows": unexplained,
                "normalized_price_tolerance": "0.005000001",
                "tolerance_role": (
                    "Diagnosticprecision classification, not exact raw-price recovery or deletion"
                ),
            }

        prior_day = previous_us_equity_session(day)
        before = [r for r in raw[symbol] if local_day(r["t"]) <= prior_day]
        calendar = us_equity_session_dates(local_day(raw[symbol][0]["t"]), prior_day)
        idx = pd.DatetimeIndex(calendar)
        by_day = {local_day(r["t"]): r for r in before}
        normalized = {
            d: dec(r["c"]) / split_factor(symbol, d, day, splits)
            for d, r in by_day.items()
            if valid(r) and not (r["v"] == 0 and r["n"] == 0)
        }
        closes = pd.DataFrame(
            {symbol: [float(normalized.get(d, Decimal("NaN"))) for d in calendar]}, index=idx
        )
        opens = pd.DataFrame(
            {
                symbol: [
                    float(dec(by_day[d]["o"]) / split_factor(symbol, d, day, splits))
                    if d in normalized
                    else float("nan")
                    for d in calendar
                ]
            },
            index=idx,
        )
        clean, _, hygiene = sanitize_price_matrices(closes, opens)
        suffix = []
        for d, value in zip(calendar, clean[symbol], strict=True):
            if pd.isna(value):
                suffix = []
            else:
                suffix.append(d)
        row = {
            "symbol": symbol,
            "decision_day": str(day),
            "prior_completed_day": str(prior_day),
            "effective_time_proxy": datetime.combine(
                day, datetime.strptime("09:30", "%H:%M").time(), NY
            ).isoformat(),
            "historical_first_visible": None,
            "feature_visibility": (
                "Current-vintage prior-day completion proxy; not historical release proof"
            ),
            "contiguous_clean_sessions": len(suffix),
            "hygiene_asof_prefix_only": hygiene.manifest(),
            "source_boundary_seed_is_life_episode_certified": False,
            "episode_id": f"source-symbol-window:{symbol}:{raw[symbol][0]['t']}",
            "dated_type_identity": (
                "Bounded source-company context only; broadhistorical eligibility/rank unaccepted"
            ),
            "crossrank": None,
            "full_plan_feature_ready": False,
            "AVWAP": None,
            "missing_AVWAP_packet": None,
            "EMA9": None,
            "EMA21": None,
            "EMA50": None,
            "rising_EMA21_lag5": None,
            "ADR20": None,
            "ADV20": None,
            "price_momentum21": None,
        }
        with localcontext() as ctx:
            ctx.prec = 60
            if len(suffix) >= 20:
                tail = [by_day[d] for d in suffix[-20:]]
                row["ADR20"] = sum(dec(r["h"]) / dec(r["l"]) - 1 for r in tail) / 20
                row["ADV20"] = sum(dec(r["c"]) * dec(r["v"]) for r in tail) / 20
            if len(suffix) >= 22:
                row["price_momentum21"] = normalized[suffix[-1]] / normalized[suffix[-22]] - 1
            if len(suffix) >= 63:
                for n in (9, 21, 50):
                    alpha = Decimal(2) / Decimal(n + 1)
                    value, values = normalized[suffix[0]], []
                    for d in suffix:
                        value = value if not values else alpha * normalized[d] + (1 - alpha) * value
                        values.append(value)
                    row[f"EMA{n}"] = value
                    if n == 21:
                        row["rising_EMA21_lag5"] = values[-1] > values[-6]
                lows = [dec(by_day[d]["l"]) / split_factor(symbol, d, day, splits) for d in suffix]
                anchors = [
                    i
                    for i in range(2, len(lows) - 2)
                    if all(lows[i] < lows[j] for j in (i - 2, i - 1, i + 1, i + 2))
                    and len(lows) - 1 - i <= 60
                ]
                if anchors:
                    tau = suffix[anchors[-1]]
                    row["missing_AVWAP_packet"] = {
                        "raw_RTH_VWAP_volume_start": str(tau) + "09:30NY",
                        "end": str(prior_day) + "sessionclose",
                        "anchor_confirmation_day": str(suffix[anchors[-1] + 2]),
                    }
        prefix_ids = [locators[("public_case_daily_raw", symbol, r["t"])] for r in before]
        row["raw_prefix_record_locators_sha256"] = hashlib.sha256(
            canonical(prefix_ids).encode()
        ).hexdigest()
        row["raw_prefix_bounds"] = [before[0]["t"], before[-1]["t"]] if before else []
        features.append(row)
        clocks.append(clock)

        for minute in range(1, 91):
            close = pd.Timestamp(
                datetime.combine(day, datetime.strptime("09:30", "%H:%M").time(), NY)
            ) + pd.Timedelta(minutes=minute)
            timeframe = 1 if minute < 15 else (5 if minute < 60 else 15)
            if timeframe > 1 and minute % timeframe:
                continue
            stamps = [
                (close - pd.Timedelta(minutes=k)).tz_convert("UTC").value
                for k in range(timeframe, 0, -1)
            ]
            parents = [by_ns.get(t) for t in stamps]
            event = {
                "symbol": symbol,
                "day": str(day),
                "grid_minutes": timeframe,
                "completed_at": close.isoformat(),
                "activation_proxy": (close + pd.Timedelta(minutes=1)).isoformat(),
                "extra_delay_activation_proxy": (close + pd.Timedelta(minutes=2)).isoformat(),
                "activation_before11": close + pd.Timedelta(minutes=1)
                < pd.Timestamp(
                    datetime.combine(day, datetime.strptime("11:00", "%H:%M").time(), NY)
                ),
                "source_parent_locators": [
                    locators[(request_id, symbol, r["t"])] for r in parents if r
                ],
                "missing_parent_minute_ns": [
                    t for t, r in zip(stamps, parents, strict=True) if r is None
                ],
            }
            if all(r is not None and valid(r) for r in parents):
                volume = sum(dec(r["v"]) for r in parents)
                event.update(
                    status="actual_completed_bar_component",
                    o=parents[0]["o"],
                    h=max(dec(r["h"]) for r in parents),
                    l=min(dec(r["l"]) for r in parents),
                    c=parents[-1]["c"],
                    v=volume,
                    vw=sum(dec(r["vw"]) * dec(r["v"]) for r in parents) / volume
                    if volume
                    else None,
                )
            else:
                event["status"] = "incomplete_or_invalid_parents_retained"
            grids.append(event)

    # Quote candidates are structural observations, not firmNBBO/fills.
    quotes = []
    for request_id, payload in packets.items():
        if "quotes" not in payload:
            continue
        rows = payload["quotes"]
        eligible = [
            r
            for r in rows
            if all(dec(r[k]) > 0 for k in ("bp", "ap", "bs", "as")) and dec(r["bp"]) <= dec(r["ap"])
        ]
        quotes.append(
            {
                "request_id": request_id,
                "source_records": len(rows),
                "crossed_records_retained": sum(dec(r["bp"]) > dec(r["ap"]) for r in rows),
                "source_conditions": sorted({c for r in rows for c in r.get("c", [])}),
                "first_structurally_valid_quote": eligible[0] if eligible else None,
                "first_uncrossed_ask_le501": next(
                    (r for r in eligible if dec(r["ap"]) <= 501), None
                ),
                "source_record_order_ns_preserved": True,
                "firm_NBBO_certified": False,
                "actual_order_fill_reconstructed": False,
                "historical_first_visible": None,
            }
        )
    save(
        DERIVED / "quote-context.json",
        {
            "contexts": quotes,
            "GME_2021_source_order": {
                "limit": "501",
                "quantity": 1,
                "created_second": "2021-01-28T11:01:07Z",
                "filled_displayed_second": "2021-01-28T11:03:56Z",
                "source_minute_at11_03": next(
                    r
                    for r in minute_case_lookup[("GME", "2021-01-28")]
                    if r["t"] == "2021-01-28T11:03:00Z"
                ),
                "interpretation": (
                    "Minute range contains501; source?condition/uncrossed qu"
                    "otes alone do not establish firmNBBO, actual fill seque"
                    "nce or private receipt accuracy"
                ),
            },
        },
    )
    csiq = minute_case_lookup[("CSIQ", "2025-12-22")]
    save(
        DERIVED / "CSIQ-execution-evidence.json",
        {
            "planned_trigger": "25.51",
            "planned_stop": "25.10",
            "selfreported_fill": "26.28",
            "plan_per_share_distance": "0.41",
            "filled_to_planned_stop_distance": "1.18",
            "quantity": None,
            "actual_exit": None,
            "P_and_L": None,
            "interpretation": (
                "Source per-share price geometry, not a realized trade r"
                "eturn. Unknownquantity cannot be resized fromfill."
            ),
            "RTH09_30_raw": next(r for r in csiq if r["t"] == "2025-12-22T14:30:00Z"),
            "timestamps_whose_range_contains_selfreported26_28": [
                r["t"] for r in csiq if dec(r["l"]) <= Decimal("26.28") <= dec(r["h"])
            ],
            "fill_time_certified": False,
            "duplicate_order_source_counterexample_retained": True,
        },
    )
    save(
        DERIVED / "daily-coverage-and-adjustment.json",
        {
            "coverage": coverage,
            "raw_all": raw_all,
            "source_records": len(canonical_records),
            "numeric_source_literals": (
                "Decimal values serializedastext; original HTTP entities retained"
            ),
            "no_total_return_series_claim": True,
        },
    )
    save(
        DERIVED / "minute-clock-and-vintage.json",
        {
            "cases": clocks,
            "cached_files_reconciled": len(old_cases),
            "not_authorfill_date_imputation": True,
        },
    )
    save(
        DERIVED / "causal-feature-candidates.json",
        {
            "features": features,
            "formula_scope": (
                "v2 price/volume formulas underdeclaredsource-windowseed"
                "; no ranking/trading/strategyreturn"
            ),
            "accepted_plan_eligibility_or_seed_connection": False,
            "current_vintage_only": True,
        },
    )
    save(
        DERIVED / "completed-bar-clock-components.json",
        {
            "events": grids,
            "orders_submitted": 0,
            "claim": (
                "Complete real input aggregates and clocks only, not strategy opportunity or fills"
            ),
        },
    )
    (DERIVED / "cached-minute-version-differences.jsonl").write_text(
        "".join(canonical(r) + "\n" for r in differences)
    )
    resource_receipt = {
        "CPU_seconds": time.process_time() - START_CPU,
        "max_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "HTTP_requests": 0,
        "fits": 0,
        "strategy_returns": 0,
        "orders": 0,
    }
    save(DERIVED / "build-resource.json", resource_receipt)
    result = {
        "actual_data_requests": 13,
        "actual_complete_entity_bytes": 2347300,
        "source_records_retained": len(canonical_records),
        "daily_raw_rows": sum(len(r) for r in raw.values()),
        "minute_case_days": len(clocks),
        "feature_candidates": len(features),
        "price_volume_feature_candidates_with63sessions": sum(
            r["contiguous_clean_sessions"] >= 63 for r in features
        ),
        "completed_grid_events": dict(Counter(r["status"] for r in grids)),
        "all_cached_vintage_differences_preserved": len(differences),
        "bounded_component_input_accepted_by_author": False,
        "independent_acceptance_required": True,
        "full_method_input_ready": False,
        "economic_execution_admitted": False,
        "specific_full_method_gaps": [
            (
                "Seven source-selected symbols cannot establish historic"
                "alTop50 or a broad unbiasedeligiblepool"
            ),
            (
                "Eight frozen single-day minute packets cannot form cont"
                "inuous2024–25 orderedexecution or the pre-anchorAVWAP i"
                "nput"
            ),
            "Sourcewindow EMA seed/type/episode continuity is not broadhistoricaleligibility proof",
            (
                "GME2025 distributedGME.WS value/receipt packet missing;"
                " stockallpriceequalsrawnotwholewealth"
            ),
            (
                "?condition sourcequotes do not certifyfirmNBBO/private "
                "fills; barpathscenarios remainhypotheses"
            ),
        ],
        "valuable_legal_components": [
            "Sourceoriginalraw/all/actions, fullordinal/hash records anddatacoverage",
            (
                "Current-vintage per-name ADR20/ADV20/momentum21/source-"
                "windowEMA values andcausal prefix"
            ),
            "Completed1/5/15minute inputclock parents and gaps; specificcached-version residuals",
            "GME sourceorderclock/rawquote context, CSIQ planned/fillpricebasis and SMCI10:1 split",
            "Distinct GME.WS heldassetright retained, not erased orvaluedzero",
        ],
        "resource": resource_receipt,
        "no_global_market_impossibility_or_method_refutation": True,
    }
    save(OUT / "actual-component-result.json", result)
    print(json.dumps(result, default=encode))


if __name__ == "__main__":
    main()
