"""Receipt-bound storage scope, invented local receipts only; no native activation."""

import json
import socket
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import current_initialization_storage as storage
from open_composer.intraday_runner.source_activity_reception import bind, save


@pytest.fixture
def case(tmp_path, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    root = tmp_path / "owned"
    root.mkdir()
    proposal = save(
        tmp_path / "proposal.json",
        dict(total_whole_route_peak_bytes=34603008, current_root_allocation=[{"root": str(root)}]),
    )
    receipt = save(
        tmp_path / "receipt.json",
        dict(
            admitted=True,
            capacity_only=True,
            task_id="BASE-H5-TWO-LEARNED-PAPER-VALIDATION-20261019",
            accepted_whole_route_peak_bytes=34603008,
            proposal=proposal,
        ),
    )
    job = dict(
        whole_route_bytes=34603008,
        protected_normal_bytes=10918819017,
        terminal_bytes=65536,
        capacity_receipt=receipt,
        owned_roots=[str(root)],
    )
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=12000000000, f_frsize=1)
    )
    return tmp_path, root, job


def test_changed_exact_admitted_peak_retains_fresh_growth_check(case):
    path, root, job = case
    first = storage.capacity(path, job)
    (root / "new-receipt").write_bytes(b"a" * 8192)
    second = storage.capacity(path, job)
    assert second["owned_allocated"] > first["owned_allocated"]
    assert second["remaining_current"] < first["remaining_current"]


@pytest.mark.parametrize("value", [True, 0, -1, 34603008.0, "34603008", 23068672])
def test_native_peak_cannot_override_exact_receipt(case, value):
    path, root, job = case
    job["whole_route_bytes"] = value
    with pytest.raises(ValueError):
        storage.capacity(path, job)


def test_proposal_peak_must_match_received_scope(case):
    path, root, job = case
    receipt = json.loads((path / "receipt.json").read_text())
    proposal = json.loads((path / "proposal.json").read_text())
    proposal["total_whole_route_peak_bytes"] = 23068672
    (path / "proposal.json").write_text(json.dumps(proposal))
    receipt["proposal"] = bind(path / "proposal.json")
    (path / "receipt.json").write_text(json.dumps(receipt))
    job["capacity_receipt"] = bind(path / "receipt.json")
    with pytest.raises(ValueError, match="proposal"):
        storage.capacity(path, job)


def test_physical_floor_is_not_lent_by_larger_logical_peak(case, monkeypatch):
    path, root, job = case
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=10918819017 + 65536, f_frsize=1)
    )
    with pytest.raises(ValueError, match="protected"):
        storage.capacity(path, job)


def test_original22_receipt_still_supported_exactly(case):
    path, root, job = case
    job["whole_route_bytes"] = 23068672
    proposal = json.loads((path / "proposal.json").read_text())
    proposal["total_whole_route_peak_bytes"] = 23068672
    (path / "proposal.json").write_text(json.dumps(proposal))
    receipt = json.loads((path / "receipt.json").read_text())
    receipt["accepted_whole_route_peak_bytes"] = 23068672
    receipt["proposal"] = bind(path / "proposal.json")
    (path / "receipt.json").write_text(json.dumps(receipt))
    job["capacity_receipt"] = bind(path / "receipt.json")
    assert storage.capacity(path, job)["remaining_current"] == 23068672 - storage.allocated_bytes(
        job["owned_roots"]
    )


def actual_replacement_schema(path, job, remaining=12288):
    receipt = json.loads((path / "receipt.json").read_text())
    proposal = receipt.pop("proposal")
    receipt["request_bindings"] = {"actual_remaining_two_session_proposal": proposal}
    receipt["concurrent_protected_commitments"] = {
        "single_synthesis": {"current_finite_remaining_future_peak_bytes": remaining}
    }
    (path / "receipt.json").write_text(json.dumps(receipt))
    job["capacity_receipt"] = bind(path / "receipt.json")


