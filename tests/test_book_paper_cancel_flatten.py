"""T-20261002-42: book_paper cancel and flatten (emergency stop path; fake client only)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_book_paper import EXECUTION, NOW, FakeClient, etb, plan_for

from open_composer.book_paper.plan import (
    AccountState,
    AssetInfo,
    BookEngineError,
    cancel_open_orders,
    cancel_receipt_path,
    flatten_dry_run_receipt,
    flatten_plan,
    flatten_receipt_path,
    load_plan_file,
    make_asset_lookup,
    read_account_state,
    read_kill_switch_state,
    submit_flatten,
    submit_plan,
    write_json_atomic,
    write_plan_file,
)
from open_composer.paper_controls import set_paper_kill_switch

REGULAR = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)  # 14:00 ET, Friday
PRE_OPEN = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)  # 08:00 ET
AFTER_CLOSE = datetime(2026, 9, 18, 21, 0, tzinfo=UTC)  # 17:00 ET
AUCTION_CUTOFF = datetime(2026, 9, 18, 19, 50, tzinfo=UTC)  # 15:50 ET


class CancelClient(FakeClient):
    """FakeClient with cancel_order_by_id; ``sticky`` ids stay open (cancel too late)."""

    def __init__(self, *args, sticky=(), **kw):
        super().__init__(*args, **kw)
        self.cancelled: list[str] = []
        self.sticky = set(sticky)
        self.fail_cancel: set[str] = set()

    def get_orders(self, filter=None):
        status = getattr(filter, "status", None)
        if (
            str(getattr(status, "value", status)).lower() == "open"
        ):  # Alpaca: pending_cancel is open
            return [o for o in self.orders if o.status in ("new", "accepted", "pending_cancel")]
        return list(self.orders)

    def cancel_order_by_id(self, order_id):
        order = next(o for o in self.orders if o.id == order_id)
        if order_id in self.fail_cancel:
            error = RuntimeError("order is already filled")
            error.status_code = 422
            raise error
        self.cancelled.append(order_id)
        order.status = "pending_cancel" if order_id in self.sticky else "canceled"


def raw_order(oid: str, symbol: str, cid: str, status: str = "accepted"):
    return SimpleNamespace(
        id=oid,
        client_order_id=cid,
        symbol=symbol,
        qty="10",
        side="buy",
        time_in_force="cls",
        status=status,
        filled_qty="0",
        filled_avg_price=None,
    )


def book_client(**kw) -> CancelClient:
    names = ["L1", "L2", "L3", "S1", "SGOV", "SPY", "FRZ", "FRAC"]
    return CancelClient(assets={s: etb(s) for s in names}, **kw)


def plan_with_orders(client) -> object:
    return plan_for(client=client)


def submitted_ids(client) -> list[str]:
    return [r.client_order_id for r in client.submitted]


# --------------------------------------------------------------------------------------
# cancel
# --------------------------------------------------------------------------------------


def test_cancel_default_cancels_only_that_plans_ids(tmp_path: Path) -> None:
    client = book_client()
    plan = plan_for(client=client)
    submit_plan(client, plan, now=NOW)
    plan_ids = {o["client_order_id"] for o in plan.orders}
    client.orders.append(raw_order("x-other-day", "L1", "bk1-" + "e" * 40))  # book id, other plan
    receipt = cancel_open_orders(
        client, account="quant1", plan=plan, reason="stop test", now=REGULAR
    )
    assert {r["client_order_id"] for r in receipt["requested"]} == plan_ids
    assert receipt["scope"] == "plan" and receipt["n_requested"] == len(plan_ids)
    assert len(client.cancelled) == len(plan_ids) and "x-other-day" not in client.cancelled
    assert [r["client_order_id"] for r in receipt["still_open_after"]] == ["bk1-" + "e" * 40]
    assert receipt["plan_sha256"] == plan.payload["plan_sha256"]
    assert receipt["execution_date"] == EXECUTION.isoformat()


def test_cancel_all_book_cancels_only_bk1_ids() -> None:
    client = book_client(
        orders=[
            raw_order("a", "L1", "bk1-" + "a" * 40),
            raw_order("b", "L2", "bk1-flat-" + "b" * 36),
            raw_order("c", "SPY", "oc-manual-1"),
            raw_order("d", "SGOV", ""),
            raw_order("e", "S1", "BK1-upper"),
        ]
    )
    receipt = cancel_open_orders(client, account="quant1", reason="halt", now=REGULAR)
    assert receipt["scope"] == "all_book"
    assert sorted(client.cancelled) == ["a", "b"]
    assert {r["broker_order_id"] for r in receipt["untouched_open_orders"]} == {"c", "d", "e"}


def test_cancel_leaves_other_orders_untouched_and_open() -> None:
    client = book_client(orders=[raw_order("a", "L1", "bk1-" + "a" * 40)])
    client.orders += [raw_order("m", "AAPL", "manual-xyz"), raw_order("n", "MSFT", "oc-123")]
    plan = SimpleNamespace(
        payload={"orders": [{"client_order_id": "manual-xyz"}, {"client_order_id": "oc-123"}]},
        orders=[{"client_order_id": "manual-xyz"}, {"client_order_id": "oc-123"}],
        execution_date=EXECUTION,
    )
    # even a plan that (wrongly) lists non-book ids cannot make cancel touch them
    receipt = cancel_open_orders(client, account="quant1", plan=plan, reason="x", now=REGULAR)
    assert client.cancelled == [] and receipt["n_requested"] == 0
    assert {o.id for o in client.orders if o.status == "accepted"} == {"a", "m", "n"}


def test_cancel_receipt_lists_what_is_left_open_and_errors(tmp_path: Path) -> None:
    client = book_client(
        orders=[
            raw_order("a", "L1", "bk1-" + "a" * 40),
            raw_order("b", "L2", "bk1-" + "b" * 40),
            raw_order("c", "L3", "bk1-" + "c" * 40),
            raw_order("m", "AAPL", "manual-1"),
        ],
        sticky={"b"},
    )
    client.fail_cancel = {"c"}
    receipt = cancel_open_orders(client, account="quant1", reason="late", now=AUCTION_CUTOFF)
    left = {r["broker_order_id"]: r["status"] for r in receipt["still_open_after"]}
    assert left == {"b": "pending_cancel", "c": "accepted", "m": "accepted"}
    assert {r["broker_order_id"] for r in receipt["still_open_requested"]} == {"b", "c"}
    errors = {r["broker_order_id"]: r["response"] for r in receipt["requested"]}
    assert errors["a"] == "cancel_requested" and errors["c"] == "error:RuntimeError:422"
    assert receipt["n_request_errors"] == 1 and receipt["n_open_after"] == 3
    path = cancel_receipt_path(tmp_path, "quant1", EXECUTION, AUCTION_CUTOFF)
    assert path.name == "cancel-2026-09-18-195000.json" and path.parent.name == "orders"
    assert json.loads(write_json_atomic(path, receipt).read_text())["reason"] == "late"


def test_cancel_needs_reason_and_verified_client_and_ignores_kill_switch(
    sample_workspace: Path,
) -> None:
    client = book_client(orders=[raw_order("a", "L1", "bk1-" + "a" * 40)])
    with pytest.raises(BookEngineError, match="reason"):
        cancel_open_orders(client, account="quant1", reason=" ", now=REGULAR)
    plain = SimpleNamespace(get_orders=lambda filter=None: [], cancel_order_by_id=lambda i: None)
    with pytest.raises(BookEngineError, match="strict Alpaca Paper factory"):
        cancel_open_orders(plain, account="quant1", reason="x", now=REGULAR)
    set_paper_kill_switch(sample_workspace, enabled=True, reason="hold", updated_by="pytest")
    receipt = cancel_open_orders(client, account="quant1", reason="x", now=REGULAR)
    assert client.cancelled == ["a"] and receipt["n_open_after"] == 0


# --------------------------------------------------------------------------------------
# flatten
# --------------------------------------------------------------------------------------

POSITIONS = {"L1": 300, "L2": -200, "SGOV": 5000, "SPY": -40, "FRZ": 100, "FRAC": 2.6}
PRICES = {"L1": 50.0, "L2": 40.0, "SGOV": 100.0, "SPY": 500.0, "FRZ": 7.0, "FRAC": 10.0}
ASSETS = {
    "L1": AssetInfo("L1", True, True, True),
    "L2": AssetInfo("L2", False, False, True),  # short, not shortable: cover must still work
    "SGOV": AssetInfo("SGOV", True, True, True),
    "SPY": AssetInfo("SPY", True, True, True),
    "FRZ": AssetInfo("FRZ", False, False, False, status="inactive"),
    "FRAC": AssetInfo("FRAC", True, True, True),
}


def snapshot(**kw) -> AccountState:
    args = {"equity": 1_000_000.0, "positions": dict(POSITIONS), "position_prices": PRICES}
    args.update(kw)
    return AccountState(**args)


def make_flatten(state=None, **kw):
    args = {
        "account": "quant1",
        "execution_date": EXECUTION,
        "reason": "test",
        "mode": "close",
        "asset_lookup": ASSETS.get,
    }
    args.update(kw)
    return flatten_plan(state or snapshot(), **args)


def test_flatten_close_mode_sides_quantities_and_skips() -> None:
    plan = make_flatten()
    rows = {o["symbol"]: o for o in plan.orders}
    assert set(rows) == {"L1", "L2", "SGOV", "SPY", "FRAC"}
    assert (rows["L1"]["side"], rows["L1"]["qty"]) == ("sell", 300)  # long -> sell
    assert (rows["L2"]["side"], rows["L2"]["qty"]) == ("buy", 200)  # short -> buy to cover
    assert (rows["SGOV"]["side"], rows["SGOV"]["qty"]) == ("sell", 5000)  # no $100 minimum logic
    assert (rows["SPY"]["side"], rows["SPY"]["qty"]) == ("buy", 40)  # F2 core short
    assert (rows["FRAC"]["side"], rows["FRAC"]["qty"]) == ("sell", 2)  # whole shares only
    assert all(isinstance(o["qty"], int) and o["time_in_force"] == "cls" for o in plan.orders)
    assert rows["L1"]["notional"] == 15000.0
    sides = [o["side"] for o in plan.orders]
    assert sides == sorted(sides, key=lambda s: s != "sell")  # sells first
    assert plan.payload["residual_fractional"] == [{"symbol": "FRAC", "qty": pytest.approx(0.6)}]
    assert plan.payload["mode"] == "close" and plan.status == "ok"
    assert all(o["client_order_id"].startswith("bk1-flat-") for o in plan.orders)
    assert all(len(o["client_order_id"]) <= 128 for o in plan.orders)


def test_flatten_skips_and_lists_untradable_position() -> None:
    plan = make_flatten(snapshot(positions={"FRZ": 100, "GONE": -50, "L1": 10}))
    assert [o["symbol"] for o in plan.orders] == ["L1"]
    skipped = {row["symbol"]: row for row in plan.payload["skipped"]}
    assert skipped["FRZ"]["reason"] == "asset_not_active" and skipped["FRZ"]["value"] == 700.0
    assert skipped["GONE"]["reason"] == "asset_not_found" and skipped["GONE"]["price"] is None
    assert plan.payload["summary"]["n_skipped"] == 2
    only_frozen = make_flatten(snapshot(positions={"FRZ": 100}))
    assert only_frozen.status == "nothing_to_close" and only_frozen.orders == []


def test_flatten_market_mode_builds_day_orders() -> None:
    plan = make_flatten(mode="market")
    assert plan.payload["time_in_force"] == "day"
    assert {o["time_in_force"] for o in plan.orders} == {"day"}
    close = make_flatten(mode="close")
    assert {o["client_order_id"] for o in plan.orders}.isdisjoint(
        {o["client_order_id"] for o in close.orders}
    )
    with pytest.raises(BookEngineError, match="mode"):
        make_flatten(mode="limit")


def test_flatten_dry_run_sends_nothing() -> None:
    client = book_client(positions=dict(POSITIONS))
    plan = make_flatten(read_account_state(client))
    receipt = flatten_dry_run_receipt(plan, now=REGULAR)
    assert receipt["dry_run"] is True and receipt["sent"] == [] and client.submitted == []
    assert receipt["window"] == {"open_now": True, "detail": ""}
    off = flatten_dry_run_receipt(make_flatten(mode="market"), now=AFTER_CLOSE)
    assert off["window"]["open_now"] is False and "regular hours" in off["window"]["detail"]


def test_flatten_market_mode_refused_outside_regular_hours() -> None:
    client = book_client(positions=dict(POSITIONS))
    plan = make_flatten(mode="market")
    for when in (PRE_OPEN, AFTER_CLOSE):
        with pytest.raises(BookEngineError, match="regular hours"):
            submit_flatten(client, plan, now=when)
    assert client.submitted == []
    report = submit_flatten(client, plan, now=AUCTION_CUTOFF)  # market mode runs until the close
    assert len(report["sent"]) == 5
    assert {str(r.time_in_force.value).lower() for r in client.submitted} == {"day"}
    # close mode keeps the existing CLS window
    close_plan = make_flatten(mode="close")
    with pytest.raises(BookEngineError, match="15:45"):
        submit_flatten(book_client(), close_plan, now=AUCTION_CUTOFF)


def test_flatten_refused_while_open_orders_exist() -> None:
    state = snapshot(open_orders=(("L1", "bk1-" + "a" * 40),))
    with pytest.raises(BookEngineError, match="cancel"):
        make_flatten(state)
    # the send path re-reads the broker and refuses too (an order appeared after planning)
    client = book_client(
        positions=dict(POSITIONS), orders=[raw_order("m", "AAPL", "manual-1", "new")]
    )
    with pytest.raises(BookEngineError, match="open orders at the broker"):
        submit_flatten(client, make_flatten(), now=REGULAR)
    assert client.submitted == []


def test_flatten_client_order_ids_are_idempotent_on_rerun() -> None:
    client = book_client(positions=dict(POSITIONS))
    first_plan = make_flatten(read_account_state(client))
    again = make_flatten(read_account_state(client))
    assert [o["client_order_id"] for o in first_plan.orders] == [
        o["client_order_id"] for o in again.orders
    ]
    assert first_plan.payload["plan_sha256"] == again.payload["plan_sha256"]
    first = submit_flatten(client, first_plan, now=REGULAR)
    n_sent = len(client.submitted)
    assert n_sent == len(first["sent"]) == 5 and first["failed"] == []
    for order in client.orders:  # the first run's orders fill; nothing is open any more
        order.status = "filled"
    second = submit_flatten(client, again, now=REGULAR)
    assert second["sent"] == [] and len(second["skipped_existing"]) == 5
    assert len(client.submitted) == n_sent
    # cancelled orders keep their ids: a re-send needs --attempt 2, which gets new ids
    for order in client.orders:
        order.status = "canceled"
    third = submit_flatten(client, again, now=REGULAR)
    assert third["sent"] == [] and "attempt" in third["skipped_existing"][0]["hint"]
    retry = make_flatten(read_account_state(client), attempt=2)
    assert {o["client_order_id"] for o in retry.orders}.isdisjoint(
        {o["client_order_id"] for o in first_plan.orders}
    )
    assert len(submit_flatten(client, retry, now=REGULAR)["sent"]) == 5


def test_flatten_works_with_kill_switch_on_and_receipt_records_it(
    sample_workspace: Path,
) -> None:
    set_paper_kill_switch(
        sample_workspace, enabled=True, reason="drawdown stop", updated_by="pytest"
    )
    state = read_kill_switch_state(sample_workspace)
    assert state == {"enabled": True, "state": "read", "reason": "drawdown stop"}
    client = book_client(positions=dict(POSITIONS))
    plan = make_flatten(read_account_state(client), kill_switch=state)
    report = submit_flatten(client, plan, now=REGULAR)
    assert len(report["sent"]) == 5
    assert report["plan"]["kill_switch"]["enabled"] is True
    path = flatten_receipt_path(sample_workspace, "quant1", EXECUTION, REGULAR)
    assert path.name == "flatten-2026-09-18-180000.json"
    saved = json.loads(write_json_atomic(path, report).read_text())
    assert saved["plan"]["kill_switch"]["reason"] == "drawdown stop" and saved["dry_run"] is False
    missing = read_kill_switch_state(sample_workspace / "nowhere")
    assert missing["enabled"] is None and missing["state"] == "control_file_missing"


def test_flatten_requires_reason_verified_client_and_flatten_plan() -> None:
    with pytest.raises(BookEngineError, match="reason"):
        make_flatten(reason="")
    plain = SimpleNamespace(get_orders=lambda filter=None: [], submit_order=lambda r: None)
    with pytest.raises(BookEngineError, match="strict Alpaca Paper factory"):
        submit_flatten(plain, make_flatten(), now=REGULAR)
    book_plan = plan_for()
    with pytest.raises(BookEngineError, match="not a flatten plan"):
        submit_flatten(book_client(), book_plan, now=REGULAR)


def test_flatten_failed_order_is_reported_and_others_continue() -> None:
    client = book_client(positions=dict(POSITIONS))
    original = client.submit_order

    def flaky(request):
        if request.symbol == "SPY":
            raise RuntimeError("rejected")
        return original(request)

    client.submit_order = flaky
    report = submit_flatten(client, make_flatten(read_account_state(client)), now=REGULAR)
    assert [f["symbol"] for f in report["failed"]] == ["SPY"] and len(report["sent"]) == 4


def test_flatten_asset_lookup_comes_from_the_broker_client() -> None:
    client = book_client(positions={"L1": 5, "ZZZ": 3})  # ZZZ unknown to the broker (404)
    plan = make_flatten(read_account_state(client), asset_lookup=make_asset_lookup(client))
    assert [o["symbol"] for o in plan.orders] == ["L1"]
    assert plan.payload["skipped"][0]["symbol"] == "ZZZ"
    assert date.fromisoformat(plan.payload["execution_date"]) == EXECUTION


def test_plan_file_roundtrip_still_works_for_cancel_scope(tmp_path: Path) -> None:
    plan = plan_for(client=book_client())
    path = write_plan_file(tmp_path, plan)
    assert load_plan_file(path).orders == plan.orders


# --------------------------------------------------------------------------------------
# CLI wiring (fake client injected; no broker)
# --------------------------------------------------------------------------------------


def _cli(monkeypatch, tmp_path: Path, client) -> tuple:
    from typer.testing import CliRunner

    from open_composer.book_paper import cli as bp_cli

    monkeypatch.setattr(bp_cli, "make_trading_client", lambda account: client)
    monkeypatch.setattr(bp_cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return CliRunner(), bp_cli.book_paper_app


def test_cli_cancel_default_and_all_book_write_receipts(monkeypatch, tmp_path: Path) -> None:
    client = book_client()
    plan = plan_for(client=client)
    submit_plan(client, plan, now=NOW)
    write_plan_file(tmp_path, plan)
    client.orders.append(raw_order("m", "AAPL", "manual-1"))
    runner, app = _cli(monkeypatch, tmp_path, client)
    base = ["cancel", "--account", "quant1", "--reason", "cli test"]
    missing = runner.invoke(app, [*base, "--date", "2026-09-17"])
    assert missing.exit_code != 0 and client.cancelled == []
    result = runner.invoke(app, [*base, "--date", EXECUTION.isoformat()])
    assert result.exit_code == 0, result.output
    assert len(client.cancelled) == len(plan.orders) and "m" not in client.cancelled
    receipts = list((tmp_path / "book").rglob("cancel-*.json")) or list(
        tmp_path.rglob("cancel-*.json")
    )
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())["reason"] == "cli test"
    allbook = runner.invoke(app, [*base, "--all-book", "--date", EXECUTION.isoformat()])
    assert allbook.exit_code == 0, allbook.output


def test_cli_flatten_dry_run_sends_nothing_and_confirm_needs_window(
    monkeypatch, tmp_path: Path
) -> None:
    client = book_client(positions=dict(POSITIONS))
    runner, app = _cli(monkeypatch, tmp_path, client)
    base = ["flatten", "--account", "quant1", "--reason", "cli test"]
    dry = runner.invoke(app, base)
    assert dry.exit_code == 0, dry.output
    assert "DRY RUN" in dry.output and "nothing sent" in dry.output and client.submitted == []
    receipts = list(tmp_path.rglob("flatten-*.json"))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())["dry_run"] is True
    bad_mode = runner.invoke(app, [*base, "--mode", "limit"])
    assert bad_mode.exit_code != 0 and client.submitted == []
