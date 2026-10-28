"""Finite native entry for one accepted current initialization job.

No cron registration, observer, credential provisioning or permissive default.
All immutable job/authority/native/code bytes precede client construction.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    aware,
    require_phase,
)
from open_composer.intraday_runner.current_initialization_runtime import (
    CurrentInitializationRuntime,
    load_authority,
)
from open_composer.intraday_runner.current_initialization_storage import (
    NativeStorage,
    capacity,
    fixed_record,
    require_prepared,
)
from open_composer.intraday_runner.source_dispatch_journal import (
    _ensure_durable_directory,
    _sync_directory,
)
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_scientific_entry import kernel_evidence
from open_composer.intraday_runner.validation_account_partition import BASE, SLOTS, slot

PHASES = {
    "decision",
    "opening",
    "risk",
    "buy",
    "cancel",
    "reconcile",
    "settle",
    "exit",
    "abandon",
    "receipt_recovery",
}
GROUPED_PHASES = {"session", "initialization", "continuation"}


def receive_recovery_scope(root, job, basis):
    """A new finite GET-only maintenance purpose; old phase clocks stay exact."""
    binding = basis.get("postclose_recovery_scope")
    expected_path = root / (
        "reports/research/program/owner-profit-delivery-plan-20261017/"
        "paper-delivery/preopen-20261020/main-postclose-owned-receipt-recovery-scope.json"
    )
    if binding != dict(
        path=str(expected_path),
        bytes=6924,
        sha256="dac99e9dc62ba78f91883907c648fd02f54974678814bc0981f1925b255435e6",
    ):
        raise ValueError("exact prospective maintenance scope absent")
    scope = json.loads(bound_bytes(root, binding))["scope"]
    start = aware(scope["not_before_utc"])
    end = aware(scope["latest_new_recovery_entry_utc"])
    if not (
        job["phase"] == "receipt_recovery"
        and basis.get("broker_writes_allowed") is False
        and basis.get("new_initialization_or_buy") is False
        and start <= aware(job["not_before"]) < aware(job["expires_at"]) <= end
    ):
        raise ValueError("invalid finite GET-only recovery interval or purpose")


def receive_extension(root, job):
    if job.get("phase") not in {"settle", "cancel", "reconcile", "receipt_recovery"} or any(
        k in job
        for k in ("maintenance_plan", "episode_continuation_plan", "code_continuation_plan")
    ):
        raise ValueError("receipt-only extension cannot fund, decide or submit")
    basis = json.loads(bound_bytes(root, job["continuation_basis"]))
    if (
        basis.get("task_id") != job["task_id"]
        or basis.get("authority") != job["authority"]
        or basis.get("new_capital_flow_USD") != 0
        or basis.get("broker_writes_allowed")
        != ("owned_cancel_only" if job["phase"] == "cancel" else False)
    ):
        raise ValueError("invalid receipt-only actual-state basis")
    for b in basis["initialization_or_attempt_receipts"]:
        bound_bytes(root, b)
    if job["phase"] in {"cancel", "reconcile", "receipt_recovery"}:
        predecessors = basis.get("account_predecessor_receipts")
        if not isinstance(predecessors, list) or not predecessors:
            raise ValueError("actual account predecessor phase evidence absent")
        for receipt in predecessors:
            bound_bytes(root, receipt)
    if basis.get("single_phase_no_timer") is not True:
        raise ValueError("no additional shared-account continuation timer")
    if job["phase"] == "receipt_recovery":
        receive_recovery_scope(root, job, basis)
    elif "postclose_recovery_scope" in basis:
        raise ValueError("maintenance scope cannot extend an old phase")
    extension = basis["receipt_only_extension"]
    manifest = json.loads(bound_bytes(root, extension["manifest"]))
    review = json.loads(bound_bytes(root, extension["review"]))
    if (
        review.get("reviewer") != "66ad4b54-ec62-400b-9a03-a29682cf58e6"
        or review.get("independent") is not True
        or review.get("verdict") != "approve_implementation"
        or review.get("accepted_receipt_only_reconciliation") is not True
        or review.get("accepted_single_phase_owned_tracking") is not True
        or (
            job["phase"] == "receipt_recovery"
            and review.get("accepted_postclose_GET_only_recovery") is not True
        )
        or (job["phase"] == "cancel" and review.get("accepted_owned_order_tracking") is not True)
        or review.get("target") != extension["manifest"]
    ):
        raise ValueError("actual receipt-only acceptance absent")
    if "lot_quantity_correction" in basis:
        plan = json.loads(bound_bytes(root, basis["lot_quantity_correction"]))
        if (
            job["phase"] != "receipt_recovery"
            or review.get("accepted_exact_saved_lot_correction") is not True
            or plan.get("task_id") != job["task_id"]
            or plan.get("authority") != job["authority"]
            or plan.get("capital_flow_USD") != 0
            or plan.get("reservation_release") is not False
        ):
            raise ValueError("exact owned saved-lot correction acceptance absent")
    installed = json.loads(bound_bytes(root, extension["integration"]))
    if (
        installed.get("status") != "integrated_verified_inert"
        or installed.get("accepted_review") != extension["review"]
        or installed.get("installed_code_bindings") != manifest["extension_code_bindings"]
    ):
        raise ValueError("exact add-only Main integration absent")
    expected = {
        str(root / ("open_composer/intraday_runner/" + name))
        for name in (
            "current_receipt_only_runtime.py",
            "current_receipt_only_entry.py",
            "current_receipt_only_launcher.py",
        )
    }
    if {b["path"] for b in manifest["extension_code_bindings"]} != expected:
        raise ValueError("extension inventory drift")
    for b in manifest["extension_code_bindings"]:
        bound_bytes(root, b)
    return basis


def gate(root, job_binding, *, now, kernel=True, preparation_only=False):
    if type(preparation_only) is not bool or type(kernel) is not bool:
        raise ValueError("unknown native guard mode")
    if preparation_only and not kernel:
        raise ValueError("preparation still requires current kernel admission")
    if (
        Path(__file__).resolve()
        != (root / "open_composer/intraday_runner/current_receipt_only_entry.py").resolve()
    ):
        raise ValueError("executing entry is outside the admitted installed root")
    job = json.loads(bound_bytes(root, job_binding))
    receive_extension(root, job)
    native = json.loads(bound_bytes(root, job["native_acceptance"]))
    if (
        job.get("task_id") not in SLOTS
        or job.get("active") is not True
        or job.get("phase") not in PHASES | GROUPED_PHASES
    ):
        raise ValueError("unknown/inactive job")
    expected = {
        k: job[k]
        for k in (
            "task_id",
            "invocation_id",
            "whole_route_bytes",
            "protected_normal_bytes",
            "terminal_bytes",
            "authority",
            "phase",
            "output",
            "code_bindings",
            "not_before",
            "expires_at",
            "capacity_receipt",
            "owned_roots",
        )
    }
    if "monitoring_projection" in job and type(job["monitoring_projection"]) is not bool:
        raise ValueError("unknown monitoring projection mode")
    for key in (
        "maintenance_plan",
        "monitoring_projection",
        "concurrent_SIP_capacity",
        "concurrent_CASH_capacity",
        "current_normal_forecast",
        "episode_continuation_plan",
        "capture_partial_slot",
        "integration_receipt",
        "continuation_basis",
        "code_continuation_plan",
    ):
        if key in job:
            expected[key] = job[key]
    if (
        native.get("accepted") is not True
        or native.get("scope") != "CURRENT_VALIDATION_NATIVE_V1"
        or native.get("job_scope") != expected
    ):
        raise ValueError("exact actual native reception absent")
    if not aware(job["not_before"]) <= aware(now) < aware(job["expires_at"]):
        raise ValueError("native job expired/inactive")
    auth = load_authority(root, job["authority"], now)
    if auth.get("session_id") == "SIX-CURRENT-SESSION-20261020":
        integrated = json.loads(bound_bytes(root, job["integration_receipt"]))
        installed = json.loads(bound_bytes(root, integrated["installed_closure"]))
        if (
            integrated.get("status") != "integrated_verified_inert"
            or integrated.get("task_id") != BASE
            or integrated.get("accepted_review") != auth["operating_acceptance"]
            or installed.get("installed_code_bindings") != job["code_bindings"]
        ):
            raise ValueError("actual Main current-session integration absent")
        if job.get("capture_partial_slot") is not True:
            raise ValueError("prospective capture requires actual retained-partial slot")
        if "maintenance_plan" in job:
            raise ValueError("prospective gen1 scope cannot replay funding")
        if auth["task_id"] == BASE and job["phase"] in {"decision", "session", "initialization"}:
            plan = json.loads(bound_bytes(root, job["episode_continuation_plan"]))
            if plan.get("new_authority") != job["authority"] or plan.get("capital_flow_USD") != 0:
                raise ValueError("missing exact zero-flow funded predecessor continuation")
    if "code_continuation_plan" in job:
        plan = json.loads(bound_bytes(root, job["code_continuation_plan"]))
        if (
            job["task_id"] != BASE
            or job["phase"] != "settle"
            or "episode_continuation_plan" in job
            or "maintenance_plan" in job
            or plan.get("new_authority") != job["authority"]
            or plan.get("capital_flow_USD") != 0
            or plan.get("checkpoint_mutation") is not False
        ):
            raise ValueError("code continuation grants GET-only GEN6 settlement")
    if job["phase"] in {"initialization", "continuation"}:
        if auth.get("session_id") != "SIX-CURRENT-SESSION-20261020":
            raise ValueError("split finite session requires exact later authority")
        if job["phase"] == "continuation":
            if "episode_continuation_plan" in job or "maintenance_plan" in job:
                raise ValueError("continuing operation cannot initialize or fund again")
            basis = json.loads(bound_bytes(root, job["continuation_basis"]))
            if (
                basis.get("task_id") != job["task_id"]
                or basis.get("authority") != job["authority"]
                or basis.get("initialization_or_attempt_receipts") is None
                or not basis["initialization_or_attempt_receipts"]
                or basis.get("new_capital_flow_USD") != 0
            ):
                raise ValueError("actual prior operating facts required")
            for row in basis["initialization_or_attempt_receipts"]:
                bound_bytes(root, row)
    expected_capacity = (
        (402653184, "46ae769194f5131e5f299031e4077cbd9e26210c48c2d381c7aa775ec61efe01")
        if auth.get("session_id") == "SIX-CURRENT-SESSION-20261020"
        else (94044160, "cc8d60c8f3b39fabcfd1c6987baa025d7810a6df345222dbf9c8325243fbbede")
    )
    if (
        (job["whole_route_bytes"], job["capacity_receipt"].get("sha256")) != expected_capacity
        or "concurrent_SIP_capacity" not in job
        or "concurrent_CASH_capacity" not in job
        or "current_normal_forecast" not in job
    ):
        raise ValueError("Oct20 native requires actual current concurrent capacity")
    if "maintenance_plan" in job:
        plan = json.loads(bound_bytes(root, job["maintenance_plan"]))
        if plan.get("new_authority") != job["authority"] or job["phase"] not in {
            "decision",
            "session",
        }:
            raise ValueError("native funding plan/authority mismatch")
    if job["task_id"] != auth["task_id"] or job["code_bindings"] != auth["code_bindings"]:
        raise ValueError("native/code authority mismatch")
    required = {
        p.resolve()
        for pattern in ("current_initialization_*.py", "source_*.py")
        for p in (root / "open_composer/intraday_runner").glob(pattern)
    }
    required.update(
        (root / p).resolve()
        for p in (
            "open_composer/intraday_runner/current_h5_component.py",
            "open_composer/intraday_runner/current_lstm_component.py",
            "open_composer/intraday_runner/current_state_component.py",
            "open_composer/intraday_runner/validation_account_partition.py",
            "scripts/run_base_current_initialization.sh",
            "scripts/rebind_current_validation_code.py",
            "scripts/run_capped.sh",
            "scripts/memory_budget.py",
            "open_composer/book_paper/accounts.py",
            "open_composer/adapters/broker/alpaca_exchange_compat.py",
            "open_composer/book_paper/cost_ledgers.py",
            "open_composer/adapters/broker/alpaca_paper.py",
            "open_composer/paper_lock.py",
            "open_composer/paper_controls.py",
            "open_composer/market_sessions.py",
            "open_composer/models/strategy_spec.py",
            "reports/ops/paper-stale-target-20261015/normal-reconcile-refresh-observation-20261016/delivery-status.py",
        )
    )
    if auth.get("session_id") == "SIX-CURRENT-SESSION-20261020":
        required.add(
            (root / "open_composer/intraday_runner/current_session_instruction.py").resolve()
        )
        if "segregated_child_adapter" in auth:
            required.add(Path(auth["segregated_child_adapter"]["path"]).resolve())
    bound = {(root / b["path"]).resolve() for b in job["code_bindings"]}
    if not required <= bound:
        raise ValueError("runtime code closure incomplete")
    output = Path(job["output"])
    if (
        not output.is_absolute()
        or output != output.resolve()
        or output.parent != Path(auth["ledger_root"]) / "invocations"
    ):
        raise ValueError("wrong fixed native output")
    if (
        output.name != job["invocation_id"]
        or not output.name.replace("-", "").replace("_", "").isalnum()
    ):
        raise ValueError("native invocation/output identity mismatch")
    result = {} if preparation_only else dict(capacity=capacity(root, job))
    if kernel:
        result["kernel"] = kernel_evidence()
    final_now = datetime.now(UTC)
    if not (
        aware(job["not_before"]) <= final_now < aware(job["expires_at"])
        and aware(auth["authorized_at"]) <= final_now < aware(auth["expires_at"])
    ):
        raise ValueError("native or authority expiry reached during admission work")
    return job, auth, result


def consume(root, job_binding):
    # Resolve identity before admission; a failed admission is still one consumed
    # invocation. Different outputs cannot bypass the native immutable identity.
    job = json.loads(bound_bytes(root, job_binding))
    auth = json.loads(bound_bytes(root, job["authority"]))
    base = Path(auth["ledger_root"])
    if (
        auth.get("account_hash") != ACCOUNT
        or base != base.resolve()
        or not base.is_absolute()
        or auth.get("task_id") != job.get("task_id")
        or base != slot(root, job["task_id"])[0]
    ):
        raise ValueError("invalid consumption root")
    ident = job["invocation_id"]
    if not ident.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid invocation identity")
    directory = base / "consumed"
    NativeStorage(root, job).check(16384, path=directory / (ident + ".json"))
    _ensure_durable_directory(directory)
    with (directory / (ident + ".json")).open("x") as stream:
        json.dump(dict(job=job_binding, consumed_at=datetime.now(UTC).isoformat()), stream)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(directory)


def phase_plan(job, authority):
    """Finite native groups; initialization completion delivers before long waits."""
    mode = job["phase"]
    if mode not in GROUPED_PHASES:
        return [(mode, None)]
    later = authority.get("session_id") == "SIX-CURRENT-SESSION-20261020"
    if not later:
        if mode != "session":
            raise ValueError("old scope cannot use new finite group")
        return [
            ("decision", None),
            ("opening", "2026-10-20T13:30:00Z"),
            ("buy", "2026-10-20T13:40:00Z"),
            ("cancel", "2026-10-20T14:00:00Z"),
            ("reconcile", "2026-10-20T20:05:00Z"),
        ]
    initial = [("decision", None), ("opening", None), ("buy", None), ("settle", None)]
    tail = [("cancel", "2026-10-20T19:50:00Z"), ("reconcile", "2026-10-20T20:05:00Z")]
    if mode == "initialization":
        return initial
    if mode == "continuation":
        # Fresh exact native acceptance binds actual prior decision/attempt,
        # checkpoint and unknown liabilities. No initialization or new entry.
        return [("risk", None), *tail]
    return [*initial, *tail]


def run_phase(runtime, phase, directory, job):
    runtime.native_normal_forecast = job.get("current_normal_forecast")
    runtime.entry_guard(extra_write_bytes=16384, local_only=True)
    directory.mkdir(exist_ok=False)
    runtime.current_phase = phase
    runtime.trace_directory = directory / "transport"
    if phase == "receipt_recovery":
        basis = receive_extension(runtime.root, job)
        runtime.lot_quantity_correction = basis.get("lot_quantity_correction")
        now = aware(runtime.clock())
        if not (
            aware(job["not_before"]) <= now < aware(job["expires_at"])
            and aware(runtime.auth["authorized_at"]) <= now < aware(runtime.auth["expires_at"])
        ):
            raise ValueError("postclose recovery or authority interval expired")
    elif phase != "abandon":
        require_phase(
            runtime.clock(),
            phase,
            runtime.auth["authorized_at"],
            runtime.auth["expires_at"],
            killed=runtime.store.load()["snapshot"]["evidence"]["risk"]["killed"]
            if phase == "exit"
            else False,
            prospective=runtime.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )
    with runtime.operation():
        if "code_continuation_plan" in job:
            from open_composer.intraday_runner.current_session_instruction import (
                continue_existing_base_code,
            )

            continue_existing_base_code(runtime, job["code_continuation_plan"])
        if phase == "decision":
            if job.get("episode_continuation_plan") is not None:
                from open_composer.intraday_runner.current_session_instruction import (
                    continue_empty_base,
                )

                runtime.current_scientific_package = runtime.receive_science()
                continue_empty_base(runtime, job["episode_continuation_plan"])
            if job.get("maintenance_plan") is not None:
                from scripts.rebind_current_validation_code import execute

                runtime.maintenance_plan = job["maintenance_plan"]
                runtime.current_scientific_package = runtime.receive_science()
                execute(runtime.root, job["maintenance_plan"], runtime=runtime)
                # The first trace belongs to funding. A subsequent complete
                # decision capture uses a new immutable trace directory.
                if runtime.gateway is not None:
                    runtime.gateway.close()
                    runtime.gateway = None
                runtime.trace_directory = directory / "decision-transport"
                runtime.trace_directory_identity = None
            result = runtime.decide(directory)
        elif phase == "opening":
            runtime.observe(directory / "account", opening=True)
            result = dict(
                status="actual_initialization_NAV_recorded"
                if runtime.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020"
                else "actual_opening_NAV_recorded"
            )
        elif phase == "risk":
            # Receipt-only tracking does not certify NAV or initiate risk trades.
            result = runtime.reconcile(directory)
        elif phase == "buy":
            result = runtime.buy(directory)
        elif phase == "cancel":
            result = runtime.cancel(directory)
        elif phase == "exit":
            result = runtime.closeout(directory)
        elif phase == "abandon":
            result = runtime.abandon(job["abandon_cid"])
        else:
            result = runtime.reconcile(directory)
        result_binding = runtime.save_capture(directory / "result.json", result)
        if job.get("monitoring_projection") is True:
            from open_composer.intraday_runner.current_initialization_monitor import publish

            projection = (
                runtime.receipt_projection(directory, result_binding)
                if phase == "receipt_recovery"
                else result_binding
            )
            publish(runtime, phase, projection)
        return result_binding


def run(root, binding):
    root = Path(root)
    initial = json.loads(bound_bytes(root, binding))
    terminal = require_prepared(initial["output"], binding, initial["invocation_id"])
    storage = NativeStorage(root, initial)
    storage.check(16384, path=Path(initial["output"]) / "started.json")
    consume(root, binding)
    job, auth, admission = gate(root, binding, now=datetime.now(UTC))
    output = Path(job["output"])
    storage.mkdir(output.parent)
    storage.check(8192, path=output)
    output.mkdir(exist_ok=False)
    storage.save(
        output / "started.json",
        dict(job=binding, admission=admission, at=datetime.now(UTC).isoformat()),
    )

    def check(
        *,
        extra_write_bytes=0,
        write_path=None,
        write_method=None,
        phase=None,
        local_only=False,
        preparation_only=False,
        receive_authority=False,
    ):
        if type(receive_authority) is not bool or (
            receive_authority
            and (
                local_only is not False
                or write_method is not None
                or write_path is not None
                or phase is not None
                or extra_write_bytes != 0
            )
        ):
            raise ValueError("authority reception is a read-only check result")
        if type(preparation_only) is not bool or (
            preparation_only
            and (
                type(extra_write_bytes) is not int
                or extra_write_bytes != 0
                or write_path is not None
                or write_method is not None
                or phase is not None
                or local_only is not False
            )
        ):
            raise ValueError("preparation cannot grant a write or physical request")
        if local_only is True:
            if write_method is not None:
                raise ValueError("forensic sealing cannot grant a broker operation")
            current = json.loads(bound_bytes(root, binding))
            receive_extension(root, current)
            for b in current["code_bindings"]:
                bound_bytes(root, b)
            kernel_evidence()
            # One fresh full scan at the actual write boundary, including the
            # payload/atomic/ancestor budget. Previously this scanned twice.
            fresh = dict(
                capacity=NativeStorage(root, current).check(
                    extra_write_bytes, path=Path(write_path) if write_path is not None else None
                )
            )
        else:
            current, received_auth, fresh = gate(
                root, binding, now=datetime.now(UTC), preparation_only=preparation_only
            )
            if write_path is not None:
                fresh["capacity"] = NativeStorage(root, current).check(
                    extra_write_bytes, path=Path(write_path)
                )
        if (
            type(extra_write_bytes) is not int
            or extra_write_bytes < 0
            or (not preparation_only and extra_write_bytes > fresh["capacity"]["remaining_current"])
        ):
            raise ValueError("next atomic capture exceeds actual whole-route remaining peak")
        if current != job:
            raise ValueError("job changed")
        if receive_authority:
            return received_auth  # Only this freshly completed check, never a cached value.
        if write_method is not None:
            allowed = {"POST": {"buy", "exit"}, "DELETE": {"cancel", "exit"}}
            mode = job["phase"]
            grouped_write = (mode == "initialization" and phase == "buy") or (
                mode == "continuation" and phase == "cancel"
            )
            if phase not in allowed.get(write_method, set()) or (
                mode not in {phase, "session"} and not grouped_write
            ):
                raise ValueError("native job does not grant this broker write")

    check.receives_authority = True
    phases = phase_plan(job, auth)
    results, failures = [], []
    new_risk_blocked = False
    for phase, due in phases:
        if phase == "buy" and new_risk_blocked:
            failures.append(dict(phase=phase, error_type="earlier_phase_blocked_new_risk"))
            continue
        if due is not None:
            seconds = (aware(due) - datetime.now(UTC)).total_seconds()
            if seconds > 0:
                time.sleep(seconds)  # One fixed native wait; no polling.
        runtime = None
        try:
            check()
            runtime_type = CurrentInitializationRuntime
            if auth.get("session_id") == "SIX-CURRENT-SESSION-20261020":
                from open_composer.intraday_runner.current_session_instruction import runtime_class

                runtime_type = runtime_class(root, auth)
            from open_composer.intraday_runner.current_receipt_only_runtime import (
                ReceiptOnlyRuntime,
            )

            runtime_type = ReceiptOnlyRuntime
            runtime = runtime_type(
                root, job["authority"], entry_guard=check, capture_storage=storage
            )
            results.append(run_phase(runtime, phase, output / phase, job))
        except Exception as exc:
            failure = dict(
                phase=phase,
                error_type=type(exc).__name__,
                at=datetime.now(UTC).isoformat(),
                # Code locations only: never exception text, credentials, locals
                # or raw account/provider bodies in a failure summary.
                locations=[
                    dict(file=f.filename, line=f.lineno, function=f.name)
                    for f in traceback.extract_tb(exc.__traceback__)[-8:]
                ],
            )
            try:
                failure_binding = storage.save(output / (phase + "-failure.json"), failure)
                if runtime is not None and job.get("monitoring_projection") is True:
                    from open_composer.intraday_runner.current_initialization_monitor import publish

                    publish(runtime, phase, failure_binding, failed=True)
            except Exception as sealing_error:
                fixed_record(
                    terminal,
                    "entry-emergency.json",
                    dict(
                        status="failed_capacity_or_sealing",
                        failure=failure,
                        sealing_error_type=type(sealing_error).__name__,
                        consumed=True,
                        acknowledgment_or_execution_success_not_inferred=True,
                    ),
                )
                raise
            failures.append(failure)
            new_risk_blocked = True
            if phase == "decision" or job["phase"] not in GROUPED_PHASES:
                break
            # Fixed later cancel/reconciliation phases remain authorized; a
            # missing ACK is never turned into resubmit or reservation release.
    result = dict(
        status="incomplete_inspect_failures"
        if failures
        else "finite_phases_completed_inspect_receipts",
        results=results,
        failures=failures,
        at=datetime.now(UTC).isoformat(),
    )

    return storage.save(output / "completion.json", result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    result = run(args.root, dict(path=str(args.job), sha256=args.sha256))
    print(json.dumps(result))
    if json.loads(Path(result["path"]).read_text()).get("failures"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
