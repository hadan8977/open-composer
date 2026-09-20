"""Pure data for the cockpit's agent-activity screen (Step 18, screen 3, T7).

Nothing in this module renders HTML, and nothing here is FastAPI-aware --
`open_composer.cockpit.app` is the only thing that imports both this module
and the template engine, mirroring `open_composer.cockpit.data.health` and
`open_composer.cockpit.data.quota`. Every function here is read-only and
never raises for a missing/unreadable data source: a bad agent file, a
missing transcript tree, or an unreachable `systemctl` degrades that one
piece to `None`/`()`/a warning string, never an exception -- the health-page
pattern this whole cockpit follows (see `health.build_health_report`'s
docstring).

Three on-disk sources, three shapes (measured 2026-09-19/20, see
`docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md` sections 4-5):

* **Agents** -- one JSON object per agent at
  ``~/.paseo/agents/<workspace-slug>/<agent-id>.json``. This module reads an
  *allowlist* of top-level keys (id/provider/cwd/workspaceId/title/the four
  timestamp fields/lastStatus/config.model/runtimeInfo.sessionId) and nothing
  else. In particular it never reads ``persistence.metadata.mcpServers.*``,
  which on a real agent file on this box holds a live bearer token
  (``persistence.metadata.mcpServers.paseo.headers.Authorization``) -- the
  allowlist is the control, not a redaction step downstream, because the
  token must never exist as a Python value here at all, not even briefly.

* **Claude transcripts** -- ``~/.claude/projects/<slug>/<sessionId>.jsonl``,
  one JSON object per line, where ``<slug>`` is the agent's ``cwd`` with
  every ``/`` replaced by ``-`` (Claude Code's own convention; verified
  against this box's real `~/.claude/projects` directory names). Assistant
  lines carry ``message.content[]`` blocks of type ``text``, ``tool_use``
  (name + input dict + id) and, in user-role lines, ``tool_result``
  (tool_use_id + content + is_error). A ``thinking`` block's body is an
  empty string with only a cryptographic signature (measured on this box's
  real transcripts, 2026-09-20) -- there is no reasoning text to recover, so
  this module never looks at a ``thinking`` block's contents and this
  screen never labels anything "reasoning". Subagent (`Task`-tool)
  transcripts at ``/tmp/claude-0/<slug>/<parentSessionId>/tasks/<id>.output``
  share this exact line shape (verified against a real one on this box) and
  are parsed with the same function.

* **Codex transcripts** -- ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``.
  Lines have a top-level ``type`` or ``response_item``/``event_msg``
  discriminant; this module only extracts ``response_item`` lines whose
  ``payload.type`` is ``message`` (assistant role only), ``function_call``,
  or ``function_call_output`` -- every other payload type (``event_msg``,
  ``token_usage_record``, ``world_state``, ``turn_context``,
  ``session_meta``, and any future/version-specific type such as
  ``agent_reasoning``) is bookkeeping this screen ignores by design, per the
  plan's explicit "treat unknown payload types as ignorable".

Every string this module produces for a template or the SSE stream --
assistant text, a tool's one-line input summary, a tool result body, even an
agent's own ``title`` -- is scrubbed with
`open_composer.cockpit.security.secret_scrub` and truncated *after*
scrubbing, at the point the value is built, not left to the template. Tool
inputs/results are the riskiest text in the whole cockpit (a `Bash` tool can
legitimately echo an environment dump, or, as measured live on this box
2026-09-20, a `curl`/`cat` of a real credentials file), which is exactly the
case this exists for.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

from open_composer.cockpit.security import secret_scrub

# --------------------------------------------------------------------------
# On-disk roots. Bare module globals, never baked into a function's default
# parameter value, so a test can monkeypatch them in place (mirrors
# `quota.CLAUDE_PROJECTS_DIR`/`quota.SUBAGENT_TASKS_ROOT`; see
# `tests/conftest.py`'s autouse fixture, which points all four at a
# nonexistent path for every test by default).
# --------------------------------------------------------------------------

PASEO_AGENTS_DIR: Final[Path] = Path.home() / ".paseo" / "agents"
CLAUDE_PROJECTS_DIR: Final[Path] = Path.home() / ".claude" / "projects"
SUBAGENT_TASKS_ROOT: Final[Path] = Path("/tmp/claude-0")  # noqa: S108 - a documented, fixed convention
CODEX_SESSIONS_DIR: Final[Path] = Path.home() / ".codex" / "sessions"

TranscriptKind = Literal["claude", "codex", "none"]
TimelineEntryKind = Literal["text", "tool", "result"]

#: Validated before any agent id ever touches the filesystem (plan section
#: "Build", item 3). Matches the `id` field on every real agent JSON on this
#: box (208 closed + 19 idle + 1 running + 1 error, all this shape).
AGENT_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
#: The subagent (`Task`-tool) id form, e.g. `a1cc5201cbea09aa9` -- the
#: filename stem of a `/tmp/claude-0/.../tasks/<id>.output` file on this box.
SUBAGENT_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{17}$")

CLOSED_STALE_HOURS: Final[float] = 48.0
#: "read a bounded tail (last 256 KiB)" -- plan "Build", item 1.
_TRANSCRIPT_TAIL_BYTES: Final[int] = 256 * 1024
#: Per-poll cap for the SSE tail (plan section 6, rule 5: bounded reads,
#: <=50MB per response) -- a single poll never reads more than this even if
#: the transcript grew by more between two 2s polls.
_STREAM_MAX_READ_BYTES: Final[int] = 1_048_576
#: "truncate each entry to 400 chars after scrubbing" -- plan "Build", item 4.
_MAX_ENTRY_TEXT_CHARS: Final[int] = 400
#: "the last assistant text (first 160 chars)" -- plan "Build", item 1.
_LAST_TEXT_LIST_CHARS: Final[int] = 160
_MAX_SUBAGENT_TASKS: Final[int] = 20

DEFAULT_SSE_POLL_INTERVAL_SECONDS: Final[float] = 2.0
DEFAULT_SSE_KEEPALIVE_INTERVAL_SECONDS: Final[float] = 15.0
DEFAULT_SSE_MAX_DURATION_SECONDS: Final[float] = 600.0

_SYSTEMCTL_TIMEOUT_SECONDS: Final[float] = 2.0
_RESEARCH_CAPPED_SLICE_NAME: Final[str] = "research-capped"

_STATE_RANK: Final[dict[str, int]] = {"running": 0, "error": 1, "idle": 2, "closed": 3}
_STATE_DOT: Final[dict[str, str]] = {
    "running": "ok",
    "idle": "unknown",
    "error": "stale",
    "closed": "unknown",
}
_FILE_TOOL_NAMES: Final[frozenset[str]] = frozenset({"Read", "Edit", "Write", "NotebookEdit"})

#: Priority order for reducing a tool's `input` dict to one display line
#: (plan "Build", item 1: "the command or file_path"); the loop falls back
#: to the first string value found, then to a short JSON dump.
_TARGET_KEY_PRIORITY: Final[tuple[str, ...]] = (
    "command",
    "cmd",
    "file_path",
    "path",
    "notebook_path",
    "pattern",
    "url",
    "description",
    "prompt",
    "query",
)


# --------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentRecord:
    """The allowlisted fields of one `~/.paseo/agents/**/*.json` file.

    Every field here is one this module explicitly chose to read; anything
    not listed (most importantly `persistence.metadata.mcpServers.*`, which
    holds a live bearer token on a real agent file on this box) is never
    touched by the loader that builds this, see `_load_agent_record`.
    """

    id: str
    provider: str
    cwd: str | None
    workspace_id: str | None
    title: str | None  # already secret_scrub'd
    created_at: datetime | None
    updated_at: datetime | None
    last_activity_at: datetime | None
    last_user_message_at: datetime | None
    last_status: str
    model: str | None
    session_id: str | None


@dataclass(frozen=True)
class TimelineEntry:
    """One row of the audit timeline: something the agent said or did.

    `target` is a tool's one-line input summary (e.g. a shortened `command`
    or `file_path`); `detail` is assistant text or a tool result body. Both
    are already `secret_scrub`'d and truncated to `_MAX_ENTRY_TEXT_CHARS` by
    the time they land here -- see `_finalize_text`. `duration_seconds` is
    only ever set on a `"tool"` entry, filled in by `_pair_tool_durations`
    once its matching `"result"` entry (same `tool_use_id`) is found.
    """

    at: datetime | None
    kind: TimelineEntryKind
    tool_name: str | None
    target: str | None
    detail: str | None
    is_error: bool
    duration_seconds: float | None
    tool_use_id: str | None


@dataclass(frozen=True)
class AgentActivity:
    """The transcript-derived half of one agent's row (plan "Build", item 1)."""

    transcript_kind: TranscriptKind
    transcript_path: Path | None
    current_file: str | None
    last_text: str | None
    last_entry_at: datetime | None
    warning: str | None


