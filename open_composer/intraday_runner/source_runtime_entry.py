"""One scoped invocation, not a scheduler, authority issuer or automatic retry.

The parent launcher records actual child exit/completion. The exact Main-installed
manifest selects one phase; default source/account/order grants do not exist.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_composer.intraday_runner.source_activity_reception import bind, receive_actual, save
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_scientific_entry import kernel_evidence

PHASES = {
    "cash",
    "abandon",
    "quantity",
    "continuity",
    "sell",
    "buy",
    "reconcile",
    "closeout",
    "opening",
    "risk",
}


def preparation_start(job):
    """Optional native-bound local import interval; never a financial window."""
    value = job.get("prepare_not_before")
    if value is None:
        return None
    prepared = datetime.fromisoformat(value)
    begin = datetime.fromisoformat(job["not_before"])
    cutoff = datetime.fromisoformat(job["quote_cutoff"])
    expiry = datetime.fromisoformat(job["expires_at"])
    if (
        job["phase"] not in {"sell", "buy"}
        or any(x.tzinfo is None for x in (prepared, begin, cutoff, expiry))
        or begin != cutoff
        or not timedelta(0) < cutoff - prepared <= timedelta(seconds=120)
        or not cutoff < expiry <= cutoff + timedelta(seconds=5)
    ):
        raise ValueError("preparation must precede the same bounded sell/buy wave")
    return prepared


# Definitions only: no factories, source receiver, account snapshot or orders.
# Do not preload scientific receiver modules: their fresh-process rule remains.
PREPARATION_MODULES = (
    "open_composer.book_paper.accounts",
    "open_composer.intraday_runner.source_method_runtime",
    "open_composer.intraday_runner.source_initial_commit",
    "open_composer.intraday_runner.source_quote_reception",
    "open_composer.research.features.price_hygiene",
)


def prepare_entry(root, job_binding, output, *, clock=None, monotonic=None, sleep=None):
    """Finite same-child preloading before full live gates, without held locks.

    Both imports and waiting are inside the original parent timeout/cgroup and
    consumed invocation. Every current binding/kernel/disk check runs again in
    run(); no financial/source/account/price/risk snapshot crosses this interval.
    """
    clock = clock or (lambda: datetime.now(UTC))
    monotonic = monotonic or time.monotonic
    sleep = sleep or time.sleep
    job = json.loads(bound_bytes(root, job_binding))
    if preparation_start(job) is None:
        return
    initial_mono = monotonic()
    admitted_at = clock()
    job, _ = entry_gate(
        root, job_binding, admitted_at, requested_output=output, allow_preparation=True
    )
    marker = output.with_suffix(".launch-consumed.json")
    if json.loads(marker.read_text()).get("job") != job_binding:
        raise ValueError("preparation requires the original consumed launcher")
    started = clock()
    cutoff = datetime.fromisoformat(job["quote_cutoff"])
    # Fix the monotonic deadline to the originally admitted remaining interval.
    # Gate/marker/import time consumes it; a later UTC sample cannot enlarge it.
    wait_budget = (cutoff - admitted_at).total_seconds()
    elapsed = monotonic() - initial_mono
    if (
        not isinstance(started, datetime)
        or started.tzinfo is None
        or started.utcoffset() is None
        or not preparation_start(job) <= admitted_at <= started < cutoff
        or not 0 <= elapsed < wait_budget
    ):
        raise ValueError("preparation start clock discontinuity/deadline")
    for name in PREPARATION_MODULES:
        elapsed = monotonic() - initial_mono
        now = clock()
        if not started <= now < cutoff or not 0 <= elapsed < wait_budget:
            raise ValueError("preparation import clock discontinuity/deadline")
        importlib.import_module(name)
    imported = clock()
    while True:
        now = clock()
        if now >= cutoff:
            break
        remaining = wait_budget - (monotonic() - initial_mono)
        if remaining <= 0:
            raise ValueError("preparation clock discontinuity/deadline")
        sleep(min(0.05, remaining, (cutoff - now).total_seconds()))
    # Publication precedes the immediate live entry gate, and is not backdated.
    save(
        output.with_suffix(".preparation.json"),
        dict(
            job=job_binding,
            admitted_at=admitted_at.isoformat(),
            admitted_remaining_seconds=wait_budget,
            started_at=started.isoformat(),
            imports_completed_at=imported.isoformat(),
            imports_wait_completed_at=clock().isoformat(),
            elapsed_seconds=monotonic() - initial_mono,
            modules=list(PREPARATION_MODULES),
            source_account_order_calls=0,
            reusable_financial_snapshot=False,
        ),
    )


def entry_gate(root, job_binding, now, *, requested_output, allow_preparation=False):
    job = json.loads(bound_bytes(root, job_binding))
    if job.get("phase") not in PHASES or job.get("active") is not True:
        raise ValueError("one actual scoped runtime invocation required")
    begin = datetime.fromisoformat(job["not_before"])
    preparation = preparation_start(job)
    lower = preparation if allow_preparation and preparation is not None else begin
    if not lower <= now < datetime.fromisoformat(job["expires_at"]):
        raise ValueError("invocation inactive/expired")
    native = json.loads(bound_bytes(root, job["native_acceptance"]))
    if (
        native.get("accepted") is not True
        or native.get("scope") != "dia_base_complete_entry_v1"
        or job["phase"] not in native.get("allowed_phases", [])
        or job["code_bindings"] != native.get("code_bindings")
        or job["authority"] != native.get("authority")
        or job.get("prepare_not_before") != native.get("prepare_not_before")
    ):
        raise ValueError("actual accepted native entry/code/account scope missing")
    for b in job["code_bindings"]:
        bound_bytes(root, b)
    needed = {p.resolve() for p in Path(__file__).parent.glob("source_*.py")}
    present = {(root / b["path"]).resolve() for b in job["code_bindings"]}
    if not needed <= present:
        raise ValueError("incomplete runtime source code closure")
    bound_bytes(root, job["authority"])
    output = Path(job["output"])
    if (
        not output.is_absolute()
        or output != output.resolve()
        or Path(requested_output).absolute() != output
        or native.get("output") != job["output"]
        or native.get("invocation_id") != job["invocation_id"]
    ):
        raise ValueError("native invocation/output identity differs")
    kernel = kernel_evidence()
    free = os.statvfs(root).f_bavail * os.statvfs(root).f_frsize
    gate = json.loads(bound_bytes(root, job["disk_admission"]))
    if (
        gate.get("accepted") is not True
        or gate.get("invocation_id") != job["invocation_id"]
        or type(gate.get("required_free_bytes")) is not int
        or gate["required_free_bytes"] <= 0
        or free < gate["required_free_bytes"]
    ):
        raise ValueError("actual whole-route disk condition not satisfied")
    return job, dict(kernel=kernel, free_bytes=free, disk_gate=job["disk_admission"])


def entry_gate_read(root, binding, expected):
    current = json.loads(bound_bytes(root, binding))
    if current != expected or current.get("source_calls_allowed") is not True:
        raise ValueError("source job scope changed/unavailable")
    bound_bytes(root, current["authority"])
    now = datetime.now(UTC)
    if (
        not datetime.fromisoformat(current["not_before"])
        <= now
        < datetime.fromisoformat(current["expires_at"])
    ):
        raise ValueError("source job scope expired")


def run(root, job_binding, output):
    job, admission = entry_gate(root, job_binding, datetime.now(UTC), requested_output=output)
    _ensure_durable_directory(output.parent.absolute())
    output.mkdir(exist_ok=False)  # Consumed once, including pre-client/transport failures.
    save(
        output / "started.json",
        dict(job=job_binding, admission=admission, actual_started_at=datetime.now(UTC).isoformat()),
    )
    if job["phase"] == "cash":
        from open_composer.intraday_runner.source_cash_observation import observe

        result = observe(
            root,
            root / job["authority"]["path"],
            Path(job["state_directory"]),
            output / "cash-observation.json",
            expected_authority_binding=job["authority"],
        )
    else:
        from open_composer.book_paper.accounts import make_trading_client
        from open_composer.intraday_runner.source_method_runtime import SourceMethodRuntime

        runtime = SourceMethodRuntime(
            root,
            authority=job["authority"],
            state_directory=Path(job["state_directory"]),
            journal_directory=Path(job["journal_directory"]),
            client_factory=lambda: make_trading_client("quant2"),
        )
        transport = None
        try:
            with runtime.session():
                phase = job["phase"]
                if phase in {"quantity", "sell", "buy", "closeout", "opening", "risk"}:
                    if job.get("source_calls_allowed") is not True:
                        raise ValueError("actual source phase not authorized")
                    from open_composer.intraday_runner.source_input_transport import (
                        ExistingSourceTransport,
                    )

                    def read_source_scope():
                        entry_gate_read(root, job_binding, job)
                        runtime._read_guard()

                    from datetime import date, timedelta

                    from open_composer.intraday_runner.source_method_controls import (
                        primary_calendar,
                    )

                    source_deadline = (
                        primary_calendar(date(2026, 10, 31))["commit_at"]
                        if phase == "quantity"
                        else datetime.fromisoformat(job["quote_cutoff"]) + timedelta(seconds=5)
                    )
                    transport = ExistingSourceTransport(
                        root,
                        job["transport_bindings"],
                        allowed_ciks=set(),
                        expires_at=min(datetime.fromisoformat(job["expires_at"]), source_deadline),
                        read_guard=read_source_scope,
                    )
                if phase == "abandon":
                    result = runtime.abandon_local(job["abandon_ids"])
                elif phase == "quantity":
                    from open_composer.intraday_runner.source_initial_commit import receive_close
                    from open_composer.intraday_runner.source_quantity_commit import prepare_commit
                    from open_composer.intraday_runner.source_scientific_entry import (
                        run as receive_science,
                    )

                    received = receive_science(
                        root,
                        grant_binding=job["scientific_grant"],
                        contract_binding=runtime.auth["bindings"]["scientific_contract"],
                        phase="receive",
                    )
                    forecast = save(output / "forecast-reception.json", received["result"])
                    q = receive_close(runtime, transport, directory=output / "close")
                    commit = output / "commit.json"
                    prepare_commit(
                        root,
                        forecast_reception=forecast,
                        quantity_input=q,
                        revision=runtime.store.load(),
                        account_hash=runtime.auth["account_hash"],
                        output=commit,
                    )
                    result = dict(kind="quantity", commit=bind(commit))
                elif phase == "continuity":
                    from open_composer.intraday_runner.source_initial_commit import confirm_initial

                    result = dict(
                        continuity=confirm_initial(
                            runtime, job["commit"], directory=output / "continuity"
                        )
                    )
                elif phase == "reconcile":
                    result = receive_actual(runtime, output / "actual")
                else:
                    from open_composer.intraday_runner.source_quote_reception import receive_window
                    from open_composer.intraday_runner.source_state_checkpoint import restore

                    signal = json.loads(bound_bytes(root, job["signal"]))
                    if (
                        signal.get("account_hash") != runtime.auth["account_hash"]
                        or signal.get("authority") != job["authority"]
                        or signal.get("phase") != phase
                    ):
                        raise ValueError("actual logged signal/account/policy linkage absent")
                    cutoff = datetime.fromisoformat(job["quote_cutoff"])
                    from open_composer.market_sessions import NEW_YORK, us_equity_session_close

                    if (
                        cutoff.tzinfo is None
                        or us_equity_session_close(cutoff.astimezone(NEW_YORK).date()) is None
                    ):
                        raise ValueError("current actual exchange session required")
                    state, _, _, _ = restore(root, runtime.store.load()["snapshot"])
                    symbols = sorted(set(runtime.auth["universe"]) | set(state.cashbook.lots))
                    from open_composer.intraday_runner.source_initial_commit import receive_prior

                    prior_binding = receive_prior(
                        root,
                        transport,
                        day=cutoff.astimezone(NEW_YORK).date(),
                        symbols=symbols,
                        directory=output / "prior-reference",
                    )
                    prior = json.loads(bound_bytes(root, prior_binding))
                    response, quotes, pages = receive_window(
                        root,
                        transport,
                        symbols=symbols,
                        universe=runtime.auth["universe"],
                        cutoff=cutoff,
                        metadata_bindings=job["quote_metadata"],
                        prior_references=prior,
                        directory=output / "quotes",
                    )
                    obs = runtime.capture_observation(quotes=quotes, directory=output / "account")
                    if phase in {"opening", "risk"}:
                        from datetime import time, timedelta

                        from open_composer.intraday_runner.source_dispatch_journal import _hash
                        from open_composer.intraday_runner.source_state_checkpoint import snapshot
                        from open_composer.market_sessions import NEW_YORK

                        observed = json.loads(bound_bytes(root, obs))
                        revision = runtime.store.load()
                        state, fills, fees, evidence = restore(root, revision["snapshot"])
                        risk = observed["risk"]
                        evidence.update({k: risk[k] for k in ("daily_halt", "kill", "high_water")})
                        if phase == "opening":
                            now = datetime.now(UTC)
                            day = now.astimezone(NEW_YORK).date()
                            opened = datetime.combine(day, time(9, 30), NEW_YORK)
                            if (
                                cutoff != opened
                                or not opened <= now <= opened + timedelta(seconds=5)
                                or observed["own_nav"] is None
                                or observed["own_nav"] <= 0
                                or evidence.get("risk_session") == day.isoformat()
                            ):
                                raise ValueError(
                                    "unknown/late/already recorded actual opening baseline"
                                )
                            evidence.update(
                                risk_session=day.isoformat(),
                                day_open_nav=observed["own_nav"],
                                daily_halt=False,
                                opening_observation=obs,
                            )
                        runtime.store.commit(
                            snapshot(state, fills, fees, evidence=evidence),
                            expected_head_sha256=_hash(revision),
                        )
                        # No order is issued from this observation phase. A kill
                        # produces a substantive owned-exit requirement for the
                        # same authorized controller, never a hidden market order.
                        result = dict(
                            status="actual_owned_risk_observation",
                            observation=obs,
                            controlled_exit_required=risk["kill"],
                            order_writes=0,
                        )
                    elif phase == "closeout":
                        result = runtime.closeout(
                            observation_binding=obs,
                            quotes=quotes,
                            quote_cutoff=cutoff,
                            signal_binding=job["signal"],
                        )
                    else:
                        result = runtime.wave(
                            commit_binding=job["commit"],
                            signal_binding=job["signal"],
                            observation_binding=obs,
                            metadata_bindings=job["quote_metadata"],
                            quote_response=response,
                            prior_references=prior,
                            side=phase,
                            continuity_binding=job["continuity"],
                            continuity_completion_binding=job["continuity_completion"],
                            quantity_completion_binding=job["quantity_completion"],
                        )
                    result["quote_capture_paths"] = pages
                    result["prior_reference"] = prior_binding
        finally:
            if transport is not None:
                transport.close()
    save(output / "result.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--job-binding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    existed = args.output.exists()
    try:
        root = args.root.resolve()
        binding = json.loads(args.job_binding.read_text())
        output = args.output.absolute()
        prepare_entry(root, binding, output)
        run(root, binding, output)
    except Exception as exc:
        # No exception string that might contain credentials/account payloads.
        if not existed and args.output.exists():
            save(
                args.output / "failure.json",
                dict(
                    error_type=type(exc).__name__,
                    actual_failed_at=datetime.now(UTC).isoformat(),
                    success=False,
                ),
            )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
