"""Actual PK/SIG order shapes and failure/restart semantics; no authenticated broker calls."""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from test_book_paper import FakeClient, etb, make_target

from open_composer.book_paper.plan import (
    BookEngineError,
    OrderPlan,
    _plan_hash,
    client_order_id,
    next_orders_receipt_path,
    orders_receipt_path,
    submit_plan,
    write_json_atomic,
    write_plan_file,
)
from open_composer.book_paper.post_close import fetch_broker_orders, reconcile
from open_composer.book_paper.reversal import reversal_legs

DAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 19, 20, tzinfo=UTC)


def not_found():
    exc = RuntimeError("not found")
    exc.status_code = 404
    return exc


def example(symbol="PK", current=-9, post=1, price=15.59):
    side = "buy" if post > current else "sell"
    qty = abs(post - current)
    row = dict(
        symbol=symbol,
        current_qty=current,
        post_qty=post,
        side=side,
        qty=qty,
        reference_price=price,
        notional=round(qty * price, 2),
        type="market",
        time_in_force="cls",
        opens_or_increases_short=post < 0 and side == "sell",
        already_submitted=False,
        client_order_id=client_order_id("book", "quant1", DAY, symbol, side, qty),
    )
    return OrderPlan(
        dict(
            status="ok",
            book_id="book",
            account="quant1",
            form="F1",
            decision_date="2026-10-14",
            execution_date=DAY.isoformat(),
            target_sha256="a" * 64,
            plan_sha256="b" * 64,
            orders=[row],
            post_trade_qty={symbol: post},
        )
    )


class ExecutionClient(FakeClient):
    def __init__(self, plan, *, close_status="filled", open_status="filled"):
        row = plan.orders[0]
        super().__init__(
            positions={row["symbol"]: row["current_qty"]},
            assets={row["symbol"]: etb(row["symbol"])},
        )
        self.legs = reversal_legs(row)
        self.close_status, self.open_status = close_status, open_status
        self.events = []
        self.after_close = lambda: None
        self.reject_open = False
        self.drop_close_ack = False

    def get_order_by_client_id(self, cid):
        self.events.append(("lookup", cid))
        for order in self.orders:
            if order.client_order_id == cid:
                return order
        raise not_found()

    def get_open_position(self, symbol):
        self.events.append(("position", self.positions.get(symbol, 0)))
        if not self.positions.get(symbol):
            raise not_found()
        qty = self.positions[symbol]
        return SimpleNamespace(qty=str(abs(qty)), side="short" if qty < 0 else "long")

    def get_orders(self, filter=None):
        result = list(self.orders)
        if getattr(filter, "symbols", None):
            result = [o for o in result if o.symbol in filter.symbols]
        if str(getattr(getattr(filter, "status", ""), "value", "")) == "open":
            result = [o for o in result if o.status in ("new", "accepted", "partially_filled")]
        return result

    def fill(self, order, status):
        filled = (
            float(order.qty)
            if status == "filled"
            else (float(order.qty) / 2 if status == "partially_filled" else 0)
        )
        old = float(order.filled_qty or 0)
        self.positions[order.symbol] += (filled - old) * (1 if order.side.value == "buy" else -1)
        order.status, order.filled_qty = status, str(filled)
        order.filled_avg_price = "20" if filled else None

    def submit_order(self, request):
        self.events.append(("submit", request.client_order_id))
        if any(o.client_order_id == request.client_order_id for o in self.orders):
            raise RuntimeError("duplicate ID must not be submitted")
        stage = "close" if request.client_order_id == self.legs[0]["client_order_id"] else "open"
        if stage == "open" and self.reject_open:
            exc = RuntimeError('{"code":40310000,"message":"insufficient buying power"}')
            exc.status_code = 403
            raise exc
        # Model the retained stock rejection, rather than permitting a fake atomic reversal.
        held = self.positions.get(request.symbol, 0)
        sign = 1 if request.side.value == "buy" else -1
        if held * sign < 0 and request.qty > abs(held):
            exc = RuntimeError(
                f"insufficient qty available (requested: {request.qty}, available: {abs(held)})"
            )
            exc.status_code = 403
            raise exc
        order = super().submit_order(request)
        self.fill(order, self.close_status if stage == "close" else self.open_status)
        if stage == "close":
            self.after_close()
            if self.drop_close_ack:
                raise TimeoutError("lost ack after fill")
        return order


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)


def run(client, plan, **kw):
    return submit_plan(client, plan, now=NOW, tif_mode="market", **kw)