@dataclass(frozen=True)
class AgentSummary:
    """One row of the `/agents` list: an `AgentRecord` plus its activity.

    `activity` is `None` for a closed agent -- `load_agents` only resolves
    and reads a transcript for a non-closed agent (plan "Build", item 1:
    "For each non-closed agent resolve its transcript path").
    """

    record: AgentRecord
    activity: AgentActivity | None


@dataclass(frozen=True)
class AgentsReport:
    agents: tuple[AgentSummary, ...]
    closed_collapsed_count: int
    closed_stale_cutoff: datetime
    generated_at: datetime
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TimelineChunk:
    """One bounded read of a transcript, for the SSE stream's polling loop."""

    entries: tuple[TimelineEntry, ...]
    next_offset: int
    transcript_path: Path | None


@dataclass(frozen=True)
class SubagentTask:
    id: str
    entries: tuple[TimelineEntry, ...]
    warning: str | None


@dataclass(frozen=True)
class AgentDetail:
    record: AgentRecord | None
    entries: tuple[TimelineEntry, ...]
    subagents: tuple[SubagentTask, ...]
    transcript_kind: TranscriptKind
    transcript_available: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class HeavyJob:
    """One `scripts/run_capped.sh`-launched scope (plan "Build", item 1)."""

    unit: str
    started_at: datetime | None
    elapsed_seconds: float | None
    memory_current_bytes: int | None
    memory_max_bytes: int | None
    memory_max_unlimited: bool
    warning: str | None


@dataclass(frozen=True)
class HeavyJobsReport:
    jobs: tuple[HeavyJob, ...]
    available: bool
    warnings: tuple[str, ...]


# --------------------------------------------------------------------------
# Small shared parsing helpers (mirrors `quota._parse_iso`/`health._read_log_tail`)
# --------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _slugify_cwd(cwd: str) -> str:
    """Claude Code's own project-directory naming convention: every `/` -> `-`.

    Verified against this box's real `~/.claude/projects` directory names,
    e.g. `/root/codex-test/open-composer` -> `-root-codex-test-open-composer`.
    """
    return cwd.replace("/", "-")


