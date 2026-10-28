"""Fresh-process source/build/publish/receive bridge to the accepted scientific package.

No schedule or native approval issuer. Actual source/action grants, exact
independent native entry and kernel admission must exist before any import or
factory construction. Scientific source/label/model semantics stay in 7b's code.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner.source_input_transport import ExistingSourceTransport
from open_composer.intraday_runner.source_method_bindings import bound_bytes


def kernel_evidence():
    lines = Path("/proc/self/cgroup").read_text().splitlines()
    line = next((x for x in lines if x.startswith("0::")), None)
    if line is None:
        raise ValueError("unified capped native cgroup required")
    path = Path("/sys/fs/cgroup") / line.split("::", 1)[1].lstrip("/")
    maximum = (path / "memory.max").read_text().strip()
    if maximum == "max" or not 0 < int(maximum) <= 900 * 1024**2 or os.sched_getaffinity(0) != {0}:
        raise ValueError("actual <=900MiB/CPU0 capped entry required")
    if (path / "memory.swap.max").read_text().strip() != "0":
        raise ValueError("actual zero-swap native scope required")
    memory = dict(
        (line.split(":")[0], int(line.split()[1]))
        for line in Path("/proc/meminfo").read_text().splitlines()
    )
    if memory["MemAvailable"] < 500 * 1024:
        raise ValueError("owner reserve not currently available")
    return dict(
        pid=os.getpid(),
        cgroup=str(path),
        memory_max_bytes=int(maximum),
        CPU_affinity=[0],
        available_KiB=memory["MemAvailable"],
        observed_at=datetime.now(UTC).isoformat(),
    )


def run(root: Path, *, grant_binding: dict, contract_binding: dict, phase: str, month="2026-10"):
    grant = json.loads(bound_bytes(root, grant_binding))
    contract = json.loads(bound_bytes(root, contract_binding))
    now = datetime.now(UTC)
    if (
        grant.get("kind") != "dia_base_scientific_runtime"
        or grant.get("active") is not True
        or phase not in grant.get("allowed_phases", [])
        or month != "2026-10"
    ):
        raise ValueError("exact prospective scientific runtime grant absent")
    if (
        not datetime.fromisoformat(grant["authorized_at"])
        <= now
        < datetime.fromisoformat(grant["expires_at"])
    ):
        raise ValueError("scientific runtime grant expired/inactive")
    native = json.loads(bound_bytes(root, grant["native_acceptance"]))
    if (
        native.get("accepted") is not True
        or native.get("scope") != "dia_base_scientific_runtime"
        or native.get("contract") != contract_binding
    ):
        raise ValueError("native scientific entry not actually accepted")
    codes = contract["reviewed_runtime_code"]
    for b in [*codes, *grant["runtime_code"]]:
        bound_bytes(root, b)
    if native.get("runtime_code") != grant["runtime_code"] or not any(
        Path(b["path"]).resolve() == Path(__file__).resolve() for b in grant["runtime_code"]
    ):
        raise ValueError("native code closure differs")
    kernel = kernel_evidence()
    package = Path(next(b["path"] for b in codes if Path(b["path"]).name == "receiver.py")).parent
    if any(
        name in sys.modules
        for name in (
            "receiver",
            "receiver_common",
            "source_contract",
            "source_writer",
            "scheduled_base",
        )
    ):
        raise ValueError("scientific bridge requires a fresh isolated process")
    sys.path.insert(0, str(package))
    receiver = importlib.import_module("receiver")

    def admit(plan, reviewed_code, calendar, invocation_id):
        actual = kernel_evidence()
        if reviewed_code != receiver.code_bindings():
            raise ValueError("scientific code changed before admission")
        for b in [*codes, *grant["runtime_code"]]:
            bound_bytes(root, b)
        if datetime.now(UTC) >= datetime.fromisoformat(grant["expires_at"]):
            raise ValueError("grant expired")
        return dict(
            role="actual scoped native admission, not paper permission",
            grant=grant_binding,
            native=grant["native_acceptance"],
            actual_kernel=actual,
            invocation_id=invocation_id,
            plan=plan,
            reviewed_code=reviewed_code,
            calendar=calendar,
        )

    def source_read_guard():
        if (
            json.loads(bound_bytes(root, grant_binding)) != grant
            or grant.get("source_calls_allowed") is not True
        ):
            raise ValueError("bound scientific source authority changed")
        bound_bytes(root, grant["native_acceptance"])
        now = datetime.now(UTC)
        if (
            not datetime.fromisoformat(grant["authorized_at"])
            <= now
            < datetime.fromisoformat(grant["expires_at"])
        ):
            raise ValueError("actual scientific source authority expired")

    transport = None
    try:
        if phase == "source":
            if grant.get("source_calls_allowed") is not True:
                raise ValueError("actual finite source authority absent")
            transport = ExistingSourceTransport(
                root,
                grant["transport_bindings"],
                allowed_ciks=set(grant["fixed_ciks"]),
                read_guard=source_read_guard,
                expires_at=min(
                    datetime.fromisoformat(grant["expires_at"]),
                    datetime.fromisoformat(contract["calendar"]["source_cutoff"]),
                ),
            )
            writer = importlib.import_module("source_writer")
            result = str(writer.collect_month_sources(month, fetch=transport.fetch, admit=admit))
        elif phase == "build":
            result = str(
                receiver.build_monthly_input(
                    package / "captures" / month / "manifest.json", admit=admit
                )
            )
        elif phase == "publish":
            result = receiver.publish_forecast(month, admit=admit)
        elif phase == "receive":
            context = package / "received" / month / "context.json"
            receiver.receive_monthly_input(context, contract["calendar"]["source_cutoff"])
            result = importlib.import_module("scheduled_base").receive(
                context.parent / "forecast", month, receiver.binding(context)
            )
            result.update(
                accepted=True, formation_month=month, native_acceptance=grant["native_acceptance"]
            )
        else:
            raise ValueError("unsupported phase")
        return dict(
            status="completed",
            phase=phase,
            actual_kernel=kernel,
            result=result,
            paper_permission=False,
        )
    finally:
        if transport is not None:
            transport.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--grant-binding", type=Path, required=True)
    p.add_argument("--contract-binding", type=Path, required=True)
    p.add_argument("--phase", choices=["source", "build", "publish", "receive"], required=True)
    args = p.parse_args()
    result = run(
        args.root.resolve(),
        grant_binding=json.loads(args.grant_binding.read_text()),
        contract_binding=json.loads(args.contract_binding.read_text()),
        phase=args.phase,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