@pytest.mark.parametrize(
    ("symbol", "current", "post", "price"),
    [
        ("PK", -9, 1, 15.59),
        ("SIG", -1, 1, 108.16),
        ("LONG", 9, -1, 20),
    ],
)
def test_retained_shapes_both_directions_fill_two_linked_legs(symbol, current, post, price):
    plan = example(symbol, current, post, price)
    original = copy.deepcopy(plan.payload)
    client = ExecutionClient(plan)
    receipt = run(client, plan)
    assert [r.qty for r in client.submitted] == [abs(current), abs(post)]
    assert all(r.time_in_force.value == "day" for r in client.submitted)
    assert len({r.client_order_id for r in client.submitted}) == 2
    assert plan.payload == original and client.positions[symbol] == post
    assert receipt["failed"] == receipt["deferred"] == []
    assert receipt["reversals"][0]["status"] == "filled"
    # A fresh broker close read and actual flat position precede the opening send.
    events = client.events
    second_submit = events.index(("submit", reversal_legs(plan.orders[0])[1]["client_order_id"]))
    assert ("position", 0) in events[:second_submit]
    assert (
        sum(
            e == ("lookup", reversal_legs(plan.orders[0])[0]["client_order_id"])
            for e in events[:second_submit]
        )
        >= 2
    )
    rec = reconcile(
        plan,
        make_target(),
        fetch_broker_orders(client, plan),
        client.positions,
        {symbol: price},
        [receipt],
    )
    assert rec["n_orders"] == rec["n_filled"] == 1
    assert rec["orders"][0]["filled_qty"] == abs(post - current)
    assert rec["orders"][0]["filled_avg_price"] == 20
    assert rec["n_position_drift_names"] == 0
    assert len(rec["orders"][0]["leg_evidence"]) == 2
    again = run(client, plan, prior_attempts=receipt["attempts"])
    assert len(client.submitted) == 2 and not again["failed"]


@pytest.mark.parametrize(
    "status",
    ["accepted", "partially_filled", "canceled", "rejected", "expired", "pending_new", "unknown"],
)
def test_nonfilled_close_never_opens_and_reports_actual_partial(status):
    plan = example()
    client = ExecutionClient(plan, close_status=status)
    receipt = run(client, plan)
    assert len(client.submitted) == 1 and receipt["deferred"]
    rec = reconcile(
        plan,
        make_target(),
        fetch_broker_orders(client, plan),
        client.positions,
        {"PK": 20},
        [receipt],
    )
    assert rec["orders"][0]["filled_qty"] == (4.5 if status == "partially_filled" else 0)
    assert rec["n_filled"] == 0 and rec["n_position_drift_names"] == 1


def test_restart_after_partial_close_can_open_once_when_close_really_finishes():
    plan = example()
    client = ExecutionClient(plan, close_status="partially_filled")
    first = run(client, plan)
    client.fill(client.orders[0], "filled")
    second = run(client, plan, prior_attempts=first["attempts"])
    assert len(client.submitted) == 2 and second["reversals"][0]["status"] == "filled"


def test_already_flat_without_our_close_evidence_defers():
    plan = example()
    client = ExecutionClient(plan)
    client.positions["PK"] = 0
    receipt = run(client, plan)
    assert client.submitted == [] and "position changed" in receipt["deferred"][0]["reason"]


def test_interruption_after_close_uses_same_plan_and_broker_fill():
    plan = example()
    client = ExecutionClient(plan)
    snapshots = []

    def crash():
        raise KeyboardInterrupt("process stopped after broker fill, before ack persistence")

    client.after_close = crash
    with pytest.raises(KeyboardInterrupt):
        run(client, plan, checkpoint=lambda report: snapshots.append(copy.deepcopy(report)))
    assert snapshots[-1]["attempts"][client.legs[0]["client_order_id"]]["outcome"] == "submitting"
    client.after_close = lambda: None
    receipt = run(client, plan, prior_attempts=snapshots[-1]["attempts"])
    assert len(client.submitted) == 2 and client.positions["PK"] == 1
    assert receipt["reversals"][0]["status"] == "filled"


def test_interruption_before_open_send_leaves_ambiguous_intent_and_no_blind_retry():
    plan = example()
    client = ExecutionClient(plan)
    snapshots = []

    def checkpoint(report):
        snapshots.append(copy.deepcopy(report))
        attempt = report["attempts"].get(client.legs[1]["client_order_id"], {})
        if attempt.get("outcome") == "submitting":
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run(client, plan, checkpoint=checkpoint)
    receipt = run(client, plan, prior_attempts=snapshots[-1]["attempts"])
    assert len(client.submitted) == 1 and client.positions["PK"] == 0
    assert any("prior attempt" in r["reason"] for r in receipt["deferred"])


