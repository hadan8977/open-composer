# ruff: noqa: E402 -- Runtime paths and frozen-source imports initialize in order.
# ruff: noqa: E501 -- Historical evidence paths and exact audit literals.
"""One finite, staging-only invocation of the existing paper-input producer.

The existing service may launch this asynchronously after its protective tick.
This file never constructs a broker client or runs a timer. Its optional input
publisher is called only by the integrated native host after successful staging.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from open_composer.paper_runtime.paths import repo_root, runtime_root

REPO = repo_root()
HERE = Path(__file__).resolve().parent
# All four reviewed input scripts are installed together beside this entrypoint.

from open_composer.paper_runtime.six.formation_continuity import partition
from open_composer.paper_runtime.six.paper_target_input_controls import (
    receive_current_paper_maintenance,
)

POLICIES = {"BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"}
TARGETS = runtime_root(REPO) / "targets"
RUNS = REPO / "reports/paper/diagnostics/dated-target-refresh"


def binding(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return dict(path=str(path), bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def receive_clock(application_day=None, reference_day=None, *, now=None):
    from open_composer.market_sessions import us_equity_session_close, us_equity_session_dates

    now = datetime.now(UTC) if now is None else now
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0), "Aware UTC clock required"
    app = now.date()
    assert application_day is None or application_day == app.isoformat()
    sessions = us_equity_session_dates(app - timedelta(days=15), app)
    assert len(sessions) >= 3 and sessions[-1] == app, "Application is not a regular session"
    ref, previous = sessions[-2], sessions[-3]
    assert reference_day is None or reference_day == ref.isoformat(), (
        "Not the exact preceding regular session"
    )
    close = us_equity_session_close(app)
    assert close is not None
    expiry = datetime.combine(app, close, tzinfo=ZoneInfo("America/New_York")).astimezone(
        UTC
    ) - timedelta(minutes=30)
    assert (
        datetime.combine(app, datetime.min.time(), tzinfo=UTC) + timedelta(minutes=20)
        <= now
        < expiry
    ), "Outside source/delivery horizon"
    return dict(
        application_day=app.isoformat(),
        reference_day=ref.isoformat(),
        prior_reference_day=previous.isoformat(),
        expiry=expiry,
    )


def receive_source_inventory(output, *, now):
    """Require a dated source and the last completed session in each bar family."""
    source = json.loads((Path(output) / "current-source.json").read_text())
    receive_clock(source["application_day"], source["reference_day"], now=now)
    for request in source["data"]:
        pages = [
            json.loads(Path(p["response"]["path"]).read_text()) if "response" in p else p
            for p in request["pages"]
        ]
        if not pages or pages[-1].get("next_page_token"):
            raise ValueError(f"Incomplete source reception: {request['group']}/{request['key']}")
        if request["key"] != "actions" and not any(
            bar["t"][:10] == source["reference_day"]
            for page in pages
            for bars in page["bars"].values()
            for bar in bars
        ):
            raise ValueError(f"Stale source reception: {request['group']}/{request['key']}")
    return source


def commands(output, application_day):
    py = REPO / ".venv/bin/python"
    torch_py = Path("/usr/bin/python3.12")
    return [
        (
            "source",
            100,
            [
                str(py),
                "-m",
                "open_composer.paper_runtime.six.fetch_current",
                "--output",
                str(output),
                "--application-day",
                application_day,
            ],
        ),
        (
            "prepare",
            600,
            [
                str(py),
                "-m",
                "open_composer.paper_runtime.six.produce_targets",
                "--output",
                str(output),
                "--phase",
                "prepare",
            ],
        ),
        (
            "inference",
            700,
            [
                str(torch_py),
                "-m",
                "open_composer.paper_runtime.six.lstm_infer",
                "--output",
                str(output),
            ],
        ),
        (
            "assemble",
            200,
            [
                str(py),
                "-m",
                "open_composer.paper_runtime.six.produce_targets",
                "--output",
                str(output),
                "--phase",
                "assemble",
            ],
        ),
        (
            "finish",
            200,
            [
                str(py),
                "-m",
                "open_composer.paper_runtime.six.produce_targets",
                "--output",
                str(output),
                "--phase",
                "finish",
            ],
        ),
    ]


def receive_packet(output, *, now):
    """Receive already-produced inputs; no source, numerical work or broker call."""
    from open_composer.intraday_runner.six_paper_service import SixPaperService

    receive_current_paper_maintenance()
    output = Path(output)
    result = json.loads((output / "target-production-result.json").read_text())
    source = receive_source_inventory(output, now=now)
    if result["application_day"] != source["application_day"]:
        raise ValueError("Target packet application does not match current input session")
    partition(result["targets"], result["blocked_policies"])
    received = {}
    for policy in result["targets"]:
        path = output / "targets" / (policy + ".json")
        body = path.read_bytes()
        target = json.loads(body)
        if target["application_day"] != source["application_day"]:
            raise ValueError(f"Stale target application: {policy}")
        SixPaperService.target_books(None, policy, target, now)
        received[policy] = body
    return received


def publish_packet(output, *, now):
    """Only input files change; the service retains books, IDs, stops and capital."""
    output = Path(output)
    received = receive_packet(output, now=now)
    predecessor = output / "predecessor-targets"
    predecessor.mkdir(exist_ok=False)
    published = {}
    for policy, body in received.items():
        receive_current_paper_maintenance()
        path = TARGETS / (policy + ".json")
        # Preserve each exact predecessor before an atomic individual-policy replacement.
        old = path.read_bytes()
        backup = predecessor / path.name
        with backup.open("xb") as stream:
            stream.write(old)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(predecessor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        temp = path.with_name("." + path.name + ".dated-refresh-" + output.name)
        with temp.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        receive_current_paper_maintenance()
        receive_clock(json.loads(body)["application_day"], json.loads(body)["reference_day"])
        os.replace(temp, path)
        fd = os.open(TARGETS, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        published[policy] = binding(path)
    save(
        output / "publication.json",
        dict(at=now.isoformat(), targets=published, books_orders_capital_or_risk_mutated=False),
    )
    return published


def write_liquidation_targets(application_day):
    from open_composer.intraday_runner.current_initialization_controls import session
    from open_composer.intraday_runner.six_paper_service import (
        CHILD_CAPITAL,
        CHILDREN,
        RETIRING_POLICIES,
        write_state,
    )

    clock = receive_clock(application_day)
    reference_day = clock["reference_day"]
    as_of = session(date.fromisoformat(reference_day))[1].isoformat()
    config = json.loads((REPO / "config/paper/six-service.json").read_text())
    targets = REPO / config["targets_root"]
    cash = dict(portfolio_action="rebalance", symbols=[], weights=[], reference_marks={})
    for policy in RETIRING_POLICIES:
        target = dict(
            cash,
            policy=policy,
            as_of=as_of,
            valid_until=clock["expiry"].isoformat(),
            application_day=application_day,
            reference_day=reference_day,
        )
        if policy in CHILD_CAPITAL:
            target["children"] = {
                name: dict(cash, capital_usd=capital)
                for name, capital in zip(CHILDREN, CHILD_CAPITAL[policy], strict=True)
            }
        write_state(targets / (policy + ".json"), target)


def poll_refresh(job, *, now):
    """One nonblocking step called AFTER the existing service protective tick.

    No new timer or background watcher. Failed/partial attempts are retained and
    never automatically replayed. Valid targets need no producer invocation.
    """
    receive_current_paper_maintenance()
    if job is not None:
        if job.poll() is None:
            return job
        job.wait()  # Already terminal: reap only, never wait for running science.
        return None
    if all(
        (TARGETS / (p + ".json")).exists()
        and json.loads((TARGETS / (p + ".json")).read_text()).get("application_day")
        == now.date().isoformat()
        for p in POLICIES
    ):
        return None
    try:
        receive_clock(now=now)
    except AssertionError:
        return None
    output = RUNS / now.date().isoformat()
    if output.exists():
        return None  # Preserve existing started/completed/partial attempt.
    # Durable launch identity is created before Popen; worker receives this exact path.
    output.mkdir(parents=True, exist_ok=False)
    save(
        output / "launch-intent.json",
        dict(
            at=now.isoformat(), producer=binding(__file__), application_day=now.date().isoformat()
        ),
    )
    log = (output / "worker.log").open("xb")
    try:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "open_composer.paper_runtime.six.run_dated_refresh",
                "--output",
                str(output),
                "--application-day",
                now.date().isoformat(),
                "--received-launch",
                "--publish",
            ],
            cwd=REPO,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    finally:
        log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--application-day", required=True)
    parser.add_argument("--received-launch", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(REPO / "reports/paper/diagnostics")
    receive_clock(args.application_day)
    receive_current_paper_maintenance()
    # Atomic unique directory also refuses completed, partial or concurrently owned runs.
    if args.received_launch:
        intent = json.loads((output / "launch-intent.json").read_text())
        assert (
            output == RUNS / args.application_day
            and intent["application_day"] == args.application_day
        )
        assert not (output / "refresh-start.json").exists()
    else:
        output.mkdir(parents=True, exist_ok=False)
    save(
        output / "refresh-start.json",
        dict(
            at=datetime.now(UTC).isoformat(),
            pid=os.getpid(),
            producer=binding(__file__),
            application_day=args.application_day,
            staging_only=not args.publish,
        ),
    )
    result = dict(
        stages=[], source_retries=0, model_fits=0, targets_published=False, broker_operator_calls=0
    )
    status = 1
    try:
        for phase, cap, command in commands(output, args.application_day):
            receive_current_paper_maintenance()
            receive_clock(args.application_day)
            wrapper = [
                str(REPO / "scripts/run_capped.sh"),
                "--class",
                "paper",
                "--mem",
                str(cap) + "M",
                "--swap",
                "0",
                "--",
                "/usr/bin/time",
                "-v",
                "-o",
                str(output / (phase + ".profile")),
                "timeout",
                "1200",
                "taskset",
                "-c",
                "0",
                "env",
                "PYTHONDONTWRITEBYTECODE=1",
                "OMP_NUM_THREADS=1",
                "OPENBLAS_NUM_THREADS=1",
                "MKL_NUM_THREADS=1",
            ]
            with (output / (phase + ".log")).open("xb") as log:
                child = subprocess.run(
                    wrapper + command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT
                )
            result["stages"].append(
                dict(
                    phase=phase,
                    exit_code=child.returncode,
                    profile=binding(output / (phase + ".profile")),
                    log=binding(output / (phase + ".log")),
                )
            )
            if child.returncode:
                raise RuntimeError(
                    phase + " failed; preserve complete/partial evidence, no automatic replay"
                )
        produced = json.loads((output / "target-production-result.json").read_text())
        partition(produced["targets"], produced["blocked_policies"])
        result.update(
            target_result=binding(output / "target-production-result.json"),
            status="complete_staging_packet_not_installed",
        )
        if args.publish:
            result.update(
                published=publish_packet(output, now=datetime.now(UTC)),
                targets_published=True,
                status="partial_current_input_packet_published"
                if produced["blocked_policies"]
                else "complete_current_input_packet_published",
            )
            write_liquidation_targets(args.application_day)
        status = 0
    except Exception as error:
        result.update(
            status="blocked_preserved_no_replay", error_type=type(error).__name__, error=str(error)
        )
    finally:
        result.update(at=datetime.now(UTC).isoformat(), exit_code=status)
        save(output / "refresh-exit.json", result)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
