from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import six_paper_service as service
from open_composer.intraday_runner import source_state_checkpoint

NOW = datetime(2026, 10, 21, 1, tzinfo=UTC)


@dataclass
class Cash:
    cash: float
    sales: list = field(default_factory=list)
    purchases: list = field(default_factory=list)
    dividends: list = field(default_factory=list)
    lots: dict = field(default_factory=dict)
    next_id: int = 0

    def quantity(self, symbol):
        return sum(lot["quantity"] for lot in self.lots.get(symbol, []))

    def free_cash(self):
        return self.cash - sum(p["amount"] for p in self.purchases)

    def nav_cash(self):
        return self.free_cash()


@pytest.fixture(autouse=True)
def cash(monkeypatch):
    module = SimpleNamespace(CashState=Cash)
    monkeypatch.setattr(service, "source_module", lambda *_: module)
    monkeypatch.setattr(source_state_checkpoint, "source_module", lambda *_: module)


def target(policy="BASE"):
    return dict(
        policy=policy,
        as_of="2026-10-21T00:00:00Z",
        valid_until="2026-10-22T00:00:00Z",
        portfolio_action="hold",
        symbols=["SPY"],
        weights=[0.2],
        reference_marks={"SPY": 600.0},
    )


def test_initialization_segregates_all_children_and_capital(tmp_path):
    state = service.initialize(tmp_path)
    assert len(state["books"]) == 16
    assert sum(b["cashbook"]["cash"] for b in state["books"].values()) == pytest.approx(120000)
    for parent in service.CHILD_CAPITAL:
        assert sum(
            state["books"][parent + "/" + c]["cashbook"]["cash"] for c in service.CHILDREN
        ) == pytest.approx(20000)


@pytest.mark.parametrize(
    "change",
    [
        dict(as_of="2026-10-22T00:00:00Z"),
        dict(valid_until="2026-10-20T00:00:00Z"),
        dict(weights=[0.3]),
        dict(symbols=["SPY", "SPY"], weights=[0.1, 0.1]),
        dict(weights=[float("nan")]),
    ],
)
def test_current_input_rejects_future_expired_or_wrong_caps(change):
    value = target()
    value.update(change)
    with pytest.raises(ValueError):
        service.validate_target(value, "BASE", NOW)


def test_migration_preserves_checkpoint_ids_holds_lots_and_file(tmp_path):
    from open_composer.intraday_runner.source_dispatch_journal import _hash

    task = service.POLICIES["BASE_STATE_BUDGET"]
    folder = (
        tmp_path
        / "reports/paper/intraday"
        / service.SLOTS[task][0]
        / service.ACCOUNT
        / "checkpoints"
    )
    folder.mkdir(parents=True)
    book = service.new_book(tmp_path, 20000)
    book["cashbook"]["lots"] = {
        "AAPL": [{"quantity": 11, "funded": "2026-10-20"}],
        "INTC": [{"quantity": 43, "funded": "2026-10-20"}],
    }
    book["consumed_ids"] = ["old-consumed"]
    book["pending"] = {
        "old-consumed": {
            "side": "liability_hold",
            "remaining_funding": [{"source": "cash", "amount": 10, "funded": "2026-10-20"}],
        }
    }
    revision = dict(generation=4, snapshot=book)
    import json

    original = json.dumps(revision).encode()
    (folder / "revision-00000004.json").write_bytes(original)
    (folder / "head.json").write_text(json.dumps(dict(generation=4, sha256=_hash(revision))))
    result = service.initialize(tmp_path)
    assert result["books"]["BASE_STATE_BUDGET"] == book
    assert (folder / "revision-00000004.json").read_bytes() == original


def test_one_bad_policy_does_not_block_five_others(tmp_path, monkeypatch):
    import json

    for policy in service.POLICIES:
        value = target(policy)
        if policy in service.CHILD_CAPITAL:
            value["children"] = {
                name: dict(symbols=["SPY"], weights=[0.2], reference_marks={"SPY": 600.0})
                for name in service.CHILDREN
            }
        (tmp_path / (policy + ".json")).write_text(json.dumps(value))
    (tmp_path / "BASE.json").write_text("bad json")
    runtime = service.SixPaperService(
        tmp_path,
        dict(targets_root=str(tmp_path)),
        tmp_path / "state.json",
        object(),
        clock=lambda: NOW,
    )
    monkeypatch.setattr(runtime, "allowed", lambda: True)
    monkeypatch.setattr(runtime, "sync_orders", lambda: None)
    monkeypatch.setattr(runtime, "preflight", lambda: ({}, {}))
    monkeypatch.setattr(runtime, "disposition", lambda: None)
    runtime.client = SimpleNamespace(get_clock=lambda: {"is_open": False})
    assert runtime.tick()
    assert runtime.state["policy_status"]["BASE"]["status"] == "blocked"
    assert (
        sum(r["status"] == "ready_waiting_rth" for r in runtime.state["policy_status"].values())
        == 5
    )
    assert not runtime.state["orders"]


