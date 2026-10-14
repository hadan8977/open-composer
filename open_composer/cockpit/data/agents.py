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
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

from open_composer.cockpit.security import secret_scrub
from open_composer.config import project_root

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
#: A non-running, non-closed session whose last activity is older than this is
#: dropped from the list and counted in `AgentsReport.stale_hidden_count`.
STALE_HIDE_HOURS: Final[float] = 72.0
#: An `error` session only counts towards `recent_error_count` (and only keeps
#: its red dot) when its last activity is at most this old.
RECENT_ERROR_HOURS: Final[float] = 24.0
#: Display-title limits (`compute_display_title`).
_DISPLAY_TITLE_CHARS: Final[int] = 80
_DISPLAY_SUBTITLE_TITLE_CHARS: Final[int] = 40
_DISPLAY_SUBTITLE_TEXT_CHARS: Final[int] = 80
#: How much of the latest human message `AgentActivity` keeps (display cuts to 80).
_LAST_HUMAN_KEEP_CHARS: Final[int] = 200
#: A Paseo auto-research round's first prompt starts with this; every round
#: shares one long prompt, so the raw title cannot tell two rounds apart.
_AUTO_ROUND_PREFIX: Final[str] = "Open Composer 自动研究"
_SYSTEM_REMINDER_RE: Final[re.Pattern[str]] = re.compile(
    r"<system-reminder>.*?</system-reminder>", re.DOTALL
)
#: Text that starts with one of these is tooling or an automated report, not a
#: message a person typed.
_NON_HUMAN_PREFIXES: Final[tuple[str, ...]] = (
    "<system-reminder>",
    "<task-notification>",
    "<command-",
    "<local-command",
    "【自动研究轮汇报",
    "【执行轮提醒",
    "<environment_context>",
    "<user_instructions>",
    "# AGENTS.md",
    "[Request interrupted",
    "This session is being continued from a previous conversation",
)
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
#: T10 build item 3: `build_agent_detail` renders at most the last this many
#: parsed entries of the bounded tail it already reads -- a busy session's
#: 256 KiB tail can still hold well over a thousand entries, each of which
#: was being rendered into the page and read again by every nested subagent
#: transcript (see `_MAX_SUBAGENT_TASKS`/`_MAX_SUBAGENT_ENTRIES` below).
_MAX_DETAIL_ENTRIES: Final[int] = 150
#: T10: was 20, sorted by filename (i.e. by nothing meaningful -- subagent
#: ids are random hex, so this was effectively an arbitrary 20, not the 20
#: newest). Now sorted by mtime descending in `load_subagent_tasks`, so this
#: is genuinely "the newest 5".
_MAX_SUBAGENT_TASKS: Final[int] = 5
#: T10: each kept subagent transcript is itself capped to its last this many
#: entries, mirroring `_MAX_DETAIL_ENTRIES` for the main timeline -- with
#: `_MAX_SUBAGENT_TASKS` above, an agent detail page reads at most
#: `_MAX_SUBAGENT_TASKS` transcripts of up to `_TRANSCRIPT_TAIL_BYTES` each,
#: never renders more than this many rows from any one of them.
_MAX_SUBAGENT_ENTRIES: Final[int] = 30

DEFAULT_SSE_POLL_INTERVAL_SECONDS: Final[float] = 2.0
DEFAULT_SSE_KEEPALIVE_INTERVAL_SECONDS: Final[float] = 15.0
DEFAULT_SSE_MAX_DURATION_SECONDS: Final[float] = 600.0

_SYSTEMCTL_TIMEOUT_SECONDS: Final[float] = 2.0
# run_capped.sh slices: research jobs inside the project memory budget since
# 2026-10-07 (oc-research-capped), paper crons (paper-capped), and the old name.
_CAPPED_SLICES: Final[frozenset[str]] = frozenset(
    {"oc-research-capped.slice", "paper-capped.slice", "research-capped.slice"}
)

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
    #: The most recent message a person typed, found in the same bounded tail
    #: (scrubbed, single line, <= `_LAST_HUMAN_KEEP_CHARS`); `None` if the tail
    #: holds none. Input to `compute_display_title`.
    last_human_message: str | None = None


