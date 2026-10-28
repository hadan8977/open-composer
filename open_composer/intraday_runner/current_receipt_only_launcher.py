"""One finite launcher with admitted fixed logs and owned-child reap on refusal.

No new timer, polling service, credential loading or financial operation. The
worker and runtime share the existing capped scope; the launcher records actual
child resource usage, never treats its own exit as broker completion.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import selectors
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import ACCOUNT, aware
from open_composer.intraday_runner.current_initialization_storage import (
    FixedSlot,
    NativeStorage,
    fixed_record,
    require_prepared,
)
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.validation_account_partition import SLOTS, slot

MODULE = "open_composer.intraday_runner.current_receipt_only_launcher"


def process_identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    return dict(
        pid=pid,
        start=raw[raw.rfind(")") + 2 :].split()[19],
        cgroup=Path(f"/proc/{pid}/cgroup").read_text(),
        pgid=os.getpgid(pid),
    )


def stop_group(process):
    # Our unreaped Popen child cannot have its PID reused. Every entry child is
    # its own session leader. SIGKILL is intentional on evidence/log overflow.
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()  # Actual OS reap, even on sink/refusal exceptions.


def stop_recorded_worker(directory, binding):
    # run_capped creates a separate scope. Do not assume killing its wrapper
    # kills that scope: use only the immutable job and exact PID/start/cgroup.
    try:
        raw = (directory / "worker.json").read_bytes().rstrip(b"\0 ")
        value = json.loads(raw)
    except (ValueError, OSError):
        return
    if value.get("job") != binding:
        raise ValueError("worker identity binding differs")
    for key in ("entry", "worker"):
        identity = value.get(key)
        if identity is None:
            continue
        try:
            actual = process_identity(identity["pid"])
        except (FileNotFoundError, ProcessLookupError):
            continue
        if actual != identity:
            raise ValueError("worker PID/start/cgroup changed; no signal sent")
        if key == "entry":
            if actual["pgid"] != actual["pid"]:
                raise ValueError("entry is not its owned process-group leader")
            try:
                os.killpg(actual["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            try:
                os.kill(actual["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass


def bounded_process(command, directory, name, *, timeout_seconds, before_run=None, cleanup=None):
    sink = FixedSlot(directory, name)
    process = None
    selector = selectors.DefaultSelector()
    started = time.monotonic()
    prior = resource.getrusage(resource.RUSAGE_CHILDREN)
    rc, failure = None, None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if before_run else subprocess.DEVNULL,
            start_new_session=True,
        )
        if before_run is not None:
            before_run(process)
            process.stdin.write(b"go\n")
            process.stdin.flush()
            process.stdin.close()
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("finite native subprocess deadline")
            for key, _ in selector.select(min(remaining, 1.0)):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                else:
                    sink.append(data)
        remaining = timeout_seconds - (time.monotonic() - started)
        rc = process.wait(timeout=max(0, remaining))
    except BaseException as exc:
        failure = type(exc).__name__
        try:
            if cleanup is not None:
                cleanup()
        finally:
            if process is not None:
                stop_group(process)
        raise
    finally:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        fixed_record(
            directory,
            name + ".resource.json",
            dict(
                exit_code=process.returncode if process is not None else None,
                failure_type=failure,
                wall_seconds=time.monotonic() - started,
                child_user_seconds=after.ru_utime - prior.ru_utime,
                child_system_seconds=after.ru_stime - prior.ru_stime,
                cumulative_children_maxrss_KiB=after.ru_maxrss,
                reaped=process is not None and process.returncode is not None,
                log_bytes=sink.offset,
                other_overhead="UNKNOWN",
                overlap="Wrapper and inner child resource counters are not additive",
            ),
        )
        selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        sink.close()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(
        exit_code=rc,
        wall_seconds=time.monotonic() - started,
        child_user_seconds=after.ru_utime - prior.ru_utime,
        child_system_seconds=after.ru_stime - prior.ru_stime,
        cumulative_children_maxrss_KiB=after.ru_maxrss,
        log_bytes=sink.offset,
        reaped=True,
    )


def worker(root, binding):
    job = json.loads(bound_bytes(root, binding))
    directory = require_prepared(job["output"], binding, job["invocation_id"])
    identity = dict(job=binding, worker=process_identity(os.getpid()), entry=None)
    fixed_record(directory, "worker.json", identity)

    # Full kernel/code/authority checks remain in the real entry, before client.
    def publish(child):
        identity["entry"] = process_identity(child.pid)
        fixed_record(directory, "worker.json", identity)

    remaining = (aware(job["expires_at"]) - datetime.now(UTC)).total_seconds()
    if not 0 < remaining <= 64800:
        raise ValueError("expired native worker")
    command = [
        str(root / ".venv/bin/python"),
        "-m",
        MODULE,
        "--entry",
        "--root",
        str(root),
        "--job",
        binding["path"],
        "--sha256",
        binding["sha256"],
    ]
    result = bounded_process(
        command, directory, "run.log", timeout_seconds=remaining, before_run=publish
    )
    fixed_record(
        directory,
        "resource.json",
        dict(
            scope_child=result,
            worker_and_outer_overhead="UNKNOWN; do not add overlapping cgroup counters",
        ),
    )
    return result["exit_code"]


def enable_subreaper():
    # Scope-wrapper death must not strand an entry that was forked inside that
    # scope. Adoption applies only to descendants of this finite launcher.
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot establish owned-child reaper")


def reap_recorded_children(directory, binding):
    try:
        value = json.loads((directory / "worker.json").read_bytes().rstrip(b"\0 "))
    except (ValueError, OSError):
        return
    if value.get("job") != binding:
        raise ValueError("wrong reaping identity")
    for key in ("entry", "worker"):
        row = value.get(key)
        if row is None:
            continue
        try:
            # stop_recorded_worker already checked/sent SIGKILL; if another
            # parent reaped it, ECHILD is expected. Never wait on arbitrary PIDs.
            os.waitpid(row["pid"], 0)
        except ChildProcessError:
            pass


def launch(root, binding):
    job = json.loads(bound_bytes(root, binding))
    auth = json.loads(bound_bytes(root, job["authority"]))
    output = Path(job["output"])
    base = slot(root, job["task_id"])[0]
    if (
        job["task_id"] not in SLOTS
        or auth.get("task_id") != job["task_id"]
        or auth["account_hash"] != ACCOUNT
        or Path(auth["ledger_root"]) != base
        or output != output.resolve()
        or output.parent != base / "invocations"
        or output.name != job["invocation_id"]
        or not output.name.replace("-", "").replace("_", "").isalnum()
    ):
        raise ValueError("wrong exact native output/identity")
    remaining = (aware(job["expires_at"]) - datetime.now(UTC)).total_seconds()
    if not 0 < remaining <= 64800:
        raise ValueError("expired native launch")
    enable_subreaper()
    storage = NativeStorage(root, job)
    directory = storage.prepare(output, binding)
    # Preparation is already exclusive and durable. No admission failure retries.
    rc, error, native = 75, None, None
    try:
        admit = bounded_process(
            [
                "/usr/bin/python3",
                str(root / "scripts/memory_budget.py"),
                "admit",
                "--kind",
                "job",
                "--mem",
                "400",
            ],
            directory,
            "memory.log",
            timeout_seconds=min(60, remaining),
        )
        if admit["exit_code"] != 0:
            raise ValueError("actual memory admission refused")
        storage.check()
        remaining = (aware(job["expires_at"]) - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ValueError("native expired during memory/storage admission")
        command = [
            str(root / "scripts/run_capped.sh"),
            "--class",
            "paper",
            "--mem",
            "400M",
            "--swap",
            "0",
            "--wait-min",
            "0",
            "--",
            "taskset",
            "-c",
            "0",
            "timeout",
            "--signal=TERM",
            "--kill-after=5s",
            str(max(1, int(remaining))) + "s",
            str(root / ".venv/bin/python"),
            "-m",
            MODULE,
            "--worker",
            "--root",
            str(root),
            "--job",
            binding["path"],
            "--sha256",
            binding["sha256"],
        ]
        native = bounded_process(
            command,
            directory,
            "scope.log",
            timeout_seconds=remaining + 6,
            cleanup=lambda: stop_recorded_worker(directory, binding),
        )
        rc = native["exit_code"]
        # An abnormal scope exit still needs the exact remaining owned-child check.
        if rc:
            stop_recorded_worker(directory, binding)
    except BaseException as exc:
        error = type(exc).__name__
    cleanup_error = None
    if native is None or rc:
        try:
            stop_recorded_worker(directory, binding)
            reap_recorded_children(directory, binding)
        except Exception as exc:
            cleanup_error = type(exc).__name__
            rc = 75
    fixed_record(
        directory,
        "native-completion.json",
        dict(
            native_exit=rc,
            error_type=error,
            scope_wrapper=native,
            owned_cleanup_error=cleanup_error,
            success_not_inferred_from_exit=True,
            other_consumption="UNKNOWN",
        ),
    )
    delivery_rc, ack = 74, False
    try:
        delivery = bounded_process(
            [
                "timeout",
                "--kill-after=1s",
                "15s",
                "paseo",
                "send",
                "--no-wait",
                "--json",
                "f9add224-744b-471c-b812-c43cc179fa38",
                f"Bounded learned-paper native invocation finished exit={rc}. Read {output} "
                "and its .launcher completion/resource. Inspect actual receipts and failures; "
                "exit is not operation/profit proof. No manual/catch-up orders.",
            ],
            directory,
            "delivery.json",
            timeout_seconds=17,
        )
        delivery_rc = delivery["exit_code"]
        raw = (directory / "delivery.json").read_bytes()[: delivery["log_bytes"]]
        # Existing delivery acknowledgement semantics, no success from command exit alone.
        from importlib.util import module_from_spec, spec_from_file_location
        from types import SimpleNamespace

        parser = root / (
            "reports/ops/paper-stale-target-20261015/"
            "normal-reconcile-refresh-observation-20261016/delivery-status.py"
        )
        spec = spec_from_file_location("fixed_delivery_parser", parser)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        ack = module.check(SimpleNamespace(read_text=lambda: raw.decode()), delivery_rc)[
            "same_owner_sent_acknowledged"
        ]
    except Exception:
        ack = False
    final = rc if delivery_rc == 0 and ack is True else 74
    fixed_record(
        directory,
        "completion.json",
        dict(
            exit_code=final,
            native_exit=rc,
            delivery_exit=delivery_rc,
            acknowledged=ack is True,
            failures_retained=True,
        ),
    )
    return final


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--job", required=True)
    p.add_argument("--sha256", required=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--worker", action="store_true")
    mode.add_argument("--entry", action="store_true")
    args = p.parse_args()
    binding = dict(path=args.job, sha256=args.sha256)
    if args.entry:
        if sys.stdin.buffer.readline(4) != b"go\n":
            raise ValueError("parent did not publish exact owned-child identity")
        from open_composer.intraday_runner.current_receipt_only_entry import run

        try:
            result = run(args.root, binding)
            rc = 2 if json.loads(Path(result["path"]).read_text()).get("failures") else 0
        except BaseException as exc:
            job = json.loads(bound_bytes(args.root, binding))
            directory = require_prepared(job["output"], binding, job["invocation_id"])
            fixed_record(
                directory,
                "entry-emergency.json",
                dict(
                    status="entry_failed", error_type=type(exc).__name__, broker_outcome="UNKNOWN"
                ),
            )
            raise
    elif args.worker:
        rc = worker(args.root, binding)
    else:
        rc = launch(args.root, binding)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
