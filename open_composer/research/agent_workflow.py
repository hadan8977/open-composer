"""Finite research rounds; file contracts are independent of the agent provider.

This coordinates agents, not financial simulation or broker operations. Existing
engines and scientific contracts remain responsible for numerical evidence.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager, nullcontext, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WORKFLOW_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["complete", "blocked"]
    summary: str = Field(min_length=1)
    decision: Literal["accept", "revise", "continue", "repair", "branch", "park", "none"]
    results: str | None
    next_brief: str | None
    checkpoint: str | None = Field(
        description="Unresolved blocker evidence; null for a completed review or result."
    )
    next_review: Literal["reuse", "plan", "result", "both"] = "reuse"


class ReplyFormatError(ValueError):
    """A correctable reply contract issue, not a failed engine/evidence validation."""


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


def codex_command(
    root: Path, role: dict, output: Path, schema: Path, *, session: str | None = None
) -> list[str]:
    """Only this boundary is provider-specific; Claude is not enabled implicitly."""
    if role["provider"] != "codex":
        raise ValueError("Only Codex is implemented; add and verify a provider adapter first")
    prefix = (
        ["codex", "exec", "resume", "--dangerously-bypass-approvals-and-sandbox"]
        if session
        else ["codex", "exec", "--cd", str(root), "--sandbox", "danger-full-access"]
    )
    return [
        *prefix,
        "--model",
        role["model"],
        "-c",
        'approval_policy="never"',
        "-c",
        f'model_reasoning_effort="{role["effort"]}"',
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output),
        *([session] if session else []),
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
    sessions, repeated = {}, set()
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
        identity = phase.get("session") or name
        if identity in sessions:
            repeated.add(identity)
        observed = sessions.setdefault(identity, {})
        for key, count in tokens.items():
            observed[key] = max(observed.get(key, 0), count)
    for observed in sessions.values():
        for key, count in observed.items():
            totals[key] = totals.get(key, 0) + count
    complete = bool(phases) and not missing and not unfinished and not repeated
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
        "sessions_with_multiple_records": sorted(repeated),
        "complete": complete,
        "scope": "All attempts, including Lead, failed and interrupted phases. Cached input is "
        "part of input. Gaps and repeated-session fieldwise maxima make observed totals a "
        "lower bound, not a full total.",
    }


def efficiency(root: Path, state: dict) -> dict:
    counts = Counts().model_dump()
    worker = state.get("latest_worker_phase", "worker")
    snapshot = state.get("phases", {}).get(worker, {}).get("results_snapshot")
    counts_error = None
    if snapshot:
        try:
            result = validate_results(root, snapshot, state["direction"])
            if result.counts is not None:
                counts = result.counts.model_dump()
        except (OSError, ValueError, TypeError) as exc:
            counts_error = type(exc).__name__
    wall_to_lead = None
    lead = state.get("phases", {}).get(latest_phase(state, "lead"), {})
    if lead.get("status") == "complete":
        try:
            received = datetime.fromisoformat(lead["started"]) + timedelta(
                seconds=lead["elapsed_seconds"]
            )
            seconds = (received - datetime.fromisoformat(state["started"])).total_seconds()
            wall_to_lead = seconds if seconds >= 0 else None
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
    return {
        "counts_validation_error": counts_error,
        "tokens": completed_tokens(state),
        "elapsed_seconds": state.get("elapsed_seconds"),
        "wall_seconds_to_lead": wall_to_lead,
        "time_scope": "elapsed_seconds sums active driver invocations; wall_seconds_to_lead "
        "includes gaps and detached computation until the latest completed Lead. "
        "A completed Lead response does not itself establish an accepted economic result.",
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
            folder = phase_folder(path.parent, phase_name, phase)
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
        worker = state.get("latest_worker_phase", "worker")
        snapshot = state.get("phases", {}).get(worker, {}).get("results_snapshot")
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
    lead_phase = state.get("latest_lead_phase", "lead")
    decision = state["phases"].get(lead_phase, {}).get("decision", state["status"])
    elapsed = metrics["elapsed_seconds"]
    duration = "?" if elapsed is None else f"{elapsed:.0f}"
    wall = metrics["wall_seconds_to_lead"]
    wall_text = "?" if wall is None else f"{wall:.0f}"
    line = (
        f"| {state['run_id']} | {state['direction']} | {decision} "
        f"executed E/A/F/V/P/D={count_text} tok={token_text} active_s={duration} "
        f"wall_s={wall_text} | "
        f"{run.relative_to(root)}/run.json |\n"
    )
    update_board(root, line, f"{run.relative_to(root)}/run.json")


def update_board(root: Path, line: str, evidence: str) -> None:
    """One current row per run; immutable attempts remain in its run directory."""
    with (root / "board.md").open("a+") as board:
        fcntl.flock(board, fcntl.LOCK_EX)
        board.seek(0)
        rows = board.readlines()
        rows = [row for row in rows if row.rstrip().split(" | ")[-1] != evidence + " |"]
        board.seek(0)
        board.truncate()
        board.write("".join(rows) + line)


def capacity_failure(folder: Path) -> bool:
    """Retry explicit transient provider capacity only, never quota/auth/general errors."""
    messages = []
    path = folder / "events.jsonl"
    if path.exists():
        with path.open() as events:
            for line in events:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") in ("error", "turn.failed"):
                    messages = [json.dumps(event)]
    path = folder / "stderr.log"
    if not messages and path.exists():
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 8000))
            messages.append(stream.read().decode(errors="replace"))
    message = "\n".join(messages).lower()
    if any(
        word in message for word in ("quota", "usage limit", "insufficient_quota", "unauthorized")
    ):
        return False
    return any(word in message for word in ("at capacity", "overloaded", "server_overloaded"))


@contextmanager
def direction_lock(path: Path):
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("This direction already has a running round") from exc
        yield


def phase_kind(name: str) -> str:
    return name.split("_resume_", 1)[0]


def latest_phase(state: dict, kind: str) -> str | None:
    names = [name for name in state.get("phases", {}) if phase_kind(name) == kind]
    return names[-1] if names else None


def phase_checkpoint(name: str, phase: dict) -> bool:
    # Legacy replies also put completed reports in this field. A successfully
    # validated complete Reply is authoritative about completion; the path stays
    # as evidence. Blocked, interrupted and invalid replies still block recovery.
    if phase_kind(name) in ("plan_review", "reviewer") and phase.get("status") == "complete":
        return phase.get("decision") != "accept"
    return phase.get("status") == "blocked" or bool(
        phase.get("checkpoint") and phase.get("status") != "complete"
    )


def has_checkpoint(state: dict) -> bool:
    phases = state.get("phases", {})
    for name, phase in phases.items():
        if not phase_checkpoint(name, phase):
            continue
        target = phase.get("resolved_by", "")
        resolved = phases.get(target, {})
        evidence = phase.get("resolution", {}).get("evidence")
        if not (
            target != name
            and phase_kind(target) == phase_kind(name)
            and resolved.get("status") == "complete"
            and not phase_checkpoint(target, resolved)
            and evidence
        ):
            return True
    return False


def phase_folder(run: Path, name: str, phase: dict) -> Path:
    # The first Martin recovery used worker/resume-N. Preserve those logs too.
    nested = run / name.replace("worker_resume_", "worker/resume-")
    return run / phase["folder"] if phase.get("folder") else nested


def phase_reply(root: Path, run: Path, name: str, phase: dict) -> Path:
    path = phase_folder(run, name, phase) / "reply.json"
    if not path.exists() and name.startswith("worker_resume_"):
        # Legacy task-local resume wrote one current reply into worker/.
        path = run / "worker/reply.json"
    reply = Reply.model_validate_json(path.read_text())
    if any(
        phase.get(key, "reuse" if key == "next_review" else None) != value
        for key, value in reply.model_dump().items()
    ):
        raise ValueError(f"Saved phase reply no longer matches: {name}")
    validate_reply(root, reply, phase_kind(name), run.parent.parent.name)
    return path


def require_local_stopped(run: Path, state: dict) -> None:
    for name, phase in state.get("phases", {}).items():
        path = phase_folder(run, name, phase) / "process.json"
        if not path.exists():
            continue
        pid = int(json.loads(path.read_text())["pid"])
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            continue
        raise ValueError(f"Local phase process group is still present: {name}, pid={pid}")


def resolve_prior_checkpoints(root: Path, run: Path, state: dict) -> None:
    """Retain each old block and bind its resolution to received role outputs."""
    lead_name = latest_phase(state, "lead")
    lead = state["phases"].get(lead_name, {})
    if (
        state.get("status") != "round_finished"
        or lead.get("status") != "complete"
        or phase_checkpoint(lead_name or "lead", lead)
    ):
        return
    for kind in ("plan_review", "worker", "reviewer", "lead"):
        current = latest_phase(state, kind)
        if current is None:
            continue
        phase = state["phases"][current]
        if phase.get("status") != "complete" or phase_checkpoint(current, phase):
            continue
        evidence = [str(phase_reply(root, run, current, phase).relative_to(root))]
        if kind == "worker":
            if not phase.get("results"):
                continue
            validate_results(root, phase["results"], state["direction"])
            evidence.append(phase["results"])
        evidence.append(str(phase_reply(root, run, lead_name, lead).relative_to(root)))
        if not all(local_path(root, name).is_file() for name in evidence):
            continue
        for name, prior in state["phases"].items():
            if name != current and phase_kind(name) == kind:
                if phase_checkpoint(name, prior):
                    prior["resolved_by"] = current
                    prior["resolution"] = {
                        "evidence": evidence,
                        "at_utc": datetime.now(UTC).isoformat(),
                        "reason": "Same-task recovery and independent Lead report no remaining "
                        "checkpoint",
                    }


def require_resolved_runs(task: Path) -> None:
    """A released lock is not proof that an interrupted job has stopped."""
    for path in (task / "runs").glob("*/run.json"):
        state = json.loads(path.read_text())
        # A local return code cannot establish whether a remote job is still live.
        unresolved = state.get("status") in ("running", "interrupted_or_failed")
        checkpoint = has_checkpoint(state)
        if (unresolved or checkpoint) and state.get("status") != "closed_after_recovery":
            raise ValueError(f"Reconcile unfinished job/checkpoint before a new start: {path}")


def reply_file(root: Path, name: str) -> Path:
    try:
        path = local_path(root, name)
        if not path.is_file():
            raise ValueError("file does not exist")
        return path
    except (OSError, ValueError) as exc:
        raise ReplyFormatError("Reply field must name one existing repository file") from exc


def validate_reply(root: Path, reply: Reply, kind: str, direction: str) -> None:
    if reply.checkpoint is not None:
        reply_file(root, reply.checkpoint)
    if reply.next_brief is not None:
        next_path = reply_file(root, reply.next_brief)
        if not 0 < next_path.stat().st_size <= 1000:
            raise ReplyFormatError("Next brief is missing or oversized")
    if reply.results is not None:
        reply_file(root, reply.results)
        validate_results(root, reply.results, direction)
    if kind == "worker" and reply.status == "complete" and reply.results is None:
        raise ReplyFormatError("A completed worker must point to engine results")
    if kind == "lead" and reply.status == "complete":
        if reply.decision not in ("continue", "repair", "branch", "park"):
            raise ReplyFormatError("Lead must choose continue/repair/branch/park")
        if reply.decision != "park" and reply.next_brief is None:
            raise ReplyFormatError("Continuing work requires a concrete next brief")


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
    resume: bool = False,
) -> dict:
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("A positive wall-clock timeout is required")
    task = local_path(root, f"research/{direction}")
    run = local_path(root, f"research/{direction}/runs/{run_id}")
    brief = (
        run / "brief.md"
        if resume
        else local_path(root, brief_name)
        if brief_name
        else task / "brief.md"
    )
    if not brief.is_file() or not 0 < brief.stat().st_size <= 1000:
        raise ValueError("A non-empty brief of at most 1000 bytes is required")
    require_research(root)
    config = json.loads((root / "research/workflow.json").read_text())
    with nullcontext() if _locked else direction_lock(task / ".round.lock"):
        started = time.monotonic()
        if resume:
            state = json.loads((run / "run.json").read_text())
            if state["direction"] != direction or state["run_id"] != run_id:
                raise ValueError("Saved run identity does not match")
            require_local_stopped(run, state)
            attempt = len(list(run.glob("before-resume-*.json"))) + 1
            archive = run / f"before-resume-{attempt}.json"
            with archive.open("x") as output:
                json.dump(state, output, ensure_ascii=False, indent=2)
            for name, prior in state["phases"].items():
                observed = read_events(phase_folder(run, name, prior))
                identities = {
                    identity
                    for identity in (
                        prior.get("session"),
                        prior.get("resumes_session"),
                        observed.get("session"),
                    )
                    if identity
                }
                if len(identities) > 1:
                    raise ValueError(f"Saved session conflicts with original event log: {name}")
                prior.update({key: value for key, value in observed.items() if value is not None})
            review_plan, review_result = state["review_plan"], state["review_result"]
            previous_elapsed = state.get("elapsed_seconds", 0)
            state.update(status="running", active_phase=None)
            state.pop("finished", None)
            state.pop("error", None)
        else:
            require_resolved_runs(task)
            run.mkdir(parents=True, exist_ok=False)
            snapshot = run / "brief.md"
            snapshot.write_bytes(brief.read_bytes())
            brief = snapshot
            previous_elapsed = 0
            state = {
                "direction": direction,
                "run_id": run_id,
                "status": "running",
                "started": datetime.now(UTC).isoformat(),
                "review_plan": review_plan,
                "review_result": review_result,
                "phases": {},
            }
        phases = (
            (["plan_review"] if review_plan else [])
            + ["worker"]
            + (["reviewer"] if review_result else [])
            + ["lead"]
        )
        state.setdefault("driver_invocations", []).append(
            {
                "started": datetime.now(UTC).isoformat(),
                "workflow_source_sha256": WORKFLOW_SOURCE_SHA256,
                "explicit_resume": resume,
            }
        )
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
            changed_upstream = False
            upstream = []
            for kind in phases:
                if kind == "reviewer" and worker_blocked:
                    continue
                prior_name = latest_phase(state, kind)
                prior = state["phases"].get(prior_name, {})
                # Dict order is retained in saved JSON, including legacy runs.
                # A completed upstream retry invalidates an older downstream
                # phase even if the driver died before creating its replacement.
                order = list(state["phases"])
                if prior and (
                    any(order.index(name) > order.index(prior_name) for name in upstream)
                    or ("depends_on" in prior and prior["depends_on"] != upstream)
                ):
                    changed_upstream = True
                reusable = (
                    prior.get("status") == "complete"
                    and not phase_checkpoint(prior_name or kind, prior)
                    and prior.get("exit_code") == 0
                )
                if kind == "plan_review":
                    reusable = reusable and prior.get("decision") == "accept"
                if resume and reusable and not changed_upstream:
                    phase_reply(root, run, prior_name, prior)
                    if kind == "worker" and not prior.get("results_snapshot"):
                        snapshot = phase_folder(run, prior_name, prior) / "results.json"
                        with snapshot.open("xb") as output:
                            output.write(local_path(root, prior["results"]).read_bytes())
                        prior["results_snapshot"] = str(snapshot.relative_to(root))
                    if kind in ("worker", "lead"):
                        state[f"latest_{kind}_phase"] = prior_name
                    upstream.append(prior_name)
                    continue
                recovery_reason = None
                capacity_retries = 0
                reply_repaired = any(
                    phase_kind(name) == kind and phase.get("automatic_recovery") == "reply_only"
                    for name, phase in state["phases"].items()
                )
                while True:
                    require_research(root)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Round deadline reached; preserve existing job state")
                    role_name = "reviewer" if kind == "plan_review" else kind
                    role = prior.get("requested_runtime", config["roles"][role_name])
                    session_to_resume = (
                        (prior.get("session") or prior.get("resumes_session"))
                        if prior and not changed_upstream
                        else None
                    )
                    if prior and not changed_upstream and not session_to_resume:
                        old_folder = phase_folder(run, prior_name, prior)
                        if (old_folder / "process.json").exists():
                            raise ValueError(
                                "Original session is unknown; reconcile its transport before retry"
                            )
                    phase = kind
                    if prior:
                        number = 1
                        while f"{kind}_resume_{number}" in state["phases"]:
                            number += 1
                        phase = f"{kind}_resume_{number}"
                    folder = run / phase
                    folder.mkdir()
                    output = folder / "reply.json"
                    command = codex_command(root, role, output, schema, session=session_to_resume)
                    state["active_phase"] = phase
                    state["phases"][phase] = {
                        "requested_runtime": role,
                        "status": "starting",
                        "started": datetime.now(UTC).isoformat(),
                        "folder": folder.name,
                        "resumes_phase": prior_name if session_to_resume else None,
                        "resumes_session": session_to_resume,
                        "depends_on": list(upstream),
                        "automatic_recovery": recovery_reason,
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
                    if resume or recovery_reason:
                        dispatch = (
                            f"\nPhase: {phase}\nBrief: {brief.relative_to(root)}\n"
                            f"Run: {run.relative_to(root)}\n"
                            "Resume saved task/session. Read run.json; reconcile jobs "
                            "and checkpoints first. Reuse outputs; no replay/provider swap. Keep "
                            "unresolved checkpoints. Return Reply; engine schema: "
                            "research/schemas/results.schema.json.\n"
                        )
                    if recovery_reason == "reply_only":
                        error_note = (
                            str(prior.get("error", "")).encode()[:80].decode(errors="ignore")
                        )
                        dispatch = (
                            f"\nRun: {run.relative_to(root)}\nBrief: brief.md (inside Run)\n"
                            "Correct Reply only: existing file paths or null. No numerical work, "
                            "evidence edits or job launches. Missing valid results means blocked. "
                            f"Validation: {error_note}\n"
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
                    if session_to_resume and session != session_to_resume:
                        raise ValueError("Recovery did not return the original session")
                    if session and any(
                        prior.get("session") == session
                        for name, prior in state["phases"].items()
                        if name != phase and (phase_kind(name) != kind or not session_to_resume)
                    ):
                        raise ValueError(
                            "Worker, Lead and review phases require independent sessions"
                        )
                    write_json(run / "run.json", state)
                    if transport["exit_code"]:
                        failure = f"Agent exited {transport['exit_code']}; inspect {folder}"
                        state["phases"][phase].update(status="interrupted_or_failed", error=failure)
                        if (
                            session
                            and capacity_failure(folder)
                            and capacity_retries < 2
                            and deadline - time.monotonic() > 30
                        ):
                            state["phases"][phase]["recovery_cause"] = "provider_capacity"
                            write_json(run / "run.json", state)
                            capacity_retries += 1
                            if recovery_reason != "reply_only":
                                recovery_reason = "provider_capacity"
                            prior_name, prior = phase, state["phases"][phase]
                            changed_upstream = False
                            time.sleep(30)
                            continue
                        raise RuntimeError(failure)
                    try:
                        try:
                            reply = Reply.model_validate_json(output.read_text())
                        except (OSError, ValueError) as exc:
                            raise ReplyFormatError(str(exc)) from exc
                        state["phases"][phase]["checkpoint"] = reply.checkpoint
                        write_json(run / "run.json", state)
                        validate_reply(root, reply, kind, direction)
                    except ReplyFormatError as exc:
                        state["phases"][phase].update(status="invalid_reply", error=str(exc))
                        write_json(run / "run.json", state)
                        if not session or reply_repaired or deadline - time.monotonic() <= 0:
                            raise
                        reply_repaired = True
                        recovery_reason = "reply_only"
                        prior_name, prior = phase, state["phases"][phase]
                        changed_upstream = False
                        continue
                    if kind == "worker" and reply.results is not None:
                        snapshot = folder / "results.json"
                        snapshot.write_bytes(local_path(root, reply.results).read_bytes())
                        state["phases"][phase]["results_snapshot"] = str(snapshot.relative_to(root))
                    state["phases"][phase].update(reply.model_dump())
                    if kind in ("worker", "lead"):
                        state[f"latest_{kind}_phase"] = phase
                    state["active_phase"] = None
                    write_json(run / "run.json", state)
                    break
                if kind == "plan_review" and (
                    reply.status != "complete" or reply.decision != "accept"
                ):
                    state["status"] = "scope_needs_revision"
                    break
                if kind == "worker":
                    worker_blocked = reply.status == "blocked"
                upstream.append(phase)
                changed_upstream = True
            else:
                state["status"] = "round_finished"
            state["finished"] = datetime.now(UTC).isoformat()
            state["active_phase"] = None
            resolve_prior_checkpoints(root, run, state)
            state["elapsed_seconds"] = previous_elapsed + time.monotonic() - started
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
            state["elapsed_seconds"] = previous_elapsed + time.monotonic() - started
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
    resume: bool = False,
) -> dict:
    root = root.resolve()
    identifier(direction)
    identifier(run_id)
    runs = local_path(root, f"research/{direction}/runs")
    require_research(root)
    runs.mkdir(exist_ok=True)
    with direction_lock(runs / f"{run_id}-series.lock"):
        return _run_series(
            root,
            direction,
            run_id,
            timeout,
            review_plan=review_plan,
            review_result=review_result,
            execute_fn=execute_fn,
            resume=resume,
        )


def prepare_pending_round(
    root: Path, saved_run: Path, pending: dict, original: str
) -> tuple[str, bool, bool]:
    """Called under the direction lock; retain any provably unstarted partial."""
    if pending.get("run") != original:
        raise ValueError("Unstarted round lacks its original pending dispatch")
    brief = pending["brief"]
    if local_path(root, brief).read_text() != pending["brief_text"]:
        raise ValueError("Pending brief changed before its first launch")
    folder = saved_run.parent
    if folder.exists():
        if any(
            p.name not in ("brief.md", "run.json.tmp") or not p.is_file() or p.is_symlink()
            for p in folder.iterdir()
        ):
            raise ValueError("Unstarted round has unexplained artifacts; reconcile first")
        snapshot = folder / "brief.md"
        if snapshot.exists() and snapshot.read_text() != pending["brief_text"]:
            raise ValueError("Partial round brief differs from its pending dispatch")
        temporary = folder / "run.json.tmp"
        if temporary.exists() and json.loads(temporary.read_text()).get("phases") != {}:
            raise ValueError("Partial state does not establish an unstarted round")
        folder.rename(folder.with_name(f"{folder.name}-unstarted-{time.time_ns()}"))
    return brief, pending["review_plan"], pending["review_result"]


def _run_series(
    root: Path,
    direction: str,
    run_id: str,
    timeout: float,
    *,
    review_plan: bool = False,
    review_result: bool = False,
    execute_fn=execute,
    resume: bool = False,
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
    existing_run = None
    if resume:
        series = json.loads(record.read_text())
        existing_run = series.get("active_round")
        if existing_run and "/" not in existing_run:
            existing_run = f"research/{direction}/runs/{existing_run}/run.json"
        if not existing_run and series.get("rounds"):
            existing_run = series["rounds"][-1]
        if not existing_run:
            raise ValueError("Series has no saved round to resume")
        saved_path = local_path(root, existing_run)
        if saved_path.exists():
            with direction_lock(saved_path.parent.parent.parent / ".round.lock"):
                require_local_stopped(saved_path.parent, json.loads(saved_path.read_text()))
        archive = record.with_name(f"{record.stem}-resume-{time.time_ns()}.json")
        with archive.open("x") as output:
            json.dump(series, output, ensure_ascii=False, indent=2)
        series.update(status="running")
        series.pop("error", None)
    else:
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
            recovering = existing_run is not None
            pending_recovery = False
            if recovering:
                parts = local_path(root, existing_run).relative_to(root).parts
                if len(parts) != 5 or parts[0] != "research" or parts[2] != "runs":
                    raise ValueError("Series recovery needs an original research run")
                direction, name = identifier(parts[1]), identifier(parts[3])
                series["active_round"] = existing_run
                saved_run = local_path(root, existing_run)
                pending_recovery = not saved_run.exists()
            else:
                number = len(series["rounds"]) + 1
                name = f"{run_id}-{number}"
                series["active_round"] = f"research/{direction}/runs/{name}/run.json"
                pending_brief = brief_name or f"research/{direction}/brief.md"
                series["pending_dispatch"] = {
                    "run": series["active_round"],
                    "brief": pending_brief,
                    "brief_text": local_path(root, pending_brief).read_text(),
                    "review_plan": review_plan,
                    "review_result": review_result,
                }
            # Keep the same series and record attempts before launch.
            if series["active_round"] not in series["rounds"]:
                series["rounds"].append(series["active_round"])
            write_json(record, series)
            lock = (
                direction_lock(local_path(root, f"research/{direction}/.round.lock"))
                if pending_recovery
                else nullcontext()
            )
            with lock:
                if pending_recovery and not saved_run.exists():
                    pending = series.get("pending_dispatch", {})
                    brief_name, review_plan, review_result = prepare_pending_round(
                        root, saved_run, pending, existing_run
                    )
                    recovering = False
                result = run_round(
                    root,
                    direction,
                    name,
                    deadline - time.monotonic(),
                    review_plan=review_plan,
                    review_result=review_result,
                    execute_fn=execute_fn,
                    brief_name=brief_name,
                    resume=recovering,
                    _locked=pending_recovery,
                )
            existing_run = None
            lead = result["phases"].get(latest_phase(result, "lead"), {})
            series["next_brief"] = lead.get("next_brief")
            if has_checkpoint(result):
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