def test_actual_replacement_schema_preserves_other_finite_obligation(case, monkeypatch):
    path, root, job = case
    actual_replacement_schema(path, job)
    observed = storage.capacity(path, job)
    threshold = (
        job["protected_normal_bytes"]
        + job["terminal_bytes"]
        + observed["remaining_current"]
        + 12288
    )
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=threshold - 1, f_frsize=1)
    )
    with pytest.raises(ValueError, match="protected"):
        storage.capacity(path, job)
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=threshold, f_frsize=1)
    )
    assert storage.capacity(path, job)["free_bytes"] == threshold


@pytest.mark.parametrize("remaining", [None, False, -1, "12288", 12288.0])
def test_replacement_unknown_other_obligation_refuses(case, remaining):
    path, root, job = case
    actual_replacement_schema(path, job, remaining)
    with pytest.raises(ValueError, match="other admitted"):
        storage.capacity(path, job)


def test_three_trial_receipt_uses_its_real_task_key_and_all_roots(case):
    path, root, job = case
    roots = [str(root)]
    for i in range(7):
        extra = path / ("owned-" + str(i))
        extra.mkdir()
        roots.append(str(extra))
    proposal = json.loads((path / "proposal.json").read_text())
    proposal["total_whole_route_peak_bytes"] = 46137344
    proposal["current_root_allocation"] = [{"root": r} for r in roots]
    (path / "proposal.json").write_text(json.dumps(proposal))
    receipt = json.loads((path / "receipt.json").read_text())
    receipt.pop("proposal")
    receipt.update(
        task_id="BASE-H5-LSTM-THREE-LEARNED-PAPER-VALIDATION-20261019",
        accepted_whole_route_peak_bytes=46137344,
        request_bindings={"actual_conditional_three_trial_proposal": bind(path / "proposal.json")},
        concurrent_protected_commitments={
            "single_synthesis": {"current_finite_remaining_future_peak_bytes": 12288}
        },
    )
    (path / "receipt.json").write_text(json.dumps(receipt))
    job.update(
        whole_route_bytes=46137344, capacity_receipt=bind(path / "receipt.json"), owned_roots=roots
    )
    assert storage.capacity(path, job)["remaining_current"] > 0
    job["owned_roots"] = roots[:-1]
    with pytest.raises(ValueError, match="roots"):
        storage.capacity(path, job)
    job["owned_roots"] = roots
    receipt["proposal"] = receipt["request_bindings"].pop("actual_conditional_three_trial_proposal")
    (path / "receipt.json").write_text(json.dumps(receipt))
    job["capacity_receipt"] = bind(path / "receipt.json")
    with pytest.raises(KeyError):
        storage.capacity(path, job)


def test_six_trial_receipt_uses_all_thirteen_roots_and_no_legacy_branch(case):
    path, root, job = case
    roots = [str(root)]
    for i in range(12):
        extra = path / ("owned-" + str(i))
        extra.mkdir()
        roots.append(str(extra))
    proposal = json.loads((path / "proposal.json").read_text())
    proposal["total_whole_route_peak_bytes"] = 90177536
    proposal["current_root_allocation"] = [{"root": r} for r in roots]
    (path / "proposal.json").write_text(json.dumps(proposal))
    receipt = json.loads((path / "receipt.json").read_text())
    receipt.pop("proposal")
    receipt.update(
        task_id="SIX-CANDIDATE-PAPER-VALIDATION-20261019",
        accepted_whole_route_peak_bytes=90177536,
        request_bindings={
            "actual_six_candidate_whole_route_proposal": bind(path / "proposal.json")
        },
        concurrent_protected_commitments={
            "single_synthesis": {"current_finite_remaining_future_peak_bytes": 12288}
        },
    )
    (path / "receipt.json").write_text(json.dumps(receipt))
    job.update(
        whole_route_bytes=90177536, capacity_receipt=bind(path / "receipt.json"), owned_roots=roots
    )
    assert storage.capacity(path, job)["remaining_current"] > 0
    job["owned_roots"] = roots[:-1]
    with pytest.raises(ValueError, match="roots"):
        storage.capacity(path, job)
    job["owned_roots"] = roots
    receipt["proposal"] = receipt["request_bindings"].pop(
        "actual_six_candidate_whole_route_proposal"
    )
    (path / "receipt.json").write_text(json.dumps(receipt))
    job["capacity_receipt"] = bind(path / "receipt.json")
    with pytest.raises(KeyError):
        storage.capacity(path, job)