def test_unknown_submit_id_is_never_retried(tmp_path):
    runtime = service.SixPaperService(tmp_path, {}, tmp_path / "state.json", object())
    import hashlib

    cid = "six-" + hashlib.sha256(b"BASE:SPY:buy:cycle").hexdigest()[:36]
    runtime.state["orders"][cid] = dict(status="prepared_unknown_until_queried")
    # An unqueryable client would fail if submit entered any broker path.
    runtime.submit("BASE", "SPY", "buy", 1, 100, "cycle")
    assert runtime.state["orders"][cid]["status"] == "prepared_unknown_until_queried"


def test_protective_cancel_has_no_signal_or_financial_reconciliation_dependency(tmp_path):
    calls = []
    client = SimpleNamespace(cancel_order_by_id=calls.append)
    runtime = service.SixPaperService(
        tmp_path, {}, tmp_path / "state.json", client, clock=lambda: NOW
    )
    runtime.state["orders"] = {"own": dict(status="new", observation={"id": "own-broker-id"})}
    runtime.cancel_due(NOW, NOW)
    runtime.cancel_due(NOW, NOW)
    assert calls == ["own-broker-id"]


def test_terminal_unused_principal_preserves_fee_hold_lots_and_consumed_id(tmp_path):
    from open_composer.intraday_runner.source_state_checkpoint import restore

    state, _, _, evidence = restore(tmp_path, service.new_book(tmp_path, 20000))
    state.reserve_buy("owned", "AAPL", 11, 342.94, 11 * 342.94 * 0.001, "2026-10-20", "2026-10-21")
    state.confirmed_fill("owned", "fill1", 11, 339.19, "2026-10-20")
    cash_before = state.cashbook
    request = dict(
        client_order_id="owned",
        symbol="AAPL",
        side="buy",
        type="limit",
        time_in_force="day",
        qty=11,
        limit_price=342.94,
    )
    order = dict(request, id="broker-id", filled_qty="11", status="filled")
    assert service.terminal_principal(state, evidence, "owned", order, request)
    assert state.pending["owned"]["side"] == "liability_hold"
    assert state.pending["owned"]["remaining_funding"][0]["amount"] >= 11 * 342.94 * 0.001
    assert state.pending["owned"]["remaining_funding"][0]["amount"] < 4
    assert "owned" in state.consumed_ids
    assert state.cashbook == cash_before
    assert state.cashbook.quantity("AAPL") == 11
    assert evidence["service_terminal_dispositions"]["owned"]["final_fees_certified"] is False


def test_nonterminal_does_not_release_principal(tmp_path):
    from open_composer.intraday_runner.source_state_checkpoint import restore

    state, _, _, evidence = restore(tmp_path, service.new_book(tmp_path, 20000))
    state.reserve_buy("owned", "SPY", 1, 600.0, 0.6, "2026-10-20", "2026-10-21")
    request = dict(
        client_order_id="owned",
        symbol="SPY",
        side="buy",
        type="limit",
        time_in_force="day",
        qty=1,
        limit_price=600.0,
    )
    order = dict(request, id="broker-id", filled_qty="0", status="pending_cancel")
    with pytest.raises(ValueError):
        service.terminal_principal(state, evidence, "owned", order, request)
    assert state.cash_reserved() == pytest.approx(600.6)


def test_actual_six_current_targets_are_accepted(tmp_path):
    import json
    from pathlib import Path

    folder = Path(
        "/root/codex-test/open-composer/reports/research/program/paper-launch-20min-20261021/targets"
    )
    if not folder.exists():
        pytest.skip("owner's actual launch input fixture unavailable")
    runtime = service.SixPaperService(
        tmp_path, {}, tmp_path / "state.json", object(), clock=lambda: NOW
    )
    for policy in service.POLICIES:
        value = json.loads((folder / (policy + ".json")).read_text())
        fixture_now = service.instant(value["valid_until"]) - timedelta(minutes=1)
        rows = runtime.target_books(policy, value, fixture_now)
        assert len(rows) == (6 if policy in service.CHILD_CAPITAL else 1)


def test_actual_durable_unreached_tail_releases_without_reusing_ids(tmp_path):
    import json
    from pathlib import Path

    root = Path("/root/codex-test/open-composer")
    if not (root / "reports/paper/intraday/lstm-crossasset-validation-20261019").exists():
        pytest.skip("original saved invocation evidence unavailable")
    runtime = service.SixPaperService(
        root,
        {},
        tmp_path / "state.json",
        SimpleNamespace(
            get_order_by_client_id=lambda cid: (_ for _ in ()).throw(ValueError("offline"))
        ),
    )
    before = json.loads(json.dumps(runtime.state["books"]))
    runtime.disposition()
    after = runtime.state["books"]["LSTM"]
    assert set(after["consumed_ids"]) == set(before["LSTM"]["consumed_ids"])
    assert len(after["evidence"].get("service_no_submit_dispositions", {})) >= 8
    assert len(after["pending"]) < len(before["LSTM"]["pending"])
    assert (
        runtime.state["books"]["BASE_STATE_BUDGET"]["cashbook"]["lots"]
        == before["BASE_STATE_BUDGET"]["cashbook"]["lots"]
    )
