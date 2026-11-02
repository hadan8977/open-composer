"""Finite research rounds; file contracts are independent of the agent provider.

This coordinates agents, not financial simulation or broker operations. Existing
engines and scientific contracts remain responsible for numerical evidence.
"""

from __future__ import annotations

import fcntl
import json
import math
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
    next_review: Literal["reuse", "plan", "result", "both"] = "reuse"


class Counts(BaseModel):
    """Engine execution counts, not accepted conclusions; omitted counts are unknown."""

    model_config = ConfigDict(extra="forbid")
    economic_comparisons: int | None = Field(default=None, ge=0, strict=True)
    financial_accounts: int | None = Field(default=None, ge=0, strict=True)
    model_fits: int | None = Field(default=None, ge=0, strict=True)
    variants: int | None = Field(default=None, ge=0, strict=True)
    paper_candidates: int | None = Field(default=None, ge=0, strict=True)
    diagnostic_steps: int | None = Field(default=None, ge=0, strict=True)


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
    counts: Counts | None = None
    counts_artifact: str | None = None

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
    if result.counts is not None:
        if result.counts_artifact not in result.source_artifacts:
            raise ValueError("Counts require a named independent engine source artifact")
        source = json.loads(local_path(root, result.counts_artifact).read_text())
        if not isinstance(source, dict):
            raise ValueError("Count artifact must contain a counts object")
        if Counts.model_validate(source.get("counts")).model_dump() != result.counts.model_dump():
            raise ValueError("Counts must match the engine artifact's counts object")
        if result.counts.economic_comparisons and (
            result.kind != "financial" or result.baseline_net_profit_usd is None
        ):
            raise ValueError("Economic comparisons require costed financial and baseline results")
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
    return {**read_events(folder), "exit_code": process.returncode}


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")


def read_events(folder: Path) -> dict:
    """Read successful turns even if the transport later failed or was interrupted."""
    usage, session, incomplete, missing = None, None, False, False
    events_path = folder / "events.jsonl"
    if events_path.exists():
        with events_path.open() as events:
            for line in events:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "thread.started":
                    session = event.get("thread_id")
                elif event.get("type") == "turn.started":
                    incomplete = True
                elif event.get("type") == "turn.completed":
                    incomplete = False
                    observed = token_values(event.get("usage"))
                    missing = missing or len(observed) != len(TOKEN_FIELDS)
                    if observed:
                        usage = usage or {}
                        for key, count in observed.items():
                            usage[key] = usage.get(key, 0) + count
    result = {"session": session, "usage": usage}
    if incomplete or missing:
        result["usage_incomplete"] = True
    return result


def token_values(usage: dict | None) -> dict:
    return {
        key: usage[key]
        for key in TOKEN_FIELDS
        if isinstance(usage, dict)
        and isinstance(usage.get(key), int)
        and not isinstance(usage[key], bool)
        and usage[key] >= 0
    }


def completed_tokens(state: dict) -> dict:
    """All attempted phases, including Lead; observed partial usage is a lower bound."""
    phases, totals, missing, unfinished = {}, {}, [], []
    for name, phase in state.get("phases", {}).items():
        if not isinstance(phase, dict):
            continue
        tokens = token_values(phase.get("usage"))
        phases[name] = tokens
        if len(tokens) != len(TOKEN_FIELDS):
            missing.append(name)
        if phase.get("usage_incomplete") or (
            phase.get("exit_code") is None and phase.get("status") not in ("complete", "blocked")
        ):
            unfinished.append(name)
        for key, count in tokens.items():
            totals[key] = totals.get(key, 0) + count
    complete = bool(phases) and not missing and not unfinished
    observed_total = (
        totals.get("input_tokens", 0) + totals.get("output_tokens", 0)
        if "input_tokens" in totals or "output_tokens" in totals
        else None
    )
    return {
        "source": "run.json all-phase usage events",
        "by_phase": phases,
        "observed_totals": totals,
        "observed_total_tokens": observed_total,
        "total_tokens": observed_total if complete else None,
        "phases_with_missing_fields": missing,
        "unfinished_phases": unfinished,
        "complete": complete,
        "scope": "All attempts, including Lead, failed and interrupted phases. Cached input is "
        "part of input. Gaps make observed totals a lower bound, not a full total.",
    }


