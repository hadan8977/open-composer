"""Reviewed BASE session02 continuation with an explicitly scoped allocation flow.

Run only after Main installs accepted bytes. Funding runs inside the existing
native decision and its GET-only capture; never via the standalone CLI. Original
checkpoint/native01/02 history is immutable. A held/consumed audit is not retried.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import subprocess
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import _atomic_write_text
from open_composer.intraday_runner.current_initialization_runtime import load_authority
from open_composer.intraday_runner.current_initialization_storage import NativeStorage
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.source_dispatch_journal import (
    _ensure_durable_directory,
    _hash,
    _sync_directory,
)
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_scientific_entry import kernel_evidence
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
from open_composer.intraday_runner.validation_account_partition import (
    ACCOUNT,
    BASE,
    LSTM,
    SLOTS,
    ValidationAccountPartition,
    receive_partition,
    slot,
)


def regular(path):
    path = Path(path)
    info = path.lstat()
    if path != path.resolve() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("exact exclusive regular file required")
    return path


def receive(root, binding):
    regular(root / binding["path"])
    return json.loads(bound_bytes(root, binding))


def unchanged_scope(
    old, new, *, allow_partition=False, allow_funding=False, allow_current_episode=False
):
    if type(allow_partition) is not bool or type(allow_funding) is not bool:
        raise ValueError("unknown partition continuation mode")
    allowed = {"code_bindings", "operating_acceptance"}
    if allow_partition:
        allowed.add("partition")
    if allow_funding:
        allowed.update({"capital_usd", "policy", "spec", "paper_validation", "scope_note"})
    added = set()
    if allow_current_episode:
        if not allow_funding or type(allow_current_episode) is not bool:
            raise ValueError("current episode only accompanies the exact funding continuation")
        added = {"current_day_selection", "application_day", "reference_day", "scientific_consumer"}
        allowed.update(added | {"scientific_acceptance", "authorized_at"})
    if set(new) != set(old) | added or any(old[k] != new[k] for k in old if k not in allowed):
        raise ValueError("code maintenance cannot change financial or lifecycle authority")
    if old["code_bindings"] == new["code_bindings"]:
        raise ValueError("not a code continuation")


def service_finished(invocation):
    if invocation not in {"base-current-session-20261019-01", "base-current-session-20261019-02"}:
        raise ValueError("not the exact failed predecessor")
    result = subprocess.run(
        ["systemctl", "show", invocation + ".service", "--property=MainPID,ActiveState"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
    if fields.get("MainPID") != "0" or fields.get("ActiveState") not in {"failed", "inactive"}:
        raise ValueError("predecessor process not terminal")
    return fields


def execute(root, plan_binding, *, runtime=None):
    root = Path(root)
    plan = receive(root, plan_binding)
    proof = receive(root, plan["precondition"])
    old = receive(root, proof["old_authority"])
    new = load_authority(root, plan["new_authority"], datetime.now(UTC))
    partition_change = old["partition"] != new["partition"]
    funding = old["capital_usd"] != new["capital_usd"]
    current_episode = "current_day_selection" in new
    unchanged_scope(
        old,
        new,
        allow_partition=partition_change,
        allow_funding=funding,
        allow_current_episode=current_episode,
    )
    if funding and (
        old["capital_usd"] != 10000
        or new["capital_usd"] != 20000
        or not partition_change
        or runtime is None
        or runtime.authority != plan["new_authority"]
        or not runtime._operation_held
        or not runtime.partition.held
        or runtime.current_phase != "decision"
        or runtime.maintenance_plan != plan_binding
    ):
        raise ValueError("funding only inside the exact native decision operation")
    if old["task_id"] != BASE or old["account_hash"] != ACCOUNT:
        raise ValueError("wrong predecessor sleeve")
    review = receive(root, new["operating_acceptance"])
    helper = review.get("maintenance_code", {})
    if (
        review.get("accepted_code_maintenance") is not True
        or review.get("maintenance_precondition") != plan["precondition"]
        or (root / helper.get("path", "")).resolve() != Path(__file__).resolve()
    ):
        raise ValueError("exact affected maintenance reception absent")
    bound_bytes(root, helper)
    if current_episode:
        from open_composer.intraday_runner.current_initialization_episode import receive_day

        receive_day(root, new)
        if (
            review.get("accepted_current_day_continuation") is not True
            or review.get("current_day_selection") != new["current_day_selection"]
            or runtime.current_scientific_package is None
        ):
            raise ValueError("current episode lacks exact affected reception")
    if partition_change:
        decision = receive_partition(root, new["partition"])
        if funding:
            from open_composer.intraday_runner.current_initialization_funding import MAIN_SHA

            if (
                new["partition"].get("sha256") != MAIN_SHA
                or review.get("maintenance_partition") != new["partition"]
                or review.get("accepted_funding_continuation") is not True
                or decision["actual_predecessor_readonly"]["old_pointer"] != proof["old_pointer"]
                or decision["actual_predecessor_readonly"]["head"] != proof["head"]
                or decision["actual_predecessor_readonly"]["revision"] != proof["revision"]
            ):
                raise ValueError("exact Main funding continuation absent")
        else:
            permission = decision.get("BASE_partition_continuation", {})
            if (
                review.get("maintenance_partition") != new["partition"]
                or decision.get("selected_task") != LSTM
                or decision.get("prior_partition") != old["partition"]
                or decision.get("account_binding") != old["main_scope"]
                or permission.get("explicitly_authorized_affected_extension") is not True
                or permission.get("allowed_BASE_authority_fields_to_change_only")
                != ["code_bindings", "operating_acceptance", "partition"]
                or permission.get("allowed_BASE_registry_fields_to_change_only")
                != ["authority", "partition"]
            ):
                raise ValueError("exact Main BASE partition continuation absent")
    # This exact Main receipt is recorded in the plan after integration; actual
    # installed bytes are independently enforced by load_authority above/below.
    integration = receive(root, plan["integration_receipt"])
    if (
        integration.get("status") != "integrated_verified_inert"
        or integration.get("task_id") != BASE
        or bound_bytes(root, integration["accepted_review"])
        != bound_bytes(root, new["operating_acceptance"])
        or receive(root, integration["installed_closure"]).get("installed_code_bindings")
        != new["code_bindings"]
    ):
        raise ValueError("exact Main repair integration not received")
    main = receive(root, proof["main_continuation"])
    if (
        main["continued_authority"].get(
            "new_invocation_successor_under_existing_scope_after_accepted_affected_repair_Main_exact_integration_and_fresh_native_gates"
        )
        is not True
    ):
        raise ValueError("prospective continuation authority absent")
    job = receive(root, proof["old_job"])
    if (
        job["authority"] != proof["old_authority"]
        or job["task_id"] != BASE
        or job["invocation_id"] != "base-current-session-20261019-02"
    ):
        raise ValueError("predecessor job differs")
    ledger, namespace = slot(root, BASE)
    registry = ledger.parent / ".account-envelope" / (BASE + ".json")
    expected_paths = {
        "old_pointer": registry,
        "head": ledger / "checkpoints/head.json",
        "revision": ledger / "checkpoints/revision-00000000.json",
        "native_consumed": ledger / "consumed" / (job["invocation_id"] + ".json"),
        "completion": Path(job["output"]) / "completion.json",
        "launcher_completion": Path(job["output"] + ".launcher") / "completion.json",
    }
    if any((root / proof[k]["path"]) != p for k, p in expected_paths.items()):
        raise ValueError("proof paths are not the existing predecessor state")
    history = proof["session01"]
    if set(history) != {
        "authority",
        "job",
        "native_consumed",
        "completion",
        "launcher_completion",
        "maintenance_completed",
    }:
        raise ValueError("complete session01 lineage required")
    prior = {key: receive(root, value) for key, value in history.items()}
    first_job = prior["job"]
    first_output = ledger / "invocations/base-current-session-20261019-01"
    if (
        first_job["invocation_id"] != first_output.name
        or first_job["task_id"] != BASE
        or first_job["authority"] != history["authority"]
        or first_job["output"] != str(first_output)
        or (root / history["native_consumed"]["path"])
        != ledger / "consumed" / (first_output.name + ".json")
        or (root / history["completion"]["path"]) != first_output / "completion.json"
        or (root / history["launcher_completion"]["path"])
        != Path(str(first_output) + ".launcher/completion.json")
        or prior["native_consumed"]["job"]["sha256"] != history["job"]["sha256"]
        or prior["completion"].get("results") != []
        or prior["launcher_completion"].get("native_exit") != 2
        or prior["launcher_completion"].get("exit_code") != 2
        or prior["maintenance_completed"].get("pointer") != proof["old_pointer"]
        or prior["maintenance_completed"].get("financial_state_changed") is not False
    ):
        raise ValueError("session01 or its consumed pointer maintenance changed")
    unchanged_scope(prior["authority"], old)
    # The predecessor job is immutable history. Its dated22MiB estimate must
    # not replace the separately accepted remaining-session capacity context.
    capacity_binding = review["maintenance_capacity_receipt"]
    capacity_receipt = receive(root, capacity_binding)
    storage_job = dict(
        job,
        capacity_receipt=capacity_binding,
        whole_route_bytes=capacity_receipt["accepted_whole_route_peak_bytes"],
    )
    if capacity_receipt.get("task_id") == "CURRENT-PAPER-CONTINUITY-AND-INITIALIZATION-20261020":
        proposal = receive(
            root, capacity_receipt["request_bindings"]["actual_f9_current_day_whole_route_proposal"]
        )
        storage_job["owned_roots"] = [r["root"] for r in proposal["current_root_allocation"]]
        storage_job["concurrent_SIP_capacity"] = review["maintenance_SIP_capacity_receipt"]
        storage_job["concurrent_CASH_capacity"] = review["maintenance_CASH_capacity_receipt"]
        storage_job["current_normal_forecast"] = plan["current_normal_forecast"]
        normal = receive(root, plan["current_normal_forecast"])
        storage_job["protected_normal_bytes"] = normal["required_available_bytes"]
        if runtime is None or runtime.native_normal_forecast != plan["current_normal_forecast"]:
            raise ValueError("funding normal forecast differs from exact native scope")
    elif capacity_receipt.get("task_id") == "SIX-CANDIDATE-PAPER-VALIDATION-20261019":
        proposal = receive(
            root, capacity_receipt["request_bindings"]["actual_six_candidate_whole_route_proposal"]
        )
        storage_job["owned_roots"] = [r["root"] for r in proposal["current_root_allocation"]]
    storage = NativeStorage(root, storage_job)
    kernel_evidence()
    storage.check()
    audit = Path(plan["audit_directory"])
    if (
        not audit.is_absolute()
        or audit != audit.resolve()
        or audit == root / plan_binding["path"]
        or audit.parent != (root / plan_binding["path"]).parent
    ):
        raise ValueError("audit must accompany the exact plan")

    funding_validity = None

    def guard(path, size, *, atomic=True):
        storage.check((2 if atomic else 1) * ((size + 4095) // 4096) * 4096 + 8192, path=path)
        # A storage scan cannot rebase an authenticated observation. This
        # callback never reads the checkpoint: it can run under its lock.
        if funding_validity is not None:
            funding_validity("after_storage_before_write:" + str(path))

    def acquire(stack, path, create=False):
        if create:
            guard(path, 0, atomic=False)
            _ensure_durable_directory(path.parent)
        else:
            regular(path)
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0), 0o600)
        stack.callback(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held, named = os.fstat(fd), regular(path).stat()
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("locked inode no longer names the required lock")
        if create:
            os.fsync(fd)
            _sync_directory(path.parent)

    with ExitStack() as stack:
        for path in (
            root / "reports/paper/.submission.lock",
            root / "reports/paper/.control.lock",
            registry.parent / "account.lock",
            ledger / ".operation.lock",
        ):
            if not funding:
                acquire(stack, path)
            else:
                regular(path)  # Held by the bound runtime.operation, not reacquired.

        def require_uninitialized_other_sleeves():
            if not partition_change:
                return
            for task in SLOTS:
                if task == BASE:
                    continue
                other, _ = slot(root, task)
                pointer_path = registry.parent / (task + ".json")
                if (
                    other.exists()
                    or other.is_symlink()
                    or pointer_path.exists()
                    or pointer_path.is_symlink()
                ):
                    raise ValueError(
                        "prospective sleeve now exists; never reset/adopt unknown state"
                    )

        require_uninitialized_other_sleeves()
        terminal = service_finished(job["invocation_id"])
        first_terminal = service_finished(first_job["invocation_id"])
        for value in history.values():
            bound_bytes(root, value)
        saved = {k: receive(root, proof[k]) for k in expected_paths}
        pointer = saved["old_pointer"]
        if pointer != dict(
            task=BASE,
            authority=proof["old_authority"],
            partition=old["partition"],
            ledger_root=str(ledger),
            namespace=namespace,
            allocation=10000,
        ):
            raise ValueError("old registry changed")
        marker = saved["native_consumed"]["job"]
        if any(marker[k] != proof["old_job"][k] for k in ("path", "sha256")):
            raise ValueError("old invocation not the consumed predecessor")
        if (
            saved["launcher_completion"].get("exit_code") != 2
            or saved["launcher_completion"].get("native_exit") != 2
            or saved["completion"].get("results") != []
        ):
            raise ValueError("not the bound unsuccessful predecessor")
        if (ledger / "initial-decision.json").exists() or (
            ledger / "initial-decision.json"
        ).is_symlink():
            raise ValueError("decision now exists")
        dispatch = ledger / "dispatch"
        lock = dispatch / ".dispatch.lock"

        def check_dispatch():
            if dispatch != dispatch.resolve() or dispatch.is_symlink():
                raise ValueError("dispatch alias")
            actual = dispatch.lstat()
            lock_stat = regular(lock).lstat()
            if (
                not stat.S_ISDIR(actual.st_mode)
                or sorted(p.name for p in dispatch.iterdir()) != [".dispatch.lock"]
                or proof["dispatch_identity"]
                != dict(
                    path=str(dispatch),
                    device=actual.st_dev,
                    inode=actual.st_ino,
                    lock_device=lock_stat.st_dev,
                    lock_inode=lock_stat.st_ino,
                )
            ):
                raise ValueError("existing empty dispatch/lock identity changed")
            if (root / proof["dispatch_lock"]["path"]) != lock:
                raise ValueError("wrong dispatch lock binding")
            bound_bytes(root, proof["dispatch_lock"])

        check_dispatch()
        acquire(stack, lock)
        check_dispatch()
        store = SourceStateCheckpoint(
            ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=BASE, write_guard=guard
        )
        current = store.load()
        if current != saved["revision"] or saved["head"] != dict(
            generation=0, sha256=_hash(current)
        ):
            raise ValueError("complete checkpoint changed")
        state = current["snapshot"]
        if (
            current["generation"] != 0
            or state["cashbook"]
            != dict(cash=10000, sales=[], purchases=[], dividends=[], lots={}, next_id=0)
            or any(
                state[k] for k in ("pending", "consumed_ids", "applied_fill_ids", "fills", "fees")
            )
            or state["evidence"].get("unresolved_actual_liabilities") is not False
        ):
            raise ValueError("not the exact empty initial financial state")
        if load_authority(root, plan["new_authority"], datetime.now(UTC)) != new:
            raise ValueError("successor changed during locks")
        guard(audit / "prepared.json", 65536)
        audit.mkdir()  # Exclusive maintenance consumption; even a failure stays.
        _sync_directory(audit.parent)
        old_bytes = bound_bytes(root, proof["old_pointer"])
        guard(audit / "old-pointer.json", len(old_bytes))
        _atomic_write_text(audit / "old-pointer.json", old_bytes.decode())
        prepared = dict(
            plan=plan_binding,
            predecessor=proof,
            service=terminal,
            session01_service=first_terminal,
            capacity_receipt=capacity_binding,
            old_pointer=pointer,
            new_authority=plan["new_authority"],
        )
        storage.save(audit / "prepared.json", prepared)
        if funding:
            # Read the exact old book with the current scoped GET-only gateway.
            # This temporary view cannot register, submit or mutate a financial book.
            from open_composer.intraday_runner.current_initialization_account import capture
            from open_composer.intraday_runner.current_initialization_funding import (
                funding_snapshot,
            )

            previous_partition = runtime.partition
            legacy = ValidationAccountPartition(
                root, old["partition"], write_guard=runtime.guard_write
            )
            legacy.held = True
            runtime.partition = legacy
            try:
                runtime.connect()
                raw = capture(
                    runtime, audit / "account", clock=runtime.clock, monotonic=runtime.monotonic
                )
            finally:
                runtime.partition = previous_partition
                legacy.held = False
            if raw["aggregate_positions"] or raw["aggregate_orders"] or raw["aggregate_activities"]:
                raise ValueError("funding cannot ignore actual account positions/orders/activities")
            observation = raw["observation"]
            capture_binding = bind(audit / "account/capture.json")

            def validate_funding(stage):
                try:
                    # Bound native/code/authority/secure identity checks first;
                    # clock/coverage checks follow their actual elapsed work.
                    runtime.read_guard(preparation_only=True)
                    bound_bytes(root, capture_binding)
                    from open_composer.intraday_runner.current_initialization_controls import (
                        require_phase,
                    )

                    require_phase(
                        runtime.clock(), "decision", new["authorized_at"], new["expires_at"]
                    )
                    funding_snapshot(
                        current,
                        observation,
                        now=runtime.clock(),
                        monotonic=runtime.monotonic(),
                        account_hash=ACCOUNT,
                        main=new["partition"],
                        capture_binding=capture_binding,
                    )
                except Exception as exc:
                    # Forensic-only publication bypasses this financial predicate,
                    # but retains the actual capacity guard. No recursive store read.
                    held = audit / "funding-hold.json"
                    if not held.exists():
                        storage.save(
                            held,
                            dict(
                                status="funding_publication_held",
                                at=runtime.clock().isoformat(),
                                stage=stage,
                                error_type=type(exc).__name__,
                                automatic_reapply=False,
                                checkpoint_or_registry_publication_may_exist=True,
                                predecessor=proof,
                                new_authority=plan["new_authority"],
                            ),
                        )
                    raise

            funding_validity = validate_funding
            funding_validity("captured_account_received")
            proposed = funding_snapshot(
                current,
                observation,
                now=runtime.clock(),
                monotonic=runtime.monotonic(),
                account_hash=ACCOUNT,
                main=new["partition"],
                capture_binding=capture_binding,
            )
            if current_episode:
                from open_composer.intraday_runner.current_initialization_episode import (
                    adopt_empty_funding_episode,
                )

                proposed = adopt_empty_funding_episode(
                    proposed, current, runtime.current_scientific_package, new
                )

            storage.save(
                audit / "funding-intent.json",
                dict(
                    predecessor_sha256=_hash(current),
                    successor_snapshot=proposed,
                    capture=capture_binding,
                    amount_USD=10000,
                    profit_USD=0,
                    new_authority=plan["new_authority"],
                    main=new["partition"],
                ),
            )
        updated = dict(
            pointer,
            authority=plan["new_authority"],
            partition=new["partition"],
            allocation=new["capital_usd"],
        )
        text = json.dumps(updated, sort_keys=True, indent=2, allow_nan=False) + "\n"
        guard(registry, len(text.encode()))
        # Final compare under every existing operation/dispatch lock.
        if registry.read_bytes() != old_bytes:
            raise ValueError("registry compare-and-swap failed")
        for key in expected_paths.keys() - {"old_pointer"}:
            bound_bytes(root, proof[key])
        for value in history.values():
            bound_bytes(root, value)
        check_dispatch()
        require_uninitialized_other_sleeves()
        if funding:
            funding_validity("before_checkpoint_commit")
            successor = store.commit(proposed, expected_head_sha256=_hash(current))
            funding_validity("after_checkpoint_publication")
            storage.save(
                audit / "funding-checkpoint.json",
                dict(
                    revision=bind(store._revision(successor["generation"])),
                    head=bind(store.directory / "head.json"),
                    amount_USD=10000,
                    profit_USD=0,
                ),
            )
        if funding:
            if registry.read_bytes() != old_bytes:
                raise ValueError("registry changed during funding checkpoint publication")
            funding_validity("after_checkpoint_receipt_before_registry_CAS")
        _atomic_write_text(registry, text)
        if funding:
            funding_validity("after_registry_publication")
        # Funding adds a revision; original revision/native/order evidence remains exact.
        for key in expected_paths.keys() - (
            {"old_pointer", "head"} if funding else {"old_pointer"}
        ):
            bound_bytes(root, proof[key])
        for value in history.values():
            bound_bytes(root, value)
        check_dispatch()
        require_uninitialized_other_sleeves()
        if funding:
            funding_validity("before_completion_receipt")
        completed_binding = storage.save(
            audit / "completed.json",
            dict(
                status="funding_successor_committed"
                if funding
                else "code_pointer_only_rebound_new_native_scope_still_required",
                at=datetime.now(UTC).isoformat(),
                plan=plan_binding,
                pointer=bind(registry),
                financial_state_changed=funding,
                capital_flow_USD=10000 if funding else 0,
                profit_from_flow_USD=0,
                broker_writes=0,
                broker_reads="bound_current_capture" if funding else 0,
            ),
        )
        if funding:
            funding_validity("after_completion_receipt")
        return completed_binding


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("sha256")
    args = parser.parse_args()
    execute(args.root, dict(path=str(args.plan), sha256=args.sha256))
