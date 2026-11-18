"""Project the owned paper pools from sealed local evidence, without acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from open_composer.market_sessions import us_equity_session_dates
from scripts.reconcile_paper_history import day_of, recovered_evidence, stamp

D = Decimal
CENT = D("0.01")
SIX = ("BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL")


def amount(value):
    result = D(str(value))
    if not result.is_finite():
        raise ValueError("nonfinite economic amount")
    return result


def funded_result(value, initial, flows=()):
    """Contributions change invested capital; they are never earned PnL."""
    capital = amount(initial) + sum((amount(f["amount_usd"]) for f in flows), D(0))
    pnl = None if value is None else amount(value) - capital
    return dict(
        capital_usd=capital,
        pnl_usd=pnl,
        return_pct=pnl / capital * 100 if pnl is not None and capital > 0 else None,
    )


def combine(pools):
    """A missing capital denominator need not erase supported dollar profit."""
    capital_missing = [p["id"] for p in pools if p["capital_usd"] is None]
    known_capital = sum((p.get("known_capital_usd", p["capital_usd"]) or D(0) for p in pools), D(0))
    capital = None if capital_missing else sum((p["capital_usd"] for p in pools), D(0))
    missing = [p["id"] for p in pools if p["pnl_usd"] is None]
    clocks = {p["at"] for p in pools if p.get("at")}
    if len(clocks) > 1:
        missing.append("valuation clocks differ")
    pnl = None if missing else sum((p["pnl_usd"] for p in pools), D(0))
    return dict(
        capital_usd=capital,
        known_capital_usd=known_capital,
        capital_missing=capital_missing,
        pnl_usd=pnl,
        return_pct=pnl / capital * 100
        if pnl is not None and capital is not None and capital > 0
        else None,
        missing=missing,
        pools=[p["id"] for p in pools],
    )


def principal(rows):
    return sum(
        (
            amount(r["qty"])
            * amount(r["price"])
            * (-1 if r["side"] in {"buy", "buy_to_cover"} else 1)
            for r in rows
        ),
        D(0),
    )


def marked_component(series, positions):
    """Use the saved position valuation, keeping raw-close charts separate."""
    point = series["points"][-1]
    market = D(0)
    for symbol, raw_quantity in point["quantity"].items():
        quantity = amount(raw_quantity)
        if not quantity:
            continue
        position = positions.get(symbol)
        if position is None or not amount(position["qty"]) or position.get("market_value") is None:
            return None
        market += quantity * amount(position["market_value"]) / amount(position["qty"])
    return amount(point["realized_fifo_usd"]) - amount(point["remaining_fifo_cost_usd"]) + market


def verify_owned_positions(received):
    owned = defaultdict(lambda: D(0))
    for row in received["activities"]:
        if row["activity_type"] == "FILL":
            owned[row["symbol"]] += amount(row["qty"]) * (
                1 if row["side"] in {"buy", "buy_to_cover"} else -1
            )
        elif row["activity_type"] == "MA" and row.get("status") == "executed":
            if row.get("symbol") and row.get("qty") is not None:
                owned[row["symbol"]] += amount(row["qty"])
    actual = {p["symbol"]: amount(p["qty"]) for p in received["positions"]}
    if any(owned[s] != actual.get(s, D(0)) for s in owned.keys() | actual.keys()):
        raise ValueError("owned FILL/MA quantities differ from saved positions")


def position_market(received):
    if any(p.get("market_value") is None for p in received["positions"]):
        return None
    return sum((amount(p["market_value"]) for p in received["positions"]), D(0))


def posted_adjustments(received, *, after_day=None):
    by_kind = defaultdict(lambda: D(0))
    for row in received["activities"]:
        if row["activity_type"] == "FILL":
            continue
        if row.get("status") != "executed" or row.get("net_amount") is None:
            raise ValueError("unresolved nontrade cash effect")
        if after_day and str(row.get("date", ""))[:10] <= after_day:
            continue
        if row["activity_type"] not in {"CSD", "CSW", "ACATC"}:
            by_kind[row["activity_type"]] += amount(row["net_amount"])
    return dict(by_kind)


def capital_at(series, day):
    """Recorded latest allocation; dated denominators require effective_capital."""
    return amount(series["initial_allocation_usd"]) + sum(
        (
            amount(f["amount_USD"])
            for f in series.get("allocation_flows", [])
            if str(day_of(f["observed_at"])) <= day
        ),
        D(0),
    )


def effective_capital(witness, at):
    """Known-by is not proof of zero or the same funding amount before it."""
    if at is None or stamp(at) < stamp(witness["known_by"]):
        return None
    return amount(witness["initial_capital_usd"]) + sum(
        (
            amount(f["amount_USD"])
            for f in witness.get("flow_records", [])
            if stamp(f["observed_at"]) <= stamp(at)
        ),
        D(0),
    )


def daily_curve(history, accounts, starts, initial, funding):
    daily = {k: {p["day"]: p for p in a["points"]} for k, a in accounts.items()}
    days = [
        str(d)
        for d in us_equity_session_dates(
            date.fromisoformat(starts["legacy"]), date.fromisoformat(history["through_session"])
        )
    ]
    result = []
    for day in days:
        pools, capital_details = [], []
        at = next((d[day]["at"] for d in daily.values() if day in d), None)
        for alias in ("legacy", "F1", "six"):
            if day < starts[alias]:
                continue
            point = daily[alias].get(day)
            capital = initial[alias]
            if alias == "six":
                effective = {name: effective_capital(w, at) for name, w in funding.items()}
                known = sum((v or D(0) for v in effective.values()), D(0))
                capital_details = ["six/" + n for n, v in effective.items() if v is None]
                capital = None if capital_details else known
            flows = [f for f in accounts[alias]["external_flows"] if f["day"] <= day]
            if alias == "F1":
                before = accounts[alias]["order_ownership"][
                    "last_account_observation_before_first_native_FILL"
                ]["day"]
                flows = [f for f in flows if f["day"] > before]
            net_flow = sum((amount(f["amount_usd"]) for f in flows), D(0))
            value = None if point is None else point.get("equity_usd")
            # Dollar ownership is already reconciled to actual fills/cash/positions.
            # It does not require inventing a missing historical allocation denominator.
            pnl = None if value is None else amount(value) - initial[alias] - net_flow
            if alias != "six":
                capital += net_flow
                known = capital
            pools.append(
                dict(
                    id=alias,
                    at=point.get("at") if point else None,
                    capital_usd=capital,
                    known_capital_usd=known,
                    pnl_usd=pnl,
                )
            )
        result.append(dict(day=day, capital_missing_details=capital_details, **combine(pools)))
    return result


def build(history, recovered, state, funding_evidence):
    accounts = recovered["accounts"]
    if set(accounts) != {"legacy", "six", "F1"} or recovered["pending"]:
        raise ValueError("three complete saved account scopes required")
    for alias, a in accounts.items():
        if not a["activity_coverage_complete"] or a["ambiguous_flow_ids"]:
            raise ValueError("incomplete flow or activity ownership")
        verify_owned_positions(a)
        if a["account_hash"] != history["recovery_summary"][alias]["account_hash"]:
            raise ValueError("sealed and received account identities differ")
    ownership = accounts["F1"]["order_ownership"]
    if ownership["filled_orders_without_original_strategy_or_probe_receipt"]:
        raise ValueError("unowned F1 orders")
    if ownership["probe_remaining_quantities"]:
        raise ValueError("probe exposure not closed at adopted baseline")
    baseline = ownership["last_account_observation_before_first_native_FILL"]
    initial = {
        "legacy": amount(accounts["legacy"]["points"][0]["equity_usd"]),
        "six": amount(
            history["recovery_summary"]["six"]["reconciliation"]["implied_opening_cash_usd"]
        ),
        "F1": amount(baseline["equity_usd"]),
    }
    histories = {s["id"]: s for s in history["histories"]}
    primitives = [
        s
        for s in history["histories"]
        if s["id"].startswith("six/") and s["kind"] == "trading_component"
    ]
    capital = sum((capital_at(s, history["through_session"]) for s in primitives), D(0))
    funding = funding_evidence["policy_funding"]
    if set(funding) != set(SIX):
        raise ValueError("each top-level policy requires its own capital witness")
    for name, witness in funding.items():
        current = effective_capital(witness, accounts["six"]["current_account"]["observed_at"])
        series = histories["six/" + name]
        children = [histories[c] for c in series.get("children", [series["id"]])]
        if current != sum((capital_at(c, history["through_session"]) for c in children), D(0)):
            raise ValueError("observed parent capital differs from owned child capital")
    starts = dict(
        legacy=accounts["legacy"]["points"][0]["day"],
        F1=str(day_of(ownership["first_native_strategy_FILL_at"])),
        six=str(min(day_of(w["known_by"]) for w in funding.values())),
    )
    if any(
        row["activity_type"] == "FILL" and str(day_of(row["transaction_time"])) < starts["six"]
        for row in accounts["six"]["activities"]
    ):
        raise ValueError("owned six exposure predates the evidenced funding start")
    rows = []
    for name in SIX:
        s = histories["six/" + name]
        children = [histories[c] for c in s.get("children", [s["id"]])]
        values = [
            marked_component(c, {p["symbol"]: p for p in accounts["six"]["positions"]})
            for c in children
        ]
        pnl = None if None in values else sum(values, D(0))
        rows.append(
            dict(
                id=s["id"],
                label="STATE" if name == "BASE_STATE_BUDGET" else name,
                pool="six",
                capital_usd=sum(
                    (capital_at(c, history["through_session"]) for c in children), D(0)
                ),
                pnl_usd=pnl,
                status="实际账本",
                first_day=min(c["first_fill"] for c in children),
            )
        )
    for s in history["histories"]:
        if not s["id"].startswith("legacy/"):
            continue
        pnl = marked_component(s, {p["symbol"]: p for p in accounts["legacy"]["positions"]})
        rows.append(
            dict(
                id=s["id"],
                label=s["label"],
                pool="legacy",
                capital_usd=s["initial_allocation_usd"],
                pnl_usd=pnl,
                status="已退出" if s["retired"] else "实际账本",
                first_day=s["first_fill"],
            )
        )
    probe_ids = set(ownership["saved_probe_order_ids"])
    f1_fills = [
        r
        for r in accounts["F1"]["activities"]
        if r["activity_type"] == "FILL" and r["order_id"] not in probe_ids
    ]
    f1_market = position_market(accounts["F1"])
    rows.insert(
        10,
        dict(
            id="F1",
            label="F1",
            pool="F1",
            capital_usd=initial["F1"],
            pnl_usd=principal(f1_fills) + f1_market if f1_market is not None else None,
            status="实际账本 · 计划归属待核",
            first_day=starts["F1"],
        ),
    )
    for row in rows:
        row["capital_usd"] = None if row["capital_usd"] is None else amount(row["capital_usd"])
        row["precise_pnl_usd"] = row["pnl_usd"]
        row["pnl_usd"] = None if row["pnl_usd"] is None else row["pnl_usd"].quantize(CENT)
        row["return_pct"] = (
            row["precise_pnl_usd"] / row["capital_usd"] * 100
            if row["capital_usd"] and row["pnl_usd"] is not None
            else None
        )
    pools = []
    adjustments = []
    for alias, a in accounts.items():
        account = a["current_account"]
        market = position_market(a)
        reconstructed = amount(account["cash"]) + market if market is not None else None
        precision = amount(account["equity"]) - reconstructed if reconstructed is not None else None
        if precision is not None and abs(precision) > CENT:
            raise ValueError("saved account valuation identity outside source precision")
        assigned = capital if alias == "six" else initial[alias]
        flows = a["external_flows"]
        if alias == "F1":
            flows = [f for f in flows if f["day"] > baseline["day"]]
        value = reconstructed + precision if reconstructed is not None else None
        if alias == "six" and value is not None:
            value -= initial["six"] - assigned + sum((amount(f["amount_usd"]) for f in flows), D(0))
            flows = []
        pool = funded_result(value, assigned, flows)
        pools.append(dict(id=alias, **pool))
        entries = posted_adjustments(a, after_day=baseline["day"] if alias == "F1" else None)
        adjustments.append(
            dict(
                pool=alias,
                entries=entries,
                posted_usd=sum(entries.values(), D(0)),
                quote_precision_usd=precision,
            )
        )
        owned_rows = [r for r in rows if r["pool"] == alias]
        row_total = (
            None
            if any(r["precise_pnl_usd"] is None for r in owned_rows)
            else sum((r["precise_pnl_usd"] for r in owned_rows), D(0))
        )
        if (
            row_total is not None
            and pool["pnl_usd"] is not None
            and abs(row_total + sum(entries.values(), D(0)) + precision - pool["pnl_usd"])
            > D("0.00000001")
        ):
            raise ValueError("strategy rows plus actual postings do not reconcile to owned pool")
    total = combine(pools)
    if any(r["pnl_usd"] is None for r in rows):
        total.update(
            pnl_usd=None, return_pct=None, missing=[r["id"] for r in rows if r["pnl_usd"] is None]
        )
    total["pnl_usd"] = total["pnl_usd"].quantize(CENT) if total["pnl_usd"] is not None else None
    adjustment = (
        None
        if total["pnl_usd"] is None
        else total["pnl_usd"] - sum((r["pnl_usd"] for r in rows), D(0))
    )
    display_rounding = (
        None
        if adjustment is None
        else adjustment
        - sum((a["posted_usd"] + (a["quote_precision_usd"] or D(0)) for a in adjustments), D(0))
    )
    unassigned_capital = total["capital_usd"] - sum((r["capital_usd"] or D(0) for r in rows), D(0))
    at = sorted(a["current_account"]["observed_at"] for a in accounts.values())
    marks = sorted(a["positions_observed_at"] for a in accounts.values())
    return dict(
        schema_version=1,
        generated_at=datetime.now(UTC).isoformat(),
        through_session=history["through_session"],
        snapshot={
            **total,
            "at_start": at[0],
            "at_end": at[-1],
            "marks_start": marks[0],
            "marks_end": marks[-1],
            "rows": rows,
            "adjustment_usd": adjustment,
            "display_rounding_usd": display_rounding,
            "unassigned_capital_usd": unassigned_capital,
            "adjustments": adjustments,
            "pool_readings": pools,
        },
        daily=daily_curve(history, accounts, starts, initial, funding),
        capital_funding_evidence=funding_evidence,
        pool_starts=starts,
        F1_observed_adopted_baseline=baseline,
        probe_executions=ownership["probe_executions"],
        F1_strategy_FILL_count=len(f1_fills),
        F1_canonical_plan_mismatches=ownership["canonical_daily_vs_submitted_plan_mismatches"],
        capital_definition=(
            "PnL / actual adopted or assigned capital including subsequent net contributions; "
            "no equal-return averaging"
        ),
        initial_pool_capital=initial,
        six_assigned_capital_usd=capital,
        six_unassigned_cash_usd=initial["six"] - capital,
        daily_clock=(
            "NY20:00 broker1D; composition changes only at evidenced pool starts; "
            "current batch and rawRTHclose are separate"
        ),
        quarantined_account_points=history["quarantined_account_points"],
        broker_or_source_API_calls=0,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--funding-witnesses", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    binding = json.loads((root / "config/paper-history-dashboard.json").read_text())
    history_path = root / binding["path"]
    raw = history_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("sealed history changed")
    history = json.loads(raw)
    consumed = {}
    received = recovered_evidence(root, consumed, date.fromisoformat(history["through_session"]))
    # Every reread receipt must be a member of the already sealed history scope.
    sealed = {r["path"]: r["sha256"] for r in history["source_bindings"]}
    for path, entry in consumed.items():
        if sealed.get(path) != entry["sha256"]:
            raise ValueError("receipt outside sealed344 scope or changed")
    state_path = (
        root
        / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/history-v1"
        / "runtime-state-received.json"
    )
    state_raw = state_path.read_bytes()
    if hashlib.sha256(state_raw).hexdigest() != sealed[str(state_path)]:
        raise ValueError("funding witness changed")
    funding_raw = args.funding_witnesses.read_bytes()
    funding = json.loads(funding_raw)
    for source in funding["original_sources"]:
        captured = source["captured"]
        data = Path(captured["path"]).read_bytes()
        if len(data) != captured["bytes"] or hashlib.sha256(data).hexdigest() != captured["sha256"]:
            raise ValueError("captured funding witness changed")
    output = build(history, received, json.loads(state_raw), funding)
    output["source_bindings"] = [
        dict(path=str(history_path), bytes=len(raw), sha256=binding["sha256"]),
        dict(
            path=str(args.funding_witnesses),
            bytes=len(funding_raw),
            sha256=hashlib.sha256(funding_raw).hexdigest(),
        ),
        *(x["captured"] for x in funding["original_sources"]),
        dict(path=str(state_path), bytes=len(state_raw), sha256=sealed[str(state_path)]),
        *consumed.values(),
    ]
    output["code_bindings"] = [
        dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in (Path(__file__), Path(recovered_evidence.__code__.co_filename))
    ]
    args.output.write_text(
        json.dumps(
            output,
            default=lambda v: float(v) if isinstance(v, D) else str(v),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            dict(
                output=str(args.output),
                pnl=output["snapshot"]["pnl_usd"],
                capital=output["snapshot"]["capital_usd"],
                rows=len(output["snapshot"]["rows"]),
            ),
            default=str,
        )
    )


if __name__ == "__main__":
    main()
