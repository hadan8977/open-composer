# ruff: noqa: E501 -- Frozen audit identities and output labels.
"""Read-only six-sleeve principal/FIFO projection from saved native evidence.

No client, state transition, inferred fee debit or certified net-return claim.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

D = Decimal
POLICIES = ("BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL")
CHILDREN = ("S1", "S2", "S3", "C2", "BASE", "H5")
CENTS = {
    "MULTI_EQUAL": (333334, 333334, 333333, 333333, 333333, 333333),
    "MULTI_HIERARCHICAL": (166667, 166667, 166666, 500000, 500000, 500000),
}
CASH = "reports/research/program/return-line-replenishment-20261016/dia-shareholder-account-20261017/accounting.py"
CASH_SHA = "4e8614da292ec9dc1b3e0fd7878b3600eaa13df787db975d11c77a7b44bd2807"


def number(value):
    assert not isinstance(value, bool)
    x = D(str(value))
    assert x.is_finite()
    return x


def binding(path):
    p = Path(path).resolve()
    data = p.read_bytes()
    return dict(path=str(p), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def checked(row, consumed):
    assert binding(row["path"]) == row
    consumed[str(row["path"])] = row
    return json.loads(Path(row["path"]).read_text(), parse_float=D)


def decimalize(value):
    if isinstance(value, float):
        return number(value)
    if isinstance(value, list):
        return [decimalize(v) for v in value]
    if isinstance(value, dict):
        return {k: decimalize(v) for k, v in value.items()}
    return value


def original_nav_cash(root, cashbook):
    """Compile only the unchanged pure accounting identity, without its imports."""
    from open_composer.paper_runtime.source_loader import source_bytes

    p = Path(root) / CASH
    data = source_bytes(p, root=root)
    assert hashlib.sha256(data).hexdigest() == CASH_SHA
    cls = next(
        n for n in ast.parse(data).body if isinstance(n, ast.ClassDef) and n.name == "CashState"
    )
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "nav_cash")
    ns = {}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(p), "exec"
        ),
        ns,
    )
    return ns["nav_cash"](SimpleNamespace(**decimalize(cashbook)))


def quantities(book):
    return {
        s: sum((number(lot["quantity"]) for lot in lots), D(0))
        for s, lots in book["cashbook"]["lots"].items()
        if sum((number(lot["quantity"]) for lot in lots), D(0))
    }


def fifo(executions):
    lots = defaultdict(list)
    realized = D(0)
    buys = D(0)
    sales = D(0)
    for e in sorted(executions, key=lambda e: (e["time"], e["id"])):
        q = number(e["quantity"])
        p = number(e["price"])
        assert q > 0 and q == q.to_integral_value() and p > 0
        if e["side"] == "buy":
            lots[e["symbol"]].append([q, p, e["id"]])
            buys += q * p
        else:
            assert e["side"] == "sell"
            sales += q * p
            while q:
                assert lots[e["symbol"]], "Sale basis absent; never invent an opening lot"
                lot = lots[e["symbol"]][0]
                used = min(q, lot[0])
                realized += used * (p - lot[1])
                q -= used
                lot[0] -= used
                if not lot[0]:
                    lots[e["symbol"]].pop(0)
    cost = {s: sum((q * p for q, p, _ in ls), D(0)) for s, ls in lots.items() if ls}
    qty = {s: sum((q for q, _, _ in ls), D(0)) for s, ls in lots.items() if ls}
    return dict(realized=realized, buys=buys, sales=sales, cost=cost, quantity=qty)


def receive_executions(state, activities, consumed):
    """Prefer actual FILL rows; label later own cumulative-only evidence explicitly."""
    assert activities["account_hash"] == state["account"]["account_hash"]
    acts = defaultdict(list)
    seen = {}
    for r in activities["activities"]:
        assert r["activity_type"] == "FILL"
        if r["id"] in seen:
            assert seen[r["id"]] == r
            continue
        seen[r["id"]] = r
        acts[r["order_id"]].append(r)
    result = {name: [] for name in state["books"]}
    summary = []
    owners = {}

    def append(book, cid, r, kind):
        result[book].append(
            dict(
                id=r["id"],
                CID=cid,
                symbol=r["symbol"],
                side=r["side"],
                quantity=number(r["qty"]),
                price=number(r["price"]),
                time=r["transaction_time"],
                basis=kind,
            )
        )

    for cid, order in state["orders"].items():
        book = order["book"]
        assert cid in state["books"][book]["consumed_ids"]
        obs = order.get("observation")
        if not obs:
            continue
        assert (
            obs["client_order_id"] == cid
            and obs["symbol"] == order["symbol"]
            and obs["side"] == order["side"]
        )
        assert number(obs["qty"]) == number(order["qty"])
        q = number(obs["filled_qty"])
        assert q >= 0
        typed = [r for r in state["books"][book]["fills"].values() if r["client_order_id"] == cid]
        assert sum((number(r["quantity"]) for r in typed), D(0)) == q, (
            "Saved applied quantity and order differ"
        )
        assert all(r["order_id"] == obs["id"] for r in typed), (
            "Typed fill references a different broker order"
        )
        if not q:
            continue
        assert obs["id"] not in owners
        owners[obs["id"]] = book
        rows = acts.get(obs["id"], [])
        have = sum((number(r["qty"]) for r in rows), D(0))
        assert have <= q
        actual = D(0)
        for r in rows:
            assert r["symbol"] == order["symbol"] and r["side"] == order["side"]
            append(book, cid, r, "saved_broker_FILL")
            actual += number(r["qty"]) * number(r["price"])
        total = q * number(obs["filled_avg_price"])
        if have < q:
            assert obs.get("filled_at") and total > actual
            # This is a reported cumulative-average principal, not a received FILL.
            append(
                book,
                cid,
                dict(
                    id=cid + ":reported-residual",
                    symbol=order["symbol"],
                    side=order["side"],
                    qty=q - have,
                    price=(total - actual) / (q - have),
                    transaction_time=obs["filled_at"],
                ),
                "saved_order_cumulative_average_only",
            )
        summary.append(
            dict(
                book=book,
                CID=cid,
                order_id=obs["id"],
                filled_quantity=q,
                FILL_quantity=have,
                FILL_notional=actual,
                reported_cumulative_notional=total,
                reported_minus_FILL_notional=total - actual if have == q else None,
                detail_complete=have == q,
            )
        )
    # Genuine pre-service executions remain part of inception, never a clean reset.
    for book, snap in state["books"].items():
        for fid, receipt in snap["fills"].items():
            cid = receipt["client_order_id"]
            if cid in state["orders"]:
                continue
            assert receipt["account_hash"] == state["account"]["account_hash"]
            body = checked(receipt["body"], consumed)
            rows = body if isinstance(body, list) else body.get("activities", body.get("data"))
            row = next(r for r in rows if r["id"] == fid)
            assert row["activity_type"] == "FILL"
            assert fid in seen and all(k in row and row[k] == v for k, v in seen[fid].items()), (
                "Seed FILL economic projection differs from immutable full body"
            )
            request = receipt["journal_snapshot"]["request"]
            assert (
                request["client_order_id"] == cid
                and row["symbol"] == request["symbol"]
                and row["side"] == request["side"]
            )
            owners.setdefault(row["order_id"], book)
            assert owners[row["order_id"]] == book
            append(book, cid, row, "saved_pre_service_FILL")
    return result, summary, owners


def project(root, state, activities, *, generated_at, consumed=None):
    consumed = {} if consumed is None else consumed
    consumed[str(Path(root) / CASH)] = binding(Path(root) / CASH)
    executions, orders, owners = receive_executions(state, activities, consumed)
    pos = state["account"]["positions"]
    at = state["account"]["observed_at"]
    now = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    assert datetime.fromisoformat(at.replace("Z", "+00:00")) <= now
    owned = defaultdict(lambda: D(0))
    confirmed_owned = defaultdict(lambda: D(0))
    books = {}
    for name, book in state["books"].items():
        qs = quantities(book)
        for s, q in qs.items():
            owned[s] += q
        evidence = book["evidence"]
        risk = evidence["risk"]
        flows = evidence.get("allocation_flows", [])
        initial = number(risk["initial_capital"])
        netflows = sum((number(x["amount_USD"]) for x in flows), D(0))
        capital = initial + netflows
        assert number(risk.get("net_allocation_flows", netflows)) == netflows
        assert number(evidence.get("allocated_capital", capital)) == capital
        missing = []
        basis = None
        try:
            basis = fifo(executions[name])
            assert executions[name] or not qs, (
                "Opening execution support is absent for stored holdings"
            )
        except AssertionError as err:
            missing.append(str(err))
            basis = None
        fill_q = basis["quantity"] if basis else qs
        if basis is not None:
            for symbol, q in fill_q.items():
                confirmed_owned[symbol] += q
        lot_drift = (
            {
                s: dict(stored=qs.get(s, D(0)), confirmed_execution=fill_q.get(s, D(0)))
                for s in set(qs) | set(fill_q)
                if qs.get(s, D(0)) != fill_q.get(s, D(0))
            }
            if basis is not None
            else None
        )
        if lot_drift:
            missing.append(
                "Stored funding lots differ EXACTLY from confirmed execution quantities; residue retained, no rounding/repair or certified unit NAV"
            )
        raw_indicative = {
            s: q * number(pos[s]["current_price"]) if s in pos else None for s, q in qs.items()
        }
        market = {
            s: q * number(pos[s]["current_price"]) if s in pos and basis is not None else None
            for s, q in fill_q.items()
        }
        mv = (
            sum(market.values(), D(0))
            if basis is not None and all(v is not None for v in market.values())
            else None
        )
        fallback = [o for o in orders if o["book"] == name and not o["detail_complete"]]
        if fallback:
            missing.append(
                "Actual individual FILL details absent for "
                + str(len(fallback))
                + " orders; reported cumulative-average basis only"
            )
        realized = basis["realized"] if basis else None
        cost = sum(basis["cost"].values(), D(0)) if basis else None
        unreal = mv - cost if mv is not None and cost is not None else None
        gross = realized + unreal if realized is not None and unreal is not None else None
        if gross is not None:
            assert gross == mv + basis["sales"] - basis["buys"]
        cash = original_nav_cash(root, book["cashbook"])
        pending = book["pending"]
        reserved = sum(
            (
                number(p["amount"])
                for row in pending.values()
                for p in row.get("remaining_funding", [])
            ),
            D(0),
        )
        fees = sum((number(row["amount"]) for row in book["fees"].values()), D(0))
        rec_div = sum((number(row["amount"]) for row in book["cashbook"]["dividends"]), D(0))
        if basis:
            ledger_gap = cash - (capital + basis["sales"] - basis["buys"] - fees + rec_div)
        else:
            ledger_gap = None
        missing += [
            "Complete attributable actual fee/commission statement is not received",
            "Dividend/rights/income completeness and broker settlement cash reconciliation are not certified",
            "Broker price source time is absent; latest saved current_price reception time is supplied",
        ]
        books[name] = dict(
            stored_lot_quantities=qs,
            stored_lot_indicative_market_value=raw_indicative,
            confirmed_execution_quantities=basis["quantity"] if basis is not None else None,
            stored_lot_quantity_drift=lot_drift,
            valuation_quantities="confirmed execution prefix; raw stored funding quantities remain separate"
            if basis is not None
            else "UNKNOWN execution support; raw lots are unconfirmed observations only",
            allocated_capital_usd=capital,
            initial_allocation_usd=initial,
            internal_allocation_flows_usd=netflows,
            allocation_flows=flows,
            external_broker_deposit_attribution_usd=None,
            holdings=[
                dict(
                    symbol=s,
                    quantity=q,
                    mark=number(pos[s]["current_price"]) if s in pos else None,
                    market_value=market[s],
                    FIFO_cost=basis["cost"].get(s, D(0)) if basis else None,
                )
                for s, q in fill_q.items()
            ],
            market_value_usd=mv,
            realized_FIFO_before_unverified_costs_usd=realized,
            unrealized_FIFO_before_unverified_costs_usd=unreal,
            remaining_FIFO_cost_usd=cost,
            trading_PnL_before_unverified_items_usd=gross,
            tracking_return_on_assigned_capital_pct=gross / capital * 100
            if gross is not None and capital
            else None,
            execution_basis_status="complete_saved_FILL_inventory"
            if not fallback and basis
            else "reported_average_provisional"
            if basis
            else "unknown",
            recorded_book_economic_cash_usd=cash,
            recorded_book_marked_value_before_unverified_items_usd=cash + mv
            if mv is not None
            else None,
            principal_vs_book_cash_residual_usd=ledger_gap,
            recorded_actual_fee_debits_usd=fees,
            complete_actual_fees_usd=None,
            estimated_incremental_cost_usd=None,
            recorded_income_receivables_usd=rec_div,
            complete_income_usd=None,
            recorded_purchase_obligations_usd=sum(
                (number(r["amount"]) for r in book["cashbook"]["purchases"]), D(0)
            ),
            recorded_sale_receivables_usd=sum(
                (number(r["amount"]) for r in book["cashbook"]["sales"]), D(0)
            ),
            remaining_reservations_usd=reserved,
            reservation_note="Includes retained fee allowances; not an expense or released cash. Past due date does not certify settlement.",
            pending_lock_count=len(pending),
            applied_fill_receipt_count=len(book["fills"]),
            halted=risk.get("halted"),
            killed=risk.get("killed"),
            retained_high_water=risk.get("high_water"),
            certified_net_PnL_usd=None,
            certified_return_pct=None,
            missing_evidence=missing,
        )
    actual = {s: number(p["qty"]) for s, p in pos.items() if number(p["qty"])}
    mismatch = {
        s: dict(owned=owned.get(s, D(0)), broker=actual.get(s, D(0)))
        for s in set(owned) | set(actual)
        if owned.get(s, D(0)) != actual.get(s, D(0))
    }
    confirmed_mismatch = {
        s: dict(confirmed=confirmed_owned.get(s, D(0)), broker=actual.get(s, D(0)))
        for s in set(confirmed_owned) | set(actual)
        if confirmed_owned.get(s, D(0)) != actual.get(s, D(0))
    }
    unsupported = [name for name, b in books.items() if b["confirmed_execution_quantities"] is None]
    if not unsupported:
        assert not confirmed_mismatch, (
            "Confirmed execution prefix versus broker quantity mismatch: " + str(confirmed_mismatch)
        )
    sleeves = {}
    numeric = [
        "allocated_capital_usd",
        "initial_allocation_usd",
        "internal_allocation_flows_usd",
        "market_value_usd",
        "realized_FIFO_before_unverified_costs_usd",
        "unrealized_FIFO_before_unverified_costs_usd",
        "remaining_FIFO_cost_usd",
        "trading_PnL_before_unverified_items_usd",
        "recorded_book_economic_cash_usd",
        "recorded_book_marked_value_before_unverified_items_usd",
        "principal_vs_book_cash_residual_usd",
        "recorded_actual_fee_debits_usd",
        "recorded_income_receivables_usd",
        "recorded_purchase_obligations_usd",
        "recorded_sale_receivables_usd",
        "remaining_reservations_usd",
        "pending_lock_count",
        "applied_fill_receipt_count",
    ]
    for policy in POLICIES:
        names = [policy + "/" + c for c in CHILDREN] if policy in CENTS else [policy]
        if policy in CENTS:
            assert [books[n]["allocated_capital_usd"] for n in names] == [
                D(c) / 100 for c in CENTS[policy]
            ]
        assert sum((books[n]["allocated_capital_usd"] for n in names), D(0)) == 20000
        row = {
            k: sum((books[n][k] for n in names), D(0))
            if all(books[n][k] is not None for n in names)
            else None
            for k in numeric
        }
        row.update(
            policy=policy,
            child_books=names if policy in CENTS else [],
            capital_includes_children_once=True,
            certified_net_PnL_usd=None,
            certified_return_pct=None,
            complete_actual_fees_usd=None,
            estimated_incremental_cost_usd=None,
            complete_income_usd=None,
            tracking_return_on_assigned_capital_pct=row["trading_PnL_before_unverified_items_usd"]
            / 200
            if row["trading_PnL_before_unverified_items_usd"] is not None
            else None,
            execution_basis_status="complete_saved_FILL_inventory"
            if all(
                books[n]["execution_basis_status"] == "complete_saved_FILL_inventory" for n in names
            )
            else "provisional_or_unknown",
        )
        holdings = defaultdict(lambda: D(0))
        for name in names:
            for h in books[name]["holdings"]:
                holdings[h["symbol"]] += h["quantity"]
        row["display_aggregate_holdings"] = dict(holdings)
        row["display_only_not_executable_parent_orders"] = True
        row["display_holdings_support"] = (
            "confirmed_execution_prefix"
            if all(books[n]["confirmed_execution_quantities"] is not None for n in names)
            else "contains_unconfirmed_raw_observations"
        )
        sleeves[policy] = row
    broker_value = sum((number(v["market_value"]) for v in pos.values()), D(0))
    own_value = (
        sum((b["market_value_usd"] for b in books.values()), D(0))
        if all(b["market_value_usd"] is not None for b in books.values())
        else None
    )
    return dict(
        schema_version=1,
        generated_at=generated_at,
        snapshot_heartbeat=state["heartbeat_at"],
        broker_account_observed_at=at,
        broker_mark_as_of=None,
        mark_freshness="saved broker current_price, no individual price timestamp; not a fresh market observation",
        mark_reception_age_seconds=D(
            str((now - datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds())
        ),
        net_PnL_status="N_A_uncertified",
        basis_note="FIFO within each separately owned book, not pooled broker average basis. Actual fill prices already include execution spread; no extra spread or historical10bp debit. Missing individual FILL detail is distinctly labelled as reported cumulative-average basis, not invented FILL rows.",
        sleeves=sleeves,
        books=books,
        quantity_reconciliation=dict(
            stored_lot_exact=not mismatch,
            stored_lot_owned=dict(owned),
            broker=actual,
            stored_lot_mismatches=mismatch,
            confirmed_execution_exact=not confirmed_mismatch if not unsupported else None,
            confirmed_execution_owned=dict(confirmed_owned) if not unsupported else None,
            confirmed_execution_partial_owned=dict(confirmed_owned),
            unsupported_execution_basis_books=unsupported,
            confirmed_execution_mismatches=confirmed_mismatch if not unsupported else None,
        ),
        market_value_reconciliation=dict(
            sum_owned=own_value,
            broker_reported_sum=broker_value,
            residual=own_value - broker_value if own_value is not None else None,
        ),
        shared_account_context=dict(
            equity=state["account"]["equity"],
            cash=state["account"]["cash"],
            not_sleeve_return=True,
            broker_position_cost_basis_total=sum(
                (number(p["cost_basis"]) for p in pos.values()), D(0)
            ),
            broker_position_unrealized_total=sum(
                (number(p["unrealized_pl"]) for p in pos.values()), D(0)
            ),
            account_equity_minus_cash_minus_position_value=number(state["account"]["equity"])
            - number(state["account"]["cash"])
            - broker_value,
        ),
        unattributed_saved_FILL_ids=[
            r["id"] for r in activities["activities"] if r["order_id"] not in owners
        ],
        order_basis=orders,
        executions=executions,
        consumed_bindings=list(consumed.values()),
        unknown_components=[
            "Actual fees/commissions and complete cash/nontrade statements",
            "Full dividend/rights/income and original/current price basis certification",
            "LSTM later individual FILL detail and cumulative-average precision",
            "Broker settlement of retained receivables/obligations; no release inferred",
        ],
        no_account_or_ledger_mutation=True,
        no_annualized_return_or_Sharpe=True,
    )


def clean(value):
    if isinstance(value, D):
        return str(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--activities", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    consumed = {}
    state = checked(binding(a.snapshot), consumed)
    activities = checked(binding(a.activities), consumed)
    for name, row in state["baseline"].items():
        data = Path(row["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        consumed[row["path"]] = binding(row["path"])
        before = json.loads(data, parse_float=D)["snapshot"]
        assert all(state["books"][name]["fills"][fid] == r for fid, r in before["fills"].items())
    result = project(
        a.root,
        state,
        activities,
        generated_at=datetime.now(UTC).isoformat(),
        consumed=consumed,
    )
    with a.output.open("x") as h:
        json.dump(clean(result), h, indent=2, allow_nan=False)
        h.write("\n")


if __name__ == "__main__":
    main()