def _read_tail_bytes(path: Path, max_bytes: int) -> tuple[bytes, bool] | None:
    """Bounded tail read: a `seek()` from the end, never the whole file.

    Returns `(chunk, possibly_truncated_first_line)`, or `None` if the file
    could not be opened at all. Mirrors `health._read_log_tail` /
    `quota._last_quota_event_in_file`'s bounded-tail pattern.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            chunk = handle.read()
    except OSError:
        return None
    return chunk, start > 0


def _iter_jsonl_lines(chunk: bytes, *, drop_first: bool) -> list[dict[str, Any]]:
    text = chunk.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if drop_first and lines:
        lines = lines[1:]  # a tail read may start mid-line; drop the fragment
    parsed: list[dict[str, Any]] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed.append(obj)
    return parsed


def _finalize_text(text: str, *, limit: int = _MAX_ENTRY_TEXT_CHARS) -> str:
    """Scrub, then truncate -- in that order, per plan "Build", item 4."""
    return secret_scrub(text or "")[:limit]


def _one_line_tool_target(name: str, input_obj: dict[str, Any]) -> str:
    """Reduce a tool's `input` dict to one display line.

    `name` is unused for key selection (every tool's own most-relevant key
    already sorts first in `_TARGET_KEY_PRIORITY`) but kept as a parameter
    so a future tool-specific rule has an obvious place to live.
    """
    del name
    for key in _TARGET_KEY_PRIORITY:
        value = input_obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in input_obj.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    if input_obj:
        try:
            return json.dumps(input_obj, default=str)
        except (TypeError, ValueError):
            return str(input_obj)
    return ""


def _stringify_tool_result_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                parts.append(str(block))
        return " ".join(parts)
    if content is None:
        return ""
    return str(content)


def _parse_function_call_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# --------------------------------------------------------------------------
# Transcript line -> TimelineEntry
# --------------------------------------------------------------------------


def _entries_from_claude_style_lines(lines: list[dict[str, Any]]) -> list[TimelineEntry]:
    """Claude Code's own transcript shape, shared verbatim by subagent output
    files (`SUBAGENT_TASKS_ROOT/**/tasks/<id>.output`) -- both are parsed by
    this one function. `thinking` blocks are never inspected: their body is
    an empty string with only a signature (measured on this box's real
    transcripts), so there is nothing in them for this screen to show.
    """
    entries: list[TimelineEntry] = []
    for line in lines:
        line_type = line.get("type")
        if line_type not in ("assistant", "user"):
            continue
        at = _parse_iso(line.get("timestamp"))
        message = line.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if line_type == "assistant" and block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    entries.append(
                        TimelineEntry(
                            at=at,
                            kind="text",
                            tool_name=None,
                            target=None,
                            detail=_finalize_text(text),
                            is_error=False,
                            duration_seconds=None,
                            tool_use_id=None,
                        )
                    )
            elif line_type == "assistant" and block_type == "tool_use":
                name = block.get("name")
                name = name if isinstance(name, str) and name else "unknown"
                raw_input = block.get("input")
                input_obj = raw_input if isinstance(raw_input, dict) else {}
                tool_use_id = block.get("id") if isinstance(block.get("id"), str) else None
                entries.append(
                    TimelineEntry(
                        at=at,
                        kind="tool",
                        tool_name=name,
                        target=_finalize_text(_one_line_tool_target(name, input_obj)),
                        detail=None,
                        is_error=False,
                        duration_seconds=None,
                        tool_use_id=tool_use_id,
                    )
                )
            elif line_type == "user" and block_type == "tool_result":
                raw_content = _stringify_tool_result_content(block.get("content"))
                is_error = bool(block.get("is_error"))
                tool_use_id = (
                    block.get("tool_use_id") if isinstance(block.get("tool_use_id"), str) else None
                )
                entries.append(
                    TimelineEntry(
                        at=at,
                        kind="result",
                        tool_name=None,
                        target=None,
                        detail=_finalize_text(raw_content),
                        is_error=is_error,
                        duration_seconds=None,
                        tool_use_id=tool_use_id,
                    )
                )
            # Any other block type (`thinking`, images, ...) is intentionally
            # ignored -- this screen shows what the agent said and did, not
            # what it "thought"; see the module docstring.
    return entries


def _entries_from_codex_lines(lines: list[dict[str, Any]]) -> list[TimelineEntry]:
    """Codex's rollout shape. Only `response_item` lines with a `message`
    (assistant role only -- developer/user echoes are the prompt, not
    something the agent said), `function_call`, or `function_call_output`
    payload become an entry; every other `type`/`payload.type` (`event_msg`,
    `token_usage_record`, `world_state`, `turn_context`, `session_meta`, and
    any future type such as `agent_reasoning`) is ignored, per the plan's
    explicit "treat unknown payload types as ignorable".
    """
    entries: list[TimelineEntry] = []
    for line in lines:
        if line.get("type") != "response_item":
            continue
        payload = line.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        at = _parse_iso(line.get("timestamp"))

        if payload_type == "message":
            if payload.get("role") != "assistant":
                continue
            content = payload.get("content")
            if not isinstance(content, list):
                continue
            texts = [
                block["text"]
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            text = " ".join(t for t in texts if t.strip())
            if text.strip():
                entries.append(
                    TimelineEntry(
                        at=at,
                        kind="text",
                        tool_name=None,
                        target=None,
                        detail=_finalize_text(text),
                        is_error=False,
                        duration_seconds=None,
                        tool_use_id=None,
                    )
                )
        elif payload_type == "function_call":
            name = payload.get("name")
            name = name if isinstance(name, str) and name else "unknown"
            input_obj = _parse_function_call_arguments(payload.get("arguments"))
            call_id = payload.get("call_id") if isinstance(payload.get("call_id"), str) else None
            entries.append(
                TimelineEntry(
                    at=at,
                    kind="tool",
                    tool_name=name,
                    target=_finalize_text(_one_line_tool_target(name, input_obj)),
                    detail=None,
                    is_error=False,
                    duration_seconds=None,
                    tool_use_id=call_id,
                )
            )
        elif payload_type == "function_call_output":
            output = payload.get("output")
            text = output if isinstance(output, str) else ("" if output is None else str(output))
            call_id = payload.get("call_id") if isinstance(payload.get("call_id"), str) else None
            entries.append(
                TimelineEntry(
                    at=at,
                    kind="result",
                    tool_name=None,
                    target=None,
                    detail=_finalize_text(text),
                    is_error=False,
                    duration_seconds=None,
                    tool_use_id=call_id,
                )
            )
        # Any other payload type is bookkeeping this screen ignores.
    return entries


def _pair_tool_durations(entries: list[TimelineEntry]) -> list[TimelineEntry]:
    """Fill in `duration_seconds` on each `"tool"` entry from its matching
    `"result"` entry (same `tool_use_id`), per plan "Build", item 2:
    "duration when derivable (tool_use -> matching tool_result by id)".
    """
    result_at_by_id: dict[str, datetime | None] = {}
    for entry in entries:
        if (
            entry.kind == "result"
            and entry.tool_use_id
            and entry.tool_use_id not in result_at_by_id
        ):
            result_at_by_id[entry.tool_use_id] = entry.at

    paired: list[TimelineEntry] = []
    for entry in entries:
        if entry.kind == "tool" and entry.tool_use_id in result_at_by_id and entry.at is not None:
            result_at = result_at_by_id[entry.tool_use_id]
            if result_at is not None:
                delta = (result_at - entry.at).total_seconds()
                if delta >= 0:
                    entry = replace(entry, duration_seconds=delta)
        paired.append(entry)
    return paired


def _read_transcript_entries(
    kind: TranscriptKind, path: Path, *, max_bytes: int
) -> list[TimelineEntry]:
    result = _read_tail_bytes(path, max_bytes)
    if result is None:
        raise OSError(f"cannot read transcript {path}")
    chunk, truncated = result
    lines = _iter_jsonl_lines(chunk, drop_first=truncated)
    entries = (
        _entries_from_codex_lines(lines)
        if kind == "codex"
        else _entries_from_claude_style_lines(lines)
    )
    return _pair_tool_durations(entries)


def summarize_activity(
    entries: Sequence[TimelineEntry],
) -> tuple[str | None, str | None, datetime | None]:
    """`(current_file, last_text, last_entry_at)` for one agent's list row.

    `current_file` prefers the latest `Read`/`Edit`/`Write` tool call's
    target (a file path); if there has not been one, it falls back to the
    latest `Bash` command -- exactly plan "Build" item 1's rule.
    """
    current_file: str | None = None
    for entry in reversed(entries):
        if entry.kind == "tool" and entry.tool_name in _FILE_TOOL_NAMES and entry.target:
            current_file = entry.target
            break
    if current_file is None:
        for entry in reversed(entries):
            if entry.kind == "tool" and entry.tool_name == "Bash" and entry.target:
                current_file = entry.target
                break

    last_text: str | None = None
    for entry in reversed(entries):
        if entry.kind == "text" and entry.detail:
            last_text = entry.detail[:_LAST_TEXT_LIST_CHARS]
            break

    last_entry_at: datetime | None = None
    for entry in reversed(entries):
        if entry.at is not None:
            last_entry_at = entry.at
            break

    return current_file, last_text, last_entry_at


# --------------------------------------------------------------------------
# Agent records
# --------------------------------------------------------------------------


def _load_agent_record(path: Path) -> tuple[AgentRecord | None, str | None]:
    """Allowlisted parse of one `~/.paseo/agents/**/*.json` file.

    Reads exactly the keys named in the module docstring's "Agents" section
    and nothing else -- in particular this function never evaluates
    `raw["persistence"]` at all, so the live bearer token that key can hold
    on a real agent file is never assigned to a Python value here, let alone
    stored on `AgentRecord`.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"failed to read {path.name}: {exc}"
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, f"failed to parse {path.name}: {exc}"
    if not isinstance(raw, dict):
        return None, f"{path.name}: not a JSON object"

    def _str(key: str) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) and value else None

    agent_id = _str("id") or path.stem

    model: str | None = None
    config = raw.get("config")
    if isinstance(config, dict):
        model_value = config.get("model")
        model = model_value if isinstance(model_value, str) and model_value else None

    # The session id and cwd become path components under CLAUDE_PROJECTS_DIR /
    # SUBAGENT_TASKS_ROOT (and a glob under CODEX_SESSIONS_DIR), so both are
    # shape-checked here: a session id must be a UUID, a cwd must be absolute.
    # Anything else is treated as "no transcript" rather than trusted.
    session_id: str | None = None
    runtime_info = raw.get("runtimeInfo")
    if isinstance(runtime_info, dict):
        session_value = runtime_info.get("sessionId")
        if isinstance(session_value, str) and AGENT_ID_RE.match(session_value):
            session_id = session_value
    cwd_value = _str("cwd")
    cwd = cwd_value if cwd_value and cwd_value.startswith("/") else None

    last_status_raw = _str("lastStatus")
    last_status = last_status_raw.lower() if last_status_raw else "unknown"

    title_raw = _str("title")
    title = secret_scrub(title_raw) if title_raw else None

    record = AgentRecord(
        id=agent_id,
        provider=_str("provider") or "unknown",
        cwd=cwd,
        workspace_id=_str("workspaceId"),
        title=title,
        created_at=_parse_iso(raw.get("createdAt")),
        updated_at=_parse_iso(raw.get("updatedAt")),
        last_activity_at=_parse_iso(raw.get("lastActivityAt")),
        last_user_message_at=_parse_iso(raw.get("lastUserMessageAt")),
        last_status=last_status,
        model=model,
        session_id=session_id,
    )
    return record, None


