"""Invented own-sleeve local checkpoints; no account/source/network operations."""

import copy
import json
import os
import socket
from pathlib import Path

import pytest

from open_composer.intraday_runner import source_state_checkpoint as mod
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations

CID = "dia-base-2026-11-03-sell-AAPL"
ACCOUNT = "a" * 64


@pytest.fixture
def case(tmp_path, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("checkpoint tests must not call network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    root = os.environ.get("OC_SOURCE_REFERENCE_ROOT")
    if not root:
        pytest.skip("explicit accepted CashState source root required")
    root = Path(root)
    cash = source_module(root, "cash").CashState(
        cash=100,
        lots={"AAPL": [{"quantity": 10, "funded": "2026-10-19"}]},
        dividends=[dict(id="unreceived-right", amount=2.55, due="2026-11-04")],
    )
    state = SourceReservations(cash)
    state.reserve_sell(CID, "AAPL", 4, 10.0, "2026-11-03", "2026-11-04", fee_buffer_rate=0.01)
    store = mod.SourceStateCheckpoint(
        tmp_path / "owned" / "state", account_hash=ACCOUNT, sleeve_id="dia-base"
    )
    return root, state, store


def snap(state, fills=None, fees=None):
    return mod.snapshot(
        state, fills or {}, fees or {}, evidence={"fixture_only": True, "broker_complete": False}
    )


def test_roundtrip_preserves_pending_unknown_and_unreceived_right(case):
    root, state, store = case
    r = store.commit(snap(state), expected_head_sha256=None)
    got = store.load()
    restored, fills, fees, evidence = mod.restore(root, got["snapshot"])
    assert got == r and restored == state and fills == fees == {}
    assert restored.pending[CID]["filled"] == 0 and not restored.cashbook.sales
    assert restored.cashbook.dividends == state.cashbook.dividends
    assert evidence["broker_complete"] is False


def test_fill_and_fee_maps_are_typed_and_atomically_saved(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    state.confirmed_fill(CID, "fill-1", 2, 10.0, "2026-11-03")
    state.confirmed_fee(CID, "fee-1", 0.10)
    fills = {"fill-1": dict(client_order_id=CID, account_hash=ACCOUNT, raw="fixture-fill")}
    fees = {"fee-1": dict(client_order_id=CID, account_hash=ACCOUNT, raw="fixture-classified-fee")}
    saved = store.commit(snap(state, fills, fees), expected_head_sha256=mod._hash(first))
    assert saved == store.load()
    assert set(saved["snapshot"]["applied_fill_ids"]) == {"fill-1", "fee-1"}
    assert len(saved["snapshot"]["fills"]) == len(saved["snapshot"]["fees"]) == 1
    with pytest.raises(ValueError, match="typed receipt"):
        snap(state, fills)


@pytest.mark.parametrize(
    "change", ["remove_fill", "change_fill", "forget_consumed", "wrong_account", "fee_collision"]
)
def test_history_rewrites_and_half_checkpoint_refuse_before_publication(case, change):
    _, state, store = case
    state.confirmed_fill(CID, "fill-1", 2, 10.0, "2026-11-03")
    fills = {"fill-1": dict(client_order_id=CID, account_hash=ACCOUNT, raw="original")}
    first = store.commit(snap(state, fills), expected_head_sha256=None)
    value = copy.deepcopy(first["snapshot"])
    if change == "remove_fill":
        value["fills"] = {}
        value["applied_fill_ids"] = []
    elif change == "change_fill":
        value["fills"]["fill-1"]["raw"] = "changed"
    elif change == "forget_consumed":
        value["consumed_ids"] = []
        value["pending"] = {}
    elif change == "wrong_account":
        value["fills"]["fill-1"]["account_hash"] = "b" * 64
    else:
        value["fees"] = copy.deepcopy(value["fills"])
    with pytest.raises(ValueError):
        store.commit(value, expected_head_sha256=mod._hash(first))
    assert store.load() == first and not store._revision(1).exists()


def test_stale_writer_does_not_overwrite_newer_checkpoint(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    with pytest.raises(ValueError, match="stale"):
        store.commit(snap(state), expected_head_sha256=None)
    assert store.load() == first


def test_real_child_death_after_revision_keeps_pending_and_requires_exact_recovery(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    pid = os.fork()
    if pid == 0:
        store._publish = lambda revision: os._exit(7)
        store.commit(snap(state), expected_head_sha256=mod._hash(first))
        os._exit(99)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 7
    orphan = json.loads(store._revision(1).read_text())
    with pytest.raises(ValueError, match="unpublished"):
        store.load()
    with pytest.raises(ValueError, match="recovery revision hash"):
        store.recover(exact_revision_sha256="0" * 64)
    assert store.recover(exact_revision_sha256=mod._hash(orphan)) == orphan
    assert store.load() == orphan
    assert orphan["snapshot"]["pending"] == first["snapshot"]["pending"]
    assert store.recover(exact_revision_sha256=mod._hash(orphan)) == orphan


def test_publish_failure_retains_exact_revision_and_old_head(case, monkeypatch):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    before = (store.directory / "head.json").read_bytes()

    def fail(*a):
        raise OSError("injected head publication failure")

    monkeypatch.setattr(store, "_publish", fail)
    with pytest.raises(OSError):
        store.commit(snap(state), expected_head_sha256=mod._hash(first))
    assert (store.directory / "head.json").read_bytes() == before
    assert store._revision(1).exists()
    with pytest.raises(ValueError, match="unpublished"):
        store.load()


def test_torn_revision_preserved_no_auto_reconstruction(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    store._revision(1).write_text('{"schema":')
    with pytest.raises(ValueError):
        store.recover(exact_revision_sha256="0" * 64)
    assert store._revision(1).read_text() == '{"schema":'
    assert store._read(store.directory / "head.json")["sha256"] == mod._hash(first)


def test_prefix_corruption_missing_revision_and_foreign_identity_block(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    store.commit(snap(state), expected_head_sha256=mod._hash(first))
    other = mod.SourceStateCheckpoint(store.directory, account_hash="b" * 64, sleeve_id="dia-base")
    with pytest.raises(ValueError, match="identity|mismatch"):
        other.load()
    path = store._revision(0)
    raw = path.read_bytes()
    changed = json.loads(raw)
    changed["snapshot"]["cashbook"]["cash"] = 999
    path.write_text(mod._canonical(changed) + "\n")
    with pytest.raises(ValueError, match="predecessor"):
        store.load()
    path.unlink()
    with pytest.raises(FileNotFoundError):
        store.load()
    path.write_bytes(raw)
    assert store.load()["generation"] == 1


def test_directory_barrier_failure_and_symlink_alias_no_checkpoint(case, monkeypatch, tmp_path):
    _, state, store = case

    def fail(*a):
        raise OSError("injected directory barrier")

    monkeypatch.setattr(mod, "_ensure_durable_directory", fail)
    with pytest.raises(OSError):
        store.commit(snap(state), expected_head_sha256=None)
    assert not store.directory.exists()
    monkeypatch.undo()
    target = tmp_path / "actual"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    bad = mod.SourceStateCheckpoint(alias, account_hash=ACCOUNT, sleeve_id="dia-base")
    with pytest.raises(ValueError, match="nonsymlink"):
        bad.commit(snap(state), expected_head_sha256=None)
    assert not list(target.iterdir())


def test_nonfinite_snapshot_never_replaces_accepted_head(case):
    _, state, store = case
    first = store.commit(snap(state), expected_head_sha256=None)
    value = copy.deepcopy(first["snapshot"])
    value["cashbook"]["cash"] = float("nan")
    with pytest.raises(ValueError):
        store.commit(value, expected_head_sha256=mod._hash(first))
    assert store.load() == first
