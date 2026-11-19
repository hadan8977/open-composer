"""Finite research rounds; file contracts are independent of the agent provider.

This coordinates agents, not financial simulation or broker operations. Existing
engines and scientific contracts remain responsible for numerical evidence.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from open_composer.research.event_wait import (
    WaitSpec,
    bind_wait,
    checkpoint_status,
    wait_event,
)
from open_composer.research.file_lock import lock_file
from open_composer.research.platform_runtime import capped_command, native_process
from open_composer.research.process_identity import identity, process_state


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
    wait: WaitSpec | None = None
    round_class: Literal["new_money_evidence", "informative_learning", "no_information"] | None = (
        Field(default=None, description="Lead only: what the completed round delivered.")
    )
    accepted_conclusions: list[str] | None = Field(
        default=None,
        description="Lead only: after-cost economic conclusions accepted this round; [] for none.",
    )


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
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_results(root: Path, name: str, direction: str) -> Results:
    path = local_path(root, name)
    result = Results.model_validate_json(path.read_text(encoding="utf-8"))
    if result.direction != direction:
        raise ValueError("Result direction does not match the assignment")
    for artifact in result.source_artifacts:
        source = local_path(root, artifact)
        if source == path or not source.is_file():
            raise ValueError(f"Missing independent engine artifact: {artifact}")
    if result.counts is not None:
        if result.counts_artifact not in result.source_artifacts:
            raise ValueError("Counts require a named independent engine source artifact")
        source = json.loads(local_path(root, result.counts_artifact).read_text(encoding="utf-8"))
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
    control = json.loads((root / "control.json").read_text(encoding="utf-8"))
    if control.get("draft") is not False or control.get("research") is not True:
        raise ValueError("Research has not been enabled in installed control.json")
    legacy = root / "reports/research/control/owner-compute-hold.json"
    if legacy.exists():
        hold = json.loads(legacy.read_text(encoding="utf-8"))
        if hold.get("research_paused") or any(
            hold.get(key) is False for key in ("research_allowed", "research_new_starts_allowed")
        ):
            raise ValueError("Legacy research hold remains active; reconcile authority first")


PROVIDERS = ("codex", "claude", "pi")


def codex_command(
    root: Path, role: dict, output: Path, schema: Path, *, session: str | None = None
) -> list[str]:
    """Codex adapter: JSON events, provider-enforced Reply schema, file output."""
    if role["provider"] != "codex":
        raise ValueError("This is the Codex adapter; dispatch by provider instead")
    prefix = (
        ["codex", "exec", "resume", "--dangerously-bypass-approvals-and-sandbox"]
        if session
        else ["codex", "exec", "--cd", str(root), "--sandbox", "danger-full-access"]
    )
    # The repo's own .codex/hooks.json (rules at start, one self-review at stop).
    prefix.append("--dangerously-bypass-hook-trust")
    return [
        *prefix,
        "--model",
        role["model"],
        "-c",
        'approval_policy="never"',
        "-c",
        f'model_reasoning_effort="{role["effort"]}"',
        # Every stored tool output is resent on each later turn; keep it small.
        "-c",
        "tool_output_token_limit=4000",
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output),
        *([session] if session else []),
        "-",
    ]


def claude_command(
    root: Path, role: dict, output: Path, schema: Path | dict, *, session: str | None = None
) -> list[str]:
    """Claude Code print mode with the documented structured-output boundary.

    The Reply arrives in the stream-json `result` event as `structured_output`,
    so the driver materializes reply.json itself. `env -C` keeps relative paths
    (brief, run, prompts) and the resume scope inside the repository; Claude
    stores sessions per working directory.
    """
    if role["provider"] != "claude":
        raise ValueError("This is the Claude adapter; dispatch by provider instead")
    document = (
        schema if isinstance(schema, dict) else json.loads(schema.read_text(encoding="utf-8"))
    )
    dispatch_schema = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    session_args = ["--resume", session] if session else ["--session-id", str(uuid.uuid4())]
    return [
        "env",
        "-C",
        str(root),
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        role["model"],
        "--effort",
        role["effort"],
        "--permission-mode",
        "bypassPermissions",
        "--json-schema",
        dispatch_schema,
        *session_args,
    ]


PI_APPEND = (
    "Your final message must be exactly one JSON object that validates against "
    "the Reply schema below. No prose, no markdown fences, no tool calls in that "
    "final message.\n"
)


def pi_command(
    root: Path, role: dict, output: Path, schema: Path | dict, *, session: str | None = None
) -> list[str]:
    """pi print mode with the project context, a resumable session and the Reply schema.

    pi has no provider-enforced structured output. The schema is appended to the
    system prompt and the driver reads the final assistant JSON itself. `env -C`
    keeps the repository scan root and pi's per-directory session storage stable.
    """
    if role["provider"] != "pi":
        raise ValueError("This is the pi adapter; dispatch by provider instead")
    document = (
        schema if isinstance(schema, dict) else json.loads(schema.read_text(encoding="utf-8"))
    )
    dispatch_schema = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    return [
        "env",
        "-C",
        str(root),
        "pi",
        "-p",
        "--mode",
        "json",
        "--model",
        role["model"],
        "--thinking",
        role["effort"],
        "--approve",
        "--no-extensions",
        "--no-mcp",
        "--no-skills",
        "--no-prompt-templates",
        "--append-system-prompt",
        PI_APPEND + dispatch_schema,
        "--session-id",
        session or str(uuid.uuid4()),
    ]


def agent_command(
    root: Path, role: dict, output: Path, schema: Path | dict, *, session: str | None = None
) -> list[str]:
    """One provider boundary; everything else is provider-independent."""
    provider = role.get("provider")
    if provider == "codex":
        return codex_command(root, role, output, schema, session=session)
    if provider == "claude":
        return claude_command(root, role, output, schema, session=session)
    if provider == "pi":
        return pi_command(root, role, output, schema, session=session)
    raise ValueError(f"Unsupported provider {provider!r}; add and verify a provider adapter first")


def reply_dispatch_schema() -> dict:
    """Strict provider output requires all keys; old saved replies still parse."""
    schema = Reply.model_json_schema()
    schema["required"] = list(schema["properties"])
    schema["properties"]["next_review"].pop("default", None)
    schema["properties"]["wait"].pop("default", None)
    for optional in ("round_class", "accepted_conclusions"):
        schema["properties"][optional].pop("default", None)
    for definition in schema.get("$defs", {}).values():
        if definition.get("type") == "object":
            definition["required"] = list(definition.get("properties", {}))
            for prop in definition.get("properties", {}).values():
                prop.pop("default", None)
    return schema


def execute(command: list[str], prompt: str, folder: Path, timeout: float) -> dict:
    """Run one agent process tree; kill the whole tree on timeout or interruption."""
    native = os.name == "nt"
    with (
        (folder / "events.jsonl").open("w", encoding="utf-8") as events,
        (folder / "stderr.log").open("w", encoding="utf-8") as err,
    ):
        kwargs = dict(stdin=subprocess.PIPE, stdout=events, stderr=err, text=True, encoding="utf-8")
        process = (
            native_process(command, Path(__file__).resolve().parents[2], **kwargs)
            if native
            else subprocess.Popen(command, start_new_session=True, **kwargs)
        )
        with process:
            try:
                write_json(
                    folder / "process.json",
                    {
                        **identity(process.pid),
                        "started": datetime.now(UTC).isoformat(),
                        "phase": folder.name,
                        "run": folder.parent.name,
                    },
                )
                process.communicate(prompt, timeout=timeout)
            except BaseException:
                if native:
                    process.kill()  # the whole job
                else:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                raise
    transport = {**read_events(folder), "exit_code": process.returncode}
    write_json(folder / "transport.json", transport)
    return transport


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")


def read_events(folder: Path) -> dict:
    """Read successful turns even if the transport later failed or was interrupted.

    Handles both provider event streams: Codex `--json` turns and Claude
    `stream-json` init/result events. Usage is normalized to the Codex fields.
    """
    usage, session, incomplete, missing = None, None, False, False
    events_path = folder / "events.jsonl"
    if events_path.exists():
        with events_path.open(encoding="utf-8") as events:
            for line in events:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "thread.started":
                    session = event.get("thread_id")
                elif kind == "turn.started":
                    incomplete = True
                elif kind == "turn.completed":
                    incomplete = False
                    observed = token_values(event.get("usage"))
                    missing = missing or len(observed) != len(TOKEN_FIELDS)
                    if observed:
                        usage = usage or {}
                        for key, count in observed.items():
                            usage[key] = usage.get(key, 0) + count
                elif kind == "system" and event.get("subtype") == "init":
                    session = event.get("session_id") or session
                    incomplete = True
                elif kind == "session":
                    session = event.get("id") or session
                elif kind in ("agent_start", "turn_start"):
                    incomplete = True
                elif kind == "message_end":
                    message = event.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        observed = pi_token_values(message.get("usage"))
                        missing = missing or len(observed) != len(TOKEN_FIELDS)
                        if observed:
                            usage = usage or {}
                            for key, count in observed.items():
                                usage[key] = usage.get(key, 0) + count
                elif kind == "agent_end":
                    incomplete = False
                elif kind == "error":
                    incomplete = True
                elif kind == "result":
                    incomplete = False
                    observed = claude_token_values(event.get("usage"))
                    missing = missing or len(observed) != len(TOKEN_FIELDS)
                    if observed:
                        usage = usage or {}
                        for key, count in observed.items():
                            usage[key] = usage.get(key, 0) + count
    result = {"session": session, "usage": usage}
    if incomplete or missing:
        result["usage_incomplete"] = True
    return result


def claude_token_values(usage: dict | None) -> dict:
    """Normalize Claude usage; its uncached input maps to Codex input semantics."""
    if not isinstance(usage, dict):
        return {}
    values = token_values(
        {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
    )
    cached = 0
    for key in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            cached += value
    if cached:
        values["cached_input_tokens"] = cached
        if "input_tokens" in values:
            # Codex counts cached input inside input_tokens; keep one meaning.
            values["input_tokens"] += cached
    return values


def claude_error(folder: Path) -> str | None:
    """A Claude result marked is_error is a failed invocation, never a Reply."""
    events_path = folder / "events.jsonl"
    if not events_path.exists():
        return None
    failure = None
    with events_path.open(encoding="utf-8") as events:
        for line in events:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "result":
                continue
            subtype = str(event.get("subtype") or "")
            if event.get("is_error") or subtype.startswith("error"):
                detail = event.get("result") or event.get("error") or subtype or "error"
                failure = f"Claude invocation failed: {str(detail)[:200]}"
    return failure


def claude_structured_reply(folder: Path) -> dict | None:
    """Claude returns the schema-validated Reply in its final result event."""
    events_path = folder / "events.jsonl"
    if not events_path.exists():
        return None
    reply = None
    with events_path.open(encoding="utf-8") as events:
        for line in events:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                candidate = event.get("structured_output")
                if isinstance(candidate, dict):
                    reply = candidate
    return reply


def pi_token_values(usage: dict | None) -> dict:
    """Normalize pi usage; cached input is part of input like the Codex fields."""
    if not isinstance(usage, dict):
        return {}
    values = token_values(
        {"input_tokens": usage.get("input"), "output_tokens": usage.get("output")}
    )
    cached = 0
    for key in ("cacheRead", "cacheWrite"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            cached += value
    if "input_tokens" in values:
        values["cached_input_tokens"] = cached
        values["input_tokens"] += cached
    return values


def pi_structured_reply(folder: Path) -> dict | None:
    """Read the final assistant JSON from pi's `--mode json` stream."""
    events_path = folder / "events.jsonl"
    if not events_path.exists():
        return None
    text = None
    with events_path.open(encoding="utf-8") as events:
        for line in events:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "message_end":
                continue
            message = event.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            parts = [
                part.get("text", "")
                for part in message.get("content", [])
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            candidate = "\n".join(part for part in parts if part).strip()
            if candidate:
                text = candidate
    return extract_json_object(text) if text else None


def extract_json_object(text: str) -> dict | None:
    """Accept a bare object or a fenced one; ignore surrounding prose."""
    start = text.find("{")
    while start != -1:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    return None


def pi_error(folder: Path) -> str | None:
    """An error event is a failed invocation, never a Reply."""
    events_path = folder / "events.jsonl"
    if not events_path.exists():
        return None
    failure = None
    with events_path.open(encoding="utf-8") as events:
        for line in events:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "error":
                continue
            detail = event.get("error") or event.get("message") or "error"
            failure = f"pi invocation failed: {str(detail)[:200]}"
    return failure


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
        "round_class": lead.get("round_class"),
        "accepted_economic_conclusions": (
            len(lead["accepted_conclusions"])
            if isinstance(lead.get("accepted_conclusions"), list)
            else None
        ),
        "counts_scope": "Explicit engine execution counts, including comparisons later rejected. "
        "Accepted economic conclusions are those the completed Lead listed; null means none were "
        "recorded. Unknown is not zero; execution is not profitability or "
        "paper readiness.",
    }