def efficiency(root: Path, state: dict) -> dict:
    counts = Counts().model_dump()
    snapshot = state.get("phases", {}).get("worker", {}).get("results_snapshot")
    counts_error = None
    if snapshot:
        try:
            result = validate_results(root, snapshot, state["direction"])
            if result.counts is not None:
                counts = result.counts.model_dump()
        except (OSError, ValueError, TypeError) as exc:
            counts_error = type(exc).__name__
    return {
        "counts_validation_error": counts_error,
        "tokens": completed_tokens(state),
        "elapsed_seconds": state.get("elapsed_seconds"),
        "counts": counts,
        "accepted_economic_conclusions": None,
        "counts_scope": "Explicit engine execution counts, including comparisons later rejected. "
        "Accepted economic conclusions require the existing independent result reception and are "
        "not inferred automatically. Unknown is not zero; execution is not profitability or "
        "paper readiness.",
    }


def summarize_runs(root: Path) -> dict:
    """Read saved attempts, including failed runs and retries; never read account limits."""
    rows, totals, sessions, duplicate_sessions = [], {}, {}, set()
    count_totals, count_unknown, seen_counts = {}, {}, set()
    elapsed, elapsed_unknown, gaps = 0.0, 0, []
    for path in sorted((root / "research").glob("*/runs/*/run.json")):
        state = json.loads(path.read_text())
        # Old interrupted runs can have usable events absent from their final run.json.
        for phase_name, phase in state.get("phases", {}).items():
            folder = path.parent / phase_name
            if (folder / "events.jsonl").exists():
                observed = read_events(folder)
                for key, value in observed.items():
                    if value is not None:
                        phase[key] = value
        metrics = efficiency(root, state)
        name = str(path.relative_to(root))
        if not metrics["tokens"]["complete"]:
            gaps.append(name)
        for phase_name, phase in state.get("phases", {}).items():
            key = phase.get("session") or f"{name}/{phase_name}"
            tokens = token_values(phase.get("usage"))
            if key in sessions:
                # Historical records may repeat a resumed session's cumulative usage.
                # Without turn identities, max is a conservative observed lower bound.
                duplicate_sessions.add(key)
                for field, value in tokens.items():
                    sessions[key][field] = max(sessions[key].get(field, 0), value)
            else:
                sessions[key] = tokens
        snapshot = state.get("phases", {}).get("worker", {}).get("results_snapshot")
        evidence = None
        if snapshot and local_path(root, snapshot).is_file():
            evidence = json.loads(local_path(root, snapshot).read_text()).get("counts_artifact")
        duplicate_counts = evidence is not None and evidence in seen_counts
        if evidence is not None:
            seen_counts.add(evidence)
        for field, value in metrics["counts"].items():
            if value is None or duplicate_counts:
                count_unknown[field] = count_unknown.get(field, 0) + 1
            else:
                count_totals[field] = count_totals.get(field, 0) + value
        seconds = metrics["elapsed_seconds"]
        if seconds is None:
            elapsed_unknown += 1
        else:
            elapsed += seconds
        rows.append({"run": name, "status": state.get("status"), "efficiency": metrics})
    for tokens in sessions.values():
        for field, value in tokens.items():
            totals[field] = totals.get(field, 0) + value
    observed_total = (
        totals.get("input_tokens", 0) + totals.get("output_tokens", 0)
        if "input_tokens" in totals or "output_tokens" in totals
        else None
    )
    return {
        "run_count": len(rows),
        "tokens": {
            "observed_totals": totals,
            "observed_total_tokens": observed_total,
            "total_tokens": observed_total if not gaps and not duplicate_sessions else None,
            "runs_with_gaps": gaps,
            "sessions_with_multiple_records": sorted(duplicate_sessions),
        },
        "counts": {
            field: {
                "observed": count_totals.get(field),
                "runs_unknown": count_unknown.get(field, 0),
            }
            for field in Counts.model_fields
        },
        "elapsed_seconds": {
            "observed": elapsed if len(rows) > elapsed_unknown else None,
            "runs_unknown": elapsed_unknown,
        },
        "accepted_economic_conclusions": None,
        "scope": "All saved runs including failures/retries. Missing usage and repeated sessions "
        "make totals lower bounds; repeated sessions use fieldwise maxima to avoid counting a "
        "cumulative record twice. Reused count artifacts are not counted twice. Cached tokens are "
        "already input. Comparisons count execution, not accepted conclusions; consult existing "
        "independent reception. Account percentages are not project cost.",
        "by_run": rows,
    }


