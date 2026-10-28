"""Finite research rounds; file contracts are independent of the agent provider.

This coordinates agents, not financial simulation or broker operations. Existing
engines and scientific contracts remain responsible for numerical evidence.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager, nullcontext, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["complete", "blocked"]
    summary: str = Field(min_length=1)
    decision: Literal["accept", "revise", "continue", "repair", "branch", "park", "none"]
    results: str | None
    next_brief: str | None
    checkpoint: str | None


class Results(BaseModel):
    """Engine-produced summary. Structural validity is not scientific acceptance."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    direction: str
    kind: Literal["financial", "diagnostic"]
    engine: str = Field(min_length=1)
    source_artifacts: list[str] = Field(min_length=1)
    data_and_exposure: str = Field(min_length=1)
    costs: str = Field(min_length=1)
    baseline: str = Field(min_length=1)
    n_trials: int = Field(ge=0)
    net_profit_usd: float | None
    baseline_net_profit_usd: float | None
    dsr: float | None = Field(ge=0, le=1)
    dsr_note: str = Field(min_length=1)
    limitations: list[str]

    @model_validator(mode="after")
    def financial_evidence(self):
        if self.kind == "financial" and (self.n_trials < 1 or self.net_profit_usd is None):
            raise ValueError("Financial results need actual trial count and net profit")
        return self


def local_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence and tasks must stay inside the repository")
    return path


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", value):
        raise ValueError("Use a short alphanumeric direction/run id")
    return value


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def validate_results(root: Path, name: str, direction: str) -> Results:
    path = local_path(root, name)
    result = Results.model_validate_json(path.read_text())
    if result.direction != direction:
        raise ValueError("Result direction does not match the assignment")
    for artifact in result.source_artifacts:
        source = local_path(root, artifact)
        if source == path or not source.is_file():
            raise ValueError(f"Missing independent engine artifact: {artifact}")
    return result


def require_research(root: Path) -> None:
    control = json.loads((root / "control.json").read_text())
    if control.get("draft") is not False or control.get("research") is not True:
        raise ValueError("Research has not been enabled in installed control.json")
    legacy = root / "reports/research/control/owner-compute-hold.json"
    if legacy.exists():
        hold = json.loads(legacy.read_text())
        if hold.get("research_paused") or any(
            hold.get(key) is False for key in ("research_allowed", "research_new_starts_allowed")
        ):
            raise ValueError("Legacy research hold remains active; reconcile authority first")


def codex_command(root: Path, role: dict, output: Path, schema: Path) -> list[str]:
    """Only this boundary is provider-specific; Claude is not enabled implicitly."""
    if role["provider"] != "codex":
        raise ValueError("Only Codex is implemented; add and verify a provider adapter first")
    return [
        "codex",
        "exec",
        "--cd",
        str(root),
        "--model",
        role["model"],
        "--sandbox",
        "danger-full-access",
        "-c",
        'approval_policy="never"',
        "-c",
        f'model_reasoning_effort="{role["effort"]}"',
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output),
        "-",
    ]


def execute(command: list[str], prompt: str, folder: Path, timeout: float) -> dict:
    """Wait for one process; preserve logs and stop its local group on interruption."""
    with (folder / "events.jsonl").open("w") as events, (folder / "stderr.log").open("w") as err:
        process = None
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=events,
                stderr=err,
                text=True,
                start_new_session=True,
            )
            write_json(
                folder / "process.json",
                {"pid": process.pid, "started": datetime.now(UTC).isoformat()},
            )
            process.communicate(prompt, timeout=timeout)
        except BaseException:
            if process is None:
                raise
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            # A promptly exiting leader can leave descendants ignoring TERM.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    usage, session = None, None
    with (folder / "events.jsonl").open() as events:
        for line in events:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage")
            elif event.get("type") == "thread.started":
                session = event.get("thread_id")
    return {"session": session, "usage": usage, "exit_code": process.returncode}


@contextmanager
def direction_lock(path: Path):
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("This direction already has a running round") from exc
        yield