def summarize_runs(root: Path) -> dict:
    """Read saved attempts, including failed runs and retries; never read account limits."""
    rows, totals, sessions, duplicate_sessions = [], {}, {}, set()
    count_totals, count_unknown, seen_counts = {}, {}, set()
    elapsed, elapsed_unknown, gaps = 0.0, 0, []
    for path in sorted((root / "research").glob("*/runs/*/run.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        # Old interrupted runs can have usable events absent from their final run.json.
        for phase_name, phase in state.get("phases", {}).items():
            folder = phase_folder(path.parent, phase_name, phase)
            if (folder / "events.jsonl").exists():
                observed = read_events(folder)
                for key, value in observed.items():
                    if value is not None:
                        phase[key] = value
        metrics = efficiency(root, state)
        name = path.relative_to(root).as_posix()
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
            evidence = json.loads(local_path(root, snapshot).read_text(encoding="utf-8")).get(
                "counts_artifact"
            )
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
        usage = json.loads(usage_path.read_text(encoding="utf-8"))
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
        f"executed E/A/F/V/P/D={count_text} class={metrics.get('round_class') or '?'} "
        f"accepted={metrics.get('accepted_economic_conclusions') or 0} "
        f"tok={token_text} active_s={duration} "
        f"wall_s={wall_text} | "
        f"{run.relative_to(root).as_posix()}/run.json |\n"
    )
    update_board(root, line, f"{run.relative_to(root).as_posix()}/run.json")


def update_board(root: Path, line: str, evidence: str) -> None:
    """One current row per run; immutable attempts remain in its run directory."""
    with (root / "board.md").open("a+", encoding="utf-8", newline="") as board:
        lock_file(board)
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
        with path.open(encoding="utf-8") as events:
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
    with path.open("a", encoding="utf-8") as lock:
        try:
            lock_file(lock, blocking=False)
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
    reply = Reply.model_validate_json(path.read_text(encoding="utf-8"))
    if any(
        phase.get(key, "reuse" if key == "next_review" else None) != value
        for key, value in reply.model_dump().items()
    ):
        raise ValueError(f"Saved phase reply no longer matches: {name}")
    validate_reply(root, reply, phase_kind(name), run.parent.parent.name)
    return path


def received_science_handoff(root: Path, run: Path, state: dict) -> bool:
    """A received scientific revision may advance while its unfinished work stays blocked.

    This does not resolve checkpoints or establish numerical completion. The
    latest validated Worker and an independent, downstream Lead must both call
    for plan review; event/resource recovery remains in the original session.
    """
    phases = state.get("phases", {})
    worker_name, lead_name = latest_phase(state, "worker"), latest_phase(state, "lead")
    worker, lead = phases.get(worker_name, {}), phases.get(lead_name, {})
    if not (
        state.get("status") == "round_finished"
        and state.get("active_phase") is None
        and worker.get("status") == "blocked"
        and worker.get("decision") in ("revise", "branch")
        and worker.get("next_brief")
        and worker.get("next_review") in ("plan", "both")
        and worker.get("results")
        and worker.get("results_snapshot")
        and worker.get("exit_code") == 0
        and worker.get("session")
        and not worker.get("wait")
        and not worker.get("wait_state")
        and worker.get("remote_status") not in ("unknown", "running")
        and lead.get("status") == "complete"
        and lead.get("decision") in ("repair", "continue", "branch")
        and lead.get("next_brief")
        and lead.get("next_review") in ("plan", "both")
        and lead.get("results") == worker.get("results")
        and lead.get("exit_code") == 0
        and lead.get("session")
        and not lead.get("checkpoint")
        and lead.get("session") != worker.get("session")
    ):
        return False
    upstream = []
    if state.get("review_plan"):
        plan_name = latest_phase(state, "plan_review")
        plan = phases.get(plan_name, {})
        if plan.get("status") != "complete" or plan.get("decision") != "accept":
            return False
        upstream.append(plan_name)
    if worker.get("depends_on") != upstream or lead.get("depends_on") != upstream + [worker_name]:
        return False
    order = list(phases)
    if any(order.index(name) >= order.index(worker_name) for name in upstream):
        return False
    if order.index(worker_name) >= order.index(lead_name) or any(
        phase.get("session") == lead["session"]
        for name, phase in phases.items()
        if name != lead_name
    ):
        return False
    # Only the received worker's original-session chain may retain blocks. An
    # unrelated checkpoint or uncertain event dispatch is never handed off.
    chain = set()
    remote_wait = False
    name = worker_name
    while name:
        if name in chain or name not in phases or phase_kind(name) != "worker":
            return False
        phase = phases[name]
        if (
            phase.get("session") != worker["session"]
            or phase.get("event_attempt", {}).get("state") == "dispatching"
            or phase.get("wait_state", {}).get("state") == "dispatching"
        ):
            return False
        wait = phase.get("wait") or {}
        remote_wait = remote_wait or bool(wait and not wait.get("local_only"))
        chain.add(name)
        name = phase.get("resumes_phase")
    # A later science reply alone cannot establish remote termination. Receive
    # explicit terminal evidence from the bound checkpoint, not a launcher exit
    # or a marker that merely requested reconciliation.
    checkpoint = {}
    if worker.get("checkpoint"):
        try:
            checkpoint = json.loads(
                local_path(root, worker["checkpoint"]).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        if not isinstance(checkpoint, dict) or checkpoint.get("remote_status") in (
            "unknown",
            "running",
            "requires_reconciliation",
        ):
            return False
    if remote_wait:
        if (
            checkpoint_status(root, run, worker.get("checkpoint"), worker["session"])["state"]
            != "available"
        ):
            return False
        terminal = False
        for item in checkpoint.get("inputs", []):
            try:
                receipt_path = local_path(root, item["path"])
                if receipt_path.suffix != ".json" or receipt_path.stat().st_size > 65536:
                    continue
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError):
                continue
            if isinstance(receipt, dict) and (
                receipt.get("controller_process_state") == "exited"
                and receipt.get("remote_status")
                not in ("unknown", "running", "requires_reconciliation")
                and receipt.get("explicit_remote_terminal")
                and receipt.get("shards") is not None
                and receipt.get("shards") == receipt.get("returned_shards")
            ):
                terminal = True
        if not terminal:
            return False
    if has_checkpoint(
        {"phases": {name: phase for name, phase in phases.items() if name not in chain}}
    ):
        return False
    for name in [*upstream, worker_name, lead_name]:
        phase_reply(root, run, name, phases[name])
    validate_results(root, worker["results_snapshot"], state["direction"])
    require_local_stopped(run, state)
    return True


def require_local_stopped(run: Path, state: dict) -> None:
    for name, phase in state.get("phases", {}).items():
        path = phase_folder(run, name, phase) / "process.json"
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if saved and process_state(saved) == "running":
            raise ValueError(f"Local phase process is still running: {name}")


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
        evidence = [phase_reply(root, run, current, phase).relative_to(root).as_posix()]
        if kind == "worker":
            if not phase.get("results"):
                continue
            validate_results(root, phase["results"], state["direction"])
            evidence.append(phase["results"])
        evidence.append(phase_reply(root, run, lead_name, lead).relative_to(root).as_posix())
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
        state = json.loads(path.read_text(encoding="utf-8"))
        # A local return code cannot establish whether a remote job is still live.
        unresolved = state.get("status") in ("running", "resource_wait", "interrupted_or_failed")
        checkpoint = has_checkpoint(state) and not received_science_handoff(
            task.parent.parent, path.parent, state
        )
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
    if reply.wait is not None and (kind != "worker" or reply.status != "blocked"):
        raise ReplyFormatError("Only a blocked worker may declare an event wait")
    if reply.checkpoint is not None:
        reply_file(root, reply.checkpoint)
    if reply.next_brief is not None:
        next_path = reply_file(root, reply.next_brief)
        if not 0 < next_path.stat().st_size <= 1000:
            raise ReplyFormatError("Next brief is missing or oversized")
    if reply.results is not None:
        result_path = reply_file(root, reply.results)
        if kind == "plan_review":
            candidate = json.loads(result_path.read_text(encoding="utf-8"))
            if (
                isinstance(candidate, dict)
                and "verdict" in candidate
                and not {"direction", "kind", "engine"}.issubset(candidate)
            ):
                raise ReplyFormatError(
                    "Plan verdict is not engine Results. Preserve the native review, "
                    "link it in summary, and return results=null; do not repeat the review."
                )
        validate_results(root, reply.results, direction)
    if kind == "worker" and reply.status == "complete" and reply.results is None:
        raise ReplyFormatError("A completed worker must point to engine results")
    if kind == "lead" and reply.status == "complete":
        if reply.decision not in ("continue", "repair", "branch", "park"):
            raise ReplyFormatError("Lead must choose continue/repair/branch/park")
        if reply.decision != "park" and reply.next_brief is None:
            raise ReplyFormatError("Continuing work requires a concrete next brief")


def reconcile_event_attempts(root: Path, run: Path, state: dict, deadline: float) -> None:
    """Receive started event continuations under the direction lock; never dispatch."""
    for name, phase in state.get("phases", {}).items():
        attempt = phase.get("event_attempt", {})
        if attempt.get("state") != "dispatching":
            continue
        folder = phase_folder(run, name, phase)
        process = folder / "process.json"
        if process.is_file():
            saved = json.loads(process.read_text(encoding="utf-8"))
            while process_state(saved) == "running":
                if time.monotonic() >= deadline:
                    raise ValueError("Event continuation process is still running")
                require_research(root)
                time.sleep(0.1)
        receipt = folder / "transport.json"
        observed = read_events(folder)
        if receipt.is_file():
            transport = json.loads(receipt.read_text(encoding="utf-8"))
        elif (
            process.is_file()
            and observed.get("session")
            and not observed.get("usage_incomplete")
            and observed.get("usage") is not None
        ):
            transport = {**observed, "exit_code": 0}
        else:
            raise ValueError("Uncertain event dispatch; reconcile original session before retry")
        if transport.get("exit_code") != 0:
            raise ValueError("Event continuation failed; preserve checkpoint for reconciliation")
        if transport.get("session") != phase.get("resumes_session"):
            raise ValueError("Event continuation did not return original session")
        reply = Reply.model_validate_json((folder / "reply.json").read_text(encoding="utf-8"))
        validate_reply(root, reply, phase_kind(name), state["direction"])
        phase.update(transport)
        phase.update(reply.model_dump())
        if reply.wait is not None:
            phase["wait_state"] = bind_wait(root, run, reply.wait)
        source = state["phases"][attempt["source_phase"]]
        if source.get("wait_state", {}).get("attempt") != name:
            raise ValueError("Event attempt binding changed")
        source["wait_state"]["state"] = "received"
        attempt["state"] = "received"
        write_json(run / "run.json", state)


def await_agent_admission(root: Path, run: Path, state: dict, phase: str, deadline: float) -> None:
    """Wait in the resident driver only for an explicit agent headroom refusal."""
    command = (
        [
            sys.executable,
            str(root / "scripts/run_capped.py"),
            "--root",
            str(root),
            "admit",
            "--kind",
            "agent",
        ]
        if os.name == "nt"
        else [sys.executable, str(root / "scripts/memory_budget.py"), "admit", "--kind", "agent"]
    )
    saved = state["phases"][phase]
    while True:
        require_research(root)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Round deadline reached during agent admission")
        result = subprocess.run(
            command, cwd=root, timeout=min(30, remaining), capture_output=True, text=True
        )
        saved.setdefault("admission_attempts", []).append(
            {
                "at_utc": datetime.now(UTC).isoformat(),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        memory_refusal = result.returncode == 2 and re.fullmatch(
            r"refuse: headroom -?\d+ MB < \d+ MB for a new agent", result.stderr.strip()
        )
        if not memory_refusal:
            write_json(run / "run.json", state)
            result.check_returncode()
            state["status"], saved["status"] = "running", "starting"
            if "resource_wait" in saved:
                saved["resource_wait"].update(state="admitted", ended=datetime.now(UTC).isoformat())
            write_json(run / "run.json", state)
            require_research(root)
            return
        state["status"], saved["status"] = "resource_wait", "resource_wait"
        saved.setdefault("resource_wait", {"started": datetime.now(UTC).isoformat()})
        saved["resource_wait"].update(state="waiting", reason=result.stderr.strip())
        write_json(run / "run.json", state)
        retry_at = min(deadline, time.monotonic() + 30)
        while time.monotonic() < retry_at:
            try:
                require_research(root)
            except ValueError:
                saved["resource_wait"]["state"] = "paused"
                write_json(run / "run.json", state)
                raise
            time.sleep(min(0.1, max(0, retry_at - time.monotonic())))
        if time.monotonic() >= deadline:
            saved["resource_wait"]["state"] = "deadline"
            write_json(run / "run.json", state)


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
    config = json.loads((root / "research/workflow.json").read_text(encoding="utf-8"))
    with nullcontext() if _locked else direction_lock(task / ".round.lock"):
        started = time.monotonic()
        if resume:
            state = json.loads((run / "run.json").read_text(encoding="utf-8"))
            if state["direction"] != direction or state["run_id"] != run_id:
                raise ValueError("Saved run identity does not match")
            if state.get("status") == "closed_after_recovery":
                raise ValueError(
                    "Round is closed_after_recovery; receive its closure, not replay it"
                )
            reconcile_event_attempts(root, run, state, started + timeout)
            require_local_stopped(run, state)
            if received_science_handoff(root, run, state):
                # Consume the already received Lead once. Replaying this blocked
                # Worker would repeat work before the requested independent review.
                return state
            attempt = len(list(run.glob("before-resume-*.json"))) + 1
            archive = run / f"before-resume-{attempt}.json"
            with archive.open("x", encoding="utf-8") as output:
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
                "explicit_resume": resume,
            }
        )
        write_json(run / "run.json", state)
        deadline = started + timeout
        schema = run / "reply.schema.json"
        write_json(schema, reply_dispatch_schema())
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
                        prior["results_snapshot"] = snapshot.relative_to(root).as_posix()
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
                    event_record = prior.get("wait_state") if kind == "worker" else None
                    if event_record and not changed_upstream:
                        if event_record.get("state") == "dispatching":
                            raise ValueError("Uncertain event attempt; reconcile original session")
                        observed = wait_event(root, run, event_record, deadline, require_research)
                        event_record.update(observed)
                        write_json(run / "run.json", state)
                        if observed["state"] != "ready":
                            reply = Reply.model_validate(
                                {k: prior.get(k) for k in Reply.model_fields if k in prior}
                            )
                            break
                        if any(
                            p.get("event_attempt", {}).get("event") == observed["event"]
                            and p["event_attempt"].get("wait_id") == event_record["id"]
                            for p in state["phases"].values()
                        ):
                            event_record["state"] = "duplicate_event"
                            write_json(run / "run.json", state)
                            reply = Reply.model_validate(
                                {k: prior.get(k) for k in Reply.model_fields if k in prior}
                            )
                            break
                        event_record["state"] = "observed"
                        write_json(run / "run.json", state)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Round deadline reached; preserve existing job state")
                    role_name = "reviewer" if kind == "plan_review" else kind
                    # Resume the original provider/model/session, but apply the
                    # installed effort to each new invocation, including recovery.
                    role = dict(prior.get("requested_runtime", config["roles"][role_name]))
                    role["effort"] = config["roles"][role_name]["effort"]
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
                    command = agent_command(root, role, output, schema, session=session_to_resume)
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
                    if event_record:
                        event_record.update(state="dispatching", attempt=phase)
                        state["phases"][phase]["event_attempt"] = {
                            "wait_id": event_record["id"],
                            "event": event_record["event"],
                            "source_phase": prior_name,
                            "state": "dispatching",
                        }
                    phase_started = time.monotonic()
                    write_json(run / "run.json", state)
                    dispatch = (
                        f"\nDirection: {direction}\nPhase: {phase}\n"
                        f"Brief: {brief.relative_to(root).as_posix()}\n"
                        f"Run: {run.relative_to(root).as_posix()}\n"
                        "Read the brief and earlier replies. Engine schema: "
                        "research/schemas/results.schema.json. Preserve authority, native gates, "
                        "paper and schedules. Return the reply schema.\n"
                    )
                    if resume or recovery_reason:
                        dispatch = (
                            f"\nPhase: {phase}\nBrief: {brief.relative_to(root).as_posix()}\n"
                            f"Run: {run.relative_to(root).as_posix()}\n"
                            "Resume saved task/session. Read run.json; reconcile jobs "
                            "and checkpoints first. Reuse outputs; "
                            "no duplicate jobs/provider swap. "
                            "Keep "
                            "unresolved checkpoints. Return Reply; engine schema: "
                            "research/schemas/results.schema.json.\n"
                        )
                    if recovery_reason == "reply_only":
                        error_note = (
                            str(prior.get("error", "")).encode()[:80].decode(errors="ignore")
                        )
                        dispatch = (
                            f"\nRun: {run.relative_to(root).as_posix()}\n"
                            "Brief: brief.md (inside Run)\n"
                            "Correct Reply only: existing file paths or null. No numerical work, "
                            "evidence edits or job launches. Missing valid results means blocked. "
                            f"Validation: {error_note}\n"
                        )
                    if len(dispatch.encode()) > 500:
                        raise ValueError("Dispatch exceeds the startup envelope")
                    prompt = local_path(root, role["prompt"]).read_text(encoding="utf-8") + dispatch
                    if execute_fn is execute:
                        await_agent_admission(root, run, state, phase, deadline)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Round deadline reached during admission")
                    wrapped = capped_command(root, command, config["agent_memory"])
                    try:
                        transport = execute_fn(wrapped, prompt, folder, remaining)
                        write_json(folder / "transport.json", transport)
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
                        if event_record:
                            event_record["state"] = "failed"
                            state["phases"][phase]["event_attempt"]["state"] = "failed"
                            write_json(run / "run.json", state)
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
                    if role["provider"] in ("claude", "pi") and not output.exists():
                        if role["provider"] == "claude":
                            structured = claude_structured_reply(folder)
                            failure_error = claude_error(folder)
                        else:
                            structured = pi_structured_reply(folder)
                            failure_error = pi_error(folder)
                        if structured is not None:
                            write_json(output, structured)
                        elif failure_error:
                            state["phases"][phase].update(
                                status="interrupted_or_failed", error=failure_error
                            )
                            write_json(run / "run.json", state)
                            raise RuntimeError(failure_error)
                    try:
                        try:
                            reply = Reply.model_validate_json(output.read_text(encoding="utf-8"))
                        except (OSError, ValueError) as exc:
                            raise ReplyFormatError(str(exc)) from exc
                        state["phases"][phase]["checkpoint"] = reply.checkpoint
                        write_json(run / "run.json", state)
                        validate_reply(root, reply, kind, direction)
                    except ReplyFormatError as exc:
                        state["phases"][phase].update(status="invalid_reply", error=str(exc))
                        if event_record:
                            event_record["state"] = "invalid_reply"
                            state["phases"][phase]["event_attempt"]["state"] = "invalid_reply"
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
                        state["phases"][phase]["results_snapshot"] = snapshot.relative_to(
                            root
                        ).as_posix()
                    state["phases"][phase].update(reply.model_dump())
                    if event_record:
                        event_record["state"] = "received"
                        state["phases"][phase]["event_attempt"]["state"] = "received"
                    if reply.wait is not None:
                        state["phases"][phase]["wait_state"] = bind_wait(root, run, reply.wait)
                        if reply.checkpoint:
                            state["phases"][phase]["checkpoint_availability"] = checkpoint_status(
                                root, run, reply.checkpoint, session
                            )
                    if kind in ("worker", "lead"):
                        state[f"latest_{kind}_phase"] = phase
                    state["active_phase"] = None
                    write_json(run / "run.json", state)
                    if kind == "worker" and reply.wait is not None:
                        prior_name, prior = phase, state["phases"][phase]
                        changed_upstream = False
                        recovery_reason = "event_ready"
                        continue
                    break
                if kind == "plan_review" and (
                    reply.status != "complete" or reply.decision != "accept"
                ):
                    state["status"] = "scope_needs_revision"
                    break
                if kind == "worker":
                    worker_blocked = reply.status == "blocked"
                    if worker_blocked and not (
                        reply.decision in ("branch", "revise")
                        and reply.next_brief is not None
                        and reply.next_review in ("plan", "both")
                    ):
                        # Waiting, transport and resource checkpoints stay in
                        # this run/session. Lead needs an economic result or an
                        # explicit material-science decision, not a status round.
                        state["status"] = "worker_checkpoint"
                        break
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
    if local_path(root, brief).read_text(encoding="utf-8") != pending["brief_text"]:
        raise ValueError("Pending brief changed before its first launch")
    folder = saved_run.parent
    if folder.exists():
        if any(
            p.name not in ("brief.md", "run.json.tmp") or not p.is_file() or p.is_symlink()
            for p in folder.iterdir()
        ):
            raise ValueError("Unstarted round has unexplained artifacts; reconcile first")
        snapshot = folder / "brief.md"
        if snapshot.exists() and snapshot.read_text(encoding="utf-8") != pending["brief_text"]:
            raise ValueError("Partial round brief differs from its pending dispatch")
        temporary = folder / "run.json.tmp"
        if (
            temporary.exists()
            and json.loads(temporary.read_text(encoding="utf-8")).get("phases") != {}
        ):
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
        series = json.loads(record.read_text(encoding="utf-8"))
        existing_run = series.get("active_round")
        if existing_run and "/" not in existing_run:
            existing_run = f"research/{direction}/runs/{existing_run}/run.json"
        if not existing_run and series.get("rounds"):
            existing_run = series["rounds"][-1]
        if not existing_run:
            raise ValueError("Series has no saved round to resume")
        saved_path = local_path(root, existing_run)
        closed = False
        if saved_path.exists():
            with direction_lock(saved_path.parent.parent.parent / ".round.lock"):
                saved_state = json.loads(saved_path.read_text(encoding="utf-8"))
                closed = saved_state.get("status") == "closed_after_recovery"
                if not closed:
                    require_local_stopped(saved_path.parent, saved_state)
        archive = record.with_name(f"{record.stem}-resume-{time.time_ns()}.json")
        with archive.open("x", encoding="utf-8") as output:
            json.dump(series, output, ensure_ascii=False, indent=2)
        series.pop("error", None)
        if closed:
            # A round closed after recovery is received once, never replayed.
            series.update(status="closed_after_recovery", active_round=None, next_brief=None)
            series.pop("pending_dispatch", None)
            write_json(record, series)
            return series
        series.update(status="running")
    else:
        with record.open("x", encoding="utf-8") as output:
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
                    "brief_text": local_path(root, pending_brief).read_text(encoding="utf-8"),
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
            if has_checkpoint(result) and not received_science_handoff(
                root, local_path(root, series["active_round"]).parent, result
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
