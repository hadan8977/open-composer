"""Saved-byte reception plus private transition/late-fact fixtures; no client."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import six_paper_service as service_module
from open_composer.intraday_runner import state_quantity_lock_transition as module
from open_composer.intraday_runner.six_paper_service import SixPaperService

NOW = datetime(2026, 10, 25, 18, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("No transport"))


def fixture():
    pending = dict(
        side="sell",
        symbol="AAPL",
        quantity=4,
        filled=0,
        limit_price=337.81,
        due="2026-10-22",
        fee_buffer_rate=0.001,
        remaining_funding=[],
        original_funding=[],
        confirmed_fee_funding=[],
    )
    current = dict(
        books={
            module.BOOK: dict(
                pending={module.CID: pending},
                evidence={"risk": {"HWM": "20k"}},
                cashbook={"lots": {"AAPL": [{"quantity": 11}]}},
                consumed_ids=[module.CID],
                fills={},
                fees={},
            ),
            "sibling": dict(
                pending={"fee-hold": {"remaining_funding": [{"amount": 0.5}]}},
                cashbook={"cash": 19999.5},
            ),
        },
        orders={
            module.CID: dict(
                book=module.BOOK,
                symbol="AAPL",
                side="sell",
                qty=4,
                status="prepared_unknown_until_queried",
                limit_price=337.81,
                last_query_failure={"matching_observations": 7},
            )
        },
        baseline={"saved": "unchanged"},
        cycles={},
        parent_risk={},
        account=dict(
            account_hash="private",
            cash="952703.75",
            observed_at=NOW.isoformat(),
            positions={"AAPL": dict(symbol="AAPL", qty="11", asset_class="us_equity")},
        ),
        open_orders=[],
        foreign_open_orders=[],
        position_mismatch={},
    )
    proof = dict(
        capture_result=dict(path="private", bytes=1, sha256=module.RESULT_SHA),
        quantity_interpretation=dict(path="private", bytes=1, sha256=module.BASIS_REVIEW_SHA),
    )
    return current, copy.deepcopy(current), proof


def test_actual_accepted_basis_immutable_reception_without_engine_or_transition():
    root = Path("/root/codex-test/open-composer")
    captured, result, review = module.basis(root)
    assert len(captured["books"]) == 16
    assert result["sha256"] == module.RESULT_SHA
    assert review["sha256"] == module.BASIS_REVIEW_SHA
    pending = captured["books"][module.BOOK]["pending"][module.CID]
    assert pending["side"] == "sell" and pending["quantity"] == 4


def test_only_two_quantity_fields_and_explicit_evidence_change_no_money_or_ID():
    current, captured, proof = fixture()
    original = copy.deepcopy(current)
    after = module.successor(current, captured, proof)
    assert current == original
    marker = after["orders"][module.CID].pop("current_quantity_lock_reconciliation")
    assert marker["original_pending"] == original["books"][module.BOOK]["pending"][module.CID]
    assert marker["original_order"] == original["orders"][module.CID]
    assert marker["monetary_release_USD"] == "0"
    after["books"][module.BOOK]["evidence"].pop("service_current_quantity_reconciliations")
    after["books"][module.BOOK]["pending"][module.CID].update(side="sell", quantity=4)
    assert after == original


@pytest.mark.parametrize(
    "change",
    ["sibling", "units", "cash", "status", "funding", "risk", "fee", "baseline"],
)
def test_changed_current_prefix_or_existing_monetary_liability_refuses(change):
    current, captured, proof = fixture()
    if change == "sibling":
        current["books"]["sibling"]["cashbook"]["cash"] -= 1
    elif change == "units":
        current["account"]["positions"]["AAPL"]["qty"] = "10"
    elif change == "cash":
        current["account"]["cash"] = "952703.74"
    elif change == "status":
        current["orders"][module.CID]["status"] = "filled"
    elif change == "funding":
        for value in (current, captured):
            value["books"][module.BOOK]["pending"][module.CID]["remaining_funding"] = [
                {"amount": 1}
            ]
    elif change == "risk":
        current["books"][module.BOOK]["evidence"]["risk"]["HWM"] = "changed"
    elif change == "fee":
        current["books"][module.BOOK]["fees"]["new"] = {"amount": 1}
    else:
        current["baseline"] = {}
    before = copy.deepcopy(current)
    with pytest.raises(ValueError):
        module.successor(current, captured, proof)
    assert current == before


def test_only_query_diagnostics_may_advance_and_remain_saved():
    current, captured, proof = fixture()
    current["orders"][module.CID]["last_query_failure"]["matching_observations"] += 1
    result = module.successor(current, captured, proof)
    assert result["orders"][module.CID]["last_query_failure"]["matching_observations"] == 8
    assert module.retired(module.CID, result["orders"][module.CID])
    assert not module.retired("some-other-ID", result["orders"][module.CID])
    assert not module.retired(
        module.CID,
        dict(current["orders"][module.CID], current_quantity_lock_reconciliation=True),
    )


def native(tmp_path, monkeypatch, fail=None):
    current, captured, proof = fixture()
    for rel, data in [
        (
            "reports/research/control/owner-compute-hold.json",
            dict(
                status="paper_allowed_research_paused",
                paper_launch_20min_20261021=dict(
                    necessary_current_paper_input_inference_and_repair_allowed=True
                ),
            ),
        ),
        (
            "reports/ops/disk-audit-20261015/handoff.json",
            dict(
                current_finite_scope_commitment_snapshot=dict(
                    current_complete_required_available_bytes=1
                )
            ),
        ),
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
    monkeypatch.setattr(
        module,
        "basis",
        lambda root: (
            captured,
            proof["capture_result"],
            proof["quantity_interpretation"],
        ),
    )
    monkeypatch.setattr(module, "implementation", lambda root: {"private": "received"})

    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as f:
            json.dump(value, f)
        return module.capture.bind(path)

    monkeypatch.setattr(module.capture, "save", save)
    writes = []
    runtime = SimpleNamespace(
        root=tmp_path,
        path=tmp_path / "native-state.json",
        state=current,
        clock=lambda: NOW,
        allowed=lambda: True,
        event=lambda *a, **kw: None,
        config=dict(current_STATE_quantity_lock_transition=module.TASK),
        call=lambda *a, **kw: pytest.fail("No broker calls"),
    )
    runtime.path.write_text(json.dumps(current))

    def publish():
        writes.append(copy.deepcopy(runtime.state))
        if fail == "before":
            raise OSError("private prepublication failure")
        runtime.path.write_text(json.dumps(runtime.state))
        if fail == "after":
            raise OSError("private postpublication failure")

    runtime.save = publish
    return runtime, writes


def test_native_commit_and_second_call_are_one_use(tmp_path, monkeypatch):
    runtime, writes = native(tmp_path, monkeypatch)
    before = copy.deepcopy(runtime.state)
    module.transition_once(runtime)
    assert len(writes) == 1 and module.retired(module.CID, runtime.state["orders"][module.CID])
    assert runtime.state["orders"][module.CID]["status"] == before["orders"][module.CID]["status"]
    after = copy.deepcopy(runtime.state)
    module.transition_once(runtime)
    assert len(writes) == 1 and runtime.state == after


@pytest.mark.parametrize("when", ["before", "after"])
def test_partial_publication_no_replay_and_memory_matches_published_checkpoint(
    tmp_path, monkeypatch, when
):
    runtime, writes = native(tmp_path, monkeypatch, fail=when)
    with pytest.raises(OSError):
        module.transition_once(runtime)
    assert runtime.state == json.loads(runtime.path.read_text())
    module.transition_once(runtime)
    assert len(writes) == 1
    assert (tmp_path / module.OUTPUT / "prepared-successor.json").exists()


@pytest.mark.parametrize("change", ["working", "fill", "wrong_quantity"])
def test_late_actual_conflict_is_retained_without_fill_or_hold_mutation(change):
    current, captured, proof = fixture()
    after = module.successor(current, captured, proof)
    original_books = copy.deepcopy(after["books"])
    observed = dict(
        client_order_id=module.CID,
        symbol="AAPL",
        side="sell",
        qty="4",
        status="expired",
        filled_qty="0",
    )
    observed.update(
        {"status": "new"}
        if change == "working"
        else {"filled_qty": "4"}
        if change == "fill"
        else {"qty": "5"}
    )
    runtime = SimpleNamespace(
        state=after,
        clock=lambda: NOW,
        save=lambda: None,
        call=lambda *a: observed,
        event=lambda *a, **kw: None,
    )
    SixPaperService.sync_orders(runtime)
    blocker = after["orders"][module.CID]["current_quantity_lock_conflict"]
    assert blocker["blocking"] is True
    assert json.loads(blocker["raw_observation_json"]) == observed
    assert after["orders"][module.CID]["status"] == "prepared_unknown_until_queried"
    assert after["books"] == original_books


def test_late_conflict_blocks_STATE_before_risk_or_order_mutation():
    current, captured, proof = fixture()
    after = module.successor(current, captured, proof)
    after["orders"][module.CID]["current_quantity_lock_conflict"] = {"status": "new"}
    runtime = SimpleNamespace(state=after, target_books=lambda *a: [(module.BOOK, {}, 20000, 0.25)])
    original = copy.deepcopy(after)
    with pytest.raises(ValueError, match="focused reconciliation"):
        SixPaperService.operate(runtime, module.BOOK, {}, {}, NOW, new_risk=True)
    assert after == original


def matching_late_order():
    return dict(
        id="provider-late",
        client_order_id=module.CID,
        symbol="AAPL",
        side="sell",
        qty="4",
        filled_qty="0",
        limit_price="337.81",
        type="limit",
        time_in_force="day",
        status="expired",
    )


def late_runtime(tmp_path, after, observed):
    path = tmp_path / "private-native.json"
    runtime = SimpleNamespace(
        state=after,
        root=tmp_path,
        clock=lambda: NOW,
        event=lambda *a, **kw: None,
        call=lambda *a: observed,
        target_books=lambda *a: [(module.BOOK, {}, 20000, 0.25)],
    )
    runtime.save = lambda: service_module.write_state(path, runtime.state)
    return runtime, path


@pytest.mark.parametrize(
    "change",
    [
        "limit",
        "type",
        "TIF",
        "filled_zero",
        "missing_id",
        "changed_id",
        "empty",
        "not_object",
        "nonfinite",
    ],
)
def test_full_late_conflicts_are_durable_typed_and_preserve_prior(tmp_path, monkeypatch, change):
    current, captured, proof = fixture()
    after = module.successor(current, captured, proof)
    observed = matching_late_order()
    if change == "limit":
        observed["limit_price"] = "337.82"
    elif change == "type":
        observed["type"] = "market"
    elif change == "TIF":
        observed["time_in_force"] = "gtc"
    elif change == "filled_zero":
        observed["status"] = "filled"
    elif change == "missing_id":
        observed.pop("id")
    elif change == "changed_id":
        after["orders"][module.CID]["observation"] = dict(observed, id="first-provider-id")
    elif change == "empty":
        observed = {}
    elif change == "not_object":
        observed = None
    else:
        observed["qty"] = float("nan")
    before = copy.deepcopy(after)
    runtime, path = late_runtime(tmp_path, after, observed)
    SixPaperService.sync_orders(runtime)
    saved = json.loads(path.read_text())
    blocker = saved["orders"][module.CID].pop("current_quantity_lock_conflict")
    assert blocker["blocking"] is True and blocker["kind"] == "retired_STATE_order_conflict_v1"
    assert blocker["raw_observation_json"] == json.dumps(observed, sort_keys=True, default=str)
    assert saved == before  # No prior observation/status/book mutation before classification.
    with pytest.raises(ValueError, match="focused reconciliation"):
        SixPaperService.operate(runtime, module.BOOK, {}, {}, NOW, new_risk=True)


def test_full_matching_zero_terminal_follows_unchanged_path_without_money_release(
    tmp_path, monkeypatch
):
    current, captured, proof = fixture()
    after = module.successor(current, captured, proof)
    original_books = copy.deepcopy(after["books"])
    observed = matching_late_order()
    runtime, path = late_runtime(tmp_path, after, observed)
    monkeypatch.setattr(
        service_module,
        "restore",
        lambda *a: (
            SimpleNamespace(pending=after["books"][module.BOOK]["pending"]),
            {},
            {},
            after["books"][module.BOOK]["evidence"],
        ),
    )
    monkeypatch.setattr(
        service_module,
        "snapshot",
        lambda *a, **kw: copy.deepcopy(original_books[module.BOOK]),
    )
    SixPaperService.sync_orders(runtime)
    saved = json.loads(path.read_text())
    assert saved["orders"][module.CID]["status"] == "expired"
    assert saved["orders"][module.CID]["observation"] == observed
    assert "current_quantity_lock_conflict" not in saved["orders"][module.CID]
    assert saved["books"] == original_books