def require_resolved_runs(task: Path) -> None:
    """A released lock is not proof that an interrupted job has stopped."""
    for path in (task / "runs").glob("*/run.json"):
        state = json.loads(path.read_text())
        phases = state.get("phases", {})
        # A local return code cannot establish whether a remote job is still live.
        unresolved = state.get("status") in ("running", "interrupted_or_failed")
        checkpoint = phases.get("worker", {}).get("checkpoint")
        if (unresolved or checkpoint) and state.get("status") != "closed_after_recovery":
            raise ValueError(f"Reconcile unfinished job/checkpoint before a new start: {path}")


def run_round(
    root: Path,
    direction: str,
    run_id: str,
    timeout: float,
    *,
    review_plan: bool = False,
    execute_fn=execute,
    brief_name: str | None = None,
    _locked: bool = False,
) -> dict:
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    if timeout <= 0:
        raise ValueError("A positive wall-clock timeout is required")
    task = local_path(root, f"research/{direction}")
    brief = local_path(root, brief_name) if brief_name else task / "brief.md"
    if not brief.is_file() or not 0 < brief.stat().st_size <= 1000:
        raise ValueError("A non-empty brief of at most 1000 bytes is required")
    require_research(root)
    config = json.loads((root / "research/workflow.json").read_text())
    phases = (["plan_review"] if review_plan else []) + ["worker", "reviewer", "lead"]
    run = local_path(root, f"research/{direction}/runs/{run_id}")
    with nullcontext() if _locked else direction_lock(task / ".round.lock"):
        require_resolved_runs(task)
        run.mkdir(parents=True, exist_ok=False)
        snapshot = run / "brief.md"
        snapshot.write_bytes(brief.read_bytes())
        brief = snapshot
        state = {"direction": direction, "run_id": run_id, "status": "running", "phases": {}}
        write_json(run / "run.json", state)
        deadline = time.monotonic() + timeout
        schema = run / "reply.schema.json"
        write_json(schema, Reply.model_json_schema())
        try:
            worker_blocked = False
            for phase in phases:
                if phase == "reviewer" and worker_blocked:
                    continue
                require_research(root)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Round deadline reached; preserve existing job state")
                role_name = "reviewer" if phase == "plan_review" else phase
                role = config["roles"][role_name]
                folder = run / phase
                folder.mkdir()
                output = folder / "reply.json"
                command = codex_command(root, role, output, schema)
                state["active_phase"] = phase
                state["phases"][phase] = {"requested_runtime": role, "status": "starting"}
                write_json(run / "run.json", state)
                dispatch = (
                    f"\nDirection: {direction}\nPhase: {phase}\n"
                    f"Brief: {brief.relative_to(root)}\nRun: {run.relative_to(root)}\n"
                    "Read the brief and earlier replies. Engine schema: "
                    "research/schemas/results.schema.json. Preserve authority, native gates, "
                    "paper and schedules. Return the reply schema.\n"
                )
                if len(dispatch.encode()) > 500:
                    raise ValueError("Dispatch exceeds the startup envelope")
                prompt = local_path(root, role["prompt"]).read_text() + dispatch
                admission = [
                    "python3",
                    str(root / "scripts/memory_budget.py"),
                    "admit",
                    "--kind",
                    "agent",
                ]
                if execute_fn is execute:
                    subprocess.run(admission, check=True, cwd=root, timeout=30)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Round deadline reached during admission")
                wrapped = [
                    str(root / "scripts/run_capped.sh"),
                    "--mem",
                    config["agent_memory"],
                    "--wait-min",
                    "0",
                    "--",
                    *command,
                ]
                transport = execute_fn(wrapped, prompt, folder, remaining)
                state["phases"][phase].update(transport)
                write_json(run / "run.json", state)
                if transport["exit_code"]:
                    raise RuntimeError(f"Agent exited {transport['exit_code']}; inspect {folder}")
                reply = Reply.model_validate_json(output.read_text())
                state["phases"][phase]["checkpoint"] = reply.checkpoint
                write_json(run / "run.json", state)
                if (
                    reply.checkpoint is not None
                    and not local_path(root, reply.checkpoint).is_file()
                ):
                    raise ValueError("Claimed checkpoint does not exist")
                if reply.next_brief is not None:
                    next_path = local_path(root, reply.next_brief)
                    if not next_path.is_file() or not 0 < next_path.stat().st_size <= 1000:
                        raise ValueError("Next brief is missing or oversized")
                if reply.results is not None:
                    validate_results(root, reply.results, direction)
                    if phase == "worker":
                        snapshot = folder / "results.json"
                        snapshot.write_bytes(local_path(root, reply.results).read_bytes())
                        state["phases"][phase]["results_snapshot"] = str(snapshot.relative_to(root))
                if phase == "worker" and reply.status == "complete" and reply.results is None:
                    raise ValueError("A completed worker must point to engine results")
                if phase == "lead" and reply.status == "complete":
                    if reply.decision not in ("continue", "repair", "branch", "park"):
                        raise ValueError("Lead must choose continue/repair/branch/park")
                    if reply.decision != "park" and reply.next_brief is None:
                        raise ValueError("Continuing work requires a concrete next brief")
                state["phases"][phase].update(reply.model_dump())
                write_json(run / "run.json", state)
                if phase == "plan_review" and (
                    reply.status != "complete" or reply.decision != "accept"
                ):
                    state["status"] = "scope_needs_revision"
                    break
                if phase == "worker":
                    worker_blocked = reply.status == "blocked"
            else:
                state["status"] = "round_finished"
            state["finished"] = datetime.now(UTC).isoformat()
            state["active_phase"] = None
            write_json(run / "run.json", state)
            lead = state["phases"].get("lead")
            if lead:
                # Board is a compact index. Full evidence/usage stays in this run.
                with (root / "board.md").open("a") as board:
                    fcntl.flock(board, fcntl.LOCK_EX)
                    board.write(
                        f"| {run_id} | {direction} | {lead['decision']} | "
                        f"{run.relative_to(root)}/run.json |\n"
                    )
            return state
        except BaseException as exc:
            state.update(
                status="interrupted_or_failed",
                error=str(exc),
                finished=datetime.now(UTC).isoformat(),
            )
            write_json(run / "run.json", state)
            raise