def finalize_metrics(root: Path, run: Path, state: dict) -> None:
    state["efficiency"] = efficiency(root, state)
    write_json(run / "run.json", state)
    # Account observation stays immutable; only recompute the local token projection.
    usage_path = run / "usage.json"
    if usage_path.exists():
        usage = json.loads(usage_path.read_text())
        usage["completed_phase_tokens"] = state["efficiency"]["tokens"]
        write_json(usage_path, usage)
    metrics = state["efficiency"]
    counts = metrics["counts"]
    token_summary = metrics["tokens"]
    tokens = token_summary["observed_total_tokens"]
    token_text = "?" if tokens is None else str(tokens)
    if tokens is not None and not token_summary["complete"]:
        token_text += "+?"
    count_text = "/".join("?" if n is None else str(n) for n in counts.values())
    decision = state["phases"].get("lead", {}).get("decision", state["status"])
    elapsed = metrics["elapsed_seconds"]
    duration = "?" if elapsed is None else f"{elapsed:.0f}"
    line = (
        f"| {state['run_id']} | {state['direction']} | {decision} "
        f"executed E/A/F/V/P/D={count_text} tok={token_text} s={duration} | "
        f"{run.relative_to(root)}/run.json |\n"
    )
    with (root / "board.md").open("a") as board:
        fcntl.flock(board, fcntl.LOCK_EX)
        board.write(line)


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
        checkpoint = any(
            phase.get("checkpoint") or phase.get("status") == "blocked" for phase in phases.values()
        )
        if (unresolved or checkpoint) and state.get("status") != "closed_after_recovery":
            raise ValueError(f"Reconcile unfinished job/checkpoint before a new start: {path}")