def test_close_lost_ack_recovered_by_broker_lookup_not_inferred_from_exception():
    plan = example()
    client = ExecutionClient(plan)
    client.drop_close_ack = True
    first = run(client, plan)
    assert len(client.submitted) == 1 and first["failed"][0]["outcome"] == "acknowledgement_unknown"
    second = run(client, plan, prior_attempts=first["attempts"])
    assert len(client.submitted) == 2 and second["reversals"][0]["status"] == "filled"


def test_opening_failure_reconciles_close_once_and_is_not_retried():
    plan = example()
    client = ExecutionClient(plan)
    client.reject_open = True
    first = run(client, plan)
    assert first["failed"][0]["outcome"] == "submission_rejected"
    rec = reconcile(
        plan,
        make_target(),
        fetch_broker_orders(client, plan),
        client.positions,
        {"PK": 20},
        [first],
    )
    assert rec["n_partial"] == 1 and rec["n_submission_rejected"] == 1
    assert rec["orders"][0]["filled_qty"] == 9 and rec["orders"][0]["unfilled_qty"] == 1
    assert rec["position_drift_vs_plan"][0]["drift_qty"] == -1
    client.reject_open = False
    run(client, plan, prior_attempts=first["attempts"])
    assert len(client.submitted) == 1


@pytest.mark.parametrize("change", ["kill", "window", "etb", "shorting", "position", "working"])
def test_late_opening_guards(change):
    plan = example("LONG", 9, -1)
    client = ExecutionClient(plan)
    closed = False

    def after_close():
        nonlocal closed
        closed = True
        if change == "etb":
            client.assets["LONG"].easy_to_borrow = False
        if change == "position":
            client.positions["LONG"] = 3
        if change == "working":
            client.orders.append(
                SimpleNamespace(symbol="LONG", client_order_id="foreign", status="new")
            )

    client.after_close = after_close
    original_account = client.get_account

    def account():
        result = original_account()
        result.shorting_enabled = not (closed and change == "shorting")
        return result

    client.get_account = account

    def kill():
        if closed and change == "kill":
            raise RuntimeError("kill switch enabled")

    def clock():
        return datetime(2026, 10, 15, 19, 45, tzinfo=UTC) if closed and change == "window" else NOW

    receipt = run(client, plan, kill_switch_check=kill, clock=clock)
    assert len(client.submitted) == 1 and receipt["deferred"]


def test_conflicting_order_before_close_and_unavailable_reads_fail_closed():
    plan = example()
    client = ExecutionClient(plan)
    client.orders.append(SimpleNamespace(symbol="PK", client_order_id="foreign", status="accepted"))
    assert run(client, plan)["deferred"] and not client.submitted
    client.orders.clear()

    def unavailable(cid):
        raise TimeoutError("unknown broker state")

    client.get_order_by_client_id = unavailable
    assert run(client, plan)["deferred"] and not client.submitted


def test_close_filled_but_stale_position_does_not_open():
    plan = example()
    client = ExecutionClient(plan)
    client.after_close = lambda: client.positions.update(PK=-9)
    assert run(client, plan)["deferred"] and len(client.submitted) == 1


def test_cls_reversal_is_explicitly_unsupported_with_no_tif_conversion():
    plan = example()
    client = ExecutionClient(plan)
    receipt = submit_plan(client, plan, now=NOW, tif_mode="close")
    assert client.submitted == [] and receipt["deferred"]
    assert receipt["time_in_force"] == "cls"


def test_reconciliation_retained_403_is_rejected_while_no_evidence_is_missing():
    plan = example()
    cid = plan.orders[0]["client_order_id"]
    retained = {
        "failed": [
            {
                "client_order_id": cid,
                "error": "APIError",
                "message": '{"available":"9","code":40310000,"message":"insufficient qty"}',
            }
        ]
    }
    rejected = reconcile(plan, make_target(), [], {"PK": -9}, {"PK": 15.59}, [retained])
    missing = reconcile(plan, make_target(), [], {"PK": -9}, {"PK": 15.59})
    assert rejected["n_submission_rejected"] == 1 and rejected["n_missing"] == 0
    assert rejected["orders"][0]["filled_qty"] == 0
    assert missing["n_missing"] == 1