@dataclass(frozen=True)
class AgentSummary:
    """One row of the `/agents` list: an `AgentRecord` plus its activity.

    `activity` is `None` for a closed agent -- `load_agents` only resolves
    and reads a transcript for a non-closed agent (plan "Build", item 1:
    "For each non-closed agent resolve its transcript path").
    """

    record: AgentRecord
    activity: AgentActivity | None
    #: Computed by `compute_display_title` (scrubbed); the raw `record.title`
    #: is the first prompt of the session, which rarely says what it is about.
    display_title: str = ""
    display_subtitle: str | None = None
    #: `True` for an `error` session whose last activity is within
    #: `RECENT_ERROR_HOURS`; an older error renders as a grey idle dot.
    recent_error: bool = False


@dataclass(frozen=True)
class AgentsReport:
    agents: tuple[AgentSummary, ...]
    closed_collapsed_count: int
    closed_stale_cutoff: datetime
    generated_at: datetime
    warnings: tuple[str, ...]
    #: Sessions whose `cwd` is missing or outside the project root. Not listed,
    #: not counted in any state.
    other_project_hidden_count: int = 0
    #: Non-running, non-closed sessions with no activity for `STALE_HIDE_HOURS`.
    stale_hidden_count: int = 0
    #: Visible `error` sessions with activity in the last `RECENT_ERROR_HOURS`.
    recent_error_count: int = 0


@dataclass(frozen=True)
class TimelineChunk:
    """One bounded read of a transcript, for the SSE stream's polling loop."""

    entries: tuple[TimelineEntry, ...]
    next_offset: int
    transcript_path: Path | None


@dataclass(frozen=True)
class SubagentTask:
    """One nested subagent transcript (T10: capped to the last
    `_MAX_SUBAGENT_ENTRIES` of `entries_total` parsed entries -- see
    `load_subagent_tasks`). `entries_total` is the count within the
    already-bounded tail this module ever reads (`_TRANSCRIPT_TAIL_BYTES`),
    not a full-file count -- the same "of what we scanned" honesty the rest
    of this module already applies (module docstring's bounded-read design).
    """

    id: str
    entries: tuple[TimelineEntry, ...]
    entries_total: int
    warning: str | None


@dataclass(frozen=True)
class AgentDetail:
    """T10: `entries` is capped to the last `_MAX_DETAIL_ENTRIES` of
    `entries_total` parsed from the transcript's own bounded tail read --
    the template renders both as `"{len(entries)} of {entries_total}
    entries"` (numbers only, never a sentence -- plan section 3.5).
    """

    record: AgentRecord | None
    entries: tuple[TimelineEntry, ...]
    entries_total: int
    subagents: tuple[SubagentTask, ...]
    transcript_kind: TranscriptKind
    transcript_available: bool
    warnings: tuple[str, ...]
    display_title: str = ""
    display_subtitle: str | None = None


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


#: T10 build item 6: every character that is not alphanumeric or `-` (not
#: just `/`) maps to `-` -- Claude Code's own project-directory slug for a
#: `cwd` that itself contains a character such as `.` (a naive `/`-only
#: replace would leave that character in the directory name, which does not
#: match how the CLI actually names the directory). No real example with a
#: `.` exists under `~/.claude/projects` on this box (checked 2026-09-20:
#: every entry here is a plain path with no dots), so this is implemented
#: per the brief without a live example to verify against, and is only ever
#: tried as a fallback after the naive `_slugify_cwd` directory is confirmed
#: absent -- it can only add a second chance to find a real transcript,
#: never take priority over the already-verified convention.
_CWD_SLUG_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9-]")


def _slugify_cwd_fallback(cwd: str) -> str:
    return _CWD_SLUG_FALLBACK_RE.sub("-", cwd)


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
            elif isinstance(block, dict) and isinstance(block.get("type"), str):
                # Binary blocks (screenshots come back as base64 image
                # blocks) are named, never dumped: a 400-char slice of
                # base64 tells the reader nothing.
                parts.append(f"[{block['type']}]")
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


def _human_text(text: str) -> str | None:
    """One message block's human-typed text, or `None` if it is not one.

    Embedded `<system-reminder>` blocks are removed first; what is left must be
    non-blank and must not start with a tooling/automation prefix.
    """
    cleaned = _SYSTEM_REMINDER_RE.sub("", text).strip()
    if not cleaned or cleaned.startswith(_NON_HUMAN_PREFIXES):
        return None
    return cleaned