def run_round(
    root: Path,
    direction: str,
    run_id: str,
    timeout: float,
    *,
    review_plan: bool = False,
    review_result: bool = False,
    execute_fn=execute,
    brief_name: str | None = None,
    _locked: bool = False,
) -> dict:
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("A positive wall-clock timeout is required")
    task = local_path(root, f"research/{direction}")
    brief = local_path(root, brief_name) if brief_name else task / "brief.md"
    if not brief.is_file() or not 0 < brief.stat().st_size <= 1000:
        raise ValueError("A non-empty brief of at most 1000 bytes is required")
    require_research(root)
    config = json.loads((root / "research/workflow.json").read_text())
    phases = (
        (["plan_review"] if review_plan else [])
        + ["worker"]
        + (["reviewer"] if review_result else [])
        + ["lead"]
    )
    run = local_path(root, f"research/{direction}/runs/{run_id}")
    with nullcontext() if _locked else direction_lock(task / ".round.lock"):
        require_resolved_runs(task)
        run.mkdir(parents=True, exist_ok=False)
        snapshot = run / "brief.md"
        snapshot.write_bytes(brief.read_bytes())
        brief = snapshot
        started = time.monotonic()
        state = {
            "direction": direction,
            "run_id": run_id,
            "status": "running",
            "started": datetime.now(UTC).isoformat(),
            "review_plan": review_plan,
            "review_result": review_result,
            "phases": {},
        }
        write_json(run / "run.json", state)
        deadline = time.monotonic() + timeout
        schema = run / "reply.schema.json"
        dispatch_schema = Reply.model_json_schema()
        # Strict provider output requires all keys; old saved replies still parse.
        dispatch_schema["required"] = list(dispatch_schema["properties"])
        dispatch_schema["properties"]["next_review"].pop("default", None)
        write_json(schema, dispatch_schema)
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
                state["phases"][phase] = {
                    "requested_runtime": role,
                    "status": "starting",
                    "started": datetime.now(UTC).isoformat(),
                }
                phase_started = time.monotonic()
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
                try:
                    transport = execute_fn(wrapped, prompt, folder, remaining)
                    state["phases"][phase].update(transport)
                finally:
                    state["phases"][phase]["elapsed_seconds"] = time.monotonic() - phase_started
                    if (folder / "events.jsonl").exists():
                        state["phases"][phase].update(read_events(folder))
                session = state["phases"][phase].get("session")
                if session and any(
                    prior.get("session") == session
                    for name, prior in state["phases"].items()
                    if name != phase
                ):
                    raise ValueError("Worker, Lead and review phases require independent sessions")
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
            state["elapsed_seconds"] = time.monotonic() - started
            finalize_metrics(root, run, state)
            return state
        except BaseException as exc:
            state.update(
                status="interrupted_or_failed",
                error=str(exc),
                finished=datetime.now(UTC).isoformat(),
            )
            active = state.get("active_phase")
            if active:
                state["phases"][active]["status"] = "interrupted_or_failed"
                state["phases"][active]["usage_incomplete"] = True
            state["elapsed_seconds"] = time.monotonic() - started
            finalize_metrics(root, run, state)
            raise


def run_series(
    root: Path,
    direction: str,
    run_id: str,
    timeout: float,
    *,
    review_plan: bool = False,
    review_result: bool = False,
    execute_fn=execute,
) -> dict:
    """Follow concrete authorized briefs across directions until a real stop.

    Review selection follows scientific scope, not directory identity. Checkpoints,
    blockers, pauses and transport failures stop without replaying existing jobs.
    """
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    if len(run_id) > 40 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Series needs a run id <=40 characters and a positive timeout")
    require_research(root)
    task = local_path(root, f"research/{direction}")
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
            series["active_round"] = f"research/{direction}/runs/{name}/run.json"
            # Record attempts before launch so a failed final round is never dropped.
            series["rounds"].append(series["active_round"])
            write_json(record, series)
            result = run_round(
                root,
                direction,
                name,
                remaining,
                review_plan=review_plan,
                review_result=review_result,
                execute_fn=execute_fn,
                brief_name=brief_name,
            )
            lead = result["phases"].get("lead", {})
            series["next_brief"] = lead.get("next_brief")
            if any(
                phase.get("checkpoint") or phase.get("status") == "blocked"
                for phase in result["phases"].values()
            ):
                series["status"] = "blocked_checkpoint"
                break
            if lead.get("status") != "complete" or not lead.get("next_brief"):
                series["status"] = "decision_handoff"
                break
            brief_name = lead["next_brief"]
            parts = local_path(root, brief_name).relative_to(root).parts
            if len(parts) < 3 or parts[0] != "research":
                raise ValueError("Next brief must belong to research/<direction>/")
            direction = identifier(parts[1])
            review = lead.get("next_review", "reuse")
            review_plan, review_result = review in ("plan", "both"), review in ("result", "both")
            series["next_review"] = review
            write_json(record, series)
        series["active_round"] = None
        write_json(record, series)
        return series
    except BaseException as exc:
        series.update(status="interrupted_or_failed", error=str(exc))
        write_json(record, series)
        raise
