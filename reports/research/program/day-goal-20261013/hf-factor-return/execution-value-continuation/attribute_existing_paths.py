"""Arithmetic attribution of immutable old paths; no new orders, fills or policies."""

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

C = Path(__file__).resolve().parent
P = C.parent
sys.path.insert(0, str(P))
from hf_completion_resources import apply_job_limit  # noqa: E402


def summarize(book):
    cost = book["cost_each_side"]
    groups = defaultdict(lambda: dict(attempts=0, filled=0, fees=0.0, filled_notional=0.0))
    for order in book["orders"]:
        key = "|".join([order["reason"], order["side"], order["status"]])
        group = groups[key]
        group["attempts"] += 1
        group["fees"] += order["fee"]
        if order["status"] == "reference_filled":
            group["filled"] += 1
            group["filled_notional"] += order["quantity"] * order["actual_reference"]
    scores = np.array([s["score"] for s in book["signals"] if s["score"] is not None])
    signals = Counter()
    for signal in book["signals"]:
        hour, minute = map(int, signal["at"].rsplit(" ", 1)[1].split(":"))
        category = ("first_hour_structural_fallback" if hour * 60 + minute < 630
                    else "mature_clock_missing") if signal["fallback"] else "finite_forecast"
        signals[category] += 1
        if signal["target"] != int(signal["actual_held"]):
            signals[category + "_desired_state_change"] += 1
        if not signal["fallback"]:
            signals["finite_above_positive_cost"] += int(signal["score"] > cost)
            signals["finite_below_negative_cost"] += int(signal["score"] < -cost)
            signals["finite_inside_inclusive_band"] += int(abs(signal["score"]) <= cost)
    orders_by_day = defaultdict(list)
    cash_by_day = defaultdict(list)
    for order in book["orders"]:
        orders_by_day[order["day"]].append(order)
    for event in book["events"]:
        if event["event"] == "proxy_cash_available" and "sale_date" in event:
            cash_by_day[event["at"][:10]].append(event)
    pending_cash = 0.0
    refusals = Counter()
    max_pending_error = 0.0
    for day in book["daily"]:
        pending_cash -= sum(e["amount"] for e in cash_by_day[day["date"]])
        for order in orders_by_day[day["date"]]:
            if order["status"] == "no_fill_invalid_frozen_lot":
                ref = order["known_sizing_reference"]
                if ref is None or not math.isfinite(ref) or ref <= 0:
                    refusals["zero_lot_missing_known_reference"] += 1
                elif order["cash_before"] < ref * (1 + cost):
                    refusals["zero_lot_available_cash_below_one_share"] += 1
                    refusals["zero_lot_with_pending_sale_cash"] += int(pending_cash > 1e-8)
                    refusals["zero_lot_pending_plus_cash_at_least_one_share"] += int(
                        pending_cash + order["cash_before"] >= ref * (1 + cost)
                    )
                else:
                    refusals["zero_lot_other"] += 1
            if order["status"] == "reference_filled" and order["side"] == "sell":
                pending_cash += order["quantity"] * order["actual_reference"] * (1 - cost)
        max_pending_error = max(max_pending_error, abs(pending_cash - day["unsettled"]))
    assert max_pending_error < 1e-6, max_pending_error
    active = None
    trade_groups = defaultdict(lambda: dict(closed_trades=0, gross_price_PnL=0.0))
    for order in book["orders"]:
        if order["status"] != "reference_filled":
            continue
        if order["side"] == "buy":
            assert active is None
            active = order
        else:
            assert active is not None and active["quantity"] == order["quantity"]
            key = active["reason"] + " -> " + order["reason"]
            group = trade_groups[key]
            group["closed_trades"] += 1
            group["gross_price_PnL"] += order["quantity"] * (
                order["actual_reference"] - active["actual_reference"]
            )
            active = None
    unrealized = (active["quantity"] * (
        book["daily"][-1]["raw_daily_closing_mark"] - active["actual_reference"]
    )) if active is not None else 0.0
    dividends = sum(e["amount"] for e in book["events"]
                    if e["event"] == "actual_exdate_entitlement")
    fees = sum(o["fee"] for o in book["orders"])
    gross_closed = sum(g["gross_price_PnL"] for g in trade_groups.values())
    terminal = book["daily"][-1]["nav"]
    reconstructed = book["initial"] + gross_closed + unrealized + dividends - fees
    assert abs(reconstructed - terminal) < 1e-6
    return dict(
        order_groups=dict(groups), signal_counts=dict(signals), refusal_attribution=dict(refusals),
        roundtrip_groups=dict(trade_groups), capital_initial=book["initial"], terminal_NAV=terminal,
        exact_actual_path_PnL=dict(closed_price_PnL=gross_closed, open_price_PnL=unrealized,
                                   dividend_entitlements=dividends, fees=fees,
                                   reconstructed_terminal=reconstructed),
        forecast_quantiles=(dict(zip(["min", "q01", "q05", "median", "q95", "q99", "max"],
                                     map(float, np.quantile(scores, [0, .01, .05, .5, .95, .99, 1]))))
                            if len(scores) else None),
        cash=dict(mean_available=float(np.mean([d["cash"] for d in book["daily"]])),
                  mean_unsettled=float(np.mean([d["unsettled"] for d in book["daily"]])),
                  days_with_unsettled=sum(d["unsettled"] > 0 for d in book["daily"]),
                  ledger_pending_cash_max_abs_error=max_pending_error),
        no_unfilled_PnL_imputed=True,
    )