def run_series(
    root: Path,
    direction: str,
    run_id: str,
    timeout: float,
    *,
    review_plan: bool = False,
    execute_fn=execute,
) -> dict:
    """Follow same-direction continue/repair decisions within one caller deadline.

    A branch, blocker, pause, failure or exhausted wall-clock envelope returns a
    durable handoff. No timer, automatic retry or owner-question loop is created.
    """
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    if len(run_id) > 40 or timeout <= 0:
        raise ValueError("Series needs a run id <=40 characters and a positive timeout")
    require_research(root)
    task = local_path(root, f"research/{direction}")
    with direction_lock(task / ".round.lock"):
        runs = task / "runs"
        runs.mkdir(exist_ok=True)
        record = runs / f"{run_id}-series.json"
        with record.open("x") as output:
            output.write("{}\n")
        series = {"status": "running", "rounds": [], "next_brief": None}
        deadline = time.monotonic() + timeout
        brief_name = None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    series["status"] = "deadline_checkpoint"
                    break
                number = len(series["rounds"]) + 1
                name = f"{run_id}-{number}"
                series["active_round"] = name
                write_json(record, series)
                result = run_round(
                    root,
                    direction,
                    name,
                    remaining,
                    review_plan=review_plan and number == 1,
                    execute_fn=execute_fn,
                    brief_name=brief_name,
                    _locked=True,
                )
                series["rounds"].append(str((runs / name / "run.json").relative_to(root)))
                lead = result["phases"].get("lead", {})
                series["next_brief"] = lead.get("next_brief")
                worker = result["phases"].get("worker", {})
                if worker.get("checkpoint") or worker.get("status") == "blocked":
                    series["status"] = "blocked_checkpoint"
                    break
                if lead.get("status") != "complete" or lead.get("decision") not in (
                    "continue",
                    "repair",
                ):
                    series["status"] = "decision_handoff"
                    break
                brief_name = lead["next_brief"]
                if not local_path(root, brief_name).is_relative_to(task):
                    series["status"] = "new_direction_handoff"
                    break
                write_json(record, series)
            series["active_round"] = None
            write_json(record, series)
            return series
        except BaseException as exc:
            series.update(status="interrupted_or_failed", error=str(exc))
            write_json(record, series)
            raise
