"""Read completed native evidence; do not run accounts or change their semantics."""

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date

import pandas as pd
from common import F1, INPUTS, OUT, ROOT, digest, save, stamp

from open_composer.market_sessions import us_equity_session_dates
from open_composer.research.agent_workflow import validate_results

BATCH = "q1-2024-attempt-cap-v1"
NATIVE = OUT / "native-runs" / BATCH


def read(folder, name):
    return json.loads((folder / f"{name}.json").read_text())


def day_of(ns):
    return str(pd.Timestamp(ns, unit="ns", tz="UTC").tz_convert("America/New_York").date())


def observed_marks(folder):
    peak, worst, exposure, n, stale = 20000.0, 0.0, 0.0, 0, 0
    with (folder / "minute-account.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["all_positive_holdings_current"] != "True":
                stale += 1
                continue
            equity, gross = float(row["equity"]), float(row["gross"])
            peak = max(peak, equity)
            worst = min(worst, 100 * (equity / peak - 1))
            exposure += gross / equity
            n += 1
    return dict(drawdown_pct=worst, mean_gross=exposure / n, observations=n, stale=stale)


def audit_arm(arm, confirmations, dates):
    folder = NATIVE / arm
    result = read(folder, "result")
    labels = read(folder, "completed-labels")
    proposals = read(folder, "proposals")
    events = read(folder, "execution-source-events")
    intents = read(folder, "native-intents")
    assert result["status"] == "complete_observed_conditional"
    for field in ("open_positions", "open_orders", "reservations", "unknown_reasons"):
        assert not result[field], (arm, field, result[field])
    assert result["positive_fills_without_actual_freshness"] == 0
    assert result["retained_book_fills"] == 0
    assert result["observed_account_days"] == result["calendar_sessions"] == len(dates)
    names = set(read(F1, "universe")["symbols"])
    coverage = read(folder, "coverage")
    assert len(names) == 29 and [c["day"] for c in coverage] == dates
    for row in coverage:
        assert set(row["symbols"]) == names
        for q in row["symbols"].values():
            assert q["received_valid"] + q["missing_invalid"] == q["expected"]
    equity = pd.read_csv(folder / "equity.csv")
    assert equity.day.tolist() == dates
    assert math.isclose(equity.equity.iloc[-1], result["native_cash"], abs_tol=1e-7)
    cashflow = sum(
        (-1 if e["action"] == "buy" else 1) * e["quantity"] * e["price"] - e["fee"] for e in events
    )
    positive = [e for e in events if e["quantity"] > 0]
    residual = result["net_dollars"] - cashflow
    assert abs(residual) <= 0.011 * len(positive) + 1e-6
    fees = sum(e["fee"] for e in events)
    assert math.isclose(fees, result["fees"], abs_tol=1e-7)
    assert math.isclose(sum(r["native_net"] for r in labels), cashflow, abs_tol=1e-6)
    assert math.isclose(sum(r["total_fees"] for r in labels), fees, abs_tol=1e-6)
    for e in positive:
        assert e["quantity"] == int(e["quantity"])
        # Native USD Money rounds the 10bp commission to cents at the callback.
        assert abs(e["fee"] - e["quantity"] * e["price"] * 0.001) <= 0.005 + 1e-9
        assert math.isclose(e["fee"] * 100, round(e["fee"] * 100), abs_tol=1e-7)
        witness = e["source_event_freshness"]
        assert witness["fresh"] and not e["retained_book_execution"]
        assert witness["actual_callback_ns"] == e["native_ns"]
        assert witness["actual_applied_book_ns"] == witness["source_event_ns"]
        assert witness["current_minute"] and witness["exact_source_price"]
        if e["action"] == "buy":
            available = e["actual_cash_before"] - e["unsettled_before"] - e["other_pending_cash"]
            assert e["quantity"] * e["price"] + e["fee"] <= available + 0.011
            assert e["price"] <= e["reference"] * 1.005 + 1e-7
    ordinal, counts, proposal_rows = {}, Counter(), []
    buys = defaultdict(list)
    for e in events:
        if e["action"] == "buy":
            buys[e["intent_id"]].append(e)
    stops = [r for r in labels if "stop" in r["exit_reason"]]
    for p in proposals:
        assert p["action"] == "A"
        if not p.get("admitted"):
            continue
        key = p["symbol"], p["day"]
        counts[key] += 1
        ordinal[p["intent_id"]] = counts[key]
        assert counts[key] <= (1 if arm == "B" else 3)
        confirmation = confirmations[p["confirmation_id"]]
        assert confirmation["legal"]
        decision_ns = pd.Timestamp(p["decision_time"]).value
        assert confirmation["end_ns"] == decision_ns
        prior_stops = [
            r["actual_exit_ns"]
            for r in stops
            if r["symbol"] == p["symbol"] and r["actual_exit_ns"] < decision_ns
        ]
        latest_stop = max(prior_stops, default=None)
        if latest_stop is not None:
            assert confirmation["structure_started_at"] > latest_stop
            assert confirmation["end_ns"] > latest_stop
        callbacks = buys.get(p["intent_id"], [])
        filled = sum(e["quantity"] for e in callbacks)
        for e in callbacks:
            if e["quantity"]:
                assert e["native_ns"] > confirmation["end_ns"]
        same_day_stop = latest_stop is not None and day_of(latest_stop) == p["day"]
        category = (
            "first_submitted_attempt"
            if counts[key] == 1
            else "after_actual_same_session_full_stop"
            if same_day_stop
            else "after_unfilled_submitted_attempt"
        )
        proposal_rows.append(
            dict(
                symbol=p["symbol"],
                day=p["day"],
                confirmation_id=p["confirmation_id"],
                intent_id=p["intent_id"],
                ordinal=counts[key],
                category=category,
                feature_status=confirmation["feature_status"],
                submitted_quantity=p["quantity"],
                filled_quantity=filled,
                decision_ns=decision_ns,
                latest_actual_full_stop_ns=latest_stop,
                same_session_prior_full_stop=same_day_stop,
                structure_started_at=confirmation["structure_started_at"],
                native_intent_created_at=intents[p["intent_id"]]["created_at"]
                if p["intent_id"] in intents
                else None,
            )
        )
    by_intent = {p["intent_id"]: p for p in proposal_rows}
    gaps = read(folder, "observation-gaps")
    trade_rows = []
    for r in labels:
        p = by_intent[r["entry_intent_id"]]
        partials = [
            e
            for e in positive
            if e["symbol"] == r["symbol"]
            and r["actual_entry_ns"] <= e["native_ns"] <= r["actual_exit_ns"]
            and e["reason"] == "partial_strength"
        ]
        assert len(partials) <= 1
        for e in partials:
            assert e["quantity"] == math.floor(0.15 * r["actual_quantity"])
        trade_rows.append(
            dict(
                symbol=r["symbol"],
                day=r["day"],
                confirmation_id=r["confirmation_id"],
                ordinal=p["ordinal"],
                category=p["category"],
                feature_status=p["feature_status"],
                same_session_prior_full_stop=p["same_session_prior_full_stop"],
                entry_ns=r["actual_entry_ns"],
                exit_ns=r["actual_exit_ns"],
                quantity=r["actual_quantity"],
                entry_price=r["actual_entry_price"],
                exit_price=r["actual_exit_price"],
                exit_reason=r["exit_reason"],
                net_dollars=r["native_net"],
                fees=r["total_fees"],
                reference_initial_price_risk_dollars=r["actual_quantity"]
                * (r["reference"] - r["initial_stop"]),
                held_gap_records=sum(
                    g["quantity"] > 0
                    and g["symbol"] == r["symbol"]
                    and r["actual_entry_ns"] < g["interval_end_ns"] <= r["actual_exit_ns"]
                    for g in gaps
                ),
            )
        )
    marks = observed_marks(folder)
    assert math.isclose(marks["drawdown_pct"], result["observed_minute_drawdown_pct"], abs_tol=1e-9)
    assert math.isclose(marks["mean_gross"], result["mean_observed_gross"], abs_tol=1e-9)
    assert marks["stale"] == result["stale_inclusive_mark_samples"]
    peak = equity.equity.cummax().clip(lower=20000)
    underwater = max_underwater = 0
    for value, high in zip(equity.equity, peak, strict=True):
        underwater = underwater + 1 if value < high else 0
        max_underwater = max(max_underwater, underwater)
    month_end = equity.assign(month=equity.day.str[:7]).groupby("month").tail(1)
    monthly = month_end.equity.diff()
    monthly.iloc[0] = month_end.equity.iloc[0] - 20000
    by_name = defaultdict(float)
    for t in trade_rows:
        by_name[t["symbol"]] += t["net_dollars"]
    category_summary = {}
    for category in sorted({p["category"] for p in proposal_rows}):
        pp = [p for p in proposal_rows if p["category"] == category]
        tt = [t for t in trade_rows if t["category"] == category]
        category_summary[category] = dict(
            submitted=len(pp),
            positive_funded_intents=sum(p["filled_quantity"] > 0 for p in pp),
            unfilled_intents=sum(p["filled_quantity"] == 0 for p in pp),
            closed_trades=len(tt),
            raw_net_dollars=sum(t["net_dollars"] for t in tt),
            fees=sum(t["fees"] for t in tt),
        )
    summary = dict(
        native_result=result,
        scheduled_symbol_days=len(dates) * len(names),
        trigger_eligible_symbol_days=sum(
            q["trigger_eligible"] for row in coverage for q in row["symbols"].values()
        ),
        missing_invalid_source_symbol_minutes=sum(
            q["missing_invalid"] for row in coverage for q in row["symbols"].values()
        ),
        cashflow_residual=residual,
        cashflow_rounding_bound=0.011 * len(positive) + 1e-6,
        actual_positive_callbacks=len(positive),
        max_native_commission_cent_rounding_abs=max(
            abs(e["fee"] - e["quantity"] * e["price"] * 0.001) for e in positive
        ),
        raw_cashflow_net=cashflow,
        observed_marks_recomputed=marks,
        session_close_drawdown_pct=float(100 * (equity.equity / peak - 1).min()),
        session_close_max_underwater_sessions=max_underwater,
        mean_session_close_gross=float((equity.gross / equity.equity).mean()),
        session_close_monthly_net=dict(zip(month_end.month, monthly, strict=True)),
        by_name_raw_net=dict(sorted(by_name.items(), key=lambda item: -item[1])),
        top_five_winners=sorted(trade_rows, key=lambda t: -t["net_dollars"])[:5],
        worst_five_losses=sorted(trade_rows, key=lambda t: t["net_dollars"])[:5],
        category_summary=category_summary,
        created_buy_intents=len(proposal_rows),
        native_submitted_buy_intents=sum(i["action"] == "buy" for i in intents.values()),
        created_intents_without_native_submission=sum(
            p["intent_id"] not in intents for p in proposal_rows
        ),
        all_funded_same_session_stop_reentries=sum(
            t["same_session_prior_full_stop"] for t in trade_rows
        ),
        full_protective_stop_exits=len(stops),
        positive_partial_callbacks=sum(
            e["quantity"] > 0 and e["reason"] == "partial_strength" for e in events
        ),
        active_gap_records=len(gaps),
        held_gap_records=sum(g["quantity"] > 0 for g in gaps),
        gaps_without_next_received_quote=sum(g["next_observed_quote_ns"] is None for g in gaps),
        short_sample_caveat=len(dates) < 252,
        low_trade_count=len(labels) < 30,
        attempts=proposal_rows,
        trades=trade_rows,
    )
    return summary, events


def main():
    confirmations = {}
    for month in ("2024-01", "2024-02", "2024-03"):
        with (INPUTS / month / "notices.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                if row["kind"] == "CONFIRMATION":
                    e = row["event"]
                    confirmations[e["confirmation_id"]] = e
    dates = [str(d) for d in us_equity_session_dates(date(2024, 1, 2), date(2024, 3, 28))]
    arms, events = {}, {}
    for arm in ("B", "R"):
        arms[arm], events[arm] = audit_arm(arm, confirmations, dates)
    indexed = {
        arm: {(r["symbol"], r["confirmation_id"]): r for r in arms[arm]["trades"]}
        for arm in ("B", "R")
    }
    common = indexed["B"].keys() & indexed["R"].keys()
    b_only, r_only = indexed["B"].keys() - common, indexed["R"].keys() - common
    paired = []
    for key in sorted(common):
        b, r = indexed["B"][key], indexed["R"][key]
        paired.append(
            dict(
                symbol=key[0],
                confirmation_id=key[1],
                B=b,
                R=r,
                net_delta=r["net_dollars"] - b["net_dollars"],
                same_entry_ns=b["entry_ns"] == r["entry_ns"],
                same_exit_ns=b["exit_ns"] == r["exit_ns"],
                same_quantity=b["quantity"] == r["quantity"],
            )
        )
    native_increment = (
        arms["R"]["native_result"]["net_dollars"] - arms["B"]["native_result"]["net_dollars"]
    )
    bridge = dict(
        common_trade_delta=sum(p["net_delta"] for p in paired),
        R_only_trade_net=sum(indexed["R"][k]["net_dollars"] for k in r_only),
        minus_B_only_trade_net=-sum(indexed["B"][k]["net_dollars"] for k in b_only),
        native_cent_rounding_delta=arms["R"]["cashflow_residual"] - arms["B"]["cashflow_residual"],
    )
    assert math.isclose(sum(bridge.values()), native_increment, abs_tol=1e-6)

    def signature(e):
        fields = ("symbol", "action", "reason", "native_ns", "quantity", "price", "fee")
        return tuple(e[k] for k in fields)

    first_difference = next(
        (
            i
            for i, (b, r) in enumerate(zip(events["B"], events["R"], strict=False))
            if signature(b) != signature(r)
        ),
        min(len(events["B"]), len(events["R"])) if len(events["B"]) != len(events["R"]) else None,
    )
    result = validate_results(ROOT, str((OUT / "results.json").relative_to(ROOT)), OUT.name)
    assert result.n_trials == 65 and result.dsr is None
    assert math.isclose(
        result.net_profit_usd, arms["R"]["native_result"]["net_dollars"], abs_tol=1e-7
    )
    assert math.isclose(
        result.baseline_net_profit_usd, arms["B"]["native_result"]["net_dollars"], abs_tol=1e-7
    )
    receipt = read(OUT, "scope-review")
    for binding in receipt["bindings"]:
        assert digest(OUT / binding["path"]) == binding["sha256"]
    sources = [p for arm in ("B", "R") for p in sorted((NATIVE / arm).iterdir()) if p.is_file()]
    output = dict(
        status="worker_checks_pass_pending_independent_result_review",
        at_utc=stamp(),
        diagnostic_only=True,
        new_financial_starts=0,
        new_fits=0,
        new_labels=0,
        calendar_sessions=len(dates),
        saved_legal_confirmations=sum(e["legal"] for e in confirmations.values()),
        arms=arms,
        native_R_minus_B=native_increment,
        account_increment_bridge=bridge,
        common_trade_comparison=paired,
        B_only_trades=[indexed["B"][k] for k in sorted(b_only)],
        R_only_trades=[indexed["R"][k] for k in sorted(r_only)],
        first_callback_difference=dict(
            index=first_difference,
            B=events["B"][first_difference]
            if first_difference is not None and first_difference < len(events["B"])
            else None,
            R=events["R"][first_difference]
            if first_difference is not None and first_difference < len(events["R"])
            else None,
        ),
        effective_independent_trials=None,
        dsr=None,
        pbo=None,
        physical_missing_interval_drawdown_or_profit_identified=False,
        source_bindings=[
            dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=digest(p))
            for p in sources
        ],
    )
    save(NATIVE / "worker-audit.json", output)
    print(
        json.dumps(
            {
                k: output[k]
                for k in (
                    "status",
                    "calendar_sessions",
                    "native_R_minus_B",
                    "account_increment_bridge",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
