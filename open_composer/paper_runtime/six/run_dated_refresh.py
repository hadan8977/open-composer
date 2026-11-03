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

from open_composer.paper_runtime.six.formation_continuity import (
    monthly_base_supported,
    partition,
    receive_h5_instruction,
    receive_state_instruction,
    request_menu,
)
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
    """Saved HTTP/request/page closure only; never reconstruct features or signals."""
    from open_composer.market_sessions import us_equity_session_dates

    output = Path(output).resolve()
    reuse = output / "source-reuse.json"
    if reuse.exists():
        receipt = json.loads(reuse.read_text())
        original = Path(receipt["original_directory"]).resolve()
        assert original == (RUNS / now.date().isoformat()).resolve() and original != output
        assert receipt["source"] == binding(original / "current-source.json")
        assert receipt["failed_attempt"] == binding(original / "refresh-exit.json")
        failed = json.loads((original / "refresh-exit.json").read_text())
        assert failed["status"] == "blocked_preserved_no_replay"
        assert failed["targets_published"] is False and failed["model_fits"] == 0
        assert failed["stages"][0]["phase"] == "source" and failed["stages"][0]["exit_code"] == 0
        assert (output / "current-source.json").read_bytes() == (original / "current-source.json").read_bytes()
        return receive_source_inventory(original, now=now)
    source = json.loads((output / "current-source.json").read_text())
    clock = receive_clock(source["application_day"], source["reference_day"], now=now)
    assert source["prior_reference_day"] == clock["prior_reference_day"]
    plan_path = (
        REPO
        / "reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020/next-session-20261021/next-session-source-plan-M1.json"
    )
    assert source["source_plan"] == binding(plan_path)
    assert (
        source["source_plan"]["sha256"]
        == "2c9c1f7f645f0268b1edc301ff97be19bf8fdbc3a878dfc9acc102511754265f"
    )
    plan = json.loads(plan_path.read_text())
    contract = source["formation_request_contract"]
    assert (
        contract["reference_day"] == source["reference_day"]
        and contract["application_day"] == source["application_day"]
    )
    menu = request_menu(plan, contract)
    assert [(r["group"], r["key"]) for r in source["data"]] == [(g, r["key"]) for g, r in menu], (
        "Incomplete/foreign source families"
    )
    assert source["full_pagination"] is True

    def checked(row, path):
        assert Path(row["path"]) == path.absolute() and path.resolve() == path.absolute(), (
            "Foreign source page"
        )
        assert row == binding(path), "Wrong source path/hash/bytes"
        return json.loads(Path(path).read_text())

    count = 0
    paths = set()
    captured = datetime.fromisoformat(source["captured_at"].replace("Z", "+00:00"))
    assert captured.tzinfo is not None and captured <= now
    for declared, (group, request) in zip(source["data"], menu, strict=True):
        params = request["params"]
        assert declared["pages"]
        cursor = None
        seen = set()
        cells = set()
        for i, page in enumerate(declared["pages"]):
            stem = output / "source" / f"{group}-{request['key']}-{i:03}"
            expected = dict(params)
            if cursor:
                expected["page_token"] = cursor
            meta = checked(page["metadata"], stem.with_suffix(".json"))
            body = checked(page["response"], stem.with_suffix(".raw"))
            assert meta["response"] == page["response"] and meta["status_code"] == 200
            intent = checked(meta["intent"], stem.with_suffix(".started.json"))
            assert (
                meta["endpoint"] == intent["endpoint"] == request["endpoint"]
                and meta["params"] == intent["params"] == expected
            )
            assert intent["retry"] == 0
            began = datetime.fromisoformat(intent["at"].replace("Z", "+00:00"))
            received = datetime.fromisoformat(meta["received_at"].replace("Z", "+00:00"))
            assert began.tzinfo is not None and received.tzinfo is not None
            assert (
                datetime.fromisoformat(clock["application_day"] + "T00:20:00+00:00")
                <= began
                <= received
                <= captured
            )
            for row in [page["metadata"], page["response"], meta["intent"]]:
                assert row["path"] not in paths
                paths.add(row["path"])
            if request["key"] == "actions":
                assert type(body["corporate_actions"]) is dict
            else:
                assert type(body["bars"]) is dict and set(body["bars"]) <= set(
                    params["symbols"].split(",")
                )
                for symbol, rows in body["bars"].items():
                    for bar in rows:
                        key = (symbol, bar["t"][:10])
                        assert key not in cells
                        cells.add(key)
                        assert params["start"][:10] <= key[1] < params["end"][:10]
            cursor = body.get("next_page_token")
            if i + 1 < len(declared["pages"]):
                assert type(cursor) is str and cursor and cursor not in seen
                seen.add(cursor)
            else:
                assert cursor is None, "Unclosed page cursor"
            count += 1
        if request["key"] != "actions":
            symbols = set(params["symbols"].split(","))
            if group == "core" and request["key"] == "raw-bars":
                symbols -= set(plan["core"]["ceased_and_carriers"]["known_no_current_bar"])
            dates = us_equity_session_dates(
                date.fromisoformat(params["start"][:10]),
                date.fromisoformat(params["end"][:10]) - timedelta(days=1),
            )
            expected = {(s, d.isoformat()) for s in symbols for d in dates}
            if group == "core" and request["key"] == "raw-bars":
                # Extended historical days support H5/BASE separately. The original
                # two most recent complete daily controls remain globally required.
                required = {(s, d) for s, d in expected if d >= clock["prior_reference_day"]}
                assert required <= cells <= expected, (
                    "Missing current/foreign core symbol/date source cells"
                )
            else:
                assert cells == expected, "Missing/extra fixed symbol/date source cells"
    assert source["physical_GETs"] == count
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
    from open_composer.market_sessions import us_equity_session_close
    from open_composer.paper_runtime.six.paper_target_input_controls import receive_action_lineage

    receive_current_paper_maintenance()
    output = Path(output)
    result = json.loads((output / "target-production-result.json").read_text())
    source = receive_source_inventory(output, now=now)
    assert result["source"] == binding(output / "current-source.json")
    assert result["application_day"] == source["application_day"] == now.date().isoformat()
    assert source["full_pagination"] is True
    partition(result["targets"], result["blocked_policies"])
    assert result["dependency_manifest"] == binding(output / "policy-dependencies.json")
    assert (
        json.loads((output / "policy-dependencies.json").read_text())["blocked"]
        == result["blocked_policies"]
    )
    application = date.fromisoformat(source["application_day"])
    reference = date.fromisoformat(source["reference_day"])
    close = us_equity_session_close(application)
    prior = us_equity_session_close(reference)
    assert close is not None and prior is not None and reference < application
    expected_asof = datetime.combine(
        reference, prior, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(UTC)
    expected_expiry = datetime.combine(
        application, close, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(UTC) - timedelta(minutes=30)
    assert now < expected_expiry
    lineage = receive_action_lineage(output)
    received = {}
    targets = {}
    for policy, row in result["targets"].items():
        path = output / "targets" / (policy + ".json")
        assert row == binding(path)
        target = json.loads(path.read_text())
        assert target["source"] == result["source"] and target["retained_action_lineage"] == lineage
        assert (
            target["application_day"] == source["application_day"]
            and target["reference_day"] == source["reference_day"]
        )
        assert datetime.fromisoformat(target["as_of"].replace("Z", "+00:00")) == expected_asof
        assert (
            datetime.fromisoformat(target["valid_until"].replace("Z", "+00:00")) == expected_expiry
        )
        # Existing pure target/whole-six-cent receiver; no service construction or tick.
        SixPaperService.target_books(None, policy, target, now)
        if policy in {"BASE", "BASE_STATE_BUDGET"}:
            monthly_base_supported(source["application_day"])
        if policy == "H5":
            receive_h5_instruction(output, target)
        if policy in {"MULTI_EQUAL", "MULTI_HIERARCHICAL"}:
            _children = (
                {v["name"]: v for v in target["children"]}
                if isinstance(target["children"], list)
                else target["children"]
            )
            monthly_base_supported(source["application_day"])
        received[policy] = path.read_bytes()
        targets[policy] = target
    receive_current_dependencies(targets, result["targets"])
    return received


def receive_current_dependencies(targets, rows):
    """Already-received policy linkage, not another source or model decision."""
    if "BASE_STATE_BUDGET" in targets:
        receive_state_instruction(
            targets["BASE_STATE_BUDGET"],
            targets["BASE"],
            targets["H5"],
            base_row=rows["BASE"],
            h5_row=rows["H5"],
        )
    for policy in {"MULTI_EQUAL", "MULTI_HIERARCHICAL"} & targets.keys():
        children = targets[policy]["children"]
        names = ["S1", "S2", "S3", "C2", "BASE", "H5"]
        assert len(children) == 6
        children = {v["name"]: v for v in children} if isinstance(children, list) else children
        assert set(children) == set(names)
        cents = (
            [333334, 333334, 333333, 333333, 333333, 333333]
            if policy == "MULTI_EQUAL"
            else [166667, 166667, 166666, 500000, 500000, 500000]
        )
        assert sum(cents) == 2000000
        for name, capital in zip(names, cents, strict=True):
            assert children[name]["name"] == name
            # Exact original wrapper cents; this is not actual funding acceptance.
            value = children[name]["capital_usd"]
            assert type(value) in [int, float] and value == capital / 100
        for name in ["BASE", "H5"]:
            assert {
                k: v for k, v in children[name].items() if k not in {"name", "capital_usd"}
            } == targets[name], (
                "Composite current BASE/H5 child differs from received standalone instruction"
            )


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
        assert path.read_bytes() == old, "Live target changed while receiving this packet"
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
            and intent["producer"] == binding(__file__)
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
            # Admission is fresh before each import-heavy child; no waiting in the broker loop.
            admission = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts/memory_budget.py"),
                    "admit",
                    "--kind",
                    "job",
                    "--class",
                    "research",
                    "--mem",
                    str(cap),
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            save(
                output / (phase + "-admission.json"),
                dict(
                    returncode=admission.returncode,
                    stdout=admission.stdout,
                    stderr=admission.stderr,
                ),
            )
            if admission.returncode:
                raise RuntimeError(phase + " admission refused; retain inputs, no automatic replay")
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
        for policy, row in produced["targets"].items():
            assert binding(output / "targets" / (policy + ".json")) == row
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