def _claude_user_line_human_text(line: dict[str, Any]) -> str | None:
    if line.get("type") != "user" or line.get("isMeta") or line.get("isCompactSummary"):
        return None
    message = line.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    blocks: list[str] = []
    if isinstance(content, str):
        blocks.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                return None  # a tool's reply, never a person
            text = block.get("text")
            if block.get("type") == "text" and isinstance(text, str):
                blocks.append(text)
    kept = [t for t in (_human_text(b) for b in blocks) if t]
    return "\n".join(kept) if kept else None


def _codex_line_human_text(line: dict[str, Any]) -> str | None:
    if line.get("type") != "response_item":
        return None
    payload = line.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    if payload.get("role") != "user":
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    blocks = [
        block["text"]
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    kept = [t for t in (_human_text(b) for b in blocks) if t]
    return "\n".join(kept) if kept else None


def last_human_message(kind: TranscriptKind, lines: list[dict[str, Any]]) -> str | None:
    """The most recent message a person typed, from already-parsed tail lines.

    Excludes tool results, `<system-reminder>`/`<task-notification>`/
    `<command-*>`/`<local-command*>` text, the automatic `【自动研究轮汇报` and
    `【执行轮提醒` reports and blank messages. Returns a scrubbed, single-line
    string (at most `_LAST_HUMAN_KEEP_CHARS`), or `None`.
    """
    extract = _codex_line_human_text if kind == "codex" else _claude_user_line_human_text
    for line in reversed(lines):
        text = extract(line)
        if text:
            return _finalize_text(" ".join(text.split()), limit=_LAST_HUMAN_KEEP_CHARS) or None
    return None


#: A long interactive session's 256 KiB tail is often all tool output, with no
#: human message in it. When the tail has none, look further back for the last
#: one -- at most this far from the end of the file, in chunks, never holding
#: more than one chunk in memory.
_HUMAN_SCAN_MAX_BYTES: Final[int] = 16 * 1024 * 1024
_HUMAN_SCAN_CHUNK_BYTES: Final[int] = 1024 * 1024
_human_scan_cache: dict[str, tuple[int, str | None]] = {}
_human_scan_lock = threading.Lock()


def _scan_human_region(kind: TranscriptKind, path: Path, start: int, end: int) -> str | None:
    """Last human message among the complete lines in bytes `[start, end)`.

    `start` must be a line boundary. Reads backwards one chunk at a time and
    only parses lines that mention a user role and carry no `tool_result`.
    """
    extract = _codex_line_human_text if kind == "codex" else _claude_user_line_human_text
    with path.open("rb") as handle:
        carry = b""
        pos = end
        while pos > start:
            low = max(start, pos - _HUMAN_SCAN_CHUNK_BYTES)
            handle.seek(low)
            parts = (handle.read(pos - low) + carry).split(b"\n")
            if low > start:
                carry, parts = parts[0], parts[1:]
            else:
                carry = b""
            for raw in reversed(parts):
                if b'"user"' not in raw or b'"tool_result"' in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                text = extract(obj)
                if text:
                    return (
                        _finalize_text(" ".join(text.split()), limit=_LAST_HUMAN_KEEP_CHARS) or None
                    )
            pos = low
    return None


def _scan_human_beyond_tail(kind: TranscriptKind, path: Path) -> str | None:
    """`last_human_message` for a transcript whose tail held none.

    Incremental: the result and the size scanned so far are cached per path,
    so a growing live transcript only re-reads what was appended since.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 1))
            ends_clean = size == 0 or handle.read(1) == b"\n"
    except OSError:
        return None
    key = str(path)
    with _human_scan_lock:
        cached = _human_scan_cache.get(key)
    try:
        if cached is not None and cached[0] <= size:
            scanned, found = cached
            fresh = _scan_human_region(kind, path, scanned, size) if size > scanned else None
            found = fresh or found
        else:
            found = _scan_human_region(kind, path, max(0, size - _HUMAN_SCAN_MAX_BYTES), size)
    except OSError:
        return None
    # A last line without its newline may still be growing: do not cache a
    # scan position in the middle of it.
    if ends_clean:
        with _human_scan_lock:
            if len(_human_scan_cache) > 256:
                _human_scan_cache.clear()
            _human_scan_cache[key] = (size, found)
    return found


def _read_transcript(
    kind: TranscriptKind, path: Path, *, max_bytes: int, scan_beyond_tail: bool = True
) -> tuple[list[TimelineEntry], str | None]:
    """One bounded tail read -> `(entries, last human message)`."""
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
    human = last_human_message(kind, lines)
    if human is None and truncated and scan_beyond_tail:
        human = _scan_human_beyond_tail(kind, path)
    return _pair_tool_durations(entries), human


def _read_transcript_entries(
    kind: TranscriptKind, path: Path, *, max_bytes: int
) -> list[TimelineEntry]:
    return _read_transcript(kind, path, max_bytes=max_bytes, scan_beyond_tail=False)[0]


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
        naive_slug = _slugify_cwd(record.cwd)
        path = base / naive_slug / f"{record.session_id}.jsonl"
        if path.is_file():
            return "claude", path
        # T10 build item 6: the naive `/`-only slug did not exist -- try
        # Claude Code's broader slug convention before giving up.
        fallback_slug = _slugify_cwd_fallback(record.cwd)
        if fallback_slug != naive_slug:
            fallback_path = base / fallback_slug / f"{record.session_id}.jsonl"
            if fallback_path.is_file():
                return "claude", fallback_path
        return "none", None
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
        entries, human = _read_transcript(kind, path, max_bytes=tail_bytes)
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
    return AgentActivity(kind, path, current_file, last_text, last_entry_at, None, human)


def _single_line(text: str, limit: int) -> str:
    return _finalize_text(" ".join(text.split()), limit=limit)


def _first_line(text: str, limit: int) -> str | None:
    for raw in text.splitlines():
        if raw.strip():
            return _finalize_text(raw.strip(), limit=limit) or None
    return None


def compute_display_title(
    record: AgentRecord,
    *,
    last_human: str | None = None,
    last_assistant_text: str | None = None,
) -> tuple[str, str | None]:
    """`(display_title, display_subtitle)` for one session; pure, scrubbed.

    * Auto-research round (raw title starts with `Open Composer 自动研究轮`):
      `主审轮`/`执行轮`/`研究轮` + ` · MM-DD HH:MM UTC` of `created_at`; the
      subtitle is the first line of the last assistant message (80 chars).
    * Otherwise the latest human message (80 chars, one line) with the subtitle
      `起始：` + the raw title (40 chars). Without a human message it is the raw
      title and no subtitle.
    """
    raw_title = record.title or ""
    if raw_title.startswith(_AUTO_ROUND_PREFIX):
        if "轮次类型：主审轮" in raw_title:
            label = "主审轮"
        elif "轮次类型：执行轮" in raw_title:
            label = "执行轮"
        else:
            label = "研究轮"
        stamp = record.created_at or record.updated_at
        title = label if stamp is None else f"{label} · {stamp.astimezone(UTC):%m-%d %H:%M} UTC"
        subtitle = (
            _first_line(last_assistant_text, _DISPLAY_SUBTITLE_TEXT_CHARS)
            if (last_assistant_text)
            else None
        )
        return title, subtitle

    fallback = _single_line(raw_title, 400) or record.id[:8]
    if last_human:
        title = _single_line(last_human, _DISPLAY_TITLE_CHARS)
        if title:
            subtitle = (
                "起始：" + _single_line(raw_title, _DISPLAY_SUBTITLE_TITLE_CHARS)
                if raw_title.strip() and _single_line(raw_title, 400) != title
                else None
            )
            return title, subtitle
    return fallback, None


#: The Now screen's live card: how many of a running session's latest tool
#: calls it shows, and how much transcript tail it reads to find them.
_LIVE_TOOL_COUNT: Final[int] = 4
_LIVE_TAIL_BYTES: Final[int] = 128 * 1024


@dataclass(frozen=True)
class LiveSession:
    """A running session for the Now screen: its record, what it is doing
    (`activity`), and its last few tool calls, oldest first."""

    record: AgentRecord
    activity: AgentActivity
    recent_tools: tuple[TimelineEntry, ...]
    display_title: str = ""
    display_subtitle: str | None = None


def build_live_session(
    record: AgentRecord,
    *,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    tools: int = _LIVE_TOOL_COUNT,
    tail_bytes: int = _LIVE_TAIL_BYTES,
) -> LiveSession:
    """One bounded tail read, shared by the activity summary and the tool feed."""
    empty = AgentActivity("none", None, None, None, None, None)
    base_title, base_subtitle = compute_display_title(record)
    try:
        kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    except OSError as exc:
        return LiveSession(
            record,
            replace(empty, warning=f"transcript lookup failed: {exc}"),
            (),
            base_title,
            base_subtitle,
        )
    if path is None:
        return LiveSession(
            record, replace(empty, transcript_kind=kind), (), base_title, base_subtitle
        )
    try:
        entries, human = _read_transcript(kind, path, max_bytes=tail_bytes)
    except OSError as exc:
        activity = AgentActivity(kind, path, None, None, None, f"transcript unreadable: {exc}")
        return LiveSession(record, activity, (), base_title, base_subtitle)
    current_file, last_text, last_entry_at = summarize_activity(entries)
    activity = AgentActivity(kind, path, current_file, last_text, last_entry_at, None, human)
    recent = [entry for entry in entries if entry.kind == "tool"][-tools:] if tools > 0 else []
    title, subtitle = compute_display_title(record, last_human=human, last_assistant_text=last_text)
    return LiveSession(record, activity, tuple(recent), title, subtitle)


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
    project_root_path: Path | None = None,
) -> AgentsReport:
    """This project's agents, sorted and bucketed, per plan "Build" item 1.

    Only sessions whose `cwd` is inside the project root are kept; the rest
    (including a missing `cwd`) are counted in `other_project_hidden_count`.
    Among the kept ones:

    * a closed agent whose last activity is older than `CLOSED_STALE_HOURS`
      is counted in `closed_collapsed_count`, not listed;
    * any other non-running agent idle for more than `STALE_HIDE_HOURS` is
      counted in `stale_hidden_count`, not listed; running agents always show;
    * `recent_error_count` counts visible `error` agents active within
      `RECENT_ERROR_HOURS`; an older visible error sorts and draws as idle.

    Sort order: running -> error -> idle -> closed, then by most-recent
    activity within each bucket.

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
    stale_cutoff = moment - timedelta(hours=STALE_HIDE_HOURS)
    error_cutoff = moment - timedelta(hours=RECENT_ERROR_HOURS)
    root_path = (project_root_path if project_root_path is not None else project_root()).resolve()
    inside_cache: dict[str, bool] = {}

    def _in_project(cwd: str | None) -> bool:
        if not cwd:
            return False
        if cwd not in inside_cache:
            try:
                inside_cache[cwd] = Path(cwd).resolve().is_relative_to(root_path)
            except (OSError, RuntimeError, ValueError):
                inside_cache[cwd] = False
        return inside_cache[cwd]

    def _reference(record: AgentRecord) -> datetime | None:
        return record.last_activity_at or record.updated_at or record.created_at

    def _is_recent_error(record: AgentRecord) -> bool:
        reference = _reference(record)
        return record.last_status == "error" and reference is not None and reference >= error_cutoff

    visible: list[AgentRecord] = []
    collapsed = 0
    stale_hidden = 0
    other_project = 0
    for record in records:
        if not _in_project(record.cwd):
            other_project += 1
            continue
        reference = _reference(record)
        if record.last_status == "closed":
            if reference is None or reference < cutoff:
                collapsed += 1
                continue
        elif record.last_status != "running" and (reference is None or reference < stale_cutoff):
            stale_hidden += 1
            continue
        visible.append(record)

    def _sort_key(record: AgentRecord) -> tuple[int, float]:
        reference = _reference(record)
        epoch = reference.timestamp() if reference is not None else float("-inf")
        status = record.last_status
        if status == "error" and not _is_recent_error(record):
            status = "idle"
        return (_STATE_RANK.get(status, len(_STATE_RANK)), -epoch)

    visible.sort(key=_sort_key)

    summaries: list[AgentSummary] = []
    recent_errors = 0
    for record in visible:
        activity: AgentActivity | None = None
        if enrich and record.last_status != "closed":
            activity = build_agent_activity(
                record, claude_root=claude_root, codex_root=codex_root, tail_bytes=tail_bytes
            )
            if activity.warning:
                warnings.append(activity.warning)
        title, subtitle = compute_display_title(
            record,
            last_human=activity.last_human_message if activity else None,
            last_assistant_text=activity.last_text if activity else None,
        )
        recent = _is_recent_error(record)
        recent_errors += 1 if recent else 0
        summaries.append(
            AgentSummary(
                record=record,
                activity=activity,
                display_title=title,
                display_subtitle=subtitle,
                recent_error=recent,
            )
        )

    return AgentsReport(
        agents=tuple(summaries),
        closed_collapsed_count=collapsed,
        closed_stale_cutoff=cutoff,
        generated_at=moment,
        warnings=tuple(warnings),
        other_project_hidden_count=other_project,
        stale_hidden_count=stale_hidden,
        recent_error_count=recent_errors,
    )


def display_status(summary: AgentSummary) -> str:
    """The state every screen draws and counts: `record.last_status`, except
    an `error` older than `RECENT_ERROR_HOURS` reads as `idle`."""
    status = summary.record.last_status
    return "idle" if status == "error" and not summary.recent_error else status


def count_display_states(report: AgentsReport) -> dict[str, int]:
    """Listed sessions per `display_status` (hidden ones are not counted)."""
    counts = {"running": 0, "idle": 0, "error": 0, "closed": 0}
    for summary in report.agents:
        state = display_status(summary)
        counts[state] = counts.get(state, 0) + 1
    return counts


#: T10 build item 5: how long `TopbarAgentsCache` reuses a `load_agents(enrich=False)`
#: result. `_topbar_agents` (`open_composer.cockpit.app`) renders this on
#: every screen, and parsing every agent JSON file (~230 on this box, ~0.3s)
#: on every request was measured as one of the cheaper-but-still-real costs
#: this task set out to remove from the request path.
_TOPBAR_AGENTS_CACHE_TTL_SECONDS: Final[float] = 10.0


class TopbarAgentsCache:
    """A short-lived cache for `load_agents(enrich=False)` (T10 build item 5).

    The brief's preferred fix was to `stat()` every agent file first and
    skip *parsing* any whose mtime is older than `CLOSED_STALE_HOURS` --
    cheap if a non-closed agent's JSON file is reliably rewritten on
    activity. Measured against this box's real `~/.paseo/agents` on
    2026-09-20, that assumption does not hold: of 21 non-closed (running
    /idle/error) agents, 19 had a file mtime *older* than `CLOSED_STALE_HOURS`
    (up to ~3 000 hours old) even though their own `lastStatus` was not
    `"closed"` -- an mtime-based skip would have silently dropped most of
    this box's idle agents from the top bar's status-dot row. This class is
    the brief's documented fallback instead: cache the full, correctly-parsed
    `load_agents(enrich=False)` result for `_TOPBAR_AGENTS_CACHE_TTL_SECONDS`,
    guarded by a lock so concurrent requests during a real box's normal
    traffic never trigger more than one re-parse per TTL period.
    """

    def __init__(self) -> None:
        self._report: AgentsReport | None = None
        self._computed_at: datetime | None = None
        self._lock = threading.Lock()

    def get(self, *, now: datetime | None = None, root: Path | None = None) -> AgentsReport:
        moment = now if now is not None else datetime.now(UTC)
        with self._lock:
            if self._report is not None and self._computed_at is not None:
                age = (moment - self._computed_at).total_seconds()
                if 0 <= age < _TOPBAR_AGENTS_CACHE_TTL_SECONDS:
                    return self._report
            report = load_agents(root=root, now=moment, enrich=False)
            self._report = report
            self._computed_at = moment
            return report


_DEFAULT_TOPBAR_AGENTS_CACHE = TopbarAgentsCache()


def get_default_topbar_agents_cache() -> TopbarAgentsCache:
    """The process-wide cache `open_composer.cockpit.app` shares across requests.

    A function, not a bare module attribute, for the same reason as
    `open_composer.cockpit.data.quota.get_default_claude_cache`: a test can
    monkeypatch this name to hand out a fresh, isolated instance instead of
    the one long-lived instance a real server keeps for its entire run.
    """
    return _DEFAULT_TOPBAR_AGENTS_CACHE


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
    path: Path | None = None,
    kind: TranscriptKind | None = None,
) -> TimelineChunk:
    """New timeline entries appended to `agent_id`'s transcript since
    `since_offset` (a byte offset), for the SSE stream's polling loop.

    Only ever reads complete lines: if the chunk read from `since_offset` up
    to `max_bytes` further ends mid-line (the writer is still mid-append),
    the trailing partial line is left unconsumed and `next_offset` points
    back to its start, so the next call picks it up whole. A single line
    longer than `max_bytes` is skipped rather than stalling the stream on it
    forever.

    T10 build item 4: `path` (with its matching `kind`), when both given,
    is used directly instead of re-resolving the transcript from `agent_id`
    -- `stream_agent_timeline` resolves the record and transcript path once
    at connect time and passes both here on every poll, so the
    `find_agent_record` glob over `PASEO_AGENTS_DIR` (and, for a Codex
    agent, `_find_codex_transcript`'s `rglob`) no longer repeats every
    `poll_interval`. Every other caller (the default, `path=None`) keeps the
    pre-T10 behavior of resolving from `agent_id` on every call.
    """
    if path is not None:
        resolved_kind: TranscriptKind = kind if kind is not None else "none"
    else:
        record = find_agent_record(agent_id, root=root)
        if record is None:
            return TimelineChunk(entries=(), next_offset=since_offset, transcript_path=None)
        resolved_kind, path = _resolve_transcript(
            record, claude_root=claude_root, codex_root=codex_root
        )
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
        if resolved_kind == "codex"
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

    kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
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

        # T10 build item 4: `record`/`path`/`kind` were already resolved once
        # above, at connect time -- passed straight through on every poll so
        # `load_timeline` never repeats the `find_agent_record` glob (nor,
        # for a Codex agent, the `_find_codex_transcript` `rglob`).
        chunk = load_timeline(agent_id, offset, path=path, kind=kind)
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