def find_agent_record(agent_id: str, *, root: Path | None = None) -> AgentRecord | None:
    """Locate and parse one agent's JSON file by id.

    `agent_id` is validated against `AGENT_ID_RE` *before* it ever reaches
    `Path.glob` -- a malformed or path-traversal-shaped id (`../../etc`)
    simply does not match and returns `None` without touching the
    filesystem, per plan "Build" item 3.
    """
    if not AGENT_ID_RE.match(agent_id):
        return None
    base = root if root is not None else PASEO_AGENTS_DIR
    if not base.is_dir():
        return None
    try:
        matches = sorted(base.glob(f"*/{agent_id}.json"))
    except OSError:
        return None
    if not matches:
        return None
    record, _warning = _load_agent_record(matches[0])
    return record


# --------------------------------------------------------------------------
# Transcript resolution
# --------------------------------------------------------------------------


def _find_codex_transcript(session_id: str, *, root: Path | None = None) -> Path | None:
    base = root if root is not None else CODEX_SESSIONS_DIR
    if not base.is_dir():
        return None
    pattern = f"rollout-*{session_id}.jsonl"
    try:
        for path in base.rglob(pattern):
            if path.is_file():
                return path
    except OSError:
        return None
    return None


def _resolve_transcript(
    record: AgentRecord, *, claude_root: Path | None = None, codex_root: Path | None = None
) -> tuple[TranscriptKind, Path | None]:
    if record.provider == "claude" and record.cwd and record.session_id:
        base = claude_root if claude_root is not None else CLAUDE_PROJECTS_DIR
        path = base / _slugify_cwd(record.cwd) / f"{record.session_id}.jsonl"
        return ("claude", path) if path.is_file() else ("none", None)
    if record.provider == "codex" and record.session_id:
        path = _find_codex_transcript(record.session_id, root=codex_root)
        return ("codex", path) if path is not None else ("none", None)
    return "none", None


