"""Small conditional source-case reference, not a funded strategy engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext

from build_case_inputs import minute_grid

CENT = Decimal("0.01")
BPS = (0, 5, 20)
BORROW_APR = (Decimal(0), Decimal("0.20"))


def d(x):
    return Decimal(str(x))


def arm(component, case_day, method, delay):
    """No IO/network/fitting. One pretrade-frozen quantity and one order trajectory."""
    out = {
        "method": method,
        "activation_delay_minutes": delay,
        "status": "invalid",
        "R": None,
        "entry": None,
        "exit": None,
        "events": [],
        "conditional_fullfill_proxy": True,
        "actual_NBBO_ETB_SSR_borrow_not_certified": True,
    }
    parent = component.get("prior_last_chartbar")
    if (
        not parent
        or not parent["complete"]
        or (method == "PDL" and not component["prior_RTH_complete"])
    ):
        out.update(status="invalid_input", reason="missing_frozen_decision_bar_or_prior_RTH_range")
        return out
    grid = minute_grid(date.fromisoformat(case_day))
    assert grid and method in ("PDL", "PREVH") and delay in (1, 5)
    low = component["prior_RTH_low"] if method == "PDL" else parent["l"]
    pref = (d(low) - CENT).quantize(CENT, rounding=ROUND_FLOOR)
    stop = (d(parent["h"]) + CENT).quantize(CENT, rounding=ROUND_CEILING)
    out.update(
        Pref=str(pref),
        S=str(stop),
        risk_budget_USD="100",
        decision_bar_start=parent["start_NY"],
        decision_bar_end=parent["end_NY"],
        decision_source_refs=parent["source_refs"],
    )
    if pref <= 0 or stop <= pref:
        out["reason"] = "invalid_positive_price_or_risk_distance"
        return out
    q0 = int((Decimal(100) / (stop - pref)).to_integral_value(rounding=ROUND_FLOOR))
    r0 = q0 * (stop - pref)
    out.update(
        q0=q0,
        R0=str(r0),
        risk_distance=str(stop - pref),
        unused_planned_risk_USD=str(Decimal(100) - r0),
    )
    if q0 < 1:
        out["reason"] = "no_integer_quantity"
        return out
    activation = grid[0] + timedelta(minutes=delay)
    expiry = grid[-1] + timedelta(minutes=1) - timedelta(minutes=15)
    out.update(
        activation_NY=activation.isoformat(),
        pending_expiry_NY=expiry.isoformat(),
        EOD_minute_start_NY=grid[-1].isoformat(),
    )
    minutes = {datetime.fromisoformat(x["timestamp_NY"]): x for x in component["RTH_minutes"]}
    state = "inactive"
    entry_time = None
    entry_price = None
    exit_price = None
    for t in grid:
        if state == "inactive" and t >= activation:
            state = "pending"
            out["events"].append({"time_NY": t.isoformat(), "event": "activate_parent"})
        # Expiry is a calendar event before processing its bar, even if the bar is absent.
        if state == "pending" and t >= expiry:
            out.update(
                status="no_fill", trading_cashflow="0", reason="clean_pending_cancelled_at_expiry"
            )
            out["events"].append({"time_NY": t.isoformat(), "event": "cancel_unfilled_parent"})
            return out
        if state not in ("pending", "held"):
            continue
        item = minutes.get(t)
        if item is None or not item["valid"]:
            out.update(
                status="missing",
                reason="active_pending_or_held_minute_missing_or_invalid",
                unknown_at_NY=t.isoformat(),
                unresolved_state=state,
                contingent_protection_scheduled_NY=(entry_time + timedelta(minutes=1)).isoformat()
                if entry_time
                else None,
            )
            out["events"].append(
                {"time_NY": t.isoformat(), "event": "unidentified_trajectory", "state": state}
            )
            return out
        row = item["row"]
        if state == "pending":
            # Every eligible pending minute can gap; do not use Pref for a later gap.
            if d(row["o"]) <= pref:
                entry_price = d(row["o"])
                fill = "open_gap_or_equal"
            elif d(row["l"]) <= pref:
                entry_price = pref
                fill = "intraminute_touch_proxy"
            else:
                continue
            entry_time = t
            state = "held"
            vol = d(row["v"])
            out["entry"] = {
                "minute_start_NY": t.isoformat(),
                "price": str(entry_price),
                "fill_proxy": fill,
                "source_ref": item["ref"],
                "barstart_label_not_exact_fill_ns": True,
                "q0": q0,
                "entry_notional": str(q0 * entry_price),
                "participation_gt_1pct_observed_minute_volume": q0 > vol * Decimal("0.01"),
                "gap_vs_trigger_USD_per_share": str(pref - entry_price),
                "entry_bar_crosses_stop_while_unprotected": d(row["h"]) >= stop,
                "protection_scheduled_NY": (t + timedelta(minutes=1)).isoformat(),
            }
            out["events"].append(
                {
                    "time_NY": t.isoformat(),
                    "event": "conditional_fullfill_entry",
                    "source_ref": item["ref"],
                }
            )
            continue
        assert state == "held" and t >= entry_time + timedelta(minutes=1)
        if d(row["o"]) >= stop:
            exit_price = d(row["o"])
            why = "protective_open_gap_or_equal"
        elif d(row["h"]) >= stop:
            exit_price = stop
            why = "protective_touch_proxy"
        elif t == grid[-1]:
            exit_price = d(row["c"])
            why = "EOD_research_convention"
        else:
            continue
        out.update(
            status="filled_closed",
            exit={
                "minute_start_NY": t.isoformat(),
                "price": str(exit_price),
                "exit_reason": why,
                "source_ref": item["ref"],
                "barstart_label_not_exact_fill_ns": True,
            },
            raw_proxy_cashflow=str(q0 * (entry_price - exit_price)),
        )
        out["events"].append(
            {
                "time_NY": t.isoformat(),
                "event": "conditional_fullfill_exit",
                "reason": why,
                "source_ref": item["ref"],
            }
        )
        return out
    out.update(
        status="missing",
        reason="session_exhausted_with_unidentified_terminal_state",
        unresolved_state=state,
    )
    return out


def cost_outputs(trajectory):
    """48 fixed transaction cells and96 borrow-stress cells across16 trajectories."""
    fee_rows = []
    borrow_rows = []
    for bps in BPS:
        row = {
            "bps_per_filled_side": bps,
            "primary": bps == 20,
            "status": trajectory["status"],
            "fee_USD": None,
            "transaction_adjusted_R": None,
            "actual_borrow_cost_unpriced": True,
        }
        if trajectory["status"] == "filled_closed":
            q = trajectory["q0"]
            e = d(trajectory["entry"]["price"])
            x = d(trajectory["exit"]["price"])
            r0 = d(trajectory["R0"])
            fees = q * (e + x) * Decimal(bps) / Decimal(10000)
            cash = q * (e - x)
            row.update(
                fee_USD=str(fees),
                entry_notional=str(q * e),
                exit_notional=str(q * x),
                transaction_adjusted_R=str((cash - fees) / r0),
                original_R0=str(r0),
            )
        elif trajectory["status"] == "no_fill":
            row.update(fee_USD="0", trading_cashflow="0", trade_R=None)
        fee_rows.append(row)
        for apr in BORROW_APR:
            stress = {
                **row,
                "assumed_APR": str(apr),
                "assumed_calendar_days": 1,
                "day_basis": 365,
                "borrow_stress_USD": None,
                "stress_R": None,
                "actual_short_tradability_certified": False,
            }
            if trajectory["status"] == "filled_closed":
                charge = q * e * apr / Decimal(365)
                stress.update(
                    borrow_stress_USD=str(charge), stress_R=str((cash - fees - charge) / r0)
                )
            elif trajectory["status"] == "no_fill":
                stress["borrow_stress_USD"] = "0"
            borrow_rows.append(stress)
    return fee_rows, borrow_rows


def replay(component, case_day, method, delay):
    with localcontext() as ctx:
        ctx.prec = 60
        trajectory = arm(component, case_day, method, delay)
        costs, borrow = cost_outputs(trajectory)
        return {
            "trajectory": trajectory,
            "transaction_costs": costs,
            "mandatory_borrow_stress": borrow,
        }