def test_stored_plan_survives_rebuild_and_receipts_are_append_only(monkeypatch, tmp_path):
    from open_composer.book_paper import cli

    plan = example()
    target = make_target(decision_date=date(2026, 10, 14), execution_date=DAY)
    plan.payload["target_sha256"] = target.payload_sha256
    plan.payload["plan_sha256"] = _plan_hash(plan.payload)
    expected_hash = plan.payload["plan_sha256"]
    write_plan_file(tmp_path, plan)
    first = orders_receipt_path(tmp_path, "quant1", DAY)
    write_json_atomic(first, {"staged_submission_version": 1, "plan_sha256": expected_hash})
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "make_trading_client", lambda _: ExecutionClient(plan))
    monkeypatch.setattr(
        "open_composer.book_paper.targets.target_path", lambda *a: tmp_path / "target"
    )
    (tmp_path / "target").touch()
    monkeypatch.setattr("open_composer.book_paper.targets.load_target_file", lambda _: target)
    # The original plan/hash is returned even though broker state has already changed.
    assert cli._build("quant1", "2026-10-14", None, 100)[3].payload == plan.payload
    rerun = next_orders_receipt_path(tmp_path, "quant1", DAY, NOW)
    write_json_atomic(rerun, {"attempts": {"cid": {"outcome": "submitting"}}})
    assert next_orders_receipt_path(tmp_path, "quant1", DAY, NOW) != rerun
    assert cli._prior_attempts(tmp_path, "quant1", DAY)["cid"]["outcome"] == "submitting"
    with cli._submission_lock(tmp_path, "quant1"):
        with pytest.raises(BookEngineError, match="another book submission"):
            with cli._submission_lock(tmp_path, "quant1"):
                pytest.fail("must not get concurrent lock")
    assert json.loads(first.read_text())["plan_sha256"] == expected_hash


@pytest.mark.parametrize("status", ["accepted", "partially_filled", "canceled", "rejected"])
def test_incomplete_open_is_explicit_and_duplicate_invocation_never_adds_orders(status):
    plan = example("PK", -9, 2)
    client = ExecutionClient(plan, open_status=status)
    first = run(client, plan)
    assert first["deferred"] and first["reversals"][0]["status"] == "deferred"
    second = run(client, plan, prior_attempts=first["attempts"])
    assert second["deferred"] and len(client.submitted) == 2
    rec = reconcile(
        plan,
        make_target(),
        fetch_broker_orders(client, plan),
        client.positions,
        {"PK": 20},
        [first, second],
    )
    assert rec["n_partial"] == 1
    assert rec["orders"][0]["filled_qty"] == (10 if status == "partially_filled" else 9)


def test_broker_id_collision_fails_identity_validation():
    plan = example()
    client = ExecutionClient(plan)
    # Client ID exists but fields do not match the frozen close request.
    client.orders.append(
        SimpleNamespace(
            client_order_id=client.legs[0]["client_order_id"],
            symbol="PK",
            side="buy",
            qty="999",
            time_in_force="day",
            status="filled",
            filled_qty="999",
        )
    )
    receipt = run(client, plan)
    assert client.submitted == [] and "identity differs" in receipt["deferred"][0]["reason"]


def test_legacy_parent_order_prevents_new_leg_ids():
    plan = example()
    client = ExecutionClient(plan)
    client.orders.append(
        SimpleNamespace(
            client_order_id=plan.orders[0]["client_order_id"], symbol="PK", status="rejected"
        )
    )
    assert run(client, plan)["deferred"] and not client.submitted


def test_close_rejection_before_ack_is_retained_without_open_or_blind_resubmit():
    plan = example()
    client = ExecutionClient(plan)

    def reject(request):
        exc = RuntimeError('{"code":40310000,"message":"shares held by another order"}')
        exc.status_code = 403
        raise exc

    client.submit_order = reject
    first = run(client, plan)
    assert first["failed"][0]["stage"] == "close" and first["deferred"]
    rec = reconcile(plan, make_target(), [], client.positions, {"PK": 20}, [first])
    assert rec["n_submission_rejected"] == 1 and rec["n_missing"] == 0
    # A retry retains the rejected intent even though a broker lookup is 404.
    second = run(client, plan, prior_attempts=first["attempts"])
    assert second["deferred"] and second["failed"] == [] and not client.submitted


def test_close_polling_can_observe_later_fill_without_background_loop():
    plan = example()
    client = ExecutionClient(plan, close_status="accepted")
    get = client.get_order_by_client_id
    observations = 0

    def delayed(cid):
        nonlocal observations
        result = get(cid)
        if cid == client.legs[0]["client_order_id"]:
            observations += 1
            if observations == 3:
                client.fill(result, "filled")
        return result

    client.get_order_by_client_id = delayed
    receipt = run(client, plan)
    assert observations == 3 and len(client.submitted) == 2
    assert receipt["reversals"][0]["status"] == "filled"