def build_agent_activity(
    record: AgentRecord,
    *,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
) -> AgentActivity:
    try:
        kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    except OSError as exc:
        return AgentActivity(
            transcript_kind="none",
            transcript_path=None,
            current_file=None,
            last_text=None,
            last_entry_at=None,
            warning=f"transcript lookup failed for agent {record.id}: {exc}",
        )
    if path is None:
        return AgentActivity(kind, None, None, None, None, None)
    try:
        entries = _read_transcript_entries(kind, path, max_bytes=tail_bytes)
    except OSError as exc:
        return AgentActivity(
            kind,
            path,
            None,
            None,
            None,
            warning=f"failed to read transcript for agent {record.id}: {exc}",
        )
    current_file, last_text, last_entry_at = summarize_activity(entries)
    return AgentActivity(kind, path, current_file, last_text, last_entry_at, None)


# --------------------------------------------------------------------------
# Agents report (the `/agents` list)
# --------------------------------------------------------------------------


def load_agents(
    *,
    root: Path | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    now: datetime | None = None,
    enrich: bool = True,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
) -> AgentsReport:
    """Every agent, sorted and bucketed, per plan "Build" item 1.

    Sort order: running -> error -> idle -> closed, then by most-recent
    activity within each bucket. A closed agent whose last activity is
    older than `CLOSED_STALE_HOURS` is dropped from the list and counted in
    `closed_collapsed_count` instead ("collapsed into a count, not listed").

    `enrich=False` skips transcript resolution/reading entirely (no
    filesystem access beyond the agent JSON files themselves) -- used by the
    persistent top bar's agent-status dots, which render on every screen and
    must stay cheap; the full `/agents` page itself always enriches.
    """
    base = root if root is not None else PASEO_AGENTS_DIR
    moment = now if now is not None else datetime.now(UTC)
    warnings: list[str] = []
    records: list[AgentRecord] = []

    if base.is_dir():
        try:
            paths = sorted(base.glob("*/*.json"))
        except OSError as exc:
            warnings.append(f"failed to list {base}: {exc}")
            paths = []
        for path in paths:
            record, warning = _load_agent_record(path)
            if warning:
                warnings.append(warning)
            if record is not None:
                records.append(record)
    # A missing agents directory is a normal empty state (e.g. a test, or a
    # box with no Paseo agents configured yet), not a warning.

    cutoff = moment - timedelta(hours=CLOSED_STALE_HOURS)
    visible: list[AgentRecord] = []
    collapsed = 0
    for record in records:
        if record.last_status == "closed":
            reference = record.last_activity_at or record.updated_at or record.created_at
            if reference is None or reference < cutoff:
                collapsed += 1
                continue
        visible.append(record)

    def _sort_key(record: AgentRecord) -> tuple[int, float]:
        reference = record.last_activity_at or record.updated_at or record.created_at
        epoch = reference.timestamp() if reference is not None else float("-inf")
        return (_STATE_RANK.get(record.last_status, len(_STATE_RANK)), -epoch)

    visible.sort(key=_sort_key)

    summaries: list[AgentSummary] = []
    for record in visible:
        activity: AgentActivity | None = None
        if enrich and record.last_status != "closed":
            activity = build_agent_activity(
                record, claude_root=claude_root, codex_root=codex_root, tail_bytes=tail_bytes
            )
            if activity.warning:
                warnings.append(activity.warning)
        summaries.append(AgentSummary(record=record, activity=activity))

    return AgentsReport(
        agents=tuple(summaries),
        closed_collapsed_count=collapsed,
        closed_stale_cutoff=cutoff,
        generated_at=moment,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------
# Timeline (detail page + SSE)
# --------------------------------------------------------------------------


def load_timeline(
    agent_id: str,
    since_offset: int = 0,
    *,
    root: Path | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    max_bytes: int = _STREAM_MAX_READ_BYTES,
) -> TimelineChunk:
    """New timeline entries appended to `agent_id`'s transcript since
    `since_offset` (a byte offset), for the SSE stream's polling loop.

    Only ever reads complete lines: if the chunk read from `since_offset` up
    to `max_bytes` further ends mid-line (the writer is still mid-append),
    the trailing partial line is left unconsumed and `next_offset` points
    back to its start, so the next call picks it up whole. A single line
    longer than `max_bytes` is skipped rather than stalling the stream on it
    forever.
    """
    record = find_agent_record(agent_id, root=root)
    if record is None:
        return TimelineChunk(entries=(), next_offset=since_offset, transcript_path=None)
    kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    if path is None:
        return TimelineChunk(entries=(), next_offset=since_offset, transcript_path=None)
    try:
        size = path.stat().st_size
    except OSError:
        return TimelineChunk(entries=(), next_offset=since_offset, transcript_path=path)

    start = min(max(since_offset, 0), size)
    end = min(size, start + max_bytes)
    if end <= start:
        return TimelineChunk(entries=(), next_offset=size, transcript_path=path)

    try:
        with path.open("rb") as handle:
            handle.seek(start)
            chunk = handle.read(end - start)
    except OSError:
        return TimelineChunk(entries=(), next_offset=since_offset, transcript_path=path)

    if chunk.endswith(b"\n"):
        complete, consumed = chunk, len(chunk)
    else:
        last_newline = chunk.rfind(b"\n")
        if last_newline == -1:
            # No newline at all in this read: either nothing new yet (empty
            # chunk) or one line longer than `max_bytes` -- skip past it so
            # the stream never stalls forever on a single oversized line.
            complete, consumed = b"", (len(chunk) if len(chunk) >= max_bytes else 0)
        else:
            complete, consumed = chunk[: last_newline + 1], last_newline + 1

    lines = _iter_jsonl_lines(complete, drop_first=False)
    entries = (
        _entries_from_codex_lines(lines)
        if kind == "codex"
        else _entries_from_claude_style_lines(lines)
    )
    entries = _pair_tool_durations(entries)

    return TimelineChunk(entries=tuple(entries), next_offset=start + consumed, transcript_path=path)


def _entry_to_stream_payload(entry: TimelineEntry) -> dict[str, Any]:
    return {
        "at": format_timeline_time(entry.at),
        "kind": entry.kind,
        "tool_name": entry.tool_name,
        "content": entry.target or entry.detail,
        "duration_seconds": round(entry.duration_seconds, 1)
        if entry.duration_seconds is not None
        else None,
        "is_error": entry.is_error,
    }


def stream_agent_timeline(
    agent_id: str,
    *,
    root: Path | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    poll_interval: float = DEFAULT_SSE_POLL_INTERVAL_SECONDS,
    keepalive_interval: float = DEFAULT_SSE_KEEPALIVE_INTERVAL_SECONDS,
    max_duration: float = DEFAULT_SSE_MAX_DURATION_SECONDS,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Iterator[str]:
    """SSE body for `GET /agents/{agent_id}/stream`.

    A plain synchronous generator (Starlette's `StreamingResponse` iterates
    a sync generator in a thread pool automatically) so it needs no asyncio
    test scaffolding: a test drives it directly with `next()`, passing a
    no-op `sleep` and a controllable `clock` to exercise the 15s keep-alive
    and the 10-minute close without ever actually sleeping.

    Tails `agent_id`'s transcript from its size *at connect time* (not from
    the beginning) -- only entries appended after the client connected are
    ever sent, per plan "Build" item 2 ("tailing the transcript from the
    current end").
    """
    clock_fn = clock if clock is not None else time.monotonic
    sleep_fn = sleep if sleep is not None else time.sleep

    record = find_agent_record(agent_id, root=root)
    if record is None:
        yield ": agent not found\n\n"
        return

    _, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    try:
        offset = path.stat().st_size if path is not None else 0
    except OSError:
        offset = 0

    start = clock_fn()
    last_keepalive = start
    yield ": stream-open\n\n"

    while True:
        now = clock_fn()
        if now - start >= max_duration:
            yield ": stream-closed (max duration reached)\n\n"
            return

        chunk = load_timeline(
            agent_id, offset, root=root, claude_root=claude_root, codex_root=codex_root
        )
        offset = chunk.next_offset
        for entry in chunk.entries:
            yield f"data: {json.dumps(_entry_to_stream_payload(entry))}\n\n"
            last_keepalive = now

        now = clock_fn()
        if now - last_keepalive >= keepalive_interval:
            yield ": keep-alive\n\n"
            last_keepalive = now

        sleep_fn(poll_interval)


# --------------------------------------------------------------------------
# Subagents + agent detail
# --------------------------------------------------------------------------


def load_subagent_tasks(
    record: AgentRecord,
    *,
    root: Path | None = None,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
    max_tasks: int = _MAX_SUBAGENT_TASKS,
) -> tuple[SubagentTask, ...]:
    """Subagent (`Task`-tool) transcripts nested under one main session.

    Degrades to `()` -- rendered as "none" -- if `SUBAGENT_TASKS_ROOT` (a
    `/tmp` tree) or this session's own `tasks/` directory is absent, which
    is the normal state after a reboot, per plan "Ground truth".
    """
    if not record.cwd or not record.session_id:
        return ()
    base = root if root is not None else SUBAGENT_TASKS_ROOT
    tasks_dir = base / _slugify_cwd(record.cwd) / record.session_id / "tasks"
    if not tasks_dir.is_dir():
        return ()
    try:
        paths = sorted(tasks_dir.glob("*.output"))
    except OSError:
        return ()

    tasks: list[SubagentTask] = []
    for path in paths[:max_tasks]:
        try:
            entries: tuple[TimelineEntry, ...] = tuple(
                _read_transcript_entries("claude", path, max_bytes=tail_bytes)
            )
            warning = None
        except OSError as exc:
            entries = ()
            warning = f"failed to read subagent transcript {path.name}: {exc}"
        tasks.append(SubagentTask(id=path.stem, entries=entries, warning=warning))
    return tuple(tasks)


def build_agent_detail(
    agent_id: str,
    *,
    root: Path | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    subagent_root: Path | None = None,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
) -> AgentDetail:
    """Everything `GET /agents/{agent_id}` needs: full timeline + nested
    subagents. `agent_id` is validated by `find_agent_record` (via
    `AGENT_ID_RE`) before any filesystem access.
    """
    record = find_agent_record(agent_id, root=root)
    if record is None:
        return AgentDetail(
            record=None,
            entries=(),
            subagents=(),
            transcript_kind="none",
            transcript_available=False,
            warnings=("agent not found",),
        )

    warnings: list[str] = []
    kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    entries: tuple[TimelineEntry, ...] = ()
    if path is not None:
        try:
            entries = tuple(_read_transcript_entries(kind, path, max_bytes=tail_bytes))
        except OSError as exc:
            warnings.append(f"failed to read transcript: {exc}")
    else:
        warnings.append("no transcript found for this agent")

    try:
        subagents = load_subagent_tasks(record, root=subagent_root, tail_bytes=tail_bytes)
    except OSError as exc:
        subagents = ()
        warnings.append(f"subagent discovery failed: {exc}")

    return AgentDetail(
        record=record,
        entries=entries,
        subagents=subagents,
        transcript_kind=kind,
        transcript_available=path is not None,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------
# Heavy jobs (`scripts/run_capped.sh`)
# --------------------------------------------------------------------------

RunSystemctl = Callable[[Sequence[str]], "str | None"]


def _run_systemctl(args: Sequence[str]) -> str | None:
    """The only subprocess this module ever starts: a read-only, 2s-bounded
    `systemctl` call (plan section 6 / T7 constraints: "the only subprocesses
    allowed are `systemctl list-units` / `systemctl show`, read-only, with a
    2 s timeout").
    """
    try:
        result = subprocess.run(
            ["systemctl", *args],
            capture_output=True,
            text=True,
            timeout=_SYSTEMCTL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def _discover_scope_units(run: RunSystemctl) -> tuple[str, ...]:
    output = run(["list-units", "--type=scope", "--all", "--no-legend"])
    if output is None:
        return ()
    units: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # A failed/degraded unit is prefixed with a bullet marker as its own
        # whitespace-separated token (e.g. "● oomtest1.scope loaded failed
        # failed ..."); strip it before taking the first field so the unit
        # name lands in the same position either way.
        stripped = stripped.lstrip("●⚠").strip()
        first_field = stripped.split(None, 1)[0] if stripped else ""
        if first_field.endswith(".scope"):
            units.append(first_field)
    return tuple(units)


def _unit_is_research_capped(run: RunSystemctl, unit: str) -> bool:
    """`list-units` alone does not show slice membership (measured on this
    box: a `run_capped.sh` scope's unit name is a random hex id, e.g.
    `run-r911bc0ee3bb143a3aa203a429f29cf32.scope`, with no "research-capped"
    substring anywhere in it) -- confirming the slice needs one more
    read-only `systemctl show`, still within the allowed command set.
    """
    output = run(["show", "-p", "Slice", "--value", unit])
    if output is None:
        return False
    return output.strip() == f"{_RESEARCH_CAPPED_SLICE_NAME}.slice"


def _parse_active_enter_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    parts = value.split()
    if not parts:
        return None
    try:
        if parts[-1] == "UTC":
            naive = datetime.strptime(" ".join(parts[:-1]), "%a %Y-%m-%d %H:%M:%S")
            return naive.replace(tzinfo=UTC)
        return datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return None


def _parse_memory_property(value: str) -> int | None:
    value = value.strip()
    if not value or value in ("infinity", "max", "[not set]", "n/a"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def load_heavy_jobs(
    *, run: RunSystemctl | None = None, now: datetime | None = None
) -> HeavyJobsReport:
    """Live `research-capped` scopes, discovered entirely read-only.

    Memory is read via `systemctl show -p MemoryCurrent -p MemoryMax`
    rather than the plan's literal
    `/sys/fs/cgroup/research-capped.slice/<unit>/memory.current` path: on
    this box `research-capped.slice` is nested under `research.slice`
    (confirmed live, 2026-09-20: `systemctl show -p ControlGroup` on a
    freshly started probe scope returned
    `/research.slice/research-capped.slice/<unit>.scope`), so that literal
    path does not exist here. `systemctl show`'s `MemoryCurrent`/`MemoryMax`
    properties report the same cgroup values without hardcoding a slice
    nesting assumption, and are still within the "only `systemctl
    list-units`/`show`" allowlist.
    """
    runner = run if run is not None else _run_systemctl
    moment = now if now is not None else datetime.now(UTC)

    probe = runner(["list-units", "--type=scope", "--all", "--no-legend"])
    if probe is None:
        return HeavyJobsReport(
            jobs=(), available=False, warnings=("systemctl unavailable or timed out",)
        )

    warnings: list[str] = []
    units: list[str] = []
    for unit in _discover_scope_units(runner):
        try:
            if _unit_is_research_capped(runner, unit):
                units.append(unit)
        except Exception as exc:  # a bad unit must not blank the whole section
            warnings.append(f"failed to inspect unit {unit}: {exc}")

    jobs: list[HeavyJob] = []
    for unit in units:
        show = runner(
            ["show", "-p", "ActiveEnterTimestamp", "-p", "MemoryCurrent", "-p", "MemoryMax", unit]
        )
        if show is None:
            jobs.append(
                HeavyJob(
                    unit=unit,
                    started_at=None,
                    elapsed_seconds=None,
                    memory_current_bytes=None,
                    memory_max_bytes=None,
                    memory_max_unlimited=False,
                    warning="systemctl show failed",
                )
            )
            continue
        props: dict[str, str] = {}
        for line in show.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                props[key] = value
        started_at = _parse_active_enter_timestamp(props.get("ActiveEnterTimestamp", ""))
        elapsed = (moment - started_at).total_seconds() if started_at is not None else None
        mem_max_raw = props.get("MemoryMax", "").strip()
        unlimited = mem_max_raw in ("infinity", "max", "[not set]", "", "n/a")
        jobs.append(
            HeavyJob(
                unit=unit,
                started_at=started_at,
                elapsed_seconds=elapsed,
                memory_current_bytes=_parse_memory_property(props.get("MemoryCurrent", "")),
                memory_max_bytes=None if unlimited else _parse_memory_property(mem_max_raw),
                memory_max_unlimited=unlimited,
                warning=None,
            )
        )

    return HeavyJobsReport(jobs=tuple(jobs), available=True, warnings=tuple(warnings))


# --------------------------------------------------------------------------
# Template-facing formatting helpers
# --------------------------------------------------------------------------


def format_elapsed_seconds(seconds: float | None) -> str:
    """Compact duration, e.g. `3h12m`, `45s`, `2d04h`. `None` -> `unknown`."""
    if seconds is None:
        return "unknown"
    total = int(max(0.0, seconds))
    if total < 60:
        return f"{total}s"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def format_timeline_time(value: datetime | None) -> str:
    """`HH:MM:SSZ`, per plan section 3.5's timestamp rule for the timeline."""
    if value is None:
        return "unknown"
    return value.astimezone(UTC).strftime("%H:%M:%S") + "Z"


def agent_state_dot(status: str) -> str:
    """Map an agent's `lastStatus` onto the shared ok/warn/stale/unknown dot
    vocabulary (`open_composer.cockpit.data.health.Status`)."""
    return _STATE_DOT.get(status, "unknown")


__all__ = [
    "AGENT_ID_RE",
    "CLAUDE_PROJECTS_DIR",
    "CLOSED_STALE_HOURS",
    "CODEX_SESSIONS_DIR",
    "DEFAULT_SSE_KEEPALIVE_INTERVAL_SECONDS",
    "DEFAULT_SSE_MAX_DURATION_SECONDS",
    "DEFAULT_SSE_POLL_INTERVAL_SECONDS",
    "PASEO_AGENTS_DIR",
    "SUBAGENT_ID_RE",
    "SUBAGENT_TASKS_ROOT",
    "AgentActivity",
    "AgentDetail",
    "AgentRecord",
    "AgentSummary",
    "AgentsReport",
    "HeavyJob",
    "HeavyJobsReport",
    "SubagentTask",
    "TimelineChunk",
    "TimelineEntry",
    "TranscriptKind",
    "agent_state_dot",
    "build_agent_activity",
    "build_agent_detail",
    "find_agent_record",
    "format_elapsed_seconds",
    "format_timeline_time",
    "load_agents",
    "load_heavy_jobs",
    "load_subagent_tasks",
    "load_timeline",
    "stream_agent_timeline",
    "summarize_activity",
]