def main():
    apply_job_limit("attribution")
    sealed = json.loads((P / "complete-costed-final-manifest.json").read_text())
    expected = {str(Path(r["path"]).resolve()): r for r in sealed["files"]}
    ids = [r["candidate_id"] for r in json.loads((P / "scientific-plan.json").read_text())["candidates"]]
    result, bindings = {}, []
    for cost in [0, 1, 5, 20, 40]:
        def load(name):
            path = P / "economic/results" / f"{name}__{cost}-ledger.json"
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            bound = expected[str(path.resolve())]
            assert len(raw) == bound["bytes"] and digest == bound["sha256"]
            bindings.append(bound)
            return json.loads(raw)

        reference = load("SPY_OVERNIGHT_ONLY")
        reference_nav = np.array([d["nav"] for d in reference["daily"]])
        signature = lambda b: [(o["at"], o["side"], o["quantity"], o["actual_reference"], o["fee"])
                               for o in b["orders"] if o["status"] == "reference_filled"]
        reference_orders = signature(reference)
        for name in ids:
            book = load(name)
            row = summarize(book)
            nav = np.array([d["nav"] for d in book["daily"]])
            row["same_cost_overnight_comparison"] = dict(
                all_daily_NAV_exact_equal=bool(np.array_equal(nav, reference_nav)),
                max_daily_NAV_abs_difference=float(np.max(np.abs(nav-reference_nav))),
                filled_order_sequence_exact_equal=signature(book) == reference_orders,
                terminal_dollar_difference=float(nav[-1]-reference_nav[-1]),
                reference_fills=len(reference_orders),
            )
            result[f"{name}__{cost}"] = row
        print("existing_path_attributed", cost, flush=True)
    output = dict(
        task_id="HF-EXECUTION-VALUE-CONTINUATION-20261014",
        at_utc=datetime.now(UTC).isoformat(), input_bindings=bindings, books=result,
        scope="Arithmetic and recorded-decision attribution only; immutable old paths",
        old_book_count=100, reference_books=5, new_model_fits=0, new_policy_simulations=0,
        counterfactual_returns_computed=False, shadow_fills_created=False,
    )
    (C / "existing-path-attribution.json").write_text(json.dumps(output, indent=2) + "\n")
    print("complete", len(result), flush=True)


if __name__ == "__main__":
    main()
