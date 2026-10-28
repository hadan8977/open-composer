"""Three selected virtual sleeves inside one owner-bound paper account.

This is an allocation/ownership guard around existing SourceStateCheckpoint
books. It neither moves cash between books nor creates broker authority.
Callers hold the existing global submission/control locks and this account lock.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import number
from open_composer.intraday_runner.source_activity_reception import save
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory, _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint

ACCOUNT = "fa6147de4f85f4f14f225c59eebb9ecc4c764e87571f413afebcb63aa76c81d4"
BASE = "BASE-CURRENT-INITIALIZATION-20261019"
H5 = "H5-LEARNED-SWING-PAPER-VALIDATION-20261019"
LSTM = "CROSS-ASSET-LSTM-PAPER-VALIDATION-20261019"
STATE = "BASE-STATE-BUDGET-PAPER-VALIDATION-20261019"
EQUAL = "MULTI-EQUAL-PAPER-VALIDATION-20261019"
HIERARCHICAL = "MULTI-HIERARCHICAL-PAPER-VALIDATION-20261019"
COMBINED_CAP = Decimal("120000")  # Exact selected inventory, not an owner global ceiling.
SLOTS = {
    BASE: ("dia-base-initialization-20261019", "basecur-20261019-fa6147de"),
    H5: ("h5-learned-swing-validation-20261019", "h5cur-20261019-fa6147de"),
    LSTM: ("lstm-crossasset-validation-20261019", "lstmcur-20261019-fa6147de"),
    STATE: ("base-state-budget-validation-20261019", "basest-20261019-fa6147de"),
    EQUAL: ("multi-equal-validation-20261019", "multeq-20261019-fa6147de"),
    HIERARCHICAL: ("multi-hierarchical-validation-20261019", "multhi-20261019-fa6147de"),
}


def slot(root, task):
    if task not in SLOTS:
        raise ValueError("not an owner-selected validation sleeve")
    directory, namespace = SLOTS[task]
    return root / "reports/paper/intraday" / directory / ACCOUNT, namespace


def receive_partition(root, binding):
    decision = json.loads(bound_bytes(root, binding))
    if decision.get("event_id") == "main-existing-paper-six-candidate-allocation-20261019":
        rows = decision["candidate_inventory"]
        funding = decision["funding"]
        if (
            [r.get("task_id") for r in rows] != list(SLOTS)
            or any(
                type(r.get("initial_allocation_USD")) is not int
                or r["initial_allocation_USD"] != 20000
                for r in rows
            )
            or funding.get("selected_six_initial_allocations_total_USD") != 120000
            or funding.get("account_hash") != ACCOUNT
            or funding.get("paper_only") is not True
            or funding.get("long_cash") is not True
            or funding.get("per_portfolio_gross_max_own_NAV_multiple") != 1
            or funding.get("no_cross_trial_idle_cash_lending") is not True
            or funding.get("no_double_reserved_account_cash_or_sale_AR") is not True
        ):
            raise ValueError("wrong exact six-policy inventory/funding scope")
        bound_bytes(root, decision["owner_directive"])
        bound_bytes(root, decision["supersedes_allocation_only"])
        return decision
    p = decision["capital"]
    if (
        p.get("combined_max_USD") != 20000
        or p.get("BASE_USD") != 10000
        or p.get("no_inter_sleeve_transfer_or_borrowed_idleallocation") is not True
        or p.get("same_verified_isolated_account") is not True
        or p.get("long_cash_only") is not True
        or p.get("gross_max") != 1
    ):
        raise ValueError("actual current shared allocation differs")
    caps = {BASE: p["BASE_USD"], H5: p.get("H5_swing_USD"), LSTM: p.get("LSTM_USD")}
    if any(type(v) is not int for v in caps.values()):
        raise ValueError("unknown sleeve allocation")
    if decision.get("selected_task") == LSTM:
        if (
            caps != {BASE: 10000, H5: 6000, LSTM: 4000}
            or decision.get("allocation_by_task_USD") != caps
            or decision.get("selected_tasks") != [BASE, H5, LSTM]
        ):
            raise ValueError("wrong exact three-sleeve partition")
        if (
            decision.get("BASE_partition_continuation", {}).get(
                "explicitly_authorized_affected_extension"
            )
            is not True
        ):
            raise ValueError("BASE partition successor not authorized")
        bound_bytes(root, decision["account_binding"])
        bound_bytes(root, decision["prior_partition"])
    elif decision.get("selected_task") == H5:
        # Retained original definition, for exact predecessor/fallback reception.
        # Actual active authority still requires its exact independent op/native binding.
        if caps != {BASE: 10000, H5: 10000, LSTM: 0}:
            raise ValueError("wrong exact legacy two-sleeve partition")
    else:
        raise ValueError("unselected partition")
    bound_bytes(root, decision["owner_instruction"])
    return decision


def allocation_map(root, binding):
    decision = receive_partition(root, binding)
    if "candidate_inventory" in decision:
        return {
            r["task_id"]: Decimal(r["initial_allocation_USD"])
            for r in decision["candidate_inventory"]
        }
    p = decision["capital"]
    return {
        BASE: Decimal(p["BASE_USD"]),
        H5: Decimal(p["H5_swing_USD"]),
        LSTM: Decimal(p["LSTM_USD"]),
    }


def allocation(root, binding, task):
    cap = allocation_map(root, binding).get(task)
    if cap is None or cap <= 0:
        raise ValueError("unallocated sleeve")
    return cap


class ValidationAccountPartition:
    def __init__(self, root, binding, *, write_guard=None):
        self.root, self.binding = Path(root), binding
        self.write_guard = write_guard
        receive_partition(self.root, binding)
        # Inside the original BASE storage root; no second uncounted registry.
        self.directory = (
            self.root / "reports/paper/intraday/dia-base-initialization-20261019/.account-envelope"
        )
        self.held = False

    def _before_write(self, path, size, *, atomic=True):
        guard = getattr(self, "write_guard", None)
        if guard is not None and guard(path, size, atomic=atomic) is not None:
            raise ValueError("shared account storage guard must raise or return None")

    @contextmanager
    def locked(self):
        self._before_write(self.directory / "account.lock", 0, atomic=False)
        _ensure_durable_directory(self.directory)
        with (self.directory / "account.lock").open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.held = True
            try:
                receive_partition(self.root, self.binding)
                yield
            finally:
                self.held = False

    def register(self, task, authority_binding):
        if not self.held:
            raise ValueError("shared account lock absent")
        cap = allocation(self.root, self.binding, task)
        auth = json.loads(bound_bytes(self.root, authority_binding))
        directory, namespace = slot(self.root, task)
        if (
            auth.get("task_id") != task
            or auth.get("account_hash") != ACCOUNT
            or number(auth.get("capital_usd")) != cap
            or auth.get("namespace") != namespace
            or auth.get("ledger_root") != str(directory)
            or auth.get("partition") != self.binding
        ):
            raise ValueError("slot registration differs from exact authority")
        path = self.directory / (task + ".json")
        if path.is_symlink():
            raise ValueError("aliased slot registration")
        value = dict(
            task=task,
            authority=authority_binding,
            partition=self.binding,
            ledger_root=str(directory),
            namespace=namespace,
            allocation=int(cap),
        )
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise ValueError("registered slot cannot silently rebind/reset")
        else:
            size = len(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode()) + 1
            self._before_write(path, size)
            save(path, value)

    def books(self):
        if not self.held:
            raise ValueError("shared account lock absent")
        if self.directory.exists() and {p.name for p in self.directory.glob("*.json")} - {
            task + ".json" for task in SLOTS
        }:
            raise ValueError(
                "unselected third/retired registered book must be resolved, not ignored"
            )
        result = {}
        caps = allocation_map(self.root, self.binding)
        for task in SLOTS:
            directory, namespace = slot(self.root, task)
            pointer = self.directory / (task + ".json")
            store = SourceStateCheckpoint(
                directory / "checkpoints",
                account_hash=ACCOUNT,
                sleeve_id=task,
                write_guard=getattr(self, "write_guard", None),
            )
            if pointer.is_symlink():
                raise ValueError("aliased slot pointer")
            if not pointer.exists():
                if (directory / "checkpoints").exists():
                    raise ValueError("orphan unregistered checkpoint; no assumed empty slot")
                continue
            cap = caps.get(task, Decimal(0))
            if cap <= 0:
                raise ValueError("registered book is not allocated in active partition")
            metadata = json.loads(pointer.read_text())
            if (
                metadata.get("partition") != self.binding
                or metadata.get("task") != task
                or metadata.get("ledger_root") != str(directory)
                or metadata.get("namespace") != namespace
                or number(metadata.get("allocation")) != cap
            ):
                raise ValueError("slot pointer identity changed")
            auth = json.loads(bound_bytes(self.root, metadata["authority"]))
            if (
                number(auth.get("capital_usd")) != cap
                or auth.get("account_hash") != ACCOUNT
                or auth.get("namespace") != namespace
                or auth.get("task_id") != task
                or auth.get("ledger_root") != str(directory)
                or auth.get("partition") != self.binding
            ):
                raise ValueError("slot scope changed")
            current = store.load()
            if current is None:
                raise ValueError("registered slot has no complete checkpoint")
            value = current["snapshot"]
            if Decimal(str(value["evidence"]["allocated_capital"])) != cap:
                raise ValueError("never reset a prior differently funded actual book")
            result[task] = dict(revision=_hash(current), snapshot=value, namespace=namespace)
        return result

    @staticmethod
    def totals(books):
        quantities, owners = {}, {}
        net_cash, pending_cash, pending_buys = Decimal(0), Decimal(0), Decimal(0)
        allocated = Decimal(0)
        for task, book in books.items():
            if task not in SLOTS:
                raise ValueError("unregistered sleeve")
            value = book["snapshot"]
            cap = number(value["evidence"]["allocated_capital"])
            if (
                cap
                not in {
                    BASE: {Decimal(10000), Decimal(20000)},
                    H5: {Decimal(6000), Decimal(10000), Decimal(20000)},
                    LSTM: {Decimal(4000), Decimal(20000)},
                    STATE: {Decimal(20000)},
                    EQUAL: {Decimal(20000)},
                    HIERARCHICAL: {Decimal(20000)},
                }[task]
            ):
                raise ValueError("unrecognized funded sleeve allocation")
            allocated += cap
            cash = value["cashbook"]
            net_cash += number(cash["cash"])
            net_cash += sum((number(x["amount"]) for x in cash["sales"]), Decimal(0))
            net_cash -= sum((number(x["amount"]) for x in cash["purchases"]), Decimal(0))
            for symbol, lots in cash["lots"].items():
                quantities[symbol] = quantities.get(symbol, Decimal(0)) + sum(
                    (number(lot["quantity"]) for lot in lots), Decimal(0)
                )
            for cid in value["consumed_ids"]:
                if cid in owners:
                    raise ValueError("cross-sleeve duplicate intent identity")
                owners[cid] = task
            for row in value["pending"].values():
                pending_cash += sum(
                    (
                        number(p["amount"])
                        for p in row.get("remaining_funding", [])
                        if p["source"] == "cash"
                    ),
                    Decimal(0),
                )
                if row["side"] == "buy":
                    pending_buys += number(row["quantity"] - row["filled"]) * number(
                        row["limit_price"]
                    )
        caps = [number(b["snapshot"]["evidence"]["allocated_capital"]) for b in books.values()]
        if any(c != 20000 for c in caps) and (any(c == 20000 for c in caps) or allocated > 20000):
            raise ValueError("legacy aggregate or mixed funding definitions")
        if allocated > COMBINED_CAP:
            raise ValueError("aggregate allocation expanded")
        return dict(
            quantities={s: q for s, q in quantities.items() if q},
            owners=owners,
            net_cash=net_cash,
            pending_cash=pending_cash,
            pending_buys=pending_buys,
            allocated=allocated,
        )

    def guard_new_risk(self, observation, task):
        books = self.books()
        if task not in books:
            raise ValueError("own funded book missing")
        if observation.get("other_checkpoint_hashes") != {
            k: b["revision"] for k, b in books.items() if k != task
        }:
            raise ValueError("other sleeve changed after account capture")
        totals = self.totals(books)
        actual_gross = number(observation["account_marked_value"])
        funds = number(observation["account_unborrowed_available"])
        selected = sum(allocation_map(self.root, self.binding).values())
        unallocated = selected - totals["allocated"]
        if unallocated < 0 or max(Decimal(0), totals["net_cash"]) + unallocated > funds:
            raise ValueError("actual unborrowed funds do not cover separate selected commitments")
        if actual_gross + totals["pending_buys"] > selected or totals["pending_cash"] > funds:
            raise ValueError("shared account gross/funding envelope exceeded")
        return books

    @staticmethod
    def account_view(books, task, positions, orders, activities):
        """Partition saved authenticated rows; never infer ownership from a prefix."""
        if task not in books:
            raise ValueError("own complete book absent")
        totals = ValidationAccountPartition.totals(books)
        actual, marks = {}, {}
        for row in positions:
            symbol, qty = row["symbol"], number(row["qty"])
            price, value = number(row["current_price"]), number(row["market_value"])
            if (
                symbol in actual
                or qty <= 0
                or qty != qty.to_integral_value()
                or row.get("side") != "long"
                or price <= 0
                or abs(qty * price - value) > Decimal(".01")
            ):
                raise ValueError("invalid actual aggregate holding/mark")
            actual[symbol], marks[symbol] = qty, price
        if any(cid not in totals["owners"] for cid in orders):
            raise ValueError("foreign/unregistered account order")
        order_owners = {row["id"]: totals["owners"][cid] for cid, row in orders.items()}
        if len(order_owners) != len(orders):
            raise ValueError("duplicate broker order identity")
        known = {}
        for owner, book in books.items():
            for field in ("fills", "fees"):
                for key in book["snapshot"][field]:
                    if key in known:
                        raise ValueError("duplicate cross-book activity")
                    known[key] = owner
        owned_activities, unassigned = [], []
        for row in activities:
            owner = known.get(row.get("id"))
            by_order = order_owners.get(row.get("order_id"))
            if owner is not None and by_order is not None and owner != by_order:
                raise ValueError("activity ownership conflict")
            owner = owner or by_order
            if owner == task:
                owned_activities.append(row)
            elif owner is None:
                unassigned.append(row)
        own_cash = books[task]["snapshot"]["cashbook"]
        own_qty = {
            s: sum((number(lot["quantity"]) for lot in lots), Decimal(0))
            for s, lots in own_cash["lots"].items()
        }
        own_qty = {s: q for s, q in own_qty.items() if q}
        units_complete = actual == totals["quantities"]
        holdings = []
        for symbol, qty in own_qty.items():
            if symbol not in marks or qty != qty.to_integral_value():
                units_complete = False
                continue
            holdings.append(
                dict(
                    symbol=symbol,
                    quantity=int(qty),
                    owned=units_complete,
                    current_price=str(marks[symbol]),
                    market_value=str(qty * marks[symbol]),
                )
            )
        own_positions = []
        for row in positions:
            symbol = row["symbol"]
            if symbol in own_qty:
                own_positions.append(
                    {
                        **row,
                        "qty": str(own_qty[symbol]),
                        "market_value": str(own_qty[symbol] * marks[symbol]),
                        "derived_own_sleeve_projection": True,
                    }
                )
        return dict(
            totals=totals,
            holdings=holdings,
            units_complete=units_complete,
            own_positions=own_positions,
            own_orders={c: o for c, o in orders.items() if totals["owners"][c] == task},
            own_activities=owned_activities,
            unassigned_activities=unassigned,
            all_activities_known=all(r.get("id") in known for r in activities),
            account_marked_value=sum((number(p["market_value"]) for p in positions), Decimal(0)),
            other_checkpoint_hashes={k: b["revision"] for k, b in books.items() if k != task},
        )