def test_fresh_lookup_ignores_stale_cached_accepted_order():
    plan = example()
    client = ExecutionClient(plan)
    first = run(client, plan)
    assert first["reversals"][0]["status"] == "filled"
    from open_composer.book_paper.plan import OrderLookup

    lookup = OrderLookup(client, DAY)
    cid = client.legs[0]["client_order_id"]
    lookup._by_id[cid] = SimpleNamespace(status="accepted")
    assert lookup.find(cid).status == "accepted"
    assert lookup.find(cid, fresh=True).status == "filled"


def test_historical_plan_rejected_before_any_broker_read_or_write():
    plan = example()
    plan.payload["execution_date"] = "2026-10-14"
    client = ExecutionClient(plan)
    with pytest.raises(BookEngineError, match="only sent on the execution date"):
        run(client, plan)
    assert client.events == client.submitted == []


def test_logical_vwap_and_qty_account_for_each_real_fill_once():
    plan = example()
    client = ExecutionClient(plan)
    receipt = run(client, plan)
    client.orders[0].filled_avg_price = "19"
    client.orders[1].filled_avg_price = "21"
    broker = fetch_broker_orders(client, plan)
    # Repeated observations of the same client ID do not count a second trade.
    rec = reconcile(
        plan, make_target(), broker + [broker[0]], client.positions, {"PK": 20}, [receipt]
    )
    assert rec["orders"][0]["filled_qty"] == 10
    assert rec["orders"][0]["filled_avg_price"] == pytest.approx(19.2)


def test_real_cli_checkpoint_precedes_close_and_second_invocation_is_idempotent(
    monkeypatch, tmp_path
):
    from typer.testing import CliRunner

    from open_composer.book_paper import cli

    plan = example()
    client = ExecutionClient(plan)

    class FrozenTime:
        @staticmethod
        def now(tz):
            return NOW

    monkeypatch.setattr(cli, "datetime", FrozenTime)
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_build", lambda *args: (tmp_path, client, None, plan))
    monkeypatch.setattr(cli, "_kill_switch_check", lambda root: lambda: None)
    monkeypatch.setattr(cli, "SUBMIT_PACE_SECONDS", 0)
    first_path = orders_receipt_path(tmp_path, "quant1", DAY)

    def check_durable_intent():
        receipt = json.loads(first_path.read_text())
        assert receipt["attempts"][client.legs[0]["client_order_id"]]["outcome"] == "submitting"
        assert (first_path.parents[1] / "plans" / f"{DAY}.json").exists()

    client.after_close = check_durable_intent
    args = ["submit", "--account", "quant1", "--submit", "--tif-mode", "market"]
    first = CliRunner().invoke(cli.book_paper_app, args)
    assert first.exit_code == 0, first.output
    original = first_path.read_bytes()
    second = CliRunner().invoke(cli.book_paper_app, args)
    assert second.exit_code == 0, second.output
    assert len(client.submitted) == 2 and first_path.read_bytes() == original
    assert len(list(first_path.parent.glob(f"{DAY}*.json"))) == 2


def test_cli_deferred_stage_has_nonzero_exit_and_durable_pending_receipt(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from open_composer.book_paper import cli

    plan = example()
    client = ExecutionClient(plan, close_status="accepted")

    class FrozenTime:
        @staticmethod
        def now(tz):
            return NOW

    monkeypatch.setattr(cli, "datetime", FrozenTime)
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_build", lambda *args: (tmp_path, client, None, plan))
    monkeypatch.setattr(cli, "_kill_switch_check", lambda root: lambda: None)
    monkeypatch.setattr(cli, "SUBMIT_PACE_SECONDS", 0)
    result = CliRunner().invoke(
        cli.book_paper_app, ["submit", "--account", "quant1", "--submit", "--tif-mode", "market"]
    )
    assert result.exit_code == 2 and "deferred" in result.output
    receipt = json.loads(orders_receipt_path(tmp_path, "quant1", DAY).read_text())
    assert receipt["deferred"] and len(client.submitted) == 1


def test_nonreversal_keeps_original_single_window_and_kill_admission():
    plan = example("PK", 0, 1)
    client = FakeClient()
    checked = []
    receipt = submit_plan(
        client,
        plan,
        now=NOW,
        tif_mode="market",
        clock=lambda: datetime(2026, 10, 15, 19, 46, tzinfo=UTC),
        kill_switch_check=lambda: checked.append("checked"),
    )
    assert len(client.submitted) == 1 and receipt["deferred"] == []
    assert checked == ["checked"]
