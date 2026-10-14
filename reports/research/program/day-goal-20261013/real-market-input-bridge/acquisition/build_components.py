"""Current-vintage source arithmetic for four preselected input cases, never NAV."""

from __future__ import annotations

import hashlib
import json
import math
import resource
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/root/codex-test/open-composer")
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent
CPU_STARTED = time.process_time()
WALL_STARTED = time.monotonic()
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402
from acquire import eligible_quote, ns, save, sha, utc  # noqa: E402

from open_composer.market_sessions import (  # noqa: E402
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.research.features.price_hygiene import sanitize_price_matrices  # noqa: E402

NY = ZoneInfo("America/New_York")
EPISODES = {
    "AAPL": ("EP320193_COMMON_2020", "2020-07-01", "2020-09-04"),
    "ATVI": ("EP718877_COMMON_PREMERGER", "2023-09-01", "2023-10-20"),
}


def row_hash(raw):
    body = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(body).hexdigest()


def jsonl(path, rows):
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def close_clock(day):
    d = date.fromisoformat(day)
    close = us_equity_session_close(d)
    return datetime.combine(d, close, NY).astimezone(UTC).isoformat() if close else None


def positive(value):
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError):
        return False


def raw_record(raw, attempt, index, kind, category=None):
    return {
        "symbol": attempt["params"]["symbols"],
        "episode_id": EPISODES[attempt["params"]["symbols"]][0],
        "kind": kind,
        "category": category,
        "source_ordinal": index,
        "raw": raw,
        "source_row_sha256": row_hash(raw),
        "entity_path": attempt["entity_path"],
        "entity_sha256": attempt["entity_sha256"],
        "request_id": attempt["input_id"],
        "page": attempt["page"],
        "actual_fetched_at": attempt["actual_fetched_at"],
        "historical_first_published_at": None,
        "historical_first_visible_at": None,
    }