def _resolve_subagent_tasks_dir(base: Path, cwd: str, session_id: str) -> Path | None:
    """The `tasks/` directory for one session, trying the naive slug first
    and Claude Code's alternate slug (T10 build item 6, mirrors
    `_resolve_transcript`'s fallback) if that does not exist.
    """
    naive = base / _slugify_cwd(cwd) / session_id / "tasks"
    if naive.is_dir():
        return naive
    fallback_slug = _slugify_cwd_fallback(cwd)
    if fallback_slug != _slugify_cwd(cwd):
        fallback = base / fallback_slug / session_id / "tasks"
        if fallback.is_dir():
            return fallback
    return None


def load_subagent_tasks(
    record: AgentRecord,
    *,
    root: Path | None = None,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
    max_tasks: int = _MAX_SUBAGENT_TASKS,
    max_entries: int = _MAX_SUBAGENT_ENTRIES,
) -> tuple[SubagentTask, ...]:
    """Subagent (`Task`-tool) transcripts nested under one main session.

    Degrades to `()` -- rendered as "none" -- if `SUBAGENT_TASKS_ROOT` (a
    `/tmp` tree) or this session's own `tasks/` directory is absent, which
    is the normal state after a reboot, per plan "Ground truth".

    T10: kept the newest `max_tasks` by *mtime*, descending -- a subagent
    id is a random hex string (`SUBAGENT_ID_RE`), so the previous
    `sorted(paths)[:max_tasks]` (lexical, by filename) picked an arbitrary
    `max_tasks` rather than the most recent ones. Each kept task's own
    entries are further capped to the last `max_entries` (of however many
    were parsed from its own bounded `tail_bytes` read) -- see
    `SubagentTask.entries_total`.
    """
    if not record.cwd or not record.session_id:
        return ()
    base = root if root is not None else SUBAGENT_TASKS_ROOT
    tasks_dir = _resolve_subagent_tasks_dir(base, record.cwd, record.session_id)
    if tasks_dir is None:
        return ()
    try:
        candidates = [p for p in tasks_dir.glob("*.output") if p.is_file()]
    except OSError:
        return ()

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    candidates.sort(key=_mtime, reverse=True)

    tasks: list[SubagentTask] = []
    for path in candidates[:max_tasks]:
        try:
            all_entries: tuple[TimelineEntry, ...] = tuple(
                _read_transcript_entries("claude", path, max_bytes=tail_bytes)
            )
            warning = None
        except OSError as exc:
            all_entries = ()
            warning = f"failed to read subagent transcript {path.name}: {exc}"
        total = len(all_entries)
        capped = all_entries[-max_entries:] if total > max_entries else all_entries
        tasks.append(
            SubagentTask(id=path.stem, entries=capped, entries_total=total, warning=warning)
        )
    return tuple(tasks)


