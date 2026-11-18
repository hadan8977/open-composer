"""Saved process records: a PID plus its start time, so a reused PID is not mistaken for it."""

from __future__ import annotations

import os
from pathlib import Path


def _start(pid: int) -> tuple[int, bool]:
    """Start time of pid and whether it is still running; ProcessLookupError if gone."""
    if os.name == "nt":
        from open_composer.research.windows_runtime import process_start

        return process_start(pid)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        raise ProcessLookupError(pid) from None
    return int(fields[19]), fields[0] != "Z"


def identity(pid: int) -> dict:
    return {"pid": pid, "start_ticks": _start(pid)[0]}


def process_state(saved: dict) -> str:
    """'running' while the saved PID still names the same live process, else 'exited'."""
    try:
        start, alive = _start(saved["pid"])
    except ProcessLookupError:
        return "exited"
    return "running" if alive and start == saved.get("start_ticks") else "exited"