def main():
    cpu0, wall0 = CPU_STARTED, WALL_STARTED
    assert sha(PARENT / "package-manifest.json") == (
        "e1f20bd777aaa3356bdc9ec575cdb67243ae9bbb010885b97c8156a15fc5faf3"
    )
    assert sha(PARENT / "partial-input/package-manifest.json") == (
        "927ea64e417e0b2c512eda40ab592b3a3e3d47d31d620820527ecfd23300779f"
    )
    interface = json.loads((OUT / "model-input-interface.json").read_text())
    manifest = json.loads((OUT / "request-manifest.json").read_text())
    ledger = json.loads((OUT / "data-request-ledger.json").read_text())
    inputs = {item["id"]: item for item in ledger["inputs"]}
    specs = {item["id"]: item for item in manifest["requests"]}
    all_records, actions, bars, selected = [], [], {}, {}
    quote_diagnostics = []
    for attempt in ledger["attempts"]:
        if attempt.get("http_status") != 200:
            continue
        entity = ROOT / attempt["entity_path"]
        assert sha(entity) == attempt["entity_sha256"]
        payload = json.loads(entity.read_bytes())
        spec = specs[attempt["input_id"]]
        symbol = spec["params"]["symbols"]
        if spec["kind"] == "actions":
            for category, rows in payload.get("corporate_actions", {}).items():
                for index, raw in enumerate(rows):
                    rec = raw_record(raw, attempt, index, "action", category)
                    rec["symbol"] = symbol
                    rec["episode_id"] = EPISODES[symbol][0]
                    rec["action_type"] = category
                    rec["ex_date"] = raw.get("ex_date")
                    rec["effective_date"] = raw.get("ex_date", raw.get("effective_date"))
                    rec["economic_effective_date"] = rec["effective_date"]
                    rec["economic_effective_timestamp"] = None
                    rec["process_date"] = raw.get("process_date")
                    rec["record_date"] = raw.get("record_date")
                    rec["payable_date"] = raw.get("payable_date")
                    rec["actual_spendable_at"] = None
                    rec["amount_or_ratio_not_account_receipt"] = True
                    if category == "cash_dividends":
                        rec["cash_per_eligible_share"] = raw.get("rate")
                        rec["cash_per_old_share"] = raw.get("rate")
                        rec["share_basis"] = "one share on stated ex-date, before any later split"
                        rec["economic_entitlement_start"] = "ex_date; not payable/process_date"
                    elif category == "forward_splits":
                        rec["new_shares_per_old_share"] = float(
                            Decimal(str(raw["new_rate"])) / Decimal(str(raw["old_rate"]))
                        )
                        rec["share_basis"] = "new_rate/old_rate; continuing common shares"
                    elif category == "cash_mergers":
                        rec["cash_per_eligible_old_share"] = raw.get("rate")
                        rec["share_basis"] = (
                            "eligible acquiree common share immediately pre-effective"
                        )
                        rec["eligibility_exclusions_and_clock_basis"] = {
                            "canonical_contract": str(
                                (PARENT / "lifecycle-contract.json").relative_to(ROOT)
                            ),
                            "sha256": sha(PARENT / "lifecycle-contract.json"),
                            "qualification": "Eligible old common; canonical exclusions apply",
                        }
                    else:
                        rec["share_basis"] = "unmapped; dependent arithmetic blocked"
                    actions.append(rec)
                    all_records.append(rec)
        else:
            rows = payload.get(spec["kind"], {}).get(symbol, [])
            recs = [raw_record(raw, attempt, i, spec["kind"]) for i, raw in enumerate(rows)]
            all_records.extend(recs)
            if spec["kind"] == "bars":
                adjustment = spec["params"]["adjustment"]
                bars.setdefault((symbol, adjustment), []).extend(recs)
            else:
                valid = [r for r in recs if eligible_quote(r["raw"], spec["params"])]
                valid.sort(key=lambda r: (ns(r["raw"]["t"]), r["source_ordinal"]))
                best = valid[0] if valid else None
                selected[spec["id"]] = best
                quote_diagnostics.append(
                    {
                        "request_id": spec["id"],
                        "status": inputs[spec["id"]]["status"],
                        "requested_window": spec["params"],
                        "raw_quote_count": len(recs),
                        "positive_non_crossed_with_positive_sizes_count": len(valid),
                        "full_window_history_complete": not bool(payload.get("next_page_token")),
                        "selected_source_row_sha256": best["source_row_sha256"] if best else None,
                        "condition_values_preserved": sorted(
                            {str(r["raw"].get("c")) for r in recs}
                        ),
                        "condition_codes_and_size_units_not_independently_certified": True,
                        "hypothetical_fill_or_capacity_claim": False,
                    }
                )
    jsonl(OUT / "normalized-source-records.jsonl", all_records)
    save(OUT / "normalized-actions.json", actions)
    save(OUT / "quote-window-coverage.json", quote_diagnostics)
    jsonl(OUT / "selected-quotes.jsonl", [v for v in selected.values() if v])
    features, returns, hygiene, session_coverage = [], [], [], []
    bar_lookup = {}
    for symbol, (episode, start, end) in EPISODES.items():
        sessions = [
            d.isoformat()
            for d in us_equity_session_dates(date.fromisoformat(start), date.fromisoformat(end))
        ]
        raw_bars = {}
        for rec in bars.get((symbol, "raw"), []):
            day = (
                datetime.fromisoformat(rec["raw"]["t"].replace("Z", "+00:00"))
                .astimezone(NY)
                .date()
                .isoformat()
            )
            rec["session"] = day
            rec["ghost"] = rec["raw"].get("v") == 0 and rec["raw"].get("n", 0) == 0
            rec["source_timestamp_is_day_bucket_not_first_visibility"] = True
            if day in sessions:
                assert day not in raw_bars, "Ambiguous duplicate daily endpoint"
                raw_bars[day] = rec
                bar_lookup[(symbol, day)] = rec
        symbol_actions = [a for a in actions if a["symbol"] == symbol]
        act_by_day = {}
        for action in symbol_actions:
            act_by_day.setdefault(action["effective_date"], []).append(action)
        native_raw = [
            float(raw_bars[d]["raw"]["c"])
            if d in raw_bars and not raw_bars[d]["ghost"] and positive(raw_bars[d]["raw"]["c"])
            else float("nan")
            for d in sessions
        ]
        native_open = [
            float(raw_bars[d]["raw"]["o"])
            if d in raw_bars and not raw_bars[d]["ghost"] and positive(raw_bars[d]["raw"]["o"])
            else float("nan")
            for d in sessions
        ]
        symbol_returns = []
        action_scope_complete = (
            inputs.get(f"{symbol}_actions_all", {}).get("status") == "complete_bounded_response"
        )
        for i, day in enumerate(sessions):
            prefix_index = pd.to_datetime(sessions[: i + 1])
            frame = pd.DataFrame({symbol: native_raw[: i + 1]}, index=prefix_index)
            opens = pd.DataFrame({symbol: native_open[: i + 1]}, index=prefix_index)
            prefix_actions = [d for d in act_by_day if d and d <= day]
            clean, _, report = sanitize_price_matrices(
                frame,
                opens,
                known_corporate_actions={symbol: prefix_actions},
                corporate_action_feed="bound current-vintage alltype actions; visibility unknown",
            )
            hygiene.append(
                {
                    "symbol": symbol,
                    "decision_session": day,
                    "prefix_last_session": day,
                    **report.manifest(),
                }
            )
            todays = act_by_day.get(day, [])
            terminal = any(a["category"] == "cash_mergers" for a in todays)
            split = Decimal(1)
            cash = Decimal(0)
            unsupported = False
            for action in todays:
                if action["category"] == "forward_splits":
                    split *= Decimal(str(action["raw"]["new_rate"])) / Decimal(
                        str(action["raw"]["old_rate"])
                    )
                elif action["category"] == "cash_dividends":
                    cash += Decimal(str(action["raw"]["rate"]))
                else:
                    unsupported = True
            current = raw_bars.get(day)
            previous = raw_bars.get(sessions[i - 1]) if i else None
            reason = None
            if not action_scope_complete:
                reason = "alltype action process-bound response incomplete/unavailable"
            elif terminal:
                reason = "Terminal right retained; ghost stock close is not cash receipt"
            elif not current:
                reason = "no raw daily bar in exact acquired bound"
            elif current["ghost"]:
                reason = "vendor ghost placeholder volume=trade_count=0"
            elif not i or not previous or previous["ghost"]:
                reason = "missing previous valid consecutive session close"
            elif unsupported:
                reason = "unmapped action type prevents per-old-share arithmetic"
            elif not math.isfinite(clean.iloc[i, 0]) or not math.isfinite(clean.iloc[i - 1, 0]):
                reason = "causal decision-prefix price hygiene excludes endpoint"
            value = None
            if not reason:
                prev_close = Decimal(str(previous["raw"]["c"]))
                this_close = Decimal(str(current["raw"]["c"]))
                value = float((split * this_close + cash) / prev_close - 1)
            rt = {
                "episode_id": episode,
                "symbol": symbol,
                "session": day,
                "r_t": value,
                "status": "current_vintage_candidate" if value is not None else "blocked",
                "reason": reason,
                "split_ratio_new_per_previous_share": float(split),
                "economic_distribution_per_previous_share": float(cash),
                "formula": "(split_ratio * close_t + cash_per_previous_share) / close_previous - 1",
                "current_bar": current,
                "previous_bar": previous,
                "effective_action_ids": [a["raw"]["id"] for a in todays],
                "no_action_consistency_basis": (
                    "Complete current inclusive process-date response; "
                    "universal action absence uncertified"
                ),
                "actual_spendable_cash_assumed": False,
                "historical_first_visible_at": None,
            }
            symbol_returns.append(rt)
            returns.append(rt)
            tail = symbol_returns[max(0, i - 4) : i + 1]
            six_days = sessions[max(0, i - 5) : i + 1]
            tail_valid = len(tail) == 5 and all(r["r_t"] is not None for r in tail)
            six_hygiene_valid = len(six_days) == 6 and all(
                math.isfinite(clean.loc[pd.Timestamp(d), symbol]) for d in six_days
            )
            available = tail_valid and six_hygiene_valid
            values = [r["r_t"] for r in tail] if available else []
            mean = math.fsum(values) / 5 if available else None
            clock = close_clock(day)
            source_times = [r["actual_fetched_at"] for d, r in raw_bars.items() if d in six_days]
            source_times += [a["actual_fetched_at"] for a in symbol_actions]
            split_trigger = any(a["category"] == "forward_splits" for a in todays)
            feature = {
                "episode_id": episode,
                "symbol": symbol,
                "decision_session": day,
                "class": "B" if available else "retained_unavailable",
                "Ret_D1": values[-1] if available else None,
                "Ret_W1": math.prod(1 + r for r in values) - 1 if available else None,
                "STD_W1": math.sqrt(math.fsum((r - mean) ** 2 for r in values) / 5)
                if available
                else None,
                "STD_ddof": 0,
                "units": "decimal return; daily population volatility, not annualized",
                "six_consecutive_endpoint_sessions": six_days,
                "five_return_inputs": [r["r_t"] for r in tail],
                "source_bar_row_sha256": [
                    raw_bars[d]["source_row_sha256"] for d in six_days if d in raw_bars
                ],
                "action_entity_bindings": sorted({a["entity_sha256"] for a in symbol_actions}),
                "historical_event_or_observation_at": clock,
                "event_clock_basis": (
                    "Nominal regular-session close from registered calendar; "
                    "original publication/late corrections unknown"
                ),
                "historical_first_published_at": None,
                "historical_first_visible_at": None,
                "actual_fetched_at": max(source_times) if source_times else None,
                "current_vintage_component_available_at": max(source_times)
                if source_times
                else None,
                "split_trigger_signal_excluded": split_trigger,
                "source_component_usable_conditionally": available and not split_trigger,
                "unavailability_reason": None
                if available
                else (reason or "fewer than five valid returns/six prefix-valid endpoints"),
                "strict_APP_input_ready": False,
                "full7_ready": False,
                "historical_universe_eligibility_certified": False,
            }
            features.append(feature)
            session_coverage.append(
                {
                    "episode_id": episode,
                    "symbol": symbol,
                    "session": day,
                    "raw_bar_present": current is not None,
                    "ghost": bool(current and current["ghost"]),
                    "price3_numerically_available": available,
                    "split_signal_exclusion": split_trigger,
                    "component_eligibility": "current-vintage source consistency only",
                    "historical_visible_eligibility": "unknown",
                    "APP_eligible": False,
                    "holding_or_right_deleted_when_input_unavailable": False,
                    "terminal_right_retained": symbol == "ATVI" and day >= "2023-10-13",
                    "reason": feature["unavailability_reason"],
                }
            )
    jsonl(OUT / "daily-return-inputs.jsonl", returns)
    jsonl(OUT / "price3-candidates.jsonl", features)
    jsonl(OUT / "prefix-hygiene.jsonl", hygiene)
    jsonl(OUT / "session-coverage.jsonl", session_coverage)
    labels = []
    for case in interface["frozen_cases"]:
        symbol = case["symbol"]
        entry_day = case["entry_session"]
        exit_day = case.get("exit_session", case.get("scheduled_exit_session"))
        entry = selected.get(f"{symbol}_quote_{entry_day}")
        exit_quote = selected.get(f"{symbol}_quote_{exit_day}")
        chain = [
            a
            for a in actions
            if a["symbol"] == symbol
            and a["effective_date"]
            and entry_day < a["effective_date"] <= exit_day
        ]
        terminal_chain = any(a["category"] == "cash_mergers" for a in chain)
        ratio = Decimal(1)
        cash = Decimal(0)
        unmapped = False
        for action in chain:
            if action["category"] == "forward_splits":
                ratio *= Decimal(str(action["raw"]["new_rate"])) / Decimal(
                    str(action["raw"]["old_rate"])
                )
            elif action["category"] == "cash_dividends":
                cash += ratio * Decimal(str(action["raw"]["rate"]))
            else:
                unmapped = True
        action_complete = inputs[f"{symbol}_actions_all"]["status"] == "complete_bounded_response"
        usable = bool(entry and exit_quote and action_complete and not unmapped)
        entry_mid = (
            (Decimal(str(entry["raw"]["bp"])) + Decimal(str(entry["raw"]["ap"]))) / 2
            if entry
            else None
        )
        exit_mid = (
            (Decimal(str(exit_quote["raw"]["bp"])) + Decimal(str(exit_quote["raw"]["ap"]))) / 2
            if exit_quote
            else None
        )
        current_times = [q["actual_fetched_at"] for q in (entry, exit_quote) if q]
        current_times += [a["actual_fetched_at"] for a in actions if a["symbol"] == symbol]
        labels.append(
            {
                "case_id": case["id"],
                "episode_id": case["episode_id"],
                "symbol": symbol,
                "decision_session": case["decision_session"],
                "nominal_signal_close_at": close_clock(case["decision_session"]),
                "entry_session": entry_day,
                "scheduled_exit_session": exit_day,
                "entry_quote": entry,
                "exit_quote": exit_quote,
                "entry_mid": float(entry_mid) if entry_mid else None,
                "exit_mid": float(exit_mid) if exit_mid else None,
                "exit_common_shares_per_entry_old_share": float(ratio)
                if not terminal_chain
                else None,
                "cash_distribution_entitlement_per_entry_share": float(cash),
                "gross_quote_entitlement_label": float((ratio * exit_mid + cash) / entry_mid - 1)
                if usable
                else None,
                "formula": (
                    "(exit_share_ratio * exit_mid + cash_entitlement_per_entry_share) "
                    "/ entry_mid - 1"
                ),
                "status": "B_current_vintage_arithmetic_candidate"
                if usable
                else "retained_blocked_label",
                "blocked_reason": None
                if usable
                else (
                    "No exit quote in acquired Oct13window; terminal receivable retained"
                    if terminal_chain
                    else "missing quote or unresolved action chain"
                ),
                "effective_action_ids": [a["raw"]["id"] for a in chain],
                "action_entity_bindings": sorted(
                    {a["entity_sha256"] for a in actions if a["symbol"] == symbol}
                ),
                "no_action_consistency_basis": (
                    "Complete provider alltype process-bound response; "
                    "universal absence uncertified"
                ),
                "historical_event_or_observation_at": exit_quote["raw"]["t"]
                if exit_quote
                else None,
                "retrospective_hypothetical_endpoint_mature_at": exit_quote["raw"]["t"]
                if usable
                else None,
                "hypothetical_maturity_assumption": (
                    "Endpoint times and current action facts assumed available at event time; "
                    "historical publication unknown"
                ),
                "historical_first_published_at": None,
                "historical_first_visible_at": None,
                "actual_fetched_at": max(current_times),
                "actual_current_candidate_mature_at": max(current_times) if usable else None,
                "terminal_cash_receivable_per_eligible_old_share": float(
                    next(a["raw"]["rate"] for a in chain if a["category"] == "cash_mergers")
                )
                if terminal_chain
                else None,
                "terminal_right_source": [a for a in chain if a["category"] == "cash_mergers"],
                "terminal_effective_timestamp": None,
                "actual_spendable_at": None,
                "missing_exit_position_state": (
                    "Retain eligible old-share claim; valuation/delivery unknown"
                )
                if not exit_quote
                else None,
                "NBBO_fill_or_size_units_certified": False,
                "quote_conditions_preserved_not_a_new_filter": True,
                "strict_APP_input_ready": False,
                "economic_or_strategy_return": False,
            }
        )
    save(OUT / "quote-label-candidates.json", labels)
    obligations = [
        a
        for a in actions
        if a["symbol"] == "AAPL"
        and a["effective_date"] in ("2020-08-07", "2020-08-31")
        or a["category"] == "cash_mergers"
    ]
    save(
        OUT / "held-asset-obligations.json",
        {
            "actions": obligations,
            "missing_inputs_never_zero_or_cancel_holdings": True,
            "actual_account_positions_assumed": False,
            "no_account_cash_receipts_available": True,
            "terminal_case": next(x for x in labels if x["case_id"] == "ATVI_terminal_noquote"),
        },
    )
    eligible_features = [r for r in features if r["Ret_D1"] is not None]
    summary = {
        "schema_version": 1,
        "generated_at_utc": utc(),
        "verdict": "actual_current_vintage_components_available_strict_APP_not_admitted",
        "raw_numeric_source_records": len(all_records),
        "raw_and_all_bar_records": sum(len(v) for v in bars.values()),
        "raw_bar_records": sum(len(v) for (s, a), v in bars.items() if a == "raw"),
        "raw_quote_records": sum(r["kind"] == "quotes" for r in all_records),
        "action_records": len(actions),
        "fixed_episodes": 2,
        "fixed_label_cases": 4,
        "calendar_session_rows": len(features),
        "price3_numerical_rows": len(eligible_features),
        "price3_usable_non_split_trigger_rows": sum(
            r["source_component_usable_conditionally"] for r in features
        ),
        "full7_rows": 0,
        "strict_APP_rows": 0,
        "actual_0945_endpoint_quotes": sum(v is not None for v in selected.values()),
        "current_vintage_gross_quote_label_candidates": sum(
            r["gross_quote_entitlement_label"] is not None for r in labels
        ),
        "retained_blocked_label_cases": [
            r["case_id"] for r in labels if r["gross_quote_entitlement_label"] is None
        ],
        "earliest_complete_price3_per_episode": {
            s: next((r for r in features if r["symbol"] == s and r["Ret_D1"] is not None), None)
            for s in EPISODES
        },
        "fixed_decision_price3": [
            r
            for r in features
            if any(
                r["symbol"] == c["symbol"] and r["decision_session"] == c["decision_session"]
                for c in interface["frozen_cases"]
            )
        ],
        "label_values": [
            {
                k: r[k]
                for k in (
                    "case_id",
                    "entry_mid",
                    "exit_mid",
                    "exit_common_shares_per_entry_old_share",
                    "gross_quote_entitlement_label",
                    "retrospective_hypothetical_endpoint_mature_at",
                    "actual_current_candidate_mature_at",
                )
            }
            for r in labels
        ],
        "first_visibility_check_stopped": True,
        "historical_first_visible_at": None,
        "source_first_seen_fact": (
            "Schemas lack historical publication/revision timestamp; Date is current HTTP clock; "
            "asof controls symbol mapping; provider CA creation time unguaranteed"
        ),
        "known_limits": [
            "Two frozen episodes and four labels; no market-wide feasibility inference",
            "Process-bound CA response supports conditional chain; universal absence uncertified",
            "All-adjusted bars diagnostic only; never feed price3 or NBBO label sharebasis",
            "Unknown first-visible/correction vintage blocks strict APP causal admission",
            "Quote conditions retained; execution, latency, units, capacity/receipt uncertified",
            "Missing RF/ETB/top500/8year/30residual/252PCA do not block independent price3",
            "No full7, two-stock ranks, median substitutes, 39factor replication, fits or NAV",
        ],
        "economic_computations": 0,
        "model_fits": 0,
        "orders": 0,
        "parent_v2_and_partial_preserved": True,
        "next_action": (
            "Model-owner independent component acceptance and scientific choice; "
            "material deltas reviewed by7b"
        ),
    }
    save(OUT / "result.json", summary)
    receipt = {
        "cpu_seconds": time.process_time() - cpu0,
        "wall_seconds": time.monotonic() - wall0,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "numeric_source_record_reads": len(all_records),
        "source_entity_files": len(ledger["attempts"]),
        "new_data_requests": 0,
        "economic_computations": 0,
        "model_fits": 0,
    }
    save(OUT / "component-build-resource-receipt.json", receipt)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "price3_numerical_rows",
                    "price3_usable_non_split_trigger_rows",
                    "current_vintage_gross_quote_label_candidates",
                    "retained_blocked_label_cases",
                    "label_values",
                )
            }
        )
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