def build_agent_detail(
    agent_id: str,
    *,
    root: Path | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
    subagent_root: Path | None = None,
    tail_bytes: int = _TRANSCRIPT_TAIL_BYTES,
    max_entries: int = _MAX_DETAIL_ENTRIES,
) -> AgentDetail:
    """Everything `GET /agents/{agent_id}` needs: full timeline + nested
    subagents. `agent_id` is validated by `find_agent_record` (via
    `AGENT_ID_RE`) before any filesystem access.

    T10: `entries` is capped to the last `max_entries` of however many were
    parsed from the transcript's own bounded `tail_bytes` read (`entries_total`
    keeps the pre-cap count so the template can render "`N` of `M` entries").
    """
    record = find_agent_record(agent_id, root=root)
    if record is None:
        return AgentDetail(
            record=None,
            entries=(),
            entries_total=0,
            subagents=(),
            transcript_kind="none",
            transcript_available=False,
            warnings=("agent not found",),
        )

    warnings: list[str] = []
    kind, path = _resolve_transcript(record, claude_root=claude_root, codex_root=codex_root)
    entries: tuple[TimelineEntry, ...] = ()
    entries_total = 0
    human: str | None = None
    last_text: str | None = None
    if path is not None:
        try:
            parsed, human = _read_transcript(kind, path, max_bytes=tail_bytes)
            all_entries = tuple(parsed)
            last_text = summarize_activity(all_entries)[1]
            entries_total = len(all_entries)
            entries = all_entries[-max_entries:] if entries_total > max_entries else all_entries
        except OSError as exc:
            warnings.append(f"failed to read transcript: {exc}")
    else:
        warnings.append("no transcript found for this agent")

    try:
        subagents = load_subagent_tasks(record, root=subagent_root, tail_bytes=tail_bytes)
    except OSError as exc:
        subagents = ()
        warnings.append(f"subagent discovery failed: {exc}")

    display_title, display_subtitle = compute_display_title(
        record, last_human=human, last_assistant_text=last_text
    )
    return AgentDetail(
        record=record,
        entries=entries,
        entries_total=entries_total,
        subagents=subagents,
        transcript_kind=kind,
        transcript_available=path is not None,
        warnings=tuple(warnings),
        display_title=display_title,
        display_subtitle=display_subtitle,
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
    return output.strip() in _CAPPED_SLICES


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


def format_entry_count(n: int) -> str:
    """An exact integer count with a space thousands-separator, e.g. `1 204`.

    T10 build item 3: the agent-detail/subagent-task section headers show
    truncation as numbers only (`"150 of 1 204 entries"`), never a sentence
    (plan section 3.5) -- this is the one formatting helper both counts in
    that header go through. Unlike `quota.format_compact_token_count`, this
    is never rounded to a `k`/`M` unit: an entry count is small enough, and
    exact enough, that "204" should not become "0.2k".
    """
    return f"{max(0, int(n)):,}".replace(",", " ")


__all__ = [
    "AGENT_ID_RE",
    "CLAUDE_PROJECTS_DIR",
    "CLOSED_STALE_HOURS",
    "RECENT_ERROR_HOURS",
    "STALE_HIDE_HOURS",
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
    "LiveSession",
    "SubagentTask",
    "TimelineChunk",
    "TimelineEntry",
    "TopbarAgentsCache",
    "TranscriptKind",
    "agent_state_dot",
    "build_agent_activity",
    "build_agent_detail",
    "build_live_session",
    "compute_display_title",
    "count_display_states",
    "display_status",
    "find_agent_record",
    "format_elapsed_seconds",
    "format_entry_count",
    "format_timeline_time",
    "get_default_topbar_agents_cache",
    "last_human_message",
    "load_agents",
    "load_heavy_jobs",
    "load_subagent_tasks",
    "load_timeline",
    "stream_agent_timeline",
    "summarize_activity",
]
