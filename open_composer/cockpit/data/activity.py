"""24-hour model-call field for the cockpit's Now and Agents screens (2026-09-24).

One pair of numbers per 10-minute bucket over the last 24 hours: how many
distinct Claude model calls were logged (assistant messages, deduplicated by
``message.id``) and how many fresh tokens they used (``input + output +
cache_creation``, the same definition `open_composer.cockpit.data.quota`
uses -- cache reads are never folded in). Both come from the same local
transcripts the quota estimate reads: every main-session transcript at
``<projects>/<slug>/<session>.jsonl`` and every subagent transcript at
``<projects>/<slug>/<session>/subagents/*.jsonl``.

Reading strategy. Transcripts are append-only, so each file keeps a byte
cursor between refreshes: the first pass reads at most
`_FIRST_READ_MAX_BYTES` from the end of each in-window file, and every later
pass reads only what was appended since (a busy box appends a few MB an hour,
while a cold 24-hour scan is ~80 MB). A file whose mtime is older than the
window cannot hold an in-window line and is never opened. A file that shrank
or was replaced (new inode) is re-read from scratch. If a first read had to
start past a file's beginning while the window still reached further back,
the field is flagged ``partial`` rather than silently undercounting.

Like every other cockpit data module this never raises for a missing or
unreadable source: an absent projects tree is an empty field, an unreadable
file is skipped, and a malformed line is ignored. Tests neutralize the
projects root through ``quota.CLAUDE_PROJECTS_DIR`` (see ``tests/conftest.py``),
which this module reads at call time for exactly that reason.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from open_composer.cockpit.data import quota

BUCKET_MINUTES: Final[int] = 10
WINDOW_HOURS: Final[int] = 24
BUCKETS: Final[int] = WINDOW_HOURS * 60 // BUCKET_MINUTES
ACTIVITY_CACHE_TTL_SECONDS: Final[float] = 60.0

_BUCKET_SECONDS: Final[int] = BUCKET_MINUTES * 60
_MAIN_GLOB: Final[str] = "*/*.jsonl"
_SUBAGENT_GLOB: Final[str] = "*/*/subagents/*.jsonl"
_MAX_FILES: Final[int] = 400
_FIRST_READ_MAX_BYTES: Final[int] = 32 * 1024 * 1024
_READ_BLOCK_BYTES: Final[int] = 64 * 1024
_MAX_LINE_BYTES: Final[int] = 4 * 1024 * 1024
_RECENT_IDS: Final[int] = 64


@dataclass(frozen=True)
class ActivityField:
    """Model calls and fresh tokens per bucket, oldest bucket first.

    The last bucket is the one in progress (it ends after ``generated_at``).
    ``files`` counts the transcripts that contributed to the window.
    """

    window_start: datetime
    window_end: datetime
    bucket_minutes: int
    calls: tuple[int, ...]
    fresh: tuple[int, ...]
    total_calls: int
    peak_calls: int
    total_fresh: int
    peak_fresh: int
    files: int
    partial: bool
    generated_at: datetime

    @property
    def available(self) -> bool:
        return self.total_calls > 0

    def bucket_start(self, index: int) -> datetime:
        return self.window_start + timedelta(minutes=self.bucket_minutes * index)


@dataclass
class _Cursor:
    inode: int
    offset: int
    skip_fragment: bool
    partial: bool
    first_read: bool = True
    calls: dict[int, int] = field(default_factory=dict)
    fresh: dict[int, int] = field(default_factory=dict)
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=_RECENT_IDS))
    last_id: str | None = None
    last_slot: int = 0
    last_fresh: int = 0


def _slot_of(moment: datetime) -> int:
    return int(moment.timestamp() // _BUCKET_SECONDS)


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _usage_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _fresh_tokens(message: dict[str, Any]) -> int:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return 0
    return (
        _usage_int(usage.get("input_tokens"))
        + _usage_int(usage.get("output_tokens"))
        + _usage_int(usage.get("cache_creation_input_tokens"))
    )


def _consume(line: bytes, cursor: _Cursor, start_slot: int) -> datetime | None:
    """Fold one transcript line into `cursor`; returns its timestamp, if any."""
    if b'"assistant"' not in line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    message = obj.get("message")
    at = _parse_ts(obj.get("timestamp"))
    if not isinstance(message, dict) or at is None:
        return None
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return at
    fresh = _fresh_tokens(message)
    if message_id == cursor.last_id:
        # One call logged as several adjacent lines sharing one usage
        # object: the last line's usage is the call's usage (quota.py's
        # "last wins" rule), so replace rather than add.
        if cursor.last_slot >= start_slot:
            cursor.fresh[cursor.last_slot] = (
                cursor.fresh.get(cursor.last_slot, 0) - cursor.last_fresh + fresh
            )
        cursor.last_fresh = fresh
        return at
    if message_id in cursor.recent:
        return at
    cursor.recent.append(message_id)
    slot = _slot_of(at)
    cursor.last_id, cursor.last_slot, cursor.last_fresh = message_id, slot, fresh
    if slot >= start_slot:
        cursor.calls[slot] = cursor.calls.get(slot, 0) + 1
        cursor.fresh[slot] = cursor.fresh.get(slot, 0) + fresh
    return at


def _advance(path: Path, cursor: _Cursor | None, start_slot: int) -> _Cursor | None:
    """Read whatever `path` gained since `cursor` and fold it in."""
    try:
        stat = path.stat()
    except OSError:
        return None
    if cursor is None or stat.st_ino != cursor.inode or stat.st_size < cursor.offset:
        begin = max(0, stat.st_size - _FIRST_READ_MAX_BYTES)
        cursor = _Cursor(inode=stat.st_ino, offset=begin, skip_fragment=begin > 0, partial=False)
    if stat.st_size == cursor.offset:
        cursor.first_read = False
        return cursor
    earliest: datetime | None = None
    try:
        with path.open("rb", buffering=_READ_BLOCK_BYTES) as handle:
            handle.seek(cursor.offset)
            position = cursor.offset
            while True:
                line = handle.readline(_MAX_LINE_BYTES)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    if len(line) < _MAX_LINE_BYTES:
                        # A line still being written: leave it for the next pass.
                        break
                    # An oversized line: drop it, and its remainder after it.
                    position += len(line)
                    cursor.skip_fragment = True
                    continue
                position += len(line)
                if cursor.skip_fragment:
                    cursor.skip_fragment = False
                    continue
                at = _consume(line, cursor, start_slot)
                if at is not None and (earliest is None or at < earliest):
                    earliest = at
            cursor.offset = position
    except OSError:
        return cursor
    if cursor.first_read:
        started_late = cursor.offset > 0 and stat.st_size > _FIRST_READ_MAX_BYTES
        cursor.partial = started_late and (earliest is None or _slot_of(earliest) >= start_slot)
        cursor.first_read = False
    return cursor


def _candidates(root: Path, window_start: datetime) -> list[Path]:
    if not root.is_dir():
        return []
    cutoff = window_start.timestamp()
    found: list[tuple[float, Path]] = []
    for pattern in (_MAIN_GLOB, _SUBAGENT_GLOB):
        try:
            paths = list(root.glob(pattern))
        except OSError:
            continue
        for path in paths:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                found.append((mtime, path))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [path for _, path in found[:_MAX_FILES]]


class ActivityFieldCache:
    """Process-wide cursors plus the last assembled field (TTL
    `ACTIVITY_CACHE_TTL_SECONDS`). Refreshed off the request path by the
    cockpit's warm thread; a request that finds it stale refreshes it under
    the lock, which only reads bytes appended since the previous pass."""

    def __init__(self) -> None:
        self._cursors: dict[Path, _Cursor] = {}
        self._field: ActivityField | None = None
        self._lock = threading.Lock()

    def get(self, *, now: datetime | None = None, root: Path | None = None) -> ActivityField:
        moment = now if now is not None else datetime.now(UTC)
        with self._lock:
            cached = self._field
            if cached is not None and root is None:
                age = (moment - cached.generated_at).total_seconds()
                if 0 <= age < ACTIVITY_CACHE_TTL_SECONDS:
                    return cached
            built = self._refresh(moment, root if root is not None else quota.CLAUDE_PROJECTS_DIR)
            if root is None:
                self._field = built
            return built

    def _refresh(self, moment: datetime, root: Path) -> ActivityField:
        end_slot = _slot_of(moment)
        start_slot = end_slot - BUCKETS + 1
        window_start = datetime.fromtimestamp(start_slot * _BUCKET_SECONDS, tz=UTC)
        paths = _candidates(root, window_start)
        cursors: dict[Path, _Cursor] = {}
        for path in paths:
            cursor = _advance(path, self._cursors.get(path), start_slot)
            if cursor is None:
                continue
            for series in (cursor.calls, cursor.fresh):
                for slot in [s for s in series if s < start_slot]:
                    del series[slot]
            cursors[path] = cursor
        self._cursors = cursors

        calls = [0] * BUCKETS
        fresh = [0] * BUCKETS
        contributing = 0
        for cursor in cursors.values():
            if cursor.calls:
                contributing += 1
            for slot, count in cursor.calls.items():
                if start_slot <= slot <= end_slot:
                    calls[slot - start_slot] += count
            for slot, tokens in cursor.fresh.items():
                if start_slot <= slot <= end_slot:
                    fresh[slot - start_slot] += tokens
        return ActivityField(
            window_start=window_start,
            window_end=window_start + timedelta(minutes=BUCKET_MINUTES * BUCKETS),
            bucket_minutes=BUCKET_MINUTES,
            calls=tuple(calls),
            fresh=tuple(fresh),
            total_calls=sum(calls),
            peak_calls=max(calls),
            total_fresh=sum(fresh),
            peak_fresh=max(fresh),
            files=contributing,
            partial=any(cursor.partial for cursor in cursors.values()),
            generated_at=moment,
        )


_DEFAULT_ACTIVITY_CACHE = ActivityFieldCache()


def get_default_activity_cache() -> ActivityFieldCache:
    return _DEFAULT_ACTIVITY_CACHE


__all__ = [
    "ACTIVITY_CACHE_TTL_SECONDS",
    "BUCKETS",
    "BUCKET_MINUTES",
    "ActivityField",
    "ActivityFieldCache",
    "get_default_activity_cache",
]
