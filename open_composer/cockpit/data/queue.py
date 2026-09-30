"""The research task queue at a glance, for the Now page.

Since 2026-09-27 research runs through ``reports/research/control/
autonomous-queue.md`` (lead rounds write briefs, execution rounds run them,
results wait for review), not through the hypothesis-card lanes the Research
tile used to summarize. The owner (2026-09-30) found that tile out of step with
what the agents were actually doing; this reads the queue itself.

Only three things are parsed per task block: the ``### T-...`` header, the
``- status:`` line and the timestamp at the start of the newest dated note.
Everything shown is passed through ``secret_scrub``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from open_composer.cockpit.security import secret_scrub
from open_composer.config import project_root

QUEUE_PATH = ("reports", "research", "control", "autonomous-queue.md")
MAX_QUEUE_BYTES = 4_000_000
RECENT_ITEMS = 4
_TITLE_CHARS = 72
_NOTE_CHARS = 120

_HEADER_RE = re.compile(r"^### (T-\d{8}-\d+)\s+(.*)$")
_STATUS_RE = re.compile(r"^- status:\s*(.*)$")
_NOTE_RE = re.compile(r"^\s+- (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})(?: UTC)?\s*(.*)$")

#: Display order and labels of the open queue states (everything else is
#: `done` or `closed` and only counts towards `QueueGlance.total`).
QUEUE_STATES = ("running", "review", "ready", "blocked")
QUEUE_LABELS = {"running": "Running", "review": "To review", "ready": "Ready", "blocked": "Blocked"}
_DOTS = {"running": "ok", "review": "warn", "ready": "ready", "done": "ok"}


@dataclass(frozen=True)
class QueueItem:
    task_id: str
    title: str
    status: str  # running | review | ready | blocked | done | closed
    status_text: str
    updated_at: datetime | None
    last_note: str | None

    @property
    def dot(self) -> str:
        return _DOTS.get(self.status, "unknown")

    @property
    def label(self) -> str:
        return QUEUE_LABELS.get(self.status, self.status)


@dataclass(frozen=True)
class QueueGlance:
    available: bool
    counts: dict[str, int]
    total: int
    recent: tuple[QueueItem, ...]  # newest dated notes first, any state
    open: tuple[QueueItem, ...] = ()  # QUEUE_STATES order, newest first within one


def normalize_status(status_text: str) -> str:
    """Map a free-text ``- status:`` value onto the tile's states.

    ``done（待主审）`` (finished by an execution round, not yet reviewed) is
    ``review``; ``partial`` still has work left, so it counts as ``running``;
    ``superseded``/``cancelled``/anything else unknown is ``closed``."""
    text = status_text.strip()
    if "待主审" in text:
        return "review"
    head = re.split(r"[（(\s]", text, maxsplit=1)[0].lower()
    if head in ("ready", "running", "blocked", "done"):
        return head
    if head == "partial":
        return "running"
    return "closed"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_queue(text: str) -> list[QueueItem]:
    items: list[QueueItem] = []
    current: dict[str, object] | None = None

    def _flush() -> None:
        if current is None:
            return
        status_text = str(current.get("status") or "")
        items.append(
            QueueItem(
                task_id=str(current["id"]),
                title=secret_scrub(_clip(str(current["title"]), _TITLE_CHARS)),
                status=normalize_status(status_text),
                status_text=secret_scrub(_clip(status_text, 40)),
                updated_at=current.get("updated_at"),  # type: ignore[arg-type]
                last_note=current.get("note"),  # type: ignore[arg-type]
            )
        )

    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            _flush()
            current = {"id": header.group(1), "title": header.group(2)}
            continue
        if current is None:
            continue
        if line.startswith("## ") or line.startswith("# "):
            _flush()
            current = None
            continue
        status = _STATUS_RE.match(line)
        if status and "status" not in current:
            current["status"] = status.group(1)
            continue
        note = _NOTE_RE.match(line)
        if note:
            try:
                at = datetime.fromisoformat(f"{note.group(1)}T{note.group(2)}:{note.group(3)}")
            except ValueError:
                continue
            at = at.replace(tzinfo=UTC)
            previous = current.get("updated_at")
            if not isinstance(previous, datetime) or at >= previous:
                current["updated_at"] = at
                current["note"] = secret_scrub(_clip(note.group(4), _NOTE_CHARS))
    _flush()
    return items


def load_queue_glance(root: Path | None = None) -> QueueGlance:
    base = root or project_root()
    path = base.joinpath(*QUEUE_PATH)
    try:
        if path.stat().st_size > MAX_QUEUE_BYTES:
            return QueueGlance(available=False, counts={}, total=0, recent=())
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return QueueGlance(available=False, counts={}, total=0, recent=())
    items = parse_queue(text)
    counts = {state: 0 for state in QUEUE_STATES}
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
    epoch = datetime.min.replace(tzinfo=UTC)
    dated = [item for item in items if item.updated_at is not None]
    dated.sort(key=lambda item: item.updated_at or epoch, reverse=True)
    rank = {state: index for index, state in enumerate(QUEUE_STATES)}
    still_open = [item for item in items if item.status in rank]
    still_open.sort(key=lambda item: (item.updated_at or epoch).timestamp(), reverse=True)
    still_open.sort(key=lambda item: rank[item.status])
    return QueueGlance(
        available=True,
        counts=counts,
        total=len(items),
        recent=tuple(dated[:RECENT_ITEMS]),
        open=tuple(still_open),
    )


__all__ = [
    "QUEUE_LABELS",
    "QUEUE_STATES",
    "QueueGlance",
    "QueueItem",
    "load_queue_glance",
    "normalize_status",
    "parse_queue",
]
